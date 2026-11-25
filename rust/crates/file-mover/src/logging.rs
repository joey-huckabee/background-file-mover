//! Lossy diagnostic sinks, independent of transfer authority and lifetime guards.
use serde::{Deserialize, Serialize};
use std::{
    io::Write,
    path::Path,
    sync::{
        Arc, Mutex, OnceLock,
        atomic::{AtomicBool, AtomicU8, AtomicU64, Ordering},
        mpsc,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const CAPACITY: usize = 1024;
const SHUTDOWN: Duration = Duration::from_millis(250);
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Level {
    #[default]
    Off,
    Error,
    Warn,
    Info,
    Debug,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Logging {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub level: Level,
    #[serde(default)]
    pub file: Option<String>,
    #[serde(default = "bytes_default")]
    pub max_file_bytes: u64,
    #[serde(default = "files_default")]
    pub max_files: u32,
}
fn bytes_default() -> u64 {
    64 * 1024 * 1024
}
fn files_default() -> u32 {
    16
}
impl Default for Logging {
    fn default() -> Self {
        Self {
            enabled: false,
            level: Level::Off,
            file: None,
            max_file_bytes: bytes_default(),
            max_files: files_default(),
        }
    }
}
impl Logging {
    pub fn active(&self) -> bool {
        self.enabled && self.level != Level::Off
    }
    pub(crate) fn validate(&self) -> Result<(), &'static str> {
        if !(65536..=1073741824).contains(&self.max_file_bytes)
            || !(1..=20).contains(&self.max_files)
            || self
                .max_file_bytes
                .checked_mul(u64::from(self.max_files))
                .is_none_or(|v| v > 1073741824)
        {
            return Err("invalid logging rotation budget");
        }
        if self.active() && self.file.is_none() {
            return Err("enabled logging requires an absolute file path");
        }
        if let Some(file) = &self.file {
            if !file.starts_with('/')
                || file.len() > 4095
                || file[1..].split('/').any(|p| {
                    p.is_empty()
                        || p == "."
                        || p == ".."
                        || p.contains('\\')
                        || p.chars().any(char::is_control)
                })
                || Path::new(file).file_name().is_none_or(|n| n.len() > 240)
                || file.len() + 5 > 4095
                || Path::new(file).parent() == Some(Path::new("/"))
            {
                return Err("invalid logging file path");
            }
        }
        Ok(())
    }
    pub(crate) fn exclude(&self, scope: &str) -> Result<(), &'static str> {
        if let Some(file) = &self.file {
            let parent = Path::new(file).parent().ok_or("logging parent required")?;
            let scope = Path::new(scope);
            if parent.starts_with(scope) || scope.starts_with(parent) {
                return Err("logging parent overlaps protected scope");
            }
        }
        Ok(())
    }
    pub(crate) fn validate_config(&self, c: &crate::Config) -> Result<(), &'static str> {
        self.validate()?;
        if self.file.is_none() {
            return Ok(());
        }
        for scope in [&c.source_root, &c.destination_root] {
            self.exclude(scope)?;
        }
        self.exclude(
            Path::new(&c.state_database)
                .parent()
                .and_then(Path::to_str)
                .ok_or("state parent required")?,
        )?;
        let mut paths = Vec::new();
        if let Some(i) = &c.protected_ingress {
            paths.extend([i.producer_socket.as_str(), i.operator_socket.as_str()]);
        }
        if let Some(i) = &c.native_ingress {
            paths.push(i.operator_socket());
            paths.extend(i.credential_paths());
        }
        if let Some(i) = &c.admin_ingress {
            self.exclude(&i.account_directory)?;
            paths.extend(i.credential_paths());
        }
        for path in paths {
            self.exclude(
                Path::new(path)
                    .parent()
                    .and_then(Path::to_str)
                    .ok_or("private parent required")?,
            )?;
        }
        Ok(())
    }
}
#[derive(Clone, Copy)]
struct Event {
    level: Level,
    code: &'static str,
    count: u64,
    job: Option<i64>,
    file: Option<usize>,
}
impl Event {
    fn line(self, journal: bool) -> String {
        let prefix = if journal {
            match self.level {
                Level::Error => "<3>",
                Level::Warn => "<4>",
                Level::Info => "<6>",
                Level::Debug => "<7>",
                Level::Off => "",
            }
        } else {
            ""
        };
        let name = match self.level {
            Level::Off => "off",
            Level::Error => "error",
            Level::Warn => "warn",
            Level::Info => "info",
            Level::Debug => "debug",
        };
        let time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        format!(
            "{prefix}time={}.{:03} pid={} level={name} code={} count={} job={} file={}\n",
            time.as_secs(),
            time.subsec_millis(),
            std::process::id(),
            self.code,
            self.count,
            self.job.map_or_else(|| "-".into(), |n| n.to_string()),
            self.file.map_or_else(|| "-".into(), |n| n.to_string())
        )
    }
}
#[derive(Default)]
struct Counters {
    dropped: AtomicU64,
    errors: AtomicU64,
    pending: AtomicU64,
    abandoned: AtomicU64,
}
#[derive(Clone)]
struct Sink {
    sender: mpsc::SyncSender<Event>,
    counters: Arc<Counters>,
}
impl Sink {
    fn send(&self, event: Event) {
        self.counters.pending.fetch_add(1, Ordering::Relaxed);
        if self.sender.try_send(event).is_err() {
            self.counters.pending.fetch_sub(1, Ordering::Relaxed);
            self.counters.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }
}
struct Dispatch {
    level: Level,
    active: AtomicBool,
    stderr: Sink,
    file: Sink,
    limiter: Mutex<Vec<(&'static str, Option<i64>, Instant)>>,
    coalesced: AtomicU64,
    evicted: AtomicU64,
}
impl Dispatch {
    fn emit(&self, level: Level, code: &'static str, job: Option<i64>, file: Option<usize>) {
        if level == Level::Off || level > self.level {
            return;
        }
        // Only constant event identifiers, never interpolated error/request data.
        if code.len() > 64
            || !code
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        {
            return;
        }
        let Ok(mut limiter) = self.limiter.try_lock() else {
            self.coalesced.fetch_add(1, Ordering::Relaxed);
            return;
        };
        let now = Instant::now();
        if let Some((_, _, last)) = limiter
            .iter_mut()
            .find(|(key, id, _)| *key == code && *id == job)
        {
            if now.duration_since(*last) < Duration::from_secs(1) {
                self.coalesced.fetch_add(1, Ordering::Relaxed);
                return;
            }
            *last = now;
        } else {
            if limiter.len() == 256 {
                limiter.remove(0);
                self.evicted.fetch_add(1, Ordering::Relaxed);
            }
            limiter.push((code, job, now));
        }
        drop(limiter);
        let event = Event {
            level,
            code,
            count: 1,
            job,
            file,
        };
        self.stderr.send(event);
        self.file.send(event);
    }
}
static LOGGER: OnceLock<Arc<Dispatch>> = OnceLock::new();
pub(crate) fn emit(level: Level, code: &'static str) {
    context(level, code, None, None);
}
pub(crate) fn context(level: Level, code: &'static str, job: Option<i64>, file: Option<usize>) {
    if let Some(l) = LOGGER.get().filter(|d| d.active.load(Ordering::Relaxed)) {
        l.emit(level, code, job, file);
    }
}
// Retain original print expressions exclusively on the byte-identical OFF path.
#[inline]
fn route_to(
    dispatch: Option<&Dispatch>,
    level: Level,
    code: &'static str,
    job: Option<i64>,
    file: Option<usize>,
    legacy: impl FnOnce(),
) {
    if let Some(l) = dispatch.filter(|d| d.active.load(Ordering::Relaxed)) {
        l.emit(level, code, job, file);
    } else {
        legacy();
    }
}
pub(crate) fn route(
    level: Level,
    code: &'static str,
    job: Option<i64>,
    file: Option<usize>,
    legacy: impl FnOnce(),
) {
    route_to(
        LOGGER.get().map(Arc::as_ref),
        level,
        code,
        job,
        file,
        legacy,
    );
}
macro_rules! diagnostic_line {
    ($level:ident, $code:literal, $job:expr, $file:expr, $legacy:expr) => {{
        $crate::logging::route($crate::logging::Level::$level, $code, $job, $file, || {
            $legacy
        });
    }};
}
pub(crate) use diagnostic_line;

pub(crate) struct Guard {
    quit: Arc<AtomicBool>,
    handles: Vec<JoinHandle<()>>,
    dispatch: Arc<Dispatch>,
}
fn shutdown(quit: &AtomicBool, handles: &mut Vec<JoinHandle<()>>) {
    quit.store(true, Ordering::Release);
    let deadline = Instant::now() + SHUTDOWN;
    while handles.iter().any(|h| !h.is_finished()) && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(1));
    }
    for handle in handles.drain(..) {
        if handle.is_finished() {
            let _ = handle.join();
        }
    }
    // A blocked diagnostic thread owns no custody. Process exit ends it; never
    // pretend it joined or add a second 250ms allowance for the other sink.
}
impl Drop for Guard {
    fn drop(&mut self) {
        shutdown(&self.quit, &mut self.handles);
        for sink in [&self.dispatch.stderr, &self.dispatch.file] {
            sink.counters.abandoned.store(
                sink.counters.pending.load(Ordering::Relaxed),
                Ordering::Relaxed,
            );
        }
        self.dispatch.active.store(false, Ordering::Relaxed);
    }
}
fn sink() -> (Sink, mpsc::Receiver<Event>) {
    let (sender, rx) = mpsc::sync_channel(CAPACITY);
    (
        Sink {
            sender,
            counters: Arc::new(Counters::default()),
        },
        rx,
    )
}
fn run_sink(
    rx: mpsc::Receiver<Event>,
    counters: Arc<Counters>,
    quit: Arc<AtomicBool>,
    level: Level,
    mut write: impl FnMut(Event) -> Result<(), ()>,
) {
    let mut last = Instant::now();
    let mut reported = 0;
    loop {
        let event = if quit.load(Ordering::Acquire) {
            rx.try_recv().ok()
        } else {
            match rx.recv_timeout(Duration::from_millis(100)) {
                Ok(e) => Some(e),
                Err(mpsc::RecvTimeoutError::Timeout) => None,
                Err(_) => break,
            }
        };
        if let Some(event) = event {
            let result = write(event);
            counters.pending.fetch_sub(1, Ordering::Relaxed);
            if result.is_err() {
                counters.errors.fetch_add(1, Ordering::Relaxed);
                break;
            }
        } else if quit.load(Ordering::Acquire) {
            break;
        }
        let drops = counters.dropped.load(Ordering::Relaxed);
        if level >= Level::Warn && drops != reported && last.elapsed() >= Duration::from_secs(1) {
            if write(Event {
                level: Level::Warn,
                code: "logging_queue_dropped",
                count: drops - reported,
                job: None,
                file: None,
            })
            .is_err()
            {
                counters.errors.fetch_add(1, Ordering::Relaxed);
                break;
            }
            reported = drops;
            last = Instant::now();
        }
    }
}
fn guarded(counters: &Counters, operation: impl FnOnce()) {
    if std::panic::catch_unwind(std::panic::AssertUnwindSafe(operation)).is_err() {
        counters.errors.fetch_add(1, Ordering::Relaxed);
    }
}
pub(crate) fn start(config: &Logging) -> Option<Guard> {
    if !config.active() {
        return None;
    }
    let (stderr, errors) = sink();
    let (file, events) = sink();
    let dispatch = Arc::new(Dispatch {
        level: config.level,
        active: AtomicBool::new(true),
        stderr,
        file,
        limiter: Mutex::new(Vec::with_capacity(256)),
        coalesced: AtomicU64::new(0),
        evicted: AtomicU64::new(0),
    });
    if LOGGER.set(dispatch.clone()).is_err() {
        return None;
    }
    let quit = Arc::new(AtomicBool::new(false));
    let mut handles = Vec::new();
    let counters = dispatch.stderr.counters.clone();
    let stop = quit.clone();
    let level = config.level;
    if let Ok(handle) = thread::Builder::new()
        .name("mover-log-stderr".into())
        .stack_size(256 * 1024)
        .spawn(move || {
            guarded(&counters, || {
                if let Ok(mut file) = mover_fs::log_file::diagnostic_stderr() {
                    run_sink(errors, counters.clone(), stop, level, |e| {
                        file.write_all(e.line(true).as_bytes()).map_err(|_| ())
                    });
                } else {
                    counters.errors.fetch_add(1, Ordering::Relaxed);
                }
            });
        })
    {
        handles.push(handle);
    } else {
        dispatch
            .stderr
            .counters
            .errors
            .fetch_add(1, Ordering::Relaxed);
    }
    let reported = Arc::new(AtomicBool::new(false));
    let failure_reported = reported.clone();
    let (ready, prepared) = mpsc::sync_channel(1);
    let gate = Arc::new(AtomicU8::new(0));
    let state = gate.clone();
    let c = config.clone();
    let stop = quit.clone();
    let diagnostics = dispatch.clone();
    if let Ok(handle) = thread::Builder::new()
        .name("mover-log-file".into())
        .stack_size(256 * 1024)
        .spawn(move || {
            guarded(&diagnostics.file.counters, || {
                let result = mover_fs::log_file::LogFile::open(
                    c.file.as_deref().unwrap_or(""),
                    c.max_file_bytes,
                    c.max_files,
                );
                if let Ok(mut file) = result {
                    if state
                        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
                        .is_err()
                    {
                        return;
                    }
                    let _ = ready.try_send(());
                    run_sink(
                        events,
                        diagnostics.file.counters.clone(),
                        stop,
                        c.level,
                        |e| {
                            if state.load(Ordering::Acquire) != 1 {
                                return Err(());
                            }
                            file.append(e.line(false).as_bytes()).map_err(|_| ())
                        },
                    );
                } else {
                    diagnostics
                        .file
                        .counters
                        .errors
                        .fetch_add(1, Ordering::Relaxed);
                }
            });
            if diagnostics.file.counters.errors.load(Ordering::Relaxed) > 0
                && !failure_reported.swap(true, Ordering::Relaxed)
            {
                diagnostics.stderr.send(Event {
                    level: Level::Error,
                    code: "logging_file_unavailable",
                    count: 1,
                    job: None,
                    file: None,
                });
            }
        })
    {
        handles.push(handle);
    } else {
        dispatch
            .file
            .counters
            .errors
            .fetch_add(1, Ordering::Relaxed);
    }
    if prepared.recv_timeout(Duration::from_millis(500)).is_err() {
        gate.store(2, Ordering::Release);
        let _ = dispatch.file.counters.errors.compare_exchange(
            0,
            1,
            Ordering::Relaxed,
            Ordering::Relaxed,
        );
        if !reported.swap(true, Ordering::Relaxed) {
            dispatch.stderr.send(Event {
                level: Level::Error,
                code: "logging_file_unavailable",
                count: 1,
                job: None,
                file: None,
            });
        }
    }
    Some(Guard {
        quit,
        handles,
        dispatch,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn local(level: Level) -> (Dispatch, mpsc::Receiver<Event>, mpsc::Receiver<Event>) {
        let (stderr, a) = sink();
        let (file, b) = sink();
        (
            Dispatch {
                level,
                active: AtomicBool::new(true),
                stderr,
                file,
                limiter: Mutex::new(Vec::with_capacity(256)),
                coalesced: AtomicU64::new(0),
                evicted: AtomicU64::new(0),
            },
            a,
            b,
        )
    }
    #[test]
    fn configuration_defaults_off_and_enforces_budget_path_and_level() {
        let c: Logging = serde_json::from_str("{}").unwrap();
        assert!(!c.active());
        assert_eq!(c.max_file_bytes * u64::from(c.max_files), 1073741824);
        assert!(start(&c).is_none());
        for raw in [
            r#"{"level":"trace"}"#,
            r#"{"unexpected":true}"#,
            r#"{"enabled":1}"#,
        ] {
            assert!(serde_json::from_str::<Logging>(raw).is_err());
        }
        let mut c = Logging {
            enabled: true,
            level: Level::Info,
            ..Logging::default()
        };
        assert!(c.validate().is_err());
        for path in [
            "relative",
            "/",
            "/logs/../secret",
            "/logs//file",
            "/logs/\\file",
            "/logs/line\n",
        ] {
            c.file = Some(path.into());
            assert!(c.validate().is_err());
        }
        c.file = Some("/private-logs/service.log".into());
        assert!(c.validate().is_ok());
        assert!(c.exclude("/private-logs/nested").is_err());
        assert!(c.exclude("/private-logs").is_err());
        assert!(c.exclude("/private").is_ok()); // Component, not string prefix.
        c.max_files = 0;
        assert!(c.validate().is_err());
        c.max_files = 20;
        assert!(c.validate().is_err());
        c.max_file_bytes = 65536;
        assert!(c.validate().is_ok());
        c.max_file_bytes = u64::MAX;
        assert!(c.validate().is_err());
    }
    #[test]
    fn level_filtering_does_not_evaluate_secrets_or_the_legacy_expression() {
        let (d, a, b) = local(Level::Error);
        let secret = "password cookie private-key token sentinel";
        route_to(Some(&d), Level::Debug, "debug_event", None, None, || {
            panic!("{secret}")
        });
        assert!(a.try_recv().is_err());
        assert!(b.try_recv().is_err());
        route_to(
            Some(&d),
            Level::Error,
            "delivery_failed",
            Some(7),
            Some(2),
            || panic!("{secret}"),
        );
        let event = a.try_recv().unwrap();
        let file = b.try_recv().unwrap();
        assert!(event.line(true).starts_with("<3>"));
        assert!(!file.line(false).starts_with('<'));
        for line in [event.line(true), file.line(false)] {
            assert!(!line.contains(secret));
            assert!(!line.contains("cookie"));
            assert!(line.contains("job=7 file=2"));
            assert!(line.len() <= 1024);
        }
        for (level, prefix) in [
            (Level::Warn, "<4>"),
            (Level::Info, "<6>"),
            (Level::Debug, "<7>"),
        ] {
            assert!(
                Event {
                    level,
                    code: "event",
                    count: 1,
                    job: None,
                    file: None
                }
                .line(true)
                .starts_with(prefix)
            );
        }
        assert!(std::mem::size_of::<Event>() <= 256);
    }
    #[test]
    fn off_executes_only_the_original_bytes() {
        let mut bytes = Vec::new();
        route_to(None, Level::Info, "never_new_output", None, None, || {
            bytes.extend_from_slice(b"Ready on localhost\n")
        });
        assert_eq!(bytes, b"Ready on localhost\n");
        let c = Logging {
            file: Some("/nonexistent-private-logs/file".into()),
            ..Logging::default()
        };
        assert!(start(&c).is_none()); // No thread, queue, lock or path I/O.
    }
    #[test]
    fn full_channel_counts_loss_without_waiting_and_limiter_is_bounded() {
        let (sink, receiver) = sink();
        let event = Event {
            level: Level::Info,
            code: "bounded",
            count: 1,
            job: None,
            file: None,
        };
        for _ in 0..CAPACITY {
            sink.send(event);
        }
        let producer = sink.clone();
        let (done, completed) = mpsc::channel();
        let handle = thread::spawn(move || {
            for _ in 0..10000 {
                producer.send(event);
            }
            let _ = done.send(());
        });
        let result = completed.recv_timeout(Duration::from_secs(2));
        let queued = receiver.try_iter().count();
        drop(receiver); // Unblock even a regressed blocking sender.
        handle.join().unwrap();
        assert!(result.is_ok(), "producer waited for a full queue");
        assert_eq!(sink.counters.dropped.load(Ordering::Relaxed), 10000);
        assert_eq!(queued, CAPACITY);
        let (d, _a, _b) = local(Level::Info);
        for id in 0..300 {
            d.emit(Level::Info, "by_job", Some(id), None);
        }
        assert_eq!(d.limiter.lock().unwrap().len(), 256);
        d.emit(Level::Info, "by_job", Some(299), None);
        assert_eq!(d.coalesced.load(Ordering::Relaxed), 1);
    }
    #[test]
    fn stuck_writer_has_one_total_shutdown_budget_and_does_not_fail_producers() {
        let (sink, rx) = sink();
        let counters = sink.counters.clone();
        let quit = Arc::new(AtomicBool::new(false));
        let stop = quit.clone();
        let (entered, waiting) = mpsc::channel();
        let (release, blocked) = mpsc::channel();
        let (done, finished) = mpsc::channel();
        let handle = thread::spawn(move || {
            run_sink(rx, counters, stop, Level::Info, |_| {
                entered.send(()).unwrap();
                blocked.recv().unwrap();
                Ok(())
            });
            done.send(()).unwrap();
        });
        sink.send(Event {
            level: Level::Info,
            code: "blocked",
            count: 1,
            job: None,
            file: None,
        });
        waiting.recv_timeout(Duration::from_secs(1)).unwrap();
        let mut handles = vec![handle];
        let start = Instant::now();
        shutdown(&quit, &mut handles);
        let elapsed = start.elapsed();
        // 250ms implementation budget, with scheduler tolerance for the test host.
        release.send(()).unwrap();
        finished.recv_timeout(Duration::from_secs(2)).unwrap();
        assert!(elapsed < Duration::from_millis(500), "{elapsed:?}");
        assert!(handles.is_empty());
    }
    #[test]
    fn writer_panic_is_recorded_without_propagating_to_the_caller() {
        let counters = Counters::default();
        guarded(&counters, || panic!("injected diagnostic writer fault"));
        assert_eq!(counters.errors.load(Ordering::Relaxed), 1);
    }
    #[test]
    fn write_failure_closes_only_its_sink() {
        let (file, rx) = sink();
        let quit = Arc::new(AtomicBool::new(false));
        let counters = file.counters.clone();
        file.send(Event {
            level: Level::Error,
            code: "io_error",
            count: 1,
            job: None,
            file: None,
        });
        run_sink(rx, counters.clone(), quit, Level::Error, |_| Err(()));
        assert_eq!(counters.errors.load(Ordering::Relaxed), 1);
        file.send(Event {
            level: Level::Error,
            code: "still_running",
            count: 1,
            job: None,
            file: None,
        });
        assert_eq!(counters.dropped.load(Ordering::Relaxed), 1);
    }
}
