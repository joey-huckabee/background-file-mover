//! Single-file local transfer, with durable boundaries for crash reconciliation.
//! Hold source/destination LocalClaimLocks and fence workers around these calls.
use super::*;
use mover_core::{Handoff, Transfer, TransferPhase};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Write},
};
type TransferResult<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn matching(store: &Store, t: &Transfer, phase: TransferPhase) -> TransferResult<()> {
    if t.phase != phase || store.transfer(t.job_id, t.file_index)? != Some(t.clone()) {
        return Err("matching durable transfer boundary required".into());
    }
    Ok(())
}
pub(super) fn claimed(store: &Store, id: i64, index: usize) -> TransferResult<OwnedFd> {
    let (intent, done) = store
        .claim_intent(id, index)?
        .ok_or("missing claim receipt")?;
    if !done {
        return Err("claim incomplete".into());
    }
    let root = root(&intent.root_path)?;
    same_directory(&owned_directory(&root, false)?, &intent.root)?;
    let namespace = namespace(&root)?;
    let area = fs::openat(
        &namespace,
        intent.private_name.as_str(),
        DIRECTORY,
        Mode::empty(),
    )?;
    same_directory(&owned_directory(&area, true)?, &intent.area)?;
    let fd = fs::openat(&area, "data", FILE, Mode::empty())?;
    if source(&fd)? != intent.source {
        return Err("claimed source changed".into());
    }
    Ok(fd)
}
pub(super) fn directories(
    t: &Transfer,
) -> TransferResult<(OwnedFd, OwnedFd, OwnedFd, OwnedFd, String)> {
    let root = root(&t.destination_root)?;
    same_directory(&owned_directory(&root, false)?, &t.root)?;
    let area = fs::openat(&root, t.job_id.to_string(), DIRECTORY, Mode::empty())?;
    same_directory(&owned_directory(&area, true)?, &t.area)?;
    let mut staging = fs::openat(&area, ".staging", DIRECTORY, Mode::empty())?;
    if t.file_index > 0 {
        staging = fs::openat(&staging, t.file_index.to_string(), DIRECTORY, Mode::empty())?;
    }
    same_directory(&owned_directory(&staging, true)?, &t.staging_directory)?;
    if owned_directory(&staging, true)?.device != t.root.device {
        return Err("staging device changed".into());
    }
    let (parent, name) = parent(&area, &t.relative_name)?;
    same_directory(&owned_directory(&parent, false)?, &t.parent)?;
    Ok((root, area, staging, parent, name))
}
fn allocate(staging: &OwnedFd, attempt: i64) -> TransferResult<ObjectIdentity> {
    let fd = fs::openat(
        staging,
        format!("{attempt}.part"),
        OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::RUSR | Mode::WUSR,
    )?;
    fs::fsync(&fd)?;
    fs::fsync(staging)?;
    Ok(source(&fd)?)
}
pub fn prepare_transfer(store: &Store, id: i64) -> TransferResult<Transfer> {
    prepare_transfer_file(store, id, 0)
}
pub fn prepare_transfer_file(store: &Store, id: i64, index: usize) -> TransferResult<Transfer> {
    let job = store.get(id)?.ok_or("unknown job")?;
    if job.recording.handoff() != Handoff::Ready202
        || index >= job.recording.submission().files().len()
        || job.context.policy.group_by_generator
        || store.transfer(id, index)?.is_some()
    {
        return Err("first transfer requires one fully claimed ungrouped file".into());
    }
    claimed(store, id, index)?;
    store.transfer_capacity(id, index)?;
    let root = root(&job.context.destination_path)?;
    namespace(&root)?;
    let first = if index > 0 {
        Some(
            store
                .transfer(id, 0)?
                .ok_or("first file owns recording directory")?,
        )
    } else {
        None
    };
    if first.is_none() {
        fs::mkdirat(&root, id.to_string(), Mode::RWXU)?;
    }
    let area = fs::openat(&root, id.to_string(), DIRECTORY, Mode::empty())?;
    if let Some(first) = &first {
        same_directory(&owned_directory(&root, false)?, &first.root)?;
        same_directory(&owned_directory(&area, true)?, &first.area)?;
    }
    if first.is_none() {
        fs::mkdirat(&area, ".staging", Mode::RWXU)?;
    }
    let mut staging = fs::openat(&area, ".staging", DIRECTORY, Mode::empty())?;
    if index > 0 {
        fs::mkdirat(&staging, index.to_string(), Mode::RWXU)?;
        let child = fs::openat(&staging, index.to_string(), DIRECTORY, Mode::empty())?;
        fs::fsync(&staging)?;
        staging = child;
    }
    let relative_name = job.recording.submission().files()[index]
        .relative_path()
        .to_owned();
    let mut current = rustix::io::dup(&area)?;
    let components: Vec<_> = relative_name.split('/').collect();
    for component in &components[..components.len() - 1] {
        match fs::mkdirat(&current, *component, Mode::RWXU) {
            Ok(()) => (),
            Err(Errno::EXIST) if index > 0 => (),
            Err(e) => return Err(e.into()),
        }
        let child = fs::openat(&current, *component, DIRECTORY, Mode::empty())?;
        fs::fsync(&child)?;
        fs::fsync(&current)?;
        current = child;
    }
    let stage = allocate(&staging, 1)?;
    fs::fsync(&area)?;
    fs::fsync(&root)?;
    let t = Transfer {
        job_id: id,
        file_index: index,
        attempt: 1,
        destination_root: job.context.destination_path,
        relative_name,
        root: owned_directory(&root, false)?,
        area: owned_directory(&area, true)?,
        parent: owned_directory(&current, false)?,
        staging_directory: owned_directory(&staging, true)?,
        stage,
        sha256: None,
        phase: TransferPhase::Intent,
    };
    store.save_transfer(&t)?;
    Ok(t)
}
pub fn restart_transfer(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::Intent)?;
    if t.attempt >= 100 {
        return Err("attempt budget exhausted; operator review required".into());
    }
    claimed(store, t.job_id, t.file_index)?;
    store.transfer_capacity(t.job_id, t.file_index)?;
    let (_, area, staging, _, _) = directories(t)?;
    // Partial/ambiguous old staging stays intact. No destructive retirement yet.
    let mut next = t.clone();
    next.attempt += 1;
    next.stage = allocate(&staging, next.attempt)?;
    fs::fsync(&area)?;
    store.save_transfer(&next)?;
    Ok(next)
}
pub fn copy_stage(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::Intent)?;
    let source_fd = claimed(store, t.job_id, t.file_index)?;
    let expected = source(&source_fd)?;
    let mut input = File::from(source_fd);
    let (_, _, staging, _, _) = directories(t)?;
    let fd = fs::openat(
        &staging,
        format!("{}.part", t.attempt),
        OFlags::RDWR | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?;
    if source(&fd)? != t.stage || t.stage.size != 0 {
        return Err("staging changed before copy".into());
    }
    let mut output = File::from(fd);
    let mut hash = Sha256::new();
    let mut total = 0_u64;
    let mut buffer = vec![0; 1024 * 1024];
    loop {
        let n = input.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        total = total.checked_add(n as u64).ok_or("byte count overflow")?;
        if total > expected.size {
            return Err("source grew during copy".into());
        }
        hash.update(&buffer[..n]);
        output.write_all(&buffer[..n])?;
    }
    if total != expected.size || source(&input)? != expected {
        return Err("source changed during copy".into());
    }
    fs::fchmod(&output, Mode::RUSR)?;
    output.sync_all()?;
    fs::fsync(&staging)?;
    let mut next = t.clone();
    next.stage = source(&output)?;
    next.sha256 = Some(format!("{:x}", hash.finalize()));
    next.phase = TransferPhase::Copied;
    if next.stage.size != total {
        return Err("staging size mismatch".into());
    }
    store.save_transfer(&next)?;
    Ok(next)
}
fn digest(fd: OwnedFd, expected: &ObjectIdentity) -> TransferResult<String> {
    let mut file = File::from(fd);
    if source(&file)? != *expected {
        return Err("verification object changed".into());
    }
    let mut hash = Sha256::new();
    let mut count = 0_u64;
    let mut buffer = vec![0; 1024 * 1024];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        count = count.checked_add(n as u64).ok_or("byte count overflow")?;
        hash.update(&buffer[..n]);
    }
    if count != expected.size || source(&file)? != *expected {
        return Err("verification size/identity changed".into());
    }
    Ok(format!("{:x}", hash.finalize()))
}
pub fn verify_stage(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::Copied)?;
    claimed(store, t.job_id, t.file_index)?;
    let (_, _, staging, _, _) = directories(t)?;
    let fd = fs::openat(&staging, format!("{}.part", t.attempt), FILE, Mode::empty())?;
    if Some(digest(fd, &t.stage)?) != t.sha256 {
        return Err("destination digest mismatch".into());
    }
    let mut next = t.clone();
    next.phase = TransferPhase::Verified;
    store.save_transfer(&next)?;
    Ok(next)
}
pub fn authorize_publication(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::Verified)?;
    let mut next = t.clone();
    next.phase = TransferPhase::PublishIntent;
    store.save_transfer(&next)?;
    Ok(next)
}
pub fn publish_stage(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::PublishIntent)?;
    claimed(store, t.job_id, t.file_index)?;
    let (_, _, staging, parent, name) = directories(t)?;
    let stage_name = format!("{}.part", t.attempt);
    let fd = match fs::openat(&parent, name.as_str(), FILE, Mode::empty()) {
        Ok(final_fd) => {
            if !matches!(
                fs::statat(&staging, stage_name.as_str(), AtFlags::SYMLINK_NOFOLLOW),
                Err(Errno::NOENT)
            ) {
                return Err("final collision or ambiguous two-name effect".into());
            }
            if source(&final_fd)? != t.stage {
                return Err("foreign final collision".into());
            }
            // Uncertain publication recovery rereads the owned final; normal
            // publication below adds no extra payload read to the 3N path.
            let read_fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
            if Some(digest(read_fd, &t.stage)?) != t.sha256 {
                return Err("recovered final digest mismatch".into());
            }
            final_fd
        }
        Err(Errno::NOENT) => {
            let stage = fs::openat(&staging, stage_name.as_str(), FILE, Mode::empty())?;
            if source(&stage)? != t.stage {
                return Err("verified staging changed".into());
            }
            fs::renameat_with(
                &staging,
                stage_name.as_str(),
                &parent,
                name.as_str(),
                RenameFlags::NOREPLACE,
            )?;
            let fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
            if source(&fd)? != t.stage {
                return Err("published object mismatch".into());
            }
            fd
        }
        Err(e) => return Err(e.into()),
    };
    fs::fsync(&fd)?;
    fs::fsync(&staging)?;
    fs::fsync(&parent)?;
    let mut next = t.clone();
    next.phase = TransferPhase::Published;
    store.save_transfer(&next)?;
    Ok(next)
}
pub fn transfer_one(store: &Store, id: i64) -> TransferResult<Transfer> {
    let job = store.get(id)?.ok_or("unknown job")?;
    if job.recording.submission().files().len() != 1 {
        return Err("use recording delivery for multi-file jobs".into());
    }
    let source_lock = LocalClaimLock::acquire(&job.context.source_root_path)?;
    let destination_lock = LocalClaimLock::acquire(&job.context.destination_path)?;
    source_lock.validate()?;
    destination_lock.validate()?;
    transfer_file(store, id, 0)
}
fn transfer_file(store: &Store, id: i64, index: usize) -> TransferResult<Transfer> {
    let mut t = match store.transfer(id, index)? {
        Some(t) if t.phase == TransferPhase::Intent => restart_transfer(store, &t)?,
        Some(t) => t,
        None => prepare_transfer_file(store, id, index)?,
    };
    if t.phase == TransferPhase::Intent {
        t = copy_stage(store, &t)?;
    }
    if t.phase == TransferPhase::Copied {
        t = verify_stage(store, &t)?;
    }
    if t.phase == TransferPhase::Verified {
        t = authorize_publication(store, &t)?;
    }
    if t.phase == TransferPhase::PublishIntent {
        t = publish_stage(store, &t)?;
    }
    if t.phase == TransferPhase::Published {
        claimed(store, id, index)?;
        let (_, _, _, parent, name) = directories(&t)?;
        let fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
        if source(&fd)? != t.stage {
            return Err("published custody lost".into());
        }
    }
    Ok(t)
}
pub fn deliver_recording(store: &Store, id: i64) -> TransferResult<()> {
    let job = store.get(id)?.ok_or("unknown job")?;
    let guard = LocalClaimLock::acquire(&job.context.source_root_path)?;
    deliver_recording_with_guard(store, id, &guard)
}
pub fn deliver_recording_with_guard(
    store: &Store,
    id: i64,
    guard: &LocalClaimLock,
) -> TransferResult<()> {
    let job = store.get(id)?.ok_or("unknown job")?;
    guard.validate_path(&job.context.source_root_path)?;
    if job.recording.handoff() != Handoff::Ready202 {
        return Err("all claims required before delivery".into());
    }
    let destination = LocalClaimLock::acquire(&job.context.destination_path)?;
    destination.validate()?;
    for index in 0..job.recording.submission().files().len() {
        transfer_file(store, id, index)?;
    }
    super::manifest::commit_manifest(store, id)?;
    Ok(())
}
