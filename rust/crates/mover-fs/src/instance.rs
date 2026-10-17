//! Cooperative local instance exclusion, independent of NFS custody locks.
use super::*;
use rustix::{
    fd::AsFd,
    net::{
        self, RecvAncillaryBuffer, RecvAncillaryMessage, RecvFlags, ReturnFlags,
        SendAncillaryBuffer, SendAncillaryMessage, SendFlags,
    },
};
use serde::{Deserialize, Serialize};
use std::{
    io::{IoSlice, IoSliceMut, Read, Write},
    mem::MaybeUninit,
    os::unix::net::UnixStream,
    path::Path,
};

pub const INSTANCE_LOCK: &str = "instance.lock";
#[derive(Debug, PartialEq, Eq)]
pub enum InstanceOwnership {
    Absent,
    Free,
    Held,
}
/// Observe the existing guard without creating or rewriting state.
pub fn instance_ownership(database: &str) -> Result<InstanceOwnership> {
    let directory = Path::new(database)
        .parent()
        .and_then(Path::to_str)
        .ok_or(ClaimError::Blocked("local state parent required"))?;
    let dir = local_parent(directory)?;
    refuse_mounted(
        directory,
        &[
            INSTANCE_LOCK,
            crate::worker_epoch::WORKER_EPOCH,
            crate::worker_epoch::WORKER_NEXT,
        ],
    )?;
    let held = match fs::openat(
        &dir,
        INSTANCE_LOCK,
        OFlags::RDWR | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
        Mode::empty(),
    ) {
        Ok(fd) => fd,
        Err(Errno::NOENT) => {
            if fs::statat(
                &dir,
                crate::worker_epoch::WORKER_EPOCH,
                AtFlags::SYMLINK_NOFOLLOW,
            )
            .is_ok()
                || fs::statat(
                    &dir,
                    crate::worker_epoch::WORKER_NEXT,
                    AtFlags::SYMLINK_NOFOLLOW,
                )
                .is_ok()
            {
                return Err(ClaimError::Blocked(
                    "worker evidence without instance guard",
                ));
            }
            return Ok(InstanceOwnership::Absent);
        }
        Err(e) => return Err(e.into()),
    };
    let guard = InstanceGuard {
        directory: directory.into(),
        parent: owned_directory(&dir, true)?,
        object: checked(&fs::fstat(&held)?)?,
        held,
    };
    guard.validate_named()?;
    let result = match fs::flock(&guard.held, fs::FlockOperation::NonBlockingLockExclusive) {
        Ok(()) => {
            if crate::worker_epoch::active(&guard, false)? {
                InstanceOwnership::Held
            } else {
                InstanceOwnership::Free
            }
        }
        Err(Errno::AGAIN) => InstanceOwnership::Held,
        Err(e) => return Err(e.into()),
    };
    guard.validate_named()?;
    Ok(result) // Close only; never explicitly unlock another shared description.
}

const LIMIT: usize = 16384;
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Proof {
    version: u32,
    directory: String,
    parent: String,
    object: String,
}

/// Close-only ownership. Never unlock the shared description explicitly.
pub struct InstanceGuard {
    directory: String,
    parent: ObjectIdentity,
    object: ObjectIdentity,
    held: OwnedFd,
}
impl InstanceGuard {
    pub(crate) fn epoch_identity(&self) -> String {
        self.object.encode()
    }
    /// Persist group lifetime evidence before inheriting any NFS descriptor.
    pub fn prepare_workers(&self) -> Result<()> {
        crate::worker_epoch::prepare(self)
    }
    pub fn state_directory(&self) -> &str {
        &self.directory
    }
    pub fn for_database(database: &str) -> Result<Self> {
        let directory = Path::new(database)
            .parent()
            .and_then(Path::to_str)
            .ok_or(ClaimError::Blocked("local state parent required"))?;
        let dir = local_parent(directory)?;
        refuse_mounted(
            directory,
            &[
                INSTANCE_LOCK,
                "control.sock",
                crate::worker_epoch::WORKER_EPOCH,
                crate::worker_epoch::WORKER_NEXT,
            ],
        )?;
        if fs::statat(&dir, INSTANCE_LOCK, AtFlags::SYMLINK_NOFOLLOW).is_err()
            && (fs::statat(
                &dir,
                crate::worker_epoch::WORKER_EPOCH,
                AtFlags::SYMLINK_NOFOLLOW,
            )
            .is_ok()
                || fs::statat(
                    &dir,
                    crate::worker_epoch::WORKER_NEXT,
                    AtFlags::SYMLINK_NOFOLLOW,
                )
                .is_ok())
        {
            return Err(ClaimError::Blocked(
                "worker evidence without instance guard",
            ));
        }
        let held = match fs::openat(
            &dir,
            INSTANCE_LOCK,
            OFlags::RDWR
                | OFlags::CREATE
                | OFlags::EXCL
                | OFlags::NOFOLLOW
                | OFlags::NONBLOCK
                | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        ) {
            Ok(fd) => {
                fs::fsync(&fd)?;
                fs::fsync(&dir)?;
                fd
            }
            Err(Errno::EXIST) => fs::openat(
                &dir,
                INSTANCE_LOCK,
                OFlags::RDWR | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
                Mode::empty(),
            )?,
            Err(e) => return Err(e.into()),
        };
        let guard = Self {
            directory: directory.into(),
            parent: owned_directory(&dir, true)?,
            object: checked(&fs::fstat(&held)?)?,
            held,
        };
        guard.validate_named()?;
        custody::exclusive(&guard.held).map_err(|_| {
            ClaimError::Blocked("local instance or surviving worker already owns state")
        })?;
        guard.validate()?;
        if crate::worker_epoch::active(&guard, true)? {
            return Err(ClaimError::Blocked(
                "local instance or surviving worker already owns state",
            ));
        }
        guard.validate_database(database)?;
        Ok(guard)
    }
    /// Inspect every SQLite recovery name before SQLite or source bootstrap.
    /// Cooperative fixed-state profile: excludes concurrent same-UID/root mutation.
    pub fn validate_database(&self, database: &str) -> Result<()> {
        self.validate()?;
        let path = Path::new(database);
        if path.parent() != Some(Path::new(&self.directory)) {
            return Err(ClaimError::Blocked(
                "SQLite state parent differs from instance guard",
            ));
        }
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .filter(|n| {
                ![
                    INSTANCE_LOCK,
                    "control.sock",
                    crate::worker_epoch::WORKER_EPOCH,
                    crate::worker_epoch::WORKER_NEXT,
                ]
                .contains(n)
                    && !["-wal", "-shm", "-journal"].iter().any(|s| n.ends_with(s))
            })
            .ok_or(ClaimError::Blocked("reserved SQLite state name"))?;
        let dir = local_parent(&self.directory)?;
        // Read kernel mount metadata BEFORE touching candidate names. A mounted
        // NFS file can block even stat/open; local parent statfs is insufficient.
        let mounts = local_mounts()?;
        let mut database_exists = false;
        for suffix in ["", "-wal", "-shm", "-journal"] {
            let file = format!("{name}{suffix}");
            if mounts.iter().any(|m| m == &path.with_file_name(&file)) {
                return Err(ClaimError::Blocked("SQLite state file is a mount point"));
            }
            let named = match fs::statat(&dir, file.as_str(), AtFlags::SYMLINK_NOFOLLOW) {
                Ok(stat) => stat,
                Err(Errno::NOENT) => continue,
                Err(e) => return Err(e.into()),
            };
            if FileType::from_raw_mode(named.st_mode) != FileType::RegularFile
                || named.st_uid != rustix::process::geteuid().as_raw()
                || named.st_nlink != 1
                || named.st_mode & 0o7022 != 0
                || named.st_mode & 0o600 != 0o600
            {
                return Err(ClaimError::Blocked("unsafe SQLite state file"));
            }
            let fd = fs::openat(
                &dir,
                file.as_str(),
                OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
                Mode::empty(),
            )?;
            let actual = fs::fstat(&fd)?;
            if observation(&actual) != observation(&named)
                || actual.st_dev != fs::fstat(&dir)?.st_dev
                || ![0xef53, 0x01021994, 0x794c7630].contains(&fs::fstatfs(&fd)?.f_type)
            {
                return Err(ClaimError::Blocked(
                    "SQLite state file identity or locality changed",
                ));
            }
            if suffix.is_empty() {
                database_exists = true;
            } else if !database_exists {
                return Err(ClaimError::Blocked(
                    "SQLite recovery file without database; preserve original state",
                ));
            }
        }
        self.validate()
    }
    /// Create only a missing database, privately, after source bootstrap succeeds.
    /// Never chmod, truncate, remove or replace existing database/recovery files.
    pub fn prepare_database(&self, database: &str) -> Result<()> {
        self.validate_database(database)?;
        let dir = local_parent(&self.directory)?;
        let name = Path::new(database)
            .file_name()
            .ok_or(ClaimError::Blocked("SQLite state name required"))?;
        match fs::openat(
            &dir,
            name,
            OFlags::RDWR
                | OFlags::CREATE
                | OFlags::EXCL
                | OFlags::NOFOLLOW
                | OFlags::NONBLOCK
                | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        ) {
            Ok(fd) => {
                fs::fsync(&fd)?;
                fs::fsync(&dir)?;
            }
            Err(Errno::EXIST) => (),
            Err(e) => return Err(e.into()),
        }
        self.validate_database(database)
    }
    fn validate_named(&self) -> Result<()> {
        let dir = local_parent(&self.directory)?;
        refuse_mounted(
            &self.directory,
            &[
                INSTANCE_LOCK,
                crate::worker_epoch::WORKER_EPOCH,
                crate::worker_epoch::WORKER_NEXT,
            ],
        )?;
        same_directory(&owned_directory(&dir, true)?, &self.parent)?;
        let actual = checked(&fs::fstat(&self.held)?)?;
        let named = checked(&fs::statat(&dir, INSTANCE_LOCK, AtFlags::SYMLINK_NOFOLLOW)?)?;
        if actual != self.object || named != self.object {
            return Err(ClaimError::Blocked("local instance guard identity changed"));
        }
        if fs::fcntl_getfl(&self.held)? & OFlags::ACCMODE != OFlags::RDWR {
            return Err(ClaimError::Blocked(
                "local instance guard must be read/write",
            ));
        }
        Ok(())
    }
    pub fn validate(&self) -> Result<()> {
        self.validate_named()?;
        // An independent description must contend before validating the inherited
        // one. An unlocked descriptor must never acquire authority in a worker.
        let dir = local_parent(&self.directory)?;
        let probe = fs::openat(
            &dir,
            INSTANCE_LOCK,
            OFlags::RDWR | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )?;
        if checked(&fs::fstat(&probe)?)? != self.object {
            return Err(ClaimError::Blocked("local instance probe identity changed"));
        }
        match fs::flock(&probe, fs::FlockOperation::NonBlockingLockExclusive) {
            Err(Errno::AGAIN) => (),
            _ => return Err(ClaimError::Blocked("local instance guard is not held")),
        }
        custody::exclusive(&self.held)?;
        self.validate_named()
    }
    /// A separate, versioned prefix on the existing private worker stream.
    /// SCM_RIGHTS preserves the locked open description, without unsafe pre_exec.
    pub fn send(
        &self,
        channel: &mut UnixStream,
    ) -> std::result::Result<(), Box<dyn std::error::Error>> {
        self.prepare_workers()?;
        let bytes = serde_json::to_vec(&Proof {
            version: 1,
            directory: self.directory.clone(),
            parent: self.parent.encode(),
            object: self.object.encode(),
        })?;
        if bytes.len() > LIMIT {
            return Err("instance proof too large".into());
        }
        let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(1))];
        let mut control = SendAncillaryBuffer::new(&mut space);
        let descriptors = [self.held.as_fd()];
        if !control.push(SendAncillaryMessage::ScmRights(&descriptors)) {
            return Err("instance descriptor encoding".into());
        }
        if net::sendmsg(
            &*channel,
            &[IoSlice::new(b"I")],
            &mut control,
            SendFlags::NOSIGNAL,
        )? != 1
        {
            return Err("instance descriptor send failed".into());
        }
        channel.write_all(&(bytes.len() as u32).to_be_bytes())?;
        channel.write_all(&bytes)?;
        let mut ack = [0];
        channel.read_exact(&mut ack)?;
        if ack != *b"A" {
            return Err("invalid instance acceptance".into());
        }
        Ok(())
    }
    pub fn receive(
        channel: &mut UnixStream,
    ) -> std::result::Result<Self, Box<dyn std::error::Error>> {
        let mut byte = [0];
        let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(2))];
        let mut control = RecvAncillaryBuffer::new(&mut space);
        let received = net::recvmsg(
            &*channel,
            &mut [IoSliceMut::new(&mut byte)],
            &mut control,
            RecvFlags::CMSG_CLOEXEC,
        )?;
        let mut held = None;
        for message in control.drain() {
            match message {
                RecvAncillaryMessage::ScmRights(fds) => {
                    for fd in fds {
                        if held.replace(fd).is_some() {
                            return Err("extra instance descriptor".into());
                        }
                    }
                }
                _ => return Err("unexpected instance ancillary message".into()),
            }
        }
        if received.bytes != 1
            || byte != *b"I"
            || received
                .flags
                .intersects(ReturnFlags::CTRUNC | ReturnFlags::TRUNC)
        {
            return Err("invalid instance descriptor frame".into());
        }
        let held = held.ok_or("missing instance descriptor")?;
        let mut length = [0; 4];
        channel.read_exact(&mut length)?;
        let length = u32::from_be_bytes(length) as usize;
        if length > LIMIT {
            return Err("instance proof too large".into());
        }
        let mut bytes = vec![0; length];
        channel.read_exact(&mut bytes)?;
        let p: Proof = serde_json::from_slice(&bytes)?;
        if p.version != 1 {
            return Err("invalid instance proof version".into());
        }
        let guard = Self {
            directory: p.directory,
            parent: ObjectIdentity::decode(&p.parent).ok_or("invalid instance parent identity")?,
            object: ObjectIdentity::decode(&p.object).ok_or("invalid instance object identity")?,
            held,
        };
        guard.validate()?;
        crate::worker_epoch::require_group(&guard)?;
        channel.write_all(b"A")?;
        Ok(guard)
    }
}
pub(crate) fn local_parent_for_epoch(directory: &str) -> Result<OwnedFd> {
    local_parent(directory)
}
fn refuse_mounted(directory: &str, names: &[&str]) -> Result<()> {
    let mounts = local_mounts()?;
    if names
        .iter()
        .any(|name| mounts.contains(&Path::new(directory).join(name)))
    {
        return Err(ClaimError::Blocked(
            "local ownership/control file is a mount point",
        ));
    }
    Ok(())
}
// mountinfo is local proc metadata, never an NFS pathname traversal.
fn local_mounts() -> Result<Vec<std::path::PathBuf>> {
    let file = std::fs::File::open("/proc/self/mountinfo")
        .map_err(|_| ClaimError::Blocked("local mount inventory unavailable"))?;
    let mut bytes = Vec::new();
    file.take(4 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| ClaimError::Blocked("local mount inventory unreadable"))?;
    if bytes.len() > 4 * 1024 * 1024 {
        return Err(ClaimError::Blocked("local mount inventory too large"));
    }
    parse_mounts(&bytes)
}
fn parse_mounts(bytes: &[u8]) -> Result<Vec<std::path::PathBuf>> {
    use std::os::unix::ffi::OsStringExt;
    let mut result = Vec::new();
    for line in bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()) {
        let fields: Vec<_> = line.split(|b| *b == b' ').collect();
        if fields.len() < 10 || !fields.contains(&b"-".as_slice()) {
            return Err(ClaimError::Blocked("invalid local mount inventory"));
        }
        let mut decoded = Vec::new();
        let mut input = fields[4];
        while !input.is_empty() {
            if input[0] == b'\\' {
                if input.len() < 4 {
                    return Err(ClaimError::Blocked("invalid mount path escape"));
                }
                let value = match &input[..4] {
                    b"\\040" => b' ',
                    b"\\011" => b'\t',
                    b"\\012" => b'\n',
                    b"\\134" => b'\\',
                    _ => return Err(ClaimError::Blocked("invalid mount path escape")),
                };
                decoded.push(value);
                input = &input[4..];
            } else {
                decoded.push(input[0]);
                input = &input[1..];
            }
        }
        if decoded.first() != Some(&b'/') {
            return Err(ClaimError::Blocked("invalid mount path"));
        }
        result.push(std::ffi::OsString::from_vec(decoded).into());
    }
    if result.is_empty() {
        return Err(ClaimError::Blocked("empty local mount inventory"));
    }
    Ok(result)
}
fn local_parent(path: &str) -> Result<OwnedFd> {
    let dir = root(path)?;
    if ![0xef53, 0x01021994, 0x794c7630].contains(&fs::fstatfs(&dir)?.f_type) {
        return Err(ClaimError::Blocked(
            "instance state filesystem must be qualified local storage",
        ));
    }
    owned_directory(&dir, true)?;
    Ok(dir)
}
fn checked(s: &Stat) -> Result<ObjectIdentity> {
    if FileType::from_raw_mode(s.st_mode) != FileType::RegularFile
        || s.st_size != 0
        || s.st_uid != rustix::process::geteuid().as_raw()
        || s.st_mode & 0o7777 != 0o600
        || s.st_nlink != 1
    {
        return Err(ClaimError::Blocked("unsafe local instance guard"));
    }
    Ok(observation(s))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    struct Fixture(std::path::PathBuf);
    impl Fixture {
        fn new() -> Self {
            let p = std::env::temp_dir().join(format!(
                "instance-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            std::fs::create_dir(&p).unwrap();
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(p)
        }
        fn database(&self) -> String {
            self.0.join("jobs.sqlite").to_str().unwrap().into()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn sqlite_recovery_layout_refuses_unsafe_names_without_mutation() {
        use std::os::unix::{
            fs::{MetadataExt, symlink},
            net::UnixListener,
        };
        for suffix in ["", "-wal", "-shm", "-journal"] {
            for case in [
                "symlink",
                "hardlink",
                "directory",
                "socket",
                "writable",
                "special",
                "readonly",
            ] {
                let f = Fixture::new();
                let database = f.database();
                let candidate = format!("{database}{suffix}");
                if !suffix.is_empty() {
                    std::fs::write(&database, b"original database").unwrap();
                }
                let target = f.0.join("original");
                std::fs::write(&target, b"preserve original bytes").unwrap();
                let original = std::fs::metadata(&target).unwrap();
                let _socket = if case == "socket" {
                    Some(UnixListener::bind(&candidate).unwrap())
                } else {
                    None
                };
                match case {
                    "symlink" => symlink(&target, &candidate).unwrap(),
                    "hardlink" => std::fs::hard_link(&target, &candidate).unwrap(),
                    "directory" => std::fs::create_dir(&candidate).unwrap(),
                    "socket" => (),
                    _ => {
                        std::fs::write(&candidate, b"preserve candidate").unwrap();
                        let mode = match case {
                            "writable" => 0o622,
                            "special" => 0o4600,
                            _ => 0o400,
                        };
                        std::fs::set_permissions(&candidate, std::fs::Permissions::from_mode(mode))
                            .unwrap();
                    }
                }
                assert!(
                    InstanceGuard::for_database(&database).is_err(),
                    "{suffix} {case}"
                );
                assert_eq!(std::fs::read(&target).unwrap(), b"preserve original bytes");
                assert_eq!(std::fs::metadata(&target).unwrap().ino(), original.ino());
                assert!(std::fs::symlink_metadata(&candidate).is_ok());
                if !suffix.is_empty() {
                    assert_eq!(std::fs::read(&database).unwrap(), b"original database");
                }
            }
        }
    }
    #[test]
    fn sqlite_state_creation_and_recovery_names_are_conservative() {
        for suffix in ["-wal", "-shm", "-journal"] {
            let f = Fixture::new();
            std::fs::write(format!("{}{suffix}", f.database()), b"unreconciled").unwrap();
            assert!(InstanceGuard::for_database(&f.database()).is_err());
            assert!(!Path::new(&f.database()).exists());
        }
        for name in [
            INSTANCE_LOCK,
            "control.sock",
            "jobs-wal",
            "jobs-shm",
            "jobs-journal",
        ] {
            let f = Fixture::new();
            assert!(InstanceGuard::for_database(f.0.join(name).to_str().unwrap()).is_err());
        }
        let f = Fixture::new();
        let guard = InstanceGuard::for_database(&f.database()).unwrap();
        assert!(!Path::new(&f.database()).exists());
        guard.prepare_database(&f.database()).unwrap();
        assert_eq!(
            std::fs::metadata(f.database())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        std::fs::write(f.database(), b"existing database").unwrap();
        std::fs::set_permissions(f.database(), std::fs::Permissions::from_mode(0o644)).unwrap();
        guard.prepare_database(&f.database()).unwrap();
        assert_eq!(std::fs::read(f.database()).unwrap(), b"existing database");
        assert_eq!(
            std::fs::metadata(f.database())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o644
        );
    }
    #[test]
    fn mount_inventory_decodes_kernel_escapes_and_fails_closed() {
        let mounts = parse_mounts(
            br"42 1 0:2 / /state/a\040b\134c\011d\012e rw - nfs server:/ rw
",
        )
        .unwrap();
        assert_eq!(
            mounts,
            vec![std::path::PathBuf::from("/state/a b\\c\td\ne")]
        );
        for bad in [
            b"".as_slice(),
            b"incomplete",
            br"42 1 0:2 / /state/\099 rw - nfs s rw",
        ] {
            assert!(parse_mounts(bad).is_err());
        }
    }
    #[test]
    fn observation_does_not_create_state_and_distinguishes_held_from_free() {
        let f = Fixture::new();
        assert_eq!(
            instance_ownership(&f.database()).unwrap(),
            InstanceOwnership::Absent
        );
        assert!(!f.0.join(INSTANCE_LOCK).exists());
        let g = InstanceGuard::for_database(&f.database()).unwrap();
        assert_eq!(
            instance_ownership(&f.database()).unwrap(),
            InstanceOwnership::Held
        );
        g.validate().unwrap();
        drop(g);
        assert_eq!(
            instance_ownership(&f.database()).unwrap(),
            InstanceOwnership::Free
        );
        assert_eq!(std::fs::read(f.0.join(INSTANCE_LOCK)).unwrap(), b"");
        assert!(!f.0.join("jobs.sqlite").exists());
    }
    #[test]
    fn transferred_description_preserves_exclusion_and_releases_only_after_last_holder() {
        let f = Fixture::new();
        let g = InstanceGuard::for_database(&f.database()).unwrap();
        let identity = g.object.clone();
        assert!(InstanceGuard::for_database(&f.database()).is_err());
        let (mut a, mut b) = UnixStream::pair().unwrap();
        let sender = std::thread::spawn(move || g.send(&mut a).unwrap());
        let inherited = InstanceGuard::receive(&mut b).unwrap();
        sender.join().unwrap();
        inherited.validate().unwrap();
        assert!(InstanceGuard::for_database(&f.database()).is_err());
        drop(inherited);
        let next = InstanceGuard::for_database(&f.database()).unwrap();
        assert_eq!(next.object, identity);
        assert_eq!(std::fs::read(f.0.join(INSTANCE_LOCK)).unwrap(), b"");
        assert!(!f.0.join("jobs.sqlite").exists());
    }
    #[test]
    fn concurrent_instance_acquisition_has_exactly_one_winner() {
        let f = Fixture::new();
        drop(InstanceGuard::for_database(&f.database()).unwrap());
        let start = std::sync::Arc::new(std::sync::Barrier::new(8));
        let finish = std::sync::Arc::new(std::sync::Barrier::new(8));
        let mut tasks = Vec::new();
        for _ in 0..8 {
            let db = f.database();
            let a = start.clone();
            let b = finish.clone();
            tasks.push(std::thread::spawn(move || {
                a.wait();
                let guard = InstanceGuard::for_database(&db);
                let won = guard.is_ok();
                b.wait();
                drop(guard);
                won
            }));
        }
        assert_eq!(
            tasks
                .into_iter()
                .map(|t| t.join().unwrap())
                .filter(|won| *won)
                .count(),
            1
        );
    }
    #[test]
    fn unsafe_guards_are_preserved_and_named_replacement_invalidates_holder() {
        for case in [
            "mode",
            "content",
            "symlink",
            "hardlink",
            "directory",
            "parent",
        ] {
            let f = Fixture::new();
            drop(InstanceGuard::for_database(&f.database()).unwrap());
            let path = f.0.join(INSTANCE_LOCK);
            match case {
                "mode" => {
                    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap()
                }
                "content" => std::fs::write(&path, b"preserve this").unwrap(),
                "symlink" => {
                    std::fs::rename(&path, f.0.join("original")).unwrap();
                    std::os::unix::fs::symlink("original", &path).unwrap();
                }
                "hardlink" => std::fs::hard_link(&path, f.0.join("alias")).unwrap(),
                "directory" => {
                    std::fs::remove_file(&path).unwrap();
                    std::fs::create_dir(&path).unwrap();
                }
                "parent" => {
                    std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o755)).unwrap()
                }
                _ => unreachable!(),
            }
            assert!(
                InstanceGuard::for_database(&f.database()).is_err(),
                "{case}"
            );
            assert!(!f.0.join("jobs.sqlite").exists());
            if case == "content" {
                assert_eq!(std::fs::read(path).unwrap(), b"preserve this");
            }
        }
        let f = Fixture::new();
        let g = InstanceGuard::for_database(&f.database()).unwrap();
        std::fs::rename(f.0.join(INSTANCE_LOCK), f.0.join("old")).unwrap();
        assert!(g.validate().is_err());
        assert!(!f.0.join(INSTANCE_LOCK).exists());
    }
    #[test]
    fn worker_prefix_rejects_missing_extra_unlocked_and_wrong_scope_descriptors() {
        for case in [
            "missing", "extra", "unlocked", "version", "scope", "readonly",
        ] {
            let f = Fixture::new();
            let g = InstanceGuard::for_database(&f.database()).unwrap();
            let mut proof = Proof {
                version: 1,
                directory: g.directory.clone(),
                parent: g.parent.encode(),
                object: g.object.encode(),
            };
            if case == "version" {
                proof.version = 2;
            }
            if case == "scope" {
                proof.object = proof.parent.clone();
            }
            let bytes = serde_json::to_vec(&proof).unwrap();
            let file = std::fs::OpenOptions::new()
                .read(true)
                .write(case != "readonly")
                .open(f.0.join(INSTANCE_LOCK))
                .unwrap();
            let fd = if case == "unlocked" || case == "readonly" {
                file.as_fd()
            } else {
                g.held.as_fd()
            };
            let descriptors = if case == "missing" {
                vec![]
            } else if case == "extra" {
                vec![fd, fd]
            } else {
                vec![fd]
            };
            let (mut a, mut b) = UnixStream::pair().unwrap();
            let mut space = [MaybeUninit::uninit(); rustix::cmsg_space!(ScmRights(2))];
            let mut control = SendAncillaryBuffer::new(&mut space);
            if !descriptors.is_empty() {
                assert!(control.push(SendAncillaryMessage::ScmRights(&descriptors)));
            }
            net::sendmsg(&a, &[IoSlice::new(b"I")], &mut control, SendFlags::NOSIGNAL).unwrap();
            a.write_all(&(bytes.len() as u32).to_be_bytes()).unwrap();
            a.write_all(&bytes).unwrap();
            drop(descriptors);
            if case == "unlocked" {
                drop(g);
            }
            assert!(InstanceGuard::receive(&mut b).is_err(), "{case}");
        }
    }
}
