//! Local pathname socket custody. No stale-name adoption or repair.
use super::*;
use std::{
    os::unix::net::UnixListener,
    path::{Path, PathBuf},
};

pub fn local_user_ids() -> (u32, u32) {
    (
        rustix::process::geteuid().as_raw(),
        rustix::process::getegid().as_raw(),
    )
}

fn parts(path: &str) -> Result<(PathBuf, String)> {
    if !path.starts_with('/')
        || path.len() > 107
        || path[1..].split('/').any(|p| {
            p.is_empty()
                || p == "."
                || p == ".."
                || p.contains('\\')
                || p.chars().any(char::is_control)
        })
    {
        return Err(ClaimError::Blocked(
            "canonical bounded ingress path required",
        ));
    }
    let path = Path::new(path);
    let parent = path
        .parent()
        .filter(|p| *p != Path::new("/"))
        .ok_or(ClaimError::Blocked("dedicated ingress parent required"))?;
    Ok((
        parent.into(),
        path.file_name()
            .and_then(|s| s.to_str())
            .ok_or(ClaimError::Blocked("ingress name required"))?
            .into(),
    ))
}

fn directory(path: &Path, mode: u32, gid: u32) -> Result<OwnedFd> {
    // Inspect kernel mount metadata before traversing any configured path.
    super::instance::ingress_local(path)?;
    let uid = local_user_ids().0;
    let mut fd = fs::open("/", DIRECTORY, Mode::empty())?;
    for part in path
        .to_str()
        .ok_or(ClaimError::Blocked("UTF-8 ingress parent required"))?[1..]
        .split('/')
    {
        let ancestor = fs::fstat(&fd)?;
        if ![0, uid].contains(&ancestor.st_uid)
            || (ancestor.st_mode & 0o022 != 0
                && !(ancestor.st_uid == 0 && ancestor.st_mode & 0o1000 != 0))
        {
            return Err(ClaimError::Blocked("unsafe ingress ancestor"));
        }
        fd = fs::openat(&fd, part, DIRECTORY, Mode::empty())?;
    }
    let stat = fs::fstat(&fd)?;
    if stat.st_uid != uid
        || stat.st_mode & 0o7777 != mode
        || stat.st_gid != gid
        || ![0xef53, 0x01021994, 0x794c7630].contains(&fs::fstatfs(&fd)?.f_type)
    {
        return Err(ClaimError::Blocked(
            "unsafe ingress parent owner/group/mode/filesystem",
        ));
    }
    Ok(fd)
}

pub struct SocketPlan {
    parent: OwnedFd,
    parent_path: PathBuf,
    name: String,
    parent_mode: u32,
    gid: u32,
    mode: u32,
}
impl SocketPlan {
    pub fn producer(path: &str, gid: u32) -> Result<Self> {
        Self::prepare(path, 0o750, gid, 0o660)
    }
    pub fn operator(path: &str) -> Result<Self> {
        Self::prepare(path, 0o700, local_user_ids().1, 0o600)
    }
    fn prepare(path: &str, parent_mode: u32, gid: u32, mode: u32) -> Result<Self> {
        let (parent_path, name) = parts(path)?;
        let parent = directory(&parent_path, parent_mode, gid)?;
        match fs::statat(&parent, name.as_str(), AtFlags::SYMLINK_NOFOLLOW) {
            Err(Errno::NOENT) => (),
            Err(e) => return Err(e.into()),
            Ok(_) => {
                return Err(ClaimError::Blocked(
                    "ingress endpoint exists; preserve and review stale/foreign endpoint",
                ));
            }
        }
        Ok(Self {
            parent,
            parent_path,
            name,
            parent_mode,
            gid,
            mode,
        })
    }
    pub fn bind(self) -> Result<LocalSocket> {
        // A validated non-writable parent excludes other UIDs. Same-UID/root
        // hostile mutation is outside the existing local custody boundary.
        self.validate_parent()?;
        let path = self.parent_path.join(&self.name);
        let listener = UnixListener::bind(&path).map_err(|_| {
            ClaimError::Blocked("ingress bind refused; existing names are never unlinked")
        })?;
        let stat = fs::statat(&self.parent, self.name.as_str(), AtFlags::SYMLINK_NOFOLLOW)?;
        let socket = LocalSocket {
            plan: self,
            listener,
            device: stat.st_dev,
            inode: stat.st_ino,
        };
        fs::chownat(
            &socket.plan.parent,
            socket.plan.name.as_str(),
            None,
            Some(rustix::process::Gid::from_raw(socket.plan.gid)),
            AtFlags::SYMLINK_NOFOLLOW,
        )?;
        std::fs::set_permissions(
            &path,
            std::os::unix::fs::PermissionsExt::from_mode(socket.plan.mode),
        )
        .map_err(|_| ClaimError::Blocked("ingress socket mode refused"))?;
        socket.validate()?;
        socket
            .listener
            .set_nonblocking(true)
            .map_err(|_| ClaimError::Blocked("ingress nonblocking refused"))?;
        Ok(socket)
    }
    fn validate_parent(&self) -> Result<()> {
        let named = directory(&self.parent_path, self.parent_mode, self.gid)?;
        let expected = fs::fstat(&self.parent)?;
        let actual = fs::fstat(&named)?;
        if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino) {
            return Err(ClaimError::Blocked("ingress parent replaced"));
        }
        Ok(())
    }
}

pub struct LocalSocket {
    plan: SocketPlan,
    listener: UnixListener,
    device: u64,
    inode: u64,
}
impl LocalSocket {
    pub fn listener(&self) -> Result<UnixListener> {
        self.validate()?;
        self.listener
            .try_clone()
            .map_err(|_| ClaimError::Blocked("ingress listener clone refused"))
    }
    pub fn validate(&self) -> Result<()> {
        self.plan.validate_parent()?;
        let s = fs::statat(
            &self.plan.parent,
            self.plan.name.as_str(),
            AtFlags::SYMLINK_NOFOLLOW,
        )?;
        if (s.st_dev, s.st_ino) != (self.device, self.inode)
            || FileType::from_raw_mode(s.st_mode) != FileType::Socket
            || s.st_uid != local_user_ids().0
            || s.st_gid != self.plan.gid
            || s.st_mode & 0o7777 != self.plan.mode
            || s.st_nlink != 1
        {
            return Err(ClaimError::Blocked("ingress endpoint replaced/unsafe"));
        }
        Ok(())
    }
}
impl Drop for LocalSocket {
    fn drop(&mut self) {
        if self.plan.validate_parent().is_ok()
            && fs::statat(
                &self.plan.parent,
                self.plan.name.as_str(),
                AtFlags::SYMLINK_NOFOLLOW,
            )
            .is_ok_and(|s| {
                (s.st_dev, s.st_ino) == (self.device, self.inode)
                    && s.st_uid == local_user_ids().0
                    && FileType::from_raw_mode(s.st_mode) == FileType::Socket
            })
        {
            let _ = fs::unlinkat(&self.plan.parent, self.plan.name.as_str(), AtFlags::empty());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::PermissionsExt;
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "ingress-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
        fn socket(&self) -> String {
            self.0.join("operator.sock").to_str().unwrap().into()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn existing_and_symlink_names_are_preserved() {
        let f = Fixture::new();
        std::fs::write(f.socket(), b"foreign").unwrap();
        assert!(SocketPlan::operator(&f.socket()).is_err());
        assert_eq!(std::fs::read(f.socket()).unwrap(), b"foreign");
        std::fs::remove_file(f.socket()).unwrap();
        std::os::unix::fs::symlink("missing", f.socket()).unwrap();
        assert!(SocketPlan::operator(&f.socket()).is_err());
        assert_eq!(
            std::fs::read_link(f.socket()).unwrap(),
            Path::new("missing")
        );
    }
    #[test]
    fn cleanup_removes_only_original_socket_and_exec_does_not_inherit_it() {
        let f = Fixture::new();
        let socket = SocketPlan::operator(&f.socket()).unwrap().bind().unwrap();
        let listener = socket.listener().unwrap();
        for fd in [socket.listener.as_raw_fd(), listener.as_raw_fd()] {
            let path = format!("/proc/self/fd/{fd}");
            let original = std::fs::read_link(&path).unwrap();
            let child = std::process::Command::new("/usr/bin/readlink")
                .arg(path)
                .output()
                .unwrap();
            assert_ne!(
                String::from_utf8_lossy(&child.stdout).trim(),
                original.to_str().unwrap()
            );
        }
        drop(listener);
        drop(socket);
        assert!(!Path::new(&f.socket()).exists());
        let socket = SocketPlan::operator(&f.socket()).unwrap().bind().unwrap();
        std::fs::rename(f.socket(), f.0.join("original.sock")).unwrap();
        std::fs::write(f.socket(), b"replacement").unwrap();
        assert!(socket.validate().is_err());
        drop(socket);
        assert_eq!(std::fs::read(f.socket()).unwrap(), b"replacement");
    }
    #[test]
    fn parent_alias_and_permissions_refuse_before_binding() {
        let f = Fixture::new();
        std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o750)).unwrap();
        assert!(SocketPlan::operator(&f.socket()).is_err());
        std::fs::set_permissions(&f.0, std::fs::Permissions::from_mode(0o700)).unwrap();
        let alias = f.0.join("alias");
        std::os::unix::fs::symlink(&f.0, &alias).unwrap();
        assert!(SocketPlan::operator(alias.join("x.sock").to_str().unwrap()).is_err());
        assert!(!Path::new(&f.socket()).exists());
    }
}
