//! TLS policy activation and actual Work admission share one short memory lock.
use crate::{
    Config,
    control::Lifecycle,
    native::Policy,
    tls_reload_ipc::{Backend, Status},
};
use rustls::{
    pki_types::{CertificateDer, UnixTime},
    server::danger::ClientCertVerifier,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    future::Future,
    path::PathBuf,
    sync::{
        Arc, Condvar, Mutex,
        atomic::{AtomicU8, Ordering},
    },
    task::{Poll, Waker},
    time::Duration,
};
use tokio::sync::watch;

const IDLE: u8 = 0;
const QUEUED: u8 = 1;
const RUNNING: u8 = 2;
const FINAL: u8 = 3;
pub(crate) fn plan(
    c: &Config,
) -> Result<Option<mover_fs::ingress::SocketPlan>, Box<dyn std::error::Error>> {
    if !c
        .native_ingress
        .as_ref()
        .is_some_and(crate::native::NativeIngress::https)
    {
        return Ok(None);
    }
    let path = std::path::Path::new(&c.state_database)
        .parent()
        .ok_or("local state parent required")?
        .join("tls-reload.sock");
    Ok(Some(mover_fs::ingress::SocketPlan::operator(
        path.to_str().ok_or("UTF-8 reload path required")?,
    )?))
}
struct ConnectionState {
    phase: AtomicU8,
    peer: Mutex<Option<Vec<CertificateDer<'static>>>>,
    waker: Mutex<Option<Waker>>,
}
impl ConnectionState {
    fn may_finish(&self) -> bool {
        matches!(self.phase.load(Ordering::Acquire), RUNNING | FINAL)
    }
    fn phase(&self, value: u8) {
        self.phase.store(value, Ordering::Release);
        if let Some(w) = self.waker.lock().expect("TLS waker").as_ref() {
            w.wake_by_ref();
        }
    }
}
struct Active {
    generation: u64,
    next_connection: u64,
    policy: Arc<Policy>,
    connections: BTreeMap<u64, (u64, Arc<ConnectionState>)>,
    loading: bool,
    draining: bool,
    last_result: &'static str,
}
pub(crate) struct Manager {
    original: Config,
    parents: BTreeSet<PathBuf>,
    lifecycle: Arc<Lifecycle>,
    guard: Arc<mover_fs::InstanceGuard>,
    active: Mutex<Active>,
    drained: Condvar,
    changed: watch::Sender<u64>,
}
#[derive(Clone)]
pub(crate) struct Lease {
    manager: Arc<Manager>,
    generation: u64,
    state: Arc<ConnectionState>,
    verifier: Arc<dyn ClientCertVerifier>,
}
pub(crate) struct Session {
    lease: Lease,
    id: u64,
    changed: watch::Receiver<u64>,
}
pub(crate) struct Permit {
    lease: Lease,
    finished: bool,
}

impl Manager {
    pub(crate) fn new(
        c: Config,
        policy: Arc<Policy>,
        lifecycle: Arc<Lifecycle>,
        guard: Arc<mover_fs::InstanceGuard>,
    ) -> Arc<Self> {
        let parents = c
            .native_ingress
            .as_ref()
            .expect("native TLS configuration")
            .credential_paths()
            .iter()
            .map(|p| {
                std::path::Path::new(p)
                    .parent()
                    .expect("validated credential parent")
                    .to_path_buf()
            })
            .collect();
        let (changed, _) = watch::channel(1);
        Arc::new(Self {
            original: c,
            parents,
            lifecycle,
            guard,
            active: Mutex::new(Active {
                generation: 1,
                next_connection: 0,
                policy,
                connections: BTreeMap::new(),
                loading: false,
                draining: false,
                last_result: "ready",
            }),
            drained: Condvar::new(),
            changed,
        })
    }
    /// Register AND snapshot under the activation lock: no missed old session.
    pub(crate) fn session(self: &Arc<Self>) -> Option<(Arc<Policy>, Session)> {
        let mut active = self.active.lock().expect("TLS active policy");
        if self.lifecycle.stop.load(Ordering::Relaxed) || active.connections.len() >= 6 {
            return None;
        }
        active.next_connection = active.next_connection.checked_add(1)?;
        let id = active.next_connection;
        let generation = active.generation;
        let policy = active.policy.clone();
        let state = Arc::new(ConnectionState {
            phase: AtomicU8::new(IDLE),
            peer: Mutex::new(None),
            waker: Mutex::new(None),
        });
        active.connections.insert(id, (generation, state.clone()));
        let lease = Lease {
            manager: self.clone(),
            generation,
            state,
            verifier: policy.client_verifier.clone(),
        };
        Some((
            policy,
            Session {
                lease,
                id,
                changed: self.changed.subscribe(),
            },
        ))
    }
    fn status(active: &Active) -> Status {
        Status {
            generation: active.generation,
            server_sha256: active.policy.server_sha256.clone(),
            client_sha256: active.policy.fingerprints.iter().cloned().collect(),
            policy_sha256: active.policy.policy_sha256.clone(),
            draining: active.draining,
            last_result: active.last_result.into(),
        }
    }
    fn candidate(&self, c: &Config) -> Result<Arc<Policy>, &'static str> {
        c.validate().map_err(|_| "invalid reload configuration")?;
        let mut before = self.original.clone();
        before.native_ingress = None;
        let mut after = c.clone();
        after.native_ingress = None;
        if serde_json::to_value(before).map_err(|_| "configuration comparison failed")?
            != serde_json::to_value(after).map_err(|_| "configuration comparison failed")?
        {
            return Err("only TLS credentials/trust/client mappings may change");
        }
        let native = c
            .native_ingress
            .as_ref()
            .filter(|n| n.https())
            .ok_or("HTTPS reload required")?;
        let initial = self
            .original
            .native_ingress
            .as_ref()
            .expect("native TLS configuration");
        let before =
            serde_json::to_value(initial).map_err(|_| "configuration comparison failed")?;
        let after = serde_json::to_value(native).map_err(|_| "configuration comparison failed")?;
        if before["authority"] != after["authority"]
            || native.operator_socket() != initial.operator_socket()
        {
            return Err("TLS authority/operator socket changes require restart");
        }
        for p in native.credential_paths() {
            if !std::path::Path::new(p)
                .parent()
                .is_some_and(|p| self.parents.contains(p))
            {
                return Err("credential directory changes require restart");
            }
        }
        self.guard
            .validate()
            .map_err(|_| "instance ownership refused")?;
        let policy = native
            .load()
            .map_err(|_| "replacement TLS credentials or policy refused")?
            .ok_or("HTTPS reload required")?;
        self.guard
            .validate()
            .map_err(|_| "instance ownership refused")?;
        Ok(policy)
    }
}
impl Backend for Manager {
    fn snapshot(&self) -> Status {
        Self::status(&self.active.lock().expect("TLS active policy"))
    }
    fn reload(&self, c: Config, expected_generation: u64) -> Result<Status, &'static str> {
        {
            let mut a = self.active.lock().expect("TLS active policy");
            if a.loading {
                return Err("TLS reload already active");
            }
            if a.generation != expected_generation {
                return Err("TLS policy generation changed");
            }
            if self.lifecycle.stop.load(Ordering::Relaxed) {
                return Err("service stopping");
            }
            a.loading = true;
            a.last_result = "loading";
        }
        // No activation lock, SQLite, payload traversal or Tokio executor I/O.
        let candidate = self.candidate(&c);
        let mut a = self.active.lock().expect("TLS active policy");
        let policy = match candidate {
            Ok(policy) => policy,
            Err(e) => {
                a.loading = false;
                a.last_result = "rejected";
                return Err(e);
            }
        };
        let Some(generation) = a.generation.checked_add(1) else {
            a.loading = false;
            a.last_result = "rejected";
            return Err("TLS generation exhausted");
        };
        if self
            .lifecycle
            .while_running(|| {
                a.policy = policy;
                a.generation = generation;
                a.draining = true;
                a.last_result = "draining";
                self.changed.send_replace(generation);
            })
            .is_none()
        {
            a.loading = false;
            a.last_result = "stopping";
            return Err("service stopping");
        }
        // Session registry lifetime is separate from queued Work/Lease clones.
        // Already admitted process calls or their terminal replies may finish.
        while a
            .connections
            .values()
            .any(|(g, s)| *g < generation && !s.may_finish())
        {
            a = self
                .drained
                .wait_timeout(a, Duration::from_millis(100))
                .expect("TLS exclusion drain")
                .0;
        }
        a.draining = false;
        a.loading = false;
        a.last_result = "applied";
        Ok(Self::status(&a))
    }
}
impl Lease {
    pub(crate) fn set_peer(&self, peer: Vec<CertificateDer<'static>>) {
        *self.state.peer.lock().expect("TLS peer") = Some(peer);
    }
    pub(crate) fn queue(&self) -> bool {
        let a = self.manager.active.lock().expect("TLS active policy");
        if a.generation != self.generation
            || self.manager.lifecycle.stop.load(Ordering::Relaxed)
            || self.state.phase.load(Ordering::Acquire) != IDLE
        {
            return false;
        }
        self.state.phase(QUEUED);
        true
    }
    pub(crate) fn admit(&self) -> Result<Permit, ()> {
        self.admit_at(UnixTime::now())
    }
    fn admit_at(&self, now: UnixTime) -> Result<Permit, ()> {
        let peer = self.state.peer.lock().map_err(|_| ())?.clone().ok_or(())?;
        let (leaf, chain) = peer.split_first().ok_or(())?;
        // Revalidate real certificate expiry/usage/chain on the effect thread.
        self.verifier
            .verify_client_cert(leaf, chain, now)
            .map_err(|_| ())?;
        let a = self.manager.active.lock().map_err(|_| ())?;
        if a.generation != self.generation
            || self.state.phase.load(Ordering::Acquire) != QUEUED
            || !a
                .policy
                .fingerprints
                .contains(&mover_fs::sha256_hex(leaf.as_ref()))
        {
            return Err(());
        }
        self.manager
            .lifecycle
            .while_running(|| self.state.phase(RUNNING))
            .ok_or(())?;
        Ok(Permit {
            lease: self.clone(),
            finished: false,
        })
    }
    fn finish(&self, terminal: bool) {
        let _a = self.manager.active.lock().expect("TLS active policy");
        self.state.phase(if terminal { FINAL } else { IDLE });
        self.manager.drained.notify_all();
    }
}
impl Permit {
    pub(crate) fn finish(mut self, terminal: bool) {
        self.lease.finish(terminal);
        self.finished = true;
    }
}
impl Drop for Permit {
    fn drop(&mut self) {
        if !self.finished {
            self.lease.finish(false);
        }
    }
}
impl Session {
    pub(crate) fn lease(&self) -> Lease {
        self.lease.clone()
    }
    pub(crate) async fn run(mut self, future: impl Future<Output = ()>) {
        let mut revoked = *self.changed.borrow() != self.lease.generation;
        let mut changed = Box::pin(self.changed.changed());
        let mut future = Box::pin(future);
        std::future::poll_fn(|cx| {
            *self.lease.state.waker.lock().expect("TLS waker") = Some(cx.waker().clone());
            if !revoked && changed.as_mut().poll(cx).is_ready() {
                revoked = true;
            }
            if revoked && !self.lease.state.may_finish() {
                return Poll::Ready(());
            }
            future.as_mut().poll(cx)
        })
        .await;
        // `future` (and its TCP/TLS stream) drops before Session's registry token.
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        let mut a = self.lease.manager.active.lock().expect("TLS active policy");
        a.connections.remove(&self.id);
        self.lease.state.waker.lock().expect("TLS waker").take();
        self.lease.manager.drained.notify_all();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{os::unix::fs::PermissionsExt, path::Path, sync::atomic::AtomicU64, time::Instant};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture {
        root: PathBuf,
        c: Config,
        manager: Arc<Manager>,
    }
    fn certificate(name: &str) -> Vec<u8> {
        std::fs::read(
            Path::new(&std::env::var("FILE_MOVER_TLS_FIXTURES").expect("SLES gate TLS fixtures"))
                .join(name),
        )
        .unwrap()
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "tls-manager-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&root).unwrap();
            std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700)).unwrap();
            for name in ["state", "operator"] {
                std::fs::create_dir(root.join(name)).unwrap();
                std::fs::set_permissions(root.join(name), std::fs::Permissions::from_mode(0o700))
                    .unwrap();
            }
            let mut c: Config =
                serde_json::from_str(include_str!("../../../config/local.example.json")).unwrap();
            let cert = PathBuf::from(std::env::var("FILE_MOVER_TLS_FIXTURES").unwrap());
            c.bind = "127.0.0.1:8443".parse().unwrap();
            c.state_database = root.join("state/jobs.sqlite").to_str().unwrap().into();
            c.native_ingress=Some(serde_json::from_value(serde_json::json!({"transport":"https","operator_socket":root.join("operator/api.sock"),"authority":"localhost:8443","server_certificates":[cert.join("server.der")],"server_key":cert.join("server.key.der"),"server_ca_certificates":[cert.join("ca.der")],"client_ca_certificates":[cert.join("ca.der")],"clients":[{"sha256":mover_fs::sha256_hex(&certificate("client.der")),"generator_id":c.generator_id}]})).unwrap());
            c.validate().unwrap();
            let guard = Arc::new(mover_fs::InstanceGuard::for_database(&c.state_database).unwrap());
            let policy = c.native_ingress.as_ref().unwrap().load().unwrap().unwrap();
            let manager = Manager::new(
                c.clone(),
                policy,
                Lifecycle::new(Arc::new(std::sync::atomic::AtomicBool::new(false)), 5),
                guard,
            );
            Self { root, c, manager }
        }
        fn session(&self) -> Session {
            let (_, s) = self.manager.session().unwrap();
            s.lease
                .set_peer(vec![CertificateDer::from(certificate("client.der"))]);
            s
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.root);
        }
    }
    #[test]
    fn cancelled_session_registry_is_independent_of_stale_queued_work() {
        let f = Fixture::new();
        let session = f.session();
        let queued = session.lease();
        assert!(queued.queue());
        drop(session);
        assert_eq!(f.manager.reload(f.c.clone(), 1).unwrap().generation, 2);
        assert!(queued.admit().is_err());
        assert!(!queued.queue());
        assert!(f.manager.active.lock().unwrap().connections.is_empty());
    }
    #[test]
    fn activation_before_first_future_poll_still_drains_the_registered_connection() {
        let f = Fixture::new();
        let session = f.session();
        let manager = f.manager.clone();
        let c = f.c.clone();
        let thread = std::thread::spawn(move || manager.reload(c, 1));
        let until = Instant::now() + Duration::from_secs(5);
        while f.manager.snapshot().generation == 1 {
            assert!(Instant::now() < until);
            std::thread::sleep(Duration::from_millis(5));
        }
        assert!(f.manager.snapshot().draining);
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
            .block_on(async {
                tokio::time::timeout(Duration::from_secs(2), session.run(std::future::pending()))
                    .await
                    .unwrap();
            });
        let status = thread.join().unwrap().unwrap();
        assert!(!status.draining);
        assert_eq!(status.last_result, "applied");
    }
    #[test]
    fn admitted_work_may_finish_but_deferral_cannot_authorize_a_later_attempt() {
        let f = Fixture::new();
        let session = f.session();
        let lease = session.lease();
        assert!(lease.queue());
        let permit = lease.admit().unwrap();
        assert_eq!(f.manager.reload(f.c.clone(), 1).unwrap().generation, 2);
        permit.finish(false);
        assert!(!lease.queue());
        assert!(lease.admit().is_err());
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
            .block_on(async {
                tokio::time::timeout(Duration::from_secs(2), session.run(std::future::pending()))
                    .await
                    .unwrap();
            });
        assert!(f.manager.active.lock().unwrap().connections.is_empty());
    }
    #[test]
    fn certificate_expiry_is_rechecked_at_actual_admission_without_changing_host_time() {
        let f = Fixture::new();
        let session = f.session();
        let lease = session.lease();
        assert!(lease.queue());
        let future = UnixTime::since_unix_epoch(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                + Duration::from_secs(3 * 86400),
        );
        assert!(lease.admit_at(future).is_err());
        assert_eq!(lease.state.phase.load(Ordering::Acquire), QUEUED);
        lease.admit().unwrap().finish(true);
    }
    #[test]
    fn rejected_replacement_and_shutdown_preserve_the_active_policy() {
        let f = Fixture::new();
        let before = f.manager.snapshot();
        let mut c = f.c.clone();
        c.check_expected_sizes = true;
        assert!(f.manager.reload(c, 1).is_err());
        assert_eq!(f.manager.snapshot().policy_sha256, before.policy_sha256);
        assert_eq!(f.manager.snapshot().generation, 1);
        f.manager.lifecycle.request_stop();
        assert!(f.manager.reload(f.c.clone(), 1).is_err());
        assert_eq!(f.manager.snapshot().generation, 1);
    }
}
