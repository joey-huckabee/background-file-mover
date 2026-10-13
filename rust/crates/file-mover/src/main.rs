use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let Some(path) = args.next() else {
        return Err("usage: file-mover CONFIG.json | --check-platform".into());
    };
    if path == "--transfer-one" {
        let config_path = args.next().ok_or("configuration path required")?;
        let job: i64 = args.next().ok_or("job ID required")?.parse()?;
        if args.next().is_some() {
            return Err("usage: file-mover --transfer-one CONFIG.json JOB_ID".into());
        }
        let config = read_config(&config_path)?;
        let store = mover_store::Store::open(&config.state_database)?;
        let result = mover_fs::transfer_one(&store, job)?;
        let committed = store
            .get(job)?
            .ok_or("unknown job")?
            .recording
            .is_committed();
        println!(
            "{}",
            serde_json::json!({"job_id":job.to_string(),"state":"Published","sha256":result.sha256,"size_bytes":result.stage.size,"source_retained":true,"committed":committed})
        );
        return Ok(());
    }
    if path == "--check-platform" && args.next().is_none() {
        println!("file-mover 0.1.0 local-claim prototype");
        return Ok(());
    }
    if args.next().is_some() {
        return Err("one configuration path required".into());
    }
    let config = read_config(&path)?;
    let stop = Arc::new(AtomicBool::new(false));
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?
        .block_on(async {
            let mut terminate =
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
            let terminate_stop = stop.clone();
            tokio::spawn(async move {
                if terminate.recv().await.is_some() {
                    terminate_stop.store(true, Ordering::Relaxed);
                }
            });
            let signal_stop = stop.clone();
            tokio::spawn(async move {
                if tokio::signal::ctrl_c().await.is_ok() {
                    signal_stop.store(true, Ordering::Relaxed);
                }
            });
            let listener = tokio::net::TcpListener::bind(config.bind).await?;
            println!("Listening on {}", listener.local_addr()?);
            file_mover::serve(listener, config, stop).await
        })
}

fn read_config(path: &str) -> Result<file_mover::Config, Box<dyn std::error::Error>> {
    use std::io::Read;
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(16385)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err("configuration too large".into());
    }
    let config: file_mover::Config = serde_json::from_slice(&bytes)?;
    config.validate()?;
    Ok(config)
}
