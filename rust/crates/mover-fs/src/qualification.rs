//! Deterministic fixture rendezvous, compiled out of production.
use super::*;

#[cfg(not(feature = "nfs-qualification"))]
pub fn pause(_: &'static str) -> Result<()> {
    Ok(())
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
    let path = std::env::var("FILE_MOVER_QUALIFICATION_RENDEZVOUS")
        .map_err(|_| ClaimError::Blocked("qualification rendezvous missing"))?;
    pause_at(&path, operation, std::time::Duration::from_secs(60))
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
