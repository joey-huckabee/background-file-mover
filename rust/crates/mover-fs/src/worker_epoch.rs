//! Local process-group lifetime evidence, persisted before any worker spawn.
//! flock may close during exit_files before a hard-NFS task actually exits.
use super::*;
use crate::instance::InstanceGuard;
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::unix::fs::MetadataExt,
    time::{Duration, Instant},
};

pub const WORKER_EPOCH: &str = "workers.json";
pub const WORKER_NEXT: &str = "workers.next";
const LIMIT: u64 = 4096;
static PREPARE: std::sync::Mutex<()> = std::sync::Mutex::new(());

#[derive(Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Epoch {
    version: u32,
    boot: String,
    namespace: String,
    group: u32,
    start: u64,
    guard: String,
}
#[derive(Debug)]
struct Task {
    pid: u32,
    group: u32,
    start: u64,
    exited: bool,
}
fn blocked() -> ClaimError {
    ClaimError::Blocked("worker lifetime evidence unavailable; preserve original state")
}
fn parse_task(bytes: &[u8]) -> Option<Task> {
    let end = bytes.windows(2).rposition(|w| w == b") ")?;
    let pid = std::str::from_utf8(bytes.split(|b| *b == b' ').next()?)
        .ok()?
        .parse()
        .ok()?;
    let fields: Vec<_> = std::str::from_utf8(&bytes[end + 2..])
        .ok()?
        .split_ascii_whitespace()
        .collect();
    if fields.len() < 20
        || fields[0].len() != 1
        || !b"RSDZTtXxKWPI".contains(&fields[0].as_bytes()[0])
    {
        return None;
    }
    Some(Task {
        pid,
        group: fields[2].parse().ok()?,
        start: fields[19].parse().ok()?,
        exited: matches!(fields[0], "Z" | "X" | "x"),
    })
}
fn task(path: &std::path::Path) -> std::io::Result<Task> {
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(8193)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 8192 {
        return Err(std::io::Error::other("oversized process state"));
    }
    parse_task(&bytes).ok_or_else(|| std::io::Error::other("invalid process state"))
}
fn valid_boot(boot: &str) -> bool {
    boot.len() == 36
        && boot.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}
fn valid_namespace(value: &str) -> bool {
    value.split_once(':').is_some_and(|(dev, ino)| {
        dev.parse::<u64>().is_ok() && ino.parse::<u64>().is_ok_and(|v| v != 0)
    })
}
fn environment() -> Result<(String, String)> {
    let mut boot = String::new();
    std::fs::File::open("/proc/sys/kernel/random/boot_id")
        .map_err(|_| blocked())?
        .take(65)
        .read_to_string(&mut boot)
        .map_err(|_| blocked())?;
    let boot = boot.trim();
    if !valid_boot(boot) {
        return Err(blocked());
    }
    let ns = std::fs::metadata("/proc/self/ns/pid").map_err(|_| blocked())?;
    let own = task(std::path::Path::new("/proc/self/stat")).map_err(|_| blocked())?;
    if own.pid != std::process::id() {
        return Err(blocked());
    }
    Ok((boot.into(), format!("{}:{}", ns.dev(), ns.ino())))
}
fn checked_file(dir: &OwnedFd, name: &str) -> Result<Option<OwnedFd>> {
    let fd = match fs::openat(
        dir,
        name,
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
        Mode::empty(),
    ) {
        Ok(fd) => fd,
        Err(Errno::NOENT) => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    let s = fs::fstat(&fd)?;
    if FileType::from_raw_mode(s.st_mode) != FileType::RegularFile
        || s.st_uid != rustix::process::geteuid().as_raw()
        || s.st_mode & 0o7777 != 0o600
        || s.st_nlink != 1
        || s.st_size < 0
        || s.st_size as u64 > LIMIT
        || s.st_dev != fs::fstat(dir)?.st_dev
        || ![0xef53, 0x01021994, 0x794c7630].contains(&fs::fstatfs(&fd)?.f_type)
        || observation(&s) != observation(&fs::statat(dir, name, AtFlags::SYMLINK_NOFOLLOW)?)
    {
        return Err(blocked());
    }
    Ok(Some(fd))
}
fn read(guard: &InstanceGuard) -> Result<Option<Epoch>> {
    let dir = crate::instance::local_parent_for_epoch(guard.state_directory())?;
    // Validate temporary names even for read-only ownership observations.
    let _ = checked_file(&dir, WORKER_NEXT)?;
    let Some(fd) = checked_file(&dir, WORKER_EPOCH)? else {
        return Ok(None);
    };
    let mut bytes = Vec::new();
    std::fs::File::from(fd)
        .take(LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| blocked())?;
    let e: Epoch = serde_json::from_slice(&bytes).map_err(|_| blocked())?;
    if bytes.len() as u64 > LIMIT
        || e.version != 1
        || e.group == 0
        || e.group > i32::MAX as u32
        || e.start == 0
        || e.guard != guard.epoch_identity()
        || !valid_boot(&e.boot)
        || !valid_namespace(&e.namespace)
    {
        return Err(blocked());
    }
    Ok(Some(e))
}
/// Called only after obtaining the physical local flock. A running old group
/// cannot spawn new workers after its coordinator's files are closed. Workers
/// never fork or change process group. Unknown observations conservatively hold.
fn group_alive(e: &Epoch, ignore_self: bool) -> Result<bool> {
    let (boot, namespace) = environment()?;
    if boot != e.boot {
        return Ok(false);
    } // Kernel tasks cannot survive a reboot.
    if namespace != e.namespace {
        return Err(blocked());
    }
    let group = rustix::process::Pid::from_raw(e.group as i32).ok_or_else(blocked)?;
    match rustix::process::test_kill_process_group(group) {
        Err(Errno::SRCH) => return Ok(false),
        Err(_) => return Ok(true),
        Ok(()) => (),
    }
    let deadline = Instant::now() + Duration::from_millis(200);
    let mut count = 0;
    let mut matched = false;
    let entries = std::fs::read_dir("/proc").map_err(|_| blocked())?;
    for entry in entries {
        count += 1;
        if count > 16384 || Instant::now() >= deadline {
            return Ok(true);
        }
        let entry = match entry {
            Ok(v) => v,
            Err(_) => return Ok(true),
        };
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|s| s.parse::<u32>().ok())
        else {
            continue;
        };
        let t = match task(&entry.path().join("stat")) {
            Ok(t) => t,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(_) => return Ok(true),
        };
        if t.pid != pid {
            return Ok(true);
        }
        if t.group != e.group {
            continue;
        }
        matched = true;
        // A same-PID caller can reacquire after a completely drained library use.
        if ignore_self && pid == std::process::id() && pid == e.group && t.start == e.start {
            continue;
        }
        if !t.exited {
            return Ok(true);
        }
        // A zombie leader alone is NOT proof that its other threads exited.
        let threads = match std::fs::read_dir(entry.path().join("task")) {
            Ok(v) => v,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(_) => return Ok(true),
        };
        for thread in threads {
            count += 1;
            if count > 16384 || Instant::now() >= deadline {
                return Ok(true);
            }
            let thread = match thread {
                Ok(v) => v,
                Err(_) => return Ok(true),
            };
            match task(&thread.path().join("stat")) {
                Ok(t) if t.group == e.group && t.exited => (),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                _ => return Ok(true),
            }
        }
    }
    // A group that exists but is invisible must never be treated as exited.
    Ok(!matched && rustix::process::test_kill_process_group(group).is_ok())
}
pub(crate) fn active(guard: &InstanceGuard, ignore_self: bool) -> Result<bool> {
    match read(guard)? {
        Some(e) => group_alive(&e, ignore_self),
        None => Ok(false),
    }
}
pub(crate) fn require_group(guard: &InstanceGuard) -> Result<()> {
    let e = read(guard)?.ok_or_else(blocked)?;
    let (boot, namespace) = environment()?;
    if e.boot != boot
        || e.namespace != namespace
        || e.group != rustix::process::getpgrp().as_raw_pid() as u32
    {
        return Err(blocked());
    }
    Ok(())
}
pub(crate) fn prepare(guard: &InstanceGuard) -> Result<()> {
    let _serial = PREPARE.lock().map_err(|_| blocked())?;
    guard.validate()?;
    let pid = rustix::process::getpid();
    if rustix::process::getpgrp() != pid {
        rustix::process::setpgid(Some(pid), Some(pid))?;
    }
    let own = task(std::path::Path::new("/proc/self/stat")).map_err(|_| blocked())?;
    if own.pid != pid.as_raw_pid() as u32 || own.group != own.pid || own.exited {
        return Err(blocked());
    }
    let (boot, namespace) = environment()?;
    let next = Epoch {
        version: 1,
        boot,
        namespace,
        group: own.pid,
        start: own.start,
        guard: guard.epoch_identity(),
    };
    if let Some(old) = read(guard)? {
        if old == next {
            return Ok(());
        }
        if group_alive(&old, true)? {
            return Err(blocked());
        }
    }
    let dir = crate::instance::local_parent_for_epoch(guard.state_directory())?;
    if checked_file(&dir, WORKER_NEXT)?.is_some() {
        // Before rename+directory sync no worker can have been spawned for this
        // temporary record. The previous published epoch has already drained.
        fs::unlinkat(&dir, WORKER_NEXT, AtFlags::empty())?;
        fs::fsync(&dir)?;
    }
    let fd = fs::openat(
        &dir,
        WORKER_NEXT,
        OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o600),
    )?;
    let mut file = std::fs::File::from(fd);
    file.write_all(&serde_json::to_vec(&next).map_err(|_| blocked())?)
        .map_err(|_| blocked())?;
    file.sync_all().map_err(|_| blocked())?;
    fs::renameat(&dir, WORKER_NEXT, &dir, WORKER_EPOCH)?;
    fs::fsync(&dir)?;
    require_group(guard)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn process_parser_uses_group_start_and_terminal_state_not_descriptor_presence() {
        for state in ["R", "D", "S", "Z", "X", "x"] {
            let line = format!(
                "42 (name ) with spaces) {state} 1 41 1 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 123 0"
            );
            let t = parse_task(line.as_bytes()).unwrap();
            assert_eq!((t.pid, t.group, t.start), (42, 41, 123));
            assert_eq!(t.exited, matches!(state, "Z" | "X" | "x"));
        }
        for bad in ["", "42 (broken", "42 (name) Q 1 41", "x (name) D 1 41"] {
            assert!(parse_task(bad.as_bytes()).is_none());
        }
    }
    struct Fixture(std::path::PathBuf);
    impl Fixture {
        fn new() -> Self {
            static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
            use std::os::unix::fs::PermissionsExt;
            let path = std::env::temp_dir().join(format!(
                "epoch-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
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
    fn live_group_member_blocks_reacquisition_without_any_inherited_guard() {
        let f = Fixture::new();
        let guard = InstanceGuard::for_database(&f.database()).unwrap();
        guard.prepare_workers().unwrap();
        let mut child = std::process::Command::new("/bin/sleep")
            .arg("30")
            .spawn()
            .unwrap();
        drop(guard);
        let dir = crate::instance::local_parent_for_epoch(f.0.to_str().unwrap()).unwrap();
        let fd = fs::openat(
            &dir,
            crate::INSTANCE_LOCK,
            OFlags::RDWR | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .unwrap();
        fs::flock(&fd, fs::FlockOperation::NonBlockingLockExclusive).unwrap();
        drop(fd); // Physical lock is free, yet the unguarded child must exclude a new start.
        assert!(InstanceGuard::for_database(&f.database()).is_err());
        assert_eq!(
            crate::instance_ownership(&f.database()).unwrap(),
            crate::InstanceOwnership::Held
        );
        child.kill().unwrap();
        child.wait().unwrap();
        let next = InstanceGuard::for_database(&f.database()).unwrap();
        next.prepare_workers().unwrap();
    }
    #[test]
    fn unsafe_or_corrupt_epoch_refuses_without_repair_or_database_creation() {
        use std::os::unix::fs::{PermissionsExt, symlink};
        for name in [WORKER_EPOCH, WORKER_NEXT] {
            for case in [
                "mode",
                "symlink",
                "hardlink",
                "directory",
                "oversized",
                "malformed",
                "version",
                "scope",
                "namespace",
            ] {
                let f = Fixture::new();
                let guard = InstanceGuard::for_database(&f.database()).unwrap();
                guard.prepare_workers().unwrap();
                let record = f.0.join(WORKER_EPOCH);
                let mut e: Epoch =
                    serde_json::from_slice(&std::fs::read(&record).unwrap()).unwrap();
                drop(guard);
                let target = f.0.join(name);
                if target.exists() {
                    std::fs::remove_file(&target).unwrap();
                }
                let original = f.0.join("original");
                std::fs::write(&original, b"preserve").unwrap();
                match case {
                    "symlink" => symlink(&original, &target).unwrap(),
                    "hardlink" => std::fs::hard_link(&original, &target).unwrap(),
                    "directory" => std::fs::create_dir(&target).unwrap(),
                    _ => {
                        match case {
                            "version" => e.version = 2,
                            "scope" => e.guard = "foreign".into(),
                            "namespace" => e.namespace = "invalid".into(),
                            _ => (),
                        }
                        let bytes = if case == "oversized" {
                            vec![b'x'; LIMIT as usize + 1]
                        } else if case == "malformed" {
                            b"broken".to_vec()
                        } else {
                            serde_json::to_vec(&e).unwrap()
                        };
                        std::fs::write(&target, bytes).unwrap();
                        std::fs::set_permissions(
                            &target,
                            std::fs::Permissions::from_mode(if case == "mode" {
                                0o644
                            } else {
                                0o600
                            }),
                        )
                        .unwrap();
                    }
                }
                // Incomplete temporary JSON is intentionally allowed: no dispatch
                // can precede its atomic publication. Test semantic corruption on main only.
                if name == WORKER_NEXT
                    && ["malformed", "version", "scope", "namespace"].contains(&case)
                {
                    continue;
                }
                let before = std::fs::symlink_metadata(&target).unwrap();
                assert!(
                    InstanceGuard::for_database(&f.database()).is_err(),
                    "{name}/{case}"
                );
                assert!(
                    crate::instance_ownership(&f.database()).is_err(),
                    "{name}/{case}"
                );
                let after = std::fs::symlink_metadata(&target).unwrap();
                assert_eq!(
                    (before.dev(), before.ino(), before.mode(), before.len()),
                    (after.dev(), after.ino(), after.mode(), after.len())
                );
                assert_eq!(std::fs::read(&original).unwrap(), b"preserve");
                assert!(!f.0.join("jobs.sqlite").exists());
            }
        }
    }
    #[test]
    fn interrupted_unpublished_epoch_is_replaced_only_after_old_group_drains() {
        use std::os::unix::fs::PermissionsExt;
        let f = Fixture::new();
        let guard = InstanceGuard::for_database(&f.database()).unwrap();
        let temporary = f.0.join(WORKER_NEXT);
        std::fs::write(&temporary, b"{partial").unwrap();
        std::fs::set_permissions(&temporary, std::fs::Permissions::from_mode(0o600)).unwrap();
        guard.prepare_workers().unwrap();
        assert!(!temporary.exists());
        assert!(f.0.join(WORKER_EPOCH).is_file());
        require_group(&guard).unwrap();
        assert!(!f.0.join("jobs.sqlite").exists());
    }
}
