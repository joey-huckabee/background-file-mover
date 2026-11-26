//! Diagnostic-file custody only. Never opens payload or durable-state objects.
use super::credentials::{local, parent_directory, parts, unchanged};
use super::*;
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom, Write},
    path::PathBuf,
};

const HEADER: &[u8] = b"file-mover-log-v1\n";
const PRIVATE: Mode = Mode::RUSR.union(Mode::WUSR);
const OPEN: OFlags = OFlags::RDWR
    .union(OFlags::APPEND)
    .union(OFlags::NOFOLLOW)
    .union(OFlags::NONBLOCK)
    .union(OFlags::CLOEXEC);

pub struct LogFile {
    directory: OwnedFd,
    path: PathBuf,
    original: Stat,
    lock: OwnedFd,
    lock_stat: Stat,
    name: String,
    file: File,
    limit: u64,
    files: u32,
    uid: u32,
    gid: u32,
}
fn named(dir: &OwnedFd, name: &str) -> Result<Option<Stat>> {
    match fs::statat(dir, name, AtFlags::SYMLINK_NOFOLLOW) {
        Ok(s) => Ok(Some(s)),
        Err(Errno::NOENT) => Ok(None),
        Err(e) => Err(e.into()),
    }
}
fn safe(s: &Stat, uid: u32, gid: u32, limit: u64) -> Result<()> {
    if FileType::from_raw_mode(s.st_mode) != FileType::RegularFile
        || s.st_uid != uid
        || s.st_gid != gid
        || s.st_nlink != 1
        || s.st_mode & 0o7777 != 0o600
        || s.st_size < 0
        || s.st_size as u64 > limit
    {
        return Err(ClaimError::Blocked("unsafe diagnostic file"));
    }
    Ok(())
}
fn open_named(
    dir: &OwnedFd,
    name: &str,
    uid: u32,
    gid: u32,
    limit: u64,
    header: bool,
) -> Result<File> {
    let before = named(dir, name)?;
    if let Some(s) = &before {
        safe(s, uid, gid, limit)?;
    }
    let flags = if before.is_some() {
        OPEN
    } else {
        OPEN | OFlags::CREATE | OFlags::EXCL
    };
    let fd = fs::openat(dir, name, flags, PRIVATE)?;
    let stat = fs::fstat(&fd)?;
    safe(&stat, uid, gid, limit)?;
    local(&fd)?;
    if before.as_ref().is_some_and(|s| !unchanged(s, &stat)) {
        return Err(ClaimError::Blocked("diagnostic name changed"));
    }
    let mut file = File::from(fd);
    if header {
        if before.is_none() {
            file.write_all(HEADER)
                .map_err(|_| ClaimError::Blocked("diagnostic header write failed"))?;
        } else {
            let mut bytes = [0; HEADER.len()];
            file.read_exact(&mut bytes)
                .map_err(|_| ClaimError::Blocked("unmanaged diagnostic file"))?;
            if bytes.as_slice() != HEADER {
                return Err(ClaimError::Blocked("unmanaged diagnostic file"));
            }
        }
    }
    Ok(file)
}
impl LogFile {
    pub fn open(path: &str, limit: u64, files: u32) -> Result<Self> {
        if !(65536..=1073741824).contains(&limit)
            || !(1..=20).contains(&files)
            || limit
                .checked_mul(u64::from(files))
                .is_none_or(|n| n > 1073741824)
        {
            return Err(ClaimError::Blocked("invalid diagnostic budget"));
        }
        let (parent, name) = parts(path, 1)?;
        if name.len() > 240 || path.len() + 5 > 4095 {
            return Err(ClaimError::Blocked("diagnostic name too long"));
        }
        let (uid, gid) = super::ingress::local_user_ids();
        if uid == 0 || gid == 0 {
            return Err(ClaimError::Blocked("non-root diagnostic custody required"));
        }
        // Inspect every managed leaf before any named filesystem I/O.
        super::instance::ingress_local(&parent)?;
        for leaf in std::iter::once(name.clone())
            .chain((1..files).map(|i| format!("{name}.{i}")))
            .chain(std::iter::once(format!("{name}.lock")))
        {
            super::instance::ingress_local(&parent.join(leaf))?;
        }
        let directory = parent_directory(&parent, uid, gid)?;
        let original = fs::fstat(&directory)?;
        let lock = open_named(&directory, &format!("{name}.lock"), uid, gid, 0, false)?;
        fs::flock(&lock, fs::FlockOperation::NonBlockingLockExclusive)?;
        let lock: OwnedFd = lock.into();
        let lock_stat = fs::fstat(&lock)?;
        let file = open_named(&directory, &name, uid, gid, limit, true)?;
        let result = Self {
            directory,
            path: parent,
            original,
            lock,
            lock_stat,
            name,
            file,
            limit,
            files,
            uid,
            gid,
        };
        result.validate()?;
        result.validate_archives()?;
        Ok(result)
    }
    fn validate(&self) -> Result<()> {
        let parent = parent_directory(&self.path, self.uid, self.gid)?;
        let actual = fs::fstat(&parent)?;
        if actual.st_dev != self.original.st_dev || actual.st_ino != self.original.st_ino {
            return Err(ClaimError::Blocked("diagnostic parent changed"));
        }
        let held = fs::fstat(&self.lock)?;
        let named_lock = named(&self.directory, &format!("{}.lock", self.name))?
            .ok_or(ClaimError::Blocked("diagnostic lock missing"))?;
        if !unchanged(&held, &self.lock_stat) || !unchanged(&held, &named_lock) {
            return Err(ClaimError::Blocked("diagnostic lock changed"));
        }
        let active = named(&self.directory, &self.name)?
            .ok_or(ClaimError::Blocked("diagnostic file missing"))?;
        let held = fs::fstat(&self.file)?;
        safe(&held, self.uid, self.gid, self.limit)?;
        if !unchanged(&active, &held) {
            return Err(ClaimError::Blocked("diagnostic file changed"));
        }
        Ok(())
    }
    fn validate_mounts(&self) -> Result<()> {
        for name in std::iter::once(self.name.clone())
            .chain((1..self.files).map(|i| format!("{}.{i}", self.name)))
            .chain(std::iter::once(format!("{}.lock", self.name)))
        {
            super::instance::ingress_local(&self.path.join(name))?;
        }
        Ok(())
    }
    fn validate_archives(&self) -> Result<Vec<(String, Stat)>> {
        let mut snapshots = Vec::new();
        for index in 1..self.files {
            let name = format!("{}.{index}", self.name);
            if let Some(stat) = named(&self.directory, &name)? {
                let file =
                    open_named(&self.directory, &name, self.uid, self.gid, self.limit, true)?;
                if !unchanged(&stat, &fs::fstat(&file)?) {
                    return Err(ClaimError::Blocked("diagnostic archive changed"));
                }
                snapshots.push((name, stat));
            }
        }
        Ok(snapshots)
    }
    fn rotate(&mut self) -> Result<()> {
        self.validate()?;
        self.validate_mounts()?;
        let archives = self.validate_archives()?;
        for index in (1..self.files).rev() {
            let name = format!("{}.{index}", self.name);
            if let Some((_, stat)) = archives.iter().find(|(n, _)| n == &name) {
                let current = named(&self.directory, &name)?
                    .ok_or(ClaimError::Blocked("diagnostic archive missing"))?;
                if !unchanged(stat, &current) {
                    return Err(ClaimError::Blocked("diagnostic archive substituted"));
                }
                if index == self.files - 1 {
                    fs::unlinkat(&self.directory, &name, AtFlags::empty())?;
                } else {
                    fs::renameat_with(
                        &self.directory,
                        &name,
                        &self.directory,
                        format!("{}.{next}", self.name, next = index + 1),
                        RenameFlags::NOREPLACE,
                    )?;
                }
            }
        }
        self.validate()?;
        if self.files == 1 {
            fs::unlinkat(&self.directory, &self.name, AtFlags::empty())?;
        } else {
            fs::renameat_with(
                &self.directory,
                &self.name,
                &self.directory,
                format!("{}.1", self.name),
                RenameFlags::NOREPLACE,
            )?;
        }
        self.file = open_named(
            &self.directory,
            &self.name,
            self.uid,
            self.gid,
            self.limit,
            true,
        )?;
        Ok(())
    }
    pub fn append(&mut self, line: &[u8]) -> Result<()> {
        if line.len() > 1024 {
            return Err(ClaimError::Blocked("diagnostic record too large"));
        }
        self.validate()?;
        if self
            .file
            .metadata()
            .map_err(|_| ClaimError::Blocked("diagnostic stat failed"))?
            .len()
            + line.len() as u64
            > self.limit
        {
            self.rotate()?;
        }
        // A crash may leave a partial final line. Separate it from the next record.
        let length = self
            .file
            .metadata()
            .map_err(|_| ClaimError::Blocked("diagnostic stat failed"))?
            .len();
        if length > 0 {
            self.file
                .seek(SeekFrom::End(-1))
                .map_err(|_| ClaimError::Blocked("diagnostic seek failed"))?;
            let mut last = [0];
            self.file
                .read_exact(&mut last)
                .map_err(|_| ClaimError::Blocked("diagnostic read failed"))?;
            if last != *b"\n" {
                if length + line.len() as u64 + 1 > self.limit {
                    self.rotate()?;
                } else {
                    self.file
                        .write_all(b"\n")
                        .map_err(|_| ClaimError::Blocked("diagnostic write failed"))?;
                }
            }
        }
        self.file
            .write_all(line)
            .map_err(|_| ClaimError::Blocked("diagnostic write failed"))?;
        Ok(())
    }
}
/// Clone stderr without a global stdio lock or changing inherited status flags.
pub fn diagnostic_stderr() -> std::io::Result<File> {
    use std::os::fd::AsFd;
    Ok(File::from(std::io::stderr().as_fd().try_clone_to_owned()?))
}
