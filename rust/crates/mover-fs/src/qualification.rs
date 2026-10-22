//! Deterministic fixture rendezvous, compiled out of production.
use super::*;

/// Evict this file's cache only for a selected read-interruption fixture.
/// Advice is not proof of eviction; the runner also checks that the read loop
/// has not completed during the outage. Production never issues this advice.
pub fn before_read(fd: &std::fs::File, operation: &'static str) -> Result<bool> {
    #[cfg(feature = "nfs-qualification")]
    if std::env::var("FILE_MOVER_QUALIFICATION_PAUSE")
        .ok()
        .as_deref()
        == Some(operation)
    {
        fs::fadvise(fd, 0, None, fs::Advice::Random)?;
        fs::fadvise(fd, 0, None, fs::Advice::DontNeed)?;
        pause(operation)?;
        return Ok(true);
    }
    let _ = (fd, operation);
    Ok(false)
}

/// Local fixture observation before any post-read metadata operation.
pub fn after_read(selected: bool) -> Result<()> {
    #[cfg(feature = "nfs-qualification")]
    if selected {
        let path = std::env::var("FILE_MOVER_QUALIFICATION_RENDEZVOUS")
            .map_err(|_| ClaimError::Blocked("qualification rendezvous missing"))?;
        let dir = root(&path)?;
        owned_directory(&dir, true)?;
        if fs::fstatfs(&dir)?.f_type == 0x6969 {
            return Err(ClaimError::Blocked(
                "qualification rendezvous must be local",
            ));
        }
        let _fd = fs::openat(
            &dir,
            "read-completed",
            OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::RUSR | Mode::WUSR,
        )?;
    }
    let _ = selected;
    Ok(())
}

#[cfg(not(feature = "nfs-qualification"))]
pub fn pause(_: &'static str) -> Result<()> {
    Ok(())
}

#[cfg(feature = "nfs-qualification")]
thread_local! {
    static CLAIM_INDEX: std::cell::Cell<Option<usize>> = const { std::cell::Cell::new(None) };
}

/// Scope the fixture's optional zero-based file selector to this claim effect.
#[cfg(feature = "nfs-qualification")]
pub struct ClaimScope(Option<usize>);
#[cfg(feature = "nfs-qualification")]
impl ClaimScope {
    pub fn enter(index: usize) -> Self {
        Self(CLAIM_INDEX.replace(Some(index)))
    }
}
#[cfg(feature = "nfs-qualification")]
impl Drop for ClaimScope {
    fn drop(&mut self) {
        CLAIM_INDEX.set(self.0);
    }
}
#[cfg(feature = "nfs-qualification")]
fn selected_claim(selector: Option<&str>, index: Option<usize>) -> Result<bool> {
    match selector {
        None => Ok(true),
        Some(value) => {
            let selected = value
                .parse::<usize>()
                .ok()
                .filter(|n| *n < 256)
                .ok_or(ClaimError::Blocked("invalid qualification claim index"))?;
            Ok(index == Some(selected))
        }
    }
}

#[cfg(feature = "nfs-qualification")]
pub fn pause(operation: &'static str) -> Result<()> {
    if std::env::var("FILE_MOVER_QUALIFICATION_PAUSE")
        .ok()
        .as_deref()
        != Some(operation)
    {
        return Ok(());
    }
    if !selected_claim(
        std::env::var("FILE_MOVER_QUALIFICATION_CLAIM_INDEX")
            .ok()
            .as_deref(),
        CLAIM_INDEX.get(),
    )? {
        return Ok(());
    }
    let path = std::env::var("FILE_MOVER_QUALIFICATION_RENDEZVOUS")
        .map_err(|_| ClaimError::Blocked("qualification rendezvous missing"))?;
    pause_at(
        &path,
        operation,
        std::time::Duration::from_secs(if operation == "shutdown_drain" {
            90
        } else {
            60
        }),
    )
}

#[cfg(feature = "nfs-qualification")]
fn pause_at(path: &str, operation: &str, budget: std::time::Duration) -> Result<()> {
    use std::io::Write;
    let dir = root(path)?;
    owned_directory(&dir, true)?;
    if fs::fstatfs(&dir)?.f_type == 0x6969 {
        return Err(ClaimError::Blocked(
            "qualification rendezvous must be local",
        ));
    }
    let fd = fs::openat(
        &dir,
        "ready",
        OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::RUSR | Mode::WUSR,
    )?;
    let mut file = std::fs::File::from(fd);
    writeln!(file, "{} {operation}", std::process::id())
        .map_err(|_| ClaimError::Blocked("qualification ready write failed"))?;
    let deadline = std::time::Instant::now() + budget;
    loop {
        match fs::openat(&dir, "go", FILE, Mode::empty()) {
            Ok(fd) => {
                source(&fd)?;
                return Ok(());
            }
            Err(Errno::NOENT) => (),
            Err(e) => return Err(e.into()),
        }
        if std::time::Instant::now() >= deadline {
            return Err(ClaimError::Blocked("qualification pause budget expired"));
        }
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
}

#[cfg(all(test, feature = "nfs-qualification"))]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn claim_selector_is_scoped_and_rejects_invalid_indices() {
        assert!(selected_claim(None, None).unwrap());
        assert!(!selected_claim(Some("1"), None).unwrap());
        assert!(!selected_claim(Some("1"), Some(0)).unwrap());
        assert!(selected_claim(Some("1"), Some(1)).unwrap());
        for value in ["", "-1", "256", "no"] {
            assert!(selected_claim(Some(value), Some(1)).is_err());
        }
        assert_eq!(CLAIM_INDEX.get(), None);
        {
            let _scope = ClaimScope::enter(1);
            assert_eq!(CLAIM_INDEX.get(), Some(1));
            {
                let _nested = ClaimScope::enter(2);
                assert_eq!(CLAIM_INDEX.get(), Some(2));
            }
            assert_eq!(CLAIM_INDEX.get(), Some(1));
        }
        assert_eq!(CLAIM_INDEX.get(), None);
    }
    #[test]
    fn local_rendezvous_is_bounded_exclusive_and_rejects_symlink_release() {
        let path = std::env::temp_dir().join(format!("qualification-pause-{}", std::process::id()));
        std::fs::create_dir(&path).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
        let name = path.to_str().unwrap();
        assert!(pause_at(name, "test", std::time::Duration::from_millis(20)).is_err());
        assert!(
            std::fs::read_to_string(path.join("ready"))
                .unwrap()
                .ends_with(" test\n")
        );
        assert!(pause_at(name, "test", std::time::Duration::ZERO).is_err());
        std::fs::remove_file(path.join("ready")).unwrap();
        std::os::unix::fs::symlink("ready", path.join("go")).unwrap();
        assert!(pause_at(name, "test", std::time::Duration::ZERO).is_err());
        std::fs::remove_file(path.join("ready")).unwrap();
        std::fs::remove_file(path.join("go")).unwrap();
        std::fs::write(path.join("go"), b"").unwrap();
        pause_at(name, "test", std::time::Duration::ZERO).unwrap();
        std::fs::remove_dir_all(&path).unwrap();
    }
}
