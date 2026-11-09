//! Private local TLS status/reload IPC, independent of lifecycle control.
//! Backend snapshots must be quick and must not wait behind credential I/O.
//! Reloads are serialized; a lost/late reply never authorizes a retry.
use mover_fs::{InstanceGuard, InstanceOwnership};
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    net::Shutdown,
    os::unix::{
        fs::{FileTypeExt, MetadataExt},
        net::UnixStream,
    },
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, SyncSender, TrySendError},
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const SOCKET: &str = "tls-reload.sock";
const REQUEST_MAX: usize = 32768;
const RESPONSE_MAX: usize = 65536;
const READ_WAIT: Duration = Duration::from_millis(100);
const WRITE_WAIT: Duration = Duration::from_millis(500);
const POLL_WAIT: Duration = Duration::from_millis(10);
const UNKNOWN: &str = "TLS reload outcome unknown; use --tls-status to compare full policy_sha256 and PID:start; generation alone is not proof; do not automatically retry";

/// Snapshots use only a brief memory lock, never filesystem/credential I/O.
/// The policy hash binds the full public TLS configuration and certificate/root
/// hashes, excluding private bytes; generation alone cannot identify a policy.
/// Backend reload owns generation admission, connection draining and stop checks.
/// Reload must finish its own bounded validation/publication; IPC teardown joins
/// the actual loader, never detaches it or releases its instance guard early.
pub(crate) trait Backend: Send + Sync {
    fn snapshot(&self) -> Status;
    fn reload(
        &self,
        c: crate::Config,
        expected_generation: u64,
    ) -> std::result::Result<Status, &'static str>;
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Status {
    pub generation: u64,
    pub policy_sha256: String,
    pub server_sha256: String,
    pub client_sha256: Vec<String>,
    pub last_result: String,
    /// Activated policy still has old unadmitted connections exiting.
    pub draining: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Reply {
    pub version: u32,
    pub instance_id: String,
    pub status: Status,
    /// A loader is reserved/running; independent of status.draining.
    pub busy: bool,
    pub ok: bool,
    pub error: Option<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    command: String,
    instance_id: String,
    expected_generation: Option<u64>,
    proposed: Option<crate::Config>,
}

fn valid_request(request: &Request, identity: &str) -> bool {
    request.version == 1
        && request.instance_id == identity
        && match request.command.as_str() {
            "status" => request.expected_generation.is_none() && request.proposed.is_none(),
            "reload" => request.expected_generation.is_some() && request.proposed.is_some(),
            _ => false,
        }
}

fn process_identity() -> Result<String> {
    let file = std::fs::File::open("/proc/self/stat")
        .map_err(|_| "TLS IPC process identity unavailable")?;
    let mut text = String::new();
    file.take(4097)
        .read_to_string(&mut text)
        .map_err(|_| "TLS IPC process identity unavailable")?;
    if text.len() > 4096 {
        return Err("TLS IPC process identity unavailable".into());
    }
    let (_, fields) = text
        .rsplit_once(") ")
        .ok_or("TLS IPC process identity unavailable")?;
    let start = fields
        .split_whitespace()
        .nth(19)
        .filter(|value| !value.is_empty() && value.bytes().all(|b| b.is_ascii_digit()))
        .ok_or("TLS IPC process identity unavailable")?;
    Ok(format!("{}:{start}", std::process::id()))
}

fn read_request(stream: &mut UnixStream) -> Result<Request> {
    let deadline = Instant::now() + READ_WAIT;
    let mut bytes = Vec::new();
    let mut buffer = [0; 4096];
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("TLS IPC request timed out".into());
        }
        stream.set_read_timeout(Some(remaining))?;
        let limit = buffer.len().min(REQUEST_MAX + 1 - bytes.len());
        match stream.read(&mut buffer[..limit]) {
            Ok(0) => break,
            Ok(count) => bytes.extend_from_slice(&buffer[..count]),
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(_) => return Err("TLS IPC request unavailable".into()),
        }
        if bytes.len() > REQUEST_MAX {
            return Err("TLS IPC request too large".into());
        }
    }
    serde_json::from_slice(&bytes).map_err(|_| "TLS IPC invalid request".into())
}

fn write_reply(stream: &mut UnixStream, reply: &Reply) -> Result<()> {
    let bytes = serde_json::to_vec(reply).map_err(|_| "TLS IPC response unavailable")?;
    if bytes.len() > RESPONSE_MAX {
        return Err("TLS IPC response too large".into());
    }
    let deadline = Instant::now() + WRITE_WAIT;
    let mut offset = 0;
    while offset < bytes.len() {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("TLS IPC response timed out".into());
        }
        stream.set_write_timeout(Some(remaining))?;
        match stream.write(&bytes[offset..]) {
            Ok(0) => return Err("TLS IPC response unavailable".into()),
            Ok(count) => offset += count,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
            Err(_) => return Err("TLS IPC response unavailable".into()),
        }
    }
    Ok(())
}

fn reply(identity: &str, status: Status, busy: bool, error: Option<&str>) -> Reply {
    Reply {
        version: 1,
        instance_id: identity.into(),
        status,
        busy,
        ok: error.is_none(),
        error: error.map(Into::into),
    }
}

struct Reservation(Arc<AtomicBool>);
impl Reservation {
    fn take(busy: &Arc<AtomicBool>) -> Option<Self> {
        busy.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .ok()
            .map(|_| Self(busy.clone()))
    }
}
impl Drop for Reservation {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}
struct Job {
    stream: UnixStream,
    proposed: crate::Config,
    expected: u64,
    reservation: Reservation,
}

fn stopped(quit: &AtomicBool, stop: &AtomicBool) -> bool {
    quit.load(Ordering::Acquire) || stop.load(Ordering::Acquire)
}

// A current-thread reactor supplies Tokio's existing safe SO_PEERCRED wrapper.
// It starts no worker threads and never drives any backend or network request.
fn checked_peer(stream: UnixStream, runtime: &tokio::runtime::Runtime) -> Result<UnixStream> {
    stream.set_nonblocking(true)?;
    let _entered = runtime.enter();
    let stream = tokio::net::UnixStream::from_std(stream)?;
    let allowed = stream
        .peer_cred()
        .is_ok_and(|peer| peer.uid() == mover_fs::ingress::local_user_ids().0);
    let stream = stream.into_std()?;
    stream.set_nonblocking(false)?;
    if !allowed {
        return Err("TLS IPC peer refused".into());
    }
    Ok(stream)
}

pub(crate) struct Server {
    quit: Arc<AtomicBool>,
    sender: Option<SyncSender<Job>>,
    accept: Option<JoinHandle<()>>,
    loader: Option<JoinHandle<()>>,
    // Retain the original LocalSocket until both actual threads have exited.
    _socket: Arc<mover_fs::ingress::LocalSocket>,
    _guard: Arc<InstanceGuard>,
}
impl Server {
    pub(crate) fn start(
        plan: mover_fs::ingress::SocketPlan,
        guard: Arc<InstanceGuard>,
        stop: Arc<AtomicBool>,
        backend: Arc<dyn Backend>,
    ) -> Result<Self> {
        guard
            .validate()
            .map_err(|_| "TLS IPC instance unavailable")?;
        if stop.load(Ordering::Acquire) {
            return Err("TLS IPC stopping".into());
        }
        let identity = process_identity()?;
        let socket = Arc::new(plan.bind().map_err(|_| "TLS IPC bind refused")?);
        let listener = socket
            .listener()
            .map_err(|_| "TLS IPC endpoint unavailable")?;
        let expected_path = Path::new(guard.state_directory()).join(SOCKET);
        if listener.local_addr()?.as_pathname() != Some(expected_path.as_path()) {
            return Err("TLS IPC endpoint must use the instance reload socket".into());
        }
        socket_identity(&expected_path)?;
        let quit = Arc::new(AtomicBool::new(false));
        let busy = Arc::new(AtomicBool::new(false));
        let (sender, receiver) = mpsc::sync_channel(1);
        let loader = {
            let guard = guard.clone();
            let socket = socket.clone();
            let quit = quit.clone();
            let stop = stop.clone();
            let busy = busy.clone();
            let backend = backend.clone();
            let identity = identity.clone();
            std::thread::Builder::new()
                .name("mover-tls-loader".into())
                .spawn(move || {
                    load_requests(
                        receiver,
                        (guard, socket),
                        quit,
                        stop,
                        busy,
                        backend,
                        identity,
                    );
                })?
        };
        let (ready_sender, ready) = mpsc::sync_channel(1);
        let accept = {
            let guard = guard.clone();
            let socket = socket.clone();
            let quit = quit.clone();
            let stop = stop.clone();
            let backend = backend.clone();
            let sender = sender.clone();
            std::thread::Builder::new()
                .name("mover-tls-ipc".into())
                .spawn(move || {
                    let runtime = match tokio::runtime::Builder::new_current_thread()
                        .enable_io()
                        .build()
                    {
                        Ok(runtime) => runtime,
                        Err(_) => return,
                    };
                    if ready_sender.send(()).is_err() {
                        return;
                    }
                    while !stopped(&quit, &stop) {
                        match listener.accept() {
                            Ok((stream, _)) => {
                                let result = (|| -> Result<()> {
                                    socket.validate().map_err(|_| "TLS IPC endpoint changed")?;
                                    let mut stream = checked_peer(stream, &runtime)?;
                                    let request = read_request(&mut stream)?;
                                    if !valid_request(&request, &identity) {
                                        return Err(
                                            "TLS IPC invalid request or instance changed".into()
                                        );
                                    }
                                    guard.validate().map_err(|_| "TLS IPC instance changed")?;
                                    if stopped(&quit, &stop) {
                                        return Err("TLS IPC stopping".into());
                                    }
                                    if request.command == "status" {
                                        return write_reply(
                                            &mut stream,
                                            &reply(
                                                &identity,
                                                backend.snapshot(),
                                                busy.load(Ordering::Acquire),
                                                None,
                                            ),
                                        );
                                    }
                                    let Some(reservation) = Reservation::take(&busy) else {
                                        return write_reply(
                                            &mut stream,
                                            &reply(
                                                &identity,
                                                backend.snapshot(),
                                                true,
                                                Some("reload_busy"),
                                            ),
                                        );
                                    };
                                    let (Some(proposed), Some(expected)) =
                                        (request.proposed, request.expected_generation)
                                    else {
                                        return Err("TLS IPC invalid reload".into());
                                    };
                                    let job = Job {
                                        stream,
                                        proposed,
                                        expected,
                                        reservation,
                                    };
                                    match sender.try_send(job) {
                                        Ok(()) => Ok(()),
                                        Err(TrySendError::Full(mut job))
                                        | Err(TrySendError::Disconnected(mut job)) => write_reply(
                                            &mut job.stream,
                                            &reply(
                                                &identity,
                                                backend.snapshot(),
                                                true,
                                                Some("reload_unavailable"),
                                            ),
                                        ),
                                    }
                                })();
                                // Invalid/failed requests close only their own stream.
                                // A delivered reload remains owned by the loader.
                                let _ = result;
                            }
                            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                                std::thread::sleep(POLL_WAIT);
                            }
                            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => (),
                            Err(_) => std::thread::sleep(POLL_WAIT),
                        }
                    }
                })
        };
        let accept = match accept {
            Ok(thread) => thread,
            Err(_) => {
                quit.store(true, Ordering::Release);
                drop(sender);
                let _ = loader.join();
                return Err("TLS IPC accept thread unavailable".into());
            }
        };
        let server = Self {
            quit,
            sender: Some(sender),
            accept: Some(accept),
            loader: Some(loader),
            _socket: socket,
            _guard: guard,
        };
        if ready.recv_timeout(Duration::from_secs(1)).is_err() {
            return Err("TLS IPC accept thread unavailable".into());
        }
        Ok(server)
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        self.quit.store(true, Ordering::Release);
        if let Some(thread) = self.accept.take() {
            let _ = thread.join();
        }
        // The accept thread has dropped its clone: this closes the work queue.
        drop(self.sender.take());
        if let Some(thread) = self.loader.take() {
            let _ = thread.join();
        }
    }
}

fn load_requests(
    receiver: Receiver<Job>,
    authority: (Arc<InstanceGuard>, Arc<mover_fs::ingress::LocalSocket>),
    quit: Arc<AtomicBool>,
    stop: Arc<AtomicBool>,
    busy: Arc<AtomicBool>,
    backend: Arc<dyn Backend>,
    identity: String,
) {
    let (guard, socket) = authority;
    while !stopped(&quit, &stop) {
        let mut job = match receiver.recv_timeout(POLL_WAIT) {
            Ok(job) => job,
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
        };
        let result = if stopped(&quit, &stop) {
            Err("stopping")
        } else if guard.validate().is_err() || socket.validate().is_err() {
            Err("instance_unavailable")
        } else {
            // The backend's private diagnostics must never enter this wire reply.
            backend
                .reload(job.proposed, job.expected)
                .map_err(|_| "reload_refused")
        };
        let (status, error) = match result {
            Ok(status) => (status, None),
            Err(error) => (backend.snapshot(), Some(error)),
        };
        drop(job.reservation);
        let response = reply(&identity, status, busy.load(Ordering::Acquire), error);
        let _ = write_reply(&mut job.stream, &response);
        let _ = job.stream.shutdown(Shutdown::Both);
    }
}

fn socket_path(database: &str) -> Result<PathBuf> {
    let parent = Path::new(database)
        .parent()
        .ok_or("TLS IPC state parent unavailable")?;
    let path = parent.join(SOCKET);
    let text = path.to_str().ok_or("TLS IPC endpoint unavailable")?;
    if !text.starts_with('/')
        || text.len() > 107
        || text[1..].split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || part.contains('\\')
                || part.chars().any(char::is_control)
        })
    {
        return Err("TLS IPC endpoint unavailable".into());
    }
    Ok(path)
}

fn socket_identity(path: &Path) -> Result<(u64, u64)> {
    let (uid, gid) = mover_fs::ingress::local_user_ids();
    let parent =
        std::fs::symlink_metadata(path.parent().ok_or("TLS IPC state parent unavailable")?)
            .map_err(|_| "TLS IPC state parent unavailable")?;
    let metadata = std::fs::symlink_metadata(path).map_err(|_| "TLS IPC endpoint unavailable")?;
    if !parent.is_dir()
        || parent.uid() != uid
        || parent.gid() != gid
        || parent.mode() & 0o7777 != 0o700
        || !metadata.file_type().is_socket()
        || metadata.uid() != uid
        || metadata.gid() != gid
        || metadata.mode() & 0o7777 != 0o600
        || metadata.nlink() != 1
    {
        return Err("TLS IPC endpoint custody refused".into());
    }
    Ok((metadata.dev(), metadata.ino()))
}

fn guard_identity(database: &str) -> Result<(u64, u64)> {
    if mover_fs::instance_ownership(database).map_err(|_| "TLS IPC owner unavailable")?
        != InstanceOwnership::Held
    {
        return Err("TLS IPC no active owner".into());
    }
    let parent = Path::new(database)
        .parent()
        .ok_or("TLS IPC state parent unavailable")?;
    let metadata = std::fs::symlink_metadata(parent.join(mover_fs::INSTANCE_LOCK))
        .map_err(|_| "TLS IPC owner unavailable")?;
    if !metadata.is_file()
        || metadata.uid() != mover_fs::ingress::local_user_ids().0
        || metadata.mode() & 0o7777 != 0o600
        || metadata.nlink() != 1
    {
        return Err("TLS IPC owner custody refused".into());
    }
    Ok((metadata.dev(), metadata.ino()))
}

fn valid_status(status: &Status) -> bool {
    [
        "ready", "loading", "draining", "applied", "rejected", "stopping",
    ]
    .contains(&status.last_result.as_str())
        && status.client_sha256.len() <= 256
        && std::iter::once(&status.policy_sha256)
            .chain(std::iter::once(&status.server_sha256))
            .chain(status.client_sha256.iter())
            .all(|hash| {
                hash.len() == 64
                    && hash
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            })
}

async fn exchange(
    path: &Path,
    expected_socket: (u64, u64),
    owner_pid: u32,
    request: &Request,
) -> Result<Reply> {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    if socket_identity(path)? != expected_socket {
        return Err("TLS IPC endpoint changed".into());
    }
    let bytes = serde_json::to_vec(request).map_err(|_| "TLS IPC request unavailable")?;
    if bytes.len() > REQUEST_MAX {
        return Err("TLS IPC request too large".into());
    }
    let mut stream = tokio::net::UnixStream::connect(path)
        .await
        .map_err(|_| "TLS IPC endpoint unavailable")?;
    let peer = stream.peer_cred().map_err(|_| "TLS IPC peer unavailable")?;
    if peer.uid() != mover_fs::ingress::local_user_ids().0
        || peer.pid().and_then(|pid| u32::try_from(pid).ok()) != Some(owner_pid)
        || socket_identity(path)? != expected_socket
    {
        return Err("TLS IPC owner or endpoint changed".into());
    }
    stream
        .write_all(&bytes)
        .await
        .map_err(|_| "TLS IPC request unavailable")?;
    stream
        .shutdown()
        .await
        .map_err(|_| "TLS IPC request unavailable")?;
    let mut bytes = Vec::new();
    stream
        .take((RESPONSE_MAX + 1) as u64)
        .read_to_end(&mut bytes)
        .await
        .map_err(|_| "TLS IPC response unavailable")?;
    if bytes.len() > RESPONSE_MAX {
        return Err("TLS IPC response too large".into());
    }
    let response: Reply = serde_json::from_slice(&bytes).map_err(|_| "TLS IPC invalid response")?;
    if response.version != 1
        || response.instance_id != request.instance_id
        || !valid_status(&response.status)
        || response.ok != response.error.is_none()
        || response
            .error
            .as_ref()
            .is_some_and(|e| e.len() > 128 || e.chars().any(char::is_control))
        || socket_identity(path)? != expected_socket
    {
        return Err("TLS IPC invalid response or instance changed".into());
    }
    Ok(response)
}

async fn command_inner(c: crate::Config, reload: bool) -> Result<(Reply, bool)> {
    let (owner, available) = crate::control::command(&c.state_database, false)
        .await
        .map_err(|_| "TLS IPC owner unavailable")?;
    if !available || owner.phase != "Running" {
        return Err("TLS IPC no running active owner".into());
    }
    let identity = owner
        .instance_id
        .ok_or("TLS IPC owner identity unavailable")?;
    let pid = owner
        .coordinator_pid
        .ok_or("TLS IPC owner identity unavailable")?;
    let guard = guard_identity(&c.state_database)?;
    let path = socket_path(&c.state_database)?;
    let socket = socket_identity(&path)?;
    let request = Request {
        version: 1,
        command: "status".into(),
        instance_id: identity.clone(),
        expected_generation: None,
        proposed: None,
    };
    let initial = tokio::time::timeout(
        Duration::from_secs(1),
        exchange(&path, socket, pid, &request),
    )
    .await
    .map_err(|_| "TLS status unavailable or timed out")??;
    if guard_identity(&c.state_database)? != guard {
        return Err("TLS IPC instance guard changed".into());
    }
    if !reload || !initial.ok {
        let ok = initial.ok;
        return Ok((initial, ok));
    }
    let request = Request {
        version: 1,
        command: "reload".into(),
        instance_id: identity,
        expected_generation: Some(initial.status.generation),
        proposed: Some(c),
    };
    // Exactly one mutation request. Any lost response is explicitly uncertain.
    let response = exchange(&path, socket, pid, &request)
        .await
        .map_err(|_| UNKNOWN)?;
    if response.ok
        && (response.status.draining
            || response.status.last_result != "applied"
            || Some(response.status.generation) != initial.status.generation.checked_add(1))
    {
        return Err(UNKNOWN.into());
    }
    let ok = response.ok;
    Ok((response, ok))
}

/// Status has a one-second overall budget. Reload has a thirty-second overall
/// budget (including discovery/status), with no automatic mutating retry.
/// A true command result does not assert that draining has completed. After a
/// lost reply, compare the full public policy hash and instance PID:start using
/// --tls-status; a generation change alone is never command-completion proof.
pub async fn command(c: crate::Config, reload: bool) -> Result<(Reply, bool)> {
    let budget = Duration::from_secs(if reload { 30 } else { 1 });
    tokio::time::timeout(budget, command_inner(c, reload))
        .await
        .map_err(|_| {
            if reload {
                UNKNOWN
            } else {
                "TLS status unavailable or timed out"
            }
        })?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strict_status_request_rejects_unknown_duplicate_and_reload_fields() {
        let valid = br#"{"version":1,"command":"status","instance_id":"7:11"}"#;
        let mut request: Request = serde_json::from_slice(valid).unwrap();
        assert!(valid_request(&request, "7:11"));
        assert!(!valid_request(&request, "7:12"));
        request.expected_generation = Some(1);
        assert!(!valid_request(&request, "7:11"));
        request.command = "reload".into();
        assert!(!valid_request(&request, "7:11"));
        for bytes in [
            br#"{"version":1,"command":"status","instance_id":"7:11","extra":0}"#.as_slice(),
            br#"{"version":1,"version":1,"command":"status","instance_id":"7:11"}"#.as_slice(),
        ] {
            assert!(serde_json::from_slice::<Request>(bytes).is_err());
        }
    }

    #[test]
    fn busy_reservation_is_exclusive_and_released_by_owner_drop() {
        let busy = Arc::new(AtomicBool::new(false));
        let first = Reservation::take(&busy).unwrap();
        assert!(Reservation::take(&busy).is_none());
        drop(first);
        let second = Reservation::take(&busy).unwrap();
        assert!(busy.load(Ordering::Acquire));
        drop(second);
        assert!(!busy.load(Ordering::Acquire));
    }

    #[test]
    fn unix_request_and_reply_bounds_close_only_the_request() {
        let (mut client, mut server) = UnixStream::pair().unwrap();
        client
            .write_all(br#"{"version":1,"command":"status","instance_id":"7:11"}"#)
            .unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        assert!(valid_request(&read_request(&mut server).unwrap(), "7:11"));
        let (mut client, mut server) = UnixStream::pair().unwrap();
        client.write_all(&vec![b'x'; REQUEST_MAX + 1]).unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        assert!(read_request(&mut server).is_err());
        let status = Status {
            generation: 1,
            policy_sha256: "c".repeat(64),
            server_sha256: "a".repeat(64),
            client_sha256: vec!["b".repeat(64)],
            last_result: "x".repeat(RESPONSE_MAX),
            draining: false,
        };
        assert!(write_reply(&mut server, &reply("7:11", status, false, None)).is_err());
    }

    #[test]
    fn full_policy_and_draining_are_required_independent_status_fields() {
        let status = Status {
            generation: 1,
            policy_sha256: "c".repeat(64),
            server_sha256: "a".repeat(64),
            client_sha256: vec!["b".repeat(64)],
            last_result: "draining".into(),
            draining: true,
        };
        assert!(valid_status(&status));
        let response = reply("7:11", status.clone(), false, None);
        assert!(response.ok && !response.busy && response.status.draining);
        let mut other_policy = status.clone();
        other_policy.policy_sha256 = "d".repeat(64);
        assert!(valid_status(&other_policy));
        assert_eq!(status.generation, other_policy.generation);
        assert_ne!(status.policy_sha256, other_policy.policy_sha256);
        for field in ["policy_sha256", "draining"] {
            let mut value = serde_json::to_value(&status).unwrap();
            value.as_object_mut().unwrap().remove(field);
            assert!(serde_json::from_value::<Status>(value).is_err());
        }
        other_policy.policy_sha256 = "not-a-public-hash".into();
        assert!(!valid_status(&other_policy));
        other_policy.policy_sha256 = status.policy_sha256;
        other_policy.last_result = "unknown".into();
        assert!(!valid_status(&other_policy));
    }

    #[test]
    fn process_identity_uses_pid_and_proc_start_field() {
        let identity = process_identity().unwrap();
        let (pid, start) = identity.split_once(':').unwrap();
        assert_eq!(pid.parse::<u32>().unwrap(), std::process::id());
        assert!(start.parse::<u64>().is_ok());
    }
}
