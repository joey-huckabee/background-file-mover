//! One bounded payload child at a time. SQLite and publication stay in parent.
use mover_core::{ClaimIntent, ObjectIdentity, Transfer, TransferPhase};
use mover_fs::LocalClaimLock;
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::{fd::AsFd, unix::net::UnixStream},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const REQUEST_LIMIT: usize = 32768;
const REPLY_LIMIT: u64 = 2048;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Assignment {
    version: u32,
    job_id: i64,
    file_index: usize,
    attempt: i64,
    phase: i64,
    destination_root: String,
    relative_name: String,
    transfer_objects: [String; 5],
    sha256: Option<String>,
    source_root: String,
    source_name: String,
    private_name: String,
    claim_objects: [String; 4],
}
impl Assignment {
    fn new(t: &Transfer, c: &ClaimIntent) -> Self {
        Self {
            version: 1,
            job_id: t.job_id,
            file_index: t.file_index,
            attempt: t.attempt,
            phase: t.phase as i64,
            destination_root: t.destination_root.clone(),
            relative_name: t.relative_name.clone(),
            transfer_objects: [&t.root, &t.area, &t.parent, &t.staging_directory, &t.stage]
                .map(ObjectIdentity::encode),
            sha256: t.sha256.clone(),
            source_root: c.root_path.clone(),
            source_name: c.source_name.clone(),
            private_name: c.private_name.clone(),
            claim_objects: [&c.root, &c.parent, &c.area, &c.source].map(ObjectIdentity::encode),
        }
    }
    fn decode(self) -> Result<(Transfer, ClaimIntent)> {
        if self.version != 1
            || self.job_id <= 0
            || self.file_index >= 256
            || !(1..=100).contains(&self.attempt)
        {
            return Err("invalid payload assignment".into());
        }
        let phase = TransferPhase::decode(self.phase).ok_or("invalid phase")?;
        if !matches!(phase, TransferPhase::Intent | TransferPhase::Copied) {
            return Err("payload operation not permitted".into());
        }
        mover_core::FileSpec::new(&self.relative_name, None)
            .map_err(|_| "invalid relative filename")?;
        if self.private_name != format!("{}-{}", self.job_id, self.file_index) {
            return Err("invalid private claim name".into());
        }
        let objects = self
            .transfer_objects
            .iter()
            .map(|s| ObjectIdentity::decode(s).ok_or("invalid identity"))
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let claims = self
            .claim_objects
            .iter()
            .map(|s| ObjectIdentity::decode(s).ok_or("invalid identity"))
            .collect::<std::result::Result<Vec<_>, _>>()?;
        Ok((
            Transfer {
                job_id: self.job_id,
                file_index: self.file_index,
                attempt: self.attempt,
                destination_root: self.destination_root,
                relative_name: self.relative_name,
                root: objects[0].clone(),
                area: objects[1].clone(),
                parent: objects[2].clone(),
                staging_directory: objects[3].clone(),
                stage: objects[4].clone(),
                sha256: self.sha256,
                phase,
            },
            ClaimIntent {
                job_id: self.job_id,
                file_index: self.file_index,
                root_path: self.source_root,
                source_name: self.source_name,
                private_name: self.private_name,
                root: claims[0].clone(),
                parent: claims[1].clone(),
                area: claims[2].clone(),
                source: claims[3].clone(),
            },
        ))
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    version: u32,
    job_id: i64,
    file_index: usize,
    attempt: i64,
    phase: i64,
    stage: String,
    sha256: Option<String>,
}
// Do not abandon a live assignment, including after IPC/polling errors. A
// blocked wait can delay shutdown; it must not authorize a replacement worker.
struct Supervised(Child);
impl Drop for Supervised {
    fn drop(&mut self) {
        let _ = self.0.kill();
        // If reaping fails, preserve this assignment rather than treating an
        // error as proof of worker exit and dispatching another writer.
        while self.0.wait().is_err() {
            std::thread::sleep(Duration::from_millis(100));
        }
    }
}
pub(crate) fn run(
    t: &Transfer,
    c: &ClaimIntent,
    source: &LocalClaimLock,
    destination: &LocalClaimLock,
    stop: &AtomicBool,
) -> Result<Transfer> {
    if stop.load(Ordering::Relaxed) {
        return Err("payload dispatch stopped".into());
    }
    source.validate_path(&c.root_path)?;
    destination.validate_path(&t.destination_root)?;
    let bytes = serde_json::to_vec(&Assignment::new(t, c))?;
    if bytes.len() > REQUEST_LIMIT {
        return Err("payload assignment too large".into());
    }
    let (mut channel, child_channel) = UnixStream::pair()?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let mut child = Supervised(
        Command::new(std::env::current_exe()?)
            .arg("--internal-payload-worker")
            // These are directory descriptors, not data streams. Inherit the same
            // flock descriptions so coordinator death cannot release custody early.
            .stdin(Stdio::from(source.inherit()?))
            .stdout(Stdio::from(destination.inherit()?))
            .stderr(Stdio::from(std::os::fd::OwnedFd::from(child_channel)))
            .spawn()?,
    );
    channel.write_all(&bytes)?;
    channel.shutdown(std::net::Shutdown::Write)?;
    let mut terminating = false;
    let status = loop {
        if let Some(status) = child.0.try_wait()? {
            break status;
        }
        if stop.load(Ordering::Relaxed) && !terminating {
            child.0.kill()?;
            terminating = true;
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    if terminating || !status.success() {
        return Err("payload child exited without a usable receipt".into());
    }
    let mut bytes = Vec::new();
    channel.take(REPLY_LIMIT + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > REPLY_LIMIT {
        return Err("payload receipt too large".into());
    }
    let receipt: Receipt = serde_json::from_slice(&bytes)?;
    let expected_phase = match t.phase {
        TransferPhase::Intent => TransferPhase::Copied,
        TransferPhase::Copied => TransferPhase::Verified,
        _ => return Err("invalid payload phase".into()),
    };
    if receipt.version != 1
        || receipt.job_id != t.job_id
        || receipt.file_index != t.file_index
        || receipt.attempt != t.attempt
        || receipt.phase != expected_phase as i64
    {
        return Err("payload receipt does not match assignment".into());
    }
    let mut next = t.clone();
    next.stage = ObjectIdentity::decode(&receipt.stage).ok_or("invalid stage receipt")?;
    next.sha256 = receipt.sha256;
    next.phase = expected_phase;
    if t.phase == TransferPhase::Copied && (next.stage != t.stage || next.sha256 != t.sha256) {
        return Err("verification changed copy evidence".into());
    }
    source.validate()?;
    destination.validate()?;
    Ok(next)
}

/// Internal mode: one filesystem assignment over a private socket, no SQLite.
pub fn worker() -> Result<()> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel)
        .take(REQUEST_LIMIT as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > REQUEST_LIMIT {
        return Err("payload assignment too large".into());
    }
    let (t, c) = serde_json::from_slice::<Assignment>(&bytes)?.decode()?;
    mover_fs::validate_payload_locks(&c.root_path, &t.destination_root)?;
    let next = match t.phase {
        TransferPhase::Intent => mover_fs::copy_effect(&t, &c)?,
        TransferPhase::Copied => mover_fs::verify_effect(&t, &c)?,
        _ => return Err("invalid payload phase".into()),
    };
    let reply = serde_json::to_vec(&Receipt {
        version: 1,
        job_id: next.job_id,
        file_index: next.file_index,
        attempt: next.attempt,
        phase: next.phase as i64,
        stage: next.stage.encode(),
        sha256: next.sha256,
    })?;
    if reply.len() as u64 > REPLY_LIMIT {
        return Err("payload receipt too large".into());
    }
    channel.write_all(&reply)?;
    Ok(())
}
