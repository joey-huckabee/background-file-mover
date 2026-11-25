use mover_core::{DeliveryPolicy, FileSpec, Handoff, Submission};
use mover_fs::{Discarded, apply, claim, discard_retained_source, prepare};
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
                    let lock = path.join(".file-mover/coordinator.lock");
                    std::fs::write(&lock, b"").unwrap();
                    std::fs::set_permissions(lock, std::fs::Permissions::from_mode(0o600)).unwrap();
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

#[test]
fn discard_retained_copy_preserves_nonempty_private_folder_and_extra_file() {
    use std::os::unix::fs::MetadataExt;

    let f = Fixture::new();
    let store = f.store();
    f.write("sub/data", b"retained payload");
    let job = store
        .accept(&f.input("extra-file", &[("sub/data", None)]), &f.context())
        .unwrap();
    claim(&store, job.job_id, 0).unwrap();
    let (intent, _) = store.claim_intent(job.job_id, 0).unwrap().unwrap();
    let area = f.0.join(".file-mover").join(&intent.private_name);
    let extra = area.join("unmanaged-extra");
    std::fs::write(&extra, b"must stay untouched").unwrap();
    let before = std::fs::metadata(&extra).unwrap();
    let directory = std::fs::metadata(&area).unwrap();
    f.write("sub/data", b"producer reused this name");

    // Removed reports the retained copy, not removal of the containing folder.
    assert_eq!(
        discard_retained_source(&intent).unwrap(),
        Discarded::Removed
    );
    assert!(!area.join("data").exists());
    assert!(area.is_dir(), "nonempty private folder must be kept");
    let after_directory = std::fs::metadata(&area).unwrap();
    assert_eq!(after_directory.dev(), directory.dev());
    assert_eq!(after_directory.ino(), directory.ino());
    assert_eq!(std::fs::read(&extra).unwrap(), b"must stay untouched");
    let after = std::fs::metadata(&extra).unwrap();
    assert_eq!(after.dev(), before.dev());
    assert_eq!(after.ino(), before.ino());
    assert_eq!(after.mode(), before.mode());
    assert_eq!(after.mtime(), before.mtime());
    assert_eq!(after.mtime_nsec(), before.mtime_nsec());
    assert_eq!(after.nlink(), before.nlink());
    assert_eq!(
        std::fs::read(f.0.join("recording/sub/data")).unwrap(),
        b"producer reused this name"
    );
    assert_eq!(
        discard_retained_source(&intent).unwrap(),
        Discarded::AlreadyAbsent
    );
    assert!(
        area.is_dir(),
        "repeat discard must also preserve the folder"
    );
    assert_eq!(std::fs::read(extra).unwrap(), b"must stay untouched");
}

#[test]
fn discard_removes_only_the_exact_retained_copy() {
    let f = Fixture::new();
    let store = f.store();
    f.write("sub/data", b"payload");
    f.write("other", b"keep");
    let job = store
        .accept(
            &f.input("discard", &[("sub/data", None), ("other", None)]),
            &f.context(),
        )
        .unwrap();
    claim(&store, job.job_id, 0).unwrap();
    claim(&store, job.job_id, 1).unwrap();
    // The producer reuses the original path; that file is never touched.
    f.write("sub/data", b"new recording");
    let (first, _) = store.claim_intent(job.job_id, 0).unwrap().unwrap();
    assert_eq!(discard_retained_source(&first).unwrap(), Discarded::Removed);
    assert!(
        !f.0.join(".file-mover/1-0").exists(),
        "emptied private area removed"
    );
    assert_eq!(
        std::fs::read(f.0.join("recording/sub/data")).unwrap(),
        b"new recording"
    );
    assert_eq!(
        std::fs::read(f.0.join(".file-mover/1-1/data")).unwrap(),
        b"keep"
    );
    // Repeating finds nothing to remove.
    assert_eq!(
        discard_retained_source(&first).unwrap(),
        Discarded::AlreadyAbsent
    );
    // A different object under the retained name is refused and kept.
    let (second, _) = store.claim_intent(job.job_id, 1).unwrap().unwrap();
    let copy = f.0.join(".file-mover/1-1/data");
    std::fs::remove_file(&copy).unwrap();
    std::fs::write(&copy, b"keep").unwrap();
    std::fs::set_permissions(&copy, std::fs::Permissions::from_mode(0o600)).unwrap();
    assert!(discard_retained_source(&second).is_err());
    assert_eq!(std::fs::read(&copy).unwrap(), b"keep");
    // A symlink in place of the private area is never followed.
    std::fs::remove_file(&copy).unwrap();
    std::fs::remove_dir(f.0.join(".file-mover/1-1")).unwrap();
    symlink(f.0.join("recording"), f.0.join(".file-mover/1-1")).unwrap();
    assert!(discard_retained_source(&second).is_err());
    assert_eq!(
        std::fs::read(f.0.join("recording/sub/data")).unwrap(),
        b"new recording"
    );
    std::fs::remove_file(f.0.join(".file-mover/1-1")).unwrap();
}

// ---- Timer-driven missing-file retries (increment 163) ----

#[test]
fn retry_admission_is_atomic_with_the_intent_and_unrecorded_allocations_are_released() {
    let f = Fixture::new();
    let s = f.store();
    f.write("a", b"abc");
    f.write("b", b"def");
    let job = s
        .accept(
            &f.input("retry-admission", &[("a", None), ("b", None)]),
            &f.context(),
        )
        .unwrap();
    let id = job.job_id;
    let root = f.0.to_str().unwrap().to_owned();
    // A first absence recorded at t=100: deadline 400.
    assert!(!s.note_missing(id, 0, 100).unwrap());
    assert_eq!(s.missing_retry_jobs().unwrap(), vec![(id, 0)]);
    assert!(s.claim_admissible(id, || 399).unwrap());
    let allocated = mover_fs::allocate_claim(
        &mover_fs::observe_claim(id, 0, &root, "recording/a", None).unwrap(),
    )
    .unwrap();
    let area = f.0.join(".file-mover").join(&allocated.private_name);
    assert!(area.is_dir());
    // Deadline passed between Allocate and recording: refused atomically,
    // nothing recorded, the block persisted.
    assert!(!s.begin_claim_admitted(&allocated, || 400).unwrap());
    assert_eq!(s.claim_intent(id, 0).unwrap(), None);
    assert!(!s.claim_admissible(id, || 100).unwrap(), "block persisted");
    // The exact empty allocation is released (a repeat finds nothing).
    assert!(mover_fs::release_claim_allocation(&allocated).unwrap());
    assert!(!area.exists());
    assert!(mover_fs::release_claim_allocation(&allocated).unwrap());
    // After a reviewed reset the job is listed with its new epoch, and a fresh
    // allocation is admitted and recorded.
    s.reset_missing(
        id,
        &mover_store::MissingResetRequest {
            command_id: "retry-reset".into(),
            review_epoch: 0,
            file_index: 0,
            retry_window_seconds: 300,
            actor: "test".into(),
            reason: "File restored".into(),
        },
        500,
    )
    .unwrap();
    assert_eq!(s.missing_retry_jobs().unwrap(), vec![(id, 1)]);
    let again = mover_fs::allocate_claim(
        &mover_fs::observe_claim(id, 0, &root, "recording/a", None).unwrap(),
    )
    .unwrap();
    assert!(s.begin_claim_admitted(&again, || 501).unwrap());
    assert_eq!(s.claim_intent(id, 0).unwrap(), Some((again.clone(), false)));
    // An allocation that gained an entry is kept.
    let other = mover_fs::allocate_claim(
        &mover_fs::observe_claim(id, 1, &root, "recording/b", None).unwrap(),
    )
    .unwrap();
    let other_area = f.0.join(".file-mover").join(&other.private_name);
    std::fs::write(other_area.join("foreign"), b"x").unwrap();
    assert!(!mover_fs::release_claim_allocation(&other).unwrap());
    assert!(other_area.join("foreign").exists());
    // A requested cancellation refuses new authorization, and settlement waits
    // while the recorded intent is unreconciled.
    assert_eq!(
        s.admin_cancel(id, "op", 600).unwrap(),
        mover_store::CancelOutcome::Accepted
    );
    assert!(!s.claim_admissible(id, || 601).unwrap());
    assert_eq!(s.settle_cancellations(602, || false, |_| false).unwrap(), 0);
    mover_fs::apply_claim_effect(&again).unwrap();
    s.finish_claim(&again).unwrap();
    assert_eq!(s.settle_cancellations(603, || false, |_| false).unwrap(), 1);
}

#[test]
fn clock_diagnostics_use_a_reset_windows_own_start() {
    let f = Fixture::new();
    let s = f.store();
    let job = s
        .accept(&f.input("retry-clock", &[("x", None)]), &f.context())
        .unwrap();
    // First absence at 100 (job window 300: deadline 400), blocked at 500,
    // then reset at 500 with a much longer window (deadline 1500).
    assert!(!s.note_missing(job.job_id, 0, 100).unwrap());
    assert!(s.claim_blocked(job.job_id, 500).unwrap());
    s.reset_missing(
        job.job_id,
        &mover_store::MissingResetRequest {
            command_id: "clock-reset".into(),
            review_epoch: 0,
            file_index: 0,
            retry_window_seconds: 1000,
            actor: "test".into(),
            reason: "Longer window".into(),
        },
        500,
    )
    .unwrap();
    // The current window started at 500, not 1500 - 300 = 1200.
    assert!(s.missing_recorded_after(800).unwrap().is_empty());
    assert_eq!(s.missing_recorded_after(499).unwrap(), vec![job.job_id]);
    assert_eq!(
        s.missing_deadlines_between(1400, 1500).unwrap(),
        vec![job.job_id]
    );
}

#[test]
fn discard_report_warns_for_kept_folder_on_removal_and_absence() {
    let f = Fixture::new();
    let store = f.store();
    f.write("data", b"retained");
    let job = store.accept(&f.input("report-leftovers", &[("data", None)]), &f.context()).unwrap();
    claim(&store, job.job_id, 0).unwrap();
    let (intent, _) = store.claim_intent(job.job_id, 0).unwrap().unwrap();
    let area = f.0.join(".file-mover").join(&intent.private_name);
    let extra = area.join("unmanaged-extra");
    std::fs::write(&extra, b"untouched").unwrap();
    assert_eq!(mover_fs::discard_retained_source_report(&intent).unwrap(), (Discarded::Removed, true));
    assert!(!area.join("data").exists());
    assert!(area.is_dir());
    assert_eq!(std::fs::read(&extra).unwrap(), b"untouched");
    // Reconcile a lost receipt: absence still reports the kept folder.
    assert_eq!(mover_fs::discard_retained_source_report(&intent).unwrap(), (Discarded::AlreadyAbsent, true));
    assert!(area.is_dir());
    assert_eq!(std::fs::read(extra).unwrap(), b"untouched");
    f.write("second", b"second copy");
    let second = store.accept(&f.input("no-leftovers", &[("second", None)]), &f.context()).unwrap();
    claim(&store, second.job_id, 0).unwrap();
    let second = store.claim_intent(second.job_id, 0).unwrap().unwrap().0;
    assert_eq!(mover_fs::discard_retained_source_report(&second).unwrap(), (Discarded::Removed, false));
    assert_eq!(mover_fs::discard_retained_source_report(&second).unwrap(), (Discarded::AlreadyAbsent, false));
}
