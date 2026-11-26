//! Bounded loopback handoff and durable local recording delivery. No deletion.
pub mod account;
pub mod account_cli;
mod account_ipc;
pub mod admin;
pub mod bootstrap;
mod cert_info;
pub mod claim_worker;
mod confirmation;
pub mod control;
pub mod delivery_worker;
mod diagnostic;
pub mod enrollment;
mod http;
pub mod ingress;
mod missing_retry;
pub mod native;
pub mod password;
pub mod payload;
mod progress;
mod reload;
mod retry_context;
pub mod session;
pub mod source_space;
pub mod tls;
mod tls_executor;
pub mod tls_reload_ipc;
use mover_core::{DeliveryPolicy, Handoff, ProtocolError, Submission};
use mover_store::{AcceptanceContext, Store, StoreError};
use serde::{Deserialize, Serialize};
use std::{
    net::SocketAddr,
    path::Path,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    net::TcpListener,
    sync::{Semaphore, oneshot},
    task::JoinSet,
    time::timeout,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub bind: SocketAddr,
    #[serde(default)]
    pub protected_ingress: Option<ingress::ProtectedIngress>,
    #[serde(default)]
    pub native_ingress: Option<native::NativeIngress>,
    #[serde(default)]
    pub admin_ingress: Option<admin::AdminIngress>,
    pub generator_id: String,
    #[serde(default)]
    pub check_expected_sizes: bool,
    /// Move mode (docs/MOVE-MODE-DESIGN.md): remove the mover's held source
    /// copies after verified delivery. Recorded per job at acceptance; cleanup
    /// also needs this loaded setting. Default off.
    #[serde(default)]
    pub delete_source_after_commit: bool,
    pub source_root: String,
    pub source_binding: mover_fs::SourceBinding,
    pub destination_root: String,
    pub destination_binding: mover_fs::DestinationBinding,
    pub state_database: String,
    #[serde(default = "retry_default")]
    pub missing_file_retry_window_seconds: u32,
    /// A late missing file is claimed by the timer only after two identical
    /// observations at least this far apart (1-300 s; MISSING-FILE-RETRY-DESIGN).
    #[serde(default = "settle_default")]
    pub missing_file_settle_seconds: u32,
    #[serde(default = "retained_jobs_default")]
    pub max_retained_jobs: u64,
    #[serde(default = "retained_bytes_default")]
    pub max_retained_bytes: u64,
    #[serde(default)]
    pub source_space_admission: source_space::Policy,
    #[serde(default = "shutdown_default")]
    pub shutdown_wait_seconds: u32,
    /// Jobs delivered at the same time (1-8), each by its own worker thread and
    /// worker child. Fixed in configuration, never derived from CPU count.
    #[serde(default = "delivery_concurrency_default")]
    pub delivery_concurrency: u32,
    /// Files of one job copied at the same time (1-8), each by its own worker
    /// child on shared destination custody. Never derived from CPU count.
    #[serde(default = "delivery_concurrency_default")]
    pub delivery_file_concurrency: u32,
    /// Copy and verification buffer bytes: 64 KiB to 64 MiB in 4 KiB pages
    /// (L2-COPY-002). Default 1 MiB.
    #[serde(default = "copy_buffer_default")]
    pub copy_buffer_bytes: u64,
}
fn settle_default() -> u32 {
    5
}
fn copy_buffer_default() -> u64 {
    mover_fs::DEFAULT_COPY_BUFFER as u64
}
fn shutdown_default() -> u32 {
    60
}
fn delivery_concurrency_default() -> u32 {
    1
}
fn retained_jobs_default() -> u64 {
    64
}
fn retained_bytes_default() -> u64 {
    1024 * 1024 * 1024 * 1024
}
fn retry_default() -> u32 {
    300
}
fn absolute(path: &str) -> bool {
    path.starts_with('/')
        && path != "/"
        && path[1..].split('/').all(|p| {
            !p.is_empty()
                && p != "."
                && p != ".."
                && !p.chars().any(char::is_control)
                && !p.contains('\\')
        })
}
impl Config {
    pub fn validate(&self) -> Result<(), &'static str> {
        self.source_space_admission.validate()?;
        if !(1..=3600).contains(&self.shutdown_wait_seconds) {
            return Err("shutdown_wait_seconds must be an integer from 1 through 3600");
        }
        if !(1..=8).contains(&self.delivery_concurrency) {
            return Err("delivery_concurrency must be an integer from 1 through 8");
        }
        if !(1..=8).contains(&self.delivery_file_concurrency) {
            return Err("delivery_file_concurrency must be an integer from 1 through 8");
        }
        if !mover_fs::valid_copy_buffer(self.copy_buffer_bytes) {
            return Err("copy_buffer_bytes must be 64 KiB to 64 MiB in whole 4 KiB pages");
        }
        if !(1..=300).contains(&self.missing_file_settle_seconds) {
            return Err("missing_file_settle_seconds must be an integer from 1 through 300");
        }
        self.destination_binding
            .validate()
            .map_err(|_| "invalid destination binding")?;
        if self.destination_binding.coordinator_id != self.source_binding.coordinator_id {
            return Err("coordinator binding mismatch");
        }
        self.source_binding
            .validate()
            .map_err(|_| "invalid source binding")?;
        if (!self.bind.ip().is_loopback()
            && !self
                .native_ingress
                .as_ref()
                .is_some_and(native::NativeIngress::https))
            || self.max_retained_jobs == 0
            || self.max_retained_bytes == 0
            || self.generator_id.trim().is_empty()
            || self.generator_id.len() > 128
            || ![
                &self.source_root,
                &self.destination_root,
                &self.state_database,
            ]
            .iter()
            .all(|p| absolute(p))
        {
            return Err(
                "loopback binding, bounded generator and canonical absolute paths required",
            );
        }
        let s = Path::new(&self.source_root);
        let d = Path::new(&self.destination_root);
        let db = Path::new(&self.state_database);
        if s.starts_with(d) || d.starts_with(s) || db.starts_with(s) || db.starts_with(d) {
            return Err("source/destination roots and local state must be separate");
        }
        if let Some(ingress) = &self.protected_ingress {
            ingress.validate(self)?;
        }
        if let Some(ingress) = &self.native_ingress {
            ingress.validate(self)?;
        }
        if let Some(ingress) = &self.admin_ingress {
            ingress.validate(self)?;
        }
        Ok(())
    }
}
#[derive(Debug, Serialize)]
pub struct Response {
    #[serde(skip)]
    pub status: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub job_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub state: Option<&'static str>,
    pub source_paths_released: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<&'static str>,
    pub retryable: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}
fn error(status: u16, code: &'static str, retryable: bool, job: Option<i64>) -> Response {
    Response {
        status,
        job_id: job.map(|j| j.to_string()),
        state: None,
        source_paths_released: false,
        error: Some(code),
        retryable,
        details: None,
    }
}
pub(crate) fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .min(i64::MAX as u64) as i64
}
fn decode(body: &[u8], c: &Config) -> Result<(Submission, AcceptanceContext), Response> {
    use mover_fs::recording_codec::{CodecError, decode_producer};
    let input = decode_producer(body).map_err(|e| {
        error(
            if e == CodecError::TooLarge { 413 } else { 400 },
            match e {
                CodecError::InvalidJson => "invalid_json",
                CodecError::InvalidFilePaths => "invalid_file_paths",
                CodecError::TooLarge => "request_too_large",
                _ => "invalid_submission",
            },
            false,
            None,
        )
    })?;
    if input.generator_id() != c.generator_id {
        return Err(error(403, "unknown_generator", false, None));
    }
    let relative = Path::new(input.source_directory())
        .strip_prefix(&c.source_root)
        .map_err(|_| error(403, "source_outside_scope", false, None))?
        .to_str()
        .ok_or_else(|| error(400, "invalid_submission", false, None))?
        .to_owned();
    // Scope authorization precedes UUID lookup; service-private components
    // must not become retryable storage failures or reveal existing IDs.
    if !relative.is_empty() && mover_core::FileSpec::new(&relative, None).is_err() {
        return Err(error(403, "source_outside_scope", false, None));
    }
    let submission = Submission::from_producer(input);
    Ok((
        submission,
        AcceptanceContext {
            source_root_id: c.source_binding.root_id.clone(),
            source_root_path: c.source_root.clone(),
            source_relative_directory: relative,
            destination_path: c.destination_root.clone(),
            destination_binding: Some(c.destination_binding.encode()),
            missing_retry_seconds: c.missing_file_retry_window_seconds,
            policy: DeliveryPolicy {
                destination_id: c.destination_binding.root_id.clone(),
                group_by_generator: false,
                delete_source_after_commit: c.delete_source_after_commit,
            },
        },
    ))
}
type Work = (
    Submission,
    AcceptanceContext,
    oneshot::Sender<Response>,
    Option<reload::Lease>,
);
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ResumeInput {
    command_id: String,
    expected_review_epoch: u32,
    reason: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MissingResetInput {
    command_id: String,
    expected_missing_review_epoch: u32,
    file_id: String,
    retry_window_seconds: u32,
    reason: String,
}
enum Observation {
    Status(i64),
    /// Admin history page (bounded; see PageRequest).
    Page(PageRequest),
    /// One bounded chunk of an admin file-name search (see SearchRequest).
    Search(SearchRequest),
    Retention(Option<i64>),
    Resume(i64, ResumeInput),
    ResetMissing(i64, MissingResetInput),
    /// Admin retry whole-request scope: instance ID and job-ID high-water mark.
    RetryScope,
    /// One admin retry occurrence. The gate runs the store decision only while
    /// the admin session is still valid, serialized with revocation.
    Retry(mover_store::RetryOccurrence, RetryGate),
    /// One admin cancel occurrence (job ID, account principal), gated likewise.
    Cancel(i64, String, RetryGate),
    /// One admin history-clear occurrence, gated likewise.
    Clear(i64, RetryGate),
    /// Deletion preview for one job and action (targets + fingerprint).
    DeletePreview(i64, mover_store::DeletionScope),
    /// Start, observe or replay one job's deletion pass, gated likewise.
    DeleteStart {
        job_id: i64,
        scope: mover_store::DeletionScope,
        principal: String,
        proof_digest: String,
        confirmed: String,
        gate: RetryGate,
    },
}
/// Runs the given work while the requesting admin session is valid; false if not.
pub(crate) type RetryGate = Box<dyn FnOnce(&mut dyn FnMut()) -> bool + Send>;
type OperatorWork = (Observation, oneshot::Sender<Response>);
struct Worker {
    sender: Option<mpsc::SyncSender<Work>>,
    thread: Option<std::thread::JoinHandle<()>>,
    deliveries: Vec<std::thread::JoinHandle<()>>,
    stop: Arc<AtomicBool>,
    observer: Option<mpsc::SyncSender<OperatorWork>>,
    observation: Option<std::thread::JoinHandle<()>>,
    _source_space: source_space::Monitor,
    _instance: Arc<mover_fs::InstanceGuard>,
    control: control::Server,
}
impl Worker {
    fn start(
        c: &Config,
        guard: mover_fs::LocalClaimLock,
        stop: Arc<AtomicBool>,
        control: control::Server,
        changes: Option<tokio::sync::watch::Sender<u64>>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        c.validate()?;
        let mut guard = guard;
        let instance = guard.instance()?.clone();
        instance.validate()?;
        instance.prepare_database(&c.state_database)?;
        let store = Arc::new(Store::open(&c.state_database)?);
        if let Some(changes) = changes {
            // Live dashboard signal: "state may have changed", never data.
            store.set_change_listener(move || changes.send_modify(|v| *v = v.wrapping_add(1)));
        }
        enrollment::authorize(c, &store, &mut guard, false, &stop)?;
        let guard = Arc::new(guard);
        store.require_destination_bindings()?;
        store.configure_limits(c.max_retained_jobs, c.max_retained_bytes)?;
        let source_space = source_space::Monitor::start(
            c.source_space_admission.clone(),
            guard.clone(),
            stop.clone(),
        )?;
        let admission = source_space.handle.clone();
        let observation_admission = admission.clone();
        // Worker activity, shared by cancellation settlement and online clear.
        // Set while the claim thread processes a submission; cancellation
        // settlement reads it inside its store transaction (see Store docs).
        let claim_active = Arc::new(AtomicBool::new(false));
        let settle_claim_active = claim_active.clone();
        // Jobs delivery workers are working on, for online clear and settlement.
        let delivering = ActiveJobs::default();
        let settle_delivering = delivering.clone();
        let (clear_claim_active, clear_delivery_job) = (claim_active.clone(), delivering.clone());
        let (observer, observations) = mpsc::sync_channel::<OperatorWork>(8);
        let observation_store = store.clone();
        let observation_instance = instance.clone();
        let observation_stop = stop.clone();
        let observation = std::thread::Builder::new()
            .name("mover-status".into())
            .spawn(move || {
                while let Ok((work, reply)) = observations.recv() {
                    if observation_stop.load(Ordering::Relaxed) {
                        let _ = reply.send(error(503, "service_stopping", true, None)); continue;
                    }
                    if observation_instance.validate().is_err() {
                        let _ = reply.send(error(409, "recording_blocked", false, None));
                        continue;
                    }
                    let response = match work {
                        Observation::Status(id) => status_response(&observation_store, id),
                        Observation::Page(request) => {
                            page_response(&observation_store, request)
                        }
                        Observation::Search(request) => {
                            search_response(&observation_store, request)
                        }
                        Observation::Retention(id) => {
                            let mut response=retention_response(&observation_store,id);
                            if id.is_none() && response.status==200 {
                                response.details.as_mut().expect("retention details")["source_space_admission"]=observation_admission.snapshot();
                            }
                            response
                        },
                        Observation::Resume(id, input) => {
                            resume_response(&observation_store, id, input)
                        }
                        Observation::ResetMissing(id, input) => {
                            missing_reset_response(&observation_store, id, input)
                        }
                        Observation::RetryScope => retry_scope_response(&observation_store),
                        Observation::DeletePreview(id, scope) => delete_preview_response(&observation_store, id, scope),
                        Observation::DeleteStart { job_id, scope, principal, proof_digest, confirmed, gate } => {
                            let mut decided = None;
                            if gate(&mut || {
                                decided = Some(delete_start_response(
                                    &observation_store,
                                    job_id,
                                    scope,
                                    &principal,
                                    &proof_digest,
                                    &confirmed,
                                ))
                            }) {
                                decided.unwrap_or_else(|| error(503, "storage_unavailable", true, None))
                            } else {
                                error(401, "authentication_required", false, None)
                            }
                        }
                        Observation::Clear(id, gate) => {
                            let (claim, delivery) = (clear_claim_active.clone(), clear_delivery_job.clone());
                            let busy = move |job: i64| {
                                claim.load(Ordering::SeqCst) || delivery.contains(job)
                            };
                            let mut decided = None;
                            if gate(&mut || decided = Some(clear_response(&observation_store, id, busy.clone()))) {
                                decided.unwrap_or_else(|| error(503, "storage_unavailable", true, None))
                            } else {
                                error(401, "authentication_required", false, None)
                            }
                        }
                        Observation::Cancel(id, principal, gate) => {
                            let mut decided = None;
                            if gate(&mut || decided = Some(cancel_response(&observation_store, id, &principal))) {
                                decided.unwrap_or_else(|| error(503, "storage_unavailable", true, None))
                            } else {
                                error(401, "authentication_required", false, None)
                            }
                        }
                        Observation::Retry(o, gate) => {
                            let mut decided = None;
                            if gate(&mut || decided = Some(retry_response(&observation_store, &o))) {
                                decided.unwrap_or_else(|| error(503, "storage_unavailable", true, None))
                            } else {
                                error(401, "authentication_required", false, None)
                            }
                        }
                    };
                    let _ = reply.send(response);
                }
            })?;
        // Delivery workers: `delivery_concurrency` threads, each delivering one
        // job at a time through its own worker child. A job is taken through
        // `ActiveJobs`, so no two workers ever deliver the same job. Worker 0
        // alone settles cancellations and runs deletion targets (one consumer
        // per target). Bookkeeping is per job, never per copied chunk.
        let mut deliveries = Vec::new();
        let custody = Arc::new(SharedCustody::default());
        // Shared destination custody whenever more than one delivery child can
        // run at once: several jobs, or several files of one job.
        let parallel = c.delivery_concurrency > 1 || c.delivery_file_concurrency > 1;
        let move_mode = c.delete_source_after_commit;
        MOVE_MODE.store(move_mode, Ordering::Relaxed);
        let tuning = delivery_worker::Tuning {
            files: c.delivery_file_concurrency as usize,
            copy_buffer: c.copy_buffer_bytes as usize,
        };
        for worker in 0..c.delivery_concurrency {
            let custody = custody.clone();
            let delivery_stop = stop.clone();
            let delivery_store = store.clone();
            let delivery_guard = guard.clone();
            let delivering = delivering.clone();
            let (settle_claim_active, settle_delivering) =
                (settle_claim_active.clone(), settle_delivering.clone());
            let spawned = std::thread::Builder::new()
            .name(if worker == 0 { "mover-local-delivery".into() } else { format!("mover-local-delivery-{worker}") })
            .spawn(move || {
                while !delivery_stop.load(Ordering::Relaxed) {
                    if delivery_guard.instance().and_then(|g| g.validate()).is_err() {
                        delivery_stop.store(true, Ordering::Relaxed);
                        break;
                    }
                    if worker == 0 {
                    // Settle cancellations of jobs no worker is still on.
                    let (active, busy) = (settle_claim_active.clone(), settle_delivering.clone());
                    if let Err(error) = delivery_store.settle_cancellations(
                        now(),
                        move || active.load(Ordering::SeqCst),
                        move |job| busy.contains(job),
                    )
                    {
                        eprintln!("Cancellation settlement failed: {error}");
                        delivery_stop.store(true, Ordering::Relaxed);
                        break;
                    }
                    // Confirmed retained-data deletions, a few targets per tick.
                    for _ in 0..16 {
                        if delivery_stop.load(Ordering::Relaxed) {
                            break;
                        }
                        let (job, index) = match delivery_store.next_deletion_target() {
                            Ok(Some((job, index, _))) => (job, index),
                            Ok(None) => break,
                            Err(error) => {
                                eprintln!("Deletion discovery failed: {error}");
                                delivery_stop.store(true, Ordering::Relaxed);
                                break;
                            }
                        };
                        // Marked active before the worker's first step.
                        let Some(_working) = delivering.enter(job) else {
                            break; // Another worker is on this job; next tick.
                        };
                        let outcome = claim_worker::discard(
                            &delivery_store,
                            &delivery_guard,
                            &delivery_stop,
                            job,
                            index,
                        );
                        if delivery_stop.load(Ordering::Relaxed) {
                            break; // Stopping: leave the target pending.
                        }
                        let diagnostic = outcome.as_ref().err().map(|d| {
                            let d: String = d.chars().filter(|c| c.is_ascii_graphic() || *c == ' ').take(240).collect();
                            if d.is_empty() { "blocked_or_uncertain".to_owned() } else { d }
                        });
                        if let Some(d) = &diagnostic {
                            eprintln!("Deletion of job {job} file {index} failed: {d}");
                        }
                        let diagnostic = diagnostic.or_else(|| {
                            matches!(&outcome, Ok(true)).then(|| mover_store::PRIVATE_LEFTOVERS.to_owned())
                        });
                        if let Err(error) = delivery_store.finish_deletion_target(
                            job,
                            index,
                            outcome.is_ok(),
                            diagnostic.as_deref(),
                            now(),
                        ) {
                            eprintln!("Deletion result persistence failed: {error}");
                            delivery_stop.store(true, Ordering::Relaxed);
                            break;
                        }
                    }
                    // Then unfinished destination data of confirmed passes, then
                    // automatic cleanup of delivered jobs' superseded attempts,
                    // under the job's destination custody lane like a delivery.
                    for _ in 0..16 {
                        if delivery_stop.load(Ordering::Relaxed) {
                            break;
                        }
                        let found = match delivery_store.next_destination_deletion() {
                            Ok(Some(work)) => Ok(Some((work, false))),
                            Ok(None) => delivery_store
                                .next_automatic_cleanup()
                                .map(|w| w.map(|w| (w, true))),
                            Err(error) => Err(error),
                        };
                        let (work, automatic) = match found {
                            Ok(Some(found)) => found,
                            Ok(None) => break,
                            Err(error) => {
                                eprintln!("Deletion discovery failed: {error}");
                                delivery_stop.store(true, Ordering::Relaxed);
                                break;
                            }
                        };
                        // Held through the worker's reaping and the result's
                        // persistence: history clear refuses a busy job.
                        let Some(_working) = delivering.enter(work.job_id) else {
                            break; // Another worker is on this job; next tick.
                        };
                        // No pass protects automatic discovery: recheck now
                        // that the job is marked busy (clear may have won).
                        if automatic {
                            match delivery_store.automatic_cleanup_eligible(&work) {
                                Ok(true) => (),
                                Ok(false) => continue,
                                Err(error) => {
                                    eprintln!("Deletion discovery failed: {error}");
                                    delivery_stop.store(true, Ordering::Relaxed);
                                    break;
                                }
                            }
                        }
                        let lane = custody.lane(
                            &delivery_store,
                            work.job_id,
                            &delivery_guard,
                            &delivery_stop,
                            parallel,
                        );
                        let shared = match &lane {
                            Lane::Shared(lock) => Some(lock.clone()),
                            Lane::Serialized(_) => None,
                            Lane::Wait => break, // Next tick.
                        };
                        let outcome = delivery_worker::discard(
                            &delivery_store,
                            &delivery_guard,
                            shared.as_deref(),
                            &delivery_stop,
                            &work,
                        );
                        drop(lane);
                        if delivery_stop.load(Ordering::Relaxed) {
                            break; // Stopping: leave the target pending.
                        }
                        let diagnostic = outcome.as_ref().err().map(|d| {
                            let d: String = d.chars().filter(|c| c.is_ascii_graphic() || *c == ' ').take(240).collect();
                            if d.is_empty() { "blocked_or_uncertain".to_owned() } else { d }
                        });
                        if let Some(d) = &diagnostic {
                            eprintln!(
                                "{} of job {} {} failed: {d}",
                                if automatic { "Cleanup" } else { "Deletion" },
                                work.job_id,
                                work.kind.code()
                            );
                        }
                        let recorded = if automatic {
                            delivery_store.finish_automatic_cleanup(
                                &work,
                                outcome.is_ok(),
                                diagnostic.as_deref(),
                            )
                        } else {
                            delivery_store.finish_destination_deletion(
                                &work,
                                outcome.is_ok(),
                                diagnostic.as_deref(),
                                now(),
                            )
                        };
                        if let Err(error) = recorded {
                            eprintln!("Deletion result persistence failed: {error}");
                            delivery_stop.store(true, Ordering::Relaxed);
                            break;
                        }
                    }
                    // Move mode: remove held source copies of delivered move
                    // jobs (design: MOVE-MODE-DESIGN), one job per round,
                    // under the job's destination custody lane.
                    for _ in 0..4 {
                        if !move_mode || delivery_stop.load(Ordering::Relaxed) {
                            break;
                        }
                        let work = match delivery_store.next_source_cleanup(now(), 16) {
                            Ok(Some(work)) => work,
                            Ok(None) => break,
                            Err(error) => {
                                eprintln!("Source cleanup discovery failed: {error}");
                                delivery_stop.store(true, Ordering::Relaxed);
                                break;
                            }
                        };
                        // Held through the worker's reaping and the results'
                        // persistence: history clear refuses a busy job.
                        let Some(_working) = delivering.enter(work.job_id) else {
                            break; // Another worker is on this job; next tick.
                        };
                        // No pass protects discovery: recheck now that the job
                        // is marked busy (clear or a deletion pass may have won).
                        match delivery_store.source_cleanup_eligible(&work, now()) {
                            Ok(true) => (),
                            Ok(false) => continue,
                            Err(error) => {
                                eprintln!("Source cleanup discovery failed: {error}");
                                delivery_stop.store(true, Ordering::Relaxed);
                                break;
                            }
                        }
                        let lane = custody.lane(
                            &delivery_store,
                            work.job_id,
                            &delivery_guard,
                            &delivery_stop,
                            parallel,
                        );
                        let shared = match &lane {
                            Lane::Shared(lock) => Some(lock.clone()),
                            Lane::Serialized(_) => None,
                            Lane::Wait => break, // Next tick.
                        };
                        let outcomes = delivery_worker::clean_sources(
                            &delivery_store,
                            &delivery_guard,
                            shared.as_deref(),
                            &delivery_stop,
                            &work,
                            now(),
                        );
                        if delivery_stop.load(Ordering::Relaxed) {
                            break; // Stopping: authorized intent stays, rerun later.
                        }
                        let outcomes: Vec<_> = outcomes
                            .into_iter()
                            .map(|(i, d)| {
                                (i, d.map(|d| {
                                    let d: String = d.chars().filter(|c| c.is_ascii_graphic() || *c == ' ').take(240).collect();
                                    if d.is_empty() { "blocked_or_uncertain".to_owned() } else { d }
                                }))
                            })
                            .collect();
                        for (i, d) in &outcomes {
                            if let Some(d) = d
                                && d != mover_store::PRIVATE_LEFTOVERS {
                                eprintln!("Source cleanup of job {} file {i} failed: {d}", work.job_id);
                            }
                        }
                        // Still holding the busy marker and the lane.
                        let recorded =
                            delivery_store.finish_source_cleanup(work.job_id, &outcomes, now());
                        drop(lane);
                        if let Err(error) = recorded {
                            eprintln!("Source cleanup result persistence failed: {error}");
                            delivery_stop.store(true, Ordering::Relaxed);
                            break;
                        }
                    }
                    }
                    match delivery_store.delivery_candidates(now(), 64) {
                        Ok(ids) => {
                            // Take the first ready job no other worker holds. The
                            // job is marked active before deliver's first
                            // cancellation check, then rechecked: the list may
                            // predate another worker finishing it.
                            let mut picked = None;
                            for id in ids {
                                if delivery_stop.load(Ordering::Relaxed) {
                                    break;
                                }
                                let Some(working) = delivering.enter(id) else {
                                    continue; // Another worker is on this job.
                                };
                                match delivery_store.is_delivery_candidate(id, now()) {
                                    Ok(true) => {
                                        picked = Some((id, working));
                                        break;
                                    }
                                    Ok(false) => continue,
                                    Err(error) => {
                                        eprintln!("Delivery discovery failed: {error}");
                                        delivery_stop.store(true, Ordering::Relaxed);
                                        break;
                                    }
                                }
                            }
                            // A loop (not `if let`) so the `continue`s below end this
                            // job and still reach the idle sleep.
                            #[allow(for_loops_over_fallibles)]
                            for (id, _working) in picked {
                                // Held to the end of this block: through the
                                // child's reaping and the final persistence.
                                let lane = custody.lane(
                                    &delivery_store,
                                    id,
                                    &delivery_guard,
                                    &delivery_stop,
                                    parallel,
                                );
                                let shared = match &lane {
                                    Lane::Shared(lock) => Some(lock.clone()),
                                    Lane::Serialized(_) => None,
                                    Lane::Wait => continue, // Next tick.
                                };
                                let mut problem = None;
                                let result = delivery_worker::deliver(
                                    &delivery_store,
                                    id,
                                    &delivery_guard,
                                    &delivery_stop,
                                    &mut problem,
                                    shared.as_deref(),
                                    tuning,
                                );
                                // A failed shared delivery may mean stale custody
                                // (for example a remounted destination): the next
                                // delivery reacquires instead of reusing it.
                                if let (Some(lock), Err(error)) = (&shared, &result)
                                    && !error.is::<delivery_worker::DeliveryCancelled>()
                                {
                                    custody.forget(lock);
                                }
                                // Informational record first, so the review shows the cause.
                                if let Some(p) = problem
                                    && let Err(error) = delivery_store.record_problem(
                                        id,
                                        mover_store::ProblemStage::Delivery,
                                        &p.diagnostic,
                                        p.file,
                                        now(),
                                    )
                                {
                                    eprintln!("Delivery {id} problem record failed: {error}");
                                }
                                if matches!(&result, Err(error) if error.is::<delivery_worker::DeliveryCancelled>()) {
                                    eprintln!("Delivery {id} stopped: job cancelled");
                                    continue;
                                }
                                if matches!(&result, Err(error) if error.is::<delivery_worker::DestinationBindingRefused>()) {
                                    if let Err(error)=delivery_store.destination_binding_refused(id,now()) {
                                        eprintln!("Destination refusal persistence failed: {error}");
                                        delivery_stop.store(true,Ordering::Relaxed);
                                    }
                                    continue;
                                }
                                if matches!(&result, Err(error) if error.is::<delivery_worker::DestinationCapacity>()) {
                                    eprintln!("Delivery {id} destination capacity backoff scheduled");
                                    if let Err(error) = delivery_store.delivery_failed_with_kind(id, now(), mover_core::DeliveryFailureKind::DestinationCapacity) {
                                        eprintln!("Delivery capacity retry persistence failed: {error}");
                                        delivery_stop.store(true, Ordering::Relaxed);
                                    }
                                    continue;
                                }
                                if matches!(result, Ok(false)) {
                                    if let Err(error) = delivery_store.delivery_deferred(id, now())
                                    {
                                        eprintln!("Delivery deferral persistence failed: {error}");
                                        delivery_stop.store(true, Ordering::Relaxed);
                                    }
                                    continue;
                                }
                                if let Err(error) = result {
                                    eprintln!("Delivery {id} requires reconciliation: {error}");
                                    if let Err(error) = delivery_store.delivery_failed(id, now()) {
                                        eprintln!("Delivery retry persistence failed: {error}");
                                        delivery_stop.store(true, Ordering::Relaxed);
                                    }
                                }
                            }
                        }
                        Err(error) => {
                            eprintln!("Delivery discovery failed: {error}");
                            delivery_stop.store(true, Ordering::Relaxed);
                        }
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
            });
            match spawned {
                Ok(t) => deliveries.push(t),
                Err(error) => {
                    stop.store(true, Ordering::Relaxed);
                    for t in deliveries {
                        let _ = t.join();
                    }
                    return Err(error.into());
                }
            }
        }
        let (sender, receiver) = mpsc::sync_channel::<Work>(1);
        let claim_stop = stop.clone();
        let check_expected_sizes = c.check_expected_sizes;
        let settle = Duration::from_secs(u64::from(c.missing_file_settle_seconds));
        let thread = match std::thread::Builder::new()
            .name("mover-local-claim".into())
            .spawn(move || {
                // Timer-driven missing-file retries share this thread with
                // producer claims (serialized); a due pass also runs after every
                // request, so steady traffic cannot starve it.
                let mut retry = missing_retry::Retry::new(settle);
                loop {
                    match receiver.recv_timeout(retry.wait(std::time::Instant::now())) {
                        Ok((submission, context, reply, lease)) => {
                            handle_submission(
                                &store,
                                &guard,
                                &claim_stop,
                                &claim_active,
                                &admission,
                                check_expected_sizes,
                                &mut retry,
                                (submission, context, reply, lease),
                            );
                        }
                        Err(mpsc::RecvTimeoutError::Timeout) => (),
                        Err(mpsc::RecvTimeoutError::Disconnected) => break,
                    }
                    if !claim_stop.load(Ordering::Relaxed) && retry.due(std::time::Instant::now()) {
                        claim_active.store(true, Ordering::SeqCst);
                        retry.pass(&store, &guard, &claim_stop, check_expected_sizes);
                        claim_active.store(false, Ordering::SeqCst);
                    }
                }
            }) {
            Ok(thread) => thread,
            Err(error) => {
                stop.store(true, Ordering::Relaxed);
                for t in deliveries {
                    let _ = t.join();
                }
                return Err(error.into());
            }
        };
        Ok(Self {
            sender: Some(sender),
            thread: Some(thread),
            deliveries,
            stop,
            observer: Some(observer),
            observation: Some(observation),
            _source_space: source_space,
            _instance: instance,
            control,
        })
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.control.lifecycle.request_stop();
        self.control.lifecycle.phase("Draining");
        let _ = mover_fs::qualification_pause("shutdown_drain");
        self.stop.store(true, Ordering::Relaxed);
        self.sender.take();
        self.observer.take();
        if let Some(t) = self.observation.take() {
            let _ = t.join();
        }
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        for t in self.deliveries.drain(..) {
            let _ = t.join();
        }
    }
}
fn claim_error(failure: mover_fs::ClaimError, id: i64) -> Response {
    match failure {
        mover_fs::ClaimError::OutcomeUncertain | mover_fs::ClaimError::ObservationChanged => error(503, "handoff_pending", true, Some(id)),
        mover_fs::ClaimError::ExpectedSizeMismatch => {
            error(409, "source_size_mismatch", false, Some(id))
        }
        mover_fs::ClaimError::Store(StoreError::AdmissionFull) => {
            error(503, "retention_capacity", true, Some(id))
        }
        mover_fs::ClaimError::Store(StoreError::Cancelled) => {
            error(409, "recording_cancelled", false, Some(id))
        }
        mover_fs::ClaimError::Store(_) => error(503, "storage_unavailable", true, Some(id)),
        _ => error(409, "recording_blocked", false, Some(id)),
    }
}
/// One producer submission on the claim thread (unchanged behavior).
#[allow(clippy::too_many_arguments)]
fn handle_submission(
    store: &Store,
    guard: &mover_fs::LocalClaimLock,
    claim_stop: &AtomicBool,
    claim_active: &AtomicBool,
    admission: &source_space::Handle,
    check_expected_sizes: bool,
    retry: &mut missing_retry::Retry,
    (submission, context, reply, lease): Work,
) {
    if claim_stop.load(Ordering::Relaxed) {
        let _ = reply.send(error(503, "service_stopping", true, None));
        return;
    }
    // Actual admission is serialized with policy activation, not
    // with enqueue: a request can have waited behind blocked I/O.
    let permit = match lease.as_ref().map(reload::Lease::admit).transpose() {
        Ok(permit) => permit,
        Err(()) => {
            let _ = reply.send(error(403, "caller_not_authorized", false, None));
            return;
        }
    };
    claim_active.store(true, Ordering::SeqCst);
    let result = process(
        store,
        guard,
        claim_stop,
        &submission,
        &context,
        admission,
        check_expected_sizes,
    );
    claim_active.store(false, Ordering::SeqCst);
    if let Some(permit) = permit {
        permit.finish(result.error != Some("source_space_unavailable"));
    }
    if let Some(job) = result.job_id.as_deref().and_then(|j| j.parse::<i64>().ok()) {
        retry.touched(job);
    }
    let _ = reply.send(result); // Lost response never rolls back a claim.
}

/// The whole-job size policy (no I/O): with checking on, a producer request
/// must carry a complete expected-size map, and every completed claim's
/// recorded size must match its expected size (legacy submissions always
/// check). Retries apply it before recovery and new claims alike.
pub(crate) fn size_policy_ok(
    store: &Store,
    job: &mover_store::Accepted,
    check_expected_sizes: bool,
) -> std::result::Result<bool, mover_store::StoreError> {
    let producer = job.recording.submission().producer();
    if check_expected_sizes && producer.is_some_and(|r| !r.expected_sizes_supplied()) {
        return Ok(false);
    }
    let check_sizes = producer.is_none() || check_expected_sizes;
    if check_sizes {
        for (index, file) in job.recording.submission().files().iter().enumerate() {
            if let Some((intent, true)) = store.claim_intent(job.job_id, index)?
                && file
                    .expected_size()
                    .is_some_and(|n| n != intent.source.size)
            {
                return Ok(false);
            }
        }
    }
    Ok(true)
}

/// Whole-job gates before claiming, shared unchanged by producer requests and
/// timer retries (docs/MISSING-FILE-RETRY-DESIGN.md), in order: cancellation,
/// persisted block, custody of completed claims, the complete size-map policy.
/// Completed claims' recorded sizes are then checked per file by the claim.
pub(crate) fn claim_gates(
    store: &Store,
    guard: &mover_fs::LocalClaimLock,
    stop: &AtomicBool,
    job: &mover_store::Accepted,
    check_expected_sizes: bool,
) -> std::result::Result<(), Response> {
    // Contract: an exact unfinished request first honors cancellation.
    match store.cancellation_requested(job.job_id) {
        Ok(false) => (),
        Ok(true) => return Err(error(409, "recording_cancelled", false, Some(job.job_id))),
        Err(_) => return Err(error(503, "storage_unavailable", true, Some(job.job_id))),
    }
    match store.claim_blocked(job.job_id, now()) {
        Ok(false) => (),
        Ok(true) => return Err(error(409, "recording_blocked", false, Some(job.job_id))),
        Err(_) => return Err(error(503, "storage_unavailable", true, Some(job.job_id))),
    }
    if let Err(e) = claim_worker::validate_existing(store, guard, stop, job.job_id, false) {
        return Err(claim_error(e, job.job_id));
    }
    if check_expected_sizes
        && job
            .recording
            .submission()
            .producer()
            .is_some_and(|r| !r.expected_sizes_supplied())
    {
        return Err(error(400, "invalid_submission", false, Some(job.job_id)));
    }
    Ok(())
}

fn process(
    store: &Store,
    guard: &mover_fs::LocalClaimLock,
    stop: &AtomicBool,
    s: &Submission,
    c: &AcceptanceContext,
    admission: &source_space::Handle,
    check_expected_sizes: bool,
) -> Response {
    if !guard.matches_path(&c.source_root_path) {
        return error(409, "recording_blocked", false, None);
    }
    if guard.instance().and_then(|g| g.validate()).is_err() {
        return error(409, "recording_blocked", false, None);
    }
    let gate = match store.replay(s) {
        Ok(true) => mover_store::NewJobAdmission::Unrestricted,
        Ok(false) => {
            if check_expected_sizes && s.producer().is_some_and(|r| !r.expected_sizes_supplied()) {
                return error(400, "invalid_submission", false, None);
            }
            admission.admission()
        }
        Err(StoreError::Protocol(
            ProtocolError::ConflictingReplay | ProtocolError::DifferentSubmission,
        )) => return error(409, "recording_id_conflict", false, None),
        Err(StoreError::SourceRootChanged | StoreError::CorruptState) => {
            return error(409, "recording_blocked", false, None);
        }
        Err(_) => return error(503, "storage_unavailable", true, None),
    };
    let mut job = match store.accept_with_admission(s, c, gate) {
        Ok(j) => j,
        Err(StoreError::Protocol(
            ProtocolError::ConflictingReplay | ProtocolError::DifferentSubmission,
        )) => return error(409, "recording_id_conflict", false, None),
        Err(StoreError::SourceSpaceLow) => return error(503, "source_space_low", true, None),
        Err(StoreError::SourceSpaceUnavailable) => {
            return error(503, "source_space_unavailable", true, None);
        }
        Err(StoreError::SourceCustodyRefused) => {
            return error(409, "recording_blocked", false, None);
        }
        Err(StoreError::SourceReserved) => return error(409, "source_reserved", false, None),
        Err(StoreError::AdmissionFull) => return error(503, "retention_capacity", true, None),
        Err(StoreError::SourceRootChanged | StoreError::CorruptState) => {
            return error(409, "recording_blocked", false, None);
        }
        Err(_) => return error(503, "storage_unavailable", true, None),
    };
    if job.recording.handoff() != Handoff::Ready202 {
        if let Err(refused) = claim_gates(store, guard, stop, &job, check_expected_sizes) {
            return refused;
        }
        for i in 0..job.recording.submission().files().len() {
            match claim_worker::claim(store, guard, stop, job.job_id, i, check_expected_sizes) {
                Ok(updated) => job = updated,
                Err(mover_fs::ClaimError::MissingSource) => {
                    return match store.note_missing(job.job_id, i, now()) {
                        Ok(false) => error(409, "source_file_missing", true, Some(job.job_id)),
                        Ok(true) => error(409, "recording_blocked", false, Some(job.job_id)),
                        Err(_) => error(503, "storage_unavailable", true, Some(job.job_id)),
                    };
                }
                Err(e) => return claim_error(e, job.job_id),
            }
        }
    }
    if job.recording.handoff() != Handoff::Ready202 {
        return error(503, "handoff_pending", true, Some(job.job_id));
    }
    if let Err(e) = claim_worker::validate_handoff(store, guard, stop, job.job_id) {
        return claim_error(e, job.job_id);
    }
    Response {
        status: 202,
        job_id: Some(job.job_id.to_string()),
        state: Some("Claimed"),
        source_paths_released: true,
        error: None,
        retryable: false,
        details: None,
    }
}
/// Latest recorded claim/delivery problem. `operation` and `errno` are parsed
/// from the bounded worker diagnostic ("<operation> errno=<n>; ...") when it has
/// that form; the raw diagnostic is always included. Omitted when none exists.
fn problem_view(problem: &mover_store::JobProblem) -> serde_json::Value {
    let head = problem.diagnostic.split(';').next().unwrap_or_default();
    let (operation, errno) = match head.split_once("errno=") {
        Some((operation, number)) => (
            operation.trim(),
            number.trim().parse::<i32>().ok().filter(|n| *n > 0),
        ),
        None => (head.trim(), None),
    };
    serde_json::json!({
        "stage": match problem.stage {
            mover_store::ProblemStage::Claim => "claim",
            mover_store::ProblemStage::Delivery => "delivery",
        },
        "operation": operation,
        "errno": errno,
        "file_id": problem.file_index.map(|i| i.to_string()),
        "diagnostic": problem.diagnostic,
        "recorded_at": problem.recorded_at,
    })
}
/// Contract DeletionStatus for the job's latest pass.
fn deletion_view(d: &mover_store::DeletionView) -> serde_json::Value {
    serde_json::json!({
        "completion_pending": d.completion_pending,
        "deleted_count": d.deleted_count,
        "failed_count": d.failed_count,
    })
}
/// Contract CancellationStatus; NotRequested when there is no request.
fn cancellation_view(c: Option<&mover_store::Cancellation>) -> serde_json::Value {
    match c {
        None => serde_json::json!({"state":"NotRequested","requested_at":null,"stopped_at":null}),
        Some(c) => serde_json::json!({
            "state": match c.state {
                mover_store::CancelState::Pending => "Pending",
                mover_store::CancelState::Cancelled => "Cancelled",
            },
            "requested_at": c.requested_at,
            "stopped_at": c.stopped_at,
        }),
    }
}
fn status_response(store: &Store, id: i64) -> Response {
    let snapshot = match store.status(id) {
        Ok(Some(s)) => s,
        Ok(None) => return error(404, "not_found", false, None),
        Err(_) => return error(503, "storage_unavailable", true, Some(id)),
    };
    let view = job_view(&snapshot);
    Response {
        status: 200,
        job_id: Some(id.to_string()),
        state: Some(view.state),
        source_paths_released: view.released,
        error: None,
        retryable: false,
        details: Some(view.details),
    }
}

/// The loaded move-mode setting (`delete_source_after_commit`), for status.
static MOVE_MODE: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

/// One derivation of state/condition/details shared by operator status and
/// admin history, so list rows and detail can never disagree.
struct JobView {
    state: &'static str,
    released: bool,
    condition: &'static str,
    details: serde_json::Value,
}
fn job_view(snapshot: &mover_store::JobStatus) -> JobView {
    let recording = &snapshot.job.recording;
    let released = recording.handoff() == Handoff::Ready202;
    let committed = recording.is_committed();
    let files: Vec<_> = recording.submission().files().iter().enumerate().map(|(i, f)| {
        let t = &snapshot.transfers[i];
        serde_json::json!({"file_id":i.to_string(),"name":f.relative_path(),"size_bytes":recording.file_size(i),
            "phase":format!("{:?}",recording.file_phase(i).expect("validated file index")),
            "transfer_phase":t.as_ref().map(|t|format!("{:?}",t.phase)),
            "attempt":t.as_ref().map(|t|t.attempt)})
    }).collect();
    let missing: Vec<_> = snapshot.missing.iter().map(|(i, deadline, blocked)| {
        let seen = missing_retry::last_seen(snapshot.job.job_id, *i);
        serde_json::json!({
            "file_id":i.to_string(),"deadline":deadline,"blocked":blocked,"deadline_elapsed":now()>=*deadline,
            "last_seen_at":seen,"settling":seen.is_some()
        })
    }).collect();
    let cancel_state = snapshot.cancellation.as_ref().map(|c| c.state);
    let moving = recording.policy().delete_source_after_commit;
    let condition = if committed {
        // A move job is complete once every held source copy is removed.
        if moving
            && (0..recording.submission().files().len())
                .any(|i| recording.file_phase(i) != Some(mover_core::FilePhase::SourceRemoved))
        {
            "CleanupPending"
        } else {
            "Committed"
        }
    } else if cancel_state == Some(mover_store::CancelState::Cancelled) {
        "Cancelled"
    } else if cancel_state == Some(mover_store::CancelState::Pending) {
        "CancellationPending"
    } else if snapshot.missing.iter().any(|(_, d, b)| *b || now() >= *d)
        || snapshot.delivery.as_ref().is_some_and(|(n, _, _)| *n >= 3)
    {
        "ReviewRequired"
    } else if !released {
        "AwaitingClaims"
    } else if snapshot.delivery.is_some() {
        "Retrying"
    } else {
        "Ready"
    };
    let mut details = serde_json::json!({"generator_id":recording.submission().generator_id(),"submission_id":recording.submission().submission_id(),
        "condition":condition,"review_epoch":snapshot.review_epoch,"missing_review_epoch":snapshot.missing_review_epoch,"manifest_phase":snapshot.manifest_phase,"source_cleanup_enabled":recording.policy().delete_source_after_commit,
        "latest_missing_reset":snapshot.latest_missing_reset.as_ref().map(|a|serde_json::json!({"command_id":a.request.command_id,"review_epoch":a.request.review_epoch,"file_id":a.request.file_index.to_string(),"retry_window_seconds":a.request.retry_window_seconds,"actor":a.request.actor,"reason":a.request.reason,"recorded_at":a.recorded_at,"prior_deadline":a.prior_deadline,"prior_blocked":a.prior_blocked,"new_deadline":a.new_deadline})),
        "latest_resume":snapshot.latest_resume.as_ref().map(|a|serde_json::json!({"command_id":a.command_id,"review_epoch":a.review_epoch,"actor":a.actor,"reason":a.reason,"recorded_at":a.recorded_at,"prior_retry_after":a.prior_retry_after,"prior_code":a.prior_code})),
        "files":files,"missing":missing,"delivery_retry":snapshot.delivery.as_ref().map(|(failures,retry_after,code)|serde_json::json!({"failures":failures,"retry_after":retry_after,"code":code}))});
    if let Some(d) = &snapshot.deletion {
        details
            .as_object_mut()
            .expect("status object")
            .insert("deletion".into(), deletion_view(d));
    }
    if let Some(s) = &snapshot.source_cleanup {
        details.as_object_mut().expect("status object").insert(
            "source_cleanup".into(),
            serde_json::json!({
                "enabled": MOVE_MODE.load(Ordering::Relaxed),
                "removed": s.removed,
                "pending": s.pending,
                "failed": s.failed,
                "next_attempt_at": s.next_attempt_at,
                "last_error": s.last_error,
            }),
        );
    }
    if let Some(c) = &snapshot.cancellation {
        details
            .as_object_mut()
            .expect("status object")
            .insert("cancellation".into(), cancellation_view(Some(c)));
    }
    if !snapshot.private_leftovers.is_empty() {
        details.as_object_mut().expect("status object").insert(
            "private_leftovers".into(),
            serde_json::json!(
                snapshot
                    .private_leftovers
                    .iter()
                    .map(|w| serde_json::json!({
                        "file_id": w.file_index.to_string(), "folder_path": w.folder_path,
                    }))
                    .collect::<Vec<_>>()
            ),
        );
    }
    if let Some(problem) = &snapshot.problem {
        details
            .as_object_mut()
            .expect("status object")
            .insert("last_problem".into(), problem_view(problem));
    }
    if let Some(request) = recording.submission().producer() {
        let object = details.as_object_mut().expect("status object");
        object.remove("submission_id");
        object.insert(
            "recording_id".into(),
            serde_json::json!(request.recording_id().to_string()),
        );
    }
    JobView {
        state: if committed {
            "Committed"
        } else if released {
            "Claimed"
        } else {
            "Accepted"
        },
        released,
        condition,
        details,
    }
}

/// Reviewed-retry context epoch for the RetryReviewSnapshot projection. Only a
/// job that the existing resume command would accept right now (released, not
/// committed, in delivery review after three failures, audit capacity left)
/// exposes its epoch. Every other job gets the permanently nonauthorizing null,
/// so an epoch copied while a job was healthy can never authorize a later retry.
fn retry_review_epoch(
    released: bool,
    committed: bool,
    delivery_failures: Option<u32>,
    epoch: u32,
) -> Option<u32> {
    (released && !committed && delivery_failures == Some(3) && epoch < 64).then_some(epoch)
}

/// One admin history page: continue after (ascending) or before (descending)
/// `cursor`, bounded by `limit`; `bound` is the instance a supplied cursor names.
pub(crate) struct PageRequest {
    pub(crate) cursor: Option<i64>,
    pub(crate) limit: usize,
    pub(crate) descending: bool,
    pub(crate) bound: Option<String>,
}

/// One chunk of an admin file-name search
/// (docs/dashboard/FILE-NAME-SEARCH-DESIGN.md).
pub(crate) struct SearchRequest {
    /// Normalized query: trimmed, Unicode-lowercased.
    pub(crate) needle: String,
    /// Hex SHA-256 of the normalized query (cursor binding).
    pub(crate) digest: String,
    /// Oldest job to scan; 0 when absent.
    pub(crate) until: i64,
    /// Scan jobs older than this one (`i64::MAX` for a first request).
    pub(crate) before: i64,
    /// The instance a continuation cursor was issued for.
    pub(crate) bound: Option<String>,
}

/// Opaque search cursor, bound to the instance, the normalized query and
/// `until`; it continues below the last job scanned.
pub(crate) fn search_cursor(instance: &str, digest: &str, until: i64, last: i64) -> String {
    format!("c1.{instance}.s.{digest}.{until}.{last}")
}

fn search_response(store: &Store, request: SearchRequest) -> Response {
    let Ok(instance) = store.instance_id() else {
        return error(503, "storage_unavailable", true, None);
    };
    if request.bound.as_ref().is_some_and(|b| *b != instance) {
        return error(400, "invalid_cursor", false, None);
    }
    let chunk = match store.search_file_paths(request.needle, request.before, request.until) {
        Ok(chunk) => chunk,
        Err(_) => return error(503, "storage_unavailable", true, None),
    };
    let next = chunk
        .continue_before
        .map(|last| search_cursor(&instance, &request.digest, request.until, last));
    let ids: Vec<String> = chunk.matches.iter().map(i64::to_string).collect();
    Response {
        status: 200,
        job_id: None,
        state: None,
        source_paths_released: false,
        error: None,
        retryable: false,
        details: Some(serde_json::json!({
            "job_ids": ids,
            "next_cursor": next,
            "scanned_jobs": chunk.scanned_jobs,
        })),
    }
}

/// Opaque admin history cursor bound to the state instance and sort order.
/// Clients must not parse it; the service rejects a cursor from another
/// instance or one used with the other order.
pub(crate) fn history_cursor(instance: &str, descending: bool, last: i64) -> String {
    format!(
        "c1.{instance}.{}.{last}",
        if descending { "d" } else { "a" }
    )
}

/// Bounded admin history page. Summary fields follow the frozen JobSummary
/// shape. Action extensions report their real, unimplemented state: no
/// cancellation was ever requested and no deletion pass exists.
fn page_response(store: &Store, request: PageRequest) -> Response {
    let PageRequest {
        cursor,
        limit,
        descending,
        bound,
    } = request;
    let Ok(instance) = store.instance_id() else {
        return error(503, "storage_unavailable", true, None);
    };
    if bound.is_some_and(|b| b != instance) {
        return error(400, "invalid_cursor", false, None);
    }
    let start = cursor.unwrap_or(if descending { i64::MAX } else { 0 });
    let (rows, more) = match store.status_page(start, limit, descending) {
        Ok(page) => page,
        Err(_) => return error(503, "storage_unavailable", true, None),
    };
    let next = if more {
        rows.last()
            .map(|(id, _)| history_cursor(&instance, descending, *id))
    } else {
        None
    };
    let items: Vec<_> = rows
        .iter()
        .map(|(id, status)| {
            let view = job_view(status);
            let mut item = serde_json::json!({
                "job_id": id.to_string(),
                "generator_id": view.details["generator_id"],
                "state": view.state,
                "condition": view.condition,
                "source_paths_released": view.released,
                "retry_review": {"instance_id": instance, "job_id": id.to_string(), "review_epoch": retry_review_epoch(
                    view.released,
                    status.job.recording.is_committed(),
                    status.delivery.as_ref().map(|(failures, _, _)| *failures),
                    status.review_epoch,
                )},
                "cancellation": cancellation_view(status.cancellation.as_ref()),
                "deletion": status.deletion.as_ref().map(deletion_view),
            });
            // Dashboard row extension (approved 2026-11-12): file progress,
            // measured size, relative folders and the effective transfer mode.
            let files = view.details["files"].as_array().map(Vec::as_slice).unwrap_or(&[]);
            // Delivered means visible to consumers: only once the job committed
            // (a cancelled job's published files were never delivered).
            let delivered = if status.job.recording.is_committed() {
                files
                    .iter()
                    .filter(|f| matches!(f["phase"].as_str(), Some("Published" | "SourceRemoved")))
                    .count()
            } else {
                0
            };
            let measured: u128 = files.iter().filter_map(|f| f["size_bytes"].as_u64()).map(u128::from).sum();
            let unmeasured = files.iter().filter(|f| f["size_bytes"].is_null()).count();
            item["files_total"] = files.len().into();
            item["files_delivered"] = delivered.into();
            // Move mode: a failing source cleanup needs attention.
            if !status.private_leftovers.is_empty() {
                item["private_leftovers_count"] = status.private_leftovers.len().into();
            }
            item["source_cleanup_failed"] = status
                .source_cleanup
                .as_ref()
                .is_some_and(|s| s.failed > 0)
                .into();
            item["measured_bytes"] = measured.to_string().into();
            item["unmeasured_files"] = unmeasured.into();
            item["source_folder"] = status.job.context.source_relative_directory.clone().into();
            item["destination_folder"] = status
                .job
                .recording
                .submission()
                .destination_component(*id)
                .into();
            item["transfer_mode"] = if view.details["source_cleanup_enabled"] == true {
                "Move"
            } else {
                "Copy"
            }
            .into();
            for key in ["recording_id", "submission_id"] {
                if let Some(value) = view.details.get(key) {
                    item[key] = value.clone();
                }
            }
            item
        })
        .collect();
    Response {
        status: 200,
        job_id: None,
        state: None,
        source_paths_released: false,
        error: None,
        retryable: false,
        details: Some(
            serde_json::json!({"items": items, "next_cursor": next, "confirmation": null}),
        ),
    }
}
fn resume_response(store: &Store, id: i64, input: ResumeInput) -> Response {
    let request = mover_store::ResumeRequest {
        command_id: input.command_id,
        review_epoch: input.expected_review_epoch,
        actor: "trusted-loopback-operator".into(),
        reason: input.reason,
    };
    match store.resume_delivery(id, &request, now()) {
        Ok(receipt) => Response {
            status: 200,
            job_id: Some(id.to_string()),
            state: None,
            source_paths_released: true,
            error: None,
            retryable: false,
            details: Some(
                serde_json::json!({"action":"DeliveryResumeScheduled","command_id":request.command_id,"review_epoch":receipt.review_epoch,"replay":receipt.replay}),
            ),
        },
        Err(StoreError::NotFound) => error(404, "not_found", false, None),
        Err(StoreError::InvalidContext) => error(400, "invalid_resume", false, Some(id)),
        Err(StoreError::ReviewConflict) => error(409, "review_conflict", false, Some(id)),
        Err(StoreError::ActionConflict) => error(409, "command_conflict", false, Some(id)),
        Err(StoreError::AuditFull) => error(409, "operator_audit_capacity", false, Some(id)),
        Err(StoreError::Cancelled) => error(409, "recording_cancelled", false, Some(id)),
        Err(_) => error(503, "storage_unavailable", true, Some(id)),
    }
}
fn observed(details: serde_json::Value) -> Response {
    Response {
        status: 200,
        error: None,
        details: Some(details),
        ..error(200, "observed", false, None)
    }
}
fn retry_scope_response(store: &Store) -> Response {
    match store
        .instance_id()
        .and_then(|i| Ok((i, store.job_id_high_water()?)))
    {
        Ok((instance, high_water)) => {
            observed(serde_json::json!({"instance_id":instance,"high_water":high_water}))
        }
        Err(_) => error(503, "storage_unavailable", true, None),
    }
}
/// Jobs that delivery workers are working on (delivery or deletion). Online
/// clear and cancellation settlement read it inside their store transactions;
/// a worker enters a job before its first store check of that job and leaves
/// when its block ends, including every early `continue`.
#[derive(Clone, Default)]
pub(crate) struct ActiveJobs(Arc<std::sync::Mutex<std::collections::BTreeSet<i64>>>);
impl ActiveJobs {
    fn set(&self) -> std::sync::MutexGuard<'_, std::collections::BTreeSet<i64>> {
        // The set stays consistent even if a holder panicked: inserts and
        // removes are single operations.
        self.0.lock().unwrap_or_else(|e| e.into_inner())
    }
    /// Marks `job` active; `None` if a worker is already on it.
    pub(crate) fn enter(&self, job: i64) -> Option<Working> {
        self.set().insert(job).then(|| Working(self.clone(), job))
    }
    pub(crate) fn contains(&self, job: i64) -> bool {
        self.set().contains(&job)
    }
}
/// Destination custody for delivery workers. With `delivery_concurrency` 1
/// every delivery uses the serialized lane, exactly as before parallel
/// delivery: its child acquires the destination itself. With more workers, a
/// bound job uses the coordinator's shared custody for its destination path,
/// acquired once in a supervised child (one attempt in flight) and inherited
/// by every delivery child, which validates its own job's binding and pin
/// against it. If acquisition fails, the job falls back to the serialized
/// lane, so destination outages and refusals keep their existing deferral
/// and review behavior. Cooperative custody, not NFS fencing.
#[derive(Default)]
struct SharedCustody {
    /// Per destination path: the custody, and whether it is draining (a shared
    /// delivery failed: no new delivery uses it, and it is released and
    /// reacquired only after every delivery still using it has exited).
    held: std::sync::Mutex<std::collections::BTreeMap<String, Held>>,
    /// One acquisition in flight; also the serialized lane, so a legacy child
    /// never races an acquisition for the same destination lock.
    lane: std::sync::Mutex<()>,
}
type Held = (Arc<mover_fs::LocalClaimLock>, bool);
enum Current {
    Usable(Arc<mover_fs::LocalClaimLock>),
    Draining,
    Absent,
}
enum Lane<'a> {
    Shared(Arc<mover_fs::LocalClaimLock>),
    Serialized(#[allow(dead_code)] std::sync::MutexGuard<'a, ()>),
    /// Shared custody of this destination is still in use; try next tick.
    Wait,
}
impl SharedCustody {
    fn held(&self) -> std::sync::MutexGuard<'_, std::collections::BTreeMap<String, Held>> {
        self.held.lock().unwrap_or_else(|e| e.into_inner())
    }
    fn serialized(&self) -> std::sync::MutexGuard<'_, ()> {
        self.lane.lock().unwrap_or_else(|e| e.into_inner())
    }
    fn lane(
        &self,
        store: &Store,
        id: i64,
        guard: &mover_fs::LocalClaimLock,
        stop: &AtomicBool,
        parallel: bool,
    ) -> Lane<'_> {
        let Ok(Some(job)) = store.get(id) else {
            return Lane::Serialized(self.serialized()); // deliver reports it.
        };
        let path = job.context.destination_path.clone();
        let binding = job
            .context
            .destination_binding
            .as_deref()
            .and_then(|b| serde_json::from_str::<mover_fs::DestinationBinding>(b).ok());
        if let (true, Some(binding)) = (parallel, binding) {
            match self.current(&path) {
                Current::Usable(lock) => return Lane::Shared(lock),
                Current::Draining => return Lane::Wait,
                Current::Absent => {}
            }
            let serial = self.serialized();
            match self.current(&path) {
                Current::Usable(lock) => return Lane::Shared(lock),
                Current::Draining => return Lane::Wait,
                Current::Absent => {}
            }
            let pin = store.destination_observation(id).ok().flatten();
            let acquired = guard
                .instance()
                .map_err(|e| e.to_string())
                .and_then(|instance| {
                    bootstrap::acquire_destination(&path, &binding, pin.as_deref(), stop, instance)
                });
            match acquired {
                Ok(lock) => {
                    let lock = Arc::new(lock);
                    self.held().insert(path, (lock.clone(), false));
                    return Lane::Shared(lock);
                }
                Err(error) => {
                    eprintln!(
                        "Shared destination custody for delivery {id} unavailable ({error}); using the serialized lane"
                    );
                    return Lane::Serialized(serial);
                }
            }
        }
        // Serialized lane: the child acquires the destination itself, which
        // requires that this coordinator does not hold it. Shared custody of
        // the same path is released once no delivery uses it.
        let serial = self.serialized();
        let mut held = self.held();
        if let Some((lock, _)) = held.get(&path) {
            if Arc::strong_count(lock) > 1 {
                return Lane::Wait;
            }
            held.remove(&path);
        }
        drop(held);
        Lane::Serialized(serial)
    }
    /// The usable custody of `path`, if any. A draining entry that no delivery
    /// uses any more is removed (its lock closes), so the caller reacquires.
    fn current(&self, path: &str) -> Current {
        let mut held = self.held();
        match held.get(path) {
            None => Current::Absent,
            Some((lock, false)) => Current::Usable(lock.clone()),
            Some((lock, true)) if Arc::strong_count(lock) > 1 => Current::Draining,
            Some(_) => {
                held.remove(path);
                Current::Absent
            }
        }
    }
    /// A shared delivery failed, possibly on stale custody (for example a
    /// remounted destination): stop handing it out. It is released and
    /// reacquired once every delivery still using it has exited.
    fn forget(&self, lock: &Arc<mover_fs::LocalClaimLock>) {
        for (held, draining) in self.held().values_mut() {
            if Arc::ptr_eq(held, lock) {
                *draining = true;
            }
        }
    }
}
/// A worker's hold on one active job; dropping it leaves the job.
pub(crate) struct Working(ActiveJobs, i64);
impl Drop for Working {
    fn drop(&mut self) {
        self.0.set().remove(&self.1);
    }
}
fn clear_response(store: &Store, id: i64, busy: impl Fn(i64) -> bool + Send + 'static) -> Response {
    match store.admin_clear(id, busy) {
        Ok(outcome) => observed(serde_json::json!({"outcome":match outcome {
            mover_store::ClearOutcome::Cleared => "cleared",
            mover_store::ClearOutcome::Skipped => "skipped",
            mover_store::ClearOutcome::Busy => "busy",
        }})),
        Err(_) => error(503, "storage_unavailable", true, None),
    }
}
fn delete_preview_response(store: &Store, id: i64, scope: mover_store::DeletionScope) -> Response {
    match store.deletion_preview(id, scope) {
        Ok(Some((targets, fingerprint))) => observed(serde_json::json!({
            "fingerprint": fingerprint,
            "targets": targets.iter().map(|t| serde_json::json!({
                "file_id": t.file_index.map(|i| i.to_string()),
                "kind": t.kind.code(),
                "relative_path": t.relative_path,
                "attempt": t.attempt,
                "size_bytes": t.size_bytes,
            })).collect::<Vec<_>>(),
        })),
        // Missing, unfinished or already deleting: nothing to confirm now.
        Ok(None) => observed(serde_json::json!({"fingerprint": null, "targets": []})),
        Err(_) => error(503, "storage_unavailable", true, None),
    }
}
fn delete_start_response(
    store: &Store,
    id: i64,
    scope: mover_store::DeletionScope,
    principal: &str,
    proof_digest: &str,
    confirmed: &str,
) -> Response {
    match store.start_deletion(id, scope, principal, proof_digest, confirmed, now()) {
        Ok(mover_store::DeletionStart::Started(v)) => {
            observed(serde_json::json!({"outcome":"started","status":deletion_view(&v)}))
        }
        Ok(mover_store::DeletionStart::Pass(v)) => {
            observed(serde_json::json!({"outcome":"pass","status":deletion_view(&v)}))
        }
        Ok(mover_store::DeletionStart::Stale) => observed(serde_json::json!({"outcome":"stale"})),
        Ok(mover_store::DeletionStart::NoWork | mover_store::DeletionStart::Skipped) => {
            observed(serde_json::json!({"outcome":"none"}))
        }
        Err(_) => error(503, "storage_unavailable", true, None),
    }
}
fn cancel_response(store: &Store, id: i64, principal: &str) -> Response {
    match store.admin_cancel(id, principal, now()) {
        Ok(outcome) => observed(serde_json::json!({"outcome":match outcome {
            mover_store::CancelOutcome::Accepted => "accepted",
            mover_store::CancelOutcome::Failed => "failed",
            mover_store::CancelOutcome::Skipped => "skipped",
        }})),
        Err(_) => error(503, "storage_unavailable", true, None),
    }
}
fn retry_response(store: &Store, o: &mover_store::RetryOccurrence) -> Response {
    match store.admin_retry(o, now()) {
        Ok(r) => observed(
            serde_json::json!({"replay":r.replay,"outcome":match r.outcome {
                mover_store::RetryOutcome::Accepted => "accepted",
                mover_store::RetryOutcome::Failed => "failed",
                mover_store::RetryOutcome::Skipped => "skipped",
            }}),
        ),
        Err(StoreError::ReviewConflict) => error(409, "review_conflict", false, None),
        Err(StoreError::ActionConflict) => error(409, "command_conflict", false, None),
        Err(StoreError::InvalidContext) => error(400, "invalid_retry_context", false, None),
        Err(StoreError::ReceiptCapacity) => error(503, "service_busy", true, None),
        Err(_) => error(503, "storage_unavailable", true, None),
    }
}
fn retention_response(store: &Store, id: Option<i64>) -> Response {
    let r = match store.retention(id) {
        Ok(Some(r)) => r,
        Ok(None) => return error(404, "not_found", false, None),
        Err(_) => return error(503, "storage_unavailable", true, id),
    };
    let limits=r.configured_limits.map(|(jobs,bytes)|serde_json::json!({"max_retained_jobs":jobs,"max_reserved_bytes":bytes.to_string()}));
    let headroom = if id.is_none() {
        r.configured_limits.map(|(jobs,bytes)|serde_json::json!({"new_job_slots":jobs.saturating_sub(r.jobs),"source_bytes":u128::from(bytes).saturating_sub(r.source_reserved_bytes).to_string(),"destination_bytes":u128::from(bytes).saturating_sub(r.destination_reserved_bytes).to_string(),"over_limit":r.jobs>jobs || r.source_reserved_bytes>u128::from(bytes) || r.destination_reserved_bytes>u128::from(bytes)}))
    } else {
        None
    };
    Response {
        status: 200,
        job_id: r.job_id.map(|id| id.to_string()),
        state: None,
        source_paths_released: false,
        error: None,
        retryable: false,
        details: Some(
            serde_json::json!({"scope":if id.is_some(){"Job"}else{"Global"},"retained_jobs":r.jobs,"committed_jobs":r.committed_jobs,"source_claims":r.source_claims,"confirmed_claims":r.confirmed_claims,"unmeasured_files":r.unmeasured_files,"source_reserved_bytes":r.source_reserved_bytes.to_string(),"destination_reserved_bytes":r.destination_reserved_bytes.to_string(),"destination_attempts_by_phase":{"Intent":r.destination_attempts_by_phase[0],"Copied":r.destination_attempts_by_phase[1],"Verified":r.destination_attempts_by_phase[2],"PublishIntent":r.destination_attempts_by_phase[3],"Published":r.destination_attempts_by_phase[4]},"configured_limits":limits,"global_headroom":headroom,"filesystem_inspected":false,"unreceipted_allocations_accounted":false,"automatic_reclamation_enabled":false}),
        ),
    }
}
async fn operator_reply(observer: &mpsc::SyncSender<OperatorWork>, work: Observation) -> Response {
    let (reply, result) = oneshot::channel();
    if observer.try_send((work, reply)).is_err() {
        error(503, "service_busy", true, None)
    } else {
        match timeout(Duration::from_secs(2), result).await {
            Ok(Ok(r)) => r,
            _ => error(503, "storage_unavailable", true, None),
        }
    }
}
fn missing_reset_response(store: &Store, id: i64, input: MissingResetInput) -> Response {
    let Some(file_index) = input
        .file_id
        .parse::<u32>()
        .ok()
        .filter(|i| i.to_string() == input.file_id)
    else {
        return error(400, "invalid_missing_reset", false, Some(id));
    };
    let request = mover_store::MissingResetRequest {
        command_id: input.command_id,
        review_epoch: input.expected_missing_review_epoch,
        file_index,
        retry_window_seconds: input.retry_window_seconds,
        actor: "trusted-loopback-operator".into(),
        reason: input.reason,
    };
    match store.reset_missing(id, &request, now()) {
        Ok(receipt) => Response {
            status: 200,
            job_id: Some(id.to_string()),
            state: None,
            source_paths_released: false,
            error: None,
            retryable: false,
            details: Some(
                serde_json::json!({"action":"MissingDeadlineReset","command_id":request.command_id,"missing_review_epoch":receipt.review_epoch,"new_deadline":receipt.new_deadline,"replay":receipt.replay}),
            ),
        },
        Err(StoreError::NotFound) => error(404, "not_found", false, None),
        Err(StoreError::InvalidContext) => error(400, "invalid_missing_reset", false, Some(id)),
        Err(StoreError::ReviewConflict) => error(409, "review_conflict", false, Some(id)),
        Err(StoreError::ActionConflict) => error(409, "command_conflict", false, Some(id)),
        Err(StoreError::AuditFull) => error(409, "operator_audit_capacity", false, Some(id)),
        Err(StoreError::Cancelled) => error(409, "recording_cancelled", false, Some(id)),
        Err(_) => error(503, "storage_unavailable", true, Some(id)),
    }
}
async fn request(stream: &mut ingress::Stream) -> Result<http::Request, Response> {
    let mut bytes = Vec::new();
    let mut buffer = [0; 4096];
    loop {
        match http::frame(&bytes) {
            http::Frame::Complete(r) => return Ok(r),
            http::Frame::Reject(s) => {
                return Err(error(
                    s,
                    match s {
                        413 => "request_too_large",
                        431 => "request_headers_too_large",
                        _ => "invalid_http",
                    },
                    false,
                    None,
                ));
            }
            http::Frame::NeedMore => (),
        }
        let n = stream
            .read(&mut buffer)
            .await
            .map_err(|_| error(400, "invalid_http", false, None))?;
        if n == 0 {
            return Err(error(400, "incomplete_request", false, None));
        }
        bytes.extend_from_slice(&buffer[..n]);
    }
}
async fn submission_reply(
    sender: &mpsc::SyncSender<Work>,
    admission: &source_space::Handle,
    submission: Submission,
    context: AcceptanceContext,
    lease: Option<reload::Lease>,
) -> Response {
    async fn once(
        sender: &mpsc::SyncSender<Work>,
        submission: Submission,
        context: AcceptanceContext,
        lease: Option<reload::Lease>,
    ) -> Response {
        let (reply, result) = oneshot::channel();
        if let Some(lease) = &lease
            && !lease.queue()
        {
            return error(403, "caller_not_authorized", false, None);
        }
        if sender
            .try_send((submission, context, reply, lease))
            .is_err()
        {
            return error(503, "service_busy", true, None);
        }
        result
            .await
            .unwrap_or_else(|_| error(503, "handoff_pending", true, None))
    }
    let mut capacity_wait = false;
    let outcome = timeout(Duration::from_secs(10), async {
        let first = once(sender, submission.clone(), context.clone(), lease.clone()).await;
        if first.error != Some("source_space_unavailable") {
            return first;
        }
        capacity_wait = true;
        let ready = admission.wait_for_probe().await;
        capacity_wait = false;
        if ready {
            once(sender, submission, context, lease).await
        } else {
            first
        }
    })
    .await;
    outcome.unwrap_or_else(|_| {
        error(
            503,
            if capacity_wait {
                "source_space_unavailable"
            } else {
                "handoff_pending"
            },
            true,
            None,
        )
    })
}
async fn connection(
    mut stream: ingress::Stream,
    c: Arc<Config>,
    sender: mpsc::SyncSender<Work>,
    observer: mpsc::SyncSender<OperatorWork>,
    admission: source_space::Handle,
    audience: ingress::Audience,
    lease: Option<reload::Lease>,
) {
    let mut producer = !matches!(audience, ingress::Audience::Operator(_));
    let mut recording_id = None;
    let response = if !audience.authorized() {
        error(403, "caller_not_authorized", false, None)
    } else {
        match timeout(Duration::from_secs(5), request(&mut stream)).await {
            Err(_) => error(408, "request_timeout", true, None),
            Ok(Err(e)) => e,
            Ok(Ok(r)) => {
                producer = audience.producer()
                    || (matches!(audience, ingress::Audience::Prototype)
                        && r.head.target == b"/api/v2/jobs");
                if r.head.headers.get("host").is_none_or(|h| h.is_empty())
                    || r.head.headers.contains_key("expect")
                    || r.head.headers.contains_key("authorization")
                {
                    error(400, "unsupported_headers", false, None)
                } else if let Some(denial) = audience.denial(&r, &c) {
                    denial
                } else if r.head.method == "GET"
                    && r.head.target == b"/healthz"
                    && r.body.is_empty()
                {
                    Response {
                        status: 200,
                        job_id: None,
                        state: Some("Running"),
                        source_paths_released: false,
                        error: None,
                        retryable: false,
                        details: None,
                    }
                } else if r.head.target == b"/api/v2/retention" {
                    if r.head.method != "GET" {
                        error(405, "method_not_allowed", false, None)
                    } else if !r.body.is_empty() {
                        error(400, "unexpected_body", false, None)
                    } else {
                        operator_reply(&observer, Observation::Retention(None)).await
                    }
                } else if r.head.target.starts_with(b"/api/v2/jobs/") {
                    let target = &r.head.target[13..];
                    let resume = target.ends_with(b"/resume");
                    let reset_missing = target.ends_with(b"/reset-missing");
                    let retention = target.ends_with(b"/retention");
                    let control = resume || reset_missing;
                    let id_bytes = if resume {
                        &target[..target.len() - 7]
                    } else if reset_missing {
                        &target[..target.len() - 14]
                    } else if retention {
                        &target[..target.len() - 10]
                    } else {
                        target
                    };
                    if r.head.method != if control { "POST" } else { "GET" } {
                        error(405, "method_not_allowed", false, None)
                    } else if !control && !r.body.is_empty() {
                        error(400, "unexpected_body", false, None)
                    } else if control
                        && r.head.headers.get("content-type").map(Vec::as_slice)
                            != Some(b"application/json")
                    {
                        error(415, "unsupported_media_type", false, None)
                    } else {
                        let id = std::str::from_utf8(id_bytes).ok().and_then(|s| {
                            s.parse::<i64>()
                                .ok()
                                .filter(|id| *id > 0 && id.to_string() == s)
                        });
                        if let Some(id) = id {
                            let work = if resume {
                                serde_json::from_slice::<ResumeInput>(&r.body)
                                    .map(|input| Observation::Resume(id, input))
                            } else if reset_missing {
                                serde_json::from_slice::<MissingResetInput>(&r.body)
                                    .map(|input| Observation::ResetMissing(id, input))
                            } else if retention {
                                Ok(Observation::Retention(Some(id)))
                            } else {
                                Ok(Observation::Status(id))
                            };
                            if let Ok(work) = work {
                                let command_id = match &work {
                                    Observation::Resume(_, input) => Some(&input.command_id),
                                    Observation::ResetMissing(_, input) => Some(&input.command_id),
                                    Observation::Status(_)
                                    | Observation::Retention(_)
                                    | Observation::Page(..)
                                    | Observation::Search(..)
                                    | Observation::RetryScope
                                    | Observation::Retry(..)
                                    | Observation::Cancel(..)
                                    | Observation::Clear(..)
                                    | Observation::DeletePreview(..)
                                    | Observation::DeleteStart { .. } => None,
                                };
                                let key_conflict = command_id.is_some_and(|id| {
                                    r.head
                                        .headers
                                        .get("idempotency-key")
                                        .is_some_and(|key| key.as_slice() != id.as_bytes())
                                });
                                if key_conflict {
                                    error(400, "idempotency_key_conflict", false, Some(id))
                                } else {
                                    let (reply, result) = oneshot::channel();
                                    if observer.try_send((work, reply)).is_err() {
                                        error(503, "service_busy", true, None)
                                    } else {
                                        match timeout(Duration::from_secs(2), result).await {
                                            Ok(Ok(r)) => r,
                                            _ => error(503, "storage_unavailable", true, Some(id)),
                                        }
                                    }
                                }
                            } else {
                                error(
                                    400,
                                    if reset_missing {
                                        "invalid_missing_reset"
                                    } else {
                                        "invalid_resume"
                                    },
                                    false,
                                    Some(id),
                                )
                            }
                        } else {
                            error(400, "invalid_job_id", false, None)
                        }
                    }
                } else if r.head.target != b"/api/v2/jobs" {
                    error(404, "not_found", false, None)
                } else if r.head.method != "POST" {
                    error(405, "method_not_allowed", false, None)
                } else if r.head.headers.get("content-type").map(Vec::as_slice)
                    != Some(b"application/json")
                {
                    error(415, "unsupported_media_type", false, None)
                } else {
                    match decode(&r.body, &c) {
                        Err(e) => e,
                        Ok((submission, context)) => {
                            recording_id =
                                submission.producer().map(|r| r.recording_id().to_string());
                            if r.head.headers.get("idempotency-key").is_some_and(|key| {
                                std::str::from_utf8(key).ok().is_none_or(|key| {
                                    mover_fs::recording_codec::validate_idempotency_key(
                                        submission
                                            .producer()
                                            .expect("producer request")
                                            .recording_id(),
                                        key,
                                    )
                                    .is_err()
                                })
                            }) {
                                error(400, "idempotency_key_conflict", false, None)
                            } else {
                                submission_reply(&sender, &admission, submission, context, lease)
                                    .await
                            }
                        }
                    }
                }
            }
        }
    };
    write_response(&mut stream, &response, recording_id, producer).await;
}
async fn write_response(
    stream: &mut ingress::Stream,
    response: &Response,
    recording_id: Option<String>,
    producer: bool,
) {
    let body = if producer {
        let value = if response.status == 202 {
            serde_json::json!({"job_id":response.job_id,"recording_id":recording_id,"accepted":true,"source_paths_released":true})
        } else {serde_json::json!({"recording_id":recording_id,"error":response.error.unwrap_or("internal_error"),"retryable":response.retryable,"retry_after_seconds":if response.status==429 {Some(1)} else {None},"source_paths_released":false})};
        serde_json::to_vec(&value)
    } else {serde_json::to_vec(response)}.expect("fixed response serialization");
    let allow = if producer && response.status == 405 {
        "Allow: POST\r\n"
    } else {
        ""
    };
    let head = format!(
        "HTTP/1.1 {} Result\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n{}{}\r\n",
        response.status,
        body.len(),
        allow,
        if producer && response.status == 429 {
            "Retry-After: 1\r\n"
        } else {
            ""
        }
    );
    let _ = timeout(Duration::from_secs(2), async {
        stream.write_all(head.as_bytes()).await?;
        stream.write_all(&body).await?;
        stream.flush().await?;
        stream.shutdown().await
    })
    .await;
}
/// Run before payload bootstrap. Caller retains the guard through Store shutdown.
/// Local lifetime metadata may be written; job data is inspected read-only.
pub fn check_state_compatibility(
    c: &Config,
    instance: &mover_fs::InstanceGuard,
    initialize: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    instance.validate_database(&c.state_database)?;
    instance.prepare_workers()?;
    Store::check_compatibility(&c.state_database, initialize)?;
    if Path::new(&c.state_database).try_exists()?
        && (!initialize || std::fs::metadata(&c.state_database)?.len() != 0)
    {
        let snapshot = mover_store::StateInspection::open(&c.state_database)?;
        mover_fs::validate_inspected_state(&snapshot)?;
        if snapshot.summary().retained_jobs > 0 && snapshot.enrollment()?.is_none() {
            return Err(StoreError::SourceEnrollmentRequired.into());
        }
        snapshot.visit_jobs(|job, _, _| {
            if job.context.destination_binding.is_none() {
                return Err(StoreError::DestinationEnrollmentRequired);
            }
            if job.recording.submission().producer().is_none()
                && job.recording.handoff() != Handoff::Ready202
            {
                return Err(StoreError::UnsupportedIdentity);
            }
            Ok(())
        })?;
        if let Some(ingress) = &c.protected_ingress {
            for root in snapshot.payload_roots()? {
                ingress.validate_payload_root(&root)?;
            }
        }
        if let Some(ingress) = &c.native_ingress {
            for root in snapshot.payload_roots()? {
                ingress.validate_payload_root(&root)?;
            }
        }
        if let Some(ingress) = &c.admin_ingress {
            for root in snapshot.payload_roots()? {
                ingress.validate_payload_root(&root)?;
            }
        }
    }
    instance.validate_database(&c.state_database)?;
    Ok(())
}

/// Caller may bind port zero for tests. Reject non-loopback listeners/configs.
pub async fn serve(
    listener: TcpListener,
    c: Config,
    stop: Arc<AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    let lifecycle = control::Lifecycle::new(stop, c.shutdown_wait_seconds);
    serve_controlled(listener, c, lifecycle).await
}
pub async fn serve_controlled(
    listener: TcpListener,
    c: Config,
    lifecycle: Arc<control::Lifecycle>,
) -> Result<(), Box<dyn std::error::Error>> {
    if c.protected_ingress.is_some() || c.native_ingress.is_some() {
        return Err("TCP listener forbidden in protected ingress mode".into());
    }
    serve_inner(Some(listener), c, lifecycle).await
}
/// Global connection budget across producer, admin and private operator sockets.
const TOTAL_CONNECTIONS: usize = 8;
/// Global slots producer and admin TCP connections can never take together.
const OPERATOR_RESERVED: usize = 1;
/// Concurrent admin browser connections (each also needs a TLS executor slot,
/// shared with producer TLS; a full producer pool can still refuse admin).
const ADMIN_CONNECTIONS: usize = 4;
// Both the deadline watcher and TLS job retain admission and instance ownership.
struct TlsBudget {
    /// Request-budget permits; an admin connection that becomes an event stream
    /// returns them early (it then holds a stream permit instead).
    request: std::sync::Mutex<Option<RequestPermits>>,
    _guard: Arc<mover_fs::InstanceGuard>,
}
struct RequestPermits {
    _permit: tokio::sync::OwnedSemaphorePermit,
    /// Producer or admin audience permit, whichever admitted this connection.
    _producer_permit: Option<tokio::sync::OwnedSemaphorePermit>,
    /// Shared producer+admin network permit (keeps an operator slot free).
    _network_permit: Option<tokio::sync::OwnedSemaphorePermit>,
}
impl TlsBudget {
    fn new(
        permit: tokio::sync::OwnedSemaphorePermit,
        producer_permit: Option<tokio::sync::OwnedSemaphorePermit>,
        network_permit: Option<tokio::sync::OwnedSemaphorePermit>,
        guard: Arc<mover_fs::InstanceGuard>,
    ) -> Self {
        Self {
            request: std::sync::Mutex::new(Some(RequestPermits {
                _permit: permit,
                _producer_permit: producer_permit,
                _network_permit: network_permit,
            })),
            _guard: guard,
        }
    }
    fn release_request(&self) {
        self.request
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take();
    }
}
// Fields drop in declaration order, even when the future was never polled.
struct TlsJob {
    future: tls_executor::Job,
    _budget: Arc<TlsBudget>,
}
impl std::future::Future for TlsJob {
    type Output = ();
    fn poll(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<()> {
        self.get_mut().future.as_mut().poll(cx)
    }
}
struct HandshakeWatch {
    socket: Arc<std::net::TcpStream>,
    _budget: Arc<TlsBudget>,
    armed: bool,
}
impl Drop for HandshakeWatch {
    fn drop(&mut self) {
        if self.armed {
            let _ = self.socket.shutdown(std::net::Shutdown::Both);
        }
    }
}
// This guard is captured by the session's inner future, including before its
// first poll. Wire exclusion precedes removing the old session registration.
struct CloseTlsWire(Arc<std::net::TcpStream>);
impl Drop for CloseTlsWire {
    fn drop(&mut self) {
        let _ = self.0.shutdown(std::net::Shutdown::Both);
    }
}

async fn serve_inner(
    listener: Option<TcpListener>,
    c: Config,
    lifecycle: Arc<control::Lifecycle>,
) -> Result<(), Box<dyn std::error::Error>> {
    let stop = lifecycle.stop.clone();
    if listener
        .as_ref()
        .is_some_and(|l| l.local_addr().is_ok_and(|a| !a.ip().is_loopback()))
    {
        return Err("loopback listener required".into());
    }
    c.validate()?;
    if stop.load(Ordering::Relaxed) {
        return Ok(());
    }
    let (ready, startup) = oneshot::channel();
    let startup_lifecycle = lifecycle.clone();
    let startup_config = c.clone();
    let startup_stop = stop.clone();
    let supervisor = std::thread::Builder::new()
        .name("mover-source-bootstrap".into())
        .spawn(move || {
            let result = (|| {
                let instance = Arc::new(
                    mover_fs::InstanceGuard::for_database(&startup_config.state_database)
                        .map_err(|e| e.to_string())?,
                );
                let control = control::Server::start(instance.clone(), startup_lifecycle.clone())
                    .map_err(|e| e.to_string())?;
                // Reject known unsafe endpoint names before SQLite can create
                // read-coordination sidecars. Local I/O retains epoch coverage;
                // the independent lifecycle controller is already available.
                let endpoint_plan = if let Some(ingress) = &startup_config.protected_ingress {
                    instance.prepare_workers().map_err(|e| e.to_string())?;
                    Some(
                        ingress::Planned::prepare(ingress)
                            .map_err(|e| format!("protected_ingress: {e}"))?,
                    )
                } else {
                    None
                };
                let native_plan = if let Some(ingress) = &startup_config.native_ingress {
                    instance.prepare_workers().map_err(|e| e.to_string())?;
                    Some(
                        mover_fs::ingress::SocketPlan::operator(ingress.operator_socket())
                            .map_err(|e| format!("native_ingress.operator_socket: {e}"))?,
                    )
                } else {
                    None
                };
                let reload_plan = reload::plan(&startup_config).map_err(|e| e.to_string())?;
                check_state_compatibility(&startup_config, &instance, false)
                    .map_err(|e| e.to_string())?;
                let native_policy = startup_config
                    .native_ingress
                    .as_ref()
                    .map(native::NativeIngress::load)
                    .transpose()
                    .map_err(|e| e.to_string())?
                    .flatten();
                let native = native_plan
                    .map(|plan| {
                        native::Prepared::bind(&startup_config, plan, native_policy, reload_plan)
                    })
                    .transpose()
                    .map_err(|e| e.to_string())?;
                let endpoints = endpoint_plan
                    .map(ingress::Planned::bind)
                    .transpose()
                    .map_err(|e| e.to_string())?;
                // Missing/invalid account or credentials refuse startup; there is
                // no setup form, default password or unauthenticated fallback.
                let admin_ingress = startup_config
                    .admin_ingress
                    .as_ref()
                    .map(|a| {
                        let record = account_cli::load_record(
                            &startup_config,
                            &instance,
                            &a.account_directory,
                        )
                        .map_err(|e| format!("admin_ingress.account_directory: {e}"))?;
                        admin::Prepared::load(&startup_config, a, record)
                    })
                    .transpose()
                    .map_err(|e| e.to_string())?;
                // Live password activation: host-local account control, only
                // with the dashboard (design: PASSWORD-ACTIVATION-DESIGN).
                let account_control = match (&admin_ingress, &startup_config.admin_ingress) {
                    (Some(prepared), Some(a)) => {
                        let (instance_id, excluded) =
                            account_cli::account_scope(&startup_config, &instance)
                                .map_err(|e| e.to_string())?;
                        Some(
                            account_ipc::Server::start(
                                instance.clone(),
                                prepared.admin(),
                                account_ipc::AccountScope {
                                    directory: a.account_directory.clone(),
                                    excluded,
                                    instance_id,
                                },
                                startup_stop.clone(),
                            )
                            .map_err(|e| format!("admin account control: {e}"))?,
                        )
                    }
                    _ => None,
                };
                let guard = bootstrap::acquire(
                    &startup_config.source_root,
                    &startup_config.source_binding,
                    &startup_stop,
                    &instance,
                )?;
                Ok((
                    guard,
                    control,
                    endpoints,
                    native,
                    admin_ingress,
                    account_control,
                ))
            })()
            .and_then(
                |(guard, control, endpoints, native, admin_ingress, account_control)| {
                    if startup_stop.load(Ordering::Relaxed) {
                        return Err("startup stopped".into());
                    }
                    let changes = admin_ingress.as_ref().map(admin::Prepared::changes);
                    Worker::start(
                        &startup_config,
                        guard,
                        startup_stop.clone(),
                        control,
                        changes,
                    )
                    .map(|worker| (worker, endpoints, native, admin_ingress, account_control))
                    .map_err(|e| e.to_string())
                },
            );
            let _ = ready.send(result);
        })?;
    let result = startup.await;
    supervisor
        .join()
        .map_err(|_| "source startup supervisor panicked")?;
    if stop.load(Ordering::Relaxed) {
        if let Ok(Ok((worker, _endpoints, native, admin_ingress, account_control))) = result {
            drop(_endpoints);
            drop(native);
            drop(account_control); // Joined before the guard goes.
            drop(admin_ingress); // Verifier never started; nothing to join.
            drop(worker);
        }
        return Ok(());
    }
    let (worker, prepared, native, admin_ingress, account_control) =
        result.map_err(|_| "source startup supervisor disconnected")??;
    let admin_ingress = admin_ingress.map(admin::Prepared::activate).transpose()?;
    let endpoints = prepared.map(ingress::Prepared::activate).transpose()?;
    let native = native
        .map(|p| p.activate(&c, lifecycle.clone(), worker._instance.clone()))
        .transpose()?;
    let tls_pool =
        if native.as_ref().is_some_and(|n| n.manager.is_some()) || admin_ingress.is_some() {
            Some(tls_executor::Pool::start(
                worker._instance.clone(),
                lifecycle.clone(),
            )?)
        } else {
            None
        };
    let permits = Arc::new(Semaphore::new(TOTAL_CONNECTIONS));
    let producer_permits = Arc::new(Semaphore::new(6));
    // Several independent browser connections, each counted in the global budget.
    let admin_permits = Arc::new(Semaphore::new(ADMIN_CONNECTIONS));
    // Producer and admin TCP connections together leave one global slot that
    // only the private operator socket can use, whatever the network load.
    let network_permits = Arc::new(Semaphore::new(TOTAL_CONNECTIONS - OPERATOR_RESERVED));
    if let Some(manager) = native.as_ref().and_then(|n| n.manager.as_ref()) {
        manager.set_budget(producer_permits.clone());
    }
    lifecycle.phase("Running");
    if let Some(native) = &native {
        let admin_note = match &admin_ingress {
            Some(a) => format!(" and admin HTTPS {}", a.address()?),
            None => String::new(),
        };
        println!(
            "Ready on native producer {} and private operator socket{admin_note}",
            native.address()?
        );
    } else if let Some(listener) = &listener {
        println!("Ready on {}", listener.local_addr()?);
    } else {
        println!("Ready on protected local producer and operator sockets");
    }
    let c = Arc::new(c);
    let mut tasks = JoinSet::new();
    while !stop.load(Ordering::Relaxed) {
        while tasks.try_join_next().is_some() {}
        if let Some(endpoints) = &endpoints {
            endpoints.validate()?;
        }
        if let Some(native) = &native {
            native.validate()?;
        }
        if let Ok(accepted) = timeout(
            Duration::from_millis(100),
            ingress::accept(
                listener.as_ref(),
                endpoints.as_ref(),
                native.as_ref(),
                admin_ingress.as_ref(),
            ),
        )
        .await
        {
            let (mut stream, audience) = accepted?;
            let tls_deadline = tokio::time::Instant::now() + Duration::from_secs(5);
            if matches!(audience, ingress::Audience::Admin) {
                let (Some(bound), Some(pool)) = (admin_ingress.as_ref(), tls_pool.as_ref()) else {
                    continue;
                };
                // Permits precede TLS work; saturation refuses without plaintext.
                let Ok(admin_permit) = admin_permits.clone().try_acquire_owned() else {
                    drop(stream);
                    continue;
                };
                let Ok(network_permit) = network_permits.clone().try_acquire_owned() else {
                    drop(stream);
                    continue;
                };
                let Ok(permit) = permits.clone().try_acquire_owned() else {
                    drop(stream);
                    continue;
                };
                let ingress::Stream::Tcp(stream) = stream else {
                    continue;
                };
                let stream = stream.into_std()?;
                let socket = Arc::new(stream.try_clone()?);
                let close = CloseTlsWire(socket.clone());
                let budget = Arc::new(TlsBudget::new(
                    permit,
                    Some(admin_permit),
                    Some(network_permit),
                    worker._instance.clone(),
                ));
                let release = {
                    let budget = budget.clone();
                    move || budget.release_request()
                };
                let watch = HandshakeWatch {
                    socket,
                    _budget: budget.clone(),
                    armed: true,
                };
                let (handshake_done, handshake) = oneshot::channel();
                tasks.spawn(async move {
                    let mut watch = watch;
                    if matches!(
                        tokio::time::timeout_at(tls_deadline, handshake).await,
                        Ok(Ok(()))
                    ) {
                        watch.armed = false;
                    }
                });
                let admin = bound.admin.clone();
                let observer = worker.observer.as_ref().unwrap().clone();
                let future = Box::pin(async move {
                    let _close = close;
                    if tokio::time::Instant::now() >= tls_deadline {
                        return;
                    }
                    let Ok(stream) = tokio::net::TcpStream::from_std(stream) else {
                        return;
                    };
                    let Some(stream) = admin.accept(stream, tls_deadline).await else {
                        return;
                    };
                    let _ = handshake_done.send(());
                    admin::connection(stream, admin, observer, Box::new(release)).await;
                });
                let _ = pool.try_spawn(Box::pin(TlsJob {
                    future,
                    _budget: budget,
                }));
                continue;
            }
            let tls_manager = if matches!(audience, ingress::Audience::Native(_)) {
                native.as_ref().and_then(|n| n.manager.clone())
            } else {
                None
            };
            if !audience.authorized() {
                if !audience.producer() {
                    drop(stream);
                    continue;
                }
                let denied = error(403, "caller_not_authorized", false, None);
                let _ = timeout(
                    Duration::from_millis(100),
                    write_response(&mut stream, &denied, None, audience.producer()),
                )
                .await;
                continue;
            }
            let producer_permit = if audience.producer() {
                match (
                    producer_permits.clone().try_acquire_owned(),
                    network_permits.clone().try_acquire_owned(),
                ) {
                    (Ok(p), Ok(n)) => Some((p, n)),
                    _ => {
                        // No plaintext HTTP response before a TLS handshake.
                        if tls_manager.is_some() {
                            drop(stream);
                            continue;
                        }
                        let busy = error(429, "rate_limited", true, None);
                        let _ = timeout(
                            Duration::from_millis(100),
                            write_response(&mut stream, &busy, None, true),
                        )
                        .await;
                        continue;
                    }
                }
            } else {
                None
            };
            let (producer_permit, network_permit) = match producer_permit {
                Some((p, n)) => (Some(p), Some(n)),
                None => (None, None),
            };
            let Ok(permit) = permits.clone().try_acquire_owned() else {
                drop(stream);
                continue;
            };
            let c = c.clone();
            let sender = worker.sender.as_ref().unwrap().clone();
            let observer = worker.observer.as_ref().unwrap().clone();
            let admission = worker._source_space.handle.clone();
            if let Some(manager) = tls_manager {
                let ingress::Stream::Tcp(stream) = stream else {
                    continue;
                };
                // Unregister the main reactor before transferring the socket.
                let stream = stream.into_std()?;
                let socket = Arc::new(stream.try_clone()?);
                let close = CloseTlsWire(socket.clone());
                let budget = Arc::new(TlsBudget::new(
                    permit,
                    producer_permit,
                    network_permit,
                    worker._instance.clone(),
                ));
                let watch = HandshakeWatch {
                    socket,
                    _budget: budget.clone(),
                    armed: true,
                };
                let (handshake_done, handshake) = oneshot::channel();
                tasks.spawn(async move {
                    let mut watch = watch;
                    if matches!(
                        tokio::time::timeout_at(tls_deadline, handshake).await,
                        Ok(Ok(()))
                    ) {
                        watch.armed = false;
                    }
                    // An armed drop also shuts down on cancellation or failed dispatch.
                    // This is transport exclusion, never proof that CPU work exited.
                });
                let future = Box::pin(async move {
                    // Never construct/poll TLS or timers for an expired queued job.
                    if tokio::time::Instant::now() >= tls_deadline {
                        return;
                    }
                    let Ok(stream) = tokio::net::TcpStream::from_std(stream) else {
                        return;
                    };
                    let stream = ingress::Stream::Tcp(stream);
                    // Raw queued transports capture no old policy or authority.
                    let Some((policy, session)) = manager.session() else {
                        return;
                    };
                    let lease = session.lease();
                    session
                        .run(async move {
                            let _close = close;
                            if mover_fs::qualification_tls_cpu_hold().is_err() || !lease.current() {
                                return;
                            }
                            let Some((stream, audience, peer)) =
                                policy.accept(stream, tls_deadline).await
                            else {
                                return;
                            };
                            let _ = handshake_done.send(());
                            lease.set_peer(peer);
                            drop(policy);
                            connection(
                                stream,
                                c,
                                sender,
                                observer,
                                admission,
                                audience,
                                Some(lease),
                            )
                            .await;
                        })
                        .await;
                });
                // Nonblocking dispatch. Failure drops the transport and all permits.
                let _ = tls_pool
                    .as_ref()
                    .expect("HTTPS executor")
                    .try_spawn(Box::pin(TlsJob {
                        future,
                        _budget: budget,
                    }));
            } else {
                tasks.spawn(async move {
                    let _permit = permit;
                    let _producer_permit = producer_permit;
                    let _network_permit = network_permit;
                    connection(stream, c, sender, observer, admission, audience, None).await;
                });
            }
        }
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    drop(tls_pool); // Join actual TLS executor exit while control/guard remain owned.
    // A timed-out password verifier may still run; join it before the guard goes.
    if let Some(bound) = &admin_ingress
        && let Some(verifier) = bound.admin.sessions.shutdown()
    {
        let _ = verifier.join();
    }
    // The account thread (a publication may be in progress) is joined while the
    // instance guard is still owned.
    drop(account_control);
    drop(admin_ingress);
    drop(endpoints);
    drop(native);
    drop(worker); // Local effects may finish; shutdown does not cancel syscalls.
    Ok(())
}

#[cfg(test)]
mod history_tests {
    #[test]
    fn retry_epoch_is_null_unless_delivery_review_is_eligible() {
        use super::retry_review_epoch as e;
        // Ready job, then the same stored epoch after reaching delivery review.
        assert_eq!(e(true, false, None, 0), None);
        assert_eq!(e(true, false, Some(2), 0), None);
        assert_eq!(e(true, false, Some(3), 0), Some(0));
        assert_eq!(e(true, false, Some(3), 7), Some(7));
        assert_eq!(e(false, false, Some(3), 0), None);
        assert_eq!(e(true, true, Some(3), 0), None);
        assert_eq!(e(true, false, Some(3), 64), None);
    }

    #[test]
    fn history_cursor_encodes_order() {
        assert_eq!(super::history_cursor("ab12", false, 7), "c1.ab12.a.7");
        assert_eq!(super::history_cursor("ab12", true, 7), "c1.ab12.d.7");
    }
    #[test]
    fn draining_custody_waits_for_its_last_user_then_reacquires() {
        use std::os::unix::fs::PermissionsExt;
        let base = std::env::temp_dir().join(format!("fm-custody-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir(&base).unwrap();
        std::fs::set_permissions(&base, std::fs::Permissions::from_mode(0o700)).unwrap();
        let area = base.join(".file-mover");
        std::fs::create_dir(&area).unwrap();
        std::fs::set_permissions(&area, std::fs::Permissions::from_mode(0o700)).unwrap();
        let lock_file = area.join(mover_fs::COORDINATOR_LOCK);
        std::fs::write(&lock_file, b"").unwrap();
        std::fs::set_permissions(&lock_file, std::fs::Permissions::from_mode(0o600)).unwrap();
        let path = base.to_str().unwrap();
        let custody = super::SharedCustody::default();
        let lock = std::sync::Arc::new(mover_fs::LocalClaimLock::acquire(path).unwrap());
        custody.held().insert(path.into(), (lock, false));
        // Jobs A and B deliver with the shared custody.
        let super::Current::Usable(a) = custody.current(path) else {
            panic!()
        };
        let super::Current::Usable(b) = custody.current(path) else {
            panic!()
        };
        // A fails: the custody drains instead of disappearing while B uses it.
        custody.forget(&a);
        drop(a);
        // Job C must wait: acquiring now would collide with B's description.
        assert!(matches!(custody.current(path), super::Current::Draining));
        assert!(mover_fs::LocalClaimLock::acquire(path).is_err());
        // B exits: the drained custody is released and C reacquires.
        drop(b);
        assert!(matches!(custody.current(path), super::Current::Absent));
        assert!(mover_fs::LocalClaimLock::acquire(path).is_ok());
        std::fs::remove_dir_all(&base).unwrap();
    }
    #[test]
    fn active_jobs_track_each_worker_hold() {
        let jobs = super::ActiveJobs::default();
        let a = jobs.enter(7).expect("first worker enters");
        assert!(jobs.enter(7).is_none(), "one worker per job");
        let b = jobs.enter(8).expect("another job is independent");
        assert!(jobs.contains(7) && jobs.contains(8));
        drop(a);
        assert!(!jobs.contains(7) && jobs.contains(8));
        assert!(jobs.enter(7).is_some(), "free again after the hold ends");
        drop(b);
        assert!(!jobs.contains(8));
    }
}
