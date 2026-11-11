//! Read-only local credential custody. Run blocking reads off the executor.
//! No pathname/key bytes enter errors. This does not parse PEM/DER or authorize
//! remote identities; same-UID/root hostile mutation is outside local custody.
use super::*;
use std::{
    io::Read,
    path::{Path, PathBuf},
};

const MAXIMUM: usize = 1024 * 1024;

struct Credential {
    directory: OwnedFd,
    file: OwnedFd,
    parent: PathBuf,
    name: String,
    original: Stat,
    parent_original: Stat,
    uid: u32,
    gid: u32,
}

pub(super) fn parts(path: &str, maximum: usize) -> Result<(PathBuf, String)> {
    if maximum == 0
        || maximum > MAXIMUM
        || !path.starts_with('/')
        || path.len() > 4095
        || path[1..].split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || part.contains('\\')
                || part.chars().any(char::is_control)
        })
    {
        return Err(ClaimError::Blocked("invalid bounded credential input"));
    }
    let path = Path::new(path);
    let parent = path
        .parent()
        .filter(|parent| *parent != Path::new("/"))
        .ok_or(ClaimError::Blocked("dedicated credential parent required"))?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(ClaimError::Blocked("credential name required"))?;
    Ok((parent.into(), name.into()))
}

pub(super) fn local(fd: &impl rustix::fd::AsFd) -> Result<()> {
    // Never enable NFS here, including in qualification builds.
    if ![0xef53, 0x01021994, 0x794c7630].contains(&fs::fstatfs(fd)?.f_type) {
        return Err(ClaimError::Blocked("credential filesystem refused"));
    }
    Ok(())
}

pub(super) fn parent_directory(path: &Path, uid: u32, gid: u32) -> Result<OwnedFd> {
    // Proc mount metadata must be inspected before configured pathname I/O.
    super::instance::ingress_local(path)?;
    let mut directory = fs::open("/", DIRECTORY, Mode::empty())?;
    for part in path
        .to_str()
        .ok_or(ClaimError::Blocked("UTF-8 credential parent required"))?[1..]
        .split('/')
    {
        let ancestor = fs::fstat(&directory)?;
        if ![0, uid].contains(&ancestor.st_uid)
            || (ancestor.st_mode & 0o022 != 0
                && !(ancestor.st_uid == 0 && ancestor.st_mode & 0o1000 != 0))
        {
            return Err(ClaimError::Blocked("unsafe credential ancestor"));
        }
        local(&directory)?;
        directory = fs::openat(&directory, part, DIRECTORY, Mode::empty())?;
    }
    let parent = fs::fstat(&directory)?;
    if parent.st_uid != uid || parent.st_gid != gid || parent.st_mode & 0o7777 != 0o700 {
        return Err(ClaimError::Blocked("unsafe credential parent custody"));
    }
    local(&directory)?;
    Ok(directory)
}

pub(super) fn check_file(stat: &Stat, maximum: usize, private: bool, uid: u32) -> Result<()> {
    let mode = stat.st_mode & 0o7777;
    let allowed_mode = if private {
        mode == 0o600
    } else {
        [0o444, 0o400, 0o600, 0o644].contains(&mode)
    };
    if FileType::from_raw_mode(stat.st_mode) != FileType::RegularFile
        || stat.st_uid != uid
        || stat.st_nlink != 1
        || !allowed_mode
        || !usize::try_from(stat.st_size).is_ok_and(|size| size <= maximum)
    {
        return Err(ClaimError::Blocked("unsafe credential file custody/size"));
    }
    Ok(())
}

// Reading may update atime; content/custody changes must still refuse.
pub(super) fn unchanged(first: &Stat, second: &Stat) -> bool {
    first.st_dev == second.st_dev
        && first.st_ino == second.st_ino
        && first.st_mode == second.st_mode
        && first.st_uid == second.st_uid
        && first.st_gid == second.st_gid
        && first.st_nlink == second.st_nlink
        && first.st_size == second.st_size
        && first.st_mtime == second.st_mtime
        && first.st_mtime_nsec == second.st_mtime_nsec
        && first.st_ctime == second.st_ctime
        && first.st_ctime_nsec == second.st_ctime_nsec
}

fn open(path: &str, maximum: usize, private: bool) -> Result<Credential> {
    let (parent, name) = parts(path, maximum)?;
    let (uid, gid) = super::ingress::local_user_ids();
    if uid == 0 || gid == 0 {
        return Err(ClaimError::Blocked("non-root credential account required"));
    }
    // Also exclude a mount on the leaf itself before stat/open could block.
    super::instance::ingress_local(&parent)?;
    super::instance::ingress_local(Path::new(path))?;
    let directory = parent_directory(&parent, uid, gid)?;
    let parent_original = fs::fstat(&directory)?;
    let named = fs::statat(&directory, name.as_str(), AtFlags::SYMLINK_NOFOLLOW)?;
    check_file(&named, maximum, private, uid)?;
    let file = fs::openat(&directory, name.as_str(), FILE, Mode::empty())?;
    let original = fs::fstat(&file)?;
    check_file(&original, maximum, private, uid)?;
    local(&file)?;
    if !unchanged(&named, &original) {
        return Err(ClaimError::Blocked("credential changed during open"));
    }
    Ok(Credential {
        directory,
        file,
        parent,
        name,
        original,
        parent_original,
        uid,
        gid,
    })
}

/// Read at most `maximum` bytes from one private, owned, local credential file.
/// `maximum` must be 1..=1 MiB. Private files require exact 0600; certificate
/// files allow 0444/0400/0600/0644. Empty contents are left to the format parser.
/// No file creation, permission changes, cleanup, logging or format fallback.
pub fn read(path: &str, maximum: usize, private: bool) -> Result<Vec<u8>> {
    read_opened(open(path, maximum, private)?, maximum, private)
}

fn read_opened(credential: Credential, maximum: usize, private: bool) -> Result<Vec<u8>> {
    let mut file = std::fs::File::from(credential.file);
    let mut bytes = Vec::new();
    (&mut file)
        .take((maximum + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| ClaimError::Blocked("credential read refused"))?;
    if bytes.len() > maximum || bytes.len() as u64 != credential.original.st_size as u64 {
        return Err(ClaimError::Blocked("credential size changed during read"));
    }
    let after = fs::fstat(&file)?;
    check_file(&after, maximum, private, credential.uid)?;
    let named = fs::statat(
        &credential.directory,
        credential.name.as_str(),
        AtFlags::SYMLINK_NOFOLLOW,
    )?;
    let parent = parent_directory(&credential.parent, credential.uid, credential.gid)?;
    if !unchanged(&credential.original, &after)
        || !unchanged(&after, &named)
        || !unchanged(
            &credential.parent_original,
            &fs::fstat(&credential.directory)?,
        )
        || !unchanged(&credential.parent_original, &fs::fstat(&parent)?)
        || super::ingress::local_user_ids() != (credential.uid, credential.gid)
    {
        return Err(ClaimError::Blocked(
            "credential custody changed during read",
        ));
    }
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::{fd::AsRawFd, unix::fs::PermissionsExt};
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let (uid, gid) = super::super::ingress::local_user_ids();
            // The retained SLES gate executes tests as non-root UID/GID 1000.
            assert_ne!(
                uid, 0,
                "credential custody tests require the non-root gate account"
            );
            assert_ne!(
                gid, 0,
                "credential custody tests require a non-root primary group"
            );
            let path = std::env::temp_dir().join(format!(
                "credential-reader-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
        fn path(&self, name: &str) -> String {
            self.0.join(name).to_str().unwrap().into()
        }
        fn write(&self, mode: u32, data: &[u8]) -> String {
            let path = self.path("credential");
            std::fs::write(&path, data).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(mode)).unwrap();
            path
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn reads_exact_bytes_and_public_modes_without_altering_files() {
        let fixture = Fixture::new();
        for mode in [0o444, 0o400, 0o600, 0o644] {
            let path = fixture.write(mode, b"\x00credential\xff\n");
            assert_eq!(read(&path, 13, false).unwrap(), b"\x00credential\xff\n");
            assert_eq!(
                std::fs::metadata(&path).unwrap().permissions().mode() & 0o7777,
                mode
            );
            // Read-only modes must be restored only by the test before rewriting.
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        let path = fixture.write(0o600, b"private");
        assert_eq!(read(&path, 7, true).unwrap(), b"private");
        assert_eq!(std::fs::read(path).unwrap(), b"private");
    }

    #[test]
    fn refuses_invalid_paths_and_bounds_before_filesystem_access() {
        for path in [
            "", "relative", "/", "/file", "/a//b", "/a/./b", "/a/../b", "/a/b/", "/a/b\\c",
            "/a/b\0c",
        ] {
            assert!(read(path, 1, true).is_err());
        }
        assert!(read(&format!("/a/{}", "x".repeat(4096)), 1, false).is_err());
        assert!(read("/nonexistent/credential", 0, true).is_err());
        assert!(read("/nonexistent/credential", MAXIMUM + 1, true).is_err());
    }

    #[test]
    fn rejects_symlink_leaf_and_parent_without_following_them() {
        let fixture = Fixture::new();
        let path = fixture.write(0o600, b"preserved");
        let link = fixture.path("link");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(read(&link, 64, true).is_err());
        let alias = fixture.path("alias");
        std::os::unix::fs::symlink(&fixture.0, &alias).unwrap();
        assert!(read(&format!("{alias}/credential"), 64, true).is_err());
        assert_eq!(std::fs::read(path).unwrap(), b"preserved");
    }

    #[test]
    fn refuses_private_and_certificate_mode_violations_and_nonregular_file() {
        let fixture = Fixture::new();
        for mode in [0o400, 0o444, 0o644, 0o640, 0o660, 0o700, 0o1600] {
            let path = fixture.write(mode, b"preserved");
            assert!(read(&path, 64, true).is_err());
            if ![0o400, 0o444, 0o644].contains(&mode) {
                assert!(read(&path, 64, false).is_err());
            }
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        assert!(read(fixture.0.to_str().unwrap(), 64, false).is_err());
        let socket = fixture.path("socket");
        let _listener = std::os::unix::net::UnixListener::bind(&socket).unwrap();
        assert!(read(&socket, 64, true).is_err());
    }

    #[test]
    fn rejects_parent_modes_and_writable_ancestor() {
        let fixture = Fixture::new();
        let path = fixture.write(0o600, b"preserved");
        for mode in [0o750, 0o770, 0o755, 0o1700] {
            std::fs::set_permissions(&fixture.0, std::fs::Permissions::from_mode(mode)).unwrap();
            assert!(read(&path, 64, true).is_err());
        }
        std::fs::set_permissions(&fixture.0, std::fs::Permissions::from_mode(0o777)).unwrap();
        let inner = fixture.0.join("inner");
        std::fs::create_dir(&inner).unwrap();
        std::fs::set_permissions(&inner, std::fs::Permissions::from_mode(0o700)).unwrap();
        std::fs::write(inner.join("credential"), b"preserved").unwrap();
        std::fs::set_permissions(
            inner.join("credential"),
            std::fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        assert!(read(inner.join("credential").to_str().unwrap(), 64, true).is_err());
    }

    #[test]
    fn rejects_hardlinks_and_oversized_files_with_exact_boundary_success() {
        let fixture = Fixture::new();
        let path = fixture.write(0o600, b"12345678");
        assert!(read(&path, 7, true).is_err());
        assert_eq!(read(&path, 8, true).unwrap(), b"12345678");
        std::fs::hard_link(&path, fixture.path("second")).unwrap();
        assert!(read(&path, 8, true).is_err());
        assert_eq!(std::fs::read(path).unwrap(), b"12345678");
    }

    #[test]
    fn metadata_recheck_detects_same_length_write_and_named_replacement() {
        let fixture = Fixture::new();
        let path = fixture.write(0o600, b"first");
        let original = open(&path, 64, true).unwrap();
        std::fs::rename(&path, fixture.path("original")).unwrap();
        fixture.write(0o600, b"other");
        assert!(read_opened(original, 64, true).is_err());
        let original = open(&path, 64, true).unwrap();
        std::fs::write(&path, b"third").unwrap();
        // Force distinct metadata even on coarse-timestamp filesystems.
        std::fs::File::open(&path)
            .unwrap()
            .set_modified(std::time::SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(1))
            .unwrap();
        assert!(read_opened(original, 64, true).is_err());
    }

    #[test]
    fn credential_and_parent_descriptors_do_not_survive_exec() {
        let fixture = Fixture::new();
        let path = fixture.write(0o600, b"private credential contents");
        let credential = open(&path, 64, true).unwrap();
        for fd in [
            credential.directory.as_raw_fd(),
            credential.file.as_raw_fd(),
        ] {
            let proc_path = format!("/proc/self/fd/{fd}");
            let original = std::fs::read_link(&proc_path).unwrap();
            let child = std::process::Command::new("/usr/bin/readlink")
                .arg(proc_path)
                .output()
                .unwrap();
            assert_ne!(
                String::from_utf8_lossy(&child.stdout).trim(),
                original.to_str().unwrap()
            );
        }
        let diagnostic = read(&path, 1, true).unwrap_err().to_string();
        assert!(!diagnostic.contains(&path));
        assert!(!diagnostic.contains("private credential contents"));
    }
}
