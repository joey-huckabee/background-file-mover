//! Bounded in-memory admin sessions: one password-verifier slot, a per-instance
//! login rate limit, global revocation and monotonic inactivity expiry.
//!
//! No listener, cookie, header or HTTP status mapping lives here; the admin HTTPS
//! increment maps these outcomes onto the frozen contract. Sessions are never
//! persisted: a restart starts with an empty map. Revoking sessions never touches
//! transfers, which belong to the service.
//!
//! Lock discipline: one mutex serializes admission, minting, authorization and
//! revocation. Password hashing, entropy and record I/O never run under it.
use crate::account::Record;
use crate::password::Password;
use std::collections::VecDeque;
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};
use subtle::ConstantTimeEq;
use zeroize::Zeroizing;

pub const MAX_SESSIONS: usize = 64;
pub const LOGIN_ATTEMPTS: usize = 5;
pub const LOGIN_WINDOW: Duration = Duration::from_secs(60);
pub const DEFAULT_IDLE: Duration = Duration::from_secs(1800);
const TOKEN_BYTES: usize = 32;
const MINT_ATTEMPTS: usize = 4;

/// Login refusals. None of them carries a username, password or token.
#[derive(Debug, PartialEq, Eq)]
pub enum LoginError {
    /// Fifth admitted attempt in the rolling window already used (429, Retry-After 60).
    RateLimited,
    /// Verifier slot or session capacity full (503 service_busy). No eviction.
    Busy,
    /// Wrong username or password; deliberately indistinguishable (401).
    InvalidCredentials,
    /// Logout or password activation won the race against this login.
    Superseded,
    /// Caller stopped waiting. The verifier keeps its slot until it actually exits
    /// and its late result can never mint a session.
    TimedOut,
    /// Entropy, verifier, worker or shutdown failure. No session was issued.
    Unavailable,
}

#[derive(Debug, PartialEq, Eq)]
pub enum AuthError {
    /// Missing, malformed, unknown, expired or revoked session.
    Unauthenticated,
    /// Session valid but the supplied CSRF value does not match it.
    CsrfMismatch,
}

#[derive(Debug, PartialEq, Eq)]
pub enum ActivationError {
    /// Different principal/instance, or revision not strictly newer.
    Rejected,
    /// Revocation generation exhausted; the manager is closed instead.
    Closed,
}

/// Whether an authorized request renews inactivity. Background polling never does.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Activity {
    Background,
    Deliberate,
}

/// Fresh secrets for the caller to place in the cookie and CSRF header.
/// No Debug/Clone: do not log or duplicate.
pub struct Issued {
    pub session: Zeroizing<String>,
    pub csrf: Zeroizing<String>,
}

pub struct Authorized {
    pub csrf: Zeroizing<String>,
    pub revision: u64,
    pub generation: u64,
    /// Server-held account identity (64 hex); used as the audit principal.
    pub principal: String,
}

type Entropy = Box<dyn Fn(&mut [u8]) -> bool + Send + Sync>;

struct Session {
    token: Zeroizing<[u8; TOKEN_BYTES]>,
    csrf: Zeroizing<[u8; TOKEN_BYTES]>,
    revision: u64,
    generation: u64,
    last: Instant,
}

struct State {
    account: Arc<Record>,
    generation: u64,
    sessions: Vec<Session>,
    attempts: VecDeque<Instant>,
    worker: Option<JoinHandle<()>>,
    closed: bool,
}

/// Authority captured at admission and rechecked before minting.
#[derive(Debug)]
pub(crate) struct Ticket {
    revision: u64,
    generation: u64,
}

pub struct Sessions {
    state: Mutex<State>,
    idle: Duration,
    entropy: Entropy,
    /// Bumped on global revocation, activation and shutdown so open event
    /// streams close immediately instead of at their next session check.
    revoked: tokio::sync::watch::Sender<u64>,
}

impl Sessions {
    pub fn new(account: Record, idle: Duration) -> Self {
        Self::with_entropy(
            account,
            idle,
            Box::new(|bytes| crate::tls::provider().secure_random.fill(bytes).is_ok()),
        )
    }

    fn with_entropy(account: Record, idle: Duration, entropy: Entropy) -> Self {
        Self {
            state: Mutex::new(State {
                account: Arc::new(account),
                generation: 0,
                sessions: Vec::with_capacity(MAX_SESSIONS),
                attempts: VecDeque::with_capacity(LOGIN_ATTEMPTS),
                worker: None,
                closed: false,
            }),
            idle,
            entropy,
            revoked: tokio::sync::watch::Sender::new(0),
        }
    }

    /// Subscribe to revocation notices (logout, password activation, shutdown).
    pub(crate) fn revocations(&self) -> tokio::sync::watch::Receiver<u64> {
        self.revoked.subscribe()
    }
    fn announce_revocation(&self) {
        self.revoked.send_modify(|v| *v = v.wrapping_add(1));
    }

    fn lock(&self) -> MutexGuard<'_, State> {
        // A panic while holding the lock cannot leave partial session state that
        // grants more access than before: every mutation is a single push/clear.
        self.state.lock().unwrap_or_else(|p| p.into_inner())
    }

    fn prune(&self, state: &mut State, now: Instant) {
        let idle = self.idle;
        state
            .sessions
            .retain(|s| now.saturating_duration_since(s.last) < idle);
        while state
            .attempts
            .front()
            .is_some_and(|t| now.saturating_duration_since(*t) >= LOGIN_WINDOW)
        {
            state.attempts.pop_front();
        }
    }

    /// Verify credentials on one owned worker thread and, if authority is still
    /// current afterwards, mint a session. Dropping this future or exceeding
    /// `deadline` never mints and never frees the verifier slot early.
    pub async fn login(
        &self,
        username: &str,
        password: Password,
        deadline: Duration,
    ) -> Result<Issued, LoginError> {
        // Absolute liveness bound, rechecked under the minting lock so entropy
        // or lock waits after verification cannot mint past the deadline.
        let expires = Instant::now().checked_add(deadline);
        let (sender, receiver) = tokio::sync::oneshot::channel();
        let username = Zeroizing::new(username.to_owned());
        let ticket = self.admit(Instant::now(), move |account| {
            let expected = account.username.as_bytes();
            // Always run the full verifier, even for a wrong username, so the
            // response cost does not reveal which field was wrong.
            let verified = account.verify(&password);
            let name_ok = bool::from(username.as_bytes().ct_eq(expected));
            let _ = sender.send(verified.map(|ok| ok & name_ok).map_err(|_| ()));
        })?;
        let verified = match tokio::time::timeout(deadline, receiver).await {
            Err(_) => return Err(LoginError::TimedOut),
            Ok(Err(_)) | Ok(Ok(Err(()))) => return Err(LoginError::Unavailable),
            Ok(Ok(Ok(verified))) => verified,
        };
        self.finish_by(ticket, verified, Instant::now(), expires)
    }

    /// Admission under the lock: rate limit, single slot, capacity. The worker
    /// is spawned while the lock is held so no second admission can slip into
    /// the gap between slot check and handle registration. Spawning is not
    /// hashing or I/O; the work itself runs after the lock is released.
    pub(crate) fn admit(
        &self,
        now: Instant,
        work: impl FnOnce(&Record) + Send + 'static,
    ) -> Result<Ticket, LoginError> {
        let mut state = self.lock();
        if state.closed {
            return Err(LoginError::Unavailable);
        }
        self.prune(&mut state, now);
        if state.attempts.len() >= LOGIN_ATTEMPTS {
            return Err(LoginError::RateLimited);
        }
        if let Some(worker) = state.worker.take() {
            if !worker.is_finished() {
                state.worker = Some(worker);
                return Err(LoginError::Busy);
            }
            // Already exited; join only collects its status.
            let _ = worker.join();
        }
        if state.sessions.len() >= MAX_SESSIONS {
            return Err(LoginError::Busy);
        }
        let account = Arc::clone(&state.account);
        let worker = std::thread::Builder::new()
            .name("admin-verifier".into())
            .spawn(move || work(&account))
            .map_err(|_| LoginError::Unavailable)?;
        state.attempts.push_back(now);
        state.worker = Some(worker);
        Ok(Ticket {
            revision: state.account.revision,
            generation: state.generation,
        })
    }

    #[cfg(test)]
    fn finish(&self, ticket: Ticket, verified: bool, now: Instant) -> Result<Issued, LoginError> {
        self.finish_by(ticket, verified, now, None)
    }

    /// Recheck liveness and authority after verification, then mint under the lock.
    pub(crate) fn finish_by(
        &self,
        ticket: Ticket,
        verified: bool,
        now: Instant,
        expires: Option<Instant>,
    ) -> Result<Issued, LoginError> {
        for _ in 0..MINT_ATTEMPTS {
            // Entropy runs outside the lock; duplicates retry with fresh values.
            let mut token = Zeroizing::new([0_u8; TOKEN_BYTES]);
            let mut csrf = Zeroizing::new([0_u8; TOKEN_BYTES]);
            let entropy_ok =
                verified && (self.entropy)(token.as_mut()) && (self.entropy)(csrf.as_mut());
            let mut state = self.lock();
            if state.closed {
                return Err(LoginError::Unavailable);
            }
            if expires.is_some_and(|d| Instant::now() >= d) {
                return Err(LoginError::TimedOut);
            }
            if state.account.revision != ticket.revision || state.generation != ticket.generation {
                return Err(LoginError::Superseded);
            }
            if !verified {
                return Err(LoginError::InvalidCredentials);
            }
            if !entropy_ok {
                return Err(LoginError::Unavailable);
            }
            self.prune(&mut state, now);
            if state.sessions.len() >= MAX_SESSIONS {
                return Err(LoginError::Busy);
            }
            let duplicate = state
                .sessions
                .iter()
                .any(|s| bool::from(s.token.ct_eq(token.as_ref())));
            if duplicate || token.ct_eq(csrf.as_ref()).into() {
                continue;
            }
            let issued = Issued {
                session: hex(&token),
                csrf: hex(&csrf),
            };
            state.sessions.push(Session {
                token,
                csrf,
                revision: ticket.revision,
                generation: ticket.generation,
                last: now,
            });
            return Ok(issued);
        }
        Err(LoginError::Unavailable)
    }

    /// Authorize one request. `csrf` must be supplied for mutations and marked
    /// reads. Only `Activity::Deliberate` renews inactivity.
    pub fn authorize(
        &self,
        session: &str,
        csrf: Option<&str>,
        activity: Activity,
        now: Instant,
    ) -> Result<Authorized, AuthError> {
        // Authentication precedes CSRF: an unknown, expired or revoked session
        // is 401 whatever CSRF value accompanies it.
        let token = unhex(session).ok_or(AuthError::Unauthenticated)?;
        let mut state = self.lock();
        if state.closed {
            return Err(AuthError::Unauthenticated);
        }
        self.prune(&mut state, now);
        let (revision, generation) = (state.account.revision, state.generation);
        let principal = state.account.account_id.clone();
        // Scan every entry so lookup time does not depend on the match position.
        let mut found = None;
        for (i, s) in state.sessions.iter().enumerate() {
            if bool::from(s.token.ct_eq(token.as_ref())) {
                found = Some(i);
            }
        }
        let s = found
            .map(|i| &mut state.sessions[i])
            .filter(|s| s.revision == revision && s.generation == generation)
            .ok_or(AuthError::Unauthenticated)?;
        if let Some(text) = csrf {
            let matches = unhex(text).is_some_and(|v| bool::from(s.csrf.ct_eq(v.as_ref())));
            if !matches {
                return Err(AuthError::CsrfMismatch);
            }
        }
        if activity == Activity::Deliberate && now > s.last {
            s.last = now;
        }
        Ok(Authorized {
            csrf: hex(&s.csrf),
            revision,
            generation,
            principal,
        })
    }

    /// Global manual logout: revoke every session and in-flight login authority.
    /// Generation exhaustion closes the manager rather than wrapping.
    pub fn logout_all(&self) -> Result<u64, ActivationError> {
        let result = {
            let mut state = self.lock();
            Self::revoke(&mut state)
        };
        self.announce_revocation();
        result
    }

    fn revoke(state: &mut State) -> Result<u64, ActivationError> {
        state.sessions.clear();
        match state.generation.checked_add(1) {
            Some(next) => {
                state.generation = next;
                Ok(next)
            }
            None => {
                state.closed = true;
                Err(ActivationError::Closed)
            }
        }
    }

    /// Activate an already validated newer revision of the same principal and
    /// revoke every session before returning. The record was decoded and checked
    /// by the caller outside this lock.
    pub fn activate(&self, record: Record) -> Result<u64, ActivationError> {
        let mut state = self.lock();
        if state.closed {
            return Err(ActivationError::Closed);
        }
        let current = &state.account;
        if record.instance_id != current.instance_id
            || record.account_id != current.account_id
            || record.username != current.username
            || record.revision <= current.revision
        {
            return Err(ActivationError::Rejected);
        }
        state.account = Arc::new(record);
        let result = Self::revoke(&mut state);
        drop(state);
        self.announce_revocation();
        result
    }

    /// Refuse all further work and hand back the verifier thread, if any. The
    /// owner must join it (off the async runtime) before releasing instance
    /// ownership; a timed-out verifier may still be running.
    pub fn shutdown(&self) -> Option<JoinHandle<()>> {
        let worker = {
            let mut state = self.lock();
            state.closed = true;
            state.sessions.clear();
            state.worker.take()
        };
        self.announce_revocation();
        worker
    }
}

/// Fallback ownership: dropping the manager without `shutdown` still refuses
/// further work and blocks until a running verifier actually exits, so its
/// thread is never detached. Owners should call `shutdown` and join off the
/// async runtime; this join then finds nothing to wait for.
impl Drop for Sessions {
    fn drop(&mut self) {
        if let Some(worker) = self.shutdown() {
            let _ = worker.join();
        }
    }
}

fn hex(bytes: &[u8; TOKEN_BYTES]) -> Zeroizing<String> {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = Zeroizing::new(String::with_capacity(TOKEN_BYTES * 2));
    for b in bytes {
        out.push(DIGITS[usize::from(b >> 4)] as char);
        out.push(DIGITS[usize::from(b & 15)] as char);
    }
    out
}

/// Accept only the canonical 64-character lowercase hex encoding.
fn unhex(text: &str) -> Option<Zeroizing<[u8; TOKEN_BYTES]>> {
    let text = text.as_bytes();
    if text.len() != TOKEN_BYTES * 2 {
        return None;
    }
    let digit = |c: u8| match c {
        b'0'..=b'9' => Some(c - b'0'),
        b'a'..=b'f' => Some(c - b'a' + 10),
        _ => None,
    };
    let mut out = Zeroizing::new([0_u8; TOKEN_BYTES]);
    for (i, pair) in text.as_chunks::<2>().0.iter().enumerate() {
        out[i] = (digit(pair[0])? << 4) | digit(pair[1])?;
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::OnceLock;
    use std::sync::atomic::{AtomicU8, Ordering};

    const INSTANCE: &str = "fixture-instance";

    fn pw(s: &str) -> Password {
        Password::new(s.as_bytes().to_vec()).unwrap()
    }

    /// One real Argon2id hash shared by every test; decoding never rehashes.
    fn record_bytes(revision: u64) -> Vec<u8> {
        static FIRST: OnceLock<Vec<u8>> = OnceLock::new();
        let first = FIRST.get_or_init(|| {
            Record::create(INSTANCE, "admin".into(), &pw("disposable fixture"))
                .unwrap()
                .encode()
                .unwrap()
                .to_vec()
        });
        let text = String::from_utf8(first.clone()).unwrap();
        text.replace("\"revision\":1", &format!("\"revision\":{revision}"))
            .into_bytes()
    }

    fn record(revision: u64) -> Record {
        Record::decode(&record_bytes(revision), INSTANCE).unwrap()
    }

    fn manager() -> Sessions {
        Sessions::new(record(1), DEFAULT_IDLE)
    }

    fn admit(s: &Sessions, now: Instant) -> Result<Ticket, LoginError> {
        s.admit(now, |_| {})
    }

    /// Admit and mint without hashing, waiting for the no-op worker to exit.
    fn mint(s: &Sessions, now: Instant) -> Issued {
        let ticket = admit(s, now).unwrap();
        let issued = s.finish(ticket, true, now).unwrap();
        wait_idle(s);
        issued
    }

    /// Mint against current authority without consuming a rate-limit attempt.
    fn issue(s: &Sessions, now: Instant) -> Result<Issued, LoginError> {
        let ticket = {
            let state = s.lock();
            Ticket {
                revision: state.account.revision,
                generation: state.generation,
            }
        };
        s.finish(ticket, true, now)
    }

    fn wait_idle(s: &Sessions) {
        while s.lock().worker.as_ref().is_some_and(|w| !w.is_finished()) {
            std::thread::yield_now();
        }
    }

    fn runtime() -> tokio::runtime::Runtime {
        tokio::runtime::Builder::new_current_thread()
            .enable_time()
            .build()
            .unwrap()
    }

    #[test]
    fn real_verification_issues_only_for_exact_credentials() {
        let rt = runtime();
        let s = manager();
        let long = Duration::from_secs(600);
        let ok = rt
            .block_on(s.login("admin", pw("disposable fixture"), long))
            .unwrap();
        assert_eq!(ok.session.len(), 64);
        assert_ne!(*ok.session, *ok.csrf);
        // The slot frees only at actual verifier thread exit, which can trail
        // the reply under load; wait so the next login is not Busy.
        wait_idle(&s);
        let now = Instant::now();
        let auth = s
            .authorize(&ok.session, Some(&ok.csrf), Activity::Deliberate, now)
            .unwrap();
        assert_eq!(*auth.csrf, *ok.csrf);
        assert_eq!(
            s.authorize(&ok.session, Some(&ok.session), Activity::Background, now)
                .err(),
            Some(AuthError::CsrfMismatch)
        );
        for (user, password) in [("admin", "wrong"), ("Admin", "disposable fixture")] {
            assert_eq!(
                rt.block_on(s.login(user, pw(password), long)).err(),
                Some(LoginError::InvalidCredentials)
            );
            wait_idle(&s);
        }
        // Non-canonical encodings of a valid token never authorize.
        let upper = ok.session.to_uppercase();
        assert_eq!(
            s.authorize(&upper, None, Activity::Background, now).err(),
            Some(AuthError::Unauthenticated)
        );
        assert!(s.shutdown().is_some_and(|w| w.join().is_ok()));
        assert_eq!(
            s.authorize(&ok.session, None, Activity::Background, now)
                .err(),
            Some(AuthError::Unauthenticated)
        );
    }

    #[test]
    fn rolling_rate_limit_counts_admitted_attempts_per_instance() {
        let s = manager();
        let t0 = Instant::now();
        for i in 0..LOGIN_ATTEMPTS {
            let ticket = admit(&s, t0 + Duration::from_secs(i as u64)).unwrap();
            assert_eq!(
                s.finish(ticket, false, t0).err(),
                Some(LoginError::InvalidCredentials)
            );
            wait_idle(&s);
        }
        assert_eq!(
            admit(&s, t0 + Duration::from_secs(59)).err(),
            Some(LoginError::RateLimited)
        );
        // Oldest attempt leaves the 60-second window; exactly one slot reopens.
        assert!(admit(&s, t0 + LOGIN_WINDOW).is_ok());
        wait_idle(&s);
        assert_eq!(
            admit(&s, t0 + LOGIN_WINDOW).err(),
            Some(LoginError::RateLimited)
        );
    }

    #[test]
    fn single_slot_is_held_until_actual_worker_exit() {
        let s = manager();
        let (release, gate) = std::sync::mpsc::channel::<()>();
        let now = Instant::now();
        let ticket = s
            .admit(now, move |_| {
                let _ = gate.recv();
            })
            .unwrap();
        assert_eq!(admit(&s, now).err(), Some(LoginError::Busy));
        release.send(()).unwrap();
        wait_idle(&s);
        assert!(s.finish(ticket, true, now).is_ok());
        assert!(admit(&s, now).is_ok());
    }

    #[test]
    fn timed_out_login_never_mints_and_keeps_slot() {
        let rt = runtime();
        let s = manager();
        let result = rt.block_on(s.login("admin", pw("disposable fixture"), Duration::ZERO));
        assert_eq!(result.err(), Some(LoginError::TimedOut));
        assert!(s.lock().sessions.is_empty());
        // Either still verifying (busy) or already exited; never a leaked session.
        match admit(&s, Instant::now()) {
            Err(LoginError::Busy) => {}
            Ok(_) => {}
            other => panic!("unexpected {other:?}"),
        }
        wait_idle(&s);
        assert!(s.lock().sessions.is_empty());
    }

    #[test]
    fn logout_or_activation_during_verification_supersedes_login() {
        let now = Instant::now();
        let s = manager();
        let ticket = admit(&s, now).unwrap();
        assert_eq!(s.logout_all(), Ok(1));
        assert_eq!(
            s.finish(ticket, true, now).err(),
            Some(LoginError::Superseded)
        );
        wait_idle(&s);

        let ticket = admit(&s, now).unwrap();
        assert_eq!(s.activate(record(2)), Ok(2));
        assert_eq!(
            s.finish(ticket, true, now).err(),
            Some(LoginError::Superseded)
        );
        wait_idle(&s);
        assert!(s.finish(admit(&s, now).unwrap(), true, now).is_ok());
    }

    #[test]
    fn revocation_after_authorization_refuses_every_later_request() {
        let now = Instant::now();
        let s = manager();
        let a = mint(&s, now);
        let b = mint(&s, now);
        assert!(
            s.authorize(&a.session, None, Activity::Background, now)
                .is_ok()
        );
        s.logout_all().unwrap();
        for issued in [&a, &b] {
            assert_eq!(
                s.authorize(
                    &issued.session,
                    Some(&issued.csrf),
                    Activity::Deliberate,
                    now
                )
                .err(),
                Some(AuthError::Unauthenticated)
            );
        }
        let c = mint(&s, now);
        s.activate(record(2)).unwrap();
        assert_eq!(
            s.authorize(&c.session, None, Activity::Background, now)
                .err(),
            Some(AuthError::Unauthenticated)
        );
    }

    #[test]
    fn activation_requires_same_principal_and_newer_revision() {
        let s = Sessions::new(record(5), DEFAULT_IDLE);
        assert_eq!(s.activate(record(5)), Err(ActivationError::Rejected));
        assert_eq!(s.activate(record(4)), Err(ActivationError::Rejected));
        let other = Record::create(INSTANCE, "admin".into(), &pw("other")).unwrap();
        let other = Record::decode(
            &String::from_utf8(other.encode().unwrap().to_vec())
                .unwrap()
                .replace("\"revision\":1", "\"revision\":9")
                .into_bytes(),
            INSTANCE,
        )
        .unwrap();
        assert_eq!(s.activate(other), Err(ActivationError::Rejected));
        assert_eq!(s.activate(record(6)), Ok(1));
    }

    #[test]
    fn inactivity_is_monotonic_and_only_deliberate_activity_renews() {
        let idle = Duration::from_secs(1800);
        let t0 = Instant::now();
        let s = Sessions::new(record(1), idle);
        let a = mint(&s, t0);
        let b = mint(&s, t0);
        let near = t0 + idle - Duration::from_secs(1);
        // Background polling just before expiry does not extend either session.
        assert!(
            s.authorize(&a.session, None, Activity::Background, near)
                .is_ok()
        );
        assert!(
            s.authorize(&b.session, None, Activity::Deliberate, near)
                .is_ok()
        );
        let after = t0 + idle;
        assert_eq!(
            s.authorize(&a.session, None, Activity::Background, after)
                .err(),
            Some(AuthError::Unauthenticated)
        );
        assert!(
            s.authorize(&b.session, None, Activity::Background, after)
                .is_ok()
        );
        // An earlier instant never moves activity backwards.
        assert!(
            s.authorize(&b.session, None, Activity::Deliberate, t0)
                .is_ok()
        );
        assert_eq!(
            s.authorize(&b.session, None, Activity::Background, near + idle)
                .err(),
            Some(AuthError::Unauthenticated)
        );
    }

    #[test]
    fn capacity_refuses_without_silent_eviction() {
        let now = Instant::now();
        let s = manager();
        // A login admitted before capacity filled is refused at minting too.
        let early = admit(&s, now).unwrap();
        wait_idle(&s);
        let first = issue(&s, now).unwrap();
        for _ in 1..MAX_SESSIONS {
            issue(&s, now).unwrap();
        }
        assert_eq!(admit(&s, now).err(), Some(LoginError::Busy));
        assert_eq!(s.finish(early, true, now).err(), Some(LoginError::Busy));
        assert_eq!(issue(&s, now).err(), Some(LoginError::Busy));
        assert!(
            s.authorize(&first.session, None, Activity::Background, now)
                .is_ok()
        );
        assert_eq!(s.lock().sessions.len(), MAX_SESSIONS);
    }

    #[test]
    fn entropy_failure_or_repeated_collision_issues_nothing() {
        let now = Instant::now();
        let s = Sessions::with_entropy(record(1), DEFAULT_IDLE, Box::new(|_| false));
        let ticket = admit(&s, now).unwrap();
        assert_eq!(
            s.finish(ticket, true, now).err(),
            Some(LoginError::Unavailable)
        );
        assert!(s.lock().sessions.is_empty());

        // Constant entropy collides token with CSRF on every attempt.
        let s = Sessions::with_entropy(
            record(1),
            DEFAULT_IDLE,
            Box::new(|b| {
                b.fill(7);
                true
            }),
        );
        assert_eq!(issue(&s, now).err(), Some(LoginError::Unavailable));

        // Second login first draws a duplicate of the existing token, retries.
        static NEXT: AtomicU8 = AtomicU8::new(0);
        const DRAWS: [u8; 6] = [0, 1, 0, 2, 3, 4];
        let s = Sessions::with_entropy(
            record(1),
            DEFAULT_IDLE,
            Box::new(|b| {
                b.fill(DRAWS[usize::from(NEXT.fetch_add(1, Ordering::Relaxed))]);
                true
            }),
        );
        let first = issue(&s, now).unwrap();
        let second = issue(&s, now).unwrap();
        assert_eq!(NEXT.load(Ordering::Relaxed), 6);
        assert_ne!(*first.session, *second.session);
        assert_eq!(s.lock().sessions.len(), 2);
    }

    #[test]
    fn exhausted_generation_closes_instead_of_wrapping() {
        let now = Instant::now();
        let s = manager();
        let a = mint(&s, now);
        s.lock().generation = u64::MAX;
        assert_eq!(s.logout_all(), Err(ActivationError::Closed));
        assert_eq!(admit(&s, now).err(), Some(LoginError::Unavailable));
        assert_eq!(
            s.authorize(&a.session, None, Activity::Background, now)
                .err(),
            Some(AuthError::Unauthenticated)
        );
    }

    #[test]
    fn minting_after_deadline_never_issues() {
        let now = Instant::now();
        // Verification finished in time, but slow entropy crosses the deadline.
        let s = Sessions::with_entropy(
            record(1),
            DEFAULT_IDLE,
            Box::new(|b| {
                std::thread::sleep(Duration::from_millis(50));
                b.fill(9);
                true
            }),
        );
        let ticket = admit(&s, now).unwrap();
        wait_idle(&s);
        let expires = Some(Instant::now() + Duration::from_millis(10));
        assert_eq!(
            s.finish_by(ticket, true, now, expires).err(),
            Some(LoginError::TimedOut)
        );
        assert!(s.lock().sessions.is_empty());
    }

    #[test]
    fn authentication_failure_precedes_malformed_csrf() {
        let idle = Duration::from_secs(60);
        let t0 = Instant::now();
        let s = Sessions::new(record(1), idle);
        let revoked = issue(&s, t0).unwrap();
        s.logout_all().unwrap();
        let expired = issue(&s, t0).unwrap();
        let live = issue(&s, t0).unwrap();
        let unknown = "0".repeat(64);
        let later = t0 + Duration::from_secs(30);
        for token in [&*revoked.session, unknown.as_str()] {
            assert_eq!(
                s.authorize(token, Some("bad"), Activity::Background, later)
                    .err(),
                Some(AuthError::Unauthenticated)
            );
        }
        assert_eq!(
            s.authorize(&live.session, Some("bad"), Activity::Background, later)
                .err(),
            Some(AuthError::CsrfMismatch)
        );
        assert_eq!(
            s.authorize(
                &expired.session,
                Some("bad"),
                Activity::Background,
                t0 + idle
            )
            .err(),
            Some(AuthError::Unauthenticated)
        );
    }

    #[test]
    fn dropping_manager_waits_for_running_verifier() {
        let s = manager();
        let (release, gate) = std::sync::mpsc::channel::<()>();
        let (exited, done) = std::sync::mpsc::channel::<()>();
        s.admit(Instant::now(), move |_| {
            let _ = gate.recv();
            let _ = exited.send(());
        })
        .unwrap();
        let dropper = std::thread::spawn(move || drop(s));
        std::thread::sleep(Duration::from_millis(100));
        assert!(!dropper.is_finished(), "drop detached a running verifier");
        release.send(()).unwrap();
        dropper.join().unwrap();
        // The verifier finished before drop returned.
        assert!(done.try_recv().is_ok());
    }

    #[test]
    fn canonical_hex_roundtrip() {
        let bytes = [0xa5_u8; TOKEN_BYTES];
        let text = hex(&bytes);
        assert_eq!(*unhex(&text).unwrap(), bytes);
        for bad in [
            "",
            &text[1..],
            &format!("{}0", *text),
            &text.replace('a', "A"),
        ] {
            assert!(unhex(bad).is_none());
        }
        assert!(unhex(&"g".repeat(64)).is_none());
    }
}
