use mover_core::{DeliveryPolicy, FilePhase, FileSpec, Submission, TransferPhase};
use mover_fs::{
    authorize_publication, claim, copy_stage, prepare_transfer, prepare_transfer_file,
    publish_stage, restart_transfer, transfer_one, verify_stage,
};
use mover_store::{AcceptanceContext, Store};
use std::{
    os::unix::fs::{MetadataExt, PermissionsExt},
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture {
    base: PathBuf,
    destination: PathBuf,
}
impl Fixture {
    fn new(cross_device: bool) -> Self {
        let base = loop {
            let p = std::env::temp_dir().join(format!(
                "mover-transfer-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match std::fs::create_dir(&p) {
                Ok(()) => break p,
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => panic!("{e}"),
            }
        };
        let destination = if cross_device {
            PathBuf::from("/dev/shm").join(base.file_name().unwrap())
        } else {
            base.join("destination")
        };
        for p in [
            base.clone(),
            base.join("source"),
            base.join("source/.file-mover"),
            base.join("source/recording"),
            base.join("source/recording/sub"),
            base.join("state"),
            destination.clone(),
            destination.join(".file-mover"),
        ] {
            if p != base {
                std::fs::create_dir(&p).unwrap();
            }
            std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700)).unwrap();
        }
        for root in [base.join("source"), destination.clone()] {
            let lock = root.join(".file-mover/coordinator.lock");
            std::fs::write(&lock, b"").unwrap();
            std::fs::set_permissions(lock, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        Self { base, destination }
    }
    fn db(&self) -> PathBuf {
        self.base.join("state/jobs.sqlite")
    }
    fn store(&self) -> Store {
        Store::open(self.db()).unwrap()
    }
    fn accept_claim(&self, data: &[u8]) {
        let s = self.store();
        std::fs::write(self.base.join("source/recording/sub/data"), data).unwrap();
        let submission = Submission::new(
            "recorder",
            "one",
            self.base.join("source/recording").to_str().unwrap(),
            vec![FileSpec::new("sub/data", None).unwrap()],
        )
        .unwrap();
        let c = AcceptanceContext {
            source_root_id: "source".into(),
            source_root_path: self.base.join("source").to_str().unwrap().into(),
            source_relative_directory: "recording".into(),
            destination_path: self.destination.to_str().unwrap().into(),
            destination_binding: None,
            policy: DeliveryPolicy {
                destination_id: "dest".into(),
                group_by_generator: false,
                delete_source_after_commit: false,
            },
            missing_retry_seconds: 300,
        };
        let job = s.accept(&submission, &c).unwrap();
        claim(&s, job.job_id, 0).unwrap();
    }
    fn claimed(&self) -> PathBuf {
        self.base.join("source/.file-mover/1-0/data")
    }
    fn accept_multi(&self) {
        let s = self.store();
        let mut files = Vec::new();
        for (name, bytes) in [
            ("sub/alpha", b"abc".as_slice()),
            ("sub/beta", b"other".as_slice()),
            ("empty", b"".as_slice()),
        ] {
            std::fs::write(self.base.join("source/recording").join(name), bytes).unwrap();
            files.push(FileSpec::new(name, None).unwrap());
        }
        let input = Submission::new(
            "recorder",
            "set",
            self.base.join("source/recording").to_str().unwrap(),
            files,
        )
        .unwrap();
        let c = AcceptanceContext {
            source_root_id: "source".into(),
            source_root_path: self.base.join("source").to_str().unwrap().into(),
            source_relative_directory: "recording".into(),
            destination_path: self.destination.to_str().unwrap().into(),
            destination_binding: None,
            policy: DeliveryPolicy {
                destination_id: "dest".into(),
                group_by_generator: false,
                delete_source_after_commit: false,
            },
            missing_retry_seconds: 300,
        };
        s.accept(&input, &c).unwrap();
        for i in 0..3 {
            claim(&s, 1, i).unwrap();
        }
    }
    fn final_path(&self) -> PathBuf {
        self.destination.join("1/sub/data")
    }
    fn stage(&self, attempt: i64) -> PathBuf {
        self.destination.join(format!("1/.staging/{attempt}.part"))
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.base).unwrap();
        if !self.destination.starts_with(&self.base) {
            std::fs::remove_dir_all(&self.destination).unwrap();
        }
    }
}

#[test]
fn cross_filesystem_copy_large_file_retains_source_and_preserves_names() {
    let f = Fixture::new(true);
    let data = vec![b'x'; 2 * 1024 * 1024 + 17];
    f.accept_claim(&data);
    assert_ne!(
        std::fs::metadata(f.claimed()).unwrap().dev(),
        std::fs::metadata(&f.destination).unwrap().dev()
    );
    let expected = std::process::Command::new("sha256sum")
        .arg(f.claimed())
        .output()
        .unwrap();
    assert!(expected.status.success());
    let expected = String::from_utf8(expected.stdout)
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap()
        .to_owned();
    std::fs::write(f.base.join("source/recording/sub/data"), b"producer reuse").unwrap();
    let store = f.store();
    let result = transfer_one(&store, 1).unwrap();
    assert_eq!(result.phase, TransferPhase::Published);
    assert_eq!(result.sha256.as_deref(), Some(expected.as_str()));
    assert_eq!(std::fs::read(f.final_path()).unwrap(), data);
    assert_eq!(std::fs::read(f.claimed()).unwrap(), data);
    assert_eq!(
        std::fs::read(f.base.join("source/recording/sub/data")).unwrap(),
        b"producer reuse"
    );
    assert!(!f.destination.join("1/COMMITTED.json").exists());
    let job = store.get(1).unwrap().unwrap();
    assert_eq!(job.recording.file_phase(0), Some(FilePhase::Published));
    assert!(!job.recording.cleanup_authorized(0, true));
    assert_eq!(transfer_one(&store, 1).unwrap(), result);
}
#[test]
fn sha256_known_vectors_include_empty_files() {
    for (bytes, expected) in [
        (
            b"".as_slice(),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        (
            b"abc".as_slice(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        ),
    ] {
        let f = Fixture::new(false);
        f.accept_claim(bytes);
        let s = f.store();
        assert_eq!(
            transfer_one(&s, 1).unwrap().sha256.as_deref(),
            Some(expected)
        );
        assert_eq!(std::fs::read(f.final_path()).unwrap(), bytes);
    }
}
#[test]
fn corrupted_staging_with_restored_metadata_fails_independent_hash() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap();
    std::fs::set_permissions(f.stage(1), std::fs::Permissions::from_mode(0o600)).unwrap();
    std::fs::write(f.stage(1), b"xyz").unwrap();
    let file = std::fs::OpenOptions::new()
        .write(true)
        .open(f.stage(1))
        .unwrap();
    let modified = std::time::UNIX_EPOCH
        + std::time::Duration::new(
            t.stage.modified_seconds as u64,
            t.stage.modified_nanos as u32,
        );
    file.set_times(std::fs::FileTimes::new().set_modified(modified))
        .unwrap();
    drop(file);
    std::fs::set_permissions(f.stage(1), std::fs::Permissions::from_mode(0o400)).unwrap();
    let error = verify_stage(&s, &t).unwrap_err();
    assert!(error.to_string().contains("digest mismatch"), "{error}");
    assert_eq!(
        s.transfer(1, 0).unwrap().unwrap().phase,
        TransferPhase::Copied
    );
    assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
    assert!(!f.final_path().exists());
}
#[test]
fn foreign_equal_content_final_is_never_overwritten() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = authorize_publication(
        &s,
        &verify_stage(
            &s,
            &copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    std::fs::write(f.final_path(), b"abc").unwrap();
    let before = std::fs::metadata(f.final_path()).unwrap().ino();
    assert!(publish_stage(&s, &t).is_err());
    assert_eq!(std::fs::metadata(f.final_path()).unwrap().ino(), before);
    assert!(f.stage(1).exists());
    assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
}
#[test]
fn receipt_failure_after_copy_restarts_into_new_owned_attempt() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = prepare_transfer(&s, 1).unwrap();
    let ro = Store::open_read_only(f.db()).unwrap();
    assert!(copy_stage(&ro, &t).is_err());
    drop(ro);
    assert_eq!(
        s.transfer(1, 0).unwrap().unwrap().phase,
        TransferPhase::Intent
    );
    assert_eq!(std::fs::read(f.stage(1)).unwrap(), b"abc");
    let t = transfer_one(&s, 1).unwrap();
    assert_eq!(t.attempt, 2);
    assert_eq!(std::fs::read(f.stage(1)).unwrap(), b"abc");
    assert_eq!(std::fs::read(f.final_path()).unwrap(), b"abc");
}
#[test]
fn receipt_failure_after_publication_reconciles_without_recopy() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = authorize_publication(
        &s,
        &verify_stage(
            &s,
            &copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    let ro = Store::open_read_only(f.db()).unwrap();
    assert!(publish_stage(&ro, &t).is_err());
    drop(ro);
    assert!(f.final_path().exists());
    assert!(!f.stage(1).exists());
    assert_eq!(
        s.transfer(1, 0).unwrap().unwrap().phase,
        TransferPhase::PublishIntent
    );
    let recovered = transfer_one(&s, 1).unwrap();
    assert_eq!(recovered.attempt, 1);
    assert_eq!(recovered.phase, TransferPhase::Published);
    assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
}
#[test]
fn lost_custody_and_source_changes_block_transfer() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = prepare_transfer(&s, 1).unwrap();
    std::fs::write(f.claimed(), b"changed").unwrap();
    assert!(copy_stage(&s, &t).is_err());
    assert!(!f.final_path().exists());
    let g = Fixture::new(false);
    g.accept_claim(b"abc");
    let s = g.store();
    let t = prepare_transfer(&s, 1).unwrap();
    std::fs::rename(
        g.destination.join("1/.staging"),
        g.destination.join("1/held"),
    )
    .unwrap();
    std::fs::create_dir(g.destination.join("1/.staging")).unwrap();
    std::fs::set_permissions(
        g.destination.join("1/.staging"),
        std::fs::Permissions::from_mode(0o700),
    )
    .unwrap();
    assert!(copy_stage(&s, &t).is_err());
    assert!(g.destination.join("1/held/1.part").exists());
}

#[test]
fn publication_intent_reconciles_owned_aliases_and_retains_source() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = authorize_publication(
        &s,
        &verify_stage(
            &s,
            &copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    std::fs::hard_link(f.stage(1), f.final_path()).unwrap();
    let recovered = publish_stage(&s, &t).unwrap();
    assert_eq!(recovered.phase, TransferPhase::Published);
    assert!(!f.stage(1).exists());
    assert_eq!(std::fs::read(f.final_path()).unwrap(), b"abc");
    assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
}

#[test]
fn manifest_intent_reconciles_owned_aliases_before_commit_receipt() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    {
        let s = f.store();
        transfer_one(&s, 1).unwrap();
    }
    let out = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--ignored", "--exact", "child_manifest", "--test-threads=1"])
        .env("FILE_MOVER_TRANSFER_DB", f.db())
        .env("FILE_MOVER_MANIFEST_POINT", "authorized")
        .output()
        .unwrap();
    assert!(out.status.success(), "{out:?}");
    let s = f.store();
    let before = s.manifest(1).unwrap().unwrap();
    assert_eq!(before.phase, 3);
    let stage = f.destination.join("1/.staging/COMMITTED.part");
    let final_path = f.destination.join("1/COMMITTED.json");
    std::fs::hard_link(&stage, &final_path).unwrap();
    let after = mover_fs::commit_manifest(&s, 1).unwrap();
    assert_eq!(after.phase, 4);
    assert_eq!(after.bytes, before.bytes);
    assert!(!stage.exists());
    assert_eq!(std::fs::read(&final_path).unwrap(), after.bytes.as_bytes());
    assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
}

#[test]
fn allocation_gap_never_adopts_or_deletes_an_existing_directory() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let ro = Store::open_read_only(f.db()).unwrap();
    assert!(prepare_transfer(&ro, 1).is_err());
    drop(ro);
    assert!(s.transfer(1, 0).unwrap().is_none());
    assert!(f.stage(1).exists());
    assert!(transfer_one(&s, 1).is_err());
    assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
}
#[test]
fn abrupt_exit_at_each_durable_copy_and_publication_boundary() {
    for stage in [
        "intent",
        "partial",
        "copied",
        "verified",
        "authorized",
        "renamed",
        "published",
    ] {
        let f = Fixture::new(false);
        f.accept_claim(b"abc");
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "--exact", "child_transfer", "--test-threads=1"])
            .env("FILE_MOVER_TRANSFER_DB", f.db())
            .env("FILE_MOVER_TRANSFER_STAGE", stage)
            .output()
            .unwrap();
        assert!(output.status.success(), "{output:?}");
        let s = f.store();
        let t = s
            .transfer(1, 0)
            .unwrap()
            .expect("child committed transfer intent");
        let phase = match stage {
            "intent" | "partial" => TransferPhase::Intent,
            "copied" => TransferPhase::Copied,
            "verified" => TransferPhase::Verified,
            "authorized" | "renamed" => TransferPhase::PublishIntent,
            _ => TransferPhase::Published,
        };
        assert_eq!(t.phase, phase);
        assert_eq!(
            f.final_path().exists(),
            matches!(stage, "renamed" | "published")
        );
        let recovered = transfer_one(&s, 1).unwrap();
        assert_eq!(recovered.phase, TransferPhase::Published);
        assert_eq!(
            recovered.attempt,
            if matches!(stage, "intent" | "partial") {
                2
            } else {
                1
            }
        );
        assert_eq!(std::fs::read(f.final_path()).unwrap(), b"abc");
        assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
        if stage == "partial" {
            assert_eq!(std::fs::read(f.stage(1)).unwrap(), b"partial");
        }
    }
}
#[test]
#[ignore]
fn child_transfer() {
    let s = Store::open(std::env::var("FILE_MOVER_TRANSFER_DB").unwrap()).unwrap();
    let stage = std::env::var("FILE_MOVER_TRANSFER_STAGE").unwrap();
    let mut t = prepare_transfer(&s, 1).unwrap();
    if stage == "partial" {
        std::fs::write(
            format!("{}/1/.staging/1.part", t.destination_root),
            b"partial",
        )
        .unwrap();
    }
    if !matches!(stage.as_str(), "intent" | "partial") {
        t = copy_stage(&s, &t).unwrap();
    }
    if matches!(
        stage.as_str(),
        "verified" | "authorized" | "renamed" | "published"
    ) {
        t = verify_stage(&s, &t).unwrap();
    }
    if matches!(stage.as_str(), "authorized" | "renamed" | "published") {
        t = authorize_publication(&s, &t).unwrap();
    }
    if stage == "renamed" {
        rustix::fs::renameat_with(
            rustix::fs::CWD,
            format!("{}/1/.staging/1.part", t.destination_root),
            rustix::fs::CWD,
            format!("{}/1/sub/data", t.destination_root),
            rustix::fs::RenameFlags::NOREPLACE,
        )
        .unwrap();
    }
    if stage == "published" {
        publish_stage(&s, &t).unwrap();
    }
    std::process::exit(0);
}

#[test]
fn failed_preparation_releases_its_capacity_reservation() {
    let f = Fixture::new(false);
    f.accept_multi();
    let s = f.store();
    // Room for file 0 (3 bytes) but not for file 0 plus file 1 (5 bytes).
    s.configure_limits(64, 7).unwrap();
    // File 1 before file 0 reserves, then fails: no recording directory yet.
    assert!(mover_fs::prepare_transfer_file(&s, 1, 1).is_err());
    // The failed attempt's reservation is gone, so file 0 still fits.
    let t = prepare_transfer(&s, 1).unwrap();
    assert_eq!(t.file_index, 0);
}
#[test]
fn multi_file_delivery_commits_exact_manifest_and_retains_every_claim() {
    let f = Fixture::new(false);
    f.accept_multi();
    let s = f.store();
    mover_fs::deliver_recording(&s, 1).unwrap();
    let bytes = std::fs::read(f.destination.join("1/COMMITTED.json")).unwrap();
    let manifest: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(manifest["instance_id"], s.instance_id().unwrap());
    assert_eq!(manifest["files"].as_array().unwrap().len(), 3);
    for (index, (name, data)) in [
        ("sub/alpha", b"abc".as_slice()),
        ("sub/beta", b"other".as_slice()),
        ("empty", b"".as_slice()),
    ]
    .into_iter()
    .enumerate()
    {
        assert_eq!(manifest["files"][index]["path"], name);
        assert_eq!(manifest["files"][index]["size_bytes"], data.len());
        assert_eq!(
            std::fs::read(f.destination.join("1").join(name)).unwrap(),
            data
        );
        assert_eq!(
            std::fs::read(f.base.join(format!("source/.file-mover/1-{index}/data"))).unwrap(),
            data
        );
    }
    let record = s.manifest(1).unwrap().unwrap();
    assert_eq!(record.bytes.as_bytes(), bytes);
    assert_eq!(record.phase, 4);
    let job = s.get(1).unwrap().unwrap();
    assert!(job.recording.is_committed());
    for i in 0..3 {
        assert!(!job.recording.cleanup_authorized(i, true));
    }
    mover_fs::deliver_recording(&s, 1).unwrap();
    assert_eq!(
        std::fs::read(f.destination.join("1/COMMITTED.json")).unwrap(),
        bytes
    );
}
#[test]
fn incomplete_set_and_foreign_manifest_never_commit() {
    let f = Fixture::new(false);
    f.accept_multi();
    let s = f.store();
    let t = authorize_publication(
        &s,
        &verify_stage(
            &s,
            &copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    publish_stage(&s, &t).unwrap();
    assert!(mover_fs::commit_manifest(&s, 1).is_err());
    assert!(s.manifest(1).unwrap().is_none());
    assert!(!f.destination.join("1/COMMITTED.json").exists());
    let g = Fixture::new(false);
    g.accept_claim(b"abc");
    let s = g.store();
    transfer_one(&s, 1).unwrap();
    let path = g.destination.join("1/COMMITTED.json");
    std::fs::write(&path, b"foreign manifest").unwrap();
    let inode = std::fs::metadata(&path).unwrap().ino();
    assert!(mover_fs::commit_manifest(&s, 1).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), b"foreign manifest");
    assert_eq!(std::fs::metadata(path).unwrap().ino(), inode);
    assert!(!s.get(1).unwrap().unwrap().recording.is_committed());
}
#[test]
fn manifest_receipt_failure_after_publication_recovers_without_recopy() {
    let f = Fixture::new(false);
    f.accept_multi();
    let s = f.store();
    let db = rusqlite::Connection::open(f.db()).unwrap();
    db.execute_batch("CREATE TRIGGER refuse_commit BEFORE UPDATE ON manifests WHEN NEW.phase=4 BEGIN SELECT RAISE(ABORT,'manifest receipt failure'); END;").unwrap();
    assert!(mover_fs::deliver_recording(&s, 1).is_err());
    assert_eq!(s.manifest(1).unwrap().unwrap().phase, 3);
    assert!(!s.get(1).unwrap().unwrap().recording.is_committed());
    let before = std::fs::read(f.destination.join("1/COMMITTED.json")).unwrap();
    db.execute_batch("DROP TRIGGER refuse_commit").unwrap();
    drop(db);
    mover_fs::deliver_recording(&s, 1).unwrap();
    assert!(s.get(1).unwrap().unwrap().recording.is_committed());
    assert_eq!(
        std::fs::read(f.destination.join("1/COMMITTED.json")).unwrap(),
        before
    );
    for i in 0..3 {
        assert_eq!(s.transfer(1, i).unwrap().unwrap().attempt, 1);
    }
}
#[test]
fn manifest_process_exit_boundaries_reconcile_owned_objects_only() {
    for point in [
        "intent",
        "allocation_effect",
        "allocated",
        "write_effect",
        "written",
        "authorized",
        "rename_effect",
        "publication_sync",
        "committed",
    ] {
        let f = Fixture::new(false);
        f.accept_claim(b"abc");
        {
            let s = f.store();
            transfer_one(&s, 1).unwrap();
        }
        let out = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "--exact", "child_manifest", "--test-threads=1"])
            .env("FILE_MOVER_TRANSFER_DB", f.db())
            .env("FILE_MOVER_MANIFEST_POINT", point)
            .output()
            .unwrap();
        assert!(out.status.success(), "{out:?}");
        let s = f.store();
        let before = s.manifest(1).unwrap().unwrap();
        let phase = match point {
            "intent" | "allocation_effect" => 0,
            "allocated" | "write_effect" => 1,
            "written" => 2,
            "authorized" | "rename_effect" | "publication_sync" => 3,
            _ => 4,
        };
        assert_eq!(before.phase, phase);
        assert_eq!(
            f.destination.join("1/COMMITTED.json").exists(),
            matches!(point, "rename_effect" | "publication_sync" | "committed")
        );
        if point == "allocation_effect" {
            assert!(mover_fs::commit_manifest(&s, 1).is_err());
            assert!(!s.get(1).unwrap().unwrap().recording.is_committed());
        } else {
            let after = mover_fs::commit_manifest(&s, 1).unwrap();
            assert_eq!(after.bytes, before.bytes);
            assert!(s.get(1).unwrap().unwrap().recording.is_committed());
        }
        assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
    }
}
#[test]
#[ignore]
fn child_manifest() {
    let s = Store::open(std::env::var("FILE_MOVER_TRANSFER_DB").unwrap()).unwrap();
    let point = std::env::var("FILE_MOVER_MANIFEST_POINT").unwrap();
    mover_fs::commit_manifest_with_checkpoints(&s, 1, |p| {
        if p == point {
            std::process::exit(0)
        }
    })
    .unwrap();
    panic!("checkpoint not reached");
}

// ---- Confirmed deletion of unfinished destination data (increment 160) ----

/// Cancel a job and confirm its partial destination files.
fn cancel_and_confirm(s: &Store, id: i64) -> Vec<mover_store::DeleteTarget> {
    s.admin_cancel(id, "op", 10).unwrap();
    s.settle_cancellations(11, || false, |_| false).unwrap();
    confirm(s, id)
}
/// Confirm the "Delete partial destination files" action's current selection.
fn confirm(s: &Store, id: i64) -> Vec<mover_store::DeleteTarget> {
    // Retained source copies are not exercised here: settle any still
    // pending so the earlier pass finishes and a fresh preview is offered.
    while let Some((job, index, _)) = s.next_deletion_target().unwrap() {
        s.finish_deletion_target(job, index, false, Some("not run in this test"), 20)
            .unwrap();
    }
    let scope = mover_store::DeletionScope::Destination;
    let (targets, digest) = s.deletion_preview(id, scope).unwrap().unwrap();
    // A distinct confirmation each time (the same one replays its pass).
    let proof: String = format!("{:064x}", NEXT.fetch_add(1, Ordering::Relaxed) + 1);
    s.start_deletion(id, scope, "op", &proof, &digest, 12)
        .unwrap();
    targets
}
/// Run every pending destination target, then every automatic cleanup, the
/// way the delivery thread does.
fn run_destination(s: &Store) -> Vec<(mover_store::DeleteKind, Option<String>)> {
    use mover_fs::DestinationTarget as T;
    use mover_store::DeleteKind as K;
    let mut out = Vec::new();
    loop {
        let (w, automatic) = match s.next_destination_deletion().unwrap() {
            Some(w) => (w, false),
            None => match s.next_automatic_cleanup().unwrap() {
                Some(w) => (w, true),
                None => break,
            },
        };
        if automatic {
            assert!(s.automatic_cleanup_eligible(&w).unwrap());
        }
        // As the worker does: verify every published final first (one each).
        let published = if w.delivered {
            w.published
                .iter()
                .map(mover_fs::published_identity)
                .collect::<Result<Vec<_>, _>>()
        } else {
            Ok(Vec::new())
        };
        let result = published.and_then(|published| {
            let target = match (w.kind, w.delivered) {
                (K::DestinationStaging, false) => T::Staging(&w.transfer),
                (K::DestinationStaging, true) => T::Superseded {
                    transfer: &w.transfer,
                    published: &published,
                },
                (K::DestinationPayload, _) => T::Payload(&w.transfer),
                (K::ManifestStaging, _) => T::Manifest(w.manifest.as_ref().unwrap()),
                _ => unreachable!(),
            };
            mover_fs::discard_unfinished_destination(target, &w.anchor)
        });
        let diagnostic = result.as_ref().err().map(|e| {
            let d: String = e
                .to_string()
                .chars()
                .filter(|c| c.is_ascii_graphic() || *c == ' ')
                .take(200)
                .collect();
            if d.is_empty() { "failed".into() } else { d }
        });
        if automatic {
            s.finish_automatic_cleanup(&w, result.is_ok(), diagnostic.as_deref())
                .unwrap();
        } else {
            s.finish_destination_deletion(&w, result.is_ok(), diagnostic.as_deref(), 20)
                .unwrap();
        }
        out.push((w.kind, diagnostic));
    }
    out
}
fn inode(p: &std::path::Path) -> (u64, u64) {
    let m = std::fs::symlink_metadata(p).unwrap();
    (m.ino(), m.nlink())
}

#[test]
fn cancelled_job_destination_data_is_deleted_exactly_with_its_folders() {
    use mover_store::DeleteKind as K;
    let f = Fixture::new(false);
    f.accept_multi();
    let s = f.store();
    // File 0 published; file 1 has a copied attempt 1 (receipt lost) and an
    // allocated attempt 2; file 2 never started.
    let t0 = prepare_transfer_file(&s, 1, 0).unwrap();
    let t0 = authorize_publication(
        &s,
        &verify_stage(&s, &copy_stage(&s, &t0).unwrap()).unwrap(),
    )
    .unwrap();
    publish_stage(&s, &t0).unwrap();
    let t1 = prepare_transfer_file(&s, 1, 1).unwrap();
    let ro = Store::open_read_only(f.db()).unwrap();
    assert!(copy_stage(&ro, &t1).is_err());
    drop(ro);
    restart_transfer(&s, &s.transfer(1, 1).unwrap().unwrap()).unwrap();
    let area = f.destination.join("1");
    assert!(area.join("sub/alpha").exists());
    assert!(area.join(".staging/1/1.part").exists());
    assert!(area.join(".staging/1/2.part").exists());
    let before = s
        .retention(Some(1))
        .unwrap()
        .unwrap()
        .destination_reserved_bytes;
    assert!(before > 0);

    let targets = cancel_and_confirm(&s, 1);
    let kinds: Vec<_> = targets
        .iter()
        .map(|t| (t.kind, t.file_index, t.attempt, t.size_bytes))
        .collect();
    assert_eq!(
        kinds,
        vec![
            (K::DestinationPayload, Some(0), Some(1), Some(3)),
            (K::DestinationStaging, Some(1), Some(1), None),
            (K::DestinationStaging, Some(1), Some(2), None),
        ]
    );
    let results = run_destination(&s);
    assert_eq!(results.len(), 3);
    assert!(results.iter().all(|(_, d)| d.is_none()), "{results:?}");
    // Everything the mover created at the destination is gone, folders too.
    assert!(!area.exists());
    assert!(f.destination.join(".file-mover/coordinator.lock").exists());
    // Retained source copies belong to the other action: untouched.
    for i in 0..3 {
        assert!(
            f.base
                .join(format!("source/.file-mover/1-{i}/data"))
                .exists()
        );
    }
    assert_eq!(
        s.retention(Some(1))
            .unwrap()
            .unwrap()
            .destination_reserved_bytes,
        0
    );
    let view = s.status(1).unwrap().unwrap().deletion.unwrap();
    assert_eq!((view.deleted_count, view.failed_count), (3, 0));
    assert!(!view.completion_pending);
    // The source action still offers the three retained copies.
    let (source, _) = s
        .deletion_preview(1, mover_store::DeletionScope::Source)
        .unwrap()
        .unwrap();
    assert_eq!(source.len(), 3);
    assert!(source.iter().all(|t| t.kind == K::RetainedSource));
    // A rerun of an already deleted payload finds nothing (durable absence).
    let anchor = s.transfer(1, 0).unwrap().unwrap();
    assert_eq!(
        mover_fs::discard_unfinished_destination(
            mover_fs::DestinationTarget::Payload(&anchor),
            &anchor
        )
        .unwrap(),
        mover_fs::Discarded::AlreadyAbsent
    );
}

#[test]
fn payload_names_recover_from_every_partial_state_and_never_touch_substitutes() {
    use mover_fs::{DestinationTarget, Discarded, discard_unfinished_destination as discard};
    // final only, alias only, both, neither; then substituted alias / final.
    for case in [
        "final",
        "alias",
        "both",
        "neither",
        "foreign_alias",
        "foreign_final",
    ] {
        let f = Fixture::new(false);
        f.accept_claim(b"abc");
        let s = f.store();
        let t = authorize_publication(
            &s,
            &verify_stage(
                &s,
                &copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap(),
            )
            .unwrap(),
        )
        .unwrap();
        let t = publish_stage(&s, &t).unwrap();
        let (fin, alias) = (f.final_path(), f.stage(1));
        match case {
            "final" => (),
            "alias" => std::fs::rename(&fin, &alias).unwrap(),
            "both" => std::fs::hard_link(&fin, &alias).unwrap(),
            "neither" => std::fs::remove_file(&fin).unwrap(),
            "foreign_alias" => std::fs::write(&alias, b"foreign").unwrap(),
            "foreign_final" => {
                std::fs::rename(&fin, &alias).unwrap();
                std::fs::write(&fin, b"foreign").unwrap();
            }
            _ => unreachable!(),
        }
        let result = discard(DestinationTarget::Payload(&t), &t);
        match case {
            "foreign_alias" | "foreign_final" => {
                assert!(result.is_err(), "{case}");
                // Nothing unlinked: both names stay.
                assert!(fin.exists() && alias.exists(), "{case}");
            }
            "neither" => assert_eq!(result.unwrap(), Discarded::AlreadyAbsent, "{case}"),
            _ => {
                assert_eq!(result.unwrap(), Discarded::Removed, "{case}");
                assert!(!fin.exists() && !alias.exists(), "{case}");
                assert!(!f.destination.join("1").exists(), "{case}");
            }
        }
        assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc", "{case}");
    }
}

#[test]
fn committed_or_substituted_destination_data_is_never_deleted() {
    let f = Fixture::new(false);
    f.accept_claim(b"abc");
    let s = f.store();
    let t = authorize_publication(
        &s,
        &verify_stage(
            &s,
            &copy_stage(&s, &prepare_transfer(&s, 1).unwrap()).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    publish_stage(&s, &t).unwrap();
    cancel_and_confirm(&s, 1);
    // A COMMITTED.json in the area refuses everything on the cancelled path.
    let committed = f.destination.join("1/COMMITTED.json");
    std::fs::write(&committed, b"{}").unwrap();
    let results = run_destination(&s);
    assert_eq!(results.len(), 1);
    assert!(results[0].1.is_some());
    assert_eq!(std::fs::read(f.final_path()).unwrap(), b"abc");
    assert!(committed.exists());
    // A fresh confirmation without the manifest; the final was replaced by
    // another object meanwhile: refused and kept.
    std::fs::remove_file(&committed).unwrap();
    std::fs::rename(f.final_path(), f.destination.join("1/aside")).unwrap();
    std::fs::write(f.final_path(), b"xyz").unwrap();
    confirm(&s, 1);
    let results = run_destination(&s);
    assert!(results[0].1.is_some());
    assert_eq!(std::fs::read(f.final_path()).unwrap(), b"xyz");
    assert_eq!(
        std::fs::read(f.destination.join("1/aside")).unwrap(),
        b"abc"
    );
    // A symlinked area is never followed.
    std::fs::rename(f.final_path(), f.destination.join("xyz")).unwrap();
    std::fs::rename(f.destination.join("1"), f.destination.join("real")).unwrap();
    std::os::unix::fs::symlink(f.destination.join("real"), f.destination.join("1")).unwrap();
    confirm(&s, 1);
    assert!(run_destination(&s)[0].1.is_some());
    assert!(f.destination.join("real/aside").exists());
}

#[test]
fn delivered_job_superseded_attempt_is_cleaned_automatically_and_nothing_else() {
    use mover_store::DeleteKind as K;
    // "linked": the leftover name now points at the published file;
    // "no_manifest": COMMITTED.json missing. Both are refused, never retried.
    for case in ["normal", "linked", "no_manifest"] {
        let f = Fixture::new(false);
        f.accept_claim(b"abc");
        let s = f.store();
        // Attempt 1 copied but its receipt lost; delivery restarts into 2.
        let t = prepare_transfer(&s, 1).unwrap();
        let ro = Store::open_read_only(f.db()).unwrap();
        assert!(copy_stage(&ro, &t).is_err());
        drop(ro);
        mover_fs::deliver_recording(&s, 1).unwrap();
        assert!(s.get(1).unwrap().unwrap().recording.is_committed());
        let manifest = f.destination.join("1/COMMITTED.json");
        let (manifest_bytes, manifest_inode) =
            (std::fs::read(&manifest).unwrap(), inode(&manifest));
        let final_inode = inode(&f.final_path());
        assert!(f.stage(1).exists());
        let before = s
            .retention(Some(1))
            .unwrap()
            .unwrap()
            .destination_reserved_bytes;
        // The manual destination action never offers a delivered job's data.
        let (manual, _) = s
            .deletion_preview(1, mover_store::DeletionScope::Destination)
            .unwrap()
            .unwrap();
        assert!(manual.is_empty(), "{case}");
        match case {
            "linked" => {
                std::fs::rename(f.stage(1), f.destination.join("1/.staging/kept")).unwrap();
                std::fs::hard_link(f.final_path(), f.stage(1)).unwrap();
            }
            "no_manifest" => {
                std::fs::rename(&manifest, f.destination.join("1/aside.json")).unwrap()
            }
            _ => (),
        }
        let results = run_destination(&s);
        assert_eq!(results.len(), 1, "{case}");
        assert_eq!(results[0].0, K::DestinationStaging);
        assert_eq!(std::fs::read(f.final_path()).unwrap(), b"abc", "{case}");
        match case {
            "normal" => {
                assert!(results[0].1.is_none(), "{results:?}");
                assert!(!f.stage(1).exists());
                assert_eq!(inode(&f.final_path()), final_inode);
                assert_eq!(std::fs::read(&manifest).unwrap(), manifest_bytes);
                assert_eq!(inode(&manifest), manifest_inode);
                assert!(f.destination.join("1/sub").is_dir());
                let after = s
                    .retention(Some(1))
                    .unwrap()
                    .unwrap()
                    .destination_reserved_bytes;
                assert_eq!(before - after, 3, "exactly the superseded attempt");
                // Not a confirmed pass: no deletion status on the job.
                assert_eq!(s.status(1).unwrap().unwrap().deletion, None);
            }
            "linked" => {
                assert!(results[0].1.is_some(), "{case}");
                assert_eq!(inode(&f.stage(1)).0, final_inode.0);
                assert!(f.destination.join("1/.staging/kept").exists());
            }
            _ => {
                assert!(results[0].1.is_some(), "{case}");
                assert!(f.stage(1).exists());
            }
        }
        // Recorded once; a failure is not retried automatically.
        assert!(run_destination(&s).is_empty(), "{case}");
    }
}

#[test]
fn manifest_staging_is_deleted_and_publication_intent_offers_no_destination_targets() {
    use mover_store::DeleteKind as K;
    // "written": manifest staging exists (phase 2). "authorized": publication
    // intent (phase 3), so COMMITTED.json may exist: nothing at the destination.
    for (point, offered) in [("written", true), ("authorized", false)] {
        let f = Fixture::new(false);
        f.accept_claim(b"abc");
        transfer_one(&f.store(), 1).unwrap();
        let out = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "--exact", "child_manifest", "--test-threads=1"])
            .env("FILE_MOVER_TRANSFER_DB", f.db())
            .env("FILE_MOVER_MANIFEST_POINT", point)
            .output()
            .unwrap();
        assert!(out.status.success(), "{out:?}");
        let s = f.store();
        s.admin_cancel(1, "op", 10).unwrap();
        s.settle_cancellations(11, || false, |_| false).unwrap();
        let destination: Vec<_> = s
            .deletion_preview(1, mover_store::DeletionScope::Destination)
            .unwrap()
            .map(|(targets, _)| targets)
            .unwrap_or_default()
            .into_iter()
            .filter(|t| t.kind != K::RetainedSource)
            .map(|t| (t.kind, t.relative_path, t.size_bytes))
            .collect();
        if offered {
            assert_eq!(
                destination,
                vec![
                    (K::DestinationPayload, "sub/data".into(), Some(3)),
                    (K::ManifestStaging, "COMMITTED.json".into(), None),
                ],
                "{point}"
            );
            confirm(&s, 1);
            let results = run_destination(&s);
            assert!(results.iter().all(|(_, d)| d.is_none()), "{results:?}");
            assert!(!f.destination.join("1").exists());
        } else {
            assert!(destination.is_empty(), "{point}: {destination:?}");
            assert_eq!(std::fs::read(f.final_path()).unwrap(), b"abc");
        }
        assert_eq!(std::fs::read(f.claimed()).unwrap(), b"abc");
    }
}
