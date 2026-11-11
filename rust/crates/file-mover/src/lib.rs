//! Bounded loopback handoff and durable local recording delivery. No deletion.
pub mod account;
pub mod account_cli;
pub mod bootstrap;
pub mod claim_worker;
pub mod control;
pub mod delivery_worker;
mod diagnostic;
pub mod enrollment;
mod http;
pub mod ingress;
pub mod native;
pub mod password;
pub mod payload;
mod reload;
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
    pub generator_id: String,
    #[serde(default)]
    pub check_expected_sizes: bool,
    pub source_root: String,
    pub source_binding: mover_fs::SourceBinding,
    pub destination_root: String,
    pub destination_binding: mover_fs::DestinationBinding,
    pub state_database: String,
    #[serde(default = "retry_default")]
    pub missing_file_retry_window_seconds: u32,
    #[serde(default = "retained_jobs_default")]
    pub max_retained_jobs: u64,
    #[serde(default = "retained_bytes_default")]
    pub max_retained_bytes: u64,
    #[serde(default)]
    pub source_space_admission: source_space::Policy,
    #[serde(default = "shutdown_default")]
    pub shutdown_wait_seconds: u32,
}
fn shutdown_default() -> u32 {
    60
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
fn now() -> i64 {
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
                delete_source_after_commit: false,
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
    Retention(Option<i64>),
    Resume(i64, ResumeInput),
    ResetMissing(i64, MissingResetInput),
}
type OperatorWork = (Observation, oneshot::Sender<Response>);
struct Worker {
    sender: Option<mpsc::SyncSender<Work>>,
    thread: Option<std::thread::JoinHandle<()>>,
    delivery: Option<std::thread::JoinHandle<()>>,
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
    ) -> Result<Self, Box<dyn std::error::Error>> {
        c.validate()?;
        let mut guard = guard;
        let instance = guard.instance()?.clone();
        instance.validate()?;
        instance.prepare_database(&c.state_database)?;
        let store = Arc::new(Store::open(&c.state_database)?);
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
                    };
                    let _ = reply.send(response);
                }
            })?;
        let delivery_stop = stop.clone();
        let delivery_store = store.clone();
        let delivery_guard = guard.clone();
        let delivery = std::thread::Builder::new()
            .name("mover-local-delivery".into())
            .spawn(move || {
                while !delivery_stop.load(Ordering::Relaxed) {
                    if delivery_guard.instance().and_then(|g| g.validate()).is_err() {
                        delivery_stop.store(true, Ordering::Relaxed);
                        break;
                    }
                    match delivery_store.delivery_candidates(now(), 1) {
                        Ok(ids) => {
                            for id in ids {
                                if delivery_stop.load(Ordering::Relaxed) {
                                    break;
                                }
                                let result = delivery_worker::deliver(
                                    &delivery_store,
                                    id,
                                    &delivery_guard,
                                    &delivery_stop,
                                );
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
            })?;
        let (sender, receiver) = mpsc::sync_channel::<Work>(1);
        let claim_stop = stop.clone();
        let check_expected_sizes = c.check_expected_sizes;
        let thread = match std::thread::Builder::new()
            .name("mover-local-claim".into())
            .spawn(move || {
                while let Ok((submission, context, reply, lease)) = receiver.recv() {
                    if claim_stop.load(Ordering::Relaxed) {
                        let _ = reply.send(error(503, "service_stopping", true, None));
                        continue;
                    }
                    // Actual admission is serialized with policy activation, not
                    // with enqueue: a request can have waited behind blocked I/O.
                    let permit = match lease.as_ref().map(reload::Lease::admit).transpose() {
                        Ok(permit) => permit,
                        Err(()) => {
                            let _ = reply.send(error(403, "caller_not_authorized", false, None));
                            continue;
                        }
                    };
                    let result = process(
                        &store,
                        &guard,
                        &claim_stop,
                        &submission,
                        &context,
                        &admission,
                        check_expected_sizes,
                    );
                    if let Some(permit) = permit {
                        permit.finish(result.error != Some("source_space_unavailable"));
                    }
                    let _ = reply.send(result); // Lost response never rolls back a claim.
                }
            }) {
            Ok(thread) => thread,
            Err(error) => {
                stop.store(true, Ordering::Relaxed);
                let _ = delivery.join();
                return Err(error.into());
            }
        };
        Ok(Self {
            sender: Some(sender),
            thread: Some(thread),
            delivery: Some(delivery),
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
        if let Some(t) = self.delivery.take() {
            let _ = t.join();
        }
    }
}
fn claim_error(failure: mover_fs::ClaimError, id: i64) -> Response {
    match failure {
        mover_fs::ClaimError::OutcomeUncertain => error(503, "handoff_pending", true, Some(id)),
        mover_fs::ClaimError::ExpectedSizeMismatch => {
            error(409, "source_size_mismatch", false, Some(id))
        }
        mover_fs::ClaimError::Store(StoreError::AdmissionFull) => {
            error(503, "retention_capacity", true, Some(id))
        }
        mover_fs::ClaimError::Store(_) => error(503, "storage_unavailable", true, Some(id)),
        _ => error(409, "recording_blocked", false, Some(id)),
    }
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
        match store.claim_blocked(job.job_id, now()) {
            Ok(false) => (),
            Ok(true) => return error(409, "recording_blocked", false, Some(job.job_id)),
            Err(_) => return error(503, "storage_unavailable", true, Some(job.job_id)),
        }
        if let Err(e) = claim_worker::validate_existing(store, guard, stop, job.job_id, false) {
            return claim_error(e, job.job_id);
        }
        if check_expected_sizes
            && job
                .recording
                .submission()
                .producer()
                .is_some_and(|r| !r.expected_sizes_supplied())
        {
            return error(400, "invalid_submission", false, Some(job.job_id));
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
fn status_response(store: &Store, id: i64) -> Response {
    let snapshot = match store.status(id) {
        Ok(Some(s)) => s,
        Ok(None) => return error(404, "not_found", false, None),
        Err(_) => return error(503, "storage_unavailable", true, Some(id)),
    };
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
    let missing: Vec<_> = snapshot.missing.iter().map(|(i, deadline, blocked)| serde_json::json!({
        "file_id":i.to_string(),"deadline":deadline,"blocked":blocked,"deadline_elapsed":now()>=*deadline
    })).collect();
    let condition = if committed {
        "Committed"
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
    let mut response = Response {
        status: 200,
        job_id: Some(id.to_string()),
        state: Some(if committed {
            "Committed"
        } else if released {
            "Claimed"
        } else {
            "Accepted"
        }),
        source_paths_released: released,
        error: None,
        retryable: false,
        details: Some(
            serde_json::json!({"generator_id":recording.submission().generator_id(),"submission_id":recording.submission().submission_id(),
            "condition":condition,"review_epoch":snapshot.review_epoch,"missing_review_epoch":snapshot.missing_review_epoch,"manifest_phase":snapshot.manifest_phase,"source_cleanup_enabled":false,
            "latest_missing_reset":snapshot.latest_missing_reset.map(|a|serde_json::json!({"command_id":a.request.command_id,"review_epoch":a.request.review_epoch,"file_id":a.request.file_index.to_string(),"retry_window_seconds":a.request.retry_window_seconds,"actor":a.request.actor,"reason":a.request.reason,"recorded_at":a.recorded_at,"prior_deadline":a.prior_deadline,"prior_blocked":a.prior_blocked,"new_deadline":a.new_deadline})),
            "latest_resume":snapshot.latest_resume.map(|a|serde_json::json!({"command_id":a.command_id,"review_epoch":a.review_epoch,"actor":a.actor,"reason":a.reason,"recorded_at":a.recorded_at,"prior_retry_after":a.prior_retry_after,"prior_code":a.prior_code})),
            "files":files,"missing":missing,"delivery_retry":snapshot.delivery.map(|(failures,retry_after,code)|serde_json::json!({"failures":failures,"retry_after":retry_after,"code":code}))}),
        ),
    };
    if let Some(request) = recording.submission().producer() {
        let details = response
            .details
            .as_mut()
            .expect("status details")
            .as_object_mut()
            .expect("status object");
        details.remove("submission_id");
        details.insert(
            "recording_id".into(),
            serde_json::json!(request.recording_id().to_string()),
        );
    }
    response
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
        Err(_) => error(503, "storage_unavailable", true, Some(id)),
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
                                    Observation::Status(_) | Observation::Retention(_) => None,
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
// Both the deadline watcher and TLS job retain admission and instance ownership.
struct TlsBudget {
    _permit: tokio::sync::OwnedSemaphorePermit,
    _producer_permit: Option<tokio::sync::OwnedSemaphorePermit>,
    _guard: Arc<mover_fs::InstanceGuard>,
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
                    Some(ingress::Planned::prepare(ingress).map_err(|e| e.to_string())?)
                } else {
                    None
                };
                let native_plan = if let Some(ingress) = &startup_config.native_ingress {
                    instance.prepare_workers().map_err(|e| e.to_string())?;
                    Some(
                        mover_fs::ingress::SocketPlan::operator(ingress.operator_socket())
                            .map_err(|e| e.to_string())?,
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
                let guard = bootstrap::acquire(
                    &startup_config.source_root,
                    &startup_config.source_binding,
                    &startup_stop,
                    &instance,
                )?;
                Ok((guard, control, endpoints, native))
            })()
            .and_then(|(guard, control, endpoints, native)| {
                if startup_stop.load(Ordering::Relaxed) {
                    return Err("startup stopped".into());
                }
                Worker::start(&startup_config, guard, startup_stop.clone(), control)
                    .map(|worker| (worker, endpoints, native))
                    .map_err(|e| e.to_string())
            });
            let _ = ready.send(result);
        })?;
    let result = startup.await;
    supervisor
        .join()
        .map_err(|_| "source startup supervisor panicked")?;
    if stop.load(Ordering::Relaxed) {
        if let Ok(Ok((worker, _endpoints, native))) = result {
            drop(_endpoints);
            drop(native);
            drop(worker);
        }
        return Ok(());
    }
    let (worker, prepared, native) =
        result.map_err(|_| "source startup supervisor disconnected")??;
    let endpoints = prepared.map(ingress::Prepared::activate).transpose()?;
    let native = native
        .map(|p| p.activate(&c, lifecycle.clone(), worker._instance.clone()))
        .transpose()?;
    let tls_pool = if native.as_ref().is_some_and(|n| n.manager.is_some()) {
        Some(tls_executor::Pool::start(
            worker._instance.clone(),
            lifecycle.clone(),
        )?)
    } else {
        None
    };
    let permits = Arc::new(Semaphore::new(8));
    let producer_permits = Arc::new(Semaphore::new(6));
    if let Some(manager) = native.as_ref().and_then(|n| n.manager.as_ref()) {
        manager.set_budget(producer_permits.clone());
    }
    lifecycle.phase("Running");
    if let Some(native) = &native {
        println!(
            "Ready on native producer {} and private operator socket",
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
            ingress::accept(listener.as_ref(), endpoints.as_ref(), native.as_ref()),
        )
        .await
        {
            let (mut stream, audience) = accepted?;
            let tls_deadline = tokio::time::Instant::now() + Duration::from_secs(5);
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
                match producer_permits.clone().try_acquire_owned() {
                    Ok(p) => Some(p),
                    Err(_) => {
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
                let budget = Arc::new(TlsBudget {
                    _permit: permit,
                    _producer_permit: producer_permit,
                    _guard: worker._instance.clone(),
                });
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
                    connection(stream, c, sender, observer, admission, audience, None).await;
                });
            }
        }
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    drop(tls_pool); // Join actual TLS executor exit while control/guard remain owned.
    drop(endpoints);
    drop(native);
    drop(worker); // Local effects may finish; shutdown does not cancel syscalls.
    Ok(())
}
