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
        source_root: String,
        destination_root: String,
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
    version: u32,
    sequence: u64,
    transfer: Option<Assignment>,
    manifest: Option<ManifestReceipt>,
    error: Option<String>,
    diagnostic: Option<String>,
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
}
impl Session {
    fn start(guard: &LocalClaimLock) -> Result<Self> {
        let (channel, worker) = UnixStream::pair()?;
        channel.set_read_timeout(Some(Duration::from_millis(100)))?;
        channel.set_write_timeout(Some(Duration::from_secs(3)))?;
        let child = Supervised(
            Command::new(std::env::current_exe()?)
                .arg("--internal-delivery-worker")
                .stdin(Stdio::from(guard.inherit()?))
                .stdout(Stdio::from(guard.inherit()?))
                .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
                .spawn()?,
        );
        Ok(Self {
            child,
            channel,
            sequence: 0,
            source_authorization: guard.source_authorization().cloned(),
        })
    }
    fn read(&mut self, mut output: &mut [u8], stop: &AtomicBool) -> Result<()> {
        while !output.is_empty() {
            if stop.load(Ordering::Relaxed) {
                return Err("delivery dispatch stopped".into());
            }
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
        self.sequence += 1;
        let bytes = serde_json::to_vec(&Request {
            version: 1,
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
        if reply.version != 1 || reply.sequence != self.sequence {
            return Err("delivery receipt sequence mismatch".into());
        }
        if let Some(detail) = &reply.diagnostic {
            if reply.error.is_none()
                || reply.transfer.is_some()
                || reply.manifest.is_some()
                || !super::diagnostic::valid(detail)
            {
                return Err("invalid failure diagnostic".into());
            }
            eprintln!("Delivery worker sequence {}: {detail}", self.sequence);
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
pub(crate) fn deliver(
    store: &Store,
    id: i64,
    guard: &LocalClaimLock,
    stop: &AtomicBool,
) -> Result<bool> {
    let job = store.get(id)?.ok_or("unknown job")?;
    if job.recording.handoff() != Handoff::Ready202
        || job.context.policy.group_by_generator
        || !guard.matches_path(&job.context.source_root_path)
    {
        return Err("invalid delivery context".into());
    }
    let mut session = Session::start(guard)?;
    let opened = session.call(
        Operation::Open {
            job_id: id,
            source_root: job.context.source_root_path.clone(),
            destination_root: job.context.destination_path.clone(),
        },
        stop,
    )?;
    if opened.error.as_deref() == Some("destination_unavailable") {
        return Ok(false);
    }
    if opened.error.is_some() || opened.transfer.is_some() || opened.manifest.is_some() {
        return Err("destination custody unavailable".into());
    }
    for index in 0..job.recording.submission().files().len() {
        let c = claim(store, id, index)?;
        let existing = store.transfer(id, index)?;
        let mut t = match existing {
            Some(t) if t.phase == TransferPhase::Intent => {
                store.transfer_capacity(id, index)?;
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
                store.transfer_capacity(id, index)?;
                let mut template = if index > 0 {
                    store.transfer(id, 0)?.ok_or("missing recording anchor")?
                } else {
                    Transfer {
                        job_id: id,
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
        for (from, to) in [
            (TransferPhase::Intent, TransferPhase::Copied),
            (TransferPhase::Copied, TransferPhase::Verified),
            (TransferPhase::PublishIntent, TransferPhase::Published),
        ] {
            if t.phase == TransferPhase::Verified {
                let mut authorized = t.clone();
                authorized.phase = TransferPhase::PublishIntent;
                store.save_transfer(&authorized)?;
                t = authorized;
            }
            if t.phase == from {
                let next = session.transfer(
                    Operation::Payload {
                        assignment: Assignment::new(&t, &c),
                    },
                    &c,
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
        let checked = session.transfer(
            Operation::Custody {
                assignment: Assignment::new(&t, &c),
            },
            &c,
            stop,
        )?;
        if checked != t {
            return Err("custody receipt mismatch".into());
        }
    }
    // Recheck every published file before constructing the recording commitment.
    for index in 0..job.recording.submission().files().len() {
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
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut context: Option<(i64, String, LocalClaimLock)> = None;
    let mut source_authorization: Option<Option<mover_fs::SourceAuthorization>> = None;
    let mut sequence = 0;
    while let Some(bytes) = child_frame(&mut channel)? {
        let request: Request = serde_json::from_slice(&bytes)?;
        if request.version != 1 || request.sequence != sequence + 1 || request.sequence > 2048 {
            return Err("invalid delivery sequence".into());
        }
        sequence = request.sequence;
        if !matches!(request.command, Operation::Manifest { .. }) && bytes.len() > 32768 {
            return Err("delivery assignment too large".into());
        }
        let mut reply = Reply {
            version: 1,
            sequence,
            transfer: None,
            manifest: None,
            error: None,
            diagnostic: None,
        };
        let result = (|| -> Result<()> {
            if let Some(prior) = &source_authorization
                && prior != &request.source_authorization
            {
                return Err("source authorization assignment changed".into());
            }
            match request.command {
                Operation::Open {
                    job_id,
                    source_root,
                    destination_root,
                } => {
                    if context.is_some() || job_id <= 0 {
                        return Err("invalid open assignment".into());
                    }
                    mover_fs::validate_payload_locks(&source_root, &source_root)?;
                    if let Some(auth) = &request.source_authorization {
                        auth.validate(&source_root)?;
                    }
                    if mover_fs::destination_unavailable(&destination_root) {
                        reply.error = Some("destination_unavailable".into());
                        return Ok(());
                    }
                    let destination = LocalClaimLock::acquire(&destination_root)?;
                    destination.validate()?;
                    context = Some((job_id, source_root, destination));
                    source_authorization = Some(request.source_authorization.clone());
                }
                command => {
                    let (id, source, destination) =
                        context.as_ref().ok_or("delivery not opened")?;
                    mover_fs::validate_payload_locks(source, source)?;
                    if let Some(auth) = &request.source_authorization {
                        auth.validate(source)?;
                    }
                    destination.validate()?;
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
                    if t.job_id != *id
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
                                TransferPhase::Intent => mover_fs::copy_effect(&t, &c)?,
                                TransferPhase::Copied => mover_fs::verify_effect(&t, &c)?,
                                TransferPhase::PublishIntent => mover_fs::publish_effect(&t, &c)?,
                                _ => return Err("invalid payload phase".into()),
                            },
                            3 => mover_fs::published_custody_effect(&t, &c)?,
                            _ => return Err("invalid delivery operation".into()),
                        };
                        reply.transfer = Some(Assignment::new(&next, &c));
                    }
                    mover_fs::validate_payload_locks(source, source)?;
                    if let Some(auth) = &request.source_authorization {
                        auth.validate(source)?;
                    }
                    destination.validate()?;
                }
            }
            Ok(())
        })();
        if let Err(e) = result {
            reply.transfer = None;
            reply.manifest = None;
            reply.error = Some("blocked_or_uncertain".into());
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
