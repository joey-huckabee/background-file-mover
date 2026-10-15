use mover_core::{DeliveryPolicy, FileSpec, Handoff, Submission};
use mover_fs::{apply, claim, prepare};
use mover_store::{AcceptanceContext, Store};
use std::{
    os::unix::fs::{PermissionsExt, symlink},
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        loop {
            let path = std::env::temp_dir().join(format!(
                "file-mover-fs-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match std::fs::create_dir(&path) {
                Ok(()) => {
                    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700))
                        .unwrap();
                    for name in [".file-mover", "recording", "recording/sub"] {
                        let dir = path.join(name);
                        std::fs::create_dir(&dir).unwrap();
                        std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700))
                            .unwrap();
                    }
                    return Self(path);
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => panic!("{e}"),
            }
        }
    }
    fn store(&self) -> Store {
        Store::open(self.0.join("state.sqlite")).unwrap()
    }
    fn context(&self) -> AcceptanceContext {
        AcceptanceContext {
            source_root_id: "local".into(),
            source_root_path: self.0.to_str().unwrap().into(),
            source_relative_directory: "recording".into(),
            destination_path: "/unused".into(),
            destination_binding: None,
            policy: DeliveryPolicy {
                destination_id: "future".into(),
                group_by_generator: false,
                delete_source_after_commit: false,
            },
            missing_retry_seconds: 300,
        }
    }
    fn input(&self, id: &str, specs: &[(&str, Option<u64>)]) -> Submission {
        Submission::new(
            "generator",
            id,
            self.0.join("recording").to_str().unwrap(),
            specs
                .iter()
                .map(|(p, n)| FileSpec::new(*p, *n).unwrap())
                .collect(),
        )
        .unwrap()
    }
    fn write(&self, path: &str, bytes: &[u8]) {
        std::fs::write(self.0.join("recording").join(path), bytes).unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn actual_sizes_nested_paths_partial_handoff_and_path_reuse() {
    let f = Fixture::new();
    let store = f.store();
    f.write("sub/data", b"payload");
    f.write("empty", b"");
    let input = f.input("first", &[("sub/data", None), ("empty", Some(0))]);
    let job = store.accept(&input, &f.context()).unwrap();
    let partial = claim(&store, job.job_id, 0).unwrap();
    assert_eq!(partial.recording.handoff(), Handoff::Pending);
    assert!(
        store
            .accept(&f.input("other", &[("sub/data", None)]), &f.context())
            .is_err()
    );
    assert!(f.0.join("recording/sub").is_dir());
    assert!(!f.0.join("recording/sub/data").exists());
    let ready = claim(&store, job.job_id, 1).unwrap();
    assert_eq!(ready.recording.handoff(), Handoff::Ready202);
    assert_eq!(ready.recording.actual_bytes_total(), Some(7));
    f.write("sub/data", b"new recording");
    drop(store);
    let store = f.store();
    assert_eq!(
        store
            .accept(&input, &f.context())
            .unwrap()
            .recording
            .handoff(),
        Handoff::Ready202
    );
    claim(&store, job.job_id, 0).unwrap();
    assert_eq!(
        std::fs::read(f.0.join("recording/sub/data")).unwrap(),
        b"new recording"
    );
    assert_eq!(
        std::fs::read(f.0.join(".file-mover/1-0/data")).unwrap(),
        b"payload"
    );
    store
        .accept(&f.input("second", &[("sub/data", None)]), &f.context())
        .unwrap();
}

#[test]
fn expected_size_mismatch_does_not_move_or_allocate() {
    let f = Fixture::new();
    let s = f.store();
    f.write("data", b"x");
    let j = s
        .accept(&f.input("a", &[("data", Some(2))]), &f.context())
        .unwrap();
    assert!(claim(&s, j.job_id, 0).is_err());
    assert!(f.0.join("recording/data").exists());
    assert!(!f.0.join(".file-mover/1-0").exists());
    assert!(s.claim_intent(j.job_id, 0).unwrap().is_none());
}

#[test]
fn durable_claim_intent_reconciles_its_two_name_link_intermediate() {
    let f = Fixture::new();
    let s = f.store();
    f.write("data", b"payload");
    let job = s
        .accept(&f.input("linked", &[("data", None)]), &f.context())
        .unwrap();
    let intent = prepare(&job, 0).unwrap();
    s.begin_claim(&intent).unwrap();
    let private = f.0.join(".file-mover/1-0/data");
    std::fs::hard_link(f.0.join("recording/data"), &private).unwrap();
    let result = claim(&s, 1, 0).unwrap();
    assert_eq!(result.recording.handoff(), Handoff::Ready202);
    assert!(!f.0.join("recording/data").exists());
    assert_eq!(std::fs::read(&private).unwrap(), b"payload");
    assert_eq!(s.claim_intent(1, 0).unwrap(), Some((intent, true)));
}

#[test]
fn local_claim_lock_excludes_second_owner_and_detects_namespace_change() {
    let f = Fixture::new();
    let lock = mover_fs::LocalClaimLock::acquire(f.0.to_str().unwrap()).unwrap();
    assert!(mover_fs::LocalClaimLock::acquire(f.0.to_str().unwrap()).is_err());
    lock.validate().unwrap();
    std::fs::rename(f.0.join(".file-mover"), f.0.join("held")).unwrap();
    std::fs::create_dir(f.0.join(".file-mover")).unwrap();
    std::fs::set_permissions(
        f.0.join(".file-mover"),
        std::fs::Permissions::from_mode(0o700),
    )
    .unwrap();
    assert!(lock.validate().is_err());
    drop(lock);
}

#[test]
fn missing_second_file_retains_first_claim_and_all_reservations() {
    let f = Fixture::new();
    let s = f.store();
    f.write("first", b"retained");
    let j = s
        .accept(
            &f.input("a", &[("first", None), ("missing", None)]),
            &f.context(),
        )
        .unwrap();
    claim(&s, j.job_id, 0).unwrap();
    assert!(claim(&s, j.job_id, 1).is_err());
    drop(s);
    let s = f.store();
    assert_eq!(
        s.get(j.job_id).unwrap().unwrap().recording.handoff(),
        Handoff::Pending
    );
    assert!(
        s.accept(&f.input("b", &[("first", None)]), &f.context())
            .is_err()
    );
    assert_eq!(
        std::fs::read(f.0.join(".file-mover/1-0/data")).unwrap(),
        b"retained"
    );
}

#[test]
fn symlinks_aliases_special_files_and_writable_parents_are_rejected() {
    let f = Fixture::new();
    let s = f.store();
    f.write("real", b"x");
    symlink("real", f.0.join("recording/link")).unwrap();
    symlink("sub", f.0.join("recording/linked-dir")).unwrap();
    f.write("sub/data", b"x");
    std::fs::hard_link(f.0.join("recording/real"), f.0.join("recording/alias")).unwrap();
    rustix::fs::mkfifoat(
        rustix::fs::CWD,
        f.0.join("recording/fifo"),
        rustix::fs::Mode::RUSR | rustix::fs::Mode::WUSR,
    )
    .unwrap();
    for name in ["link", "linked-dir/data", "real", "fifo"] {
        let j = s
            .accept(&f.input(name, &[(name, None)]), &f.context())
            .unwrap();
        assert!(claim(&s, j.job_id, 0).is_err());
    }
    std::fs::set_permissions(
        f.0.join("recording/sub"),
        std::fs::Permissions::from_mode(0o777),
    )
    .unwrap();
    let j = s
        .accept(&f.input("unsafe", &[("sub/data", None)]), &f.context())
        .unwrap();
    assert!(claim(&s, j.job_id, 0).is_err());
    assert!(f.0.join("recording/sub/data").exists());
}

#[test]
fn collisions_and_unrecorded_directory_are_never_adopted() {
    let f = Fixture::new();
    let s = f.store();
    f.write("data", b"original");
    let j = s
        .accept(&f.input("a", &[("data", None)]), &f.context())
        .unwrap();
    let intent = prepare(&j, 0).unwrap();
    assert!(apply(&s, &intent).is_err()); // Allocation is not authorization.
    assert!(prepare(&j, 0).is_err()); // Simulates crash before intent commit.
    s.begin_claim(&intent).unwrap();
    std::fs::write(f.0.join(".file-mover/1-0/data"), b"original").unwrap();
    assert!(apply(&s, &intent).is_err());
    assert_eq!(
        std::fs::read(f.0.join("recording/data")).unwrap(),
        b"original"
    );
    assert_eq!(
        s.get(j.job_id).unwrap().unwrap().recording.handoff(),
        Handoff::Pending
    );
}

#[test]
fn identity_changes_and_recovery_with_reappeared_original_block() {
    let f = Fixture::new();
    let s = f.store();
    f.write("data", b"original");
    let j = s
        .accept(&f.input("a", &[("data", None)]), &f.context())
        .unwrap();
    let intent = prepare(&j, 0).unwrap();
    s.begin_claim(&intent).unwrap();
    std::fs::rename(f.0.join("recording/data"), f.0.join("recording/held")).unwrap();
    f.write("data", b"replacement");
    assert!(apply(&s, &intent).is_err());
    std::fs::remove_file(f.0.join("recording/data")).unwrap();
    std::fs::rename(f.0.join("recording/held"), f.0.join("recording/data")).unwrap();
    apply(&s, &intent).unwrap();
    f.write("data", b"premature reuse");
    assert!(apply(&s, &intent).is_err());
    assert_eq!(
        std::fs::read(f.0.join("recording/data")).unwrap(),
        b"premature reuse"
    );
}

#[test]
fn database_failure_after_effect_requires_reconciliation_before_handoff() {
    let f = Fixture::new();
    let s = f.store();
    f.write("data", b"retained");
    let j = s
        .accept(&f.input("a", &[("data", None)]), &f.context())
        .unwrap();
    let intent = prepare(&j, 0).unwrap();
    s.begin_claim(&intent).unwrap();
    apply(&s, &intent).unwrap();
    let ro = Store::open_read_only(f.0.join("state.sqlite")).unwrap();
    assert!(ro.finish_claim(&intent).is_err());
    drop(ro);
    assert_eq!(
        s.get(j.job_id).unwrap().unwrap().recording.handoff(),
        Handoff::Pending
    );
    drop(s);
    let s = f.store();
    assert_eq!(
        claim(&s, j.job_id, 0).unwrap().recording.handoff(),
        Handoff::Ready202
    );
}

#[test]
fn replacement_private_directory_blocks_effect_and_preserves_source() {
    let f = Fixture::new();
    let s = f.store();
    f.write("data", b"protected");
    let j = s
        .accept(&f.input("a", &[("data", None)]), &f.context())
        .unwrap();
    let intent = prepare(&j, 0).unwrap();
    s.begin_claim(&intent).unwrap();
    std::fs::rename(f.0.join(".file-mover/1-0"), f.0.join(".file-mover/held")).unwrap();
    let replacement = f.0.join(".file-mover/1-0");
    std::fs::create_dir(&replacement).unwrap();
    std::fs::set_permissions(&replacement, std::fs::Permissions::from_mode(0o700)).unwrap();
    assert!(apply(&s, &intent).is_err());
    assert_eq!(
        std::fs::read(f.0.join("recording/data")).unwrap(),
        b"protected"
    );
    assert_eq!(
        s.get(j.job_id).unwrap().unwrap().recording.handoff(),
        Handoff::Pending
    );
}

#[test]
fn abrupt_process_exit_reconciles_intent_effect_and_receipt_boundaries() {
    for stage in ["intent", "rename", "effect", "receipt"] {
        let f = Fixture::new();
        f.write("data", b"payload");
        let input = f.input("a", &[("data", None)]);
        {
            let s = f.store();
            s.accept(&input, &f.context()).unwrap();
        }
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "--exact", "child_claim", "--test-threads=1"])
            .env("FILE_MOVER_CLAIM_ROOT", &f.0)
            .env("FILE_MOVER_CLAIM_STAGE", stage)
            .output()
            .unwrap();
        assert!(output.status.success(), "{output:?}");
        let s = f.store();
        let (_, receipt_done) = s
            .claim_intent(1, 0)
            .unwrap()
            .expect("child committed intent");
        assert_eq!(receipt_done, stage == "receipt");
        assert_eq!(f.0.join("recording/data").exists(), stage == "intent");
        assert_eq!(f.0.join(".file-mover/1-0/data").exists(), stage != "intent");
        assert_eq!(
            s.get(1).unwrap().unwrap().recording.handoff(),
            if stage == "receipt" {
                Handoff::Ready202
            } else {
                Handoff::Pending
            }
        );
        if stage == "receipt" {
            f.write("data", b"reuse");
        }
        assert_eq!(
            claim(&s, 1, 0).unwrap().recording.handoff(),
            Handoff::Ready202
        );
        assert_eq!(
            std::fs::read(f.0.join(".file-mover/1-0/data")).unwrap(),
            b"payload"
        );
        if stage == "receipt" {
            assert_eq!(std::fs::read(f.0.join("recording/data")).unwrap(), b"reuse");
        }
    }
}
#[test]
#[ignore]
fn child_claim() {
    let root = std::env::var("FILE_MOVER_CLAIM_ROOT").unwrap();
    let stage = std::env::var("FILE_MOVER_CLAIM_STAGE").unwrap();
    let root = PathBuf::from(root);
    let s = Store::open(root.join("state.sqlite")).unwrap();
    let j = s.get(1).unwrap().unwrap();
    let intent = prepare(&j, 0).unwrap();
    s.begin_claim(&intent).unwrap();
    if stage == "rename" {
        rustix::fs::renameat_with(
            rustix::fs::CWD,
            root.join("recording/data"),
            rustix::fs::CWD,
            root.join(".file-mover/1-0/data"),
            rustix::fs::RenameFlags::NOREPLACE,
        )
        .unwrap();
        // Exit immediately after the effect, before directory synchronization.
    } else if stage != "intent" {
        apply(&s, &intent).unwrap();
    }
    if stage == "receipt" {
        s.finish_claim(&intent).unwrap();
    }
    std::process::exit(0); // Bypass all Drops; WAL/effect recovery in parent.
}
