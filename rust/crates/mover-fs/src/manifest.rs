//! Exact immutable recording manifest; allocation/writing/publication receipts.
use super::*;
use mover_core::{ManifestRecord, TransferPhase};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom, Write},
};
type ManifestResult<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    version: u32,
    instance_id: String,
    job_id: String,
    generator_id: String,
    submission_id: String,
    files: Vec<Entry>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    file_id: String,
    path: String,
    size_bytes: u64,
    algorithm: String,
    sha256: String,
}

fn expected(store: &Store, id: i64) -> ManifestResult<(String, OwnedFd, OwnedFd)> {
    let job = store.get(id)?.ok_or("unknown recording")?;
    let mut files = Vec::new();
    let mut shared = None;
    for index in 0..job.recording.submission().files().len() {
        let t = store.transfer(id, index)?.ok_or("unpublished file")?;
        if t.phase != TransferPhase::Published {
            return Err("all files must be published".into());
        }
        super::transfer::claimed(store, id, index)?;
        let (_, area, staging, parent, name) = super::transfer::directories(&t)?;
        let fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
        if source(&fd)? != t.stage {
            return Err("published custody lost before commitment".into());
        }
        if index == 0 {
            shared = Some((area, staging));
        }
        files.push(Entry {
            file_id: index.to_string(),
            path: t.relative_name,
            size_bytes: t.stage.size,
            algorithm: "sha256".into(),
            sha256: t.sha256.ok_or("missing digest")?,
        });
    }
    let m = Manifest {
        version: 1,
        instance_id: store.instance_id()?,
        job_id: id.to_string(),
        generator_id: job.recording.submission().generator_id().into(),
        submission_id: job.recording.submission().submission_id().into(),
        files,
    };
    let bytes = serde_json::to_string(&m)?;
    if bytes.len() > 131072 {
        return Err("manifest limit exceeded".into());
    }
    let (area, staging) = shared.ok_or("empty recording")?;
    Ok((bytes, area, staging))
}
fn read_exact_manifest(fd: &mut File, m: &ManifestRecord) -> ManifestResult<()> {
    let before = source(fd)?;
    if Some(before.clone()) != m.object {
        return Err("manifest object changed".into());
    }
    let mut bytes = Vec::new();
    (&mut *fd).take(131073).read_to_end(&mut bytes)?;
    if bytes != m.bytes.as_bytes() || source(fd)? != before {
        return Err("manifest content mismatch".into());
    }
    // Strict schema, duplicate-field rejection, exact bytes and required set.
    let _: Manifest = serde_json::from_slice(&bytes)?;
    Ok(())
}
pub fn commit_manifest(store: &Store, id: i64) -> ManifestResult<ManifestRecord> {
    commit_manifest_with_checkpoints(store, id, |_| {})
}
/// Narrow effect-boundary observer for process-crash qualification.
pub fn commit_manifest_with_checkpoints(
    store: &Store,
    id: i64,
    mut checkpoint: impl FnMut(&'static str),
) -> ManifestResult<ManifestRecord> {
    commit_with_workers(store, id, &mut checkpoint, None)
}
type Publisher<'a> =
    &'a mut dyn FnMut(&mover_core::Transfer, &ManifestRecord) -> ManifestResult<ManifestRecord>;
pub fn commit_manifest_with_publication(
    store: &Store,
    id: i64,
    mut publication: impl FnMut(
        &mover_core::Transfer,
        &ManifestRecord,
    ) -> ManifestResult<ManifestRecord>,
) -> ManifestResult<ManifestRecord> {
    commit_with_workers(store, id, &mut |_| {}, Some(&mut publication))
}
fn commit_with_workers(
    store: &Store,
    id: i64,
    checkpoint: &mut impl FnMut(&'static str),
    publication: Option<Publisher<'_>>,
) -> ManifestResult<ManifestRecord> {
    let (bytes, area, staging) = expected(store, id)?;
    let sha256 = format!("{:x}", Sha256::digest(bytes.as_bytes()));
    let mut m = match store.manifest(id)? {
        Some(m) => m,
        None => {
            let m = ManifestRecord {
                job_id: id,
                bytes: bytes.clone(),
                sha256: sha256.clone(),
                phase: 0,
                object: None,
            };
            store.save_manifest(&m)?;
            m
        }
    };
    if m.bytes != bytes || m.sha256 != sha256 {
        return Err("recorded manifest differs from published set".into());
    }
    checkpoint("intent");
    if m.phase == 0 {
        let fd = fs::openat(
            &staging,
            "COMMITTED.part",
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::RUSR | Mode::WUSR,
        )?;
        fs::fsync(&fd)?;
        fs::fsync(&staging)?;
        checkpoint("allocation_effect");
        m.object = Some(source(&fd)?);
        m.phase = 1;
        store.save_manifest(&m)?;
        checkpoint("allocated");
    }
    if m.phase == 1 {
        let held = fs::openat(&staging, "COMMITTED.part", FILE, Mode::empty())?;
        let allocated = source(&held)?;
        let owned = m.object.as_ref().ok_or("missing allocation receipt")?;
        if allocated.device != owned.device
            || allocated.inode != owned.inode
            || allocated.uid != owned.uid
        {
            return Err("manifest allocation custody lost".into());
        }
        fs::fchmod(&held, Mode::RUSR | Mode::WUSR)?;
        let fd = fs::openat(
            &staging,
            "COMMITTED.part",
            OFlags::RDWR | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?;
        let actual = source(&fd)?;
        let owned = m.object.as_ref().ok_or("missing allocation receipt")?;
        if actual.device != owned.device
            || actual.inode != owned.inode
            || actual.uid != owned.uid
            || source(&held)?.inode != actual.inode
        {
            return Err("manifest allocation custody lost".into());
        }
        // Only the recorded owned manifest staging object may be rewritten;
        // exact manifest bytes are already durable, unlike an incomplete copy.
        let mut file = File::from(fd);
        file.set_len(0)?;
        file.seek(SeekFrom::Start(0))?;
        file.write_all(m.bytes.as_bytes())?;
        fs::fchmod(&file, Mode::RUSR)?;
        file.sync_all()?;
        fs::fsync(&staging)?;
        checkpoint("write_effect");
        m.object = Some(source(&file)?);
        m.phase = 2;
        store.save_manifest(&m)?;
        checkpoint("written");
    }
    if m.phase == 2 {
        let mut file = File::from(fs::openat(&staging, "COMMITTED.part", FILE, Mode::empty())?);
        read_exact_manifest(&mut file, &m)?;
        m.phase = 3;
        store.save_manifest(&m)?;
        checkpoint("authorized");
    }
    if m.phase == 3 {
        m = if let Some(publication) = publication {
            let anchor = store.transfer(id, 0)?.ok_or("missing manifest anchor")?;
            let next = publication(&anchor, &m)?;
            if next.job_id != m.job_id
                || next.bytes != m.bytes
                || next.sha256 != m.sha256
                || next.object != m.object
                || next.phase != 4
            {
                return Err("invalid manifest publication receipt".into());
            }
            next
        } else {
            publish_manifest_in_directories(&area, &staging, &m, checkpoint)?
        };
        store.save_manifest(&m)?;
        checkpoint("committed");
    } else if m.phase == 4 {
        let mut file = File::from(fs::openat(&area, "COMMITTED.json", FILE, Mode::empty())?);
        read_exact_manifest(&mut file, &m)?;
    }
    Ok(m)
}
pub fn publish_manifest_effect(
    t: &mover_core::Transfer,
    m: &ManifestRecord,
) -> ManifestResult<ManifestRecord> {
    if t.phase != TransferPhase::Published
        || t.file_index != 0
        || t.job_id != m.job_id
        || m.phase != 3
        || m.bytes.len() > 131072
        || format!("{:x}", Sha256::digest(m.bytes.as_bytes())) != m.sha256
    {
        return Err("invalid manifest publication assignment".into());
    }
    let (_, area, staging, _, _) = super::transfer::directories(t)?;
    publish_manifest_in_directories(&area, &staging, m, &mut |_| {})
}
fn publish_manifest_in_directories(
    area: &OwnedFd,
    staging: &OwnedFd,
    m: &ManifestRecord,
    checkpoint: &mut impl FnMut(&'static str),
) -> ManifestResult<ManifestRecord> {
    let fd = match fs::openat(area, "COMMITTED.json", FILE, Mode::empty()) {
        Ok(fd) => {
            if !matches!(
                fs::statat(staging, "COMMITTED.part", AtFlags::SYMLINK_NOFOLLOW),
                Err(Errno::NOENT)
            ) {
                return Err("manifest collision or ambiguous effect".into());
            }
            fd
        }
        Err(Errno::NOENT) => {
            let mut file = File::from(fs::openat(staging, "COMMITTED.part", FILE, Mode::empty())?);
            read_exact_manifest(&mut file, m)?;
            fs::renameat_with(
                staging,
                "COMMITTED.part",
                area,
                "COMMITTED.json",
                RenameFlags::NOREPLACE,
            )?;
            checkpoint("rename_effect");
            fs::openat(area, "COMMITTED.json", FILE, Mode::empty())?
        }
        Err(e) => return Err(e.into()),
    };
    let mut file = File::from(fd);
    read_exact_manifest(&mut file, m)?;
    file.sync_all()?;
    fs::fsync(staging)?;
    fs::fsync(area)?;
    checkpoint("publication_sync");
    let mut next = m.clone();
    next.phase = 4;
    Ok(next)
}
