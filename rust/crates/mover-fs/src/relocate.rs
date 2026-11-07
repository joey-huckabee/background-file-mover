//! No-clobber regular-file relocation under an immutable durable intent and
//! protected, fenced parents. Two-name recovery admits exactly the owned alias.
use super::payload_io::namespace;
use super::*;
pub(super) struct Relocated {
    pub fd: OwnedFd,
    pub recovered: bool,
}
fn exact(fd: &OwnedFd, expected: &ObjectIdentity, links: u64) -> Result<()> {
    let mut observation = expected.clone();
    observation.links = links;
    if source_with_links(fd, links)? != observation {
        return Err(ClaimError::Blocked("relocation object changed"));
    }
    Ok(())
}
pub(super) fn owned(
    old: &OwnedFd,
    old_name: &str,
    new: &OwnedFd,
    new_name: &str,
    expected: &ObjectIdentity,
    checkpoint: &mut impl FnMut(&'static str),
    operation: &'static str,
) -> Result<Relocated> {
    move_with(
        old,
        old_name,
        new,
        new_name,
        expected,
        &mut |step| {
            checkpoint(step);
            if step == "link_durable" {
                super::qualification_pause(operation)?;
            }
            #[cfg(feature = "nfs-qualification")]
            if let Some(point) = match (operation, step) {
                ("claim_link", "link_enter") => Some("claim_link_rpc"),
                ("claim_link", "unlink_enter") => Some("claim_unlink_rpc"),
                ("file_link", "link_enter") => Some("file_link_rpc"),
                ("manifest_link", "link_enter") => Some("manifest_link_rpc"),
                ("file_link", "link_effect") => Some("file_link_sync"),
                ("manifest_link", "link_effect") => Some("manifest_link_sync"),
                ("file_link", "unlink_enter") => Some("file_unlink"),
                ("manifest_link", "unlink_enter") => Some("manifest_unlink"),
                ("file_link", "unlink_effect") => Some("file_unlink_sync"),
                ("manifest_link", "unlink_effect") => Some("manifest_unlink_sync"),
                _ => None,
            } {
                super::qualification_pause(point)?;
            }
            Ok(())
        },
        || fs::renameat_with(old, old_name, new, new_name, RenameFlags::NOREPLACE),
    )
}
fn move_with(
    old: &OwnedFd,
    old_name: &str,
    new: &OwnedFd,
    new_name: &str,
    expected: &ObjectIdentity,
    checkpoint: &mut impl FnMut(&'static str) -> Result<()>,
    rename: impl FnOnce() -> std::result::Result<(), Errno>,
) -> Result<Relocated> {
    if expected.links != 1
        || fs::fstat(old)?.st_dev != expected.device
        || fs::fstat(new)?.st_dev != expected.device
    {
        return Err(ClaimError::Blocked(
            "relocation requires one-link same-device intent",
        ));
    }
    let existing = match fs::openat(new, new_name, FILE, Mode::empty()) {
        Ok(fd) => Some(fd),
        Err(Errno::NOENT) => None,
        Err(e) => return Err(ClaimError::Operation("relocate.open_final", e)),
    };
    let recovered = existing.is_some();
    let final_fd = if let Some(fd) = existing {
        match fs::openat(old, old_name, FILE, Mode::empty()) {
            Ok(original) => {
                exact(&original, expected, 2)?;
                exact(&fd, expected, 2)?;
                fd
            }
            Err(Errno::NOENT) => {
                exact(&fd, expected, 1)?;
                namespace("relocate.final_file_sync", || fs::fsync(&fd))?;
                namespace("relocate.new_parent_sync", || fs::fsync(new))?;
                namespace("relocate.old_parent_sync", || fs::fsync(old))?;
                return Ok(Relocated { fd, recovered });
            }
            Err(e) => return Err(ClaimError::Operation("relocate.open_original", e)),
        }
    } else {
        let original = namespace("relocate.open_original", || {
            fs::openat(old, old_name, FILE, Mode::empty())
        })?;
        exact(&original, expected, 1)?;
        namespace("relocate.original_file_sync", || fs::fsync(&original))?;
        match rename() {
            Ok(()) => {
                checkpoint("rename_effect")?;
                let fd = namespace("relocate.open_final", || {
                    fs::openat(new, new_name, FILE, Mode::empty())
                })?;
                exact(&fd, expected, 1)?;
                namespace("relocate.final_file_sync", || fs::fsync(&fd))?;
                namespace("relocate.new_parent_sync", || fs::fsync(new))?;
                namespace("relocate.old_parent_sync", || fs::fsync(old))?;
                return Ok(Relocated { fd, recovered });
            }
            Err(Errno::NOSYS | Errno::OPNOTSUPP | Errno::INVAL) => (),
            Err(e) => return Err(ClaimError::Operation("relocate.rename_noreplace", e)),
        }
        namespace("relocate.link_exclusive", || {
            #[cfg(feature = "nfs-qualification")]
            checkpoint("link_enter").map_err(|_| Errno::IO)?;
            fs::linkat(old, old_name, new, new_name, AtFlags::empty())
        })?;
        checkpoint("link_effect")?;
        let fd = namespace("relocate.open_final", || {
            fs::openat(new, new_name, FILE, Mode::empty())
        })?;
        exact(&original, expected, 2)?;
        exact(&fd, expected, 2)?;
        fd
    };
    // Establish the new name durably before removing the old one. Recheck both
    // bindings under the producer handoff/protected-parent fencing contract.
    namespace("relocate.final_file_sync", || fs::fsync(&final_fd))?;
    namespace("relocate.new_parent_sync", || fs::fsync(new))?;
    checkpoint("link_durable")?;
    exact(
        &namespace("relocate.open_original", || {
            fs::openat(old, old_name, FILE, Mode::empty())
        })?,
        expected,
        2,
    )?;
    exact(
        &namespace("relocate.open_final", || {
            fs::openat(new, new_name, FILE, Mode::empty())
        })?,
        expected,
        2,
    )?;
    namespace("relocate.unlink_original", || {
        #[cfg(feature = "nfs-qualification")]
        checkpoint("unlink_enter").map_err(|_| Errno::IO)?;
        fs::unlinkat(old, old_name, AtFlags::empty())
    })?;
    checkpoint("unlink_effect")?;
    namespace("relocate.old_parent_sync", || fs::fsync(old))?;
    checkpoint("unlink_durable")?;
    exact(&final_fd, expected, 1)?;
    Ok(Relocated {
        fd: final_fd,
        recovered,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        os::unix::fs::PermissionsExt,
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "relocate-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
            std::fs::write(path.join("old"), b"owned payload").unwrap();
            Self(path)
        }
        fn directory(&self) -> OwnedFd {
            fs::open(&self.0, DIRECTORY, Mode::empty()).unwrap()
        }
        fn expected(&self) -> ObjectIdentity {
            source(&fs::openat(self.directory(), "old", FILE, Mode::empty()).unwrap()).unwrap()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn unsupported_rename_uses_exclusive_link_without_extra_payload_read() {
        for errno in [Errno::INVAL, Errno::NOSYS, Errno::OPNOTSUPP] {
            let f = Fixture::new();
            let dir = f.directory();
            let expected = f.expected();
            let moved = move_with(&dir, "old", &dir, "new", &expected, &mut |_| Ok(()), || {
                Err(errno)
            })
            .unwrap();
            assert!(!moved.recovered);
            assert_eq!(source(&moved.fd).unwrap(), expected);
            assert!(!f.0.join("old").exists());
            assert_eq!(std::fs::read(f.0.join("new")).unwrap(), b"owned payload");
        }
    }
    #[test]
    fn rename_error_after_effect_preserves_final_and_recovers_only_exact_ownership() {
        let f = Fixture::new();
        let dir = f.directory();
        let expected = f.expected();
        let result = move_with(&dir, "old", &dir, "new", &expected, &mut |_| Ok(()), || {
            // Simulate a server-applied rename whose reply reports EIO.
            fs::renameat(&dir, "old", &dir, "new")?;
            Err(Errno::IO)
        });
        let error = result.err().unwrap();
        let detail = failure_diagnostic(&error);
        assert!(detail.starts_with("relocate.rename_noreplace errno=5;"));
        assert!(detail.contains("preserve source/state"));
        assert!(!f.0.join("old").exists());
        assert_eq!(std::fs::read(f.0.join("new")).unwrap(), b"owned payload");
        let recovered = owned(&dir, "old", &dir, "new", &expected, &mut |_| {}, "").unwrap();
        assert!(recovered.recovered);
        assert_eq!(source(&recovered.fd).unwrap(), expected);
    }
    #[test]
    fn other_rename_failures_never_trigger_a_fallback() {
        for errno in [Errno::IO, Errno::ACCESS, Errno::XDEV, Errno::EXIST] {
            let f = Fixture::new();
            let dir = f.directory();
            assert!(
                move_with(
                    &dir,
                    "old",
                    &dir,
                    "new",
                    &f.expected(),
                    &mut |_| Ok(()),
                    || Err(errno)
                )
                .is_err()
            );
            assert!(f.0.join("old").exists());
            assert!(!f.0.join("new").exists());
        }
    }
    #[test]
    fn collision_at_the_link_transition_never_clobbers_or_removes_original() {
        let f = Fixture::new();
        let dir = f.directory();
        let expected = f.expected();
        let result = move_with(&dir, "old", &dir, "new", &expected, &mut |_| Ok(()), || {
            std::fs::write(f.0.join("new"), b"racing foreign file").unwrap();
            Err(Errno::INVAL)
        });
        assert!(matches!(
            result,
            Err(ClaimError::Operation(
                "relocate.link_exclusive",
                Errno::EXIST
            ))
        ));
        assert_eq!(std::fs::read(f.0.join("old")).unwrap(), b"owned payload");
        assert_eq!(
            std::fs::read(f.0.join("new")).unwrap(),
            b"racing foreign file"
        );
    }
    #[test]
    fn foreign_collision_and_unrecorded_extra_link_are_preserved() {
        let f = Fixture::new();
        let dir = f.directory();
        let expected = f.expected();
        std::fs::write(f.0.join("new"), b"foreign").unwrap();
        assert!(owned(&dir, "old", &dir, "new", &expected, &mut |_| {}, "").is_err());
        assert_eq!(std::fs::read(f.0.join("new")).unwrap(), b"foreign");
        assert!(f.0.join("old").exists());
        std::fs::remove_file(f.0.join("new")).unwrap();
        std::fs::hard_link(f.0.join("old"), f.0.join("new")).unwrap();
        std::fs::hard_link(f.0.join("old"), f.0.join("third")).unwrap();
        assert!(owned(&dir, "old", &dir, "new", &expected, &mut |_| {}, "").is_err());
        assert!(f.0.join("old").exists());
        assert!(f.0.join("third").exists());
    }
    #[test]
    fn abrupt_exit_after_each_link_substep_reconciles_exact_owned_names() {
        for stage in [
            "link_effect",
            "link_durable",
            "unlink_effect",
            "unlink_durable",
        ] {
            let f = Fixture::new();
            let expected = f.expected();
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--ignored",
                    "--exact",
                    "relocate::tests::child_link",
                    "--test-threads=1",
                ])
                .env("MOVER_RELOCATE_PATH", &f.0)
                .env("MOVER_RELOCATE_STAGE", stage)
                .output()
                .unwrap();
            assert!(output.status.success(), "{output:?}");
            assert!(f.0.join("new").exists(), "{stage}");
            assert_eq!(f.0.join("old").exists(), stage.starts_with("link"));
            let dir = f.directory();
            let moved = owned(&dir, "old", &dir, "new", &expected, &mut |_| {}, "").unwrap();
            assert!(moved.recovered);
            assert_eq!(source(&moved.fd).unwrap(), expected);
            assert!(!f.0.join("old").exists());
            assert_eq!(std::fs::read(f.0.join("new")).unwrap(), b"owned payload");
        }
    }
    #[test]
    #[ignore = "subprocess fault helper"]
    fn child_link() {
        let path = std::env::var("MOVER_RELOCATE_PATH").unwrap();
        let stage = std::env::var("MOVER_RELOCATE_STAGE").unwrap();
        let dir = fs::open(path.as_str(), DIRECTORY, Mode::empty()).unwrap();
        let expected = source(&fs::openat(&dir, "old", FILE, Mode::empty()).unwrap()).unwrap();
        move_with(
            &dir,
            "old",
            &dir,
            "new",
            &expected,
            &mut |boundary| {
                if boundary == stage {
                    std::process::exit(0);
                }
                Ok(())
            },
            || Err(Errno::INVAL),
        )
        .unwrap();
        panic!("fault boundary was not reached");
    }

    #[test]
    fn failed_link_checkpoint_preserves_both_owned_names_for_recovery() {
        let f = Fixture::new();
        let dir = f.directory();
        let expected = f.expected();
        let result = move_with(
            &dir,
            "old",
            &dir,
            "new",
            &expected,
            &mut |step| {
                if step == "link_durable" {
                    return Err(ClaimError::Blocked("interrupted checkpoint"));
                }
                Ok(())
            },
            || Err(Errno::INVAL),
        );
        assert!(matches!(
            result,
            Err(ClaimError::Blocked("interrupted checkpoint"))
        ));
        exact(
            &fs::openat(&dir, "old", FILE, Mode::empty()).unwrap(),
            &expected,
            2,
        )
        .unwrap();
        exact(
            &fs::openat(&dir, "new", FILE, Mode::empty()).unwrap(),
            &expected,
            2,
        )
        .unwrap();
        let recovered = owned(&dir, "old", &dir, "new", &expected, &mut |_| {}, "").unwrap();
        assert!(recovered.recovered);
        assert_eq!(source(&recovered.fd).unwrap(), expected);
        assert!(!f.0.join("old").exists());
        assert_eq!(std::fs::read(f.0.join("new")).unwrap(), b"owned payload");
    }
}
