//! Local lifecycle IPC, independent of SQLite, transfer mounts and the executor.
use mover_fs::{InstanceGuard, InstanceOwnership, instance_ownership};
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::unix::{
        fs::{FileTypeExt, MetadataExt, PermissionsExt},
        net::UnixListener,
    },
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const SOCKET: &str = "control.sock";
const IO_WAIT: Duration = Duration::from_millis(500);

pub struct Lifecycle {
    pub(crate) stop: Arc<AtomicBool>,
    wait: u32,
    state: Mutex<State>,
}
struct State {
    first_stop: Option<Instant>,
    phase: &'static str,
}
impl Lifecycle {
    pub fn new(stop: Arc<AtomicBool>, wait: u32) -> Arc<Self> {
        Arc::new(Self {
            stop,
            wait,
            state: Mutex::new(State {
                first_stop: None,
                phase: "Starting",
            }),
        })
    }
    pub fn request_stop(&self) {
        let mut state = self.state.lock().expect("lifecycle state");
        state.first_stop.get_or_insert_with(Instant::now);
        state.phase = "Draining";
        self.stop.store(true, Ordering::Relaxed);
    }
    pub(crate) fn phase(&self, phase: &'static str) {
        let mut state = self.state.lock().expect("lifecycle state");
        if state.first_stop.is_none() {
            state.phase = phase;
        }
    }
    fn snapshot(&self, identity: &str) -> Snapshot {
        if self.stop.load(Ordering::Relaxed) {
            self.request_stop();
        }
        let state = self.state.lock().expect("lifecycle state");
        let remaining = state
            .first_stop
            .map(|start| Duration::from_secs(self.wait.into()).saturating_sub(start.elapsed()));
        let expired = remaining.is_some_and(|v| v.as_millis() == 0);
        Snapshot {
            version: 1,
            instance_id: Some(identity.into()),
            coordinator_pid: Some(std::process::id()),
            phase: if expired {
                "ShutdownIncomplete"
            } else {
                state.phase
            }
            .into(),
            shutdown_wait_seconds: Some(self.wait),
            shutdown_remaining_ms: remaining.map(|v| v.as_millis() as u64),
            workers: children(),
            message: expired.then(|| "shutdown incomplete; restart blocked".into()),
        }
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    command: String,
    instance_id: Option<String>,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    version: u32,
    pub instance_id: Option<String>,
    pub coordinator_pid: Option<u32>,
    pub phase: String,
    pub shutdown_wait_seconds: Option<u32>,
    pub shutdown_remaining_ms: Option<u64>,
    pub workers: Vec<u32>,
    pub message: Option<String>,
}
impl Snapshot {
    fn local(phase: &str, message: Option<&str>) -> Self {
        Self {
            version: 1,
            instance_id: None,
            coordinator_pid: None,
            phase: phase.into(),
            shutdown_wait_seconds: None,
            shutdown_remaining_ms: None,
            workers: vec![],
            message: message.map(Into::into),
        }
    }
}
fn socket_path(database: &str) -> Result<PathBuf> {
    Ok(Path::new(database)
        .parent()
        .ok_or("local state parent required")?
        .join(SOCKET))
}
fn socket_identity(path: &Path) -> Result<(u64, u64)> {
    let m = std::fs::symlink_metadata(path)?;
    if !m.file_type().is_socket() || m.mode() & 0o7777 != 0o600 || m.nlink() != 1 {
        return Err("unsafe local control endpoint; preserve state".into());
    }
    // Parent/guard ownership is validated separately; socket must have that owner.
    if m.uid() != std::fs::metadata(path.parent().ok_or("local state parent required")?)?.uid() {
        return Err("foreign local control endpoint".into());
    }
    Ok((m.dev(), m.ino()))
}
fn process_stamp(pid: u32) -> Option<(String, bool)> {
    let text = std::fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
    parsed_stamp(pid, &text)
}
fn parsed_stamp(pid: u32, text: &str) -> Option<(String, bool)> {
    let (_, fields) = text.rsplit_once(") ")?;
    let mut fields = fields.split_whitespace();
    let state = fields.next()?;
    let start = fields.nth(18)?; // field 22, after state (field 3).
    Some((format!("{pid}:{start}"), state == "Z" || state == "X"))
}
fn children() -> Vec<u32> {
    let mut ids = Vec::new();
    if let Ok(tasks) = std::fs::read_dir("/proc/self/task") {
        for task in tasks.take(128).flatten() {
            if let Ok(text) = std::fs::read_to_string(task.path().join("children")) {
                for pid in text
                    .split_whitespace()
                    .take(64)
                    .filter_map(|v| v.parse().ok())
                {
                    if ids.len() < 64 {
                        ids.push(pid);
                    }
                }
            }
        }
    }
    ids.sort_unstable();
    ids.dedup();
    ids
}
pub(crate) struct Server {
    pub(crate) lifecycle: Arc<Lifecycle>,
    quit: Arc<AtomicBool>,
    thread: Option<std::thread::JoinHandle<()>>,
    path: PathBuf,
    socket: (u64, u64),
    guard: Arc<InstanceGuard>,
}
impl Server {
    pub(crate) fn start(guard: Arc<InstanceGuard>, lifecycle: Arc<Lifecycle>) -> Result<Self> {
        guard.validate()?;
        let path = Path::new(guard.state_directory()).join(SOCKET);
        match std::fs::symlink_metadata(&path) {
            Ok(_) => {
                socket_identity(&path)?;
                std::fs::remove_file(&path)?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
        let listener = UnixListener::bind(&path)?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        let socket = socket_identity(&path)?;
        listener.set_nonblocking(true)?;
        let identity = process_stamp(std::process::id())
            .ok_or("local process identity unavailable")?
            .0;
        let quit = Arc::new(AtomicBool::new(false));
        let thread_quit = quit.clone();
        let thread_state = lifecycle.clone();
        let thread_guard = guard.clone();
        let thread = std::thread::Builder::new()
            .name("mover-lifecycle".into())
            .spawn(move || {
                while !thread_quit.load(Ordering::Relaxed) {
                    if thread_state.stop.load(Ordering::Relaxed) {
                        thread_state.request_stop();
                    }
                    match listener.accept() {
                        Ok((mut stream, _)) => {
                            let result = (|| -> Result<()> {
                                stream.set_read_timeout(Some(Duration::from_millis(100)))?;
                                stream.set_write_timeout(Some(Duration::from_millis(100)))?;
                                let mut bytes = Vec::new();
                                (&mut stream).take(257).read_to_end(&mut bytes)?;
                                if bytes.len() > 256 {
                                    return Err("control request too large".into());
                                }
                                let r: Request = serde_json::from_slice(&bytes)?;
                                if r.version != 1
                                    || !["status", "stop"].contains(&r.command.as_str())
                                    || r.instance_id.as_ref().is_some_and(|v| v != &identity)
                                {
                                    return Err(
                                        "invalid control request or instance changed".into()
                                    );
                                }
                                thread_guard.validate()?;
                                if r.command == "stop" {
                                    thread_state.request_stop();
                                }
                                let snapshot = thread_state.snapshot(&identity);
                                stream.write_all(&serde_json::to_vec(&snapshot)?)?;
                                Ok(())
                            })();
                            if result.is_err() {
                                let _ = stream.shutdown(std::net::Shutdown::Both);
                            }
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(Duration::from_millis(10))
                        }
                        Err(_) => {
                            thread_state.request_stop();
                            break;
                        }
                    }
                }
            })?;
        Ok(Self {
            lifecycle,
            quit,
            thread: Some(thread),
            path,
            socket,
            guard,
        })
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        self.quit.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        if self.guard.validate().is_ok() && socket_identity(&self.path).ok() == Some(self.socket) {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}
fn valid_snapshot(s: &Snapshot) -> bool {
    let Some(wait) = s.shutdown_wait_seconds.filter(|v| (1..=3600).contains(v)) else {
        return false;
    };
    let Some(pid) = s.coordinator_pid.filter(|v| *v > 0) else {
        return false;
    };
    let Some(id) = s.instance_id.as_deref().filter(|v| v.len() <= 64) else {
        return false;
    };
    let Some((owner, start)) = id.split_once(':') else {
        return false;
    };
    if owner.parse::<u32>().ok() != Some(pid)
        || start.parse::<u64>().is_err()
        || s.workers.len() > 64
        || s.workers.contains(&0)
    {
        return false;
    }
    match s.phase.as_str() {
        "Starting" | "Running" => s.shutdown_remaining_ms.is_none(),
        "Draining" => s
            .shutdown_remaining_ms
            .is_some_and(|v| v > 0 && v <= u64::from(wait) * 1000),
        "ShutdownIncomplete" => s.shutdown_remaining_ms == Some(0),
        _ => false,
    }
}
async fn exchange(path: &Path, command: &str, expected: Option<&str>) -> Result<Snapshot> {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    tokio::time::timeout(IO_WAIT, async {
        let mut stream = tokio::net::UnixStream::connect(path).await?;
        let bytes = serde_json::to_vec(&Request {
            version: 1,
            command: command.into(),
            instance_id: expected.map(Into::into),
        })?;
        stream.write_all(&bytes).await?;
        stream.shutdown().await?;
        let mut bytes = Vec::new();
        stream.take(4097).read_to_end(&mut bytes).await?;
        if bytes.len() > 4096 {
            return Err("control response too large".into());
        }
        let s: Snapshot = serde_json::from_slice(&bytes)?;
        if s.version != 1
            || !valid_snapshot(&s)
            || expected.is_some_and(|v| s.instance_id.as_deref() != Some(v))
        {
            return Err("control instance changed".into());
        }
        Ok(s)
    })
    .await
    .map_err(|_| "local controller unavailable or timed out")?
}
fn unserved(database: &str) -> Result<(Snapshot, bool)> {
    match instance_ownership(database)? {
        InstanceOwnership::Free | InstanceOwnership::Absent => {
            Ok((Snapshot::local("NoActiveOwner", None), true))
        }
        InstanceOwnership::Held => Ok((
            Snapshot::local(
                "OwnerUnavailable",
                Some("shutdown incomplete; restart blocked"),
            ),
            false,
        )),
    }
}
/// Bounded local observation/control. No source, destination or SQLite access.
pub async fn command(database: &str, stop: bool) -> Result<(Snapshot, bool)> {
    // Validates local state/guard without creating files before connecting.
    let ownership = instance_ownership(database)?;
    let path = socket_path(database)?;
    if ownership != InstanceOwnership::Held {
        return unserved(database);
    }
    let guard_path = Path::new(database)
        .parent()
        .ok_or("local state parent required")?
        .join(mover_fs::INSTANCE_LOCK);
    let metadata = std::fs::symlink_metadata(&guard_path)?;
    let guard_identity = (metadata.dev(), metadata.ino());
    if !path.try_exists()? {
        return Ok((
            Snapshot::local(
                "OwnerUnavailable",
                Some("shutdown incomplete; restart blocked"),
            ),
            false,
        ));
    }
    socket_identity(&path)?;
    let sent = Instant::now();
    let initial = match exchange(&path, if stop { "stop" } else { "status" }, None).await {
        Ok(s) => s,
        Err(_) => {
            return Ok((
                Snapshot::local(
                    "OwnerUnavailable",
                    Some("shutdown incomplete; restart blocked"),
                ),
                false,
            ));
        }
    };
    if !stop {
        let ok = initial.phase != "ShutdownIncomplete";
        return Ok((initial, ok));
    }
    let identity = initial
        .instance_id
        .clone()
        .ok_or("missing control identity")?;
    let pid = initial.coordinator_pid.ok_or("missing coordinator PID")?;
    let budget = initial
        .shutdown_remaining_ms
        .ok_or("missing shutdown deadline")?;
    // Subtract the whole first exchange conservatively, never extending the daemon deadline.
    let deadline = sent + Duration::from_millis(budget);
    let mut latest = initial;
    loop {
        if Instant::now() >= deadline {
            latest.phase = "ShutdownIncomplete".into();
            latest.shutdown_remaining_ms = Some(0);
            latest.message = Some("shutdown incomplete; restart blocked".into());
            return Ok((latest, false));
        }
        let alive = match std::fs::read_to_string(format!("/proc/{pid}/stat")) {
            Ok(text) => {
                let (stamp, exited) =
                    parsed_stamp(pid, &text).ok_or("cannot establish coordinator exit")?;
                stamp == identity && !exited
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
            Err(e) => return Err(e.into()),
        };
        let metadata = std::fs::symlink_metadata(&guard_path)?;
        if (metadata.dev(), metadata.ino()) != guard_identity {
            return Err("instance guard identity changed; preserve state".into());
        }
        let free = instance_ownership(database)? == InstanceOwnership::Free;
        if !alive && free {
            latest.phase = "Stopped".into();
            latest.shutdown_remaining_ms = Some(0);
            latest.workers.clear();
            latest.message = None;
            return Ok((latest, true));
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        if let Ok(Ok(s)) = tokio::time::timeout(
            remaining.min(IO_WAIT),
            exchange(&path, "status", Some(&identity)),
        )
        .await
        {
            latest = s;
        } // A lost endpoint is never exit proof.
        let remaining = deadline.saturating_duration_since(Instant::now());
        tokio::time::sleep(remaining.min(Duration::from_millis(50))).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn controller_rejects_unbounded_deadlines_unknown_phases_and_foreign_process_shapes() {
        let l = Lifecycle::new(Arc::new(AtomicBool::new(false)), 60);
        let id = process_stamp(std::process::id()).unwrap().0;
        let mut s = l.snapshot(&id);
        assert!(valid_snapshot(&s));
        s.shutdown_wait_seconds = Some(3601);
        assert!(!valid_snapshot(&s));
        s.shutdown_wait_seconds = Some(60);
        s.phase = "Draining".into();
        s.shutdown_remaining_ms = Some(u64::MAX);
        assert!(!valid_snapshot(&s));
        s.shutdown_remaining_ms = Some(60000);
        assert!(valid_snapshot(&s));
        s.phase = "Unknown".into();
        assert!(!valid_snapshot(&s));
        s.phase = "ShutdownIncomplete".into();
        s.shutdown_remaining_ms = Some(0);
        assert!(valid_snapshot(&s));
        s.instance_id = Some("foreign".into());
        assert!(!valid_snapshot(&s));
        s.instance_id = Some(id);
        s.workers = vec![1; 65];
        assert!(!valid_snapshot(&s));
    }
    #[test]
    fn first_monotonic_deadline_survives_repeat_requests_and_phase_changes() {
        let l = Lifecycle::new(Arc::new(AtomicBool::new(false)), 60);
        l.request_stop();
        let first = l.state.lock().unwrap().first_stop;
        l.request_stop();
        l.phase("Running");
        assert_eq!(l.state.lock().unwrap().first_stop, first);
        assert_eq!(l.snapshot("test").phase, "Draining");
        l.state.lock().unwrap().first_stop = Some(Instant::now() - Duration::from_secs(61));
        let s = l.snapshot("test");
        assert_eq!(s.phase, "ShutdownIncomplete");
        assert_eq!(s.shutdown_remaining_ms, Some(0));
        assert!(process_stamp(std::process::id()).is_some());
    }
}
