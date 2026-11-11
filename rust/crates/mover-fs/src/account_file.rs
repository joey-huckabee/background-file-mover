//! Offline, cooperative account-file custody. No record parsing or secret logging.
//! Callers retain InstanceGuard through this object's closure. Same-UID/root
//! hostile mutation is outside the existing local custody boundary.
use super::credentials::{check_file, local, parent_directory, parts, unchanged};
use super::*;
use std::{
    io::{Read, Write},
    path::{Path, PathBuf},
};

const ACCOUNT: &str = "admin-account.json";
const NEXT: &str = "admin-account.next";
const LOCK: &str = "account.lock";
const LIMIT: usize = 8192;
const WRITE: OFlags = OFlags::RDWR
    .union(OFlags::NOFOLLOW)
    .union(OFlags::NONBLOCK)
    .union(OFlags::CLOEXEC);
const PRIVATE: Mode = Mode::RUSR.union(Mode::WUSR);

pub struct AccountDirectory {
    directory: OwnedFd,
    path: PathBuf,
    original: Stat,
    lock: OwnedFd,
    lock_original: Stat,
    uid: u32,
    gid: u32,
    #[cfg(test)]
    fault: std::cell::Cell<Option<Fault>>,
}

fn same_inode(a: &Stat, b: &Stat) -> bool {
    a.st_dev == b.st_dev && a.st_ino == b.st_ino
}
fn named(directory: &OwnedFd, name: &str) -> Result<Option<Stat>> {
    match fs::statat(directory, name, AtFlags::SYMLINK_NOFOLLOW) {
        Ok(stat) => Ok(Some(stat)),
        Err(Errno::NOENT) => Ok(None),
        Err(error) => Err(error.into()),
    }
}
fn mounts(path: &Path) -> Result<()> {
    super::instance::ingress_local(path)?;
    for name in [ACCOUNT, NEXT, LOCK] {
        super::instance::ingress_local(&path.join(name))?;
    }
    Ok(())
}

/// Open a precreated private directory outside all supplied scopes. Exclusions
/// are canonical absolute file/directory paths; overlap is rejected both ways.
/// The separate persistent lock is never unlinked, replaced or explicitly unlocked.
pub fn open(directory: &str, excluded: &[String]) -> Result<AccountDirectory> {
    let (path, _) = parts(&format!("{directory}/{ACCOUNT}"), LIMIT)?;
    for exclusion in excluded {
        if !exclusion.starts_with('/')
            || exclusion.len() > 4095
            || (exclusion != "/"
                && exclusion[1..].split('/').any(|p| {
                    p.is_empty()
                        || p == "."
                        || p == ".."
                        || p.contains('\\')
                        || p.chars().any(char::is_control)
                }))
        {
            return Err(ClaimError::Blocked("invalid account exclusion"));
        }
        let exclusion = Path::new(exclusion);
        if path.starts_with(exclusion) || exclusion.starts_with(&path) {
            return Err(ClaimError::Blocked(
                "account directory overlaps excluded scope",
            ));
        }
    }
    let (uid, gid) = super::ingress::local_user_ids();
    if uid == 0 || gid == 0 {
        return Err(ClaimError::Blocked("non-root account custody required"));
    }
    // All fixed leaves are checked before any named stat/open/create.
    mounts(&path)?;
    let directory = parent_directory(&path, uid, gid)?;
    let original = fs::fstat(&directory)?;
    if named(&directory, NEXT)?.is_some() {
        return Err(ClaimError::Blocked(
            "account staging exists; preserve and review",
        ));
    }
    let before = named(&directory, LOCK)?;
    if let Some(stat) = &before {
        check_file(stat, 0, true, uid)?;
    }
    let flags = if before.is_some() {
        WRITE
    } else {
        WRITE | OFlags::CREATE | OFlags::EXCL
    };
    let lock = fs::openat(&directory, LOCK, flags, PRIVATE)?;
    let lock_original = fs::fstat(&lock)?;
    check_file(&lock_original, 0, true, uid)?;
    local(&lock)?;
    if lock_original.st_dev != original.st_dev
        || before
            .as_ref()
            .is_some_and(|stat| !unchanged(stat, &lock_original))
    {
        return Err(ClaimError::Blocked("account lock custody changed"));
    }
    fs::flock(&lock, fs::FlockOperation::NonBlockingLockExclusive)?;
    let account = AccountDirectory {
        directory,
        path,
        original,
        lock,
        lock_original,
        uid,
        gid,
        #[cfg(test)]
        fault: std::cell::Cell::new(None),
    };
    account.validate(None)?;
    if before.is_none() {
        fs::fsync(&account.lock)?;
        fs::fsync(&account.directory)?;
    }
    // Refuse an unsafe existing account during open as well as during read.
    account.read()?;
    Ok(account)
}

impl AccountDirectory {
    pub fn open(directory: &str, excluded: &[String]) -> Result<Self> {
        open(directory, excluded)
    }

    fn validate(&self, staging: Option<&Stat>) -> Result<()> {
        mounts(&self.path)?;
        let reopened = parent_directory(&self.path, self.uid, self.gid)?;
        let held = fs::fstat(&self.directory)?;
        if !same_inode(&self.original, &held)
            || !same_inode(&held, &fs::fstat(&reopened)?)
            || held.st_mode != self.original.st_mode
            || held.st_uid != self.uid
            || held.st_gid != self.gid
            || super::ingress::local_user_ids() != (self.uid, self.gid)
        {
            return Err(ClaimError::Blocked("account parent custody changed"));
        }
        local(&self.directory)?;
        let lock = fs::fstat(&self.lock)?;
        check_file(&lock, 0, true, self.uid)?;
        let lock_name = named(&self.directory, LOCK)?
            .ok_or(ClaimError::Blocked("account lock name missing"))?;
        if !unchanged(&self.lock_original, &lock) || !unchanged(&lock, &lock_name) {
            return Err(ClaimError::Blocked("account lock name changed"));
        }
        match (staging, named(&self.directory, NEXT)?) {
            (None, None) => (),
            (Some(expected), Some(actual)) if unchanged(expected, &actual) => (),
            _ => return Err(ClaimError::Blocked("account staging custody refused")),
        }
        Ok(())
    }

    fn read_named(&self) -> Result<Option<(Vec<u8>, Stat)>> {
        let Some(before) = named(&self.directory, ACCOUNT)? else {
            return Ok(None);
        };
        check_file(&before, LIMIT, true, self.uid)?;
        if before.st_dev != self.original.st_dev {
            return Err(ClaimError::Blocked("account device changed"));
        }
        let fd = fs::openat(&self.directory, ACCOUNT, FILE, Mode::empty())?;
        let opened = fs::fstat(&fd)?;
        check_file(&opened, LIMIT, true, self.uid)?;
        local(&fd)?;
        if !unchanged(&before, &opened) {
            return Err(ClaimError::Blocked("account changed during open"));
        }
        let mut file = std::fs::File::from(fd);
        let mut bytes = Vec::new();
        (&mut file)
            .take((LIMIT + 1) as u64)
            .read_to_end(&mut bytes)
            .map_err(|_| ClaimError::Blocked("account read refused"))?;
        let after = fs::fstat(&file)?;
        let final_name = named(&self.directory, ACCOUNT)?
            .ok_or(ClaimError::Blocked("account disappeared during read"))?;
        if bytes.len() > LIMIT
            || bytes.len() as u64 != opened.st_size as u64
            || !unchanged(&opened, &after)
            || !unchanged(&after, &final_name)
        {
            return Err(ClaimError::Blocked("account changed during read"));
        }
        Ok(Some((bytes, after)))
    }

    pub fn read(&self) -> Result<Option<Vec<u8>>> {
        self.validate(None)?;
        let result = self.read_named()?;
        self.validate(None)?;
        Ok(result.map(|(bytes, _)| bytes))
    }

    /// Publish opaque bounded bytes. None is no-clobber initialization; Some
    /// requires exact old bytes and stable custody through replacement preflight.
    /// OutcomeUncertain requires review, never automatic restore/retry/adoption.
    pub fn publish(&self, bytes: &[u8], expected: Option<&[u8]>) -> Result<()> {
        if bytes.len() > LIMIT || expected.is_some_and(|old| old.len() > LIMIT) {
            return Err(ClaimError::Blocked("account contents exceed bound"));
        }
        self.validate(None)?;
        let old = self.read_named()?;
        if old.as_ref().map(|(bytes, _)| bytes.as_slice()) != expected {
            return Err(ClaimError::Blocked("account expected contents differ"));
        }
        let stage = fs::openat(
            &self.directory,
            NEXT,
            WRITE | OFlags::CREATE | OFlags::EXCL,
            PRIVATE,
        )?;
        let mut file = std::fs::File::from(stage);
        // Capture the actual created inode even if later mode/write/sync checks fail.
        let created = fs::fstat(&file)?;
        let prepared = (|| -> Result<Stat> {
            check_file(&created, LIMIT, true, self.uid)?;
            local(&file)?;
            if created.st_dev != self.original.st_dev {
                return Err(ClaimError::Blocked("account staging device changed"));
            }
            file.write_all(bytes)
                .map_err(|_| ClaimError::Blocked("account write refused"))?;
            #[cfg(test)]
            self.fail(Fault::FileSync)?;
            fs::fsync(&file)?;
            let ready = fs::fstat(&file)?;
            check_file(&ready, LIMIT, true, self.uid)?;
            self.validate(Some(&ready))?;
            let current = self.read_named()?;
            if current.as_ref().map(|(bytes, _)| bytes.as_slice()) != expected
                || match (&old, &current) {
                    (Some((_, a)), Some((_, b))) => !unchanged(a, b),
                    (None, None) => false,
                    _ => true,
                }
            {
                return Err(ClaimError::Blocked("account changed before publication"));
            }
            #[cfg(test)]
            self.fail(Fault::BeforePublish)?;
            self.validate(Some(&ready))?;
            if !unchanged(&ready, &fs::fstat(&file)?) {
                return Err(ClaimError::Blocked("account staging changed"));
            }
            match (&old, named(&self.directory, ACCOUNT)?) {
                (None, None) => (),
                (Some((_, before)), Some(after)) if unchanged(before, &after) => (),
                _ => {
                    return Err(ClaimError::Blocked(
                        "account name changed before publication",
                    ));
                }
            }
            Ok(ready)
        })();
        let ready = match prepared {
            Ok(ready) => ready,
            Err(error) => {
                self.clean_stage(&file, &created)?;
                return Err(error);
            }
        };
        // From the first publication attempt onward preserve evidence on every
        // error. Never clean the staging alias after a possibly completed link.
        let published = (|| -> Result<()> {
            if expected.is_none() {
                fs::linkat(
                    &self.directory,
                    NEXT,
                    &self.directory,
                    ACCOUNT,
                    AtFlags::empty(),
                )?;
                #[cfg(test)]
                self.fail(Fault::AfterPublish)?;
                // link changes ctime/nlink: verify both exact aliases before unlink.
                self.validate_parent_lock_after_link(&file, &ready)?;
                fs::unlinkat(&self.directory, NEXT, AtFlags::empty())?;
            } else {
                fs::renameat(&self.directory, NEXT, &self.directory, ACCOUNT)?;
                #[cfg(test)]
                self.fail(Fault::AfterPublish)?;
            }
            #[cfg(test)]
            self.fail(Fault::ParentSync)?;
            fs::fsync(&self.directory)?;
            self.validate(None)?;
            let (actual, stat) = self.read_named()?.ok_or(ClaimError::OutcomeUncertain)?;
            if actual != bytes || !same_inode(&stat, &ready) {
                return Err(ClaimError::OutcomeUncertain);
            }
            Ok(())
        })();
        published.map_err(|_| ClaimError::OutcomeUncertain)
    }

    fn clean_stage(&self, file: &std::fs::File, created: &Stat) -> Result<()> {
        let held = fs::fstat(file)?;
        // Validate exact owned inode; unknown staging is never removed.
        self.validate(Some(&held))?;
        if !same_inode(created, &held)
            || held.st_nlink != 1
            || held.st_uid != self.uid
            || FileType::from_raw_mode(held.st_mode) != FileType::RegularFile
        {
            return Err(ClaimError::Blocked("account staging cleanup refused"));
        }
        fs::unlinkat(&self.directory, NEXT, AtFlags::empty())?;
        fs::fsync(&self.directory)?;
        Ok(())
    }

    fn validate_parent_lock_after_link(&self, file: &std::fs::File, ready: &Stat) -> Result<()> {
        let held = fs::fstat(file)?;
        // validate accepts the now two-link staging stat but still checks the
        // unchanged persistent lock, parent, mount inventory and exact name.
        self.validate(Some(&held))?;
        let final_name = named(&self.directory, ACCOUNT)?.ok_or(ClaimError::OutcomeUncertain)?;
        if !same_inode(ready, &held)
            || held.st_nlink != 2
            || !unchanged(&held, &final_name)
            || held.st_mode != ready.st_mode
            || held.st_uid != ready.st_uid
            || held.st_gid != ready.st_gid
            || held.st_size != ready.st_size
        {
            return Err(ClaimError::OutcomeUncertain);
        }
        Ok(())
    }

    #[cfg(test)]
    fn fail(&self, point: Fault) -> Result<()> {
        if self.fault.get() == Some(point) {
            return Err(ClaimError::Io(Errno::IO));
        }
        Ok(())
    }
}

#[cfg(test)]
#[derive(Clone, Copy, PartialEq, Eq)]
enum Fault {
    FileSync,
    BeforePublish,
    AfterPublish,
    ParentSync,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{MetadataExt, PermissionsExt, symlink};
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let (uid, gid) = super::super::ingress::local_user_ids();
            assert_ne!(uid, 0, "account tests require non-root gate account");
            assert_ne!(gid, 0, "account tests require non-root primary group");
            let path = std::env::temp_dir().join(format!(
                "account-file-{}-{}",
                std::process::id(),
                NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
        fn open(&self) -> AccountDirectory {
            open(self.0.to_str().unwrap(), &[]).unwrap()
        }
        fn write(&self, name: &str, bytes: &[u8], mode: u32) {
            std::fs::write(self.0.join(name), bytes).unwrap();
            std::fs::set_permissions(self.0.join(name), std::fs::Permissions::from_mode(mode))
                .unwrap();
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn initializes_replaces_and_reopens_exact_bytes_with_persistent_lock() {
        let f = Fixture::new();
        let a = f.open();
        let lock = std::fs::metadata(f.0.join(LOCK)).unwrap().ino();
        assert!(a.read().unwrap().is_none());
        a.publish(b"first\0\xff", None).unwrap();
        assert_eq!(a.read().unwrap().unwrap(), b"first\0\xff");
        a.publish(b"second", Some(b"first\0\xff")).unwrap();
        assert_eq!(a.read().unwrap().unwrap(), b"second");
        assert_eq!(
            std::fs::metadata(f.0.join(ACCOUNT))
                .unwrap()
                .permissions()
                .mode()
                & 0o7777,
            0o600
        );
        assert_eq!(std::fs::metadata(f.0.join(ACCOUNT)).unwrap().nlink(), 1);
        assert!(!f.0.join(NEXT).exists());
        drop(a);
        assert_eq!(f.open().read().unwrap().unwrap(), b"second");
        assert_eq!(std::fs::metadata(f.0.join(LOCK)).unwrap().ino(), lock);
    }

    #[test]
    fn no_clobber_and_stale_expected_preserve_original_without_staging() {
        let f = Fixture::new();
        let a = f.open();
        assert!(a.publish(b"new", Some(b"missing")).is_err());
        a.publish(b"original", None).unwrap();
        let before = std::fs::metadata(f.0.join(ACCOUNT)).unwrap().ino();
        assert!(a.publish(b"other", None).is_err());
        assert!(a.publish(b"other", Some(b"stale")).is_err());
        assert_eq!(a.read().unwrap().unwrap(), b"original");
        assert_eq!(std::fs::metadata(f.0.join(ACCOUNT)).unwrap().ino(), before);
        assert!(!f.0.join(NEXT).exists());
    }

    #[test]
    fn lock_excludes_another_open_and_is_not_replaced_on_release() {
        let f = Fixture::new();
        let a = f.open();
        let inode = std::fs::metadata(f.0.join(LOCK)).unwrap().ino();
        assert!(open(f.0.to_str().unwrap(), &[]).is_err());
        drop(a);
        let _b = f.open();
        assert_eq!(std::fs::metadata(f.0.join(LOCK)).unwrap().ino(), inode);
    }

    #[test]
    fn refuses_staging_leftovers_even_when_the_account_is_absent() {
        let f = Fixture::new();
        f.write(NEXT, b"unknown", 0o600);
        assert!(open(f.0.to_str().unwrap(), &[]).is_err());
        assert_eq!(std::fs::read(f.0.join(NEXT)).unwrap(), b"unknown");
        assert!(!f.0.join(LOCK).exists());
    }

    #[test]
    fn refuses_noncanonical_overlapping_and_unsafe_parent_paths() {
        let f = Fixture::new();
        for path in [
            "relative",
            "/",
            "/tmp/../account",
            "/tmp//account",
            "/tmp/account/",
        ] {
            assert!(open(path, &[]).is_err());
        }
        for excluded in [
            f.0.clone(),
            f.0.parent().unwrap().into(),
            f.0.join("nested"),
        ] {
            assert!(open(f.0.to_str().unwrap(), &[excluded.to_str().unwrap().into()]).is_err());
        }
        assert!(open(f.0.to_str().unwrap(), &["relative".into()]).is_err());
        for mode in [0o750, 0o770, 0o1700] {
            std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(mode)).unwrap();
            assert!(open(f.0.to_str().unwrap(), &[]).is_err());
        }
        std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o700)).unwrap();
        let alias = f.0.join("alias");
        symlink(&f.0, &alias).unwrap();
        assert!(open(alias.to_str().unwrap(), &[]).is_err());
        assert!(!f.0.join(LOCK).exists());
    }

    #[test]
    fn refuses_account_and_lock_symlinks_hardlinks_modes_and_nonregular_files() {
        for name in [ACCOUNT, LOCK] {
            for kind in 0..5 {
                let f = Fixture::new();
                f.write("original", b"", 0o600);
                let target = f.0.join(name);
                match kind {
                    0 => symlink(f.0.join("original"), &target).unwrap(),
                    1 => std::fs::hard_link(f.0.join("original"), &target).unwrap(),
                    2 => f.write(name, b"", 0o644),
                    3 => std::fs::create_dir(&target).unwrap(),
                    _ => symlink(f.0.join("nonexistent"), &target).unwrap(),
                }
                assert!(open(f.0.to_str().unwrap(), &[]).is_err());
                assert!(std::fs::symlink_metadata(target).is_ok());
            }
        }
        let f = Fixture::new();
        f.write(LOCK, b"nonempty", 0o600);
        assert!(open(f.0.to_str().unwrap(), &[]).is_err());
    }

    #[test]
    fn exact_size_limit_and_oversize_refusal() {
        let f = Fixture::new();
        let a = f.open();
        let bytes = vec![42; LIMIT];
        a.publish(&bytes, None).unwrap();
        assert_eq!(a.read().unwrap().unwrap(), bytes);
        assert!(a.publish(&vec![42; LIMIT + 1], Some(&bytes)).is_err());
        assert_eq!(a.read().unwrap().unwrap(), bytes);
        drop(a);
        f.write(ACCOUNT, &vec![42; LIMIT + 1], 0o600);
        assert!(open(f.0.to_str().unwrap(), &[]).is_err());
    }

    #[test]
    fn lock_name_replacement_refuses_without_cleaning_foreign_names() {
        let f = Fixture::new();
        let a = f.open();
        std::fs::rename(f.0.join(LOCK), f.0.join("original-lock")).unwrap();
        f.write(LOCK, b"", 0o600);
        assert!(a.read().is_err());
        assert!(a.publish(b"new", None).is_err());
        assert!(f.0.join("original-lock").exists());
        assert!(f.0.join(LOCK).exists());
        assert!(!f.0.join(ACCOUNT).exists());
    }

    #[test]
    fn cleanup_refuses_a_substituted_staging_inode() {
        let f = Fixture::new();
        let a = f.open();
        let fd = fs::openat(
            &a.directory,
            NEXT,
            WRITE | OFlags::CREATE | OFlags::EXCL,
            PRIVATE,
        )
        .unwrap();
        let file = std::fs::File::from(fd);
        let created = fs::fstat(&file).unwrap();
        std::fs::rename(f.0.join(NEXT), f.0.join("retained-stage")).unwrap();
        f.write(NEXT, b"foreign", 0o600);
        assert!(a.clean_stage(&file, &created).is_err());
        assert_eq!(std::fs::read(f.0.join(NEXT)).unwrap(), b"foreign");
        assert!(f.0.join("retained-stage").exists());
    }

    #[test]
    fn parent_replacement_is_not_followed_or_modified() {
        let f = Fixture::new();
        let other = Fixture::new();
        let a = f.open();
        std::fs::rename(&f.0, other.0.join("original-parent")).unwrap();
        std::fs::create_dir(&f.0).unwrap();
        std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o700)).unwrap();
        assert!(a.read().is_err());
        assert!(a.publish(b"new", None).is_err());
        assert!(!f.0.join(LOCK).exists());
        assert!(!f.0.join(ACCOUNT).exists());
        assert!(other.0.join("original-parent").join(LOCK).exists());
    }

    #[test]
    fn prepublication_faults_clean_only_owned_stage_and_preserve_old_bytes() {
        for replacement in [false, true] {
            for fault in [Fault::FileSync, Fault::BeforePublish] {
                let f = Fixture::new();
                let a = f.open();
                if replacement {
                    a.publish(b"old", None).unwrap();
                }
                a.fault.set(Some(fault));
                let expected = if replacement {
                    Some(b"old".as_slice())
                } else {
                    None
                };
                let result = a.publish(b"new", expected);
                assert!(result.is_err());
                assert!(!matches!(result, Err(ClaimError::OutcomeUncertain)));
                assert!(!f.0.join(NEXT).exists());
                assert_eq!(a.read().unwrap().as_deref(), expected);
            }
        }
    }

    #[test]
    fn postpublication_faults_are_uncertain_and_never_restore_or_adopt() {
        for replacement in [false, true] {
            for fault in [Fault::AfterPublish, Fault::ParentSync] {
                let f = Fixture::new();
                let a = f.open();
                if replacement {
                    a.publish(b"old", None).unwrap();
                }
                a.fault.set(Some(fault));
                let expected = if replacement {
                    Some(b"old".as_slice())
                } else {
                    None
                };
                assert!(matches!(
                    a.publish(b"new", expected),
                    Err(ClaimError::OutcomeUncertain)
                ));
                assert_eq!(std::fs::read(f.0.join(ACCOUNT)).unwrap(), b"new");
                if !replacement && fault == Fault::AfterPublish {
                    assert_eq!(std::fs::metadata(f.0.join(ACCOUNT)).unwrap().nlink(), 2);
                    assert_eq!(std::fs::read(f.0.join(NEXT)).unwrap(), b"new");
                    assert!(a.read().is_err());
                } else {
                    assert!(!f.0.join(NEXT).exists());
                    assert_eq!(std::fs::metadata(f.0.join(ACCOUNT)).unwrap().nlink(), 1);
                }
            }
        }
    }
}
