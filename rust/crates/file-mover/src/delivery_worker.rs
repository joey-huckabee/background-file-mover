//! One recording session: filesystem access in child, SQLite transitions in parent.
use super::payload::{Assignment, Supervised};
use mover_core::{ClaimIntent, Handoff, ManifestRecord, ObjectIdentity, Transfer, TransferPhase};
use mover_fs::LocalClaimLock;
use mover_store::Store;
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::{fd::AsFd, unix::net::UnixStream},
    process::{Command, Stdio},
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[derive(Debug)]
pub(crate) struct DestinationBindingRefused;
impl std::fmt::Display for DestinationBindingRefused {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("destination binding requires operator review")
    }
}
impl std::error::Error for DestinationBindingRefused {}
#[derive(Debug)]
pub(crate) struct DestinationCapacity;
impl std::fmt::Display for DestinationCapacity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("destination payload capacity backoff required")
    }
}
impl std::error::Error for DestinationCapacity {}
/// The job was cancelled; delivery stopped between steps. Not a failure.
#[derive(Debug)]
pub(crate) struct DeliveryCancelled;
impl std::fmt::Display for DeliveryCancelled {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("delivery stopped: job cancelled")
    }
}
impl std::error::Error for DeliveryCancelled {}
fn stop_if_cancelled(store: &Store, id: i64) -> Result<()> {
    if store.cancellation_requested(id)? {
        return Err(Box::new(DeliveryCancelled));
    }
    Ok(())
}
#[derive(Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum FailureClass {
    DestinationCapacity,
}
const LIMIT: usize = 393216;
const REPLY_LIMIT: usize = 32768;
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ManifestWire {
    job_id: i64,
    bytes: String,
    sha256: String,
    phase: i64,
    object: Option<String>,
}
impl ManifestWire {
    fn new(m: &ManifestRecord) -> Self {
        Self {
            job_id: m.job_id,
            bytes: m.bytes.clone(),
            sha256: m.sha256.clone(),
            phase: m.phase,
            object: m.object.as_ref().map(ObjectIdentity::encode),
        }
    }
    fn decode(self) -> Result<ManifestRecord> {
        Ok(ManifestRecord {
            job_id: self.job_id,
            bytes: self.bytes,
            sha256: self.sha256,
            phase: self.phase,
            object: self
                .object
                .map(|s| ObjectIdentity::decode(&s).ok_or("invalid manifest identity"))
                .transpose()?,
        })
    }
}
#[derive(Serialize, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
enum Operation {
    Open {
        job_id: i64,
        #[serde(default)]
        recording_directory: Option<String>,
        source_root: String,
        destination_root: String,
        #[serde(default)]
        destination_binding: Option<mover_fs::DestinationBinding>,
        #[serde(default)]
        destination_observation: Option<String>,
        /// The child's stdout is the coordinator's destination custody (shared
        /// delivery), adopted instead of acquiring a new lock.
        #[serde(default)]
        shared_destination: bool,
        /// Copy/verification buffer for this session (validated by the child).
        #[serde(default)]
        copy_buffer_bytes: Option<u64>,
    },
    Prepare {
        assignment: Assignment,
    },
    Restart {
        assignment: Assignment,
    },
    Payload {
        assignment: Assignment,
    },
    Custody {
        assignment: Assignment,
    },
    Manifest {
        assignment: Assignment,
        manifest: ManifestWire,
    },
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ManifestReceipt {
    job_id: i64,
    sha256: String,
    phase: i64,
    object: Option<String>,
}
impl ManifestReceipt {
    fn new(m: &ManifestRecord) -> Self {
        Self {
            job_id: m.job_id,
            sha256: m.sha256.clone(),
            phase: m.phase,
            object: m.object.as_ref().map(ObjectIdentity::encode),
        }
    }
    fn decode(self, bytes: &str) -> Result<ManifestRecord> {
        Ok(ManifestRecord {
            job_id: self.job_id,
            bytes: bytes.into(),
            sha256: self.sha256,
            phase: self.phase,
            object: self
                .object
                .map(|s| ObjectIdentity::decode(&s).ok_or("invalid manifest identity"))
                .transpose()?,
        })
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    version: u32,
    sequence: u64,
    command: Operation,
    #[serde(default)]
    source_authorization: Option<mover_fs::SourceAuthorization>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    destination_authorization: Option<mover_fs::DestinationAuthorization>,
    version: u32,
    sequence: u64,
    transfer: Option<Assignment>,
    manifest: Option<ManifestReceipt>,
    error: Option<String>,
    diagnostic: Option<String>,
    failure: Option<FailureClass>,
}
// This is a scheduling hint, never a receipt. Reject mixed or out-of-scope hints.
fn capacity_hint(reply: &Reply, copying: bool) -> Result<bool> {
    if reply.failure.is_none() {
        return Ok(false);
    }
    if !copying
        || reply.error.as_deref() != Some("blocked_or_uncertain")
        || reply.transfer.is_some()
        || reply.manifest.is_some()
        || reply.destination_authorization.is_some()
        || reply
            .diagnostic
            .as_ref()
            .is_none_or(|d| !super::diagnostic::valid(d))
    {
        return Err("invalid capacity failure hint".into());
    }
    Ok(true)
}
fn write_frame(stream: &mut UnixStream, bytes: &[u8], limit: usize) -> Result<()> {
    if bytes.len() > limit {
        return Err("worker frame too large".into());
    }
    stream.write_all(&(bytes.len() as u32).to_be_bytes())?;
    stream.write_all(bytes)?;
    Ok(())
}
fn child_frame(stream: &mut UnixStream) -> Result<Option<Vec<u8>>> {
    let mut header = [0; 4];
    let n = stream.read(&mut header[..1])?;
    if n == 0 {
        return Ok(None);
    }
    stream.read_exact(&mut header[1..])?;
    let length = u32::from_be_bytes(header) as usize;
    if length > LIMIT {
        return Err("worker frame too large".into());
    }
    let mut bytes = vec![0; length];
    stream.read_exact(&mut bytes)?;
    Ok(Some(bytes))
}
struct Session {
    child: Supervised,
    channel: UnixStream,
    sequence: u64,
    source_authorization: Option<mover_fs::SourceAuthorization>,
    /// Last validated child diagnostic (bounded, path-free).
    diagnostic: Option<String>,
    /// Coordinator end of the child's advisory progress channel.
    progress: std::os::fd::OwnedFd,
    job: i64,
    files: usize,
}

/// What went wrong in a failed delivery, for the job's problem record.
pub(crate) struct Problem {
    pub(crate) diagnostic: String,
    pub(crate) file: Option<usize>,
}
impl Session {
    /// `shared`: the coordinator's destination custody, passed as the child's
    /// stdout; otherwise stdout is the source custody again (legacy mode, where
    /// the child acquires the destination itself).
    fn start(
        guard: &LocalClaimLock,
        shared: Option<&LocalClaimLock>,
        job: i64,
        files: usize,
    ) -> Result<Self> {
        let (mut channel, worker) = UnixStream::pair()?;
        channel.set_read_timeout(Some(Duration::from_millis(100)))?;
        channel.set_write_timeout(Some(Duration::from_secs(3)))?;
        guard.instance()?.prepare_workers()?;
        let child = Supervised(
            Command::new(std::env::current_exe()?)
                .arg("--internal-delivery-worker")
                .stdin(Stdio::from(guard.inherit()?))
                .stdout(Stdio::from(shared.unwrap_or(guard).inherit()?))
                .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
                .spawn()?,
        );
        channel.set_read_timeout(Some(Duration::from_secs(3)))?;
        guard.instance()?.send(&mut channel)?;
        let (progress, child_end) = mover_fs::progress_pair()?;
        mover_fs::send_progress_channel(&channel, &child_end)?;
        drop(child_end);
        channel.set_read_timeout(Some(Duration::from_millis(100)))?;
        Ok(Self {
            child,
            channel,
            sequence: 0,
            source_authorization: guard.source_authorization().cloned(),
            diagnostic: None,
            progress,
            job,
            files,
        })
    }
    /// Live speed for the dashboard: take whatever progress the child sent
    /// while this coordinator waits for the step's reply.
    fn observe_progress(&self) {
        for update in mover_fs::drain_progress(&self.progress) {
            super::progress::BOARD.update(self.job, self.files, update);
        }
    }
    fn read(&mut self, mut output: &mut [u8], stop: &AtomicBool) -> Result<()> {
        while !output.is_empty() {
            if stop.load(Ordering::Relaxed) {
                return Err("delivery dispatch stopped".into());
            }
            self.observe_progress();
            match self.channel.read(output) {
                Ok(0) => return Err("delivery worker exited without receipt".into()),
                Ok(n) => {
                    output = &mut output[n..];
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::WouldBlock
                            | std::io::ErrorKind::TimedOut
                            | std::io::ErrorKind::Interrupted
                    ) =>
                {
                    if self.child.0.try_wait()?.is_some() {
                        return Err("delivery worker exited without receipt".into());
                    }
                }
                Err(e) => return Err(e.into()),
            }
        }
        Ok(())
    }
    fn call(&mut self, command: Operation, stop: &AtomicBool) -> Result<Reply> {
        if stop.load(Ordering::Relaxed) || self.sequence >= 2048 {
            return Err("delivery command budget stopped".into());
        }
        let copying = matches!(&command, Operation::Payload { assignment } if assignment.is_copy());
        self.sequence += 1;
        let bytes = serde_json::to_vec(&Request {
            version: 2,
            sequence: self.sequence,
            command,
            source_authorization: self.source_authorization.clone(),
        })?;
        write_frame(&mut self.channel, &bytes, LIMIT)?;
        let mut header = [0; 4];
        self.read(&mut header, stop)?;
        let length = u32::from_be_bytes(header) as usize;
        if length > REPLY_LIMIT {
            return Err("delivery receipt too large".into());
        }
        let mut bytes = vec![0; length];
        self.read(&mut bytes, stop)?;
        let reply: Reply = serde_json::from_slice(&bytes)?;
        if reply.version != 2 || reply.sequence != self.sequence {
            return Err("delivery receipt sequence mismatch".into());
        }
        let capacity = capacity_hint(&reply, copying)?;
        if let Some(detail) = &reply.diagnostic {
            if reply.error.is_none()
                || reply.transfer.is_some()
                || reply.manifest.is_some()
                || !super::diagnostic::valid(detail)
            {
                return Err("invalid failure diagnostic".into());
            }
            eprintln!("Delivery worker sequence {}: {detail}", self.sequence);
            self.diagnostic = Some(detail.clone());
        }
        if capacity {
            return Err(Box::new(DestinationCapacity));
        }
        if reply.error.as_deref() == Some("destination_binding_refused") {
            return Err(Box::new(DestinationBindingRefused));
        }
        Ok(reply)
    }
    fn transfer(
        &mut self,
        command: Operation,
        c: &ClaimIntent,
        stop: &AtomicBool,
    ) -> Result<Transfer> {
        let r = self.call(command, stop)?;
        if r.error.is_some() || r.manifest.is_some() {
            return Err("delivery effect uncertain or blocked".into());
        }
        let (t, returned, m) = r.transfer.ok_or("missing transfer receipt")?.decode()?;
        if returned != *c || m.is_some() {
            return Err("claim context changed in receipt".into());
        }
        Ok(t)
    }
}
fn claim(store: &Store, id: i64, index: usize) -> Result<ClaimIntent> {
    let (c, done) = store.claim_intent(id, index)?.ok_or("missing claim")?;
    if !done {
        return Err("claim incomplete".into());
    }
    Ok(c)
}
/// Returns false only for a confirmed unavailable destination, with no allocation.
/// Deliver one job. On failure `problem` receives the worker's diagnostic (or a
/// fixed code) and the file being processed, unless the service is stopping.
pub(crate) fn deliver(
    store: &Store,
    id: i64,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
    problem: &mut Option<Problem>,
    shared: Option<&LocalClaimLock>,
    tuning: Tuning,
) -> Result<bool> {
    // The job's live progress entry ends with this attempt.
    let _tracked = super::progress::Tracked(id);
    // Declared before the session so they drop after it: an unsaved attempt's
    // capacity stays reserved until its worker child has been killed and
    // reaped, not merely until the step that allocated it failed.
    let mut holds = Vec::new();
    let mut session = None;
    let mut file = None;
    let mut parallel_diagnostic = None;
    let result = deliver_steps(
        store,
        id,
        guard,
        stop,
        &mut session,
        &mut file,
        &mut holds,
        shared,
        tuning,
        &mut parallel_diagnostic,
    );
    if let Err(error) = &result
        && !stop.load(Ordering::Relaxed)
        && !error.is::<DeliveryCancelled>()
    {
        let diagnostic = parallel_diagnostic
            .or_else(|| {
                session
                    .as_mut()
                    .and_then(|s: &mut Session| s.diagnostic.take())
            })
            .unwrap_or_else(|| {
                if error.is::<DestinationBindingRefused>() {
                    "destination_binding_refused".into()
                } else {
                    super::diagnostic::describe(error.as_ref())
                }
            });
        *problem = Some(Problem { diagnostic, file });
    }
    result
}

/// Parallel files: stop here if a sibling has failed (a step boundary).
fn halt_point(halt: Option<&AtomicBool>) -> Result<()> {
    if halt.is_some_and(|h| h.load(Ordering::SeqCst)) {
        return Err(Box::new(Halted));
    }
    Ok(())
}
/// Per-delivery settings from the configuration.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Tuning {
    /// Files of one job copied at the same time (`delivery_file_concurrency`).
    pub(crate) files: usize,
    /// Copy and verification buffer bytes (`copy_buffer_bytes`).
    pub(crate) copy_buffer: usize,
}
/// A sibling file's session failed or the job must stop: this file stops
/// before its next step. Internal to parallel file delivery; never recorded.
#[derive(Debug)]
struct Halted;
impl std::fmt::Display for Halted {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("parallel file delivery halted")
    }
}
impl std::error::Error for Halted {}

/// Starts a session and opens the job's destination. `None` means the
/// destination is confirmed unavailable (a deferral, nothing allocated).
fn open_session(
    store: &Store,
    id: i64,
    job: &mover_store::Accepted,
    guard: &LocalClaimLock,
    shared: Option<&LocalClaimLock>,
    copy_buffer: usize,
    stop: &AtomicBool,
) -> Result<Option<Session>> {
    let mut session = Session::start(guard, shared, id, job.recording.submission().files().len())?;
    let opened = session.call(
        Operation::Open {
            job_id: id,
            recording_directory: Some(job.recording.submission().destination_component(id)),
            source_root: job.context.source_root_path.clone(),
            destination_root: job.context.destination_path.clone(),
            destination_binding: job
                .context
                .destination_binding
                .as_ref()
                .map(|b| serde_json::from_str(b))
                .transpose()?,
            destination_observation: store.destination_observation(id)?,
            shared_destination: shared.is_some(),
            copy_buffer_bytes: Some(copy_buffer as u64),
        },
        stop,
    )?;
    if opened.error.as_deref() == Some("destination_binding_refused") {
        return Err(Box::new(DestinationBindingRefused));
    }
    if opened.error.as_deref() == Some("destination_unavailable") {
        return Ok(None);
    }
    if opened.error.is_some() || opened.transfer.is_some() || opened.manifest.is_some() {
        return Err("destination custody unavailable".into());
    }
    if let Some(binding) = &job.context.destination_binding {
        let authorization = opened
            .destination_authorization
            .ok_or("missing destination authorization")?;
        if authorization.binding.encode() != *binding {
            return Err("destination receipt policy changed".into());
        }
        store.pin_destination(id, binding, &authorization.observation)?;
    } else if guard.source_authorization().is_some() {
        return Err("destination policy required".into());
    }
    Ok(Some(session))
}

/// The file's current attempt: the existing transfer, a restarted attempt
/// (new staging) for an unfinished one, or a first allocation. Files after the
/// first take their recording directory from file 0's transfer.
fn setup_file<'a>(
    store: &'a Store,
    id: i64,
    index: usize,
    job: &mover_store::Accepted,
    session: &mut Session,
    holds: &mut Vec<mover_store::CapacityHold<'a>>,
    stop: &AtomicBool,
) -> Result<(Transfer, ClaimIntent)> {
    stop_if_cancelled(store, id)?;
    let c = claim(store, id, index)?;
    let existing = store.transfer(id, index)?;
    let t = match existing {
        Some(t) if t.phase == TransferPhase::Intent => {
            holds.push(store.transfer_capacity(id, index)?);
            let next = session.transfer(
                Operation::Restart {
                    assignment: Assignment::new(&t, &c),
                },
                &c,
                stop,
            )?;
            let mut expected = t.clone();
            expected.attempt += 1;
            expected.stage = next.stage.clone();
            if next != expected {
                return Err("restart receipt mismatch".into());
            }
            store.save_transfer(&next)?;
            next
        }
        Some(t) => t,
        None => {
            holds.push(store.transfer_capacity(id, index)?);
            let mut template = if index > 0 {
                store.transfer(id, 0)?.ok_or("missing recording anchor")?
            } else {
                Transfer {
                    job_id: id,
                    recording_directory: job.recording.submission().destination_component(id),
                    file_index: index,
                    attempt: 1,
                    destination_root: job.context.destination_path.clone(),
                    relative_name: String::new(),
                    root: c.root.clone(),
                    area: c.root.clone(),
                    parent: c.root.clone(),
                    staging_directory: c.root.clone(),
                    stage: c.root.clone(),
                    sha256: None,
                    phase: TransferPhase::Intent,
                }
            };
            template.file_index = index;
            template.relative_name = job.recording.submission().files()[index]
                .relative_path()
                .into();
            template.attempt = 1;
            template.phase = TransferPhase::Intent;
            template.sha256 = None;
            let next = session.transfer(
                Operation::Prepare {
                    assignment: Assignment::new(&template, &c),
                },
                &c,
                stop,
            )?;
            if next.job_id != id
                || next.file_index != index
                || next.attempt != 1
                || next.destination_root != template.destination_root
                || next.recording_directory != template.recording_directory
                || next.relative_name != template.relative_name
                || next.phase != TransferPhase::Intent
                || next.sha256.is_some()
                || next.stage.size != 0
            {
                return Err("allocation receipt mismatch".into());
            }
            store.save_transfer(&next)?;
            next
        }
    };
    Ok((t, c))
}

/// Copy, verify and publish one file, then recheck its custody. `halt` (parallel
/// files only) stops before the next step once a sibling has failed.
fn advance_file(
    store: &Store,
    mut t: Transfer,
    c: &ClaimIntent,
    session: &mut Session,
    stop: &AtomicBool,
    halt: Option<&AtomicBool>,
) -> Result<()> {
    let halted = || halt_point(halt);
    for (from, to) in [
        (TransferPhase::Intent, TransferPhase::Copied),
        (TransferPhase::Copied, TransferPhase::Verified),
        (TransferPhase::PublishIntent, TransferPhase::Published),
    ] {
        // Before any effect or record of this step, PublishIntent included.
        halted()?;
        if t.phase == TransferPhase::Verified {
            let mut authorized = t.clone();
            authorized.phase = TransferPhase::PublishIntent;
            store.save_transfer(&authorized)?;
            t = authorized;
        }
        if t.phase == from {
            halted()?;
            let next = session.transfer(
                Operation::Payload {
                    assignment: Assignment::new(&t, c),
                },
                c,
                stop,
            )?;
            let mut expected = t.clone();
            expected.phase = to;
            if from == TransferPhase::Intent {
                expected.stage = next.stage.clone();
                expected.sha256 = next.sha256.clone();
            }
            if next != expected {
                return Err("payload receipt mismatch".into());
            }
            store.save_transfer(&next)?;
            t = next;
        }
    }
    halted()?;
    let checked = session.transfer(
        Operation::Custody {
            assignment: Assignment::new(&t, c),
        },
        c,
        stop,
    )?;
    if checked != t {
        return Err("custody receipt mismatch".into());
    }
    Ok(())
}

/// Why parallel file delivery stopped, carried out of a file thread (errors
/// themselves are not `Send`) and rebuilt with the same classification.
enum FileFailure {
    Deferred,
    Cancelled,
    BindingRefused,
    Capacity,
    Other(String),
}
impl FileFailure {
    fn of(error: &(dyn std::error::Error + 'static)) -> Self {
        if error.is::<DeliveryCancelled>() {
            Self::Cancelled
        } else if error.is::<DestinationBindingRefused>() {
            Self::BindingRefused
        } else if error.is::<DestinationCapacity>() {
            Self::Capacity
        } else {
            Self::Other(error.to_string())
        }
    }
    fn into_result(self) -> Result<bool> {
        match self {
            Self::Deferred => Ok(false),
            Self::Cancelled => Err(Box::new(DeliveryCancelled)),
            Self::BindingRefused => Err(Box::new(DestinationBindingRefused)),
            Self::Capacity => Err(Box::new(DestinationCapacity)),
            Self::Other(message) => Err(message.into()),
        }
    }
}

/// Files 0..n of one job, up to `concurrency` at a time, each thread with its
/// own session (child) on the shared destination custody. File 0's attempt is
/// set up first (it creates the recording directory) and handed over. The
/// first failure halts the other files before their next step; every thread,
/// its child and its capacity holds are finished before this returns (the
/// all-files barrier precedes any manifest step).
#[allow(clippy::too_many_arguments)]
fn deliver_files_parallel(
    store: &Store,
    id: i64,
    job: &mover_store::Accepted,
    guard: &LocalClaimLock,
    shared: &LocalClaimLock,
    stop: &AtomicBool,
    tuning: Tuning,
    first: (Transfer, ClaimIntent),
    failed: &mut Option<(FileFailure, Option<String>, Option<usize>)>,
) {
    let files = job.recording.submission().files().len();
    let next = std::sync::atomic::AtomicUsize::new(0);
    let first = std::sync::Mutex::new(Some(first));
    let halt = AtomicBool::new(false);
    let outcome = std::sync::Mutex::new(None);
    let fail = |failure: FileFailure, diagnostic: Option<String>, index: Option<usize>| {
        halt.store(true, Ordering::SeqCst);
        let mut slot = outcome.lock().unwrap_or_else(|e| e.into_inner());
        if slot.is_none() {
            *slot = Some((failure, diagnostic, index));
        }
    };
    std::thread::scope(|scope| {
        for worker in 0..tuning.files.min(files) {
            let spawned = std::thread::Builder::new()
                .name(format!("mover-delivery-file-{worker}"))
                .spawn_scoped(scope, || {
                    // Holds before the session: released only after its child exits.
                    let mut holds = Vec::new();
                    let mut session: Option<Session> = None;
                    loop {
                        if stop.load(Ordering::Relaxed) || halt.load(Ordering::SeqCst) {
                            return;
                        }
                        let index = next.fetch_add(1, Ordering::SeqCst);
                        if index >= files {
                            return;
                        }
                        let current = match &mut session {
                            Some(s) => s,
                            None => match open_session(
                                store,
                                id,
                                job,
                                guard,
                                Some(shared),
                                tuning.copy_buffer,
                                stop,
                            ) {
                                Ok(Some(s)) => session.insert(s),
                                Ok(None) => return fail(FileFailure::Deferred, None, None),
                                Err(e) => {
                                    return fail(FileFailure::of(e.as_ref()), None, Some(index));
                                }
                            },
                        };
                        let result = (|| -> Result<()> {
                            // Open may have finished after a sibling failed.
                            halt_point(Some(&halt))?;
                            let prepared = if index == 0 {
                                first.lock().unwrap_or_else(|e| e.into_inner()).take()
                            } else {
                                None
                            };
                            let (t, c) = match prepared {
                                Some(p) => p,
                                None => {
                                    setup_file(store, id, index, job, current, &mut holds, stop)?
                                }
                            };
                            advance_file(store, t, &c, current, stop, Some(&halt))
                        })();
                        if let Err(e) = result {
                            if !e.is::<Halted>() {
                                fail(
                                    FileFailure::of(e.as_ref()),
                                    current.diagnostic.take(),
                                    Some(index),
                                );
                            }
                            return;
                        }
                    }
                });
            if let Err(error) = spawned {
                // Resource exhaustion: no panic in the dispatcher; the started
                // siblings halt and are joined when the scope ends.
                fail(
                    FileFailure::Other(format!("delivery file thread unavailable: {error}")),
                    None,
                    None,
                );
                break;
            }
        }
    });
    *failed = outcome.into_inner().unwrap_or_else(|e| e.into_inner());
}

#[allow(clippy::too_many_arguments)]
fn deliver_steps<'a>(
    store: &'a Store,
    id: i64,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
    slot: &mut Option<Session>,
    file: &mut Option<usize>,
    holds: &mut Vec<mover_store::CapacityHold<'a>>,
    shared: Option<&LocalClaimLock>,
    tuning: Tuning,
    parallel_diagnostic: &mut Option<String>,
) -> Result<bool> {
    let job = store.get(id)?.ok_or("unknown job")?;
    if shared.is_some_and(|s| {
        !s.matches_path(&job.context.destination_path) || job.context.destination_binding.is_none()
    }) {
        return Err("shared destination custody scope mismatch".into());
    }
    stop_if_cancelled(store, id)?;
    if job.recording.handoff() != Handoff::Ready202
        || job.context.policy.group_by_generator
        || !guard.matches_path(&job.context.source_root_path)
    {
        return Err("invalid delivery context".into());
    }
    let Some(opened) = open_session(store, id, &job, guard, shared, tuning.copy_buffer, stop)?
    else {
        return Ok(false);
    };
    let session = slot.insert(opened);
    let files = job.recording.submission().files().len();
    match shared {
        // Several files at once: needs shared custody (every child adopts it).
        Some(shared) if tuning.files > 1 && files > 1 => {
            *file = Some(0);
            let first = setup_file(store, id, 0, &job, session, holds, stop)?;
            let mut failed = None;
            deliver_files_parallel(
                store,
                id,
                &job,
                guard,
                shared,
                stop,
                tuning,
                first,
                &mut failed,
            );
            if let Some((failure, diagnostic, index)) = failed {
                *file = index;
                *parallel_diagnostic = diagnostic;
                return failure.into_result();
            }
            if stop.load(Ordering::Relaxed) {
                return Err("delivery dispatch stopped".into());
            }
        }
        _ => {
            for index in 0..files {
                *file = Some(index);
                let (t, c) = setup_file(store, id, index, &job, session, holds, stop)?;
                advance_file(store, t, &c, session, stop, None)?;
            }
        }
    }
    // Recheck every published file before constructing the recording commitment.
    for index in 0..job.recording.submission().files().len() {
        *file = Some(index);
        stop_if_cancelled(store, id)?;
        let c = claim(store, id, index)?;
        let t = store.transfer(id, index)?.ok_or("missing published file")?;
        if session.transfer(
            Operation::Custody {
                assignment: Assignment::new(&t, &c),
            },
            &c,
            stop,
        )? != t
        {
            return Err("custody receipt mismatch".into());
        }
    }
    *file = None;
    stop_if_cancelled(store, id)?;
    let expected = mover_fs::expected_manifest(store, id)?;
    let mut m = match store.manifest(id)? {
        Some(m) => m,
        None => {
            store.save_manifest(&expected)?;
            expected.clone()
        }
    };
    if m.bytes != expected.bytes || m.sha256 != expected.sha256 {
        return Err("manifest context changed".into());
    }
    let anchor = store.transfer(id, 0)?.ok_or("missing anchor")?;
    let c = claim(store, id, 0)?;
    loop {
        let r = session.call(
            Operation::Manifest {
                assignment: Assignment::new(&anchor, &c),
                manifest: ManifestWire::new(&m),
            },
            stop,
        )?;
        if r.error.is_some() || r.transfer.is_some() {
            return Err("manifest effect uncertain or blocked".into());
        }
        let next = r
            .manifest
            .ok_or("missing manifest receipt")?
            .decode(&m.bytes)?;
        if next.job_id != m.job_id
            || next.bytes != m.bytes
            || next.sha256 != m.sha256
            || next.phase != if m.phase == 4 { 4 } else { m.phase + 1 }
            || (m.phase >= 2 && next.object != m.object)
        {
            return Err("manifest receipt mismatch".into());
        }
        if m.phase == 4 {
            if next != m {
                return Err("manifest custody changed".into());
            }
            break;
        }
        store.save_manifest(&next)?;
        m = next;
        if m.phase == 4 {
            break;
        }
    }
    Ok(true)
}
pub fn worker() -> Result<()> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let _instance = mover_fs::InstanceGuard::receive(&mut channel)?;
    // Advisory; reporting never waits or fails a step (see ProgressSender).
    let mut progress = mover_fs::receive_progress_channel(&channel)?;
    channel.set_read_timeout(None)?; // Preserve the existing session assignment wait.
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    // (job, recording directory, source root, destination custody, shared).
    // (job, recording directory, source root, destination custody, shared,
    // copy buffer bytes).
    let mut context: Option<(i64, String, String, LocalClaimLock, bool, usize)> = None;
    let mut source_authorization: Option<Option<mover_fs::SourceAuthorization>> = None;
    let mut sequence = 0;
    while let Some(bytes) = child_frame(&mut channel)? {
        _instance.validate()?;
        let request: Request = serde_json::from_slice(&bytes)?;
        if request.version != 2 || request.sequence != sequence + 1 || request.sequence > 2048 {
            return Err("invalid delivery sequence".into());
        }
        sequence = request.sequence;
        if !matches!(request.command, Operation::Manifest { .. }) && bytes.len() > 32768 {
            return Err("delivery assignment too large".into());
        }
        let mut reply = Reply {
            destination_authorization: None,
            version: 2,
            sequence,
            transfer: None,
            manifest: None,
            error: None,
            diagnostic: None,
            failure: None,
        };
        let mut checking_destination = false;
        let mut copying_payload = false;
        let result = (|| -> Result<()> {
            if let Some(prior) = &source_authorization
                && prior != &request.source_authorization
            {
                return Err("source authorization assignment changed".into());
            }
            match request.command {
                Operation::Open {
                    job_id,
                    recording_directory,
                    source_root,
                    destination_root,
                    destination_binding,
                    destination_observation,
                    shared_destination,
                    copy_buffer_bytes,
                } => {
                    if context.is_some() || job_id <= 0 {
                        return Err("invalid open assignment".into());
                    }
                    let copy_buffer = match copy_buffer_bytes {
                        None => mover_fs::DEFAULT_COPY_BUFFER,
                        Some(bytes) if mover_fs::valid_copy_buffer(bytes) => bytes as usize,
                        Some(_) => return Err("invalid copy buffer size".into()),
                    };
                    let component = recording_directory.unwrap_or_else(|| job_id.to_string());
                    if !mover_core::valid_recording_directory(job_id, &component) {
                        return Err("invalid recording scope".into());
                    }
                    mover_fs::validate_worker_source(
                        &source_root,
                        request.source_authorization.as_ref(),
                    )?;
                    if shared_destination && destination_binding.is_none() {
                        return Err("shared destination custody requires a binding".into());
                    }
                    // Shared mode: stdout is destination custody, checked once
                    // the destination is known to be available (below).
                    if shared_destination {
                        mover_fs::validate_source_lock(&source_root)?;
                    } else {
                        mover_fs::validate_payload_locks(&source_root, &source_root)?;
                    }
                    checking_destination = destination_binding.is_some();
                    if let (Some(source), Some(destination)) =
                        (&request.source_authorization, &destination_binding)
                        && source.binding.coordinator_id != destination.coordinator_id
                    {
                        return Err("destination coordinator binding mismatch".into());
                    }
                    let unavailable = match &destination_binding {
                        Some(binding) => binding.unavailable(&destination_root)?,
                        None => mover_fs::destination_unavailable(&destination_root),
                    };
                    if unavailable {
                        reply.error = Some("destination_unavailable".into());
                        return Ok(());
                    }
                    if request.source_authorization.is_some() && destination_binding.is_none() {
                        return Err("destination policy required".into());
                    }
                    let destination = match &destination_binding {
                        // The job's own binding and pin, against the shared custody.
                        Some(binding) if shared_destination => LocalClaimLock::adopt_destination(
                            &destination_root,
                            binding,
                            destination_observation.as_deref(),
                            std::io::stdout().as_fd().try_clone_to_owned()?,
                        )?,
                        Some(binding) => LocalClaimLock::acquire_destination(
                            &destination_root,
                            binding,
                            destination_observation.as_deref(),
                        )?,
                        None if destination_observation.is_none() => {
                            LocalClaimLock::acquire(&destination_root)?
                        }
                        None => return Err("destination observation without policy".into()),
                    };
                    destination.validate()?;
                    if shared_destination {
                        // Within the binding-refusal boundary (a binding is required).
                        mover_fs::validate_destination_lock(&destination_root)?;
                    }
                    reply.destination_authorization =
                        destination.destination_authorization().cloned();
                    context = Some((
                        job_id,
                        component,
                        source_root,
                        destination,
                        shared_destination,
                        copy_buffer,
                    ));
                    source_authorization = Some(request.source_authorization.clone());
                }
                command => {
                    let (id, component, source, destination, shared, copy_buffer) =
                        context.as_ref().ok_or("delivery not opened")?;
                    let copy_buffer = *copy_buffer;
                    // The descriptors this session was started with: stdout is
                    // the destination custody in shared mode (checked inside the
                    // binding-refusal boundary), the source otherwise.
                    let source_locks = |source: &str| {
                        if *shared {
                            mover_fs::validate_source_lock(source)
                        } else {
                            mover_fs::validate_payload_locks(source, source)
                        }
                    };
                    let destination_locks = || {
                        if *shared {
                            mover_fs::validate_destination_lock(destination.source_path())?;
                        }
                        destination.validate()
                    };
                    mover_fs::validate_worker_source(
                        source,
                        request.source_authorization.as_ref(),
                    )?;
                    source_locks(source)?;
                    checking_destination = true;
                    destination_locks()?;
                    checking_destination = false;
                    let (assignment, kind, manifest) = match command {
                        Operation::Prepare { assignment } => (assignment, 0, None),
                        Operation::Restart { assignment } => (assignment, 1, None),
                        Operation::Payload { assignment } => (assignment, 2, None),
                        Operation::Custody { assignment } => (assignment, 3, None),
                        Operation::Manifest {
                            assignment,
                            manifest,
                        } => (assignment, 4, Some(manifest)),
                        _ => unreachable!(),
                    };
                    let (t, c, embedded) = assignment.decode()?;
                    if t.recording_directory != *component
                        || t.job_id != *id
                        || c.job_id != *id
                        || t.file_index != c.file_index
                        || c.root_path != *source
                        || !destination.matches_path(&t.destination_root)
                        || embedded.is_some()
                    {
                        return Err("delivery assignment scope changed".into());
                    }
                    if let Some(m) = manifest {
                        let m = m.decode()?;
                        let next = mover_fs::manifest_step_effect(&t, &m)?;
                        reply.manifest = Some(ManifestReceipt::new(&next));
                    } else {
                        let next = match kind {
                            0 => mover_fs::prepare_transfer_effect(&t, &c)?,
                            1 => mover_fs::restart_transfer_effect(&t, &c)?,
                            2 => match t.phase {
                                TransferPhase::Intent => {
                                    copying_payload = true;
                                    let file_index =
                                        u32::try_from(t.file_index).unwrap_or(u32::MAX);
                                    let total = c.source.size;
                                    mover_fs::copy_effect_observed(
                                        &t,
                                        &c,
                                        copy_buffer,
                                        &mut |done| {
                                            progress.report(mover_fs::ProgressUpdate {
                                                file_index,
                                                phase: mover_fs::ProgressPhase::Copying,
                                                done,
                                                total,
                                            })
                                        },
                                    )?
                                }
                                TransferPhase::Copied => {
                                    let file_index =
                                        u32::try_from(t.file_index).unwrap_or(u32::MAX);
                                    let total = t.stage.size;
                                    mover_fs::verify_effect_observed(
                                        &t,
                                        &c,
                                        copy_buffer,
                                        &mut |done| {
                                            progress.report(mover_fs::ProgressUpdate {
                                                file_index,
                                                phase: mover_fs::ProgressPhase::Verifying,
                                                done,
                                                total,
                                            })
                                        },
                                    )?
                                }
                                TransferPhase::PublishIntent => mover_fs::publish_effect(&t, &c)?,
                                _ => return Err("invalid payload phase".into()),
                            },
                            3 => mover_fs::published_custody_effect(&t, &c)?,
                            _ => return Err("invalid delivery operation".into()),
                        };
                        reply.transfer = Some(Assignment::new(&next, &c));
                    }
                    mover_fs::validate_worker_source(
                        source,
                        request.source_authorization.as_ref(),
                    )?;
                    source_locks(source)?;
                    checking_destination = true;
                    destination_locks()?;
                }
            }
            Ok(())
        })();
        if let Err(e) = result {
            if !checking_destination
                && copying_payload
                && mover_fs::is_payload_capacity_failure(e.as_ref())
            {
                reply.failure = Some(FailureClass::DestinationCapacity);
            }
            reply.destination_authorization = None;
            reply.transfer = None;
            reply.manifest = None;
            reply.error = Some(
                if checking_destination {
                    "destination_binding_refused"
                } else {
                    "blocked_or_uncertain"
                }
                .into(),
            );
            reply.diagnostic = Some(super::diagnostic::describe(e.as_ref()));
        }
        let finish = reply.error.is_some();
        write_frame(&mut channel, &serde_json::to_vec(&reply)?, REPLY_LIMIT)?;
        if finish {
            break;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn a_halted_file_stops_before_recording_its_next_step() {
        let base = std::env::temp_dir().join(format!("fm-halt-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&base).unwrap();
        let store = Store::open(base.join("jobs.sqlite")).unwrap();
        let id = |inode| ObjectIdentity {
            device: 1,
            inode,
            uid: 1000,
            size: 0,
            modified_seconds: 1,
            modified_nanos: 0,
            links: 1,
        };
        let c = ClaimIntent {
            job_id: 1,
            file_index: 0,
            root_path: "/r".into(),
            source_name: "a".into(),
            private_name: "1-0".into(),
            root: id(1),
            parent: id(2),
            area: id(3),
            source: id(4),
        };
        let t = Transfer {
            job_id: 1,
            recording_directory: "1".into(),
            file_index: 0,
            attempt: 1,
            destination_root: "/d".into(),
            relative_name: "a".into(),
            root: id(5),
            area: id(6),
            parent: id(7),
            staging_directory: id(8),
            stage: id(9),
            sha256: Some("a".repeat(64)),
            phase: TransferPhase::Verified,
        };
        // A session whose child is never asked anything.
        let mut session = Session {
            child: Supervised(Command::new("sleep").arg("30").spawn().unwrap()),
            channel: UnixStream::pair().unwrap().0,
            sequence: 0,
            source_authorization: None,
            diagnostic: None,
            progress: mover_fs::progress_pair().unwrap().0,
            job: 1,
            files: 1,
        };
        let stop = AtomicBool::new(false);
        let halt = AtomicBool::new(true);
        // Verified -> PublishIntent would be persisted first; halted, nothing is.
        let error = advance_file(&store, t, &c, &mut session, &stop, Some(&halt)).unwrap_err();
        assert!(error.is::<Halted>());
        assert_eq!(store.transfer(1, 0).unwrap(), None);
        assert_eq!(session.sequence, 0, "no step was sent to the child");
        assert!(halt_point(Some(&halt)).unwrap_err().is::<Halted>());
        assert!(halt_point(None).is_ok());
        drop(session);
        let _ = std::fs::remove_dir_all(&base);
    }
    #[test]
    fn capacity_hints_reject_receipts_wrong_scope_and_unknown_classes_without_parsing_text() {
        let mut reply = Reply {
            destination_authorization: None,
            version: 2,
            sequence: 1,
            transfer: None,
            manifest: None,
            error: Some("blocked_or_uncertain".into()),
            diagnostic: Some("safe fixed detail".into()),
            failure: Some(FailureClass::DestinationCapacity),
        };
        assert!(capacity_hint(&reply, true).unwrap());
        assert!(capacity_hint(&reply, false).is_err());
        reply.error = None;
        assert!(capacity_hint(&reply, true).is_err());
        reply.error = Some("destination_binding_refused".into());
        assert!(capacity_hint(&reply, true).is_err());
        reply.error = Some("blocked_or_uncertain".into());
        reply.manifest = Some(ManifestReceipt {
            job_id: 1,
            sha256: "digest".into(),
            phase: 4,
            object: None,
        });
        assert!(capacity_hint(&reply, true).is_err());
        reply.manifest = None;
        reply.transfer = Some(serde_json::from_value(serde_json::json!({
            "version":1,"job_id":1,"file_index":0,"attempt":1,"phase":0,
            "destination_root":"root","relative_name":"data","transfer_objects":["x","x","x","x","x"],
            "sha256":null,"source_root":"source","source_name":"data","private_name":"1-0",
            "claim_objects":["x","x","x","x"]
        })).unwrap());
        assert!(capacity_hint(&reply, true).is_err());
        reply.transfer = None;
        let mut value = serde_json::to_value(&reply).unwrap();
        value["failure"] = serde_json::json!("unknown_retry_everything");
        assert!(serde_json::from_value::<Reply>(value).is_err());
        reply.diagnostic = None;
        assert!(capacity_hint(&reply, true).is_err());
        reply.failure = None;
        reply.diagnostic = Some("payload_copy_write errno=28".into());
        assert!(!capacity_hint(&reply, true).unwrap());
    }
}
