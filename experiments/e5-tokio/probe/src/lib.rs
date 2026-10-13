use std::io::Write;
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicUsize, Ordering},
    Arc,
};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::signal::unix::{signal, SignalKind};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub type Work = Arc<dyn Fn(usize) -> std::result::Result<(), String> + Send + Sync>;

pub fn runtime() -> std::io::Result<tokio::runtime::Runtime> {
    tokio::runtime::Builder::new_current_thread()
        .enable_io()
        .enable_time()
        .max_blocking_threads(2)
        .thread_name("e5-blocking")
        .build()
}

fn proc_bits(name: &str) -> Result<u64> {
    let status = std::fs::read_to_string("/proc/thread-self/status")?;
    let value = status
        .lines()
        .find_map(|l| l.strip_prefix(name))
        .ok_or("missing signal status")?;
    Ok(u64::from_str_radix(value.trim(), 16)?)
}

fn masks() -> Result<()> {
    assert_eq!(
        proc_bits("SigBlk:")? & ((1 << 1) | (1 << 14)),
        0,
        "stop signals must be unblocked"
    );
    Ok(())
}

pub async fn tcp_once<F>(handler: F) -> Result<()>
where
    F: FnOnce(Vec<u8>) -> Vec<u8> + Send + 'static,
{
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
    let addr = listener.local_addr()?;
    let server = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut bytes = Vec::new();
        tokio::time::timeout(
            Duration::from_secs(2),
            (&mut socket).take(1025).read_to_end(&mut bytes),
        )
        .await
        .unwrap()
        .unwrap();
        assert!(bytes.len() <= 1024, "bounded request");
        let reply = tokio::task::spawn_blocking(move || handler(bytes))
            .await
            .unwrap();
        tokio::time::timeout(Duration::from_secs(2), socket.write_all(&reply))
            .await
            .unwrap()
            .unwrap();
        socket.shutdown().await.unwrap();
    });
    let mut client = tokio::net::TcpStream::connect(addr).await?;
    let body = r#"{"source":"a","dest":"b"}"#;
    client
        .write_all(
            format!(
                "POST /api/jobs HTTP/1.1\r\nContent-Length: {}\r\n\r\n{body}",
                body.len()
            )
            .as_bytes(),
        )
        .await?;
    client.shutdown().await?;
    let mut reply = Vec::new();
    tokio::time::timeout(
        Duration::from_secs(2),
        (&mut client).take(1025).read_to_end(&mut reply),
    )
    .await??;
    assert_eq!(
        reply,
        b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
    );
    server.await?;
    println!("PASS Tokio bounded async TCP accept/read/write, timeouts, blocking handoff and close-framed response");
    Ok(())
}

pub fn reply() -> Vec<u8> {
    b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}".to_vec()
}

async fn self_test(work: Work) -> Result<()> {
    let limit = Arc::new(tokio::sync::Semaphore::new(2));
    let active = Arc::new(AtomicUsize::new(0));
    let peak = Arc::new(AtomicUsize::new(0));
    let mut jobs = Vec::new();
    for i in 0..4 {
        let limit = limit.clone();
        let active = active.clone();
        let peak = peak.clone();
        let work = work.clone();
        jobs.push(tokio::spawn(async move {
            let permit = limit.acquire_owned().await.unwrap();
            tokio::task::spawn_blocking(move || {
                let n = active.fetch_add(1, Ordering::SeqCst) + 1;
                peak.fetch_max(n, Ordering::SeqCst);
                std::thread::sleep(Duration::from_millis(80));
                let result = work(i);
                active.fetch_sub(1, Ordering::SeqCst);
                drop(permit);
                result
            })
            .await
            .unwrap()
        }));
    }
    tokio::time::sleep(Duration::from_millis(20)).await;
    assert!(
        jobs.iter().any(|j| !j.is_finished()),
        "timer progresses while workers remain active"
    );
    for job in jobs {
        job.await??;
    }
    assert_eq!(peak.load(Ordering::SeqCst), 2);
    assert_eq!(active.load(Ordering::SeqCst), 0);
    let (tx, rx) = tokio::sync::oneshot::channel();
    let started = tokio::task::spawn_blocking(move || {
        tx.send(()).unwrap();
        std::thread::sleep(Duration::from_millis(40));
        7
    });
    rx.await?;
    started.abort();
    assert_eq!(
        started.await?,
        7,
        "abort must not be treated as stopping started work"
    );
    tcp_once(|bytes| {
        assert!(bytes.starts_with(b"POST /api/jobs "));
        reply()
    })
    .await?;
    println!("PASS current-thread timer/channel progress, semaphore admission, two blocking threads, started-blocking abort semantics and worker drain");
    Ok(())
}

async fn signals(mode: &str, work: Work) -> Result<usize> {
    let cycles = if mode == "cycle" { 3 } else { 1 };
    let mut completed = 0;
    for cycle in 0..cycles {
        masks()?;
        let mut term = signal(SignalKind::terminate())?;
        let mut interrupt = signal(SignalKind::interrupt())?;
        let (tx, mut rx) = tokio::sync::mpsc::channel(1);
        let tx2 = tx.clone();
        let a = tokio::spawn(async move {
            if term.recv().await.is_some() {
                let _ = tx.send(15).await;
            }
        });
        let b = tokio::spawn(async move {
            if interrupt.recv().await.is_some() {
                let _ = tx2.send(2).await;
            }
        });
        let stop = Arc::new(AtomicBool::new(false));
        let ticks = Arc::new(AtomicUsize::new(0));
        let ticking = ticks.clone();
        let ticker_stop = stop.clone();
        let ticker = tokio::spawn(async move {
            while !ticker_stop.load(Ordering::SeqCst) {
                tokio::time::sleep(Duration::from_millis(10)).await;
                ticking.fetch_add(1, Ordering::SeqCst);
            }
        });
        let worker = if mode == "active" {
            let work = work.clone();
            let stopped = stop.clone();
            let (ready_tx, ready_rx) = tokio::sync::oneshot::channel();
            let worker =
                tokio::task::spawn_blocking(move || -> std::result::Result<usize, String> {
                    masks().map_err(|e| e.to_string())?;
                    let mut n = 0;
                    let mut ready = Some(ready_tx);
                    while !stopped.load(Ordering::SeqCst) {
                        work(n)?;
                        n += 1;
                        if let Some(tx) = ready.take() {
                            let _ = tx.send(());
                        }
                        std::thread::sleep(Duration::from_millis(30));
                    }
                    Ok(n)
                });
            tokio::time::timeout(Duration::from_secs(5), ready_rx).await??;
            Some(worker)
        } else {
            None
        };
        println!("READY {} {} {cycle}", std::process::id(), mode);
        std::io::stdout().flush()?;
        let received = tokio::time::timeout(Duration::from_secs(15), rx.recv())
            .await?
            .ok_or("signal stream closed")?;
        stop.store(true, Ordering::SeqCst);
        if let Some(worker) = worker {
            let n = tokio::time::timeout(Duration::from_secs(5), worker).await???;
            assert!(n > 0);
            completed += n;
        }
        ticker.await?;
        a.abort();
        b.abort();
        let _ = a.await;
        let _ = b.await;
        assert_eq!(
            proc_bits("SigCgt:")? & ((1 << 1) | (1 << 14)),
            (1 << 1) | (1 << 14),
            "registered handlers remain after dropping streams"
        );
        // Keep the terminal fixture alive briefly so a burst exercises sticky
        // stop/coalescing without racing process exit between kill invocations.
        if mode == "active" {
            tokio::time::sleep(Duration::from_millis(80)).await;
        }
        println!("PASS signal {received} cycle={cycle} worker_drain={completed} ticks={} masks_unblocked handlers_process_global",ticks.load(Ordering::SeqCst));
    }
    Ok(completed)
}

pub fn run(mode: &str, work: Work) -> Result<usize> {
    masks()?;
    assert_ne!(
        proc_bits("SigIgn:")? & (1 << 12),
        0,
        "Rust startup SIGPIPE policy must remain ignored"
    );
    let (mut writer, reader) = std::os::unix::net::UnixStream::pair()?;
    drop(reader);
    assert_eq!(
        writer.write_all(b"x").unwrap_err().kind(),
        std::io::ErrorKind::BrokenPipe
    );
    println!("PASS SIGPIPE ignored and broken-pipe write returns an error");
    let rt = runtime()?;
    let n = if mode == "self" {
        rt.block_on(self_test(work))?;
        4
    } else {
        rt.block_on(signals(mode, work))?
    };
    rt.shutdown_timeout(Duration::from_secs(2));
    println!("PASS joined blocking work and explicit runtime shutdown");
    Ok(n)
}

pub fn file_work(directory: &Path) -> Result<Work> {
    std::fs::create_dir_all(directory)?;
    let directory = directory.to_owned();
    Ok(Arc::new(move |i| {
        let mut file =
            std::fs::File::create(directory.join(format!("job-{i}"))).map_err(|e| e.to_string())?;
        file.write_all(b"committed").map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())
    }))
}
