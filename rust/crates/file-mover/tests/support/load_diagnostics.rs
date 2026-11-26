//! Opt-in diagnostics for the sustained-load fixture only. No runtime changes.
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    io::{self, Read, Write},
    net::{SocketAddr, TcpStream},
    os::{fd::OwnedFd, unix::net::UnixStream},
    process::Stdio,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const STDERR_LIMIT: usize = 1024 * 1024;
const RESPONSE_LIMIT: u64 = 1024 * 1024;
#[derive(Default)]
struct Tail {
    bytes: VecDeque<u8>,
    omitted: usize,
    scan_tail: Vec<u8>,
    utf8_tail: Vec<u8>,
    invalid_utf8: bool,
    panicked: bool,
    retry_budget: bool,
    eof: bool,
    error: Option<String>,
}
impl Tail {
    fn append(&mut self, bytes: &[u8]) {
        // Preserve the original audit over the WHOLE stream, including markers
        // split across reads or evicted from the bounded diagnostic tail.
        let mut utf8 = std::mem::take(&mut self.utf8_tail);
        utf8.extend_from_slice(bytes);
        if let Err(error) = std::str::from_utf8(&utf8) {
            if error.error_len().is_none() {
                self.utf8_tail = utf8[error.valid_up_to()..].to_vec();
            } else {
                self.invalid_utf8 = true;
            }
        }
        let mut scan = std::mem::take(&mut self.scan_tail);
        scan.extend_from_slice(bytes);
        self.panicked |= scan.windows(b"panicked".len()).any(|w| w == b"panicked");
        self.retry_budget |= scan
            .windows(b"retry pass used".len())
            .any(|w| w == b"retry pass used");
        self.scan_tail = scan[scan.len().saturating_sub(14)..].to_vec();
        self.bytes.extend(bytes);
        let excess = self.bytes.len().saturating_sub(STDERR_LIMIT);
        self.bytes.drain(..excess);
        self.omitted += excess;
    }
    fn text(&self) -> String {
        String::from_utf8_lossy(&self.bytes.iter().copied().collect::<Vec<_>>()).into_owned()
    }
}
struct Reader {
    stop: Arc<AtomicBool>,
    handle: JoinHandle<()>,
}
pub(super) struct Diagnostics {
    address: SocketAddr,
    maximum_job: u64,
    tail: Arc<Mutex<Tail>>,
    reader: Mutex<Option<Reader>>,
    requests: Mutex<BTreeMap<String, String>>,
    statuses: Mutex<BTreeMap<u64, Value>>,
    reported: Mutex<BTreeSet<String>>,
}
impl Diagnostics {
    pub(super) fn new(address: SocketAddr, maximum_job: u64) -> Arc<Self> {
        Arc::new(Self {
            address,
            maximum_job,
            tail: Arc::new(Mutex::new(Tail::default())),
            reader: Mutex::new(None),
            requests: Mutex::new(BTreeMap::new()),
            statuses: Mutex::new(BTreeMap::new()),
            reported: Mutex::new(BTreeSet::new()),
        })
    }
    pub(super) fn stderr(&self) -> Stdio {
        Stdio::from(self.captured_fd())
    }
    fn captured_fd(&self) -> OwnedFd {
        // A socketpair supplies stdlib read timeouts: no fcntl/dependency or
        // indefinitely blocked pipe-reader join if a descendant retains stderr.
        let (mut read, write) = UnixStream::pair().unwrap();
        read.set_read_timeout(Some(Duration::from_millis(100)))
            .unwrap();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let tail = self.tail.clone();
        self.tail.lock().unwrap().eof = false;
        let handle = thread::Builder::new()
            .name("sustained-load-stderr".into())
            .spawn(move || {
                let mut bytes = [0; 4096];
                let mut stopping_at = None;
                loop {
                    if stopping.load(Ordering::Acquire) {
                        let since = stopping_at.get_or_insert_with(Instant::now);
                        if since.elapsed() >= Duration::from_secs(1) {
                            break;
                        }
                    }
                    match read.read(&mut bytes) {
                        Ok(0) => {
                            tail.lock().unwrap().eof = true;
                            break;
                        }
                        Ok(n) => tail.lock().unwrap().append(&bytes[..n]),
                        Err(e)
                            if matches!(
                                e.kind(),
                                io::ErrorKind::WouldBlock
                                    | io::ErrorKind::TimedOut
                                    | io::ErrorKind::Interrupted
                            ) => {}
                        Err(e) => {
                            tail.lock().unwrap().error = Some(e.to_string());
                            break;
                        }
                    }
                }
            })
            .unwrap();
        *self.reader.lock().unwrap() = Some(Reader { stop, handle });
        write.into()
    }
    pub(super) fn finish(&self) {
        let reader = self.reader.lock().unwrap_or_else(|e| e.into_inner()).take();
        if let Some(reader) = reader {
            reader.stop.store(true, Ordering::Release);
            let _ = reader.handle.join();
        }
    }
    pub(super) fn captured_text(&self) -> String {
        self.tail.lock().unwrap_or_else(|e| e.into_inner()).text()
    }
    pub(super) fn audit_stderr(&self) -> io::Result<String> {
        self.finish();
        let tail = self.tail.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(error) = &tail.error {
            return Err(io::Error::other(error.clone()));
        }
        if !tail.eof {
            return Err(io::Error::other("captured stderr did not reach EOF"));
        }
        if tail.invalid_utf8 || !tail.utf8_tail.is_empty() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "service stderr was not UTF-8",
            ));
        }
        let mut text = tail.text();
        if tail.panicked {
            text.push_str("\n[whole-stream audit: panicked]\n");
        }
        if tail.retry_budget {
            text.push_str("\n[whole-stream audit: retry pass used]\n");
        }
        Ok(text)
    }
    pub(super) fn request(&self, input: &Value) {
        let thread = format!("{:?}", thread::current().id());
        let recording = input["recording_id"]
            .as_str()
            .unwrap_or("<missing recording_id>");
        // One entry per test/sender thread (seven), updated once per ready()
        // call, never once per service_busy retry.
        self.requests
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .insert(thread, recording.to_owned());
    }
    pub(super) fn remember(&self, id: &str, status: &Value) {
        if let Ok(id) = id.parse::<u64>()
            && (1..=self.maximum_job).contains(&id)
        {
            self.statuses
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .insert(id, status.clone());
        }
    }
    pub(super) fn on_panic(self: &Arc<Self>) -> PanicReport {
        PanicReport(self.clone())
    }
    fn print_stderr(&self) {
        let tail = self.tail.lock().unwrap_or_else(|e| e.into_inner());
        eprintln!(
            "SUSTAINED_FAILURE service stderr so far (tail limit={STDERR_LIMIT}, omitted_bytes={}, eof={}, reader_error={:?}):\n{}",
            tail.omitted,
            tail.eof,
            tail.error,
            tail.text()
        );
    }
    pub(super) fn report(&self, reason: &str) {
        // A bad reply is printed before panic; its unwind guard must not
        // duplicate it. Other failing threads still get their own snapshot.
        let thread = format!("{:?}", thread::current().id());
        if !self
            .reported
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .insert(thread)
        {
            return;
        }
        eprintln!(
            "SUSTAINED_FAILURE {reason}; last recording_id by thread: {:?}",
            self.requests.lock().unwrap_or_else(|e| e.into_inner())
        );
        // Print logs first, even if the service has exited or status is stuck.
        self.print_stderr();
        let target = self
            .requests
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .get(&format!("{:?}", thread::current().id()))
            .cloned();
        for (id, status) in self
            .statuses
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .iter()
        {
            eprintln!(
                "SUSTAINED_FAILURE cached job_id={id} recording_id={} full_status={status}",
                status["details"]["recording_id"]
            );
        }
        // A producer error need not disclose job_id. This fresh fixture has at
        // most 29 jobs: enumerate its bounded ID range, without a resend or
        // writable Store open. Keep the entire status JSON, including problems,
        // missing files and per-file claim/transfer phases, without projection.
        let until = Instant::now() + Duration::from_secs(5);
        for id in 1..=self.maximum_job {
            if Instant::now() >= until {
                eprintln!("SUSTAINED_FAILURE status deadline reached before job_id={id}");
                break;
            }
            match diagnostic_status(self.address, id, until) {
                Ok((code, body)) => {
                    if code == 200 {
                        self.remember(&id.to_string(), &body);
                    }
                    if target
                        .as_deref()
                        .is_some_and(|uuid| body["details"]["recording_id"].as_str() == Some(uuid))
                    {
                        eprintln!(
                            "SUSTAINED_FAILURE target recording_id={} resolved_job_id={id}",
                            body["details"]["recording_id"]
                        );
                    }
                    eprintln!(
                        "SUSTAINED_FAILURE GET job_id={id} recording_id={} http={code} full_status={body}",
                        body["details"]["recording_id"]
                    );
                }
                Err(e) => eprintln!("SUSTAINED_FAILURE GET job_id={id} unavailable: {e}"),
            }
        }
        self.print_stderr();
    }
}
impl Drop for Diagnostics {
    fn drop(&mut self) {
        self.finish();
    }
}
pub(super) struct PanicReport(Arc<Diagnostics>);
impl Drop for PanicReport {
    fn drop(&mut self) {
        if thread::panicking() {
            self.0.report("test/sender panic (before service teardown)");
        }
    }
}
fn diagnostic_status(address: SocketAddr, id: u64, until: Instant) -> io::Result<(u16, Value)> {
    let timeout = until
        .saturating_duration_since(Instant::now())
        .min(Duration::from_millis(250));
    if timeout.is_zero() {
        return Err(io::Error::other("diagnostic deadline"));
    }
    let mut stream = TcpStream::connect_timeout(&address, timeout)?;
    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;
    write!(
        stream,
        "GET /api/v2/jobs/{id} HTTP/1.1\r\nHost: localhost\r\n\r\n"
    )?;
    let mut raw = Vec::new();
    let mut chunk = [0; 4096];
    loop {
        if Instant::now() >= until {
            return Err(io::Error::other("diagnostic deadline"));
        }
        let n = stream.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        if raw.len() as u64 + n as u64 > RESPONSE_LIMIT {
            return Err(io::Error::other("status response too large"));
        }
        raw.extend_from_slice(&chunk[..n]);
    }
    let split = raw
        .windows(4)
        .position(|s| s == b"\r\n\r\n")
        .ok_or_else(|| io::Error::other("invalid status framing"))?;
    let head = std::str::from_utf8(&raw[..split]).map_err(io::Error::other)?;
    let code = head
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| io::Error::other("missing status code"))?
        .parse()
        .map_err(io::Error::other)?;
    let body = serde_json::from_slice(&raw[split + 4..]).map_err(io::Error::other)?;
    Ok((code, body))
}

#[test]
fn stderr_tail_is_bounded_and_preserves_evicted_split_audit_markers() {
    let mut tail = Tail::default();
    tail.append(b"panic");
    tail.append(b"ked retry pass us");
    tail.append(b"ed");
    tail.append(&vec![b'x'; STDERR_LIMIT]);
    assert_eq!(tail.bytes.len(), STDERR_LIMIT);
    assert!(tail.omitted > 0);
    assert!(tail.panicked && tail.retry_budget);
    assert!(!tail.text().contains("panicked"));
    tail.append(&[0xc3]);
    tail.append(&[0xa9]); // A valid character split across reads.
    assert!(!tail.invalid_utf8 && tail.utf8_tail.is_empty());
    tail.append(&[0xff]);
    assert!(tail.invalid_utf8);
}
#[test]
fn stderr_reader_drains_before_join_and_preserves_capture_across_service_runs() {
    let diagnostics = Diagnostics::new("127.0.0.1:1".parse().unwrap(), 1);
    for text in [b"first\n".as_slice(), b"second\n"] {
        let fd = diagnostics.captured_fd();
        let mut writer = std::fs::File::from(fd);
        writer.write_all(text).unwrap();
        drop(writer);
        diagnostics.finish();
    }
    assert_eq!(diagnostics.audit_stderr().unwrap(), "first\nsecond\n");
}

#[test]
fn status_capture_preserves_the_full_json_body() {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    listener.set_nonblocking(true).unwrap();
    let body = serde_json::json!({"job_id":"3","details":{
        "recording_id":"fixture-uuid","problem":{"errno":28},
        "missing":[{"file_id":"0"}],"claims":[{"complete":false}],
        "transfers":[{"phase":"Intent"}],"extra":"must not be projected away"}});
    let expected = body.clone();
    let server = thread::spawn(move || {
        let until = Instant::now() + Duration::from_secs(2);
        let mut stream = loop {
            match listener.accept() {
                Ok((stream, _)) => break stream,
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                    assert!(Instant::now() < until, "diagnostic client did not connect");
                    thread::sleep(Duration::from_millis(5));
                }
                Err(e) => panic!("diagnostic listener: {e}"),
            }
        };
        stream
            .set_read_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        let mut request = Vec::new();
        while !request.ends_with(b"\r\n\r\n") {
            let mut byte = [0];
            stream.read_exact(&mut byte).unwrap();
            request.push(byte[0]);
            assert!(request.len() <= 1024);
        }
        assert!(request.starts_with(b"GET /api/v2/jobs/3 HTTP/1.1"));
        let body = body.to_string();
        write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        )
        .unwrap();
    });
    let response = diagnostic_status(address, 3, Instant::now() + Duration::from_secs(2));
    server.join().unwrap();
    assert_eq!(response.unwrap(), (200, expected));
}
#[test]
fn retained_stderr_descriptor_does_not_prevent_reader_exit_or_pass_a_partial_audit() {
    let diagnostics = Diagnostics::new("127.0.0.1:1".parse().unwrap(), 1);
    let _still_open = diagnostics.captured_fd();
    let start = Instant::now();
    diagnostics.finish();
    assert!(start.elapsed() < Duration::from_secs(3));
    assert!(diagnostics.audit_stderr().is_err());
}
