//! Bounded, demand-triggered source observation, independent of claim workers.
use mover_core::{SpaceDecision, SpaceStatistics};
use mover_store::NewJobAdmission;
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::{fd::AsFd, unix::net::UnixStream},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    time::{Duration, Instant},
};
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Policy {
    pub enabled: bool,
    pub min_available_bytes: u64,
    pub min_available_percent: u8,
    pub max_sample_age_seconds: u64,
    pub probe_timeout_seconds: u64,
}
impl Default for Policy {
    fn default() -> Self {
        Self {
            enabled: false,
            min_available_bytes: 0,
            min_available_percent: 0,
            max_sample_age_seconds: 5,
            probe_timeout_seconds: 2,
        }
    }
}
impl Policy {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.min_available_percent > 100
            || !(1..=60).contains(&self.max_sample_age_seconds)
            || !(1..=self.max_sample_age_seconds).contains(&self.probe_timeout_seconds)
            || (self.enabled && self.min_available_bytes == 0 && self.min_available_percent == 0)
        {
            return Err("invalid source-space admission policy");
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Failure {
    Unavailable,
    CustodyRefused,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    sequence: u64,
    root_path: String,
    authorization: mover_fs::SourceAuthorization,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    version: u32,
    sequence: u64,
    root_path: String,
    statistics: Option<[u64; 3]>,
    error: Option<Failure>,
    diagnostic: Option<String>,
}
#[derive(Default)]
struct Cache {
    started: Option<Instant>,
    result: Option<Result<SpaceDecision, Failure>>,
    busy: bool,
    sequence: u64,
}
#[derive(Clone)]
pub(crate) struct Handle {
    policy: Policy,
    cache: Arc<Mutex<Cache>>,
    demand: Option<mpsc::SyncSender<()>>,
    changed: Arc<tokio::sync::Notify>,
    waiters: Arc<tokio::sync::Semaphore>,
}
impl Handle {
    /// Never waits for filesystem I/O. First request triggers a probe and retries.
    pub(crate) fn admission(&self) -> NewJobAdmission {
        if !self.policy.enabled {
            return NewJobAdmission::Unrestricted;
        }
        let mut c = self.cache.lock().expect("source-space cache");
        let age = Duration::from_secs(self.policy.max_sample_age_seconds);
        let fresh = c.started.is_some_and(|start| start.elapsed() <= age);
        if !fresh && !c.busy {
            c.started = Some(Instant::now());
            c.result = None;
            c.busy = true;
            if self.demand.as_ref().is_none_or(|d| d.try_send(()).is_err()) {
                c.busy = false;
                c.result = Some(Err(Failure::Unavailable));
            }
        }
        self.decision(&c)
    }
    /// Bounded HTTP wait only: claim/database owners never await this probe.
    pub(crate) async fn wait_for_probe(&self) -> bool {
        let Ok(_permit) = self.waiters.try_acquire() else {
            return false;
        };
        let changed = self.changed.notified();
        tokio::pin!(changed);
        changed.as_mut().enable();
        {
            let c = self.cache.lock().expect("source-space cache");
            if !c.busy {
                return c.result.is_some();
            }
        }
        tokio::time::timeout(
            Duration::from_secs(self.policy.probe_timeout_seconds),
            changed,
        )
        .await
        .is_ok()
    }
    fn decision(&self, c: &Cache) -> NewJobAdmission {
        let Some(started) = c.started else {
            return NewJobAdmission::Unavailable;
        };
        let expires_at = started + Duration::from_secs(self.policy.max_sample_age_seconds);
        if Instant::now() > expires_at || c.busy {
            return NewJobAdmission::Unavailable;
        }
        match c.result {
            Some(Ok(d)) => NewJobAdmission::SourceSpace {
                expires_at,
                sufficient: d.sufficient,
            },
            Some(Err(Failure::CustodyRefused)) => NewJobAdmission::CustodyRefused,
            _ => NewJobAdmission::Unavailable,
        }
    }
    pub(crate) fn snapshot(&self) -> serde_json::Value {
        let c = self.cache.lock().expect("source-space cache");
        let age = c.started.map(|t| t.elapsed());
        let fresh =
            age.is_some_and(|d| d <= Duration::from_secs(self.policy.max_sample_age_seconds));
        let d = if self.policy.enabled && fresh && !c.busy {
            c.result.and_then(Result::ok)
        } else {
            None
        };
        let state = if !self.policy.enabled {
            "Disabled"
        } else if let Some(d) = d {
            if d.sufficient { "Sufficient" } else { "Low" }
        } else {
            "Unknown"
        };
        let reason = if state != "Unknown" {
            None
        } else if !fresh && c.started.is_some() {
            Some("sample_expired")
        } else if c.busy
            && age.is_some_and(|d| d >= Duration::from_secs(self.policy.probe_timeout_seconds))
        {
            Some("probe_timeout")
        } else if c.busy {
            Some("probe_pending")
        } else if matches!(c.result, Some(Err(Failure::CustodyRefused))) {
            Some("custody_refused")
        } else if c.result.is_some() {
            Some("probe_unavailable")
        } else {
            Some("not_sampled")
        };
        serde_json::json!({"policy":self.policy,"scope":"SourceRoot","observation_source":"supervised_child",
            "state":state,"observed_available_bytes":d.map(|d|d.available_bytes.to_string()),"required_available_bytes":d.map(|d|d.required_bytes.to_string()),
            "sample_age_ms":if self.policy.enabled {age.map(|d|d.as_millis().min(u128::from(u64::MAX)) as u64)}else{None},"reason":reason})
    }
}
pub(crate) struct Monitor {
    pub(crate) handle: Handle,
    thread: Option<std::thread::JoinHandle<()>>,
    stop: Arc<AtomicBool>,
}
impl Monitor {
    pub(crate) fn start(
        policy: Policy,
        guard: Arc<mover_fs::LocalClaimLock>,
        stop: Arc<AtomicBool>,
    ) -> std::io::Result<Self> {
        let (sender, receiver) = mpsc::sync_channel(1);
        let handle = Handle {
            demand: policy.enabled.then_some(sender),
            policy,
            cache: Arc::new(Mutex::new(Cache::default())),
            changed: Arc::new(tokio::sync::Notify::new()),
            waiters: Arc::new(tokio::sync::Semaphore::new(2)),
        };
        let thread = if handle.policy.enabled {
            let h = handle.clone();
            let stop = stop.clone();
            Some(
                std::thread::Builder::new()
                    .name("mover-source-space".into())
                    .spawn(move || {
                        while !stop.load(Ordering::Relaxed) {
                            match receiver.recv_timeout(Duration::from_millis(100)) {
                                Ok(()) => (),
                                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                                Err(_) => break,
                            }
                            if stop.load(Ordering::Relaxed) {
                                break;
                            }
                            let (started, sequence) = {
                                let mut c = h.cache.lock().expect("source-space cache");
                                let Some(next) = c.sequence.checked_add(1) else {
                                    stop.store(true, Ordering::Relaxed);
                                    break;
                                };
                                c.sequence = next;
                                (c.started.expect("probe dispatch timestamp"), next)
                            };
                            let result = probe(
                                &guard,
                                &stop,
                                sequence,
                                started + Duration::from_secs(h.policy.probe_timeout_seconds),
                            )
                            .and_then(|s| {
                                s.decide(
                                    h.policy.min_available_bytes,
                                    h.policy.min_available_percent,
                                )
                                .ok_or(Failure::Unavailable)
                            });
                            let mut c = h.cache.lock().expect("source-space cache");
                            // exchange only returns after confirmed exit, even on errors.
                            c.busy = false;
                            c.result = Some(
                                if started.elapsed()
                                    > Duration::from_secs(h.policy.probe_timeout_seconds)
                                {
                                    Err(Failure::Unavailable)
                                } else {
                                    result
                                },
                            );
                            h.changed.notify_waiters();
                        }
                    })?,
            )
        } else {
            None
        };
        eprintln!(
            "Source-space admission policy: {}",
            serde_json::to_string(&handle.policy).expect("policy serialization")
        );
        Ok(Self {
            handle,
            thread,
            stop,
        })
    }
}
impl Drop for Monitor {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}
fn decode(request: &Request, bytes: &[u8]) -> Result<SpaceStatistics, Failure> {
    let reply: Reply = serde_json::from_slice(bytes).map_err(|_| Failure::Unavailable)?;
    if reply.version != 1
        || reply.sequence != request.sequence
        || reply.root_path != request.root_path
    {
        return Err(Failure::Unavailable);
    }
    if let Some(detail) = &reply.diagnostic {
        if reply.error.is_none() || reply.statistics.is_some() || !super::diagnostic::valid(detail)
        {
            return Err(Failure::Unavailable);
        }
        eprintln!("Source-space worker: {detail}");
    }
    match (reply.statistics, reply.error) {
        (Some([available_blocks, total_blocks, fragment_size]), None)
            if reply.diagnostic.is_none() =>
        {
            Ok(SpaceStatistics {
                available_blocks,
                total_blocks,
                fragment_size,
            })
        }
        (None, Some(f)) => Err(f),
        _ => Err(Failure::Unavailable),
    }
}
fn probe(
    guard: &mover_fs::LocalClaimLock,
    stop: &AtomicBool,
    sequence: u64,
    deadline: Instant,
) -> Result<SpaceStatistics, Failure> {
    let authorization = guard
        .source_authorization()
        .cloned()
        .ok_or(Failure::CustodyRefused)?;
    if authorization.enrollment.is_none() {
        return Err(Failure::CustodyRefused);
    }
    let root_path = guard.source_path().to_owned();
    let request = Request {
        version: 1,
        sequence,
        root_path,
        authorization,
    };
    let bytes = serde_json::to_vec(&request).map_err(|_| Failure::Unavailable)?;
    if bytes.len() > 16384 {
        return Err(Failure::Unavailable);
    }
    let reply = super::payload::exchange_deadline(
        &bytes,
        "--internal-source-space-worker",
        guard,
        guard,
        stop,
        4096,
        Some(deadline),
    )
    .map_err(|_| Failure::Unavailable)?;
    decode(&request, &reply)
}
/// Internal child: bounded private request/reply, inherited custody, no database.
pub fn worker() -> Result<(), Box<dyn std::error::Error>> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let _instance = mover_fs::InstanceGuard::receive(&mut channel)?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel).take(16385).read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err("source-space request too large".into());
    }
    let r: Request = serde_json::from_slice(&bytes)?;
    if r.version != 1 || r.sequence == 0 || r.authorization.enrollment.is_none() {
        return Err("invalid source-space assignment".into());
    }
    let result: Result<SpaceStatistics, mover_fs::ClaimError> = (|| {
        r.authorization.validate(&r.root_path)?;
        mover_fs::validate_payload_locks(&r.root_path, &r.root_path)?;
        mover_fs::qualification_pause("source_space_statistics")?;
        #[cfg(feature = "nfs-qualification")]
        if std::env::var("FILE_MOVER_QUALIFICATION_SOURCE_SPACE_FAULT")
            .ok()
            .as_deref()
            == Some("unavailable")
        {
            return Err(mover_fs::source_space_unavailable_fault());
        }
        let s = mover_fs::source_space_statistics(&r.root_path, &r.authorization)?;
        mover_fs::validate_payload_locks(&r.root_path, &r.root_path)?;
        Ok(s)
    })();
    let mut reply = Reply {
        version: 1,
        sequence: r.sequence,
        root_path: r.root_path,
        statistics: None,
        error: None,
        diagnostic: None,
    };
    match result {
        Ok(s) => reply.statistics = Some([s.available_blocks, s.total_blocks, s.fragment_size]),
        Err(e) => {
            reply.error = Some(if matches!(e, mover_fs::ClaimError::Blocked(_)) {
                Failure::CustodyRefused
            } else {
                Failure::Unavailable
            });
            reply.diagnostic = Some(super::diagnostic::describe(&e));
        }
    }
    let bytes = serde_json::to_vec(&reply)?;
    if bytes.len() > 4096 {
        return Err("source-space reply too large".into());
    }
    channel.write_all(&bytes)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn policy_is_default_off_and_strict_even_when_disabled() {
        for text in ["{}", r#"{"enabled":false}"#] {
            let p: Policy = serde_json::from_str(text).unwrap();
            assert!(!p.enabled);
            p.validate().unwrap();
        }
        for text in [
            "null",
            r#"{"enabled":true,"min_available_bytes":-1}"#,
            r#"{"enabled":true,"min_available_bytes":1.5}"#,
            r#"{"enabled":false,"enabled":true}"#,
            r#"{"unknown":1}"#,
            r#"{"min_available_percent":256}"#,
        ] {
            assert!(serde_json::from_str::<Policy>(text).is_err(), "{text}");
        }
        for text in [
            r#"{"enabled":true}"#,
            r#"{"min_available_percent":101}"#,
            r#"{"probe_timeout_seconds":0}"#,
            r#"{"max_sample_age_seconds":61}"#,
            r#"{"probe_timeout_seconds":6}"#,
        ] {
            assert!(
                serde_json::from_str::<Policy>(text)
                    .unwrap()
                    .validate()
                    .is_err(),
                "{text}"
            );
        }
        for text in [
            r#"{"enabled":true,"min_available_percent":5}"#,
            r#"{"enabled":true,"min_available_bytes":18446744073709551615}"#,
        ] {
            serde_json::from_str::<Policy>(text)
                .unwrap()
                .validate()
                .unwrap();
        }
    }
    #[test]
    fn cache_is_monotonic_bounded_and_disabled_never_dispatches() {
        let (tx, rx) = mpsc::sync_channel(1);
        let cache = Arc::new(Mutex::new(Cache::default()));
        let mut h = Handle {
            policy: Policy::default(),
            cache: cache.clone(),
            demand: Some(tx),
            changed: Arc::new(tokio::sync::Notify::new()),
            waiters: Arc::new(tokio::sync::Semaphore::new(2)),
        };
        assert!(matches!(h.admission(), NewJobAdmission::Unrestricted));
        assert!(rx.try_recv().is_err());
        assert_eq!(h.snapshot()["state"], "Disabled");
        h.policy = Policy {
            enabled: true,
            min_available_bytes: 1,
            ..Policy::default()
        };
        assert!(matches!(h.admission(), NewJobAdmission::Unavailable));
        rx.try_recv().unwrap();
        for _ in 0..100 {
            assert!(matches!(h.admission(), NewJobAdmission::Unavailable));
        }
        assert!(rx.try_recv().is_err());
        {
            let mut c = cache.lock().unwrap();
            c.started = Some(Instant::now() - Duration::from_secs(3));
        }
        assert_eq!(h.snapshot()["reason"], "probe_timeout");
        assert!(rx.try_recv().is_err());
        {
            let mut c = cache.lock().unwrap();
            c.busy = false;
            c.started = Some(Instant::now());
            c.result = Some(Ok(SpaceDecision {
                available_bytes: 100,
                required_bytes: 1,
                sufficient: true,
            }));
        }
        assert!(matches!(
            h.admission(),
            NewJobAdmission::SourceSpace {
                sufficient: true,
                ..
            }
        ));
        assert_eq!(h.snapshot()["state"], "Sufficient");
        {
            let mut c = cache.lock().unwrap();
            c.started = Some(Instant::now() - Duration::from_secs(6));
        }
        assert_eq!(h.snapshot()["reason"], "sample_expired");
        assert!(rx.try_recv().is_err());
        assert!(matches!(h.admission(), NewJobAdmission::Unavailable));
        rx.try_recv().unwrap();
    }
    #[test]
    fn private_space_receipt_rejects_mixed_wrong_scope_and_unknown_fields() {
        let auth: mover_fs::SourceAuthorization=serde_json::from_value(serde_json::json!({"binding":{"version":3,"coordinator_id":"m","root_id":"s","endpoint_id":"e","marker_id":"p","filesystem":"local","role":"source"},"observation":"test"})).unwrap();
        let request = Request {
            version: 1,
            sequence: 5,
            root_path: "/source".into(),
            authorization: auth,
        };
        let base = serde_json::json!({"version":1,"sequence":5,"root_path":"/source","statistics":[1,100,4096],"error":null,"diagnostic":null});
        assert!(decode(&request, &serde_json::to_vec(&base).unwrap()).is_ok());
        for (field, value) in [
            ("version", serde_json::json!(2)),
            ("sequence", serde_json::json!(4)),
            ("root_path", serde_json::json!("/other")),
            ("extra", serde_json::json!(true)),
            ("error", serde_json::json!("custody_refused")),
            ("diagnostic", serde_json::json!("fake")),
            ("error", serde_json::json!("unknown")),
        ] {
            let mut reply = base.clone();
            reply[field] = value;
            assert!(
                decode(&request, &serde_json::to_vec(&reply).unwrap()).is_err(),
                "{reply}"
            );
        }
    }
    #[test]
    fn async_probe_wait_reserves_slots_and_observes_completion_without_lost_wakeup() {
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
            .block_on(async {
                let cache = Arc::new(Mutex::new(Cache {
                    busy: true,
                    started: Some(Instant::now()),
                    ..Cache::default()
                }));
                let h = Handle {
                    policy: Policy {
                        enabled: true,
                        min_available_bytes: 1,
                        ..Policy::default()
                    },
                    cache: cache.clone(),
                    demand: None,
                    changed: Arc::new(tokio::sync::Notify::new()),
                    waiters: Arc::new(tokio::sync::Semaphore::new(2)),
                };
                let full = h.waiters.acquire_many(2).await.unwrap();
                assert!(!h.wait_for_probe().await);
                drop(full);
                let changed = h.changed.clone();
                let complete = tokio::spawn(async move {
                    tokio::task::yield_now().await;
                    {
                        let mut c = cache.lock().unwrap();
                        c.busy = false;
                        c.result = Some(Err(Failure::Unavailable));
                    }
                    changed.notify_waiters();
                });
                assert!(h.wait_for_probe().await);
                complete.await.unwrap();
                assert!(h.wait_for_probe().await); // completed before registration
            });
    }
}
