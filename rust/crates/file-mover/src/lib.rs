//! Bounded loopback handoff and durable local recording delivery. No deletion.
mod http;
pub mod payload;
use mover_core::{DeliveryPolicy, FileSpec, Handoff, ProtocolError, Submission};
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
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::{Semaphore, oneshot},
    task::JoinSet,
    time::timeout,
};

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub bind: SocketAddr,
    pub generator_id: String,
    pub source_root: String,
    pub destination_root: String,
    pub state_database: String,
    #[serde(default = "retry_default")]
    pub missing_file_retry_window_seconds: u32,
    #[serde(default = "retained_jobs_default")]
    pub max_retained_jobs: u64,
    #[serde(default = "retained_bytes_default")]
    pub max_retained_bytes: u64,
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
        if !self.bind.ip().is_loopback()
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
        Ok(())
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    generator_id: String,
    submission_id: String,
    source_path: String,
    files: Vec<InputFile>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InputFile {
    name: String,
    #[serde(default, deserialize_with = "optional_size")]
    size_bytes: Option<u64>,
}
fn optional_size<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Option<u64>, D::Error> {
    u64::deserialize(d).map(Some)
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
    let input: Input =
        serde_json::from_slice(body).map_err(|_| error(400, "invalid_json", false, None))?;
    if input.generator_id != c.generator_id {
        return Err(error(403, "unknown_generator", false, None));
    }
    if input.submission_id.len() > 128
        || input.generator_id.len() > 128
        || input.files.len() > 256
        || !absolute(&input.source_path)
    {
        return Err(error(400, "invalid_submission", false, None));
    }
    let relative = Path::new(&input.source_path)
        .strip_prefix(&c.source_root)
        .map_err(|_| error(403, "source_outside_scope", false, None))?
        .to_str()
        .ok_or_else(|| error(400, "invalid_submission", false, None))?
        .to_owned();
    let files = input
        .files
        .into_iter()
        .map(|f| FileSpec::new(f.name, f.size_bytes))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| error(400, "invalid_file_paths", false, None))?;
    let submission = Submission::new(
        input.generator_id,
        input.submission_id,
        input.source_path,
        files,
    )
    .map_err(|_| error(400, "invalid_submission", false, None))?;
    Ok((
        submission,
        AcceptanceContext {
            source_root_id: "local-source".into(),
            source_root_path: c.source_root.clone(),
            source_relative_directory: relative,
            destination_path: c.destination_root.clone(),
            missing_retry_seconds: c.missing_file_retry_window_seconds,
            policy: DeliveryPolicy {
                destination_id: "configured-local".into(),
                group_by_generator: false,
                delete_source_after_commit: false,
            },
        },
    ))
}
type Work = (Submission, AcceptanceContext, oneshot::Sender<Response>);
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
}
impl Worker {
    fn start(c: &Config) -> Result<Self, Box<dyn std::error::Error>> {
        c.validate()?;
        let guard = Arc::new(mover_fs::LocalClaimLock::acquire(&c.source_root)?);
        let store = Arc::new(Store::open(&c.state_database)?);
        store.configure_limits(c.max_retained_jobs, c.max_retained_bytes)?;
        let (observer, observations) = mpsc::sync_channel::<OperatorWork>(8);
        let observation_store = store.clone();
        let observation = std::thread::Builder::new()
            .name("mover-status".into())
            .spawn(move || {
                while let Ok((work, reply)) = observations.recv() {
                    let response = match work {
                        Observation::Status(id) => status_response(&observation_store, id),
                        Observation::Retention(id) => retention_response(&observation_store, id),
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
        let stop = Arc::new(AtomicBool::new(false));
        let delivery_stop = stop.clone();
        let delivery_store = store.clone();
        let delivery_guard = guard.clone();
        let delivery = std::thread::Builder::new()
            .name("mover-local-delivery".into())
            .spawn(move || {
                while !delivery_stop.load(Ordering::Relaxed) {
                    match delivery_store.delivery_candidates(now(), 1) {
                        Ok(ids) => {
                            for id in ids {
                                if delivery_stop.load(Ordering::Relaxed) {
                                    break;
                                }
                                let unavailable =
                                    delivery_store.get(id).ok().flatten().is_some_and(|job| {
                                        mover_fs::destination_unavailable(
                                            &job.context.destination_path,
                                        )
                                    });
                                if unavailable {
                                    if let Err(error) = delivery_store.delivery_deferred(id, now())
                                    {
                                        eprintln!("Delivery deferral persistence failed: {error}");
                                        delivery_stop.store(true, Ordering::Relaxed);
                                    }
                                    continue;
                                }
                                if let Err(error) = mover_fs::deliver_recording_with_payload(
                                    &delivery_store,
                                    id,
                                    &delivery_guard,
                                    |t, intent, destination| {
                                        payload::run(
                                            t,
                                            intent,
                                            &delivery_guard,
                                            destination,
                                            &delivery_stop,
                                        )
                                    },
                                ) {
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
        let thread = match std::thread::Builder::new()
            .name("mover-local-claim".into())
            .spawn(move || {
                while let Ok((submission, context, reply)) = receiver.recv() {
                    let result = process(&store, &guard, &submission, &context);
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
        })
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
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
fn process(
    store: &Store,
    guard: &mover_fs::LocalClaimLock,
    s: &Submission,
    c: &AcceptanceContext,
) -> Response {
    if guard.validate().is_err() {
        return error(409, "recording_blocked", false, None);
    }
    let mut job = match store.accept(s, c) {
        Ok(j) => j,
        Err(StoreError::Protocol(
            ProtocolError::ConflictingReplay | ProtocolError::DifferentSubmission,
        )) => return error(409, "submission_conflict", false, None),
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
        for i in 0..s.files().len() {
            match mover_fs::claim(store, job.job_id, i) {
                Ok(updated) => job = updated,
                Err(mover_fs::ClaimError::MissingSource) => {
                    return match store.note_missing(job.job_id, i, now()) {
                        Ok(false) => error(503, "handoff_pending", true, Some(job.job_id)),
                        Ok(true) => error(409, "recording_blocked", false, Some(job.job_id)),
                        Err(_) => error(503, "storage_unavailable", true, Some(job.job_id)),
                    };
                }
                Err(mover_fs::ClaimError::ExpectedSizeMismatch) => {
                    return error(409, "source_size_mismatch", false, Some(job.job_id));
                }
                Err(mover_fs::ClaimError::Store(StoreError::AdmissionFull)) => {
                    return error(503, "retention_capacity", true, Some(job.job_id));
                }
                Err(mover_fs::ClaimError::Store(_)) => {
                    return error(503, "storage_unavailable", true, Some(job.job_id));
                }
                Err(_) => return error(409, "recording_blocked", false, Some(job.job_id)),
            }
        }
    }
    if job.recording.handoff() != Handoff::Ready202 {
        return error(503, "handoff_pending", true, Some(job.job_id));
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
    Response {
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
async fn request(stream: &mut TcpStream) -> Result<http::Request, Response> {
    let mut bytes = Vec::new();
    let mut buffer = [0; 4096];
    loop {
        match http::frame(&bytes) {
            http::Frame::Complete(r) => return Ok(r),
            http::Frame::Reject(s) => return Err(error(s, "invalid_http", false, None)),
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
async fn connection(
    mut stream: TcpStream,
    c: Arc<Config>,
    sender: mpsc::SyncSender<Work>,
    observer: mpsc::SyncSender<OperatorWork>,
) {
    let response = match timeout(Duration::from_secs(5), request(&mut stream)).await {
        Err(_) => error(408, "request_timeout", true, None),
        Ok(Err(e)) => e,
        Ok(Ok(r)) => {
            if r.head.headers.get("host").is_none_or(|h| h.is_empty())
                || r.head.headers.contains_key("expect")
                || r.head.headers.contains_key("authorization")
            {
                error(400, "unsupported_headers", false, None)
            } else if r.head.method == "GET" && r.head.target == b"/healthz" && r.body.is_empty() {
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
                        if r.head.headers.get("idempotency-key").is_some_and(|key| {
                            key.as_slice() != submission.submission_id().as_bytes()
                        }) {
                            error(400, "idempotency_key_conflict", false, None)
                        } else {
                            let (reply, result) = oneshot::channel();
                            if sender.try_send((submission, context, reply)).is_err() {
                                error(503, "service_busy", true, None)
                            } else {
                                match timeout(Duration::from_secs(10), result).await {
                                    Ok(Ok(r)) => r,
                                    _ => error(503, "handoff_pending", true, None),
                                }
                            }
                        }
                    }
                }
            }
        }
    };
    let body = serde_json::to_vec(&response).expect("fixed response serialization");
    let head = format!(
        "HTTP/1.1 {} Result\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        response.status,
        body.len()
    );
    let _ = timeout(Duration::from_secs(2), async {
        stream.write_all(head.as_bytes()).await?;
        stream.write_all(&body).await?;
        stream.shutdown().await
    })
    .await;
}
/// Caller may bind port zero for tests. Reject non-loopback listeners/configs.
pub async fn serve(
    listener: TcpListener,
    c: Config,
    stop: Arc<AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    if !listener.local_addr()?.ip().is_loopback() {
        return Err("loopback listener required".into());
    }
    let worker = Worker::start(&c)?;
    let c = Arc::new(c);
    let permits = Arc::new(Semaphore::new(8));
    let mut tasks = JoinSet::new();
    while !stop.load(Ordering::Relaxed) {
        while tasks.try_join_next().is_some() {}
        if let Ok(accepted) = timeout(Duration::from_millis(100), listener.accept()).await {
            let (stream, _) = accepted?;
            let Ok(permit) = permits.clone().try_acquire_owned() else {
                drop(stream);
                continue;
            };
            let c = c.clone();
            let sender = worker.sender.as_ref().unwrap().clone();
            let observer = worker.observer.as_ref().unwrap().clone();
            tasks.spawn(async move {
                let _permit = permit;
                connection(stream, c, sender, observer).await;
            });
        }
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    drop(worker); // Local effects may finish; shutdown does not cancel syscalls.
    Ok(())
}
