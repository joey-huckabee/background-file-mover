//! Legacy one-command filesystem worker and shared child supervision. No SQLite.
use mover_core::{ClaimIntent, ManifestRecord, ObjectIdentity, Transfer, TransferPhase};
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
const MANIFEST_LIMIT: usize = 393216;
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ManifestInput {
    job_id: i64,
    bytes: String,
    sha256: String,
    phase: i64,
    object: String,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Assignment {
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    manifest: Option<ManifestInput>,
}
impl Assignment {
    pub(crate) fn is_copy(&self) -> bool {
        self.phase == TransferPhase::Intent as i64
    }
    pub(crate) fn new(t: &Transfer, c: &ClaimIntent) -> Self {
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
            manifest: None,
        }
    }
    pub(crate) fn decode(self) -> Result<(Transfer, ClaimIntent, Option<ManifestRecord>)> {
        if self.version != 1
            || self.job_id <= 0
            || self.file_index >= 256
            || !(1..=100).contains(&self.attempt)
        {
            return Err("invalid payload assignment".into());
        }
        let phase = TransferPhase::decode(self.phase).ok_or("invalid phase")?;
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
        if phase != TransferPhase::Intent
            && (objects[4].size != claims[3].size
                || self.sha256.as_ref().is_none_or(|s| {
                    s.len() != 64
                        || !s
                            .bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                }))
        {
            return Err("invalid copied-file evidence".into());
        }
        let manifest = self
            .manifest
            .map(|m| -> Result<ManifestRecord> {
                Ok(ManifestRecord {
                    job_id: m.job_id,
                    bytes: m.bytes,
                    sha256: m.sha256,
                    phase: m.phase,
                    object: Some(
                        ObjectIdentity::decode(&m.object).ok_or("invalid manifest identity")?,
                    ),
                })
            })
            .transpose()?;
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
            manifest,
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
pub(crate) struct Supervised(pub(crate) Child);
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
pub(crate) fn exchange(
    bytes: &[u8],
    mode: &str,
    source: &LocalClaimLock,
    destination: &LocalClaimLock,
    stop: &AtomicBool,
    reply_limit: u64,
) -> Result<Vec<u8>> {
    if stop.load(Ordering::Relaxed) {
        return Err("worker dispatch stopped".into());
    }
    let (mut channel, child_channel) = UnixStream::pair()?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    let mut child = Supervised(
        Command::new(std::env::current_exe()?)
            .arg(mode)
            // These are directory descriptors, not data streams. Inherit the same
            // flock descriptions so coordinator death cannot release custody early.
            .stdin(Stdio::from(source.inherit()?))
            .stdout(Stdio::from(destination.inherit()?))
            .stderr(Stdio::from(std::os::fd::OwnedFd::from(child_channel)))
            .spawn()?,
    );
    channel.write_all(bytes)?;
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
    channel.take(reply_limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > reply_limit {
        return Err("payload receipt too large".into());
    }
    Ok(bytes)
}

/// Internal mode: one filesystem assignment over a private socket, no SQLite.
pub fn worker() -> Result<()> {
    let mut channel = UnixStream::from(std::io::stderr().as_fd().try_clone_to_owned()?);
    channel.set_read_timeout(Some(Duration::from_secs(3)))?;
    channel.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut bytes = Vec::new();
    (&mut channel)
        .take(MANIFEST_LIMIT as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > MANIFEST_LIMIT {
        return Err("payload assignment too large".into());
    }
    let assignment = serde_json::from_slice::<Assignment>(&bytes)?;
    if assignment.manifest.is_none() && bytes.len() > REQUEST_LIMIT {
        return Err("payload assignment too large".into());
    }
    let (t, c, manifest) = assignment.decode()?;
    mover_fs::validate_payload_locks(&c.root_path, &t.destination_root)?;
    let reply = if let Some(m) = manifest {
        let next = mover_fs::publish_manifest_effect(&t, &m)?;
        Receipt {
            version: 1,
            job_id: t.job_id,
            file_index: t.file_index,
            attempt: t.attempt,
            phase: next.phase,
            stage: next.object.ok_or("missing manifest object")?.encode(),
            sha256: Some(next.sha256),
        }
    } else {
        let next = match t.phase {
            TransferPhase::Intent => mover_fs::copy_effect(&t, &c)?,
            TransferPhase::Copied => mover_fs::verify_effect(&t, &c)?,
            TransferPhase::PublishIntent => mover_fs::publish_effect(&t, &c)?,
            _ => return Err("invalid payload phase".into()),
        };
        Receipt {
            version: 1,
            job_id: next.job_id,
            file_index: next.file_index,
            attempt: next.attempt,
            phase: next.phase as i64,
            stage: next.stage.encode(),
            sha256: next.sha256,
        }
    };
    let reply = serde_json::to_vec(&reply)?;
    if reply.len() as u64 > REPLY_LIMIT {
        return Err("payload receipt too large".into());
    }
    channel.write_all(&reply)?;
    Ok(())
}
