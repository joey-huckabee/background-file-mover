use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicUsize, Ordering},
    Arc,
};
use std::time::{Duration, Instant};

const MAX_HEAD: usize = 8192;
const MAX_BODY: usize = 65536;

#[derive(Debug)]
pub struct Head {
    pub method: String,
    pub target: Vec<u8>,
    pub headers: BTreeMap<String, Vec<u8>>,
    pub consumed: usize,
}
#[derive(Debug)]
pub enum HeadResult {
    Complete(Head),
    NeedMore,
    Bad,
    TooLarge,
}
#[derive(Debug)]
pub struct Request {
    pub head: Head,
    pub body: Vec<u8>,
}
#[derive(Debug)]
pub enum Frame {
    Complete(Request),
    NeedMore,
    Reject(u16),
}

pub fn head(input: &[u8], max_head: usize) -> HeadResult {
    let window = &input[..input.len().min(max_head.saturating_add(4))];
    let Some(end) = window.windows(4).position(|w| w == b"\r\n\r\n") else {
        return if input.len() > max_head {
            HeadResult::TooLarge
        } else {
            HeadResult::NeedMore
        };
    };
    let consumed = end + 4;
    if consumed > max_head {
        return HeadResult::TooLarge;
    }
    let bytes = &input[..consumed];
    // httparse permits bare LF and leading empty lines. Preserve strict CRLF.
    for (i, b) in bytes.iter().enumerate() {
        if (*b == b'\n' && (i == 0 || bytes[i - 1] != b'\r'))
            || (*b == b'\r' && bytes.get(i + 1) != Some(&b'\n'))
        {
            return HeadResult::Bad;
        }
    }
    let line_end = bytes.windows(2).position(|w| w == b"\r\n").unwrap();
    let parts: Vec<_> = bytes[..line_end].split(|b| *b == b' ').collect();
    if parts.len() != 3
        || parts[0].is_empty()
        || parts[0].len() > 16
        || !parts[0].iter().all(u8::is_ascii_uppercase)
        || parts[1].first() != Some(&b'/')
        || parts[1].iter().any(|b| *b <= 0x20 || *b == 0x7f)
        || !matches!(parts[2], b"HTTP/1.0" | b"HTTP/1.1")
    {
        return HeadResult::Bad;
    }
    let mut slots = [httparse::EMPTY_HEADER; 64];
    let mut parsed = httparse::Request::new(&mut slots);
    // C++ accepts arbitrary non-control target bytes, but httparse exposes a
    // UTF-8 &str. Validate original bytes above; substitute only non-ASCII
    // target bytes in a bounded temporary head for upstream syntax parsing.
    // Offsets stay identical and the returned target always uses original bytes.
    let mut sanitized;
    let parser_input = if std::str::from_utf8(parts[1]).is_err() {
        sanitized = bytes.to_vec();
        let start = parts[0].len() + 1;
        for b in &mut sanitized[start..start + parts[1].len()] {
            if !b.is_ascii() {
                *b = b'?';
            }
        }
        sanitized.as_slice()
    } else {
        bytes
    };
    match parsed.parse(parser_input) {
        Ok(httparse::Status::Complete(n)) if n == consumed => (),
        _ => return HeadResult::Bad,
    }
    let mut headers = BTreeMap::new();
    for header in parsed.headers.iter() {
        if !header
            .name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
        {
            return HeadResult::Bad;
        }
        let name = header.name.to_ascii_lowercase();
        let value = header.value;
        let start = value
            .iter()
            .position(|b| !matches!(b, b' ' | b'\t'))
            .unwrap_or(value.len());
        let end = value
            .iter()
            .rposition(|b| !matches!(b, b' ' | b'\t'))
            .map_or(start, |i| i + 1);
        let value = &value[start..end];
        if value.iter().any(|b| *b < 0x20 || *b == 0x7f) || headers.contains_key(&name) {
            return HeadResult::Bad;
        }
        headers.insert(name, value.to_vec());
    }
    HeadResult::Complete(Head {
        method: parsed.method.unwrap().into(),
        target: parts[1].to_vec(),
        headers,
        consumed,
    })
}

pub fn content_length(h: &Head) -> Result<usize, u16> {
    if h.headers.contains_key("transfer-encoding") {
        return Err(400);
    }
    let Some(value) = h.headers.get("content-length") else {
        return Ok(0);
    };
    if value.is_empty() {
        return Err(400);
    }
    let mut n = 0_u64;
    for b in value {
        if !b.is_ascii_digit() {
            return Err(400);
        }
        n = n
            .checked_mul(10)
            .and_then(|n| n.checked_add(u64::from(*b - b'0')))
            .ok_or(413_u16)?;
    }
    if n > MAX_BODY as u64 {
        return Err(413);
    }
    Ok(n as usize)
}

pub fn frame(input: &[u8]) -> Frame {
    match head(input, MAX_HEAD) {
        HeadResult::NeedMore => Frame::NeedMore,
        HeadResult::Bad => Frame::Reject(400),
        HeadResult::TooLarge => Frame::Reject(431),
        HeadResult::Complete(head) => match content_length(&head) {
            Err(status) => Frame::Reject(status),
            Ok(n) if input.len() < head.consumed + n => Frame::NeedMore,
            Ok(n) if input.len() > head.consumed + n => Frame::Reject(400),
            Ok(_) => {
                let body = input[head.consumed..].to_vec();
                Frame::Complete(Request { head, body })
            }
        },
    }
}

fn signature(input: &[u8]) -> String {
    match head(input, MAX_HEAD) {
        HeadResult::NeedMore => "NEED_MORE".into(),
        HeadResult::Bad => "BAD".into(),
        HeadResult::TooLarge => "TOO_LARGE".into(),
        HeadResult::Complete(h) => match content_length(&h) {
            Ok(n) => format!("OK:{}:{n}", h.consumed),
            Err(status) => format!("CL:{status}"),
        },
    }
}

pub fn exercise(corpus: &Path) -> Result<(), Box<dyn std::error::Error>> {
    println!(
        "CPU runtime SSE4.2={} AVX2={}",
        std::is_x86_feature_detected!("sse4.2"),
        std::is_x86_feature_detected!("avx2")
    );
    println!(
        "CPU_BUILD {}",
        if cfg!(httparse_disable_simd = "1") {
            "SIMD disabled/SWAR"
        } else {
            "baseline x86-64 with runtime dispatch"
        }
    );
    let expected = std::fs::read_to_string(corpus.join("oracle.tsv"))?;
    let mut seeds = Vec::new();
    let mut count = 0;
    for line in expected.lines() {
        let (name, verdict) = line.split_once('\t').ok_or("oracle row")?;
        let bytes = std::fs::read(corpus.join(name))?;
        assert_eq!(signature(&bytes), verdict, "C++ corpus {name}");
        seeds.push(bytes);
        count += 1;
    }
    assert_eq!(count, 37);
    println!("PASS 37 HTTP corpus head/consumed-length/Content-Length outcomes match C++");
    let policy = std::fs::read_to_string(corpus.join("policy.tsv"))?;
    for line in policy.lines() {
        let (name, verdict) = line.split_once('\t').ok_or("policy oracle row")?;
        let bytes = std::fs::read(corpus.join(name))?;
        assert_eq!(signature(&bytes), verdict, "C++ policy {name}");
    }
    let HeadResult::Complete(raw) = head(b"GET /\xff HTTP/1.1\r\n\r\n", MAX_HEAD) else {
        panic!("raw target")
    };
    assert_eq!(raw.target, b"/\xff");
    println!("PASS raw non-UTF8 target bytes preserved with bounded upstream parsing adapter");
    let valid = b"POST /api/jobs HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\n\r\n";
    for n in 0..valid.len() {
        assert!(matches!(head(&valid[..n], MAX_HEAD), HeadResult::NeedMore));
    }
    assert!(matches!(frame(valid), Frame::NeedMore));
    let mut body = valid.to_vec();
    body.extend_from_slice(b"{}");
    assert!(matches!(frame(&body), Frame::Complete(_)));
    body.push(b'x');
    assert!(matches!(frame(&body), Frame::Reject(400)));
    let pipeline = b"GET / HTTP/1.1\r\n\r\nGET / HTTP/1.1\r\n\r\n";
    assert!(matches!(frame(pipeline), Frame::Reject(400)));
    for invalid in [
        b"GET / HTTP/1.1\nX: y\r\n\r\n".as_slice(),
        b"\r\nGET / HTTP/1.1\r\n\r\n",
        b"GET  / HTTP/1.1\r\n\r\n",
        b"GET / HTTP/1.1\r\nX: a\tb\r\n\r\n",
        b"GET / HTTP/1.1\r\nX: y\r\nx: z\r\n\r\n",
        b"GET / HTTP/1.1\r\nX: y\r\n folded\r\n\r\n",
        b"GET / HTTP/1.1\r\nX!: y\r\n\r\n",
    ] {
        assert!(matches!(head(invalid, MAX_HEAD), HeadResult::Bad));
    }
    let HeadResult::Complete(h) = head(b"GET / HTTP/1.0\r\nMiXeD: \t v \t\r\n\r\n", MAX_HEAD)
    else {
        panic!("normalization")
    };
    assert_eq!(h.headers["mixed"], b"v");
    assert_eq!(content_length(&h), Ok(0));
    for (value, status) in [
        ("0", 0),
        ("0002", 0),
        ("65536", 0),
        ("65537", 413),
        ("18446744073709551616", 413),
        ("", 400),
        ("+2", 400),
        ("-2", 400),
        ("2,2", 400),
        ("0x10", 400),
        ("2.0", 400),
    ] {
        let text = format!("POST / HTTP/1.1\r\nContent-Length: {value}\r\n\r\n");
        let HeadResult::Complete(h) = head(text.as_bytes(), MAX_HEAD) else {
            panic!("CL head")
        };
        assert_eq!(content_length(&h).err().unwrap_or(0), status, "CL {value}");
    }
    for encoding in ["", "identity", "chunked", "gzip"] {
        let text = format!(
            "POST / HTTP/1.1\r\nTransfer-Encoding: {encoding}\r\nContent-Length: 0\r\n\r\n"
        );
        assert!(matches!(frame(text.as_bytes()), Frame::Reject(400)));
    }
    for count in [64, 65] {
        let mut text = "GET / HTTP/1.1\r\n".to_string();
        for i in 0..count {
            text.push_str(&format!("h{i}: v\r\n"));
        }
        text.push_str("\r\n");
        assert_eq!(
            matches!(head(text.as_bytes(), MAX_HEAD), HeadResult::Complete(_)),
            count == 64
        );
    }
    let prefix = "GET / HTTP/1.1\r\nX: ";
    for size in [8192, 8193] {
        let text = format!("{prefix}{}\r\n\r\n", "x".repeat(size - prefix.len() - 4));
        assert_eq!(
            matches!(head(text.as_bytes(), MAX_HEAD), HeadResult::Complete(_)),
            size == 8192
        );
        assert_eq!(
            matches!(head(&vec![b'x'; size], MAX_HEAD), HeadResult::TooLarge),
            size == 8193
        );
    }
    let mut full = b"POST / HTTP/1.1\r\nContent-Length: 65536\r\n\r\n".to_vec();
    full.extend(vec![b'x'; 65536]);
    assert!(matches!(frame(&full), Frame::Complete(_)));
    println!("PASS every proper prefix, exact head/header/body bounds, CRLF/token policy, normalized headers, duplicate/TE/CL rejection, body completeness and extra/pipelined bytes");
    let mut state = 0xE4_2026_u64;
    for i in 0..10000 {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        let mut bytes = seeds[i % seeds.len()].clone();
        let offset = state as usize % (bytes.len() + 1);
        match i % 3 {
            0 => bytes.insert(offset, (state >> 32) as u8),
            1 if offset < bytes.len() => {
                bytes.remove(offset);
            }
            _ if offset < bytes.len() => bytes[offset] ^= (state >> 32) as u8,
            _ => bytes.push(0),
        }
        if let HeadResult::Complete(h) = head(&bytes, MAX_HEAD) {
            assert!(h.consumed <= bytes.len());
            assert!(h.headers.len() <= 64);
        }
        let _ = frame(&bytes);
    }
    println!("PASS 10000 deterministic HTTP corpus mutations without panic");
    Ok(())
}

fn response(stream: &mut TcpStream, code: u16) -> std::io::Result<()> {
    let reason = match code {
        200 => "OK",
        201 => "Created",
        400 => "Bad Request",
        408 => "Request Timeout",
        413 => "Payload Too Large",
        431 => "Request Header Fields Too Large",
        503 => "Service Unavailable",
        _ => "Internal Server Error",
    };
    stream.set_write_timeout(Some(Duration::from_millis(200)))?;
    stream.write_all(format!("HTTP/1.1 {code} {reason}\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}",).as_bytes())?;
    stream.shutdown(Shutdown::Write)
}

fn receive(stream: &mut TcpStream) -> Frame {
    let deadline = Instant::now() + Duration::from_millis(200);
    let mut input = Vec::new();
    let mut buffer = [0_u8; 1024];
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Frame::Reject(408);
        }
        if stream.set_read_timeout(Some(remaining)).is_err() {
            return Frame::Reject(400);
        }
        match stream.read(&mut buffer) {
            Ok(0) => return Frame::Reject(400),
            Ok(n) => {
                if input.len() + n > MAX_HEAD + MAX_BODY {
                    return Frame::Reject(413);
                }
                input.extend_from_slice(&buffer[..n]);
                match frame(&input) {
                    Frame::NeedMore => (),
                    verdict => return verdict,
                }
            }
            Err(e)
                if matches!(
                    e.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                return Frame::Reject(408)
            }
            Err(_) => return Frame::Reject(400),
        }
    }
}

fn read_status(stream: &mut TcpStream) -> Result<u16, Box<dyn std::error::Error>> {
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    let mut bytes = Vec::new();
    stream.read_to_end(&mut bytes)?;
    let mut headers = [httparse::EMPTY_HEADER; 8];
    let mut parsed = httparse::Response::new(&mut headers);
    let httparse::Status::Complete(n) = parsed.parse(&bytes)? else {
        return Err("partial response".into());
    };
    assert_eq!(&bytes[n..], b"{}");
    assert!(parsed
        .headers
        .iter()
        .any(|h| h.name.eq_ignore_ascii_case("Connection") && h.value == b"close"));
    assert!(parsed
        .headers
        .iter()
        .any(|h| h.name.eq_ignore_ascii_case("Content-Length") && h.value == b"2"));
    Ok(parsed.code.unwrap())
}

pub fn exercise_tcp<F>(handler: F, json_policy: bool) -> Result<(), Box<dyn std::error::Error>>
where
    F: Fn(&Request) -> u16 + Send + Sync + 'static,
{
    let listener = TcpListener::bind("127.0.0.1:0")?;
    listener.set_nonblocking(true)?;
    let address = listener.local_addr()?;
    let stop = Arc::new(AtomicBool::new(false));
    let active = Arc::new(AtomicUsize::new(0));
    let peak = Arc::new(AtomicUsize::new(0));
    let worker_stop = stop.clone();
    let worker_active = active.clone();
    let worker_peak = peak.clone();
    let handler = Arc::new(handler);
    let server = std::thread::spawn(move || {
        let mut workers: Vec<std::thread::JoinHandle<()>> = Vec::new();
        let end = Instant::now() + Duration::from_secs(10);
        while !worker_stop.load(Ordering::SeqCst) && Instant::now() < end {
            let mut i = 0;
            while i < workers.len() {
                if workers[i].is_finished() {
                    workers.swap_remove(i).join().unwrap();
                } else {
                    i += 1;
                }
            }
            match listener.accept() {
                Ok((mut stream, _)) => {
                    if workers.len() >= 4 {
                        let _ = response(&mut stream, 503);
                        continue;
                    }
                    let count = worker_active.fetch_add(1, Ordering::SeqCst) + 1;
                    if count > 4 {
                        worker_active.fetch_sub(1, Ordering::SeqCst);
                        let _ = response(&mut stream, 503);
                        continue;
                    }
                    worker_peak.fetch_max(count, Ordering::SeqCst);
                    let active = worker_active.clone();
                    let handler = handler.clone();
                    workers.push(std::thread::spawn(move || {
                        let status = match receive(&mut stream) {
                            Frame::Complete(r) => handler(&r),
                            Frame::Reject(code) => code,
                            Frame::NeedMore => 500,
                        };
                        let _ = response(&mut stream, status);
                        active.fetch_sub(1, Ordering::SeqCst);
                    }));
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(1))
                }
                Err(e) => panic!("accept: {e}"),
            }
        }
        for worker in workers {
            worker.join().unwrap();
        }
    });
    let exchange = |bytes: &[u8]| -> Result<u16, Box<dyn std::error::Error>> {
        let mut stream = TcpStream::connect(address)?;
        stream.write_all(bytes)?;
        stream.shutdown(Shutdown::Write)?;
        read_status(&mut stream)
    };
    let get = b"GET /api/status HTTP/1.1\r\n\r\n";
    for (bytes, status) in [
        (b"GET / HTTP/1.1\r\nX: a\r\nx: b\r\n\r\n".as_slice(), 400),
        (
            b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n",
            400,
        ),
        (b"POST / HTTP/1.1\r\nContent-Length: 65537\r\n\r\n", 413),
        (b"POST / HTTP/1.1\r\nContent-Length: 2\r\n\r\n{}x", 400),
        (b"POST / HTTP/1.1\r\nContent-Length: 3\r\n\r\nx", 400),
    ] {
        assert_eq!(exchange(bytes)?, status);
    }
    let mut slow = TcpStream::connect(address)?;
    let start = Instant::now();
    slow.write_all(b"G")?;
    assert_eq!(
        exchange(get)?,
        200,
        "valid request must progress alongside slow client"
    );
    std::thread::sleep(Duration::from_millis(80));
    slow.write_all(b"E")?;
    std::thread::sleep(Duration::from_millis(80));
    slow.write_all(b"T")?;
    assert_eq!(read_status(&mut slow)?, 408);
    assert!(
        start.elapsed() < Duration::from_millis(800),
        "dribbled bytes must not reset deadline"
    );
    let mut blockers = Vec::new();
    for _ in 0..4 {
        blockers.push(TcpStream::connect(address)?);
    }
    let admission_deadline = Instant::now() + Duration::from_millis(100);
    while active.load(Ordering::SeqCst) < 4 && Instant::now() < admission_deadline {
        std::thread::sleep(Duration::from_millis(1));
    }
    assert_eq!(active.load(Ordering::SeqCst), 4);
    let mut excess = TcpStream::connect(address)?;
    assert_eq!(
        read_status(&mut excess)?,
        503,
        "bounded connection admission"
    );
    for mut blocker in blockers {
        blocker.shutdown(Shutdown::Write)?;
        assert_eq!(read_status(&mut blocker)?, 400);
    }
    let post = |body: &str| {
        format!(
            "POST /api/jobs HTTP/1.1\r\nContent-Length: {}\r\n\r\n{body}",
            body.len()
        )
    };
    if json_policy {
        assert_eq!(
            exchange(post(r#"{"source":null,"dest":"b"}"#).as_bytes())?,
            400
        );
    }
    assert_eq!(
        exchange(post(r#"{"source":"a","dest":"b"}"#).as_bytes())?,
        201
    );
    assert_eq!(exchange(get)?, 200, "listener survives hostile clients");
    stop.store(true, Ordering::SeqCst);
    server.join().map_err(|_| "TCP server panic")?;
    assert_eq!(active.load(Ordering::SeqCst), 0);
    assert!(peak.load(Ordering::SeqCst) <= 4);
    println!("PASS bounded loopback TCP: bad framing/TE/oversize/extra/truncated bodies, absolute slow-client deadline, concurrent valid progress, bounded worker admission/reaping, request/response framing and continued service; peak_workers={}",peak.load(Ordering::SeqCst));
    Ok(())
}
