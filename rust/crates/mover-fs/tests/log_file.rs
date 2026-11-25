use mover_fs::log_file::LogFile;
use std::{
    os::unix::fs::{MetadataExt, PermissionsExt, symlink},
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "mover-log-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }
    fn file(&self) -> String {
        self.0.join("service.log").to_str().unwrap().into()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}
fn supported_user() -> bool {
    if mover_fs::effective_uid() == 0 {
        eprintln!("SKIP: private log-file tests require the non-root service UID");
        false
    } else {
        true
    }
}
#[test]
fn logging_file_creation_rotation_and_lock_keep_private_custody() {
    if !supported_user() {
        return;
    }
    let f = Fixture::new();
    let mut log = LogFile::open(&f.file(), 65536, 2).unwrap();
    let stat = std::fs::metadata(f.file()).unwrap();
    assert_eq!(stat.mode() & 0o7777, 0o600);
    assert_eq!(stat.uid(), mover_fs::effective_uid());
    assert_eq!(stat.gid(), std::fs::metadata(&f.0).unwrap().gid());
    assert_eq!(stat.nlink(), 1);
    assert!(LogFile::open(&f.file(), 65536, 2).is_err());
    let line = [b'x'; 1023].into_iter().chain(*b"\n").collect::<Vec<_>>();
    for _ in 0..200 {
        log.append(&line).unwrap();
    }
    for name in ["service.log", "service.log.1"] {
        let path = f.0.join(name);
        let stat = std::fs::metadata(&path).unwrap();
        assert!(stat.len() <= 65536);
        assert_eq!(stat.mode() & 0o7777, 0o600);
        assert!(
            std::fs::read(path)
                .unwrap()
                .starts_with(b"file-mover-log-v1\n")
        );
    }
    assert!(!f.0.join("service.log.2").exists());
    assert_eq!(std::fs::read_dir(&f.0).unwrap().count(), 3);
    drop(log);
    let mut log = LogFile::open(&f.file(), 65536, 2).unwrap();
    log.append(b"after restart\n").unwrap();
    assert!(
        std::fs::read(f.file())
            .unwrap()
            .ends_with(b"after restart\n")
    );
}
#[test]
fn logging_refuses_symlink_modes_hardlinks_and_substituted_names_without_touching_them() {
    if !supported_user() {
        return;
    }
    let f = Fixture::new();
    let target = f.0.join("untouched");
    std::fs::write(&target, b"secret sentinel").unwrap();
    symlink(&target, f.file()).unwrap();
    assert!(LogFile::open(&f.file(), 65536, 2).is_err());
    assert_eq!(std::fs::read(&target).unwrap(), b"secret sentinel");
    std::fs::remove_file(f.file()).unwrap();
    let linked = f.0.join("linked-target");
    std::fs::write(&linked, b"file-mover-log-v1\nprivate data").unwrap();
    std::fs::set_permissions(&linked, std::fs::Permissions::from_mode(0o600)).unwrap();
    std::fs::hard_link(&linked, f.file()).unwrap();
    assert!(LogFile::open(&f.file(), 65536, 2).is_err());
    std::fs::remove_file(f.file()).unwrap();
    std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o755)).unwrap();
    assert!(LogFile::open(&f.file(), 65536, 2).is_err());
    std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o700)).unwrap();
    let alias = Fixture::new();
    let parent = alias.0.join("alias");
    symlink(&f.0, &parent).unwrap();
    assert!(LogFile::open(parent.join("log").to_str().unwrap(), 65536, 2).is_err());
    let mut log = LogFile::open(&f.file(), 65536, 2).unwrap();
    std::fs::rename(f.file(), f.0.join("held")).unwrap();
    std::fs::write(f.file(), b"foreign").unwrap();
    assert!(log.append(b"must not write\n").is_err());
    assert_eq!(std::fs::read(f.file()).unwrap(), b"foreign");
    assert_eq!(std::fs::read(&target).unwrap(), b"secret sentinel");
}
#[test]
fn rotation_preserves_foreign_archive_and_single_file_cap() {
    if !supported_user() {
        return;
    }
    let f = Fixture::new();
    let mut log = LogFile::open(&f.file(), 65536, 2).unwrap();
    let foreign = f.0.join("service.log.1");
    std::fs::write(&foreign, b"foreign archive").unwrap();
    std::fs::set_permissions(&foreign, std::fs::Permissions::from_mode(0o600)).unwrap();
    let line = [b'x'; 1024];
    let mut refused = false;
    for _ in 0..100 {
        if log.append(&line).is_err() {
            refused = true;
            break;
        }
    }
    assert!(refused);
    assert_eq!(std::fs::read(&foreign).unwrap(), b"foreign archive");
    let single = Fixture::new();
    let mut log = LogFile::open(&single.file(), 65536, 1).unwrap();
    for _ in 0..100 {
        log.append(b"a line\n").unwrap();
    }
    for _ in 0..100 {
        log.append(&[b'x'; 1024]).unwrap();
    }
    assert!(std::fs::metadata(single.file()).unwrap().len() <= 65536);
    assert!(!single.0.join("service.log.1").exists());
}
