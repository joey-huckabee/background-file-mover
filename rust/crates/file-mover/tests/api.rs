use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
#[test]
fn pending_capacity_retry_survives_restart_and_recovers_without_operator_resume() {
    let mut f = Fixture::uninitialized(300);
    assert!(
        initialize_source(&f.root.join("config.json"))
            .status
            .success()
    );
    provision_destination(&f);
    f.write("data", b"original recording");
    f.start_with_payload_fault(Some("payload_copy_write"));
    assert_eq!(
        f.post(&f.input("capacity-recovery", json!([{"name":"data"}])))
            .0,
        202
    );
    f.write("data", b"producer reused path");
    if cfg!(feature = "nfs-qualification") {
        let until = Instant::now() + Duration::from_secs(15);
        let pending = loop {
            let (_, current) = status(&f, "1");
            if current["details"]["delivery_retry"]["failures"] == 1 {
                break current;
            }
            assert!(Instant::now() < until, "{current}");
            std::thread::sleep(Duration::from_millis(50));
        };
        assert_eq!(pending["details"]["condition"], "Retrying");
        assert_eq!(
            pending["details"]["delivery_retry"]["code"],
            "destination_capacity_requires_review"
        );
        assert_eq!(pending["details"]["files"][0]["attempt"], 1);
        assert!(pending["details"]["latest_resume"].is_null());
        let partial = f.root.join("destination/1/.staging/1.part");
        let before = std::fs::read(&partial).unwrap();
        f.stop();
        f.start(); // Capacity fault removed; persisted deadline must still gate dispatch.
        assert_eq!(status(&f, "1").1, pending);
        std::thread::sleep(Duration::from_secs(1));
        assert_eq!(status(&f, "1").1, pending);
        let until = Instant::now() + Duration::from_secs(60);
        loop {
            let (_, current) = status(&f, "1");
            assert_ne!(current["details"]["condition"], "ReviewRequired");
            if current["state"] == "Committed" {
                assert_eq!(current["details"]["files"][0]["attempt"], 2);
                assert_eq!(
                    current["details"]["delivery_retry"],
                    pending["details"]["delivery_retry"]
                );
                assert!(current["details"]["latest_resume"].is_null());
                break;
            }
            assert!(Instant::now() < until, "{current}");
            std::thread::sleep(Duration::from_millis(50));
        }
        assert_eq!(std::fs::read(partial).unwrap(), before);
    }
    wait_manifest(&f, "1");
    assert_eq!(
        std::fs::read(f.root.join("destination/1/data")).unwrap(),
        b"original recording"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"original recording"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"producer reused path"
    );
    f.stop();
}
#[test]
fn effect_diagnostics_preserve_uncertain_allocations_manifest_review_and_recovery() {
    // Allocation sync can leave an unreceipted object: never promise auto-repair.
    for (fault, recoverable, committed_name) in [
        ("staging_allocate", false, false),
        ("staging_allocation_sync", false, false),
        ("staging_allocation_directory_sync", false, false),
        ("manifest_allocate", true, false),
        ("manifest_allocation_sync", false, false),
        ("manifest_staging_sync", false, false),
        ("manifest_truncate", true, false),
        ("manifest_seek", true, false),
        ("manifest_write", true, false),
        ("manifest_writable", true, false),
        ("manifest_readonly", true, false),
        ("manifest_file_sync", true, false),
        ("manifest_read", true, false),
        ("manifest_directory_sync", true, true),
    ] {
        let mut f = Fixture::uninitialized(300);
        assert!(
            initialize_source(&f.root.join("config.json"))
                .status
                .success()
        );
        provision_destination(&f);
        f.write("data", b"private recording contents");
        f.start_with_faults(None, Some(fault));
        assert_eq!(f.post(&f.input(fault, json!([{"name":"data"}]))).0, 202);
        f.write("data", b"producer reused path");
        if cfg!(feature = "nfs-qualification") {
            let deadline = Instant::now() + Duration::from_secs(45);
            let reviewed = loop {
                assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
                let (_, current) = status(&f, "1");
                assert_eq!(current["state"], "Claimed");
                if current["details"]["condition"] == "ReviewRequired" {
                    break current;
                }
                assert!(Instant::now() < deadline, "{fault}: {current}");
                std::thread::sleep(Duration::from_millis(50));
            };
            assert_eq!(reviewed["details"]["delivery_retry"]["failures"], 3);
            assert_eq!(
                reviewed["details"]["delivery_retry"]["code"],
                "delivery_requires_review"
            );
            let committed = f.root.join("destination/1/COMMITTED.json");
            assert_eq!(committed.exists(), committed_name, "{fault}");
            if committed_name {
                let manifest: Value =
                    serde_json::from_slice(&std::fs::read(&committed).unwrap()).unwrap();
                assert_eq!(manifest["job_id"], "1");
                assert_eq!(
                    std::fs::read(f.root.join("destination/1/data")).unwrap(),
                    b"private recording contents"
                );
            }
            let mut stderr = f.child.as_mut().unwrap().stderr.take().unwrap();
            f.stop();
            let mut log = String::new();
            stderr.read_to_string(&mut log).unwrap();
            let errno = 5;
            assert!(log.contains(&format!("{fault} errno={errno};")), "{log}");
            assert!(log.contains("preserve source/state"), "{log}");
            assert!(!log.contains("private recording contents"));
            assert!(!log.contains(f.root.to_str().unwrap()));
            // Removing the fixture fault does not itself clear review.
            f.start();
            assert_eq!(status(&f, "1").1, reviewed);
            assert_eq!(committed.exists(), committed_name);
            assert_eq!(
                std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
                b"private recording contents"
            );
            assert_eq!(
                std::fs::read(f.root.join("source/current/data")).unwrap(),
                b"producer reused path"
            );
            if !recoverable {
                // Existing exclusive-allocation refusal survives restart; no repair here.
                f.stop();
                continue;
            }
            assert_eq!(resume(&f, "1", &resume_body(0)).0, 200);
            assert_eq!(
                resume(&f, "1", &resume_body(0)).1["details"]["replay"],
                true
            );
        }
        wait_manifest(&f, "1");
        assert_eq!(
            std::fs::read(f.root.join("destination/1/data")).unwrap(),
            b"private recording contents"
        );
        assert_eq!(
            std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
            b"private recording contents"
        );
        assert_eq!(
            std::fs::read(f.root.join("source/current/data")).unwrap(),
            b"producer reused path"
        );
        f.stop();
    }
}

#[test]
fn payload_diagnostics_preserve_review_resume_and_production_ignores_faults() {
    for (fault, phase) in [
        ("payload_source_read", "Intent"),
        ("payload_copy_write", "Intent"),
        ("payload_copy_file_sync", "Intent"),
        ("payload_copy_directory_sync", "Intent"),
        ("payload_verification_read", "Copied"),
        ("payload_publication_file_sync", "PublishIntent"),
        ("payload_publication_staging_sync", "PublishIntent"),
        ("payload_publication_directory_sync", "PublishIntent"),
    ] {
        let mut f = Fixture::uninitialized(300);
        assert!(
            initialize_source(&f.root.join("config.json"))
                .status
                .success()
        );
        provision_destination(&f);
        f.write("data", b"private recording contents");
        f.start_with_payload_fault(Some(fault));
        assert_eq!(f.post(&f.input(fault, json!([{"name":"data"}]))).0, 202);
        f.write("data", b"producer reused path");
        if cfg!(feature = "nfs-qualification") {
            let deadline = Instant::now() + Duration::from_secs(150);
            let reviewed = loop {
                assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
                let (_, current) = status(&f, "1");
                assert_eq!(current["state"], "Claimed");
                assert!(!f.root.join("destination/1/COMMITTED.json").exists());
                if current["details"]["condition"] == "ReviewRequired" {
                    break current;
                }
                assert!(Instant::now() < deadline, "{fault}: {current}");
                std::thread::sleep(Duration::from_millis(50));
            };
            assert_eq!(reviewed["details"]["delivery_retry"]["failures"], 3);
            assert_eq!(
                reviewed["details"]["delivery_retry"]["code"],
                if fault == "payload_copy_write" {
                    "destination_capacity_requires_review"
                } else {
                    "delivery_requires_review"
                }
            );
            assert_eq!(reviewed["details"]["files"][0]["transfer_phase"], phase);
            let published = f.root.join("destination/1/data");
            assert_eq!(published.exists(), phase == "PublishIntent");
            if published.exists() {
                assert_eq!(
                    std::fs::read(published).unwrap(),
                    b"private recording contents"
                );
            }
            let mut stderr = f.child.as_mut().unwrap().stderr.take().unwrap();
            f.stop();
            let mut log = String::new();
            stderr.read_to_string(&mut log).unwrap();
            let errno = if fault == "payload_copy_write" { 28 } else { 5 };
            assert!(log.contains(&format!("{fault} errno={errno};")), "{log}");
            assert!(log.contains("preserve source/state"), "{log}");
            assert!(!log.contains("private recording contents"));
            assert!(!log.contains(f.root.to_str().unwrap()));
            // Removing the fixture fault does not itself clear review.
            f.start();
            assert_eq!(status(&f, "1").1, reviewed);
            assert!(!f.root.join("destination/1/COMMITTED.json").exists());
            assert_eq!(resume(&f, "1", &resume_body(0)).0, 200);
            assert_eq!(
                resume(&f, "1", &resume_body(0)).1["details"]["replay"],
                true
            );
        }
        wait_manifest(&f, "1");
        assert_eq!(
            std::fs::read(f.root.join("destination/1/data")).unwrap(),
            b"private recording contents"
        );
        assert_eq!(
            std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
            b"private recording contents"
        );
        assert_eq!(
            std::fs::read(f.root.join("source/current/data")).unwrap(),
            b"producer reused path"
        );
        f.stop();
    }
}

#[test]
fn enrollment_io_failures_preserve_prepared_state_and_production_ignores_controls() {
    for fault in [
        "short_write",
        "interrupted_write",
        "write_zero",
        "write_enospc",
        "write_eio",
        "file_sync",
        "directory_sync",
    ] {
        let mut f = Fixture::uninitialized(300);
        f.write("data", b"producer input must remain untouched");
        let config = f.root.join("config.json");
        let result = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
            .arg("--initialize-source")
            .arg(&config)
            .env("FILE_MOVER_QUALIFICATION_ENROLLMENT_FAULT", fault)
            .output()
            .unwrap();
        let failed = cfg!(feature = "nfs-qualification")
            && !["short_write", "interrupted_write"].contains(&fault);
        assert_eq!(result.status.success(), !failed, "{fault}: {result:?}");
        let receipt = f.root.join("source/.file-mover/source-enrollment.json");
        let bytes = std::fs::read(&receipt).unwrap();
        let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let ownership = store.source_ownership().unwrap().unwrap();
        assert_eq!(ownership.object.is_none(), failed);
        assert_eq!(store.job_count().unwrap(), 0);
        drop(store);
        if failed {
            let error = String::from_utf8(result.stderr).unwrap();
            assert!(error.contains("create_receipt"), "{error}");
            assert!(
                error.contains("preserve original state and source for review"),
                "{error}"
            );
            let stage = match fault {
                "file_sync" => "enrollment_file_sync errno=5",
                "directory_sync" => "enrollment_directory_sync errno=5",
                "write_enospc" => "enrollment_write errno=28",
                "write_eio" => "enrollment_write errno=5",
                _ => "enrollment write returned zero",
            };
            assert!(error.contains(stage), "{error}");
            if fault.starts_with("write_") {
                assert_eq!(bytes.len(), 7);
                assert!(ownership.receipt.as_bytes().starts_with(&bytes));
            } else {
                assert_eq!(bytes, ownership.receipt.as_bytes());
            }
            assert!(refused_start(&config).contains("enrollment pending"));
            assert!(!initialize_source(&config).status.success());
            assert_eq!(std::fs::read(&receipt).unwrap(), bytes);
        } else {
            assert_eq!(bytes, ownership.receipt.as_bytes());
            f.start();
            f.stop();
        }
        assert_eq!(
            std::fs::read(f.root.join("source/current/data")).unwrap(),
            b"producer input must remain untouched"
        );
    }
}

#[test]
fn missing_enrollment_receipt_reports_verification_stage_without_repair() {
    let mut f = Fixture::new(300);
    f.stop();
    let receipt = f.root.join("source/.file-mover/source-enrollment.json");
    std::fs::remove_file(&receipt).unwrap();
    let output = initialize_source(&f.root.join("config.json"));
    assert!(!output.status.success());
    let log = String::from_utf8(output.stderr).unwrap();
    assert!(log.contains("verify_receipt"), "{log}");
    assert!(
        log.contains("preserve original state and source for review"),
        "{log}"
    );
    assert!(!receipt.exists());
}

fn initialize_source(config: &std::path::Path) -> std::process::Output {
    Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--initialize-source")
        .arg(config)
        .output()
        .unwrap()
}
#[test]
fn explicit_source_enrollment_is_required_and_matching_restart_keeps_the_pair() {
    let mut f = Fixture::uninitialized(300);
    let config = f.root.join("config.json");
    assert!(refused_start(&config).contains("SourceEnrollmentRequired"));
    let receipt = f.root.join("source/.file-mover/source-enrollment.json");
    assert!(!receipt.exists());
    assert!(initialize_source(&config).status.success());
    let bytes = std::fs::read(&receipt).unwrap();
    f.start();
    f.write("data", b"first enrolled recording");
    let body = f.input("paired", json!([{"name":"data"}]));
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    assert!(initialize_source(&config).status.success());
    assert_eq!(std::fs::read(&receipt).unwrap(), bytes);
    f.start();
    assert_eq!(f.post(&body).0, 202);
    f.stop();
}
#[test]
fn fresh_database_cannot_adopt_enrolled_source_after_clean_release() {
    let mut f = Fixture::new(300);
    f.write("data", b"private old state payload");
    assert_eq!(
        f.post(&f.input("old-state", json!([{"name":"data"}]))).0,
        202
    );
    f.stop();
    let receipt = f.root.join("source/.file-mover/source-enrollment.json");
    let saved = std::fs::read(&receipt).unwrap();
    let path = f.root.join("config.json");
    let original = std::fs::read(&path).unwrap();
    let mut config: Value = serde_json::from_slice(&original).unwrap();
    let fresh = f.root.join("fresh-state");
    std::fs::create_dir(&fresh).unwrap();
    std::fs::set_permissions(&fresh, std::fs::Permissions::from_mode(0o700)).unwrap();
    config["state_database"] = json!(fresh.join("jobs.sqlite"));
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    assert!(refused_start(&path).contains("SourceEnrollmentRequired"));
    assert!(!initialize_source(&path).status.success());
    assert_eq!(std::fs::read(&receipt).unwrap(), saved);
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"private old state payload"
    );
    std::fs::write(&path, original).unwrap();
    f.start();
    f.stop();
}
#[test]
fn missing_unsafe_or_replaced_active_receipt_is_never_repaired() {
    for case in [
        "missing",
        "foreign",
        "permissions",
        "symlink",
        "hardlink",
        "replacement",
        "oversized",
        "fifo",
    ] {
        let mut f = Fixture::new(300);
        f.stop();
        let receipt = f.root.join("source/.file-mover/source-enrollment.json");
        let bytes = std::fs::read(&receipt).unwrap();
        let backup = f.root.join("receipt-backup");
        match case {
            "missing" => std::fs::remove_file(&receipt).unwrap(),
            "foreign" => {
                std::fs::set_permissions(&receipt, std::fs::Permissions::from_mode(0o600)).unwrap();
                std::fs::write(&receipt, b"{}").unwrap();
            }
            "permissions" => {
                std::fs::set_permissions(&receipt, std::fs::Permissions::from_mode(0o600)).unwrap()
            }
            "symlink" => {
                std::fs::rename(&receipt, &backup).unwrap();
                std::os::unix::fs::symlink(&backup, &receipt).unwrap();
            }
            "hardlink" => std::fs::hard_link(&receipt, &backup).unwrap(),
            "replacement" => {
                std::fs::rename(&receipt, &backup).unwrap();
                std::fs::write(&receipt, &bytes).unwrap();
                std::fs::set_permissions(&receipt, std::fs::Permissions::from_mode(0o400)).unwrap();
            }
            "oversized" => {
                std::fs::set_permissions(&receipt, std::fs::Permissions::from_mode(0o600)).unwrap();
                std::fs::write(&receipt, vec![b'x'; 8193]).unwrap();
            }
            "fifo" => {
                std::fs::remove_file(&receipt).unwrap();
                assert!(
                    Command::new("mkfifo")
                        .arg(&receipt)
                        .status()
                        .unwrap()
                        .success()
                );
            }
            _ => unreachable!(),
        }
        refused_start(&f.root.join("config.json"));
        assert!(
            !initialize_source(&f.root.join("config.json"))
                .status
                .success(),
            "{case}"
        );
        if case == "missing" {
            assert!(!receipt.exists());
        }
    }
}
#[test]
fn prepared_enrollment_retries_only_without_an_ambiguous_root_receipt() {
    for created in [false, true] {
        let mut f = Fixture::uninitialized(300);
        let config = f.root.join("config.json");
        let source = f.root.join("source");
        let guard =
            mover_fs::LocalClaimLock::acquire_bound(source.to_str().unwrap(), &binding()).unwrap();
        let auth = guard.source_authorization().unwrap();
        let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let receipt = mover_fs::EnrollmentReceipt::new(store.instance_id().unwrap(), auth).encode();
        store
            .prepare_source_ownership(
                source.to_str().unwrap(),
                &auth.binding.encode(),
                &auth.observation,
                &receipt,
            )
            .unwrap();
        if created {
            mover_fs::create_source_enrollment(source.to_str().unwrap(), auth, &receipt).unwrap();
        }
        drop(store);
        drop(guard);
        assert!(refused_start(&config).contains("enrollment pending"));
        let initialized = initialize_source(&config);
        assert_eq!(initialized.status.success(), !created, "{initialized:?}");
        if !created {
            f.start();
            f.stop();
        } else {
            assert!(refused_start(&config).contains("enrollment pending"));
        }
    }
}
#[test]
fn source_enrollment_refuses_legacy_namespace_and_existing_local_enrollment() {
    for local in [false, true] {
        let f = Fixture::uninitialized(300);
        if local {
            let source = f.root.join("source");
            let guard =
                mover_fs::LocalClaimLock::acquire_bound(source.to_str().unwrap(), &binding())
                    .unwrap();
            let auth = guard.source_authorization().unwrap();
            mover_store::Store::open(f.root.join("state/jobs.sqlite"))
                .unwrap()
                .enroll_source(
                    source.to_str().unwrap(),
                    &binding().encode(),
                    &auth.observation,
                )
                .unwrap();
        } else {
            std::fs::create_dir(f.root.join("source/.file-mover/1-0")).unwrap();
        }
        assert!(
            !initialize_source(&f.root.join("config.json"))
                .status
                .success()
        );
        assert!(
            !f.root
                .join("source/.file-mover/source-enrollment.json")
                .exists()
        );
    }
}
#[test]
fn active_source_receipt_replacement_blocks_live_claim() {
    let mut f = Fixture::new(300);
    f.write("data", b"producer data");
    let receipt = f.root.join("source/.file-mover/source-enrollment.json");
    let bytes = std::fs::read(&receipt).unwrap();
    std::fs::rename(&receipt, f.root.join("original-receipt")).unwrap();
    std::fs::write(&receipt, bytes).unwrap();
    std::fs::set_permissions(&receipt, std::fs::Permissions::from_mode(0o400)).unwrap();
    let (status, body) = f.post(&f.input("changed-enrollment", json!([{"name":"data"}])));
    assert_eq!(status, 409);
    assert_eq!(body["source_paths_released"], false);
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"producer data"
    );
    f.stop();
}
#[test]
fn missing_or_unsafe_source_lock_refuses_before_sqlite_and_never_repairs_it() {
    use std::os::unix::fs::symlink;
    for case in [
        "missing",
        "permissions",
        "symlink",
        "hardlink",
        "content",
        "fifo",
    ] {
        let mut f = Fixture::new(300);
        f.stop();
        let source = f.root.join("source");
        let lock = source.join(".file-mover/coordinator.lock");
        match case {
            "missing" => std::fs::remove_file(&lock).unwrap(),
            "permissions" => {
                std::fs::set_permissions(&lock, std::fs::Permissions::from_mode(0o644)).unwrap()
            }
            "symlink" => {
                let backup = f.root.join("lock-backup");
                std::fs::rename(&lock, &backup).unwrap();
                symlink(backup, &lock).unwrap();
            }
            "hardlink" => std::fs::hard_link(&lock, f.root.join("lock-alias")).unwrap(),
            "content" => std::fs::write(&lock, b"not a lease").unwrap(),
            "fifo" => {
                std::fs::remove_file(&lock).unwrap();
                assert!(
                    Command::new("mkfifo")
                        .arg(&lock)
                        .status()
                        .unwrap()
                        .success()
                );
                std::fs::set_permissions(&lock, std::fs::Permissions::from_mode(0o600)).unwrap();
            }
            _ => unreachable!(),
        }
        let fresh = f.root.join("fresh-state");
        std::fs::create_dir(&fresh).unwrap();
        std::fs::set_permissions(&fresh, std::fs::Permissions::from_mode(0o700)).unwrap();
        let path = f.root.join("config.json");
        let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        config["state_database"] = json!(fresh.join("jobs.sqlite"));
        std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
        refused_start(&path);
        assert!(!fresh.join("jobs.sqlite").exists());
        if case == "missing" {
            assert!(!lock.exists());
        }
    }
}
#[test]
fn old_binding_versions_cannot_start_the_enrollment_protocol() {
    let mut f = Fixture::new(300);
    f.stop();
    let path = f.root.join("config.json");
    let original: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    for (role, version) in [
        ("source_binding", 1),
        ("source_binding", 2),
        ("destination_binding", 1),
        ("destination_binding", 2),
    ] {
        let mut config = original.clone();
        config[role]["version"] = json!(version);
        std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
        assert!(refused_start(&path).contains("invalid"));
    }
}
#[test]
fn replaced_source_lock_cannot_rebind_and_original_custody_can_restart() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained recording");
    let body = f.input("lock-restart", json!([{"name":"data"}]));
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    let root = f.root.join("source");
    let lock = root.join(".file-mover/coordinator.lock");
    let original = f.root.join("original-lock");
    std::fs::rename(&lock, &original).unwrap();
    provision_lock(&root);
    assert!(refused_start(&f.root.join("config.json")).contains("SourceRootChanged"));
    assert_eq!(
        std::fs::read(root.join(".file-mover/1-0/data")).unwrap(),
        b"retained recording"
    );
    std::fs::remove_file(&lock).unwrap();
    std::fs::rename(original, lock).unwrap();
    f.start();
    assert_eq!(f.post(&body).0, 202);
    f.stop();
}
#[test]
fn live_source_lock_replacement_blocks_claim_without_releasing_paths() {
    let mut f = Fixture::new(300);
    f.write("data", b"producer still owns this");
    let source = f.root.join("source");
    std::fs::rename(
        source.join(".file-mover/coordinator.lock"),
        f.root.join("held-lock"),
    )
    .unwrap();
    provision_lock(&source);
    let (code, reply) = f.post(&f.input("lock-changed", json!([{"name":"data"}])));
    assert_eq!(code, 409);
    assert_eq!(reply["source_paths_released"], false);
    assert_eq!(
        std::fs::read(source.join("current/data")).unwrap(),
        b"producer still owns this"
    );
    assert!(!source.join(".file-mover/1-0").exists());
    f.stop();
}
#[test]
fn claim_worker_rejects_directory_and_readonly_lock_descriptors() {
    use std::os::fd::AsFd;
    let mut f = Fixture::new(300);
    f.stop();
    f.write("data", b"untouched");
    for relative in [".file-mover", ".file-mover/coordinator.lock"] {
        let descriptor = std::fs::File::open(f.root.join("source").join(relative)).unwrap();
        let (mut channel, worker) = std::os::unix::net::UnixStream::pair().unwrap();
        let instance = mover_fs::InstanceGuard::for_database(
            f.root.join("state/jobs.sqlite").to_str().unwrap(),
        )
        .unwrap();
        instance.prepare_workers().unwrap();
        let mut child = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
            .arg("--internal-claim-worker")
            .stdin(Stdio::from(
                descriptor.as_fd().try_clone_to_owned().unwrap(),
            ))
            .stdout(Stdio::from(descriptor))
            .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
            .spawn()
            .unwrap();
        channel
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        instance.send(&mut channel).unwrap();
        let assignment = json!({"assignment":{"operation":"observe","version":1,"job_id":1,"file_index":0,"root_path":f.root.join("source"),"source_name":"current/data","expected_size":null},"source_authorization":null});
        channel
            .write_all(&serde_json::to_vec(&assignment).unwrap())
            .unwrap();
        channel.shutdown(std::net::Shutdown::Write).unwrap();
        let mut response = Vec::new();
        channel.read_to_end(&mut response).unwrap();
        assert!(child.wait().unwrap().success());
        let response: Value = serde_json::from_slice(&response).unwrap();
        assert!(response["error"].is_string());
        assert!(response["claim"].is_null());
        assert!(!f.root.join("source/.file-mover/1-0").exists());
    }
}
#[test]
fn delivery_worker_refuses_replaced_destination_lock_before_payload() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained");
    assert_eq!(
        f.post(&f.input("lock-session", json!([{"name":"data"}]))).0,
        202
    );
    f.stop();
    provision_destination(&f);
    let guard = mover_fs::LocalClaimLock::acquire_bound(
        f.root.join("source").to_str().unwrap(),
        &binding(),
    )
    .unwrap();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let t = prepare_transfer_bound(&store, 1).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    let (mut child, mut channel) = effect_child(&guard, &guard, "--internal-delivery-worker");
    let opened = session_authorized_reply(
        &mut channel,
        1,
        json!({"operation":"open","job_id":1,"source_root":f.root.join("source"),"destination_root":f.root.join("destination"),"destination_binding":destination_binding(),"destination_observation":store.destination_observation(1).unwrap()}),
        guard.source_authorization(),
    );
    assert!(opened["error"].is_null());
    let destination = f.root.join("destination");
    std::fs::rename(
        destination.join(".file-mover/coordinator.lock"),
        f.root.join("held-destination-lock"),
    )
    .unwrap();
    provision_lock(&destination);
    let refused = session_authorized_reply(
        &mut channel,
        2,
        json!({"operation":"payload","assignment":payload_assignment(&t,&claim)}),
        guard.source_authorization(),
    );
    assert_eq!(refused["error"], "destination_binding_refused");
    assert!(refused["transfer"].is_null());
    drop(channel);
    assert!(child.wait().unwrap().success());
    assert_eq!(
        std::fs::metadata(destination.join("1/.staging/1.part"))
            .unwrap()
            .len(),
        0
    );
}
fn binding() -> mover_fs::SourceBinding {
    serde_json::from_value(
        json!({"version":3,"coordinator_id":"test-owner","root_id":"local-source",
        "endpoint_id":"test-local","marker_id":"test-marker","filesystem":"local","role":"source"}),
    )
    .unwrap()
}
fn destination_binding() -> mover_fs::DestinationBinding {
    serde_json::from_value(json!({"version":3,"coordinator_id":"test-owner","root_id":"configured-local",
        "endpoint_id":"test-local-destination","marker_id":"test-destination-marker","filesystem":"local","role":"destination"})).unwrap()
}
fn provision_lock(root: &std::path::Path) {
    use std::fs::OpenOptions;
    use std::os::unix::fs::OpenOptionsExt;
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(root.join(".file-mover/coordinator.lock"))
        .unwrap();
}
fn provision_destination_marker(root: &std::path::Path) {
    let marker = root.join(".file-mover/destination-binding.json");
    std::fs::write(&marker, destination_binding().encode()).unwrap();
    std::fs::set_permissions(marker, std::fs::Permissions::from_mode(0o600)).unwrap();
}
fn provision_binding(root: &std::path::Path) {
    let marker = root.join(".file-mover/source-binding.json");
    std::fs::write(&marker, binding().encode()).unwrap();
    std::fs::set_permissions(marker, std::fs::Permissions::from_mode(0o600)).unwrap();
}
fn refused_start(config: &std::path::Path) -> String {
    let output = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg(config)
        .output()
        .unwrap();
    assert!(!output.status.success());
    let log = format!(
        "{}{}",
        String::from_utf8(output.stdout).unwrap(),
        String::from_utf8(output.stderr).unwrap()
    );
    assert!(!log.contains("Ready on"), "{log}");
    log
}
#[test]
fn source_marker_and_filesystem_failures_precede_sqlite() {
    let mut f = Fixture::new(300);
    f.stop();
    let source = f.root.join("source");
    let marker = source.join(".file-mover/source-binding.json");
    let fresh = f.root.join("fresh-state");
    std::fs::create_dir(&fresh).unwrap();
    std::fs::set_permissions(&fresh, std::fs::Permissions::from_mode(0o700)).unwrap();
    let config_path = f.root.join("config.json");
    let original: Value = serde_json::from_slice(&std::fs::read(&config_path).unwrap()).unwrap();
    let backup = f.root.join("marker-backup");
    std::fs::write(&backup, binding().encode()).unwrap();
    std::fs::set_permissions(&backup, std::fs::Permissions::from_mode(0o600)).unwrap();
    for case in [
        "missing",
        "foreign",
        "filesystem",
        "permissions",
        "symlink",
        "hardlink",
        "oversized",
        "invalid",
    ] {
        let _ = std::fs::remove_file(&marker);
        let alias = f.root.join("marker-alias");
        let _ = std::fs::remove_file(&alias);
        provision_binding(&source);
        let mut config = original.clone();
        config["state_database"] = json!(fresh.join("jobs.sqlite"));
        match case {
            "missing" => std::fs::remove_file(&marker).unwrap(),
            "foreign" => {
                let mut b = binding();
                b.coordinator_id = "foreign-owner".into();
                std::fs::write(&marker, b.encode()).unwrap();
            }
            "filesystem" => {
                let mut b = binding();
                b.filesystem = mover_fs::SourceFilesystem::Nfs;
                config["source_binding"] = json!(b);
                std::fs::write(&marker, b.encode()).unwrap();
            }
            "permissions" => {
                std::fs::set_permissions(&marker, std::fs::Permissions::from_mode(0o644)).unwrap()
            }
            "symlink" => {
                std::fs::remove_file(&marker).unwrap();
                std::os::unix::fs::symlink(&backup, &marker).unwrap();
            }
            "hardlink" => std::fs::hard_link(&marker, &alias).unwrap(),
            "oversized" => std::fs::write(&marker, vec![b'x'; 4097]).unwrap(),
            "invalid" => std::fs::write(&marker, b"{}").unwrap(),
            _ => unreachable!(),
        }
        std::fs::write(&config_path, serde_json::to_vec(&config).unwrap()).unwrap();
        refused_start(&config_path);
        assert!(!fresh.join("jobs.sqlite").exists(), "{case}");
    }
}
#[test]
fn source_marker_replacement_blocks_restart_without_rebinding_or_losing_claims() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained");
    let input = f.input("binding-restart", json!([{"name":"data"}]));
    assert_eq!(f.post(&input).0, 202);
    f.write("data", b"next recording");
    f.stop();
    let marker = f.root.join("source/.file-mover/source-binding.json");
    let held = f.root.join("original-marker");
    std::fs::rename(&marker, &held).unwrap();
    provision_binding(&f.root.join("source"));
    let log = refused_start(&f.root.join("config.json"));
    assert!(log.contains("SourceRootChanged"), "{log}");
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"retained"
    );
    std::fs::remove_file(&marker).unwrap();
    std::fs::rename(&held, &marker).unwrap();
    f.start();
    assert_eq!(f.post(&input).0, 202);
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"next recording"
    );
}
#[test]
fn marker_change_during_runtime_blocks_claim_before_source_movement() {
    let f = Fixture::new(300);
    f.write("data", b"untouched");
    let mut b = binding();
    b.marker_id = "changed".into();
    std::fs::write(
        f.root.join("source/.file-mover/source-binding.json"),
        b.encode(),
    )
    .unwrap();
    let (code, reply) = f.post(&f.input("changed-binding", json!([{"name":"data"}])));
    assert_eq!(code, 409);
    assert_eq!(reply["source_paths_released"], false);
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"untouched"
    );
    assert!(!f.root.join("source/.file-mover/1-0/data").exists());
}
#[test]
fn replacement_root_with_original_marker_cannot_rebind_existing_state() {
    let mut f = Fixture::new(300);
    f.write("data", b"original source");
    f.stop();
    let source = f.root.join("source");
    let original = f.root.join("original-source");
    std::fs::rename(&source, &original).unwrap();
    std::fs::create_dir(&source).unwrap();
    std::fs::create_dir(source.join(".file-mover")).unwrap();
    for path in [&source, &source.join(".file-mover")] {
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).unwrap();
    }
    provision_lock(&source);
    let marker = ".file-mover/source-binding.json";
    std::fs::rename(original.join(marker), source.join(marker)).unwrap();
    assert!(refused_start(&f.root.join("config.json")).contains("SourceRootChanged"));
    assert_eq!(
        std::fs::read(original.join("current/data")).unwrap(),
        b"original source"
    );
    std::fs::rename(source.join(marker), original.join(marker)).unwrap();
    std::fs::remove_file(source.join(".file-mover/coordinator.lock")).unwrap();
    std::fs::remove_dir(source.join(".file-mover")).unwrap();
    std::fs::remove_dir(&source).unwrap();
    std::fs::rename(&original, &source).unwrap();
    f.start();
}
#[test]
fn source_binding_is_required_and_strictly_validated() {
    let base = json!({"bind":"127.0.0.1:0","generator_id":"g","source_root":"/source","destination_root":"/destination","destination_binding":destination_binding(),"state_database":"/state/jobs.sqlite"});
    assert!(serde_json::from_value::<file_mover::Config>(base.clone()).is_err());
    for field in ["coordinator_id", "root_id", "endpoint_id", "marker_id"] {
        let mut value = base.clone();
        value["source_binding"] = json!(binding());
        value["source_binding"][field] = json!("../wrong");
        assert!(
            serde_json::from_value::<file_mover::Config>(value)
                .unwrap()
                .validate()
                .is_err()
        );
    }
    for (field, bad) in [
        ("filesystem", json!("auto")),
        ("role", json!("destination")),
        ("extra", json!(true)),
    ] {
        let mut value = base.clone();
        value["source_binding"] = json!(binding());
        value["source_binding"][field] = bad;
        assert!(serde_json::from_value::<file_mover::Config>(value).is_err());
    }
}
#[test]
fn populated_unenrolled_state_refuses_service_startup_and_preserves_source() {
    let mut f = Fixture::new(300);
    f.stop();
    f.write("data", b"legacy source");
    let state = f.root.join("legacy-state");
    std::fs::create_dir(&state).unwrap();
    std::fs::set_permissions(&state, std::fs::Permissions::from_mode(0o700)).unwrap();
    let path = state.join("jobs.sqlite");
    let store = mover_store::Store::open(&path).unwrap();
    let submission = mover_core::Submission::new(
        "recorder",
        "legacy",
        f.root.join("source/current").to_str().unwrap(),
        vec![mover_core::FileSpec::new("data", None).unwrap()],
    )
    .unwrap();
    let context = mover_store::AcceptanceContext {
        source_root_id: "local-source".into(),
        source_root_path: f.root.join("source").to_str().unwrap().into(),
        source_relative_directory: "current".into(),
        destination_path: f.root.join("destination").to_str().unwrap().into(),
        destination_binding: None,
        missing_retry_seconds: 300,
        policy: mover_core::DeliveryPolicy {
            destination_id: "configured-local".into(),
            group_by_generator: false,
            delete_source_after_commit: false,
        },
    };
    let job = store.accept(&submission, &context).unwrap();
    drop(store);
    let config_path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&config_path).unwrap()).unwrap();
    config["state_database"] = json!(path);
    std::fs::write(&config_path, serde_json::to_vec(&config).unwrap()).unwrap();
    assert!(refused_start(&config_path).contains("SourceEnrollmentRequired"));
    let store = mover_store::Store::open(&path).unwrap();
    assert_eq!(
        store.get(job.job_id).unwrap().unwrap().recording,
        job.recording
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"legacy source"
    );
}
#[test]
fn executable_identifies_its_compiled_filesystem_capability() {
    let result = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--check-platform")
        .output()
        .unwrap();
    assert!(result.status.success());
    let mode = if mover_fs::nfs_qualification_enabled() {
        "nfs-qualification"
    } else {
        "production"
    };
    assert!(
        String::from_utf8(result.stdout)
            .unwrap()
            .contains(&format!("build={mode}"))
    );
}
#[test]
fn stopped_startup_exits_cleanly_without_source_or_database_access() {
    let mut f = Fixture::new(300);
    f.stop();
    let source = f.root.join("absent-source");
    let database = f.root.join("absent-state/jobs.sqlite");
    let config: file_mover::Config = serde_json::from_value(json!({
        "bind":"127.0.0.1:0","generator_id":"recorder","source_root":source,
        "source_binding":binding(),"destination_binding":destination_binding(),
        "destination_root":f.root.join("destination"),"state_database":database
    }))
    .unwrap();
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap()
        .block_on(async {
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            file_mover::serve(
                listener,
                config,
                std::sync::Arc::new(std::sync::atomic::AtomicBool::new(true)),
            )
            .await
            .unwrap();
        });
    assert!(!source.exists());
    assert!(!database.exists());
}
fn bootstrap_child(f: &Fixture, body: &Value) -> (Child, std::os::unix::net::UnixStream) {
    let mut body = body.clone();
    body["source_binding"] = json!(binding());
    let (mut channel, worker) = std::os::unix::net::UnixStream::pair().unwrap();
    let guard =
        mover_fs::InstanceGuard::for_database(f.root.join("state/jobs.sqlite").to_str().unwrap())
            .unwrap();
    channel
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    guard.prepare_workers().unwrap();
    let child = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--internal-bootstrap-worker")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
        .spawn()
        .unwrap();
    guard.send(&mut channel).unwrap();
    channel
        .write_all(&serde_json::to_vec(&body).unwrap())
        .unwrap();
    channel.shutdown(std::net::Shutdown::Write).unwrap();
    (child, channel)
}
#[test]
fn bootstrap_transfers_the_locked_description_without_reopening_source() {
    let mut f = Fixture::new(300);
    f.stop();
    let path = f.root.join("source").to_str().unwrap().to_owned();
    let (mut child, channel) = bootstrap_child(&f, &json!({"version":1,"source_root":path}));
    let mut receiver = mover_fs::BootstrapReceiver::default();
    let deadline = Instant::now() + Duration::from_secs(5);
    let lock = loop {
        if let Some(lock) = receiver
            .poll_bound(&channel, &path, Some(&binding()))
            .unwrap()
        {
            break lock;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    };
    assert!(child.wait().unwrap().success());
    lock.validate().unwrap();
    assert!(mover_fs::LocalClaimLock::acquire(&path).is_err());
    let inherited = lock.inherit().unwrap();
    drop(lock);
    assert!(mover_fs::LocalClaimLock::acquire(&path).is_err());
    drop(inherited);
    assert!(mover_fs::LocalClaimLock::acquire(&path).is_ok());
}
#[test]
fn bootstrap_rejects_wrong_scope_and_invalid_requests() {
    let mut f = Fixture::new(300);
    f.stop();
    let path = f.root.join("source").to_str().unwrap().to_owned();
    for body in [
        json!({"version":2,"source_root":path}),
        json!({"version":1,"source_root":path,"unexpected":true}),
        json!({"version":1,"source_root":"x".repeat(17000)}),
    ] {
        let (mut child, channel) = bootstrap_child(&f, &body);
        assert!(!child.wait().unwrap().success());
        let mut receiver = mover_fs::BootstrapReceiver::default();
        loop {
            match receiver.poll_bound(&channel, &path, Some(&binding())) {
                Err(_) => break,
                Ok(None) => {}
                Ok(Some(_)) => panic!("invalid bootstrap received custody"),
            }
        }
    }
    let (mut child, channel) = bootstrap_child(&f, &json!({"version":1,"source_root":path}));
    assert!(child.wait().unwrap().success());
    let mut receiver = mover_fs::BootstrapReceiver::default();
    loop {
        match receiver.poll_bound(&channel, "/another/source", Some(&binding())) {
            Err(_) => break,
            Ok(None) => {}
            Ok(Some(_)) => panic!("wrong scope received custody"),
        }
    }
    drop(receiver);
    drop(channel);
    assert!(mover_fs::LocalClaimLock::acquire(&path).is_ok());
}
#[test]
fn startup_contention_never_announces_readiness_or_opens_sqlite() {
    let mut f = Fixture::new(300);
    f.stop();
    let _held = mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let fresh = f.root.join("fresh-state");
    std::fs::create_dir(&fresh).unwrap();
    std::fs::set_permissions(&fresh, std::fs::Permissions::from_mode(0o700)).unwrap();
    let config_path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&config_path).unwrap()).unwrap();
    config["state_database"] = json!(fresh.join("jobs.sqlite"));
    std::fs::write(&config_path, serde_json::to_vec(&config).unwrap()).unwrap();
    let output = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg(config_path)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(
        !String::from_utf8(output.stdout)
            .unwrap()
            .contains("Ready on")
    );
    assert!(!fresh.join("jobs.sqlite").exists());
}
#[test]
fn delivery_session_large_manifest_returns_metadata_only_receipts() {
    let mut f = Fixture::new(300);
    f.write("data", b"large manifest");
    assert_eq!(
        f.post(&f.input("large-manifest", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let t = prepare_transfer_bound(&store, 1).unwrap();
    let t = mover_fs::copy_stage(&store, &t).unwrap();
    let t = mover_fs::verify_stage(&store, &t).unwrap();
    let t = mover_fs::authorize_publication(&store, &t).unwrap();
    let t = mover_fs::publish_stage(&store, &t).unwrap();
    let c = store.claim_intent(1, 0).unwrap().unwrap().0;
    let mut m = mover_fs::expected_manifest(&store, 1).unwrap();
    // Keep identical valid V1 metadata while exercising the full document bound.
    let end = m.bytes.pop().unwrap();
    assert_eq!(end, '}');
    m.bytes.push_str(&" ".repeat(40000));
    m.bytes.push('}');
    assert!(m.bytes.len() > 32768 && m.bytes.len() < 131072);
    assert!(serde_json::from_str::<Value>(&m.bytes).is_ok());
    let hash_input = f.root.join("hash-input");
    std::fs::write(&hash_input, m.bytes.as_bytes()).unwrap();
    let digest = Command::new("sha256sum").arg(&hash_input).output().unwrap();
    assert!(digest.status.success());
    m.sha256 = String::from_utf8(digest.stdout)
        .unwrap()
        .split_whitespace()
        .next()
        .unwrap()
        .into();
    store.save_manifest(&m).unwrap();
    let (mut child, mut channel) = effect_child(&source, &source, "--internal-delivery-worker");
    assert!(session_reply(&mut channel,1,json!({"operation":"open","job_id":1,"source_root":f.root.join("source"),"destination_root":f.root.join("destination")}))["error"].is_null());
    for phase in 1..=4 {
        let r = session_reply(
            &mut channel,
            phase + 1,
            json!({"operation":"manifest","assignment":payload_assignment(&t,&c),"manifest":{"job_id":m.job_id,"bytes":m.bytes,"sha256":m.sha256,"phase":m.phase,"object":m.object.as_ref().map(mover_core::ObjectIdentity::encode)}}),
        );
        assert!(r["error"].is_null());
        assert!(r["manifest"].get("bytes").is_none());
        assert!(serde_json::to_vec(&r).unwrap().len() < 2048);
        assert_eq!(r["manifest"]["phase"], phase);
        assert_eq!(r["manifest"]["sha256"], m.sha256);
        m.phase = phase as i64;
        m.object = Some(
            mover_core::ObjectIdentity::decode(r["manifest"]["object"].as_str().unwrap()).unwrap(),
        );
        store.save_manifest(&m).unwrap();
    }
    assert_eq!(
        std::fs::read_to_string(f.root.join("destination/1/COMMITTED.json")).unwrap(),
        m.bytes
    );
    channel.shutdown(std::net::Shutdown::Write).unwrap();
    assert!(child.wait().unwrap().success());
}
fn session_reply(
    channel: &mut std::os::unix::net::UnixStream,
    sequence: u64,
    command: Value,
) -> Value {
    session_authorized_reply(channel, sequence, command, None)
}
fn session_authorized_reply(
    channel: &mut std::os::unix::net::UnixStream,
    sequence: u64,
    command: Value,
    authorization: Option<&mover_fs::SourceAuthorization>,
) -> Value {
    let bytes = serde_json::to_vec(&json!({"version":2,"sequence":sequence,"command":command,"source_authorization":authorization})).unwrap();
    channel
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .unwrap();
    channel.write_all(&bytes).unwrap();
    let mut header = [0; 4];
    channel.read_exact(&mut header).unwrap();
    let size = u32::from_be_bytes(header) as usize;
    assert!(size <= 32768);
    let mut bytes = vec![0; size];
    channel.read_exact(&mut bytes).unwrap();
    let reply: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(reply["version"], 2);
    assert_eq!(reply["sequence"], sequence);
    reply
}
#[test]
fn delivery_session_checks_source_binding_and_rejects_authorization_downgrade() {
    let mut f = Fixture::new(300);
    f.write("data", b"source retained");
    assert_eq!(
        f.post(&f.input("session-binding", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let guard = mover_fs::LocalClaimLock::acquire_bound(
        f.root.join("source").to_str().unwrap(),
        &binding(),
    )
    .unwrap();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let t = prepare_transfer_bound(&store, 1).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    let command = json!({"operation":"payload","assignment":payload_assignment(&t,&claim)});
    for downgrade in [true, false] {
        let (mut child, mut channel) = effect_child(&guard, &guard, "--internal-delivery-worker");
        let opened = session_authorized_reply(
            &mut channel,
            1,
            json!({"operation":"open","job_id":1,"source_root":f.root.join("source"),"destination_root":f.root.join("destination"),"destination_binding":destination_binding()}),
            guard.source_authorization(),
        );
        assert!(opened["error"].is_null());
        if !downgrade {
            let mut changed = binding();
            changed.marker_id = "changed".into();
            std::fs::write(
                f.root.join("source/.file-mover/source-binding.json"),
                changed.encode(),
            )
            .unwrap();
        }
        let refused = session_authorized_reply(
            &mut channel,
            2,
            command.clone(),
            if downgrade {
                None
            } else {
                guard.source_authorization()
            },
        );
        assert!(refused["error"].is_string());
        assert!(refused["transfer"].is_null());
        // A blocked reply terminates the session. Never reuse that assignment.
        drop(channel);
        assert!(child.wait().unwrap().success());
    }
    assert_eq!(
        std::fs::metadata(f.root.join("destination/1/.staging/1.part"))
            .unwrap()
            .len(),
        0
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"source retained"
    );
}
fn transfer_from_wire(t: &Value) -> mover_core::Transfer {
    let object = |i: usize| {
        mover_core::ObjectIdentity::decode(t["transfer_objects"][i].as_str().unwrap()).unwrap()
    };
    mover_core::Transfer {
        job_id: t["job_id"].as_i64().unwrap(),
        file_index: t["file_index"].as_u64().unwrap() as usize,
        attempt: t["attempt"].as_i64().unwrap(),
        destination_root: t["destination_root"].as_str().unwrap().into(),
        relative_name: t["relative_name"].as_str().unwrap().into(),
        root: object(0),
        area: object(1),
        parent: object(2),
        staging_directory: object(3),
        stage: object(4),
        sha256: t["sha256"].as_str().map(str::to_owned),
        phase: mover_core::TransferPhase::decode(t["phase"].as_i64().unwrap()).unwrap(),
    }
}
#[test]
fn delivery_session_allocates_restarts_and_commits_manifest_between_parent_receipts() {
    let mut f = Fixture::new(300);
    f.write("data", b"abcdefgh");
    assert_eq!(f.post(&f.input("session", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let c = store.claim_intent(1, 0).unwrap().unwrap().0;
    let (mut child, mut channel) = effect_child(&source, &source, "--internal-delivery-worker");
    let opened = session_reply(
        &mut channel,
        1,
        json!({"operation":"open","job_id":1,"source_root":f.root.join("source"),"destination_root":f.root.join("destination"),"destination_binding":destination_binding()}),
    );
    assert!(opened["error"].is_null());
    assert!(
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).is_err()
    );
    let mut template = mover_core::Transfer {
        job_id: 1,
        file_index: 0,
        attempt: 1,
        destination_root: f.root.join("destination").to_str().unwrap().into(),
        relative_name: "data".into(),
        root: c.root.clone(),
        area: c.root.clone(),
        parent: c.root.clone(),
        staging_directory: c.root.clone(),
        stage: c.root.clone(),
        sha256: None,
        phase: mover_core::TransferPhase::Intent,
    };
    let r = session_reply(
        &mut channel,
        2,
        json!({"operation":"prepare","assignment":payload_assignment(&template,&c)}),
    );
    assert!(r["error"].is_null());
    template = transfer_from_wire(&r["transfer"]);
    assert!(store.transfer(1, 0).unwrap().is_none());
    store.save_transfer(&template).unwrap();
    std::fs::write(f.root.join("destination/1/.staging/1.part"), b"partial").unwrap();
    let r = session_reply(
        &mut channel,
        3,
        json!({"operation":"restart","assignment":payload_assignment(&template,&c)}),
    );
    assert!(r["error"].is_null());
    let t = transfer_from_wire(&r["transfer"]);
    assert_eq!(t.attempt, 2);
    assert_eq!(store.transfer(1, 0).unwrap(), Some(template));
    assert_eq!(
        std::fs::read(f.root.join("destination/1/.staging/1.part")).unwrap(),
        b"partial"
    );
    store.save_transfer(&t).unwrap();
    let mut t = t;
    let mut seq = 4;
    for expected in [
        mover_core::TransferPhase::Copied,
        mover_core::TransferPhase::Verified,
        mover_core::TransferPhase::Published,
    ] {
        if expected == mover_core::TransferPhase::Published {
            t = mover_fs::authorize_publication(&store, &t).unwrap();
        }
        let r = session_reply(
            &mut channel,
            seq,
            json!({"operation":"payload","assignment":payload_assignment(&t,&c)}),
        );
        seq += 1;
        assert!(r["error"].is_null());
        let next = transfer_from_wire(&r["transfer"]);
        assert_eq!(next.phase, expected);
        assert_eq!(store.transfer(1, 0).unwrap(), Some(t));
        store.save_transfer(&next).unwrap();
        t = next;
    }
    let r = session_reply(
        &mut channel,
        seq,
        json!({"operation":"custody","assignment":payload_assignment(&t,&c)}),
    );
    seq += 1;
    assert_eq!(transfer_from_wire(&r["transfer"]), t);
    let mut m = mover_fs::expected_manifest(&store, 1).unwrap();
    store.save_manifest(&m).unwrap();
    for expected in [1, 2, 3, 4, 4] {
        let body = json!({"operation":"manifest","assignment":payload_assignment(&t,&c),"manifest":{"job_id":m.job_id,"bytes":m.bytes,"sha256":m.sha256,"phase":m.phase,"object":m.object.as_ref().map(mover_core::ObjectIdentity::encode)}});
        let r = session_reply(&mut channel, seq, body);
        seq += 1;
        assert!(r["error"].is_null());
        assert_eq!(store.manifest(1).unwrap(), Some(m.clone()));
        assert_eq!(r["manifest"]["phase"], expected);
        m.phase = expected;
        m.object = Some(
            mover_core::ObjectIdentity::decode(r["manifest"]["object"].as_str().unwrap()).unwrap(),
        );
        store.save_manifest(&m).unwrap();
    }
    assert!(store.get(1).unwrap().unwrap().recording.is_committed());
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
    channel.shutdown(std::net::Shutdown::Write).unwrap();
    assert!(child.wait().unwrap().success());
    assert!(
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).is_ok()
    );
}
#[test]
fn delivery_session_keeps_both_locks_after_parent_closes_and_rejects_stale_sequence_or_version() {
    for version in [2, 1] {
        let mut f = Fixture::new(300);
        f.stop();
        provision_destination(&f);
        let source =
            mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
        let (mut child, mut channel) = effect_child(&source, &source, "--internal-delivery-worker");
        let command = json!({"operation":"open","job_id":1,"source_root":f.root.join("source"),"destination_root":f.root.join("destination")});
        assert!(session_reply(&mut channel, 1, command.clone())["error"].is_null());
        drop(source);
        for path in ["source", "destination"] {
            assert!(
                mover_fs::LocalClaimLock::acquire(f.root.join(path).to_str().unwrap()).is_err()
            );
        }
        let bytes = serde_json::to_vec(
            &json!({"version":version,"sequence":if version == 2 {1} else {2},"command":command}),
        )
        .unwrap();
        channel
            .write_all(&(bytes.len() as u32).to_be_bytes())
            .unwrap();
        channel.write_all(&bytes).unwrap();
        assert!(!child.wait().unwrap().success());
        drop(channel);
        for path in ["source", "destination"] {
            assert!(mover_fs::LocalClaimLock::acquire(f.root.join(path).to_str().unwrap()).is_ok());
        }
        assert!(!f.root.join("destination/1").exists());
    }
}

#[test]
fn delivery_session_refuses_oversized_frame_before_any_allocation() {
    let mut f = Fixture::new(300);
    f.stop();
    provision_destination(&f);
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let (mut child, mut channel) = effect_child(&source, &source, "--internal-delivery-worker");
    channel.write_all(&393217_u32.to_be_bytes()).unwrap();
    assert!(!child.wait().unwrap().success());
    assert!(!f.root.join("destination/1").exists());
}
fn payload_child(
    source: &mover_fs::LocalClaimLock,
    destination: &mover_fs::LocalClaimLock,
) -> (Child, std::os::unix::net::UnixStream) {
    effect_child(source, destination, "--internal-payload-worker")
}
fn effect_child(
    source: &mover_fs::LocalClaimLock,
    destination: &mover_fs::LocalClaimLock,
    mode: &str,
) -> (Child, std::os::unix::net::UnixStream) {
    let (mut channel, worker) = std::os::unix::net::UnixStream::pair().unwrap();
    channel
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    let database = std::path::Path::new(source.source_path())
        .parent()
        .unwrap()
        .join("state/jobs.sqlite");
    let instance = mover_fs::InstanceGuard::for_database(database.to_str().unwrap()).unwrap();
    instance.prepare_workers().unwrap();
    let child = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg(mode)
        .stdin(Stdio::from(source.inherit().unwrap()))
        .stdout(Stdio::from(destination.inherit().unwrap()))
        .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
        .spawn()
        .unwrap();
    instance.send(&mut channel).unwrap();
    (child, channel)
}
fn child_reply(
    source: &mover_fs::LocalClaimLock,
    destination: &mover_fs::LocalClaimLock,
    mode: &str,
    body: &Value,
) -> Value {
    let body = if mode == "--internal-claim-worker" {
        json!({"assignment":body,"source_authorization":source.source_authorization()})
    } else {
        body.clone()
    };
    let (mut child, mut channel) = effect_child(source, destination, mode);
    channel
        .write_all(&serde_json::to_vec(&body).unwrap())
        .unwrap();
    channel.shutdown(std::net::Shutdown::Write).unwrap();
    assert!(child.wait().unwrap().success());
    let mut bytes = Vec::new();
    channel.read_to_end(&mut bytes).unwrap();
    serde_json::from_slice(&bytes).unwrap()
}
fn claim_from_wire(c: &Value) -> mover_core::ClaimIntent {
    let object =
        |i: usize| mover_core::ObjectIdentity::decode(c["objects"][i].as_str().unwrap()).unwrap();
    mover_core::ClaimIntent {
        job_id: c["job_id"].as_i64().unwrap(),
        file_index: c["file_index"].as_u64().unwrap() as usize,
        root_path: c["root_path"].as_str().unwrap().into(),
        source_name: c["source_name"].as_str().unwrap().into(),
        private_name: c["private_name"].as_str().unwrap().into(),
        root: object(0),
        parent: object(1),
        area: object(2),
        source: object(3),
    }
}
#[test]
fn claim_children_preserve_intent_receipt_order_and_reconcile_lost_reply() {
    let mut f = Fixture::new(300);
    let input = f.input("child-claim", json!([{"name":"data"}]));
    assert_eq!(f.post(&input).0, 503);
    f.stop();
    f.write("data", b"claim data");
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let guard = mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let observed = child_reply(
        &guard,
        &guard,
        "--internal-claim-worker",
        &json!({"operation":"observe","version":1,"job_id":1,"file_index":0,"root_path":f.root.join("source"),"source_name":"current/data","expected_size":null}),
    );
    assert!(observed["error"].is_null());
    assert_eq!(
        observed["claim"]["objects"][3]
            .as_str()
            .map(mover_core::ObjectIdentity::decode)
            .unwrap()
            .unwrap()
            .size,
        10
    );
    assert!(store.claim_intent(1, 0).unwrap().is_none());
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    store.claim_capacity(10).unwrap();
    let allocated = child_reply(
        &guard,
        &guard,
        "--internal-claim-worker",
        &json!({"operation":"allocate","version":1,"claim":observed["claim"]}),
    );
    let intent = claim_from_wire(&allocated["claim"]);
    assert!(store.claim_intent(1, 0).unwrap().is_none());
    assert!(f.root.join("source/current/data").exists());
    store.begin_claim(&intent).unwrap();
    let body = json!({"operation":"apply","version":1,"claim":allocated["claim"]});
    let first = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    assert_eq!(claim_from_wire(&first["claim"]), intent);
    assert_eq!(
        store.claim_intent(1, 0).unwrap(),
        Some((intent.clone(), false))
    );
    assert!(!f.root.join("source/current/data").exists());
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"claim data"
    );
    // Discard the first result without an applied database receipt, then reconcile.
    let replay = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    assert_eq!(claim_from_wire(&replay["claim"]), intent);
    store.finish_claim(&intent).unwrap();
    drop(guard);
    drop(store);
    f.write("data", b"producer reuse");
    f.start();
    assert_eq!(f.post(&input).0, 202);
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"producer reuse"
    );
}
#[test]
fn claim_child_reports_missing_and_refuses_changed_observation_before_allocation() {
    let mut f = Fixture::new(300);
    f.stop();
    let guard = mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let body = json!({"operation":"observe","version":1,"job_id":1,"file_index":0,"root_path":f.root.join("source"),"source_name":"current/data","expected_size":null});
    let missing = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    assert_eq!(missing["error"], "missing_source");
    f.write("data", b"old");
    let observed = child_reply(&guard, &guard, "--internal-claim-worker", &body);
    f.write("data", b"changed size");
    let refused = child_reply(
        &guard,
        &guard,
        "--internal-claim-worker",
        &json!({"operation":"allocate","version":1,"claim":observed["claim"]}),
    );
    assert_eq!(refused["error"], "expected_size_mismatch");
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"changed size"
    );
}
#[test]
fn publication_child_reconciles_file_and_manifest_effects_without_database_receipts() {
    let mut f = Fixture::new(300);
    f.write("data", b"publication");
    assert_eq!(
        f.post(&f.input("publish-child", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).unwrap();
    let t = prepare_transfer_bound(&store, 1).unwrap();
    let t = mover_fs::copy_stage(&store, &t).unwrap();
    let t = mover_fs::verify_stage(&store, &t).unwrap();
    let mut t = mover_fs::authorize_publication(&store, &t).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    for _ in 0..2 {
        let r = child_reply(
            &source,
            &destination,
            "--internal-payload-worker",
            &payload_assignment(&t, &claim),
        );
        assert_eq!(r["phase"], 4);
        assert_eq!(r["stage"], t.stage.encode());
        assert_eq!(store.transfer(1, 0).unwrap(), Some(t.clone()));
        assert_eq!(
            std::fs::read(f.root.join("destination/1/data")).unwrap(),
            b"publication"
        );
        assert!(!f.root.join("destination/1/.staging/1.part").exists());
    }
    t.phase = mover_core::TransferPhase::Published;
    store.save_transfer(&t).unwrap();
    let interrupted = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        mover_fs::commit_manifest_with_checkpoints(&store, 1, |point| {
            if point == "authorized" {
                panic!("before manifest publication");
            }
        })
        .unwrap();
    }));
    assert!(interrupted.is_err());
    let m = store.manifest(1).unwrap().unwrap();
    assert_eq!(m.phase, 3);
    let mut body = payload_assignment(&t, &claim);
    body["manifest"] = json!({"job_id":m.job_id,"bytes":m.bytes,"sha256":m.sha256,"phase":m.phase,"object":m.object.as_ref().unwrap().encode()});
    for _ in 0..2 {
        let r = child_reply(&source, &destination, "--internal-payload-worker", &body);
        assert_eq!(r["phase"], 4);
        assert_eq!(r["sha256"], m.sha256);
        assert_eq!(store.manifest(1).unwrap(), Some(m.clone()));
        assert!(!store.get(1).unwrap().unwrap().recording.is_committed());
        assert_eq!(
            std::fs::read_to_string(f.root.join("destination/1/COMMITTED.json")).unwrap(),
            m.bytes
        );
    }
    let mut committed = m;
    committed.phase = 4;
    store.save_manifest(&committed).unwrap();
    assert!(store.get(1).unwrap().unwrap().recording.is_committed());
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
fn payload_assignment(t: &mover_core::Transfer, c: &mover_core::ClaimIntent) -> Value {
    json!({"version":1,"job_id":t.job_id,"file_index":t.file_index,"attempt":t.attempt,"phase":t.phase as i64,
        "destination_root":t.destination_root,"relative_name":t.relative_name,
        "transfer_objects":[t.root.encode(),t.area.encode(),t.parent.encode(),t.staging_directory.encode(),t.stage.encode()],
        "sha256":t.sha256,"source_root":c.root_path,"source_name":c.source_name,"private_name":c.private_name,
        "claim_objects":[c.root.encode(),c.parent.encode(),c.area.encode(),c.source.encode()]})
}
#[test]
fn payload_children_copy_verify_without_database_access_or_publication() {
    let mut f = Fixture::new(300);
    f.write("data", b"child payload");
    assert_eq!(f.post(&f.input("payload", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).unwrap();
    let mut transfer = prepare_transfer_bound(&store, 1).unwrap();
    let (claim, done) = store.claim_intent(1, 0).unwrap().unwrap();
    assert!(done);
    for phase in [
        mover_core::TransferPhase::Copied,
        mover_core::TransferPhase::Verified,
    ] {
        let before = transfer.clone();
        let (mut child, mut channel) = payload_child(&source, &destination);
        channel
            .write_all(&serde_json::to_vec(&payload_assignment(&transfer, &claim)).unwrap())
            .unwrap();
        channel.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(child.wait().unwrap().success());
        let mut bytes = Vec::new();
        channel.read_to_end(&mut bytes).unwrap();
        let receipt: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(receipt["phase"], phase as i64);
        assert_eq!(receipt["job_id"], 1);
        assert_eq!(receipt["attempt"], before.attempt);
        assert_eq!(store.transfer(1, 0).unwrap(), Some(before));
        transfer.phase = phase;
        transfer.stage =
            mover_core::ObjectIdentity::decode(receipt["stage"].as_str().unwrap()).unwrap();
        transfer.sha256 = Some(receipt["sha256"].as_str().unwrap().to_owned());
        store.save_transfer(&transfer).unwrap();
        assert!(!f.root.join("destination/1/data").exists());
        assert!(!f.root.join("destination/1/COMMITTED.json").exists());
    }
    assert_eq!(
        std::fs::read(f.root.join("destination/1/.staging/1.part")).unwrap(),
        b"child payload"
    );
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
#[test]
fn live_payload_child_retains_both_locks_after_parent_descriptors_close() {
    let mut f = Fixture::new(300);
    f.stop();
    provision_destination(&f);
    let source_path = f.root.join("source");
    let destination_path = f.root.join("destination");
    let source = mover_fs::LocalClaimLock::acquire(source_path.to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(destination_path.to_str().unwrap()).unwrap();
    let (mut child, channel) = payload_child(&source, &destination);
    drop(source);
    drop(destination);
    assert!(mover_fs::LocalClaimLock::acquire(source_path.to_str().unwrap()).is_err());
    assert!(mover_fs::LocalClaimLock::acquire(destination_path.to_str().unwrap()).is_err());
    child.kill().unwrap();
    assert!(!child.wait().unwrap().success());
    drop(channel);
    assert!(mover_fs::LocalClaimLock::acquire(source_path.to_str().unwrap()).is_ok());
    assert!(mover_fs::LocalClaimLock::acquire(destination_path.to_str().unwrap()).is_ok());
}
#[test]
fn malformed_payload_assignments_preserve_stage_and_source() {
    let mut f = Fixture::new(300);
    f.write("data", b"protected");
    assert_eq!(
        f.post(&f.input("invalid-payload", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let source =
        mover_fs::LocalClaimLock::acquire(f.root.join("source").to_str().unwrap()).unwrap();
    let destination =
        mover_fs::LocalClaimLock::acquire(f.root.join("destination").to_str().unwrap()).unwrap();
    let transfer = prepare_transfer_bound(&store, 1).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    for body in [
        b"{}".to_vec(),
        vec![b'x'; 32769],
        {
            let mut input = payload_assignment(&transfer, &claim);
            input["phase"] = json!(3);
            serde_json::to_vec(&input).unwrap()
        },
        {
            let mut input = payload_assignment(&transfer, &claim);
            input["private_name"] = json!("../foreign");
            serde_json::to_vec(&input).unwrap()
        },
    ] {
        let (mut child, mut channel) = payload_child(&source, &destination);
        channel.write_all(&body).unwrap();
        channel.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(!child.wait().unwrap().success());
        assert_eq!(store.transfer(1, 0).unwrap(), Some(transfer.clone()));
        assert_eq!(
            std::fs::metadata(f.root.join("destination/1/.staging/1.part"))
                .unwrap()
                .len(),
            0
        );
        assert_eq!(
            std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
            b"protected"
        );
    }
}
struct Fixture {
    root: PathBuf,
    address: SocketAddr,
    child: Option<Child>,
}
impl Fixture {
    fn new(window: u32) -> Self {
        let mut f = Self::uninitialized(window);
        let initialized = initialize_source(&f.root.join("config.json"));
        assert!(initialized.status.success(), "{initialized:?}");
        f.start();
        f
    }
    fn uninitialized(window: u32) -> Self {
        let root = loop {
            let p = std::env::temp_dir().join(format!(
                "file-mover-api-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match std::fs::create_dir(&p) {
                Ok(()) => break p,
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => panic!("{e}"),
            }
        };
        for path in [
            root.clone(),
            root.join("source"),
            root.join("source/.file-mover"),
            root.join("source/current"),
            root.join("source/current/sub"),
            root.join("state"),
        ] {
            if path != root {
                std::fs::create_dir(&path).unwrap();
            }
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).unwrap();
        }
        let address = TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap();
        provision_lock(&root.join("source"));
        provision_binding(&root.join("source"));
        std::fs::write(root.join("config.json"),serde_json::to_vec(&json!({"bind":address.to_string(),"generator_id":"recorder","source_root":root.join("source"),"source_binding":binding(),"destination_binding":destination_binding(),"destination_root":root.join("destination"),"state_database":root.join("state/jobs.sqlite"),"missing_file_retry_window_seconds":window})).unwrap()).unwrap();
        Self {
            root,
            address,
            child: None,
        }
    }
    fn start(&mut self) {
        self.start_with_payload_fault(None);
    }
    fn start_with_payload_fault(&mut self, fault: Option<&str>) {
        self.start_with_faults(fault, None);
    }
    fn start_with_faults(&mut self, fault: Option<&str>, effect_fault: Option<&str>) {
        let mut command = Command::new(
            std::env::var("FILE_MOVER_TEST_EXECUTABLE")
                .expect("SLES gate provides audited service binary"),
        );
        if let Some(fault) = fault {
            command.env("FILE_MOVER_QUALIFICATION_PAYLOAD_FAULT", fault);
        }
        if let Some(fault) = effect_fault {
            command.env("FILE_MOVER_QUALIFICATION_EFFECT_FAULT", fault);
        }
        self.start_command(command);
    }
    fn start_command(&mut self, mut command: Command) {
        // Direct internal-worker tests temporarily use this long-lived test
        // process as their coordinator. Retire only that synthetic fixture epoch
        // after reacquisition proves every other group member has exited. Real
        // service epochs (different PIDs) are never cleared by the harness.
        let epoch = self.root.join("state/workers.json");
        if let Ok(bytes) = std::fs::read(&epoch)
            && let Ok(value) = serde_json::from_slice::<Value>(&bytes)
            && value["group"].as_u64() == Some(u64::from(std::process::id()))
        {
            let _instance = mover_fs::InstanceGuard::for_database(
                self.root.join("state/jobs.sqlite").to_str().unwrap(),
            )
            .expect("direct test workers must exit before retiring their synthetic epoch");
            std::fs::remove_file(&epoch).unwrap();
            std::fs::File::open(self.root.join("state"))
                .unwrap()
                .sync_all()
                .unwrap();
        }
        self.child = Some(
            command
                .arg(self.root.join("config.json"))
                .stdout(Stdio::null())
                .stderr(Stdio::piped())
                .spawn()
                .unwrap(),
        );
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            if let Ok(mut stream) =
                TcpStream::connect_timeout(&self.address, Duration::from_millis(100))
            {
                stream
                    .set_read_timeout(Some(Duration::from_secs(1)))
                    .unwrap();
                stream
                    .write_all(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n")
                    .unwrap();
                let mut response = String::new();
                if stream.read_to_string(&mut response).is_ok()
                    && response.starts_with("HTTP/1.1 200 ")
                {
                    return;
                }
            }
            if let Some(status) = self.child.as_mut().unwrap().try_wait().unwrap() {
                let mut stderr = String::new();
                self.child
                    .as_mut()
                    .unwrap()
                    .stderr
                    .take()
                    .unwrap()
                    .read_to_string(&mut stderr)
                    .unwrap();
                panic!("startup {status}: {stderr}");
            }
            assert!(Instant::now() < deadline, "startup timeout");
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn stop(&mut self) {
        let mut child = self.child.take().unwrap();
        assert!(
            Command::new("/bin/kill")
                .args([
                    if NEXT.load(Ordering::Relaxed).is_multiple_of(2) {
                        "-INT"
                    } else {
                        "-TERM"
                    },
                    &child.id().to_string()
                ])
                .status()
                .unwrap()
                .success()
        );
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if let Some(status) = child.try_wait().unwrap() {
                assert!(status.success());
                break;
            }
            if Instant::now() >= deadline {
                child.kill().unwrap();
                child.wait().unwrap();
                panic!("graceful shutdown timeout");
            }
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn input(&self, id: &str, files: Value) -> Value {
        json!({"generator_id":"recorder","submission_id":id,"source_path":self.root.join("source/current"),"files":files})
    }
    fn write(&self, name: &str, bytes: &[u8]) {
        std::fs::write(self.root.join("source/current").join(name), bytes).unwrap();
    }
    fn raw(&self, bytes: &[u8]) -> (u16, Value) {
        exchange(self.address, bytes)
    }
    fn post(&self, body: &Value) -> (u16, Value) {
        self.raw(&post_bytes(body))
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
        std::fs::remove_dir_all(&self.root).unwrap();
    }
}
fn post_bytes(body: &Value) -> Vec<u8> {
    post_text(&serde_json::to_string(body).unwrap())
}
fn post_text(body: &str) -> Vec<u8> {
    format!("POST /api/v2/jobs HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{}",body.len(),body).into_bytes()
}
fn exchange(address: SocketAddr, bytes: &[u8]) -> (u16, Value) {
    let mut s = TcpStream::connect(address).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(15))).unwrap();
    s.write_all(bytes).unwrap();
    let mut response = String::new();
    s.read_to_string(&mut response).unwrap();
    let (head, body) = response.split_once("\r\n\r\n").unwrap();
    assert!(head.contains("Connection: close"));
    let declared: usize = head
        .lines()
        .find_map(|line| line.strip_prefix("Content-Length: "))
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(declared, body.len());
    (
        head.split_whitespace().nth(1).unwrap().parse().unwrap(),
        serde_json::from_str(body).unwrap(),
    )
}
#[test]
fn actual_executable_handoff_restart_replay_and_reused_paths() {
    let mut f = Fixture::new(300);
    f.write("sub/data", b"payload");
    f.write("empty", b"");
    let body = f.input(
        "first",
        json!([{"name":"sub/data"},{"name":"empty","size_bytes":0}]),
    );
    let (status, response) = f.post(&body);
    assert_eq!(status, 202);
    assert_eq!(response["state"], "Claimed");
    assert_eq!(response["source_paths_released"], true);
    assert!(f.root.join("source/current/sub").is_dir());
    assert!(!f.root.join("source/current/sub/data").exists());
    f.write("sub/data", b"new");
    f.stop();
    f.start();
    let (status, replay) = f.post(&body);
    assert_eq!(status, 202);
    assert_eq!(replay["job_id"], response["job_id"]);
    assert_eq!(
        std::fs::read(f.root.join("source/current/sub/data")).unwrap(),
        b"new"
    );
    let mut conflict = body.clone();
    conflict["files"] = json!([{"name":"sub/data"}]);
    assert_eq!(f.post(&conflict).0, 409);
    assert_eq!(
        f.post(&f.input("next", json!([{"name":"sub/data"}]))).0,
        202
    );
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 2);
}
#[test]
fn malformed_json_scope_and_http_framing_never_claim() {
    let mut f = Fixture::new(300);
    f.write("data", b"unchanged");
    let body = f.input("valid", json!([{"name":"data"}]));
    for change in ["destination_root", "unexpected"] {
        let mut b = body.clone();
        b[change] = json!("forbidden");
        assert_eq!(f.post(&b).0, 400);
    }
    let mut b = body.clone();
    b["generator_id"] = json!("other");
    assert_eq!(f.post(&b).0, 403);
    b = body.clone();
    b["source_path"] = json!(format!("{}-outside", f.root.join("source").display()));
    assert_eq!(f.post(&b).0, 403);
    for file in [
        json!({"name":"../data"}),
        json!({"name":"data","size_bytes":null}),
        json!({"name":"data","size_bytes":1.0}),
        json!({"name":"data","size_bytes":-1}),
    ] {
        let mut b = body.clone();
        b["files"] = json!([file]);
        assert_eq!(f.post(&b).0, 400);
    }
    assert_eq!(
        f.raw(&post_text(
            "{\"generator_id\":\"recorder\",\"generator_id\":\"recorder\"}"
        ))
        .0,
        400
    );
    for (request, status) in [
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\ncontent-length: 2\r\n\r\n{}",
            400,
        ),
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n",
            400,
        ),
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Length: 65537\r\n\r\n",
            413,
        ),
        (
            "POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\n{}",
            415,
        ),
        ("GET /api/v2/jobs HTTP/1.1\r\nHost: h\r\n\r\n", 405),
        ("GET /other HTTP/1.1\r\nHost: h\r\n\r\n", 404),
    ] {
        assert_eq!(f.raw(request.as_bytes()).0, status);
    }
    assert!(f.root.join("source/current/data").exists());
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 0);
}
#[test]
fn partial_claim_missing_retry_and_persisted_expiry() {
    let mut f = Fixture::new(300);
    f.write("first", b"retained");
    let input = f.input("partial", json!([{"name":"first"},{"name":"missing"}]));
    let (status, pending) = f.post(&input);
    assert_eq!(status, 503);
    assert_eq!(pending["retryable"], true);
    assert_eq!(pending["source_paths_released"], false);
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
    f.stop();
    f.start();
    f.write("missing", b"arrived");
    let (status, ready) = f.post(&input);
    assert_eq!(status, 202);
    assert_eq!(ready["job_id"], pending["job_id"]);
    f.stop();
    let mut expired = Fixture::new(0);
    let body = expired.input("late", json!([{"name":"missing"}]));
    let (status, blocked) = expired.post(&body);
    assert_eq!(status, 409);
    assert_eq!(blocked["retryable"], false);
    expired.stop();
    expired.start();
    expired.write("missing", b"late file");
    assert_eq!(expired.post(&body).0, 409);
    assert!(expired.root.join("source/current/missing").exists());
    expired.stop();
}
#[test]
fn slow_client_does_not_block_health_and_concurrent_replays_are_bounded() {
    let mut f = Fixture::new(300);
    let _slow = TcpStream::connect(f.address).unwrap();
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
    f.write("data", b"once");
    let bytes = post_bytes(&f.input("concurrent", json!([{"name":"data"}])));
    let threads: Vec<_> = (0..4)
        .map(|_| {
            let bytes = bytes.clone();
            let address = f.address;
            std::thread::spawn(move || exchange(address, &bytes))
        })
        .collect();
    let replies: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert!(replies.iter().any(|r| r.0 == 202));
    assert!(replies.iter().all(|r| matches!(r.0, 202 | 503)));
    assert_eq!(f.raw(&bytes).0, 202);
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 1);
}
#[test]
fn unsafe_startup_configuration_is_rejected() {
    let c = file_mover::Config {
        bind: "0.0.0.0:8080".parse().unwrap(),
        generator_id: "g".into(),
        source_root: "/source".into(),
        source_binding: binding(),
        destination_binding: destination_binding(),
        destination_root: "/dest".into(),
        state_database: "/state/db".into(),
        missing_file_retry_window_seconds: 300,
        max_retained_jobs: 64,
        max_retained_bytes: 1024 * 1024 * 1024 * 1024,
        source_space_admission: Default::default(),
        shutdown_wait_seconds: 60,
    };
    assert!(c.validate().is_err());
    let mut c = c;
    c.bind = "127.0.0.1:8080".parse().unwrap();
    assert!(c.validate().is_ok());
    c.state_database = "/source/db".into();
    assert!(c.validate().is_err());
}

#[test]
fn lost_response_retry_finds_one_durable_job() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained");
    let body = f.input("lost-response", json!([{"name":"data"}]));
    let mut stream = TcpStream::connect(f.address).unwrap();
    stream.write_all(&post_bytes(&body)).unwrap();
    drop(stream);
    let deadline = Instant::now() + Duration::from_secs(5);
    while !f.root.join("source/.file-mover/1-0/data").exists() {
        assert!(
            Instant::now() < deadline,
            "disconnected request must finish claiming"
        );
        std::thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(store.job_count().unwrap(), 1);
}

#[test]
fn actual_transfer_command_publishes_but_retains_claimed_source() {
    let mut f = Fixture::new(300);
    f.write("sub/data", b"abc");
    let (status, response) = f.post(&f.input("copy", json!([{"name":"sub/data"}])));
    assert_eq!(status, 202);
    f.stop();
    f.write("sub/data", b"new recording");
    for p in [
        f.root.join("destination"),
        f.root.join("destination/.file-mover"),
    ] {
        std::fs::create_dir(&p).unwrap();
        std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700)).unwrap();
    }
    provision_lock(&f.root.join("destination"));
    provision_destination_marker(&f.root.join("destination"));
    let output = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--transfer-one")
        .arg(f.root.join("config.json"))
        .arg(response["job_id"].as_str().unwrap())
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
    let result: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["state"], "Published");
    assert_eq!(result["source_retained"], true);
    assert_eq!(result["committed"], false);
    assert_eq!(
        result["sha256"],
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    assert_eq!(
        std::fs::read(f.root.join("destination/1/sub/data")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/sub/data")).unwrap(),
        b"new recording"
    );
}

fn provision_destination(f: &Fixture) {
    for p in [
        f.root.join("destination"),
        f.root.join("destination/.file-mover"),
    ] {
        std::fs::create_dir(&p).unwrap();
        std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700)).unwrap();
    }
    provision_lock(&f.root.join("destination"));
    provision_destination_marker(&f.root.join("destination"));
}
fn status(f: &Fixture, id: &str) -> (u16, Value) {
    f.raw(format!("GET /api/v2/jobs/{id} HTTP/1.1\r\nHost: h\r\n\r\n").as_bytes())
}
fn retention(f: &Fixture, id: Option<&str>) -> (u16, Value) {
    let path = id.map_or_else(
        || "/api/v2/retention".to_owned(),
        |id| format!("/api/v2/jobs/{id}/retention"),
    );
    f.raw(format!("GET {path} HTTP/1.1\r\nHost: h\r\n\r\n").as_bytes())
}
#[test]
fn retention_api_reports_admission_headroom_and_committed_retained_sources() {
    let mut f = Fixture::new(300);
    let (code, r) = retention(&f, None);
    assert_eq!(code, 200);
    assert_eq!(r["details"]["retained_jobs"], 0);
    assert_eq!(r["details"]["global_headroom"]["new_job_slots"], 64);
    let body = f.input("accounting", json!([{"name":"data"},{"name":"late"}]));
    f.write("data", b"abc");
    assert_eq!(f.post(&body).0, 503);
    let (_, r) = retention(&f, Some("1"));
    assert_eq!(r["details"]["source_reserved_bytes"], "3");
    assert_eq!(r["details"]["unmeasured_files"], 1);
    assert_eq!(r["details"]["confirmed_claims"], 1);
    assert!(r["details"]["global_headroom"].is_null());
    f.write("late", b"xy");
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    provision_destination(&f);
    f.start();
    wait_manifest(&f, "1");
    f.stop();
    f.start();
    let (_, r) = retention(&f, None);
    assert_eq!(r["details"]["source_reserved_bytes"], "5");
    assert_eq!(r["details"]["destination_reserved_bytes"], "5");
    assert_eq!(r["details"]["committed_jobs"], 1);
    assert_eq!(
        r["details"]["destination_attempts_by_phase"]["Published"],
        2
    );
    assert_eq!(
        r["details"]["global_headroom"]["source_bytes"],
        (1099511627776_u64 - 5).to_string()
    );
    assert_eq!(r["details"]["filesystem_inspected"], false);
    assert_eq!(r["details"]["automatic_reclamation_enabled"], false);
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
    assert_eq!(retention(&f, Some("999")).0, 404);
    assert_eq!(retention(&f, Some("01")).0, 400);
    assert_eq!(
        f.raw(b"POST /api/v2/retention HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
    assert_eq!(
        f.raw(b"GET /api/v2/retention HTTP/1.1\r\nHost: h\r\nContent-Length: 1\r\n\r\nx")
            .0,
        400
    );
    assert_eq!(
        f.raw(b"POST /api/v2/jobs/1/retention HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
}
#[test]
fn retention_api_charges_interrupted_attempts_and_does_not_claim_to_find_orphans() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    assert_eq!(
        f.post(&f.input("attempt-accounting", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    {
        let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let t = prepare_transfer_bound(&s, 1).unwrap();
        mover_fs::restart_transfer(&s, &t).unwrap();
        // Allocation without a receipt cannot be attributed by database accounting.
        std::fs::write(
            f.root.join("destination/1/.staging/unreceipted.part"),
            b"unknown bytes",
        )
        .unwrap();
        for time in [100, 105, 110] {
            s.delivery_failed(1, time).unwrap();
        }
    }
    f.start();
    let (_, r) = retention(&f, Some("1"));
    assert_eq!(r["details"]["destination_reserved_bytes"], "6");
    assert_eq!(r["details"]["destination_attempts_by_phase"]["Intent"], 2);
    assert_eq!(r["details"]["unreceipted_allocations_accounted"], false);
    assert_eq!(
        std::fs::read(f.root.join("destination/1/.staging/unreceipted.part")).unwrap(),
        b"unknown bytes"
    );
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
}
fn reset_body(epoch: u32, file: &str, seconds: u32) -> Value {
    json!({"command_id":format!("missing-{epoch}"),"expected_missing_review_epoch":epoch,"file_id":file,"retry_window_seconds":seconds,"reason":"Confirmed recorder has not reused the pending source paths"})
}
fn reset_bytes(body: &str) -> Vec<u8> {
    format!("POST /api/v2/jobs/1/reset-missing HTTP/1.1\r\nHost: h\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",body.len()).into_bytes()
}
fn reset(f: &Fixture, body: &Value) -> (u16, Value) {
    f.raw(&reset_bytes(&body.to_string()))
}
#[test]
fn missing_reset_lost_response_survives_restart_and_partial_claims_complete() {
    let mut f = Fixture::new(0);
    f.write("data", b"abc");
    let submission = f.input("missing-reset", json!([{"name":"data"},{"name":"late"}]));
    assert_eq!(f.post(&submission).0, 409);
    assert_eq!(status(&f, "1").1["details"]["files"][0]["phase"], "Claimed");
    let body = reset_body(0, "1", 300);
    let mut stream = TcpStream::connect(f.address).unwrap();
    stream.write_all(&reset_bytes(&body.to_string())).unwrap();
    drop(stream);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if status(&f, "1").1["details"]["missing_review_epoch"] == 1 {
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    let (_, s) = status(&f, "1");
    let new_deadline = s["details"]["missing"][0]["deadline"].clone();
    assert_eq!(s["source_paths_released"], false);
    assert_eq!(s["details"]["latest_missing_reset"]["file_id"], "1");
    f.stop();
    f.start();
    let (code, r) = reset(&f, &body);
    assert_eq!(code, 200);
    assert_eq!(r["details"]["replay"], true);
    assert_eq!(r["source_paths_released"], false);
    assert_eq!(r["details"]["new_deadline"], new_deadline);
    assert_eq!(f.post(&submission).0, 503);
    assert_eq!(
        status(&f, "1").1["details"]["missing"][0]["deadline"],
        new_deadline
    );
    assert!(!f.root.join("source/current/data").exists());
    f.write("late", b"later");
    assert_eq!(f.post(&submission).0, 202);
    f.write("data", b"producer reuse");
    f.stop();
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert_eq!(
        s.get(1).unwrap().unwrap().recording.handoff(),
        mover_core::Handoff::Ready202
    );
    assert_eq!(s.status(1).unwrap().unwrap().missing_review_epoch, 1);
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-1/data")).unwrap(),
        b"later"
    );
}
#[test]
fn missing_reset_expiry_requires_new_epoch_and_rejects_bad_requests() {
    let mut f = Fixture::new(0);
    let submission = f.input("expiry", json!([{"name":"absent"}]));
    assert_eq!(f.post(&submission).0, 409);
    for file in ["01", "-1", "+0", "4294967296"] {
        assert_eq!(reset(&f, &reset_body(0, file, 10)).0, 400);
    }
    for seconds in [0, 86401] {
        assert_eq!(reset(&f, &reset_body(0, "0", seconds)).0, 400);
    }
    for body in [
        "{}",
        r#"{"command_id":"x","command_id":"y","file_id":"0","expected_missing_review_epoch":0,"retry_window_seconds":10,"reason":"fix"}"#,
        r#"{"command_id":"x","file_id":"0","expected_missing_review_epoch":0,"retry_window_seconds":10,"reason":"fix","extra":true}"#,
    ] {
        assert_eq!(f.raw(&reset_bytes(body)).0, 400);
    }
    assert_eq!(
        f.raw(b"GET /api/v2/jobs/1/reset-missing HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
    let body = reset_body(0, "0", 1);
    let (code, r) = reset(&f, &body);
    assert_eq!(code, 200);
    let deadline = r["details"]["new_deadline"].clone();
    let limit = Instant::now() + Duration::from_secs(4);
    loop {
        if status(&f, "1").1["details"]["condition"] == "ReviewRequired" {
            break;
        }
        assert!(Instant::now() < limit);
        std::thread::sleep(Duration::from_millis(20));
    }
    // Expiry visibility need not have persisted blocked yet; reset/replay handles both.
    assert_eq!(reset(&f, &body).1["details"]["new_deadline"], deadline);
    assert_eq!(f.post(&submission).0, 409);
    let mut stale = body.clone();
    stale["command_id"] = json!("stale-new-command");
    assert_eq!(reset(&f, &stale).1["error"], "review_conflict");
    let mut conflict = body.clone();
    conflict["retry_window_seconds"] = json!(10);
    assert_eq!(reset(&f, &conflict).1["error"], "command_conflict");
    assert_eq!(reset(&f, &reset_body(1, "0", 300)).0, 200);
    f.stop();
    f.start();
    assert_eq!(f.post(&submission).0, 503);
    assert_eq!(status(&f, "1").1["details"]["missing_review_epoch"], 2);
}
#[test]
fn missing_reset_rejects_unexpired_claimed_and_committed_files() {
    let mut f = Fixture::new(300);
    let submission = f.input("unexpired", json!([{"name":"data"}]));
    assert_eq!(f.post(&submission).0, 503);
    let (_, before) = status(&f, "1");
    assert_eq!(
        reset(&f, &reset_body(0, "0", 300)).1["error"],
        "review_conflict"
    );
    assert_eq!(status(&f, "1").1, before);
    f.write("data", b"abc");
    assert_eq!(f.post(&submission).0, 202);
    assert_eq!(reset(&f, &reset_body(0, "0", 300)).0, 409);
    f.stop();
    provision_destination(&f);
    f.start();
    wait_manifest(&f, "1");
    f.stop();
    f.start();
    assert_eq!(reset(&f, &reset_body(0, "0", 300)).0, 409);
    assert_eq!(status(&f, "1").1["details"]["missing_review_epoch"], 0);
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
fn resume_body(epoch: u32) -> Value {
    json!({"command_id":format!("resume-{epoch}"),"expected_review_epoch":epoch,"reason":"Inspected protected staging and destination"})
}
fn resume_bytes(id: &str, body: &str) -> Vec<u8> {
    format!("POST /api/v2/jobs/{id}/resume HTTP/1.1\r\nHost: h\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",body.len()).into_bytes()
}
fn resume(f: &Fixture, id: &str, body: &Value) -> (u16, Value) {
    f.raw(&resume_bytes(id, &body.to_string()))
}
fn seed_review(f: &Fixture) {
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    for time in [100, 105, 110] {
        s.delivery_failed(1, time).unwrap();
    }
}
#[test]
fn operator_resume_keeps_collision_safe_and_reconciles_same_verified_attempt() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    assert_eq!(f.post(&f.input("resume", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    f.write("data", b"producer reuse");
    {
        let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let t = prepare_transfer_bound(&s, 1).unwrap();
        let t = mover_fs::copy_stage(&s, &t).unwrap();
        let t = mover_fs::verify_stage(&s, &t).unwrap();
        mover_fs::authorize_publication(&s, &t).unwrap();
    }
    let final_path = f.root.join("destination/1/data");
    std::fs::write(&final_path, b"foreign recording").unwrap();
    seed_review(&f);
    f.start();
    assert_eq!(status(&f, "1").1["details"]["review_epoch"], 0);
    let (code, r) = resume(&f, "1", &resume_body(0));
    assert_eq!(code, 200);
    assert_eq!(r["details"]["replay"], false);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if status(&f, "1").1["details"]["delivery_retry"]["failures"] == 1 {
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    assert_eq!(std::fs::read(&final_path).unwrap(), b"foreign recording");
    assert!(!f.root.join("destination/1/COMMITTED.json").exists());
    f.stop();
    seed_review(&f);
    f.start();
    // Replaying an earlier successful command does not unblock a newer review.
    assert_eq!(
        resume(&f, "1", &resume_body(0)).1["details"]["replay"],
        true
    );
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    let mut stale = resume_body(0);
    stale["command_id"] = json!("different-stale");
    assert_eq!(resume(&f, "1", &stale).0, 409);
    f.stop();
    // Remove only this test's deliberately created foreign collision fixture.
    std::fs::remove_file(&final_path).unwrap();
    f.start();
    assert_eq!(resume(&f, "1", &resume_body(1)).0, 200);
    wait_manifest(&f, "1");
    f.stop();
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert!(s.get(1).unwrap().unwrap().recording.is_committed());
    assert_eq!(s.transfer(1, 0).unwrap().unwrap().attempt, 1);
    assert_eq!(s.status(1).unwrap().unwrap().review_epoch, 2);
    assert_eq!(std::fs::read(&final_path).unwrap(), b"abc");
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"producer reuse"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"abc"
    );
}
#[test]
fn operator_resume_lost_reply_survives_restart_and_invalid_requests_do_not_reset() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    assert_eq!(
        f.post(&f.input("resume-lost", json!([{"name":"data"}]))).0,
        202
    );
    assert_eq!(resume(&f, "1", &resume_body(0)).0, 409);
    assert_eq!(resume(&f, "999", &resume_body(0)).0, 404);
    let mut wrong_key = String::from_utf8(resume_bytes("1", &resume_body(0).to_string())).unwrap();
    wrong_key = wrong_key.replace("Host: h\r\n", "Host: h\r\nIdempotency-Key: different\r\n");
    assert_eq!(
        f.raw(wrong_key.as_bytes()).1["error"],
        "idempotency_key_conflict"
    );
    for body in [
        "{}",
        r#"{"command_id":"a","expected_review_epoch":0,"reason":"","extra":true}"#,
        r#"{"command_id":"a","command_id":"b","expected_review_epoch":0,"reason":"fix"}"#,
        r#"{"command_id":"a","expected_review_epoch":-1,"reason":"fix"}"#,
    ] {
        assert_eq!(f.raw(&resume_bytes("1", body)).0, 400);
    }
    f.stop();
    seed_review(&f);
    f.start();
    let mut stream = TcpStream::connect(f.address).unwrap();
    stream
        .write_all(&resume_bytes("1", &resume_body(0).to_string()))
        .unwrap();
    drop(stream);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if status(&f, "1").1["details"]["review_epoch"] == 1 {
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    f.stop();
    f.start();
    let (code, r) = resume(&f, "1", &resume_body(0));
    assert_eq!(code, 200);
    assert_eq!(r["details"]["replay"], true);
    let (_, s) = status(&f, "1");
    assert_eq!(s["details"]["latest_resume"]["command_id"], "resume-0");
    assert_eq!(
        s["details"]["latest_resume"]["actor"],
        "trusted-loopback-operator"
    );
    let mut conflict = resume_body(0);
    conflict["reason"] = json!("changed reason");
    assert_eq!(resume(&f, "1", &conflict).1["error"], "command_conflict");
    f.stop();
}
#[test]
fn operator_resume_rejects_unclaimed_and_committed_jobs() {
    let mut f = Fixture::new(0);
    let body = f.input("not-claimed", json!([{"name":"missing"}]));
    assert_eq!(f.post(&body).0, 409);
    let (_, before) = status(&f, "1");
    assert_eq!(
        resume(&f, "1", &resume_body(0)).1["error"],
        "review_conflict"
    );
    assert_eq!(status(&f, "1").1, before);
    assert_eq!(
        f.raw(b"GET /api/v2/jobs/1/resume HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        405
    );
    assert_eq!(
        f.raw(b"POST /api/v2/jobs/1/resume HTTP/1.1\r\nHost: h\r\n\r\n")
            .0,
        415
    );
    provision_destination(&f);
    f.write("data", b"abc");
    assert_eq!(
        f.post(&f.input("complete", json!([{"name":"data"}]))).0,
        202
    );
    wait_manifest(&f, "2");
    f.stop();
    f.start();
    assert_eq!(status(&f, "2").1["state"], "Committed");
    assert_eq!(
        resume(&f, "2", &resume_body(0)).1["error"],
        "review_conflict"
    );
    assert_eq!(status(&f, "2").1["details"]["review_epoch"], 0);
    assert!(f.root.join("source/.file-mover/2-0/data").exists());
}
#[test]
fn operator_status_observes_partial_claims_outage_and_committed_restart() {
    let mut f = Fixture::new(300);
    f.write("data", b"abc");
    let body = f.input("status", json!([{"name":"data"},{"name":"empty"}]));
    assert_eq!(f.post(&body).0, 503);
    let (code, pending) = status(&f, "1");
    assert_eq!(code, 200);
    assert_eq!(pending["state"], "Accepted");
    assert_eq!(pending["source_paths_released"], false);
    assert_eq!(pending["details"]["files"][0]["size_bytes"], 3);
    assert_eq!(pending["details"]["files"][1]["phase"], "Pending");
    assert_eq!(pending["details"]["missing"].as_array().unwrap().len(), 1);
    f.write("empty", b"");
    assert_eq!(f.post(&body).0, 202);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let (_, s) = status(&f, "1");
        if s["details"]["condition"] == "Retrying" {
            assert_eq!(
                s["details"]["delivery_retry"]["code"],
                "destination_unavailable"
            );
            assert_eq!(s["source_paths_released"], true);
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    f.stop();
    provision_destination(&f);
    f.start();
    wait_manifest(&f, "1");
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let (_, s) = status(&f, "1");
        if s["state"] == "Committed" {
            assert_eq!(s["details"]["manifest_phase"], 4);
            assert_eq!(s["details"]["source_cleanup_enabled"], false);
            assert_eq!(s["details"]["files"][1]["size_bytes"], 0);
            assert_eq!(s["details"]["files"][0]["transfer_phase"], "Published");
            break;
        }
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    f.stop();
    f.start();
    assert_eq!(status(&f, "1").1["state"], "Committed");
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
}
#[test]
fn operator_status_rejects_invalid_routes_and_reports_review_without_reset() {
    let mut f = Fixture::new(0);
    assert_eq!(status(&f, "999").0, 404);
    for id in [
        "0",
        "-1",
        "01",
        "+1",
        "1?x=1",
        "1/files",
        "9223372036854775808",
    ] {
        assert_eq!(status(&f, id).0, 400, "{id}");
    }
    assert_eq!(
        f.raw(b"POST /api/v2/jobs/1 HTTP/1.1\r\nHost: h\r\n\r\n").0,
        405
    );
    assert_eq!(
        f.raw(b"GET /api/v2/jobs/1 HTTP/1.1\r\nHost: h\r\nContent-Length: 1\r\n\r\nx")
            .0,
        400
    );
    assert_eq!(
        f.post(&f.input("missing", json!([{"name":"absent"}]))).0,
        409
    );
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    f.stop();
    f.start();
    let (_, s) = status(&f, "1");
    assert_eq!(s["details"]["condition"], "ReviewRequired");
    assert_eq!(s["source_paths_released"], false);
    assert_eq!(s["details"]["missing"][0]["blocked"], true);
}
fn wait_manifest(f: &Fixture, id: &str) -> Value {
    let path = f.root.join("destination").join(id).join("COMMITTED.json");
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        if let Ok(bytes) = std::fs::read(&path) {
            // Consumer visibility can precede the coordinator's applied receipt.
            // Tests that stop/reopen the service must wait for both boundaries.
            let manifest = serde_json::from_slice(&bytes).unwrap();
            let (code, job) = status(f, id);
            if code == 200 && job["state"] == "Committed" {
                return manifest;
            }
        }
        assert!(Instant::now() < deadline, "background commitment timeout");
        std::thread::sleep(Duration::from_millis(50));
    }
}
#[test]
fn background_multi_file_delivery_commits_after_202_without_more_requests() {
    let mut f = Fixture::new(300);
    provision_destination(&f);
    f.write("sub/alpha", b"abc");
    f.write("sub/beta", b"other");
    f.write("empty", b"");
    let input = f.input(
        "automatic",
        json!([{"name":"sub/alpha"},{"name":"sub/beta"},{"name":"empty","size_bytes":0}]),
    );
    let (status, response) = f.post(&input);
    assert_eq!(status, 202);
    f.write("sub/alpha", b"producer reuse");
    let manifest = wait_manifest(&f, response["job_id"].as_str().unwrap());
    assert_eq!(manifest["files"].as_array().unwrap().len(), 3);
    assert_eq!(
        std::fs::read(f.root.join("destination/1/sub/alpha")).unwrap(),
        b"abc"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/sub/alpha")).unwrap(),
        b"producer reuse"
    );
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
    f.stop();
    let s = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert!(s.get(1).unwrap().unwrap().recording.is_committed());
    for i in 0..3 {
        assert!(
            f.root
                .join(format!("source/.file-mover/1-{i}/data"))
                .exists()
        );
    }
}
#[test]
fn restart_discovers_claimed_delivery_and_keeps_original_destination() {
    let mut f = Fixture::new(300);
    f.write("data", b"persisted");
    assert_eq!(f.post(&f.input("restart", json!([{"name":"data"}]))).0, 202);
    f.stop();
    provision_destination(&f);
    let path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    config["destination_root"] = json!(f.root.join("replacement"));
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    f.start();
    let manifest = wait_manifest(&f, "1");
    assert_eq!(manifest["files"][0]["size_bytes"], 9);
    assert!(!f.root.join("replacement/1").exists());
    f.stop();
    let output = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg("--transfer-one")
        .arg(f.root.join("config.json"))
        .arg("1")
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
    let state: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(state["committed"], true);
}
#[test]
fn retention_limits_refuse_new_work_without_false_release_or_orphan() {
    let mut f = Fixture::new(300);
    f.stop();
    let path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    config["max_retained_jobs"] = json!(1);
    config["max_retained_bytes"] = json!(3);
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    f.start();
    f.write("data", b"abcd");
    let body = f.input("limited", json!([{"name":"data"}]));
    let (status, response) = f.post(&body);
    assert_eq!(status, 503);
    assert_eq!(response["error"], "retention_capacity");
    assert_eq!(response["source_paths_released"], false);
    assert!(f.root.join("source/current/data").exists());
    assert!(!f.root.join("source/.file-mover/1-0").exists());
    f.stop();
    config["max_retained_bytes"] = json!(10);
    std::fs::write(path, serde_json::to_vec(&config).unwrap()).unwrap();
    f.start();
    assert_eq!(f.post(&body).0, 202);
    f.write("other", b"x");
    assert_eq!(f.post(&f.input("extra", json!([{"name":"other"}]))).0, 503);
    assert_eq!(f.post(&body).0, 202);
    f.stop();
}

fn prepare_transfer_bound(
    store: &mover_store::Store,
    id: i64,
) -> Result<mover_core::Transfer, Box<dyn std::error::Error>> {
    let job = store.get(id)?.unwrap();
    let binding = destination_binding();
    let authorization =
        mover_fs::DestinationAuthorization::observe(&job.context.destination_path, &binding)?;
    store.pin_destination(id, &binding.encode(), &authorization.observation)?;
    mover_fs::prepare_transfer(store, id)
}
fn wait_delivery_failure(f: &Fixture) -> Value {
    let deadline = Instant::now() + Duration::from_secs(8);
    loop {
        let s = status(f, "1").1;
        if s["details"]["delivery_retry"]["code"] == "destination_binding_requires_review" {
            return s;
        }
        assert!(Instant::now() < deadline, "{s}");
        std::thread::sleep(Duration::from_millis(20));
    }
}
#[test]
fn destination_binding_is_required_strict_and_coordinator_scoped() {
    let f = Fixture::new(300);
    let original: Value =
        serde_json::from_slice(&std::fs::read(f.root.join("config.json")).unwrap()).unwrap();
    let mut missing = original.clone();
    missing
        .as_object_mut()
        .unwrap()
        .remove("destination_binding");
    assert!(serde_json::from_value::<file_mover::Config>(missing).is_err());
    for (field, bad) in [
        ("role", json!("source")),
        ("filesystem", json!("automatic")),
        ("unknown", json!(true)),
        ("version", json!(1)),
        ("root_id", json!("../escape")),
        ("coordinator_id", json!("another-owner")),
    ] {
        let mut value = original.clone();
        value["destination_binding"][field] = bad;
        assert!(
            serde_json::from_value::<file_mover::Config>(value)
                .map(|c| c.validate().is_err())
                .unwrap_or(true)
        );
    }
}
#[test]
fn destination_marker_custody_is_required_without_creating_or_adopting_markers() {
    use std::os::unix::fs::symlink;
    for case in [
        "missing",
        "mode",
        "symlink",
        "hardlink",
        "oversized",
        "malformed",
    ] {
        let mut f = Fixture::new(300);
        f.stop();
        provision_destination(&f);
        let marker = f
            .root
            .join("destination/.file-mover/destination-binding.json");
        match case {
            "missing" => std::fs::remove_file(&marker).unwrap(),
            "mode" => {
                std::fs::set_permissions(&marker, std::fs::Permissions::from_mode(0o644)).unwrap()
            }
            "symlink" => {
                let backup = f.root.join("marker");
                std::fs::rename(&marker, &backup).unwrap();
                symlink(backup, &marker).unwrap();
            }
            "hardlink" => std::fs::hard_link(&marker, f.root.join("marker-alias")).unwrap(),
            "oversized" => std::fs::write(&marker, vec![b'x'; 4097]).unwrap(),
            "malformed" => std::fs::write(&marker, b"{}").unwrap(),
            _ => unreachable!(),
        }
        f.start();
        f.write("data", b"keep");
        assert_eq!(f.post(&f.input(case, json!([{"name":"data"}]))).0, 202);
        wait_delivery_failure(&f);
        assert!(!f.root.join("destination/1").exists());
        if case == "missing" {
            assert!(!marker.exists());
        }
        f.stop();
    }
}
#[test]
fn populated_state_without_destination_policy_refuses_service_startup() {
    let mut f = Fixture::new(300);
    f.write("data", b"legacy retained");
    f.stop();
    let database = f.root.join("state/jobs.sqlite");
    let store = mover_store::Store::open(&database).unwrap();
    let submission = mover_core::Submission::new(
        "recorder",
        "legacy-destination",
        f.root.join("source/current").to_str().unwrap(),
        vec![mover_core::FileSpec::new("data", None).unwrap()],
    )
    .unwrap();
    let context = mover_store::AcceptanceContext {
        source_root_id: "local-source".into(),
        source_root_path: f.root.join("source").to_str().unwrap().into(),
        source_relative_directory: "current".into(),
        destination_path: f.root.join("destination").to_str().unwrap().into(),
        destination_binding: None,
        missing_retry_seconds: 300,
        policy: mover_core::DeliveryPolicy {
            destination_id: "configured-local".into(),
            group_by_generator: false,
            delete_source_after_commit: false,
        },
    };
    store.accept(&submission, &context).unwrap();
    drop(store);
    assert!(refused_start(&f.root.join("config.json")).contains("DestinationEnrollmentRequired"));
    let store = mover_store::Store::open(database).unwrap();
    assert_eq!(store.job_count().unwrap(), 1);
    assert_eq!(
        std::fs::read(f.root.join("source/current/data")).unwrap(),
        b"legacy retained"
    );
}
#[test]
fn unavailable_destination_claims_then_foreign_marker_requires_review_without_allocation() {
    let mut f = Fixture::new(300);
    f.write("data", b"custody retained");
    let body = f.input("destination-foreign", json!([{"name":"data"}]));
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    assert!(store.destination_observation(1).unwrap().is_none());
    drop(store);
    provision_destination(&f);
    let marker = f
        .root
        .join("destination/.file-mover/destination-binding.json");
    let mut foreign = destination_binding();
    foreign.marker_id = "foreign".into();
    std::fs::write(&marker, foreign.encode()).unwrap();
    f.start();
    let s = wait_delivery_failure(&f);
    assert!(s["source_paths_released"].as_bool().unwrap());
    assert!(!f.root.join("destination/1").exists());
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"custody retained"
    );
    provision_destination_marker(&f.root.join("destination"));
    f.start();
    assert_eq!(status(&f, "1").1["details"]["condition"], "ReviewRequired");
    assert!(!f.root.join("destination/1").exists());
    assert_eq!(resume(&f, "1", &resume_body(0)).0, 200);
    wait_manifest(&f, "1");
    f.stop();
}
#[test]
fn destination_declared_nfs_refuses_matching_marker_on_local_filesystem() {
    let mut f = Fixture::new(300);
    f.stop();
    provision_destination(&f);
    let mut b = destination_binding();
    b.filesystem = mover_fs::SourceFilesystem::Nfs;
    b.nfs_mount = Some(mover_fs::NfsMountProfile {
        profile: mover_fs::MountProfile::Buffered,
        mountpoint: f.root.join("destination").to_str().unwrap().into(),
        source: "192.0.2.1:/expected".into(),
        addr: "192.0.2.1".into(),
    });
    let path = f.root.join("config.json");
    let mut config: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    config["destination_binding"] = json!(b);
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    std::fs::write(
        f.root
            .join("destination/.file-mover/destination-binding.json"),
        b.encode(),
    )
    .unwrap();
    f.start();
    f.write("data", b"nfs expected");
    assert_eq!(
        f.post(&f.input("nfs-fallback", json!([{"name":"data"}]))).0,
        202
    );
    wait_delivery_failure(&f);
    assert!(!f.root.join("destination/1").exists());
    f.stop();
}
#[test]
fn destination_root_replacement_is_refused_before_first_allocation() {
    let mut f = Fixture::new(300);
    f.write("data", b"approved root");
    let body = f.input("destination-replaced", json!([{"name":"data"}]));
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    provision_destination(&f);
    let path = f.root.join("destination");
    let saved = f.root.join("approved-destination");
    {
        let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
        let lock = mover_fs::LocalClaimLock::acquire_destination(
            path.to_str().unwrap(),
            &destination_binding(),
            None,
        )
        .unwrap();
        store
            .pin_destination(
                1,
                &destination_binding().encode(),
                &lock.destination_authorization().unwrap().observation,
            )
            .unwrap();
    }
    std::fs::rename(&path, &saved).unwrap();
    provision_destination(&f);
    // Even preserve the original marker inode: the replacement root remains foreign.
    std::fs::remove_file(path.join(".file-mover/destination-binding.json")).unwrap();
    std::fs::rename(
        saved.join(".file-mover/destination-binding.json"),
        path.join(".file-mover/destination-binding.json"),
    )
    .unwrap();
    f.start();
    wait_delivery_failure(&f);
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    assert!(!path.join("1").exists());
    assert!(!saved.join("1").exists());
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"approved root"
    );
}
#[test]
fn delivery_session_rechecks_destination_marker_before_payload() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained");
    assert_eq!(
        f.post(&f.input("destination-session", json!([{"name":"data"}])))
            .0,
        202
    );
    f.stop();
    provision_destination(&f);
    let guard = mover_fs::LocalClaimLock::acquire_bound(
        f.root.join("source").to_str().unwrap(),
        &binding(),
    )
    .unwrap();
    let store = mover_store::Store::open(f.root.join("state/jobs.sqlite")).unwrap();
    let t = prepare_transfer_bound(&store, 1).unwrap();
    let claim = store.claim_intent(1, 0).unwrap().unwrap().0;
    let (mut child, mut channel) = effect_child(&guard, &guard, "--internal-delivery-worker");
    let opened = session_authorized_reply(
        &mut channel,
        1,
        json!({"operation":"open","job_id":1,"source_root":f.root.join("source"),"destination_root":f.root.join("destination"),"destination_binding":destination_binding(),"destination_observation":store.destination_observation(1).unwrap()}),
        guard.source_authorization(),
    );
    assert!(opened["error"].is_null());
    let mut changed = destination_binding();
    changed.marker_id = "changed".into();
    std::fs::write(
        f.root
            .join("destination/.file-mover/destination-binding.json"),
        changed.encode(),
    )
    .unwrap();
    let reply = session_authorized_reply(
        &mut channel,
        2,
        json!({"operation":"payload","assignment":payload_assignment(&t,&claim)}),
        guard.source_authorization(),
    );
    assert!(reply["error"].is_string());
    assert!(reply["transfer"].is_null());
    drop(channel);
    assert!(child.wait().unwrap().success());
    assert_eq!(
        std::fs::metadata(f.root.join("destination/1/.staging/1.part"))
            .unwrap()
            .len(),
        0
    );
}

fn configure_space(f: &Fixture, policy: Value) {
    let path = f.root.join("config.json");
    let mut c: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    c["source_space_admission"] = policy;
    std::fs::write(path, serde_json::to_vec(&c).unwrap()).unwrap();
}
fn space_post_until(f: &Fixture, body: &Value, target: u16) -> Value {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let (code, r) = f.post(body);
        if code == target {
            return r;
        }
        assert_eq!(code, 503, "{r}");
        assert_eq!(r["error"], "source_space_unavailable", "{r}");
        assert!(Instant::now() < deadline, "{r}");
        std::thread::sleep(Duration::from_millis(30));
    }
}
#[test]
fn source_space_low_refuses_without_job_and_preserves_partial_replay_and_restart() {
    let mut f = Fixture::new(300);
    f.write("a", b"old");
    let partial = f.input("partial-space", json!([{"name":"a"},{"name":"b"}]));
    assert_eq!(f.post(&partial).1["error"], "handoff_pending");
    f.stop();
    configure_space(
        &f,
        json!({"enabled":true,"min_available_bytes":u64::MAX,"max_sample_age_seconds":1,"probe_timeout_seconds":1}),
    );
    f.start();
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["reason"],
        "not_sampled"
    );
    assert_eq!(f.post(&partial).1["error"], "handoff_pending");
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["reason"],
        "not_sampled"
    );
    let mut conflict = partial.clone();
    conflict["files"] = json!([{"name":"different"}]);
    assert_eq!(f.post(&conflict).0, 409);
    f.write("new", b"pending");
    let body = f.input("new-space", json!([{"name":"new"}]));
    let first = f.post(&body);
    assert_eq!(first.0, 503);
    assert!(
        ["source_space_low", "source_space_unavailable"]
            .contains(&first.1["error"].as_str().unwrap())
    );
    let deadline = Instant::now() + Duration::from_secs(5);
    let refused = loop {
        let (_, r) = f.post(&body);
        if r["error"] == "source_space_low" {
            break r;
        }
        assert!(Instant::now() < deadline, "{r}");
        std::thread::sleep(Duration::from_millis(30));
    };
    assert_eq!(refused["source_paths_released"], false);
    assert!(refused.get("job_id").is_none());
    assert_eq!(retention(&f, None).1["details"]["retained_jobs"], 1);
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["state"],
        "Low"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/new")).unwrap(),
        b"pending"
    );
    assert!(!f.root.join("source/.file-mover/2-0").exists());
    f.write("b", b"other");
    assert_eq!(f.post(&partial).0, 202);
    f.write("a", b"new recording");
    assert_eq!(f.post(&partial).0, 202);
    std::thread::sleep(Duration::from_millis(1100));
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["reason"],
        "sample_expired"
    );
    f.stop();
    f.start();
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["reason"],
        "not_sampled"
    );
    assert_eq!(f.post(&partial).0, 202);
    // Threshold restoration requires a fresh sample, not a persisted permit.
    f.stop();
    configure_space(&f, json!({"enabled":true,"min_available_bytes":1}));
    f.start();
    assert_eq!(space_post_until(&f, &body, 202)["job_id"], "2");
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["state"],
        "Sufficient"
    );
    assert_eq!(
        std::fs::read(f.root.join("source/current/a")).unwrap(),
        b"new recording"
    );
    f.stop();
    configure_space(&f, json!({"enabled":false,"min_available_bytes":u64::MAX}));
    f.start();
    f.write("off", b"off");
    assert_eq!(
        f.post(&f.input("off-space", json!([{"name":"off"}]))).0,
        202
    );
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["state"],
        "Disabled"
    );
    assert!(
        retention(&f, Some("1")).1["details"]
            .get("source_space_admission")
            .is_none()
    );
}
#[test]
fn enabled_source_space_native_sample_allows_nested_empty_delivery_without_double_charge() {
    let mut f = Fixture::new(300);
    f.stop();
    configure_space(
        &f,
        json!({"enabled":true,"min_available_bytes":1,"min_available_percent":1}),
    );
    provision_destination(&f);
    f.start();
    f.write("sub/data", b"native statistics");
    f.write("empty", b"");
    let body = f.input(
        "native-space",
        json!([{"name":"sub/data"},{"name":"empty","size_bytes":0}]),
    );
    assert_eq!(
        space_post_until(&f, &body, 202)["source_paths_released"],
        true
    );
    let deadline = Instant::now() + Duration::from_secs(10);
    while status(&f, "1").1["state"] != "Committed" {
        assert!(Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(20));
    }
    let (_, r) = retention(&f, None);
    assert_eq!(r["details"]["filesystem_inspected"], false);
    assert!(
        r["details"]["source_space_admission"]["observed_available_bytes"]
            .as_str()
            .unwrap()
            .parse::<u128>()
            .unwrap()
            > 0
    );
    assert_eq!(r["details"]["source_reserved_bytes"], "17");
    assert!(f.root.join("source/.file-mover/1-0/data").exists());
    assert_eq!(f.post(&body).0, 202);
}
#[test]
fn source_space_probe_faults_are_qualification_only_and_do_not_gate_existing_jobs() {
    let mut f = Fixture::new(300);
    f.write("existing", b"retained");
    let old = f.input("existing-space", json!([{"name":"existing"}]));
    assert_eq!(f.post(&old).0, 202);
    f.stop();
    configure_space(&f, json!({"enabled":true,"min_available_bytes":1}));
    let mut command = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap());
    command.env("FILE_MOVER_QUALIFICATION_SOURCE_SPACE_FAULT", "unavailable");
    f.start_command(command);
    f.write("new", b"new");
    let body = f.input("fault-space", json!([{"name":"new"}]));
    if cfg!(feature = "nfs-qualification") {
        for _ in 0..5 {
            let (code, r) = f.post(&body);
            assert_eq!(code, 503);
            assert_eq!(r["error"], "source_space_unavailable");
            std::thread::sleep(Duration::from_millis(40));
        }
        assert_eq!(retention(&f, None).1["details"]["retained_jobs"], 1);
        assert_eq!(f.post(&old).0, 202);
        assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
    } else {
        assert_eq!(space_post_until(&f, &body, 202)["job_id"], "2");
    }
}
#[test]
fn source_space_probe_timeout_preserves_responsive_replay_and_custody() {
    let mut f = Fixture::new(300);
    f.write("existing", b"retained");
    let old = f.input("timeout-old", json!([{"name":"existing"}]));
    assert_eq!(f.post(&old).0, 202);
    f.stop();
    configure_space(
        &f,
        json!({"enabled":true,"min_available_bytes":1,"probe_timeout_seconds":1,"max_sample_age_seconds":2}),
    );
    let rendezvous = f.root.join("space-pause");
    std::fs::create_dir(&rendezvous).unwrap();
    std::fs::set_permissions(&rendezvous, std::fs::Permissions::from_mode(0o700)).unwrap();
    let mut command = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap());
    command
        .env("FILE_MOVER_QUALIFICATION_PAUSE", "source_space_statistics")
        .env("FILE_MOVER_QUALIFICATION_RENDEZVOUS", &rendezvous);
    f.start_command(command);
    f.write("new", b"new");
    let body = f.input("timeout-new", json!([{"name":"new"}]));
    let address = f.address;
    let bytes = post_bytes(&body);
    let pending = std::thread::spawn(move || exchange(address, &bytes));
    if cfg!(feature = "nfs-qualification") {
        let deadline = Instant::now() + Duration::from_secs(3);
        while !rendezvous.join("ready").exists() {
            assert!(Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(10));
        }
        let ready = std::fs::read_to_string(rendezvous.join("ready")).unwrap();
        let started = Instant::now();
        assert_eq!(f.post(&old).0, 202);
        assert!(started.elapsed() < Duration::from_secs(2));
        assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
        assert_eq!(retention(&f, None).1["details"]["retained_jobs"], 1);
        let (code, r) = pending.join().unwrap();
        assert_eq!(code, 503);
        assert_eq!(r["error"], "source_space_unavailable");
        std::thread::sleep(Duration::from_millis(200));
        assert_eq!(
            retention(&f, None).1["details"]["source_space_admission"]["state"],
            "Unknown"
        );
        assert_eq!(
            std::fs::read_to_string(rendezvous.join("ready")).unwrap(),
            ready
        );
        assert_eq!(f.post(&old).0, 202);
    } else {
        assert_eq!(pending.join().unwrap().0, 202);
        assert!(!rendezvous.join("ready").exists());
    }
    f.stop();
}
#[test]
fn source_space_cold_and_expired_samples_do_not_require_fast_recorder_retries() {
    let mut f = Fixture::new(300);
    f.stop();
    configure_space(
        &f,
        json!({"enabled":true,"min_available_bytes":1,"max_sample_age_seconds":1,"probe_timeout_seconds":1}),
    );
    f.start();
    f.write("one", b"1");
    assert_eq!(
        f.post(&f.input("slow-retry-one", json!([{"name":"one"}])))
            .0,
        202
    );
    std::thread::sleep(Duration::from_millis(1100));
    assert_eq!(
        retention(&f, None).1["details"]["source_space_admission"]["state"],
        "Unknown"
    );
    f.write("two", b"2");
    assert_eq!(
        f.post(&f.input("slow-retry-two", json!([{"name":"two"}])))
            .0,
        202
    );
    assert_eq!(retention(&f, None).1["details"]["retained_jobs"], 2);
}

fn instance_refusal(mut command: Command) {
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let until = Instant::now() + Duration::from_secs(4);
    loop {
        if child.try_wait().unwrap().is_some() {
            break;
        }
        if Instant::now() > until {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("duplicate instance failed to refuse promptly");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    let result = child.wait_with_output().unwrap();
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr)
            .contains("local instance or surviving worker already owns state"),
        "{result:?}"
    );
}
#[test]
fn local_instance_refuses_all_effect_entry_points_before_bootstrap_or_sqlite() {
    let mut f = Fixture::new(300);
    let exe = std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap();
    let mut config: Value =
        serde_json::from_slice(&std::fs::read(f.root.join("config.json")).unwrap()).unwrap();
    config["bind"] = json!("127.0.0.1:0");
    config["state_database"] = json!(f.root.join("state/not-created.sqlite"));
    config["source_root"] = json!(f.root.join("unavailable-source"));
    let path = f.root.join("duplicate.json");
    std::fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
    for mode in [None, Some("--initialize-source"), Some("--transfer-one")] {
        let mut command = Command::new(&exe);
        if let Some(mode) = mode {
            command.arg(mode);
        }
        command.arg(&path);
        if mode == Some("--transfer-one") {
            command.arg("1");
        }
        instance_refusal(command);
        assert!(!f.root.join("state/not-created.sqlite").exists());
        assert!(!f.root.join("unavailable-source").exists());
    }
    assert_eq!(f.raw(b"GET /healthz HTTP/1.1\r\nHost: h\r\n\r\n").0, 200);
    f.stop();
    f.start();
    f.stop();
}
#[test]
fn all_six_worker_modes_retain_explicit_local_ownership_without_parent_holder() {
    use std::os::unix::net::UnixStream;
    let f = Fixture::uninitialized(300);
    let db = f.root.join("state/jobs.sqlite");
    let exe = std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap();
    for mode in [
        "bootstrap",
        "enrollment",
        "claim",
        "payload",
        "delivery",
        "source-space",
    ] {
        let guard = mover_fs::InstanceGuard::for_database(db.to_str().unwrap()).unwrap();
        let (mut channel, worker) = UnixStream::pair().unwrap();
        channel
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        channel
            .set_write_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        guard.prepare_workers().unwrap();
        let mut child = Command::new(&exe)
            .arg(format!("--internal-{mode}-worker"))
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
            .spawn()
            .unwrap();
        guard.send(&mut channel).unwrap(); // ACK proves child validation, not just a queued fd.
        drop(guard);
        assert!(child.try_wait().unwrap().is_none(), "{mode}");
        assert!(
            mover_fs::InstanceGuard::for_database(db.to_str().unwrap()).is_err(),
            "{mode}"
        );
        child.kill().unwrap();
        child.wait().unwrap();
        drop(channel);
        drop(mover_fs::InstanceGuard::for_database(db.to_str().unwrap()).unwrap());
        assert!(!db.exists());
        // Same internal mode without the descriptor prefix cannot reach effects.
        let (mut channel, worker) = UnixStream::pair().unwrap();
        let mut child = Command::new(&exe)
            .arg(format!("--internal-{mode}-worker"))
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::from(std::os::fd::OwnedFd::from(worker)))
            .spawn()
            .unwrap();
        channel.write_all(b"I").unwrap();
        channel.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(!child.wait().unwrap().success());
        assert!(!db.exists());
    }
}
#[test]
fn killed_coordinator_cannot_release_local_guard_held_by_paused_claim_worker() {
    if !cfg!(feature = "nfs-qualification") {
        return;
    }
    let mut f = Fixture::uninitialized(300);
    assert!(
        initialize_source(&f.root.join("config.json"))
            .status
            .success()
    );
    provision_destination(&f);
    let rendezvous = f.root.join("instance-pause");
    std::fs::create_dir(&rendezvous).unwrap();
    std::fs::set_permissions(&rendezvous, std::fs::Permissions::from_mode(0o700)).unwrap();
    f.write("data", b"original recording");
    let exe = std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap();
    let mut command = Command::new(&exe);
    command
        .env("FILE_MOVER_QUALIFICATION_PAUSE", "claim_apply")
        .env("FILE_MOVER_QUALIFICATION_RENDEZVOUS", &rendezvous);
    f.start_command(command);
    let body = f.input("surviving-worker", json!([{"name":"data"}]));
    let bytes = serde_json::to_vec(&body).unwrap();
    let address = f.address;
    let pending = std::thread::spawn(move || {
        let mut s = TcpStream::connect(address).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(15))).unwrap();
        write!(s,"POST /api/v2/jobs HTTP/1.1\r\nHost: h\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",bytes.len()).unwrap();
        s.write_all(&bytes).unwrap();
        let mut reply = String::new();
        let _ = s.read_to_string(&mut reply);
        reply
    });
    let until = Instant::now() + Duration::from_secs(5);
    while !rendezvous.join("ready").exists() {
        assert!(Instant::now() < until);
        std::thread::sleep(Duration::from_millis(10));
    }
    let ready = std::fs::read_to_string(rendezvous.join("ready")).unwrap();
    let worker = ready.split_whitespace().next().unwrap();
    assert!(worker.bytes().all(|b| b.is_ascii_digit()));
    let mut parent = f.child.take().unwrap();
    parent.kill().unwrap();
    parent.wait().unwrap();
    assert!(!pending.join().unwrap().starts_with("HTTP/1.1 202"));
    let mut duplicate = Command::new(&exe);
    duplicate.arg(f.root.join("config.json"));
    instance_refusal(duplicate);
    assert!(
        Command::new("/bin/kill")
            .args(["-KILL", worker])
            .status()
            .unwrap()
            .success()
    );
    let db = f.root.join("state/jobs.sqlite");
    let until = Instant::now() + Duration::from_secs(3);
    loop {
        match mover_fs::InstanceGuard::for_database(db.to_str().unwrap()) {
            Ok(g) => {
                drop(g);
                break;
            }
            Err(_) => {
                assert!(Instant::now() < until);
                std::thread::sleep(Duration::from_millis(10));
            }
        }
    }
    f.start();
    assert_eq!(f.post(&body).0, 202);
    wait_manifest(&f, "1");
    assert_eq!(
        std::fs::read(f.root.join("source/.file-mover/1-0/data")).unwrap(),
        b"original recording"
    );
    f.stop();
}

fn control_child(f: &Fixture, mode: &str) -> Child {
    Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg(mode)
        .arg(f.root.join("config.json"))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap()
}
fn control_result(mut child: Child, seconds: u64) -> (bool, Value) {
    let deadline = Instant::now() + Duration::from_secs(seconds);
    while child.try_wait().unwrap().is_none() {
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("unbounded lifecycle controller");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    let out = child.wait_with_output().unwrap();
    let value = serde_json::from_slice(&out.stdout).unwrap_or_else(|e| panic!("{e}: {out:?}"));
    (out.status.success(), value)
}
fn local_status(f: &Fixture) -> (bool, Value) {
    control_result(control_child(f, "--status"), 3)
}
fn shutdown_config(f: &Fixture, value: Value) {
    let path = f.root.join("config.json");
    let mut c: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    c["shutdown_wait_seconds"] = value;
    std::fs::write(&path, serde_json::to_vec(&c).unwrap()).unwrap();
}
#[test]
fn shutdown_setting_defaults_to_sixty_and_rejects_unbounded_or_noninteger_values() {
    let f = Fixture::uninitialized(300);
    let base: Value =
        serde_json::from_slice(&std::fs::read(f.root.join("config.json")).unwrap()).unwrap();
    let c: file_mover::Config = serde_json::from_value(base.clone()).unwrap();
    assert_eq!(c.shutdown_wait_seconds, 60);
    for value in [json!(1), json!(3600)] {
        let mut c = base.clone();
        c["shutdown_wait_seconds"] = value;
        assert!(
            serde_json::from_value::<file_mover::Config>(c)
                .unwrap()
                .validate()
                .is_ok()
        );
    }
    for value in [
        json!(0),
        json!(3601),
        json!(-1),
        json!(1.5),
        json!("60"),
        Value::Null,
        json!(true),
        json!(4294967296_u64),
    ] {
        let mut c = base.clone();
        c["shutdown_wait_seconds"] = value;
        if let Ok(c) = serde_json::from_value::<file_mover::Config>(c) {
            assert!(c.validate().is_err());
        }
    }
    assert!(!f.root.join("state/instance.lock").exists());
}
#[test]
fn local_controller_observes_clean_stop_without_sqlite_or_transfer_mount_access() {
    let mut f = Fixture::new(300);
    let (ok, s) = local_status(&f);
    assert!(ok);
    assert_eq!(s["phase"], "Running");
    assert_eq!(s["shutdown_wait_seconds"], 60);
    // Status/stop do not need source traversal, bindings, destination or a DB query.
    std::fs::rename(f.root.join("source"), f.root.join("source-hidden")).unwrap();
    let (ok, s) = local_status(&f);
    assert!(ok);
    assert_eq!(s["phase"], "Running");
    assert!(control_result(control_child(&f, "--stop"), 5).0);
    assert!(f.child.take().unwrap().wait().unwrap().success());
    assert!(!f.root.join("state/control.sock").exists());
    assert!(f.root.join("state/instance.lock").exists());
    let (ok, s) = local_status(&f);
    assert!(ok);
    assert_eq!(s["phase"], "NoActiveOwner");
    std::fs::rename(f.root.join("source-hidden"), f.root.join("source")).unwrap();
    f.start();
    f.stop();
}
#[test]
fn local_controller_absence_or_surviving_holder_never_creates_state_or_reports_false_completion() {
    let f = Fixture::uninitialized(300);
    for mode in ["--status", "--stop"] {
        let (ok, s) = control_result(control_child(&f, mode), 3);
        assert!(ok);
        assert_eq!(s["phase"], "NoActiveOwner");
    }
    assert!(!f.root.join("state/instance.lock").exists());
    let guard =
        mover_fs::InstanceGuard::for_database(f.root.join("state/jobs.sqlite").to_str().unwrap())
            .unwrap();
    for mode in ["--status", "--stop"] {
        let (ok, s) = control_result(control_child(&f, mode), 3);
        assert!(!ok);
        assert_eq!(s["phase"], "OwnerUnavailable");
        assert_eq!(s["message"], "shutdown incomplete; restart blocked");
    }
    assert!(!f.root.join("state/jobs.sqlite").exists());
    drop(guard);
}
#[test]
fn control_endpoint_rejects_invalid_requests_and_preserves_unsafe_named_files() {
    use std::os::unix::net::UnixStream;
    let mut f = Fixture::new(300);
    for body in [
        b"{}".to_vec(),
        vec![b'x'; 257],
        serde_json::to_vec(&json!({"version":1,"command":"stop","instance_id":"foreign"})).unwrap(),
        serde_json::to_vec(&json!({"version":2,"command":"stop","instance_id":null})).unwrap(),
    ] {
        let mut s = UnixStream::connect(f.root.join("state/control.sock")).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        s.write_all(&body).unwrap();
        s.shutdown(std::net::Shutdown::Write).unwrap();
        let mut reply = vec![];
        let _ = s.read_to_end(&mut reply);
        assert!(reply.is_empty());
        assert_eq!(local_status(&f).1["phase"], "Running");
    }
    f.stop();
    let endpoint = f.root.join("state/control.sock");
    std::fs::write(&endpoint, b"preserve this unrelated file").unwrap();
    let result = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap())
        .arg(f.root.join("config.json"))
        .output()
        .unwrap();
    assert!(!result.status.success());
    assert_eq!(
        std::fs::read(endpoint).unwrap(),
        b"preserve this unrelated file"
    );
}
#[test]
fn unresponsive_local_endpoint_returns_bounded_owner_unavailable() {
    use std::os::unix::net::UnixListener;
    let f = Fixture::uninitialized(300);
    let _guard =
        mover_fs::InstanceGuard::for_database(f.root.join("state/jobs.sqlite").to_str().unwrap())
            .unwrap();
    let endpoint = f.root.join("state/control.sock");
    let _socket = UnixListener::bind(&endpoint).unwrap();
    std::fs::set_permissions(&endpoint, std::fs::Permissions::from_mode(0o600)).unwrap();
    for mode in ["--status", "--stop"] {
        let start = Instant::now();
        let (ok, s) = control_result(control_child(&f, mode), 3);
        assert!(!ok);
        assert_eq!(s["phase"], "OwnerUnavailable");
        assert!(start.elapsed() < Duration::from_secs(2));
    }
    assert!(!f.root.join("state/jobs.sqlite").exists());
}
#[test]
fn configured_stop_deadline_survives_repeated_requests_signals_and_config_edits() {
    if !cfg!(feature = "nfs-qualification") {
        return;
    }
    for _ in 0..3 {
        let mut f = Fixture::new(300);
        f.stop();
        shutdown_config(&f, json!(2));
        let rendezvous = f.root.join("drain");
        std::fs::create_dir(&rendezvous).unwrap();
        std::fs::set_permissions(&rendezvous, std::fs::Permissions::from_mode(0o700)).unwrap();
        let mut command = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap());
        command
            .env("FILE_MOVER_QUALIFICATION_PAUSE", "shutdown_drain")
            .env("FILE_MOVER_QUALIFICATION_RENDEZVOUS", &rendezvous);
        f.start_command(command);
        f.write("data", b"retained while stopping");
        let start = Instant::now();
        let first = control_child(&f, "--stop");
        let deadline = Instant::now() + Duration::from_secs(3);
        while !rendezvous.join("ready").exists() {
            assert!(Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(10));
        }
        shutdown_config(&f, json!(3600));
        assert!(
            Command::new("/bin/kill")
                .args(["-TERM", &f.child.as_ref().unwrap().id().to_string()])
                .status()
                .unwrap()
                .success()
        );
        let second = control_result(control_child(&f, "--stop"), 4);
        let first = control_result(first, 4);
        let identity = first.1["instance_id"].clone();
        for (ok, s) in [first, second] {
            assert!(!ok);
            assert_eq!(s["instance_id"], identity);
            assert_eq!(s["phase"], "ShutdownIncomplete");
            assert_eq!(s["shutdown_wait_seconds"], 2);
            assert_eq!(s["shutdown_remaining_ms"], 0);
        }
        // The client's conservative wait can end before the daemon's deadline.
        // Poll only within the original test bound; never treat Draining as exit.
        let status_deadline = start + Duration::from_secs(4);
        let mut last_remaining = 2000;
        loop {
            assert!(Instant::now() < status_deadline);
            let (ok, status) = local_status(&f);
            assert!(Instant::now() < status_deadline);
            assert!(f.child.as_mut().unwrap().try_wait().unwrap().is_none());
            assert_eq!(status["instance_id"], identity);
            assert_eq!(status["shutdown_wait_seconds"], 2);
            let remaining = status["shutdown_remaining_ms"].as_u64().unwrap();
            assert!(remaining <= last_remaining, "shutdown countdown increased");
            match status["phase"].as_str().unwrap() {
                "ShutdownIncomplete" => {
                    assert!(!ok);
                    assert_eq!(remaining, 0);
                    break;
                }
                "Draining" => {
                    assert!(ok);
                    assert!(remaining > 0);
                }
                phase => panic!("unexpected post-stop status: {phase}"),
            }
            last_remaining = remaining;
            std::thread::sleep(Duration::from_millis(10));
        }
        let mut duplicate = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap());
        duplicate
            .arg("--initialize-source")
            .arg(f.root.join("config.json"));
        instance_refusal(duplicate);
        std::fs::write(rendezvous.join("go"), b"").unwrap();
        assert!(f.child.take().unwrap().wait().unwrap().success());
        assert_eq!(
            std::fs::read(f.root.join("source/current/data")).unwrap(),
            b"retained while stopping"
        );
        assert_eq!(local_status(&f).1["phase"], "NoActiveOwner");
        f.start();
        f.stop();
    }
}
#[test]
fn default_sixty_second_stop_returns_incomplete_while_delayed_drain_retains_ownership() {
    if !cfg!(feature = "nfs-qualification") {
        return;
    }
    let mut f = Fixture::new(300);
    f.stop();
    let rendezvous = f.root.join("default-drain");
    std::fs::create_dir(&rendezvous).unwrap();
    std::fs::set_permissions(&rendezvous, std::fs::Permissions::from_mode(0o700)).unwrap();
    let mut command = Command::new(std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap());
    command
        .env("FILE_MOVER_QUALIFICATION_PAUSE", "shutdown_drain")
        .env("FILE_MOVER_QUALIFICATION_RENDEZVOUS", &rendezvous);
    f.start_command(command);
    let start = Instant::now();
    let (ok, s) = control_result(control_child(&f, "--stop"), 64);
    assert!(!ok);
    assert_eq!(s["shutdown_wait_seconds"], 60);
    assert_eq!(s["phase"], "ShutdownIncomplete");
    assert!(
        start.elapsed() >= Duration::from_secs(59) && start.elapsed() < Duration::from_secs(63)
    );
    assert!(f.child.as_mut().unwrap().try_wait().unwrap().is_none());
    assert!(
        mover_fs::InstanceGuard::for_database(f.root.join("state/jobs.sqlite").to_str().unwrap())
            .is_err()
    );
    std::fs::write(rendezvous.join("go"), b"").unwrap();
    assert!(f.child.take().unwrap().wait().unwrap().success());
    assert!(local_status(&f).0);
    f.start();
    f.stop();
}

#[test]
fn unsafe_sqlite_files_refuse_all_effect_commands_before_source_access() {
    use std::os::unix::fs::symlink;
    let exe = std::env::var("FILE_MOVER_TEST_EXECUTABLE").unwrap();
    for suffix in ["", "-wal", "-shm", "-journal"] {
        for case in ["symlink", "hardlink", "writable"] {
            let f = Fixture::uninitialized(300);
            let database = f.root.join("state/jobs.sqlite");
            if !suffix.is_empty() {
                std::fs::write(&database, b"original database").unwrap();
            }
            let candidate = database.with_file_name(format!("jobs.sqlite{suffix}"));
            let original = f.root.join("original");
            std::fs::write(&original, b"original content").unwrap();
            match case {
                "symlink" => symlink(&original, &candidate).unwrap(),
                "hardlink" => std::fs::hard_link(&original, &candidate).unwrap(),
                _ => {
                    std::fs::write(&candidate, b"unsafe content").unwrap();
                    std::fs::set_permissions(&candidate, std::fs::Permissions::from_mode(0o666))
                        .unwrap();
                }
            }
            let path = f.root.join("config.json");
            let mut c: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            c["source_root"] = json!(f.root.join("missing-source"));
            std::fs::write(&path, serde_json::to_vec(&c).unwrap()).unwrap();
            for mode in [None, Some("--initialize-source"), Some("--transfer-one")] {
                let mut command = Command::new(&exe);
                if let Some(mode) = mode {
                    command.arg(mode);
                }
                command.arg(&path);
                if mode == Some("--transfer-one") {
                    command.arg("1");
                }
                let mut child = command
                    .stdout(Stdio::null())
                    .stderr(Stdio::piped())
                    .spawn()
                    .unwrap();
                let until = Instant::now() + Duration::from_secs(4);
                while child.try_wait().unwrap().is_none() {
                    if Instant::now() > until {
                        child.kill().unwrap();
                        child.wait().unwrap();
                        panic!("state refusal blocked");
                    }
                    std::thread::sleep(Duration::from_millis(10));
                }
                let output = child.wait_with_output().unwrap();
                assert!(!output.status.success());
                assert!(
                    String::from_utf8_lossy(&output.stderr).contains("unsafe SQLite state file"),
                    "{output:?}"
                );
                assert_eq!(std::fs::read(&original).unwrap(), b"original content");
                assert!(!f.root.join("missing-source").exists());
                assert!(!f.root.join("state/control.sock").exists());
                if !suffix.is_empty() {
                    assert_eq!(std::fs::read(&database).unwrap(), b"original database");
                }
            }
        }
    }
}
#[test]
fn private_sqlite_files_recover_original_wal_after_coordinator_death() {
    let mut f = Fixture::new(300);
    f.write("data", b"retained across SQLite recovery");
    let body = f.input("state-recovery", json!([{"name":"data"}]));
    assert_eq!(f.post(&body).0, 202);
    for suffix in ["", "-wal", "-shm"] {
        assert_eq!(
            std::fs::metadata(f.root.join(format!("state/jobs.sqlite{suffix}")))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }
    let mut child = f.child.take().unwrap();
    child.kill().unwrap();
    child.wait().unwrap();
    assert!(f.root.join("state/jobs.sqlite-wal").exists());
    f.start();
    assert_eq!(f.post(&body).0, 202);
    assert_eq!(retention(&f, None).1["details"]["retained_jobs"], 1);
    f.stop();
    // Earlier private-directory databases may be 0644. Preserve their mode.
    let database = f.root.join("state/jobs.sqlite");
    std::fs::set_permissions(&database, std::fs::Permissions::from_mode(0o644)).unwrap();
    f.start();
    assert_eq!(f.post(&body).0, 202);
    f.stop();
    assert_eq!(
        std::fs::metadata(&database).unwrap().permissions().mode() & 0o777,
        0o644
    );
}

#[test]
fn nfs_profile_configuration_is_explicit_and_cannot_downgrade_to_local() {
    let base = json!({"bind":"127.0.0.1:0","generator_id":"g","source_root":"/source",
        "destination_root":"/destination","state_database":"/state/jobs.sqlite",
        "source_binding":binding(),"destination_binding":destination_binding()});
    for role in ["source_binding", "destination_binding"] {
        let mut value = base.clone();
        value[role]["filesystem"] = json!("nfs");
        assert!(
            serde_json::from_value::<file_mover::Config>(value.clone())
                .unwrap()
                .validate()
                .is_err()
        );
        value[role]["nfs_mount"] = json!({"profile":"NMP-41B","mountpoint":"/share",
            "source":"192.0.2.1:/export","addr":"192.0.2.1"});
        assert!(
            serde_json::from_value::<file_mover::Config>(value.clone())
                .unwrap()
                .validate()
                .is_ok()
        );
        value[role]["filesystem"] = json!("local");
        assert!(
            serde_json::from_value::<file_mover::Config>(value.clone())
                .unwrap()
                .validate()
                .is_err()
        );
        value[role]["filesystem"] = json!("nfs");
        value[role]["nfs_mount"]["profile"] = json!("unknown");
        assert!(serde_json::from_value::<file_mover::Config>(value).is_err());
    }
}
