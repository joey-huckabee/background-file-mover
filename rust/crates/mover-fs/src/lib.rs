//! First local-filesystem claim worker. Blocking calls must run off the executor.
//! Requires one fenced worker, immutable handed-off files and protected parents.
//! NFS, link fallback and deployment/mount qualification are deliberately blocked.

use mover_core::{ClaimIntent, FileSpec, ObjectIdentity};
use mover_store::{Accepted, Store};
use rustix::{
    fd::OwnedFd,
    fs::{self, AtFlags, FileType, Mode, OFlags, RenameFlags, Stat},
    io::Errno,
};

#[derive(Debug)]
pub enum ClaimError {
    Io(Errno),
    Store(mover_store::StoreError),
    Blocked(&'static str),
    MissingSource,
    ExpectedSizeMismatch,
}
impl std::fmt::Display for ClaimError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for ClaimError {}
impl From<Errno> for ClaimError {
    fn from(e: Errno) -> Self {
        Self::Io(e)
    }
}
impl From<mover_store::StoreError> for ClaimError {
    fn from(e: mover_store::StoreError) -> Self {
        Self::Store(e)
    }
}
type Result<T> = std::result::Result<T, ClaimError>;
const DIRECTORY: OFlags = OFlags::RDONLY
    .union(OFlags::DIRECTORY)
    .union(OFlags::NOFOLLOW)
    .union(OFlags::CLOEXEC);
const FILE: OFlags = OFlags::RDONLY
    .union(OFlags::NOFOLLOW)
    .union(OFlags::CLOEXEC)
    .union(OFlags::NONBLOCK);

mod manifest;
mod transfer;
pub use manifest::commit_manifest;
pub use manifest::commit_manifest_with_checkpoints;
pub fn destination_unavailable(path: &str) -> bool {
    matches!(
        root(path).and_then(|r| namespace(&r).map(|_| ())),
        Err(ClaimError::Io(Errno::NOENT))
    )
}
pub use transfer::{
    authorize_publication, copy_stage, prepare_transfer, publish_stage, restart_transfer,
    transfer_one, verify_stage,
};
pub use transfer::{deliver_recording, deliver_recording_with_guard, prepare_transfer_file};

fn observation(s: &Stat) -> ObjectIdentity {
    ObjectIdentity {
        device: s.st_dev,
        inode: s.st_ino,
        uid: s.st_uid,
        size: s.st_size as u64,
        modified_seconds: s.st_mtime,
        modified_nanos: s.st_mtime_nsec,
        links: s.st_nlink,
    }
}
fn owned_directory(fd: &OwnedFd, private: bool) -> Result<ObjectIdentity> {
    let s = fs::fstat(fd)?;
    if s.st_uid != rustix::process::geteuid().as_raw()
        || s.st_mode & if private { 0o077 } else { 0o022 } != 0
    {
        return Err(ClaimError::Blocked("directory custody/permissions"));
    }
    Ok(observation(&s))
}
fn root(path: &str) -> Result<OwnedFd> {
    if !path.starts_with('/') || path == "/" {
        return Err(ClaimError::Blocked("absolute configured root required"));
    }
    let mut dir = fs::open("/", DIRECTORY, Mode::empty())?;
    for part in path[1..].split('/') {
        if part.is_empty() || part == "." || part == ".." {
            return Err(ClaimError::Blocked("noncanonical root"));
        }
        dir = fs::openat(&dir, part, DIRECTORY, Mode::empty())?;
    }
    owned_directory(&dir, false)?;
    // This first slice only qualifies local ext, tmpfs and container overlay.
    // A reachable NFS mount is not a qualified durable/cached recovery endpoint.
    if ![0xef53, 0x01021994, 0x794c7630].contains(&fs::fstatfs(&dir)?.f_type) {
        return Err(ClaimError::Blocked(
            "filesystem not qualified for local claim slice",
        ));
    }
    Ok(dir)
}
fn parent(root: &OwnedFd, name: &str) -> Result<(OwnedFd, String)> {
    FileSpec::new(name, None).map_err(|_| ClaimError::Blocked("invalid source name"))?;
    let mut dir = rustix::io::dup(root)?;
    let mut parts = name.split('/').peekable();
    let device = fs::fstat(root)?.st_dev;
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            return Ok((dir, part.to_owned()));
        }
        dir = fs::openat(&dir, part, DIRECTORY, Mode::empty())?;
        if owned_directory(&dir, false)?.device != device {
            return Err(ClaimError::Blocked("cross-device traversal"));
        }
    }
    Err(ClaimError::Blocked("empty source name"))
}
fn source(fd: &impl rustix::fd::AsFd) -> Result<ObjectIdentity> {
    let s = fs::fstat(fd)?;
    if FileType::from_raw_mode(s.st_mode) != FileType::RegularFile
        || s.st_size < 0
        || s.st_uid != rustix::process::geteuid().as_raw()
        || s.st_mode & 0o022 != 0
        || s.st_nlink != 1
    {
        return Err(ClaimError::Blocked(
            "source must be owned regular file with one link",
        ));
    }
    Ok(observation(&s))
}
fn same_directory(actual: &ObjectIdentity, expected: &ObjectIdentity) -> Result<()> {
    if actual.device != expected.device
        || actual.inode != expected.inode
        || actual.uid != expected.uid
    {
        return Err(ClaimError::Blocked("directory identity changed"));
    }
    Ok(())
}
fn namespace(root: &OwnedFd) -> Result<OwnedFd> {
    let dir = fs::openat(root, ".file-mover", DIRECTORY, Mode::empty())?;
    if owned_directory(&dir, true)?.device != fs::fstat(root)?.st_dev {
        return Err(ClaimError::Blocked("claim namespace on another device"));
    }
    Ok(dir)
}

/// Local service singleton and custody guard. Holding this directory lock is
/// not a remote-worker fence; this increment still rejects NFS.
pub struct LocalClaimLock {
    path: String,
    root: ObjectIdentity,
    namespace: ObjectIdentity,
    _held: OwnedFd,
}
impl LocalClaimLock {
    pub fn acquire(path: &str) -> Result<Self> {
        let root = root(path)?;
        let namespace = namespace(&root)?;
        fs::flock(&namespace, fs::FlockOperation::NonBlockingLockExclusive)?;
        Ok(Self {
            path: path.into(),
            root: owned_directory(&root, false)?,
            namespace: owned_directory(&namespace, true)?,
            _held: namespace,
        })
    }
    pub fn validate(&self) -> Result<()> {
        let root = root(&self.path)?;
        same_directory(&owned_directory(&root, false)?, &self.root)?;
        same_directory(&owned_directory(&namespace(&root)?, true)?, &self.namespace)
    }
    pub fn validate_path(&self, path: &str) -> Result<()> {
        if self.path != path {
            return Err(ClaimError::Blocked("source scope changed"));
        }
        self.validate()
    }
}

/// Allocate an exclusive private directory, without moving any source data.
/// Administrator must first provision root/.file-mover as a service-owned 0700
/// directory. Allocation failure or a crash before begin_claim leaves an orphan
/// that blocks reuse; this API never adopts or deletes an existing directory.
pub fn prepare(job: &Accepted, index: usize) -> Result<ClaimIntent> {
    prepare_checked(None, job, index)
}
fn prepare_checked(store: Option<&Store>, job: &Accepted, index: usize) -> Result<ClaimIntent> {
    let file = job
        .recording
        .submission()
        .files()
        .get(index)
        .ok_or(ClaimError::Blocked("unknown file"))?;
    let source_name = if job.context.source_relative_directory.is_empty() {
        file.relative_path().to_owned()
    } else {
        format!(
            "{}/{}",
            job.context.source_relative_directory,
            file.relative_path()
        )
    };
    let root = root(&job.context.source_root_path)?;
    let namespace = namespace(&root)?;
    let (parent, name) = parent(&root, &source_name).map_err(|error| match error {
        ClaimError::Io(Errno::NOENT) => ClaimError::MissingSource,
        other => other,
    })?;
    let file_fd = fs::openat(&parent, name.as_str(), FILE, Mode::empty()).map_err(|error| {
        if error == Errno::NOENT {
            ClaimError::MissingSource
        } else {
            error.into()
        }
    })?;
    let source = source(&file_fd)?;
    if source.device != fs::fstat(&root)?.st_dev {
        return Err(ClaimError::Blocked("cross-device source"));
    }
    if file.expected_size().is_some_and(|n| n != source.size) {
        return Err(ClaimError::ExpectedSizeMismatch);
    }
    if let Some(store) = store {
        store.claim_capacity(source.size)?;
    }
    let private_name = format!("{}-{index}", job.job_id);
    fs::mkdirat(&namespace, private_name.as_str(), Mode::RWXU)?;
    let area = fs::openat(&namespace, private_name.as_str(), DIRECTORY, Mode::empty())?;
    fs::fsync(&area)?;
    fs::fsync(&namespace)?;
    fs::fsync(&root)?;
    Ok(ClaimIntent {
        job_id: job.job_id,
        file_index: index,
        root_path: job.context.source_root_path.clone(),
        source_name,
        private_name,
        root: owned_directory(&root, false)?,
        parent: owned_directory(&parent, false)?,
        area: owned_directory(&area, true)?,
        source,
    })
}

/// Apply or reconcile a COMMITTED intent. Caller must fence all other workers.
/// Errors after an effect are uncertain: retain intent and reconcile; never undo.
/// Unsupported NOREPLACE fails closed; no overwrite/copy/delete fallback.
pub fn apply(store: &Store, intent: &ClaimIntent) -> Result<()> {
    if store.claim_intent(intent.job_id, intent.file_index)? != Some((intent.clone(), false)) {
        return Err(ClaimError::Blocked(
            "matching committed unfinished intent required",
        ));
    }
    if intent.private_name != format!("{}-{}", intent.job_id, intent.file_index) {
        return Err(ClaimError::Blocked("invalid operation name"));
    }
    let root = root(&intent.root_path)?;
    same_directory(&owned_directory(&root, false)?, &intent.root)?;
    let (parent, name) = parent(&root, &intent.source_name)?;
    same_directory(&owned_directory(&parent, false)?, &intent.parent)?;
    let namespace = namespace(&root)?;
    let area = fs::openat(
        &namespace,
        intent.private_name.as_str(),
        DIRECTORY,
        Mode::empty(),
    )?;
    same_directory(&owned_directory(&area, true)?, &intent.area)?;
    let claimed = match fs::openat(&area, "data", FILE, Mode::empty()) {
        Ok(fd) => fd,
        Err(Errno::NOENT) => {
            let original = fs::openat(&parent, name.as_str(), FILE, Mode::empty())?;
            if source(&original)? != intent.source {
                return Err(ClaimError::Blocked("source changed since durable intent"));
            }
            fs::fsync(&original)?;
            fs::renameat_with(
                &parent,
                name.as_str(),
                &area,
                "data",
                RenameFlags::NOREPLACE,
            )?;
            let fd = fs::openat(&area, "data", FILE, Mode::empty())?;
            if source(&fd)? != intent.source {
                return Err(ClaimError::Blocked("claimed identity mismatch"));
            }
            fd
        }
        Err(e) => return Err(e.into()),
    };
    if source(&claimed)? != intent.source {
        return Err(ClaimError::Blocked("foreign/changed private claim"));
    }
    match fs::statat(&parent, name.as_str(), AtFlags::SYMLINK_NOFOLLOW) {
        Err(Errno::NOENT) => (),
        _ => {
            return Err(ClaimError::Blocked(
                "original name remains or absence uncertain",
            ));
        }
    }
    fs::fsync(&claimed)?;
    fs::fsync(&area)?;
    fs::fsync(&parent)?;
    fs::fsync(&namespace)?;
    Ok(())
}

/// Synchronous local coordinator; no transaction spans filesystem operations.
pub fn claim(store: &Store, job_id: i64, index: usize) -> Result<Accepted> {
    let job = store
        .get(job_id)?
        .ok_or(ClaimError::Blocked("unknown job"))?;
    let intent = match store.claim_intent(job_id, index)? {
        Some((_, true)) => return Ok(job), // Never inspect a producer's reused path.
        Some((intent, false)) => intent,
        None => {
            let intent = prepare_checked(Some(store), &job, index)?;
            store.begin_claim(&intent)?;
            intent
        }
    };
    apply(store, &intent)?;
    Ok(store.finish_claim(&intent)?)
}
