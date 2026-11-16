//! Live admin password activation over a host-local socket.
//!
//! Design: docs/dashboard/PASSWORD-ACTIVATION-DESIGN.md. The host-local
//! `--admin-password-change` command derives the verifier itself (the password
//! never reaches the service), sends it here, and the running service, which
//! owns the account directory while it runs, publishes the next revision and
//! then activates it through `Sessions::activate_serialized` before replying.
//! No HTTP route; separate from the lifecycle, producer and operator sockets.
use crate::{account::Record, admin::Admin, password::Verifier};
use mover_fs::InstanceGuard;
use std::{
    collections::VecDeque,
    io::{Read, Write},
    os::unix::net::{UnixListener, UnixStream},
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use zeroize::Zeroizing;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

pub(crate) const SOCKET: &str = "account.sock";
const REQUEST_LIMIT: usize = 2048;
const REPLY_LIMIT: usize = 1024;
/// The whole request must arrive within this time; reply writes have the same bound.
const FRAME_DEADLINE: Duration = Duration::from_secs(1);
/// Bounded wait for actions admitted before a password activation.
const SETTLE: Duration = Duration::from_secs(10);
/// Retained change outcomes (in memory; cleared by restart).
const HISTORY: usize = 16;

/// Where the account lives, as computed by the guarded startup preflight.
pub(crate) struct AccountScope {
    pub(crate) directory: String,
    pub(crate) excluded: Vec<String>,
    pub(crate) instance_id: String,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Outcome {
    Activated { revision: u64, settled: bool },
    Unchanged,
    Uncertain,
}

struct Handler {
    admin: Arc<Admin>,
    scope: AccountScope,
    identity: String,
    history: VecDeque<(String, Outcome)>,
}

pub(crate) struct Server {
    quit: Arc<AtomicBool>,
    thread: Option<std::thread::JoinHandle<()>>,
    path: PathBuf,
    socket: (u64, u64),
    guard: Arc<InstanceGuard>,
}

impl Server {
    /// Bind `account.sock` beside `control.sock` (same custody rules) and serve
    /// one request at a time on a dedicated thread until `stop` or drop. The
    /// thread holds the instance guard; drop joins it before ownership ends.
    pub(crate) fn start(
        guard: Arc<InstanceGuard>,
        admin: Arc<Admin>,
        scope: AccountScope,
        stop: Arc<AtomicBool>,
    ) -> Result<Self> {
        guard.validate()?;
        let path = Path::new(guard.state_directory()).join(SOCKET);
        match std::fs::symlink_metadata(&path) {
            Ok(_) => {
                crate::control::socket_identity(&path)?;
                std::fs::remove_file(&path)?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
        let listener = UnixListener::bind(&path)?;
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        }
        let socket = crate::control::socket_identity(&path)?;
        listener.set_nonblocking(true)?;
        let identity =
            crate::control::local_identity().ok_or("local process identity unavailable")?;
        let quit = Arc::new(AtomicBool::new(false));
        let thread_quit = quit.clone();
        let thread_guard = guard.clone();
        let mut handler = Handler {
            admin,
            scope,
            identity,
            history: VecDeque::new(),
        };
        let thread = std::thread::Builder::new()
            .name("mover-account".into())
            .spawn(move || {
                while !thread_quit.load(Ordering::Relaxed) && !stop.load(Ordering::Relaxed) {
                    match listener.accept() {
                        Ok((stream, _)) => {
                            if thread_guard.validate().is_err() {
                                break;
                            }
                            handler.serve(stream);
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(Duration::from_millis(10))
                        }
                        Err(_) => break,
                    }
                }
            })?;
        Ok(Self {
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
        if self.guard.validate().is_ok()
            && crate::control::socket_identity(&self.path).ok() == Some(self.socket)
        {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}

/// Whole request within `FRAME_DEADLINE` (trickled bytes cannot hold the
/// thread), at most `limit` bytes, ended by the peer's write shutdown.
fn read_frame(stream: &mut UnixStream, limit: usize) -> Result<Vec<u8>> {
    let deadline = Instant::now() + FRAME_DEADLINE;
    let mut bytes = Vec::new();
    let mut chunk = [0_u8; 512];
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return Err("account request deadline exceeded".into());
        }
        stream.set_read_timeout(Some(left))?;
        match stream.read(&mut chunk) {
            Ok(0) => return Ok(bytes),
            Ok(n) => {
                bytes.extend_from_slice(&chunk[..n]);
                if bytes.len() > limit {
                    return Err("account request too large".into());
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => (),
            Err(_) => return Err("account request deadline exceeded".into()),
        }
    }
}

fn valid_change_id(id: &str) -> bool {
    id.len() == 64
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl Handler {
    fn serve(&mut self, mut stream: UnixStream) {
        let result = (|| -> Result<()> {
            // Only the service's own user: socket mode plus peer credentials.
            if mover_fs::socket_peer_uid(&stream)? != mover_fs::effective_uid() {
                return Err("account control peer refused".into());
            }
            let bytes = read_frame(&mut stream, REQUEST_LIMIT)?;
            let request: serde_json::Value = serde_json::from_slice(&bytes)?;
            let reply = self.handle(&request)?;
            let out = serde_json::to_vec(&reply)?;
            if out.len() > REPLY_LIMIT {
                return Err("account reply too large".into());
            }
            stream.set_write_timeout(Some(FRAME_DEADLINE))?;
            stream.write_all(&out)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = stream.shutdown(std::net::Shutdown::Both);
        }
    }

    fn handle(&mut self, request: &serde_json::Value) -> Result<serde_json::Value> {
        let object = request.as_object().ok_or("invalid account request")?;
        let text = |k: &str| object.get(k).and_then(|v| v.as_str());
        if object.get("version") != Some(&serde_json::json!(1)) {
            return Err("unsupported account request version".into());
        }
        if let Some(id) = object.get("instance_id")
            && !id.is_null()
            && id.as_str() != Some(self.identity.as_str())
        {
            return Ok(Self::unchanged("instance_changed"));
        }
        match text("command") {
            Some("account-status") => {
                let allowed = ["version", "command", "instance_id", "change_id"];
                if object.keys().any(|k| !allowed.contains(&k.as_str())) {
                    return Err("invalid account status request".into());
                }
                let change = match object.get("change_id") {
                    None | Some(serde_json::Value::Null) => None,
                    Some(v) => Some(
                        v.as_str()
                            .filter(|id| valid_change_id(id))
                            .ok_or("invalid change id")?,
                    ),
                };
                Ok(self.status(change))
            }
            Some("password-replace") => {
                let allowed = [
                    "version",
                    "command",
                    "instance_id",
                    "change_id",
                    "base_revision",
                    "verifier",
                ];
                if object.keys().any(|k| !allowed.contains(&k.as_str()))
                    || text("instance_id").is_none()
                {
                    return Err("invalid password replace request".into());
                }
                let change_id = text("change_id")
                    .filter(|id| valid_change_id(id))
                    .ok_or("invalid change id")?
                    .to_owned();
                let base = text("base_revision")
                    .filter(|r| r.len() <= 20 && r.bytes().all(|b| b.is_ascii_digit()))
                    .and_then(|r| r.parse::<u64>().ok())
                    .ok_or("invalid base revision")?;
                let verifier =
                    Zeroizing::new(text("verifier").ok_or("verifier required")?.to_owned());
                Ok(self.replace(change_id, base, &verifier))
            }
            _ => Err("unknown account command".into()),
        }
    }

    fn published(&self) -> Option<Zeroizing<Vec<u8>>> {
        let area =
            mover_fs::account_file::open(&self.scope.directory, &self.scope.excluded).ok()?;
        area.read().ok().flatten().map(Zeroizing::new)
    }
    fn published_revision(&self) -> Option<u64> {
        let bytes = self.published()?;
        Record::decode(&bytes, &self.scope.instance_id)
            .ok()
            .map(|r| r.revision)
    }

    fn status(&self, change: Option<&str>) -> serde_json::Value {
        let active = self.admin.sessions.account();
        let published = self.published_revision();
        let change =
            change.map(
                |id| match self.history.iter().find(|(c, _)| c == id).map(|(_, o)| *o) {
                    None => serde_json::Value::Null,
                    Some(o) => outcome_json(o, Some(standing(o, active.revision, published))),
                },
            );
        serde_json::json!({
            "version": 1,
            "instance_id": self.identity,
            "username": active.username,
            "active_revision": active.revision.to_string(),
            "published_revision": published.map(|r| r.to_string()),
            "change": change.unwrap_or(serde_json::Value::Null),
        })
    }

    fn unchanged(code: &str) -> serde_json::Value {
        serde_json::json!({"version": 1, "outcome": "unchanged", "code": code})
    }
    fn remember(&mut self, change_id: String, outcome: Outcome) {
        if self.history.len() == HISTORY {
            self.history.pop_front();
        }
        self.history.push_back((change_id, outcome));
    }

    fn replace(&mut self, change_id: String, base: u64, verifier: &str) -> serde_json::Value {
        // A change still retained is never applied twice; after eviction or
        // restart the base-revision check refuses an exact old request.
        if self.history.iter().any(|(c, _)| *c == change_id) {
            return Self::unchanged("duplicate_change");
        }
        let (outcome, code) = self.apply(base, verifier);
        self.remember(change_id, outcome);
        match outcome {
            Outcome::Unchanged => Self::unchanged(code),
            o => {
                let mut v = outcome_json(o, None);
                if let Outcome::Uncertain = o {
                    v["code"] = code.into();
                }
                v
            }
        }
    }

    fn apply(&self, base: u64, verifier: &str) -> (Outcome, &'static str) {
        let active = self.admin.sessions.account();
        if active.revision != base {
            return (Outcome::Unchanged, "revision_conflict");
        }
        let Ok(verifier) = Verifier::from_encoded(verifier.to_owned()) else {
            return (Outcome::Unchanged, "invalid_verifier");
        };
        // The service owns the account directory while running: re-read the
        // published record under account.lock and require it to be the active
        // one (a published-but-not-activated change is never overwritten).
        let Ok(area) = mover_fs::account_file::open(&self.scope.directory, &self.scope.excluded)
        else {
            return (Outcome::Unchanged, "refused");
        };
        let Some(old) = area.read().ok().flatten().map(Zeroizing::new) else {
            return (Outcome::Unchanged, "account_changed");
        };
        match Record::decode(&old, &self.scope.instance_id) {
            Ok(on_disk) if on_disk.same_record(&active) => (),
            _ => return (Outcome::Unchanged, "account_changed"),
        }
        let Ok(next) = active.with_verifier(verifier) else {
            return (Outcome::Unchanged, "refused");
        };
        let revision = next.revision;
        let Ok(bytes) = next.encode() else {
            return (Outcome::Unchanged, "refused");
        };
        if area.publish(&bytes, Some(&old)).is_err() {
            // Unchanged only if the old record is provably still published.
            let still_old = area
                .read()
                .ok()
                .flatten()
                .is_some_and(|now| now.as_slice() == old.as_slice());
            return if still_old {
                (Outcome::Unchanged, "refused")
            } else {
                (Outcome::Uncertain, "publication_uncertain")
            };
        }
        drop(area);
        match self.admin.sessions.activate_serialized(base, next, SETTLE) {
            Ok(settled) => (Outcome::Activated { revision, settled }, ""),
            Err(_) => (Outcome::Uncertain, "activation_failed"),
        }
    }
}

/// Standing of an activated change: decided by the active revision first.
fn standing(outcome: Outcome, active: u64, published: Option<u64>) -> &'static str {
    match outcome {
        Outcome::Activated { revision, .. } if active > revision => "superseded",
        Outcome::Activated { revision, .. }
            if active == revision && published == Some(revision) =>
        {
            "active"
        }
        _ => "unverified",
    }
}

fn outcome_json(outcome: Outcome, standing: Option<&str>) -> serde_json::Value {
    let mut v = match outcome {
        Outcome::Activated { revision, settled } => serde_json::json!({
            "version": 1, "outcome": "activated", "revision": revision.to_string(), "settled": settled}),
        Outcome::Unchanged => serde_json::json!({"version": 1, "outcome": "unchanged"}),
        Outcome::Uncertain => serde_json::json!({"version": 1, "outcome": "uncertain"}),
    };
    if let (Outcome::Activated { .. }, Some(s)) = (outcome, standing) {
        v["standing"] = s.into();
    }
    v
}

// ---- host-local client ----

/// One request to the running service's account socket. `wait` bounds the
/// reply (a replace includes publication and the activation settle time).
pub(crate) fn call(
    database: &str,
    request: &serde_json::Value,
    wait: Duration,
) -> Result<serde_json::Value> {
    let path = endpoint(database).ok_or(
        "the running service has no account control endpoint (admin_ingress not configured, or the service is stopping)",
    )?;
    let mut stream = UnixStream::connect(&path)?;
    stream.set_write_timeout(Some(FRAME_DEADLINE))?;
    stream.write_all(&serde_json::to_vec(request)?)?;
    stream.shutdown(std::net::Shutdown::Write)?;
    stream.set_read_timeout(Some(wait))?;
    let mut bytes = Vec::new();
    (&mut stream)
        .take((REPLY_LIMIT + 1) as u64)
        .read_to_end(&mut bytes)?;
    if bytes.is_empty() || bytes.len() > REPLY_LIMIT {
        return Err("account control reply missing or too large".into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}

/// The account socket of the service owning `database`, if it serves one.
pub(crate) fn endpoint(database: &str) -> Option<std::path::PathBuf> {
    let path = Path::new(database).parent()?.join(SOCKET);
    crate::control::socket_identity(&path).ok().map(|_| path)
}

/// A fresh random change id (32 bytes, hex).
pub(crate) fn new_change_id() -> Result<String> {
    let mut id = Zeroizing::new([0_u8; 32]);
    crate::tls::provider()
        .secure_random
        .fill(id.as_mut())
        .map_err(|_| "entropy unavailable")?;
    Ok(id.iter().map(|b| format!("{b:02x}")).collect())
}

/// Wait bound for a replace reply.
pub(crate) const REPLACE_WAIT: Duration = Duration::from_secs(30);
/// Wait bound for a status reply.
pub(crate) const STATUS_WAIT: Duration = Duration::from_secs(5);

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn standing_follows_the_active_revision_first() {
        let a = Outcome::Activated {
            revision: 5,
            settled: true,
        };
        assert_eq!(standing(a, 5, Some(5)), "active");
        assert_eq!(standing(a, 6, Some(6)), "superseded");
        // Published read-back unavailable or ahead: still active in memory.
        assert_eq!(standing(a, 5, None), "unverified");
        assert_eq!(standing(a, 5, Some(6)), "unverified");
        assert_eq!(outcome_json(a, Some("active"))["standing"], "active");
        assert_eq!(
            outcome_json(Outcome::Unchanged, Some("active")).get("standing"),
            None
        );
    }
    #[test]
    fn change_ids_are_exact_lowercase_hex() {
        assert!(valid_change_id(&"a1".repeat(32)));
        assert!(!valid_change_id(&"A1".repeat(32)));
        assert!(!valid_change_id(&"a1".repeat(31)));
        assert!(valid_change_id(&new_change_id().unwrap()));
    }
    #[test]
    fn a_trickled_request_is_cut_off_at_the_deadline() {
        let (mut server, mut client) = UnixStream::pair().unwrap();
        let writer = std::thread::spawn(move || {
            for _ in 0..30 {
                if client.write_all(b" ").is_err() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(60));
            }
        });
        let began = Instant::now();
        assert!(read_frame(&mut server, REQUEST_LIMIT).is_err());
        assert!(began.elapsed() < Duration::from_millis(1500));
        drop(server);
        writer.join().unwrap();
    }
    #[test]
    fn oversized_requests_are_refused() {
        let (mut server, mut client) = UnixStream::pair().unwrap();
        client.write_all(&vec![b'x'; REQUEST_LIMIT + 1]).unwrap();
        client.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(read_frame(&mut server, REQUEST_LIMIT).is_err());
    }
}
