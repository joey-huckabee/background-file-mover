use rustix::fd::{AsRawFd, OwnedFd};
use rustix::fs::{self, AtFlags, FlockOperation, Mode, OFlags, RenameFlags, Stat};
use rustix::io::Errno;
use std::error::Error;
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;

type ProbeResult<T> = Result<T, Box<dyn Error>>;

fn directory(path: &Path) -> rustix::io::Result<OwnedFd> {
    fs::open(
        path,
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
}

fn create(dir: &OwnedFd, name: &str, value: &[u8]) -> ProbeResult<()> {
    let fd = fs::openat(
        dir,
        name,
        OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::RUSR | Mode::WUSR,
    )?;
    let mut file = File::from(fd);
    file.write_all(value)?;
    fs::fsync(&file)?;
    Ok(())
}

fn read(dir: &OwnedFd, name: &str) -> ProbeResult<Vec<u8>> {
    let fd = fs::openat(
        dir,
        name,
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?;
    let mut file = File::from(fd);
    let mut value = Vec::new();
    file.read_to_end(&mut value)?;
    Ok(value)
}

fn identity(a: &Stat, b: &Stat) -> bool {
    a.st_dev == b.st_dev
        && a.st_ino == b.st_ino
        && fs::FileType::from_raw_mode(a.st_mode) == fs::FileType::from_raw_mode(b.st_mode)
}

fn missing(dir: &OwnedFd, name: &str) -> bool {
    matches!(
        fs::statat(dir, name, AtFlags::SYMLINK_NOFOLLOW),
        Err(Errno::NOENT)
    )
}

fn fallback(dir: &OwnedFd, from: &str, to: &str) -> ProbeResult<()> {
    fs::linkat(dir, from, dir, to, AtFlags::empty())?;
    let source = fs::statat(dir, from, AtFlags::SYMLINK_NOFOLLOW)?;
    let destination = fs::statat(dir, to, AtFlags::SYMLINK_NOFOLLOW)?;
    assert!(identity(&source, &destination));
    // Deliberately verify the two-name recovery state before removing the source.
    println!("PASS interrupted link/unlink: both names identify the same inode");
    fs::unlinkat(dir, from, AtFlags::empty())?;
    fs::fsync(dir)?;
    assert!(missing(dir, from));
    Ok(())
}

pub fn exercise(path: &Path, mode: &str) -> ProbeResult<()> {
    if !["rename", "fallback", "enosys", "notsup"].contains(&mode) {
        return Err("invalid move mode".into());
    }
    std::fs::create_dir_all(path)?;
    let dir = directory(path)?;
    let filesystem = fs::fstatfs(&dir)?;
    println!("FILESYSTEM_TYPE {:#x}", filesystem.f_type);
    let uid = rustix::process::getuid().as_raw();
    assert_eq!(uid, 1000, "probe must run unprivileged");
    create(&dir, "original", b"original recording")?;
    let before = fs::statat(&dir, "original", AtFlags::SYMLINK_NOFOLLOW)?;
    let fd = fs::openat(
        &dir,
        "original",
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?;
    let opened = fs::fstat(&fd)?;
    assert!(identity(&before, &opened));
    assert_eq!(opened.st_uid, uid);
    assert_eq!(
        fs::FileType::from_raw_mode(opened.st_mode),
        fs::FileType::RegularFile
    );
    assert!(rustix::io::fcntl_getfd(&fd)?.contains(rustix::io::FdFlags::CLOEXEC));
    let raw = fd.as_raw_fd();
    drop(fd);
    assert!(!Path::new(&format!("/proc/self/fd/{raw}")).exists());
    println!("PASS fd-relative open/stat, trusted UID/type, CLOEXEC, and RAII close");

    fs::symlinkat("original", &dir, "symlink")?;
    assert_eq!(
        fs::openat(
            &dir,
            "symlink",
            OFlags::RDONLY | OFlags::NOFOLLOW,
            Mode::empty()
        )
        .unwrap_err(),
        Errno::LOOP
    );
    fs::mkdirat(&dir, "child", Mode::RWXU)?;
    fs::symlinkat("child", &dir, "directory-link")?;
    assert!(fs::openat(
        &dir,
        "directory-link",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
        Mode::empty()
    )
    .is_err());
    println!("PASS symlink and directory-component traversal rejected");

    // Replace a classified entry deterministically; an opened descriptor keeps
    // its identity, and a newly opened replacement must not match the old stat.
    create(&dir, "race", b"before swap")?;
    let expected = fs::statat(&dir, "race", AtFlags::SYMLINK_NOFOLLOW)?;
    fs::renameat(&dir, "race", &dir, "held-old")?;
    create(&dir, "race", b"after swap")?;
    let replacement = fs::openat(
        &dir,
        "race",
        OFlags::RDONLY | OFlags::NOFOLLOW,
        Mode::empty(),
    )?;
    assert!(!identity(&expected, &fs::fstat(&replacement)?));
    println!("PASS regular-file entry swap detected by descriptor identity");

    let lock = fs::openat(
        &dir,
        "original",
        OFlags::RDWR | OFlags::NOFOLLOW,
        Mode::empty(),
    )?;
    let contender = fs::openat(
        &dir,
        "original",
        OFlags::RDWR | OFlags::NOFOLLOW,
        Mode::empty(),
    )?;
    fs::flock(&lock, FlockOperation::NonBlockingLockExclusive)?;
    assert_eq!(
        fs::flock(&contender, FlockOperation::NonBlockingLockExclusive).unwrap_err(),
        Errno::WOULDBLOCK
    );
    fs::flock(&lock, FlockOperation::Unlock)?;
    fs::flock(&contender, FlockOperation::NonBlockingLockExclusive)?;
    fs::flock(&contender, FlockOperation::Unlock)?;
    println!("PASS advisory lock contention and release");

    create(&dir, "source", b"move payload")?;
    create(&dir, "collision", b"must not overwrite")?;
    if mode == "rename" {
        assert_eq!(
            fs::renameat_with(&dir, "source", &dir, "collision", RenameFlags::NOREPLACE)
                .unwrap_err(),
            Errno::EXIST
        );
        fs::renameat_with(&dir, "source", &dir, "destination", RenameFlags::NOREPLACE)?;
        assert!(missing(&dir, "source"));
        println!("PASS renameat2 NOREPLACE success and collision retention");
    } else {
        if mode == "enosys" || mode == "notsup" {
            let error =
                fs::renameat_with(&dir, "source", &dir, "destination", RenameFlags::NOREPLACE)
                    .unwrap_err();
            assert_eq!(
                error,
                if mode == "enosys" {
                    Errno::NOSYS
                } else {
                    Errno::OPNOTSUPP
                }
            );
            assert!(missing(&dir, "destination"));
            assert_eq!(read(&dir, "source")?, b"move payload");
            println!("PASS injected renameat2 error {error:?} retains source before fallback");
        }
        assert_eq!(
            fs::linkat(&dir, "source", &dir, "collision", AtFlags::empty()).unwrap_err(),
            Errno::EXIST
        );
        assert_eq!(read(&dir, "collision")?, b"must not overwrite");
        fallback(&dir, "source", "destination")?;
        println!("PASS forced link/unlink fallback and collision retention");
    }
    assert_eq!(read(&dir, "destination")?, b"move payload");
    assert_eq!(read(&dir, "collision")?, b"must not overwrite");
    let delivered = fs::openat(&dir, "destination", OFlags::RDONLY, Mode::empty())?;
    fs::fsync(&delivered)?;
    fs::fsync(&dir)?;
    assert!(missing(&dir, "never-existed"));
    fs::unlinkat(&dir, "destination", AtFlags::empty())?;
    assert!(missing(&dir, "destination"));
    fs::fsync(&dir)?;
    println!("PASS file/directory fsync, missing classification, and unlinkat");
    Ok(())
}
