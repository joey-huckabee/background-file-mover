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
    pub fn for_database(database: &str) -> Result<Self> {
        let directory = Path::new(database)
            .parent()
            .and_then(Path::to_str)
            .ok_or(ClaimError::Blocked("local state parent required"))?;
        let dir = local_parent(directory)?;
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
        Ok(guard)
    }
    fn validate_named(&self) -> Result<()> {
        let dir = local_parent(&self.directory)?;
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
        self.validate()?;
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
        channel.write_all(b"A")?;
        Ok(guard)
    }
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
