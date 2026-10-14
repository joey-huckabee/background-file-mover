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
    claimed_intent(&intent)
}
fn claimed_intent(intent: &ClaimIntent) -> TransferResult<OwnedFd> {
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
    let first = if index > 0 {
        store
            .transfer(id, 0)?
            .ok_or("first file owns recording directory")?
    } else {
        Transfer {
            job_id: id,
            file_index: index,
            attempt: 1,
            destination_root: job.context.destination_path.clone(),
            relative_name: String::new(),
            root: job_claim(store, id, index)?.root.clone(),
            area: job_claim(store, id, index)?.root.clone(),
            parent: job_claim(store, id, index)?.root.clone(),
            staging_directory: job_claim(store, id, index)?.root.clone(),
            stage: job_claim(store, id, index)?.root,
            sha256: None,
            phase: TransferPhase::Intent,
        }
    };
    let mut template = first;
    template.file_index = index;
    template.relative_name = job.recording.submission().files()[index]
        .relative_path()
        .into();
    let t = prepare_transfer_effect(&template, &job_claim(store, id, index)?)?;
    store.save_transfer(&t)?;
    Ok(t)
}
fn job_claim(store: &Store, id: i64, index: usize) -> TransferResult<ClaimIntent> {
    let (c, done) = store.claim_intent(id, index)?.ok_or("missing claim")?;
    if !done {
        return Err("claim incomplete".into());
    }
    Ok(c)
}
pub fn prepare_transfer_effect(
    template: &Transfer,
    claim: &ClaimIntent,
) -> TransferResult<Transfer> {
    let id = template.job_id;
    let index = template.file_index;
    if id != claim.job_id || index != claim.file_index || id <= 0 || index >= 256 {
        return Err("invalid staging assignment".into());
    }
    mover_core::FileSpec::new(&template.relative_name, None).map_err(|_| "invalid staging name")?;
    claimed_intent(claim)?;
    let root = root(&template.destination_root)?;
    namespace(&root)?;
    let first = (index > 0).then_some(template);
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
    let relative_name = template.relative_name.clone();
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
        destination_root: template.destination_root.clone(),
        relative_name,
        root: owned_directory(&root, false)?,
        area: owned_directory(&area, true)?,
        parent: owned_directory(&current, false)?,
        staging_directory: owned_directory(&staging, true)?,
        stage,
        sha256: None,
        phase: TransferPhase::Intent,
    };
    Ok(t)
}
pub fn restart_transfer(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::Intent)?;
    if t.attempt >= 100 {
        return Err("attempt budget exhausted; operator review required".into());
    }
    claimed(store, t.job_id, t.file_index)?;
    store.transfer_capacity(t.job_id, t.file_index)?;
    let next = restart_transfer_effect(t, &job_claim(store, t.job_id, t.file_index)?)?;
    store.save_transfer(&next)?;
    Ok(next)
}
pub fn restart_transfer_effect(t: &Transfer, claim: &ClaimIntent) -> TransferResult<Transfer> {
    if t.phase != TransferPhase::Intent
        || t.attempt >= 100
        || t.job_id != claim.job_id
        || t.file_index != claim.file_index
    {
        return Err("invalid restart assignment".into());
    }
    claimed_intent(claim)?;
    let (_, area, staging, _, _) = directories(t)?;
    // Partial/ambiguous old staging stays intact. No destructive retirement yet.
    let mut next = t.clone();
    next.attempt += 1;
    next.stage = allocate(&staging, next.attempt)?;
    fs::fsync(&area)?;
    Ok(next)
}
pub fn copy_stage(store: &Store, t: &Transfer) -> TransferResult<Transfer> {
    matching(store, t, TransferPhase::Intent)?;
    let (intent, done) = store
        .claim_intent(t.job_id, t.file_index)?
        .ok_or("missing claim")?;
    if !done {
        return Err("claim incomplete".into());
    }
    let next = copy_effect(t, &intent)?;
    store.save_transfer(&next)?;
    Ok(next)
}
/// Filesystem-only payload operation. Caller must hold custody locks and match
/// this assignment to a durable intent; this function never accesses SQLite.
pub fn copy_effect(t: &Transfer, intent: &ClaimIntent) -> TransferResult<Transfer> {
    if t.phase != TransferPhase::Intent
        || t.job_id != intent.job_id
        || t.file_index != intent.file_index
    {
        return Err("invalid copy assignment".into());
    }
    let source_fd = claimed_intent(intent)?;
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
        if total == n as u64 {
            super::qualification_pause("copy_chunk")?;
        }
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
    let (intent, done) = store
        .claim_intent(t.job_id, t.file_index)?
        .ok_or("missing claim")?;
    if !done {
        return Err("claim incomplete".into());
    }
    let next = verify_effect(t, &intent)?;
    store.save_transfer(&next)?;
    Ok(next)
}
/// Independent destination reread; no database access or publication.
pub fn verify_effect(t: &Transfer, intent: &ClaimIntent) -> TransferResult<Transfer> {
    if t.phase != TransferPhase::Copied
        || t.job_id != intent.job_id
        || t.file_index != intent.file_index
    {
        return Err("invalid verification assignment".into());
    }
    claimed_intent(intent)?;
    let (_, _, staging, _, _) = directories(t)?;
    let fd = fs::openat(&staging, format!("{}.part", t.attempt), FILE, Mode::empty())?;
    if Some(digest(fd, &t.stage)?) != t.sha256 {
        return Err("destination digest mismatch".into());
    }
    let mut next = t.clone();
    next.phase = TransferPhase::Verified;
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
    let (intent, done) = store
        .claim_intent(t.job_id, t.file_index)?
        .ok_or("missing claim")?;
    if !done {
        return Err("claim incomplete".into());
    }
    let next = publish_effect(t, &intent)?;
    store.save_transfer(&next)?;
    Ok(next)
}
pub fn publish_effect(t: &Transfer, intent: &ClaimIntent) -> TransferResult<Transfer> {
    super::qualification_pause("publish")?;
    if t.phase != TransferPhase::PublishIntent
        || t.job_id != intent.job_id
        || t.file_index != intent.file_index
    {
        return Err("invalid publication assignment".into());
    }
    claimed_intent(intent)?;
    let (_, _, staging, parent, name) = directories(t)?;
    let stage_name = format!("{}.part", t.attempt);
    let moved =
        super::relocate::owned(&staging, &stage_name, &parent, &name, &t.stage, &mut |_| {})?;
    if moved.recovered {
        // Only uncertain recovery adds a payload reread; normal transfer is 3N.
        let read_fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
        if Some(digest(read_fd, &t.stage)?) != t.sha256 {
            return Err("recovered final digest mismatch".into());
        }
    }
    let fd = moved.fd;
    fs::fsync(&fd)?;
    fs::fsync(&staging)?;
    fs::fsync(&parent)?;
    let mut next = t.clone();
    next.phase = TransferPhase::Published;
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
    transfer_file_with_payload(store, id, index, &mut |t, intent| match t.phase {
        TransferPhase::Intent => copy_effect(t, intent),
        TransferPhase::Copied => verify_effect(t, intent),
        TransferPhase::PublishIntent => publish_effect(t, intent),
        _ => Err("invalid payload phase".into()),
    })
}
fn transfer_file_with_payload(
    store: &Store,
    id: i64,
    index: usize,
    payload: &mut impl FnMut(&Transfer, &ClaimIntent) -> TransferResult<Transfer>,
) -> TransferResult<Transfer> {
    let mut t = match store.transfer(id, index)? {
        Some(t) if t.phase == TransferPhase::Intent => restart_transfer(store, &t)?,
        Some(t) => t,
        None => prepare_transfer_file(store, id, index)?,
    };
    if t.phase == TransferPhase::Intent {
        t = run_payload(store, &t, payload)?;
    }
    if t.phase == TransferPhase::Copied {
        t = run_payload(store, &t, payload)?;
    }
    if t.phase == TransferPhase::Verified {
        t = authorize_publication(store, &t)?;
    }
    if t.phase == TransferPhase::PublishIntent {
        t = run_payload(store, &t, payload)?;
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
fn run_payload(
    store: &Store,
    t: &Transfer,
    payload: &mut impl FnMut(&Transfer, &ClaimIntent) -> TransferResult<Transfer>,
) -> TransferResult<Transfer> {
    matching(store, t, t.phase)?;
    let (intent, done) = store
        .claim_intent(t.job_id, t.file_index)?
        .ok_or("missing claim")?;
    if !done {
        return Err("claim incomplete".into());
    }
    let next = payload(t, &intent)?;
    // The SQLite owner validates the immutable context and adjacent transition.
    store.save_transfer(&next)?;
    Ok(next)
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
    deliver_recording_with_payload(store, id, guard, |t, intent, _| match t.phase {
        TransferPhase::Intent => copy_effect(t, intent),
        TransferPhase::Copied => verify_effect(t, intent),
        TransferPhase::PublishIntent => publish_effect(t, intent),
        _ => Err("invalid payload phase".into()),
    })
}
/// Hold both namespace locks across each payload assignment and its receipt.
pub fn deliver_recording_with_payload(
    store: &Store,
    id: i64,
    guard: &LocalClaimLock,
    mut payload: impl FnMut(&Transfer, &ClaimIntent, &LocalClaimLock) -> TransferResult<Transfer>,
) -> TransferResult<()> {
    deliver_recording_with_workers(store, id, guard, &mut payload, |t, m, _| {
        super::manifest::publish_manifest_effect(t, m)
    })
}
pub fn deliver_recording_with_workers(
    store: &Store,
    id: i64,
    guard: &LocalClaimLock,
    mut payload: impl FnMut(&Transfer, &ClaimIntent, &LocalClaimLock) -> TransferResult<Transfer>,
    mut publication: impl FnMut(
        &Transfer,
        &mover_core::ManifestRecord,
        &LocalClaimLock,
    ) -> TransferResult<mover_core::ManifestRecord>,
) -> TransferResult<()> {
    let job = store.get(id)?.ok_or("unknown job")?;
    guard.validate_path(&job.context.source_root_path)?;
    if job.recording.handoff() != Handoff::Ready202 {
        return Err("all claims required before delivery".into());
    }
    let destination = LocalClaimLock::acquire(&job.context.destination_path)?;
    destination.validate()?;
    for index in 0..job.recording.submission().files().len() {
        transfer_file_with_payload(store, id, index, &mut |t, intent| {
            payload(t, intent, &destination)
        })?;
    }
    super::manifest::commit_manifest_with_publication(store, id, |t, m| {
        publication(t, m, &destination)
    })?;
    Ok(())
}

pub fn published_custody_effect(t: &Transfer, claim: &ClaimIntent) -> TransferResult<Transfer> {
    if t.phase != TransferPhase::Published
        || t.job_id != claim.job_id
        || t.file_index != claim.file_index
    {
        return Err("invalid custody assignment".into());
    }
    claimed_intent(claim)?;
    let (_, _, _, parent, name) = directories(t)?;
    let fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
    if source(&fd)? != t.stage {
        return Err("published custody lost".into());
    }
    Ok(t.clone())
}
