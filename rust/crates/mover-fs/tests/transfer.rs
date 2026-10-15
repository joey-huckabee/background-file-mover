use mover_core::{DeliveryPolicy, FilePhase, FileSpec, Submission, TransferPhase};
use mover_fs::{
    authorize_publication, claim, copy_stage, prepare_transfer, publish_stage, transfer_one,
    verify_stage,
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
