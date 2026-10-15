use super::*;
use mover_core::Handoff;
use std::sync::{
    Arc,
    atomic::{AtomicU64, Ordering},
};

#[test]
fn schema_one_migrates_without_losing_accepted_jobs() {
    let fixture = Fixture::new();
    {
        let mut db = Database::open(&fixture.db(), false).unwrap();
        db.accept(&input("a", "old", "data"), &context()).unwrap();
        db.connection
            .execute_batch("DROP TABLE source_enrollment; DROP TABLE missing_resets; DROP TABLE operator_resumes; DROP TABLE delivery_failures; DROP TABLE manifests; DROP TABLE metadata; DROP TABLE transfers; DROP TABLE missing; DROP TABLE claims; PRAGMA user_version=1;")
            .unwrap();
    }
    assert!(matches!(
        Store::open_read_only(fixture.db()),
        Err(StoreError::UnsupportedSchema)
    ));
    let store = Store::open(fixture.db()).unwrap();
    let replay = store
        .accept(&input("a", "old", "data"), &context())
        .unwrap();
    assert!(replay.replay);
    assert_eq!(replay.recording.handoff(), Handoff::Pending);
    assert!(store.claim_intent(replay.job_id, 0).unwrap().is_none());
    assert!(
        store
            .accept(&input("b", "new", "data"), &context())
            .is_err()
    );
}

static NEXT: AtomicU64 = AtomicU64::new(0);

#[test]
fn source_enrollment_is_durable_and_never_rebound() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    s.enroll_source("/mnt/recordings", "binding-v1", "observation-v1")
        .unwrap();
    let job = s
        .accept(&input("g", "enrolled", "data"), &context())
        .unwrap();
    drop(s);
    let s = Store::open(f.db()).unwrap();
    s.enroll_source("/mnt/recordings", "binding-v1", "observation-v1")
        .unwrap();
    for (path, binding, observation) in [
        ("/other", "binding-v1", "observation-v1"),
        ("/mnt/recordings", "foreign", "observation-v1"),
        ("/mnt/recordings", "binding-v1", "replaced"),
    ] {
        assert!(matches!(
            s.enroll_source(path, binding, observation),
            Err(StoreError::SourceRootChanged)
        ));
    }
    assert_eq!(s.get(job.job_id).unwrap().unwrap().recording, job.recording);
    s.enroll_source("/mnt/recordings", "binding-v1", "observation-v1")
        .unwrap();
    let mut other = context();
    other.source_root_path = "/other".into();
    assert!(matches!(
        s.accept(&input("g", "other-root", "other-data"), &other),
        Err(StoreError::SourceRootChanged)
    ));
}
#[test]
fn schema_seven_jobs_require_explicit_enrollment_without_losing_jobs() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let job = s.accept(&input("g", "legacy", "data"), &context()).unwrap();
    drop(s);
    let c = Connection::open(f.db()).unwrap();
    c.execute_batch("DROP TABLE source_enrollment; PRAGMA user_version=7;")
        .unwrap();
    drop(c);
    let s = Store::open(f.db()).unwrap();
    assert!(matches!(
        s.enroll_source("/source", "binding-v1", "observed"),
        Err(StoreError::SourceEnrollmentRequired)
    ));
    assert_eq!(s.get(job.job_id).unwrap().unwrap().recording, job.recording);
    assert_eq!(s.job_count().unwrap(), 1);
}
#[test]
fn schema_seven_empty_state_can_enroll_after_migration() {
    let f = Fixture::new();
    drop(Store::open(f.db()).unwrap());
    let c = Connection::open(f.db()).unwrap();
    c.execute_batch("DROP TABLE source_enrollment; PRAGMA user_version=7;")
        .unwrap();
    drop(c);
    let s = Store::open(f.db()).unwrap();
    s.enroll_source("/source", "binding-v1", "observed")
        .unwrap();
    assert_eq!(s.job_count().unwrap(), 0);
}

#[test]
fn retention_reports_pending_observations_without_truncating_large_totals() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let empty = s.retention(None).unwrap().unwrap();
    assert_eq!(empty.jobs, 0);
    assert_eq!(empty.source_reserved_bytes, 0);
    assert!(s.retention(Some(999)).unwrap().is_none());
    let j = ready_job(&s);
    let pending = s
        .accept(&input("h", "pending-retention", "other"), &context())
        .unwrap();
    s.begin_claim(&intent_for(&pending, 0, u64::MAX)).unwrap();
    s.configure_limits(2, u64::MAX).unwrap();
    let r = s.retention(None).unwrap().unwrap();
    assert_eq!(r.jobs, 2);
    assert_eq!(r.source_claims, 3);
    assert_eq!(r.confirmed_claims, 2);
    assert_eq!(r.unmeasured_files, 1);
    assert_eq!(r.source_reserved_bytes, 2 * u128::from(u64::MAX) + 3);
    assert_eq!(r.destination_reserved_bytes, 0);
    assert_eq!(r.configured_limits, Some((2, u64::MAX)));
    assert!(matches!(
        s.claim_capacity(0),
        Err(StoreError::AdmissionFull)
    ));
    let one = s.retention(Some(j.job_id)).unwrap().unwrap();
    assert_eq!(one.jobs, 1);
    assert_eq!(one.source_reserved_bytes, u128::from(u64::MAX) + 3);
    drop(s);
    let s = Store::open_read_only(f.db()).unwrap();
    let r = s.retention(None).unwrap().unwrap();
    assert_eq!(r.source_reserved_bytes, 2 * u128::from(u64::MAX) + 3);
    assert!(r.configured_limits.is_none());
}
#[test]
fn retention_counts_old_attempts_and_committed_sources_without_releasing_capacity() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let mut c = context();
    c.policy.group_by_generator = false;
    let input = Submission::new(
        "g",
        "attempts",
        "/mnt/recordings/current",
        vec![FileSpec::new("data", None).unwrap()],
    )
    .unwrap();
    let j = s.accept(&input, &c).unwrap();
    let intent = intent_for(&j, 0, 3);
    s.begin_claim(&intent).unwrap();
    s.finish_claim(&intent).unwrap();
    let mut t = Transfer {
        job_id: j.job_id,
        file_index: 0,
        attempt: 1,
        destination_root: c.destination_path,
        relative_name: "data".into(),
        root: intent.root.clone(),
        area: intent.area.clone(),
        parent: intent.parent.clone(),
        staging_directory: intent.area.clone(),
        stage: ObjectIdentity {
            size: 0,
            ..intent.source.clone()
        },
        sha256: None,
        phase: TransferPhase::Intent,
    };
    s.save_transfer(&t).unwrap();
    t.attempt = 2;
    t.stage.inode += 1;
    s.save_transfer(&t).unwrap();
    t.stage.size = 3;
    t.sha256 = Some("a".repeat(64));
    for phase in [
        TransferPhase::Copied,
        TransferPhase::Verified,
        TransferPhase::PublishIntent,
        TransferPhase::Published,
    ] {
        t.phase = phase;
        s.save_transfer(&t).unwrap();
    }
    let mut m = ManifestRecord {
        job_id: j.job_id,
        bytes: "trusted worker receipt".into(),
        sha256: "b".repeat(64),
        phase: 0,
        object: None,
    };
    s.save_manifest(&m).unwrap();
    m.phase = 1;
    m.object = Some(ObjectIdentity {
        size: 0,
        ..intent.source.clone()
    });
    s.save_manifest(&m).unwrap();
    m.object.as_mut().unwrap().size = m.bytes.len() as u64;
    for phase in 2..=4 {
        m.phase = phase;
        s.save_manifest(&m).unwrap();
    }
    s.configure_limits(1, 6).unwrap();
    let r = s.retention(Some(j.job_id)).unwrap().unwrap();
    assert_eq!(r.committed_jobs, 1);
    assert_eq!(r.source_reserved_bytes, 3);
    assert_eq!(r.destination_reserved_bytes, 6);
    assert_eq!(r.destination_attempts_by_phase, [1, 0, 0, 0, 1]);
    assert!(matches!(
        s.transfer_capacity(j.job_id, 0),
        Err(StoreError::AdmissionFull)
    ));
    drop(s);
    let s = Store::open_read_only(f.db()).unwrap();
    assert_eq!(
        s.retention(None)
            .unwrap()
            .unwrap()
            .destination_reserved_bytes,
        6
    );
}

fn reset_request(epoch: u32) -> MissingResetRequest {
    MissingResetRequest {
        command_id: format!("reset-{epoch}"),
        review_epoch: epoch,
        file_index: 1,
        retry_window_seconds: 10,
        actor: "test-operator".into(),
        reason: "Confirmed recorder still owns the missing entry".into(),
    }
}
#[test]
fn schema_six_migration_preserves_delivery_audit_and_missing_deadlines() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let complete = ready_job(&s);
    review(&s, complete.job_id);
    s.resume_delivery(complete.job_id, &resume_request(0), 120)
        .unwrap();
    let pending = s
        .accept(&input("g", "pending", "other"), &context())
        .unwrap();
    s.note_missing(pending.job_id, 1, 100).unwrap();
    let instance = s.instance_id().unwrap();
    drop(s);
    let c = Connection::open(f.db()).unwrap();
    c.execute_batch(
        "DROP TABLE source_enrollment; DROP TABLE missing_resets; PRAGMA user_version=6;",
    )
    .unwrap();
    drop(c);
    assert!(matches!(
        Store::open_read_only(f.db()),
        Err(StoreError::UnsupportedSchema)
    ));
    let s = Store::open(f.db()).unwrap();
    assert_eq!(s.instance_id().unwrap(), instance);
    assert_eq!(s.status(complete.job_id).unwrap().unwrap().review_epoch, 1);
    let p = s.status(pending.job_id).unwrap().unwrap();
    assert_eq!(p.missing, vec![(1, 400, false)]);
    assert_eq!(p.missing_review_epoch, 0);
}
#[test]
fn missing_reset_preserves_claims_reservations_and_old_replays_do_not_extend_deadlines() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = s
        .accept(&input("g", "pending", "data"), &context())
        .unwrap();
    let intent = intent_for(&j, 0, 3);
    s.begin_claim(&intent).unwrap();
    s.finish_claim(&intent).unwrap();
    s.note_missing(j.job_id, 1, 100).unwrap();
    let r = reset_request(0);
    let receipt = s.reset_missing(j.job_id, &r, 400).unwrap();
    assert_eq!(receipt.new_deadline, 410);
    assert!(!receipt.replay);
    assert_eq!(s.claim_intent(j.job_id, 0).unwrap(), Some((intent, true)));
    let c = Connection::open(f.db()).unwrap();
    assert_eq!(
        c.query_row(
            "SELECT count(*) FROM reservations WHERE job_id=?1",
            [j.job_id],
            |r| r.get::<_, i64>(0)
        )
        .unwrap(),
        2
    );
    assert!(!s.claim_blocked(j.job_id, 409).unwrap());
    assert!(s.claim_blocked(j.job_id, 410).unwrap());
    drop(s);
    let s = Store::open(f.db()).unwrap();
    let replay = s.reset_missing(j.job_id, &r, 500).unwrap();
    assert!(replay.replay);
    assert_eq!(replay.new_deadline, 410);
    assert!(s.claim_blocked(j.job_id, 500).unwrap());
    let mut stale = r.clone();
    stale.command_id = "different-stale".into();
    assert!(matches!(
        s.reset_missing(j.job_id, &stale, 500),
        Err(StoreError::ReviewConflict)
    ));
    let mut conflict = r.clone();
    conflict.retry_window_seconds = 20;
    assert!(matches!(
        s.reset_missing(j.job_id, &conflict, 500),
        Err(StoreError::ActionConflict)
    ));
    let a = s
        .status(j.job_id)
        .unwrap()
        .unwrap()
        .latest_missing_reset
        .unwrap();
    assert_eq!(a.prior_deadline, 400);
    assert!(!a.prior_blocked);
    assert_eq!(a.recorded_at, 400);
    s.reset_missing(j.job_id, &reset_request(1), 500).unwrap();
    assert!(!s.claim_blocked(j.job_id, 509).unwrap());
    assert_eq!(s.status(j.job_id).unwrap().unwrap().missing_review_epoch, 2);
}
#[test]
fn missing_reset_failure_rolls_back_audit_and_deadline_together() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = s
        .accept(&input("g", "pending", "data"), &context())
        .unwrap();
    s.note_missing(j.job_id, 1, 100).unwrap();
    let c = Connection::open(f.db()).unwrap();
    c.execute_batch("CREATE TRIGGER reject_deadline BEFORE UPDATE ON missing BEGIN SELECT RAISE(ABORT,'test rollback'); END;").unwrap();
    assert!(matches!(
        s.reset_missing(j.job_id, &reset_request(0), 400),
        Err(StoreError::Sqlite(_))
    ));
    let p = s.status(j.job_id).unwrap().unwrap();
    assert_eq!(p.missing, vec![(1, 400, false)]);
    assert_eq!(p.missing_review_epoch, 0);
    assert!(p.latest_missing_reset.is_none());
    c.execute_batch("DROP TRIGGER reject_deadline;").unwrap();
    assert!(
        !s.reset_missing(j.job_id, &reset_request(0), 400)
            .unwrap()
            .replay
    );
}
#[test]
fn missing_reset_checks_review_state_overflow_and_bounded_audit() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = s
        .accept(&input("g", "pending", "data"), &context())
        .unwrap();
    assert!(matches!(
        s.reset_missing(999, &reset_request(0), 100),
        Err(StoreError::NotFound)
    ));
    assert!(matches!(
        s.reset_missing(j.job_id, &reset_request(0), 100),
        Err(StoreError::ReviewConflict)
    ));
    s.note_missing(j.job_id, 1, 100).unwrap();
    assert!(matches!(
        s.reset_missing(j.job_id, &reset_request(0), 399),
        Err(StoreError::ReviewConflict)
    ));
    for seconds in [0, 86401] {
        let mut r = reset_request(0);
        r.retry_window_seconds = seconds;
        assert!(matches!(
            s.reset_missing(j.job_id, &r, 400),
            Err(StoreError::InvalidContext)
        ));
    }
    assert!(matches!(
        s.reset_missing(j.job_id, &reset_request(0), i64::MAX),
        Err(StoreError::InvalidContext)
    ));
    for epoch in 0..64 {
        s.reset_missing(j.job_id, &reset_request(epoch), 400 + 10 * i64::from(epoch))
            .unwrap();
    }
    assert!(matches!(
        s.reset_missing(j.job_id, &reset_request(64), 1040),
        Err(StoreError::AuditFull)
    ));
    assert!(
        s.reset_missing(j.job_id, &reset_request(63), 2000)
            .unwrap()
            .replay
    );
    assert_eq!(
        s.status(j.job_id).unwrap().unwrap().missing_review_epoch,
        64
    );
}

fn ready_job(s: &Store) -> Accepted {
    let j = s
        .accept(&input("g", "operator", "data"), &context())
        .unwrap();
    for i in 0..2 {
        let intent = intent_for(&j, i, if i == 0 { 3 } else { u64::MAX });
        s.begin_claim(&intent).unwrap();
        s.finish_claim(&intent).unwrap();
    }
    s.get(j.job_id).unwrap().unwrap()
}
fn review(s: &Store, id: i64) {
    for time in [100, 105, 110] {
        s.delivery_failed(id, time).unwrap();
    }
}
fn resume_request(epoch: u32) -> ResumeRequest {
    ResumeRequest {
        command_id: format!("cmd-{epoch}"),
        review_epoch: epoch,
        actor: "test-operator".into(),
        reason: "Inspected retained custody".into(),
    }
}
#[test]
fn schema_five_migration_preserves_claims_instance_and_review() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = ready_job(&s);
    review(&s, j.job_id);
    let instance = s.instance_id().unwrap();
    drop(s);
    let c = Connection::open(f.db()).unwrap();
    c.execute_batch(
        "DROP TABLE source_enrollment; DROP TABLE missing_resets; DROP TABLE operator_resumes; PRAGMA user_version=5;",
    )
    .unwrap();
    drop(c);
    assert!(matches!(
        Store::open_read_only(f.db()),
        Err(StoreError::UnsupportedSchema)
    ));
    let s = Store::open(f.db()).unwrap();
    let status = s.status(j.job_id).unwrap().unwrap();
    assert_eq!(s.instance_id().unwrap(), instance);
    assert_eq!(status.review_epoch, 0);
    assert_eq!(status.delivery.unwrap().0, 3);
    assert_eq!(status.job.recording.handoff(), Handoff::Ready202);
}
#[test]
fn operator_resume_is_audited_idempotent_and_rejects_stale_review_epochs() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = ready_job(&s);
    let request = resume_request(0);
    assert!(matches!(
        s.resume_delivery(j.job_id, &request, 115),
        Err(StoreError::ReviewConflict)
    ));
    review(&s, j.job_id);
    assert_eq!(
        s.resume_delivery(j.job_id, &request, 115).unwrap(),
        ResumeReceipt {
            review_epoch: 1,
            replay: false
        }
    );
    assert_eq!(s.delivery_candidates(115, 1).unwrap(), vec![j.job_id]);
    drop(s);
    let s = Store::open(f.db()).unwrap();
    review(&s, j.job_id);
    assert!(s.resume_delivery(j.job_id, &request, 999).unwrap().replay);
    assert!(s.delivery_candidates(999, 1).unwrap().is_empty());
    let mut stale = request.clone();
    stale.command_id = "new-but-stale".into();
    assert!(matches!(
        s.resume_delivery(j.job_id, &stale, 999),
        Err(StoreError::ReviewConflict)
    ));
    let mut conflict = request.clone();
    conflict.reason = "different".into();
    assert!(matches!(
        s.resume_delivery(j.job_id, &conflict, 999),
        Err(StoreError::ActionConflict)
    ));
    let snapshot = s.status(j.job_id).unwrap().unwrap();
    let audit = snapshot.latest_resume.unwrap();
    assert_eq!(audit.recorded_at, 115);
    assert_eq!(audit.prior_retry_after, 115);
    assert_eq!(audit.reason, request.reason);
    assert_eq!(audit.actor, request.actor);
    assert_eq!(snapshot.review_epoch, 1);
    assert_eq!(snapshot.delivery.unwrap().0, 3);
    assert_eq!(
        s.resume_delivery(j.job_id, &resume_request(1), 1000)
            .unwrap()
            .review_epoch,
        2
    );
}
#[test]
fn operator_resume_rolls_back_audit_and_retry_reset_together() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = ready_job(&s);
    review(&s, j.job_id);
    let c = Connection::open(f.db()).unwrap();
    c.execute_batch("CREATE TRIGGER reject_reset BEFORE DELETE ON delivery_failures BEGIN SELECT RAISE(ABORT,'test rollback'); END;").unwrap();
    assert!(matches!(
        s.resume_delivery(j.job_id, &resume_request(0), 115),
        Err(StoreError::Sqlite(_))
    ));
    let snapshot = s.status(j.job_id).unwrap().unwrap();
    assert_eq!(snapshot.review_epoch, 0);
    assert!(snapshot.latest_resume.is_none());
    assert_eq!(snapshot.delivery.unwrap().0, 3);
    c.execute_batch("DROP TRIGGER reject_reset;").unwrap();
    assert!(
        !s.resume_delivery(j.job_id, &resume_request(0), 116)
            .unwrap()
            .replay
    );
}
#[test]
fn operator_resume_bounds_audit_retention_and_rejects_invalid_commands() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    let j = ready_job(&s);
    assert!(matches!(
        s.resume_delivery(999, &resume_request(0), 100),
        Err(StoreError::NotFound)
    ));
    for bad in ["", " ", "line\nfeed"] {
        let mut r = resume_request(0);
        r.reason = bad.into();
        assert!(matches!(
            s.resume_delivery(j.job_id, &r, 100),
            Err(StoreError::InvalidContext)
        ));
    }
    for epoch in 0..64 {
        review(&s, j.job_id);
        s.resume_delivery(j.job_id, &resume_request(epoch), 120)
            .unwrap();
    }
    review(&s, j.job_id);
    let mut r = resume_request(64);
    r.command_id = "overflow".into();
    assert!(matches!(
        s.resume_delivery(j.job_id, &r, 120),
        Err(StoreError::AuditFull)
    ));
    assert!(
        s.resume_delivery(j.job_id, &resume_request(63), 121)
            .unwrap()
            .replay
    );
    assert_eq!(s.status(j.job_id).unwrap().unwrap().review_epoch, 64);
}

#[test]
fn status_snapshot_preserves_deadlines_review_and_claims_across_restart() {
    let f = Fixture::new();
    let s = Store::open(f.db()).unwrap();
    assert!(s.status(999).unwrap().is_none());
    let job = s.accept(&input("g", "status", "data"), &context()).unwrap();
    s.note_missing(job.job_id, 0, 100).unwrap();
    let before = s.status(job.job_id).unwrap().unwrap();
    assert_eq!(before.job.recording.handoff(), Handoff::Pending);
    assert!(!before.missing[0].2);
    let deadline = before.missing[0].1;
    // Observation does not persist expiry or change admission/retry state.
    assert_eq!(
        s.status(job.job_id).unwrap().unwrap().missing,
        before.missing
    );
    assert!(s.claim_blocked(job.job_id, deadline).unwrap());
    for t in [100, 105, 110] {
        s.delivery_failed(job.job_id, t).unwrap();
    }
    drop(s);
    let s = Store::open_read_only(f.db()).unwrap();
    let after = s.status(job.job_id).unwrap().unwrap();
    assert_eq!(after.missing, vec![(0, deadline, true)]);
    assert_eq!(
        after.delivery,
        Some((3, 115, "delivery_requires_review".into()))
    );
    assert!(after.transfers.iter().all(Option::is_none));
    assert!(after.manifest_phase.is_none());
}

#[test]
fn coordination_migration_preserves_instance_and_bounded_delivery_retries() {
    let f = Fixture::new();
    let mut db = Database::open(&f.db(), false).unwrap();
    let job = db.accept(&input("g", "old", "data"), &context()).unwrap();
    db.connection.execute_batch("DROP TABLE source_enrollment; DROP TABLE missing_resets; DROP TABLE operator_resumes; DROP TABLE delivery_failures; DROP TABLE manifests; DROP TABLE metadata; PRAGMA user_version=4;").unwrap();
    drop(db);
    let s = Store::open(f.db()).unwrap();
    let instance = s.instance_id().unwrap();
    assert_eq!(instance.len(), 32);
    assert!(s.delivery_candidates(100, 1).unwrap().is_empty());
    s.begin_claim(&intent_for(&job, 0, 3)).unwrap();
    s.finish_claim(&intent_for(&job, 0, 3)).unwrap();
    s.begin_claim(&intent_for(&job, 1, u64::MAX)).unwrap();
    s.finish_claim(&intent_for(&job, 1, u64::MAX)).unwrap();
    assert_eq!(s.delivery_candidates(100, 1).unwrap(), vec![job.job_id]);
    s.delivery_deferred(job.job_id, 100).unwrap();
    assert!(s.delivery_candidates(104, 1).unwrap().is_empty());
    assert_eq!(s.delivery_candidates(105, 1).unwrap(), vec![job.job_id]);
    for time in [105, 110, 115] {
        s.delivery_failed(job.job_id, time).unwrap();
    }
    assert!(s.delivery_candidates(1000, 1).unwrap().is_empty());
    drop(s);
    let s = Store::open(f.db()).unwrap();
    assert_eq!(s.instance_id().unwrap(), instance);
    assert!(s.delivery_candidates(1000, 1).unwrap().is_empty());
}

#[test]
fn schema_three_migration_retains_claim_evidence() {
    let f = Fixture::new();
    let mut db = Database::open(&f.db(), false).unwrap();
    let job = db.accept(&input("g", "old", "data"), &context()).unwrap();
    let intent = intent_for(&job, 0, 7);
    db.begin_claim(&intent).unwrap();
    db.finish_claim(&intent).unwrap();
    db.connection
        .execute_batch("DROP TABLE source_enrollment; DROP TABLE missing_resets; DROP TABLE operator_resumes; DROP TABLE delivery_failures; DROP TABLE manifests; DROP TABLE metadata; DROP TABLE transfers; PRAGMA user_version=3;")
        .unwrap();
    drop(db);
    assert!(matches!(
        Store::open_read_only(f.db()),
        Err(StoreError::UnsupportedSchema)
    ));
    let s = Store::open(f.db()).unwrap();
    assert_eq!(s.claim_intent(job.job_id, 0).unwrap().unwrap().0, intent);
    assert!(s.transfer(job.job_id, 0).unwrap().is_none());
}

#[test]
fn transfer_phase_skips_and_failed_commit_cannot_advance_publication() {
    let f = Fixture::new();
    let mut db = Database::open(&f.db(), false).unwrap();
    let mut c = context();
    c.policy.group_by_generator = false;
    let input = Submission::new(
        "g",
        "one",
        "/mnt/recordings/current",
        vec![FileSpec::new("data", None).unwrap()],
    )
    .unwrap();
    let job = db.accept(&input, &c).unwrap();
    let intent = intent_for(&job, 0, 3);
    db.begin_claim(&intent).unwrap();
    db.finish_claim(&intent).unwrap();
    let mut t = Transfer {
        job_id: job.job_id,
        file_index: 0,
        attempt: 1,
        destination_root: c.destination_path,
        relative_name: "data".into(),
        root: intent.root.clone(),
        area: intent.area.clone(),
        parent: intent.parent.clone(),
        staging_directory: intent.area.clone(),
        stage: mover_core::ObjectIdentity {
            size: 0,
            ..intent.source
        },
        sha256: None,
        phase: TransferPhase::Intent,
    };
    db.save_transfer(&t).unwrap();
    t.stage.size = 3;
    t.sha256 = Some("a".repeat(64));
    t.phase = TransferPhase::Verified;
    assert!(db.save_transfer(&t).is_err());
    t.phase = TransferPhase::Copied;
    db.connection.execute_batch("CREATE TRIGGER refuse_transfer BEFORE UPDATE ON transfers BEGIN SELECT RAISE(ABORT,'receipt failure'); END;").unwrap();
    assert!(db.save_transfer(&t).is_err());
    assert_eq!(
        load_transfer(&db.connection, job.job_id, 0)
            .unwrap()
            .unwrap()
            .phase,
        TransferPhase::Intent
    );
    db.connection
        .execute_batch("DROP TRIGGER refuse_transfer")
        .unwrap();
    db.save_transfer(&t).unwrap();
    t.phase = TransferPhase::Verified;
    db.save_transfer(&t).unwrap();
    t.phase = TransferPhase::PublishIntent;
    db.save_transfer(&t).unwrap();
    t.phase = TransferPhase::Published;
    db.save_transfer(&t).unwrap();
    drop(db);
    assert_eq!(
        Store::open(f.db())
            .unwrap()
            .get(job.job_id)
            .unwrap()
            .unwrap()
            .recording
            .file_phase(0),
        Some(mover_core::FilePhase::Published)
    );
}

#[test]
fn missing_deadline_survives_restart_replay_and_clock_rollback() {
    let f = Fixture::new();
    let store = Store::open(f.db()).unwrap();
    let job = store
        .accept(&input("g", "missing", "data"), &context())
        .unwrap();
    assert!(!store.note_missing(job.job_id, 0, 100).unwrap());
    assert!(!store.note_missing(job.job_id, 0, 150).unwrap());
    drop(store);
    let store = Store::open(f.db()).unwrap();
    store
        .accept(&input("g", "missing", "data"), &context())
        .unwrap();
    assert!(!store.claim_blocked(job.job_id, 399).unwrap());
    assert!(store.claim_blocked(job.job_id, 400).unwrap());
    assert!(store.claim_blocked(job.job_id, 100).unwrap());
    assert!(store.note_missing(job.job_id, 0, 500).unwrap());
}

#[test]
fn schema_two_migration_preserves_partial_claims() {
    let f = Fixture::new();
    let mut db = Database::open(&f.db(), false).unwrap();
    let job = db.accept(&input("g", "old", "data"), &context()).unwrap();
    let intent = intent_for(&job, 0, 7);
    db.begin_claim(&intent).unwrap();
    db.finish_claim(&intent).unwrap();
    db.connection
        .execute_batch("DROP TABLE source_enrollment; DROP TABLE missing_resets; DROP TABLE operator_resumes; DROP TABLE delivery_failures; DROP TABLE manifests; DROP TABLE metadata; DROP TABLE transfers; DROP TABLE missing; PRAGMA user_version=2;")
        .unwrap();
    drop(db);
    let store = Store::open(f.db()).unwrap();
    let job = store.get(job.job_id).unwrap().unwrap();
    assert_eq!(
        job.recording.file_phase(0),
        Some(mover_core::FilePhase::Claimed)
    );
    assert_eq!(job.recording.handoff(), Handoff::Pending);
    assert!(!store.note_missing(job.job_id, 1, 100).unwrap());
}

fn intent_for(job: &Accepted, index: usize, size: u64) -> ClaimIntent {
    let identity = ObjectIdentity {
        device: 1,
        inode: 2,
        uid: 1000,
        size,
        modified_seconds: 1,
        modified_nanos: 0,
        links: 1,
    };
    ClaimIntent {
        job_id: job.job_id,
        file_index: index,
        root_path: job.context.source_root_path.clone(),
        source_name: job
            .context
            .source_name(&job.recording.submission().files()[index]),
        private_name: format!("{}-{index}", job.job_id),
        root: identity.clone(),
        parent: identity.clone(),
        area: identity.clone(),
        source: identity,
    }
}

#[test]
fn failed_last_receipt_rolls_back_claim_fact_and_reservation_release() {
    let f = Fixture::new();
    let mut db = Database::open(&f.db(), false).unwrap();
    let job = db.accept(&input("a", "one", "data"), &context()).unwrap();
    let first = intent_for(&job, 0, 7);
    let last = intent_for(&job, 1, u64::MAX);
    db.begin_claim(&first).unwrap();
    db.finish_claim(&first).unwrap();
    db.begin_claim(&last).unwrap();
    db.connection.execute_batch("CREATE TRIGGER refuse_release BEFORE DELETE ON reservations BEGIN SELECT RAISE(ABORT,'injected release failure'); END;").unwrap();
    assert!(db.finish_claim(&last).is_err());
    assert!(
        !load_claim(&db.connection, job.job_id, 1)
            .unwrap()
            .unwrap()
            .1
    );
    assert_eq!(
        load(&db.connection, job.job_id)
            .unwrap()
            .unwrap()
            .recording
            .handoff(),
        Handoff::Pending
    );
    assert_eq!(
        db.connection
            .query_row("SELECT count(*) FROM reservations", [], |r| r
                .get::<_, i64>(0))
            .unwrap(),
        2
    );
    db.connection
        .execute_batch("DROP TRIGGER refuse_release")
        .unwrap();
    assert_eq!(
        db.finish_claim(&last).unwrap().recording.handoff(),
        Handoff::Ready202
    );
    drop(db);
    assert_eq!(
        Store::open(f.db())
            .unwrap()
            .get(job.job_id)
            .unwrap()
            .unwrap()
            .recording
            .handoff(),
        Handoff::Ready202
    );
}

#[test]
fn damaged_claim_identity_blocks_startup() {
    let f = Fixture::new();
    let mut db = Database::open(&f.db(), false).unwrap();
    let job = db.accept(&input("a", "one", "data"), &context()).unwrap();
    db.begin_claim(&intent_for(&job, 0, 7)).unwrap();
    db.connection
        .execute("UPDATE claims SET source_identity='foreign'", [])
        .unwrap();
    drop(db);
    assert!(matches!(Store::open(f.db()), Err(StoreError::CorruptState)));
}
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        loop {
            let path = std::env::temp_dir().join(format!(
                "file-mover-store-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match std::fs::create_dir(&path) {
                Ok(()) => return Self(path),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => panic!("fixture: {error}"),
            }
        }
    }
    fn db(&self) -> PathBuf {
        self.0.join("state.sqlite")
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}

fn input(generator: &str, id: &str, name: &str) -> Submission {
    Submission::new(
        generator,
        id,
        "/mnt/recordings/current",
        vec![
            FileSpec::new(name, None).unwrap(),
            FileSpec::new("telemetry/events", Some(u64::MAX)).unwrap(),
        ],
    )
    .unwrap()
}
fn context() -> AcceptanceContext {
    AcceptanceContext {
        source_root_id: "recordings".into(),
        source_root_path: "/mnt/recordings".into(),
        source_relative_directory: "current".into(),
        destination_path: "/mnt/archive".into(),
        policy: DeliveryPolicy {
            destination_id: "archive".into(),
            group_by_generator: true,
            delete_source_after_commit: false,
        },
        missing_retry_seconds: 300,
    }
}
fn sqlite_code(error: &StoreError) -> Option<rusqlite::ErrorCode> {
    match error {
        StoreError::Sqlite(rusqlite::Error::SqliteFailure(error, _)) => Some(error.code),
        _ => None,
    }
}

#[test]
fn qualified_sqlite_options_and_durable_settings() {
    let fixture = Fixture::new();
    let db = Database::open(&fixture.db(), false).unwrap();
    assert_eq!(rusqlite::version(), "3.53.2");
    let mode: String = db
        .connection
        .pragma_query_value(None, "journal_mode", |r| r.get(0))
        .unwrap();
    assert_eq!(mode, "wal");
    for (name, value) in [
        ("synchronous", 2),
        ("foreign_keys", 1),
        ("user_version", SCHEMA_VERSION),
        ("application_id", APPLICATION_ID),
    ] {
        let actual: i64 = db
            .connection
            .pragma_query_value(None, name, |r| r.get(0))
            .unwrap();
        assert_eq!(actual, value);
    }
    assert!(
        db.connection
            .query_row("SELECT \"not_a_column\"", [], |r| r.get::<_, String>(0))
            .is_err()
    );
    let extension = db
        .connection
        .query_row("SELECT load_extension('must-not-load')", [], |r| {
            r.get::<_, String>(0)
        })
        .unwrap_err();
    assert!(extension.to_string().contains("no such function"));
}

#[test]
fn acceptance_survives_reopen_without_authorizing_202() {
    let fixture = Fixture::new();
    let submission = input("a", "42", "video/camera");
    let saved = {
        let store = Store::open(fixture.db()).unwrap();
        store.accept(&submission, &context()).unwrap()
    };
    assert_eq!(saved.recording.handoff(), Handoff::Pending);
    let store = Store::open(fixture.db()).unwrap();
    assert_eq!(store.get(saved.job_id).unwrap(), Some(saved.clone()));
    assert_eq!(
        store.accept(&submission, &context()).unwrap().job_id,
        saved.job_id
    );
    assert_eq!(store.job_count().unwrap(), 1);
    assert_eq!(store.get(i64::MAX).unwrap(), None);
}

#[test]
fn replay_rejects_changed_details_and_keeps_original_context() {
    let fixture = Fixture::new();
    let store = Store::open(fixture.db()).unwrap();
    let submission = input("a", "42", "video/camera");
    let saved = store.accept(&submission, &context()).unwrap();
    let mut changed = context();
    changed.destination_path = "/mnt/new-archive".into();
    changed.policy.destination_id = "new-archive".into();
    changed.policy.group_by_generator = false;
    changed.policy.delete_source_after_commit = true;
    changed.missing_retry_seconds = 900;
    let replay = store.accept(&submission, &changed).unwrap();
    assert!(replay.replay);
    assert_eq!(replay.job_id, saved.job_id);
    assert_eq!(replay.context, saved.context);
    let changed_body = input("a", "42", "video/different");
    assert!(matches!(
        store.accept(&changed_body, &context()),
        Err(StoreError::Protocol(ProtocolError::ConflictingReplay))
    ));
    assert_eq!(store.job_count().unwrap(), 1);
}

#[test]
fn generator_scoped_ids_are_independent_when_sources_are_disjoint() {
    let fixture = Fixture::new();
    let store = Store::open(fixture.db()).unwrap();
    let first = store
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap();
    let mut other = context();
    other.source_relative_directory = "other".into();
    let second = store
        .accept(&input("b", "42", "video/camera"), &other)
        .unwrap();
    assert_ne!(first.job_id, second.job_id);
    assert_eq!(store.job_count().unwrap(), 2);
}

#[test]
fn source_reservations_survive_reopen_and_cross_generator_submissions() {
    let fixture = Fixture::new();
    {
        let store = Store::open(fixture.db()).unwrap();
        store
            .accept(&input("a", "42", "video/camera"), &context())
            .unwrap();
    }
    let store = Store::open(fixture.db()).unwrap();
    assert!(matches!(
        store.accept(&input("b", "43", "video/camera"), &context()),
        Err(StoreError::SourceReserved)
    ));
    let mut moved_root = context();
    moved_root.source_root_path = "/mnt/replaced".into();
    assert!(matches!(
        store.accept(&input("b", "44", "other"), &moved_root),
        Err(StoreError::SourceRootChanged)
    ));
    assert_eq!(store.job_count().unwrap(), 1);
}

#[test]
fn writer_lock_failure_does_not_accept_then_same_id_can_retry() {
    let fixture = Fixture::new();
    let store = Store::open(fixture.db()).unwrap();
    let blocker = Connection::open(fixture.db()).unwrap();
    blocker.execute_batch("BEGIN IMMEDIATE").unwrap();
    let request = input("a", "42", "video/camera");
    let error = store.accept(&request, &context()).unwrap_err();
    assert_eq!(sqlite_code(&error), Some(rusqlite::ErrorCode::DatabaseBusy));
    assert_eq!(store.job_count().unwrap(), 0);
    blocker.execute_batch("ROLLBACK").unwrap();
    assert!(!store.accept(&request, &context()).unwrap().replay);
}

#[test]
fn read_only_database_refuses_new_acceptance() {
    let fixture = Fixture::new();
    drop(Store::open(fixture.db()).unwrap());
    let store = Store::open_read_only(fixture.db()).unwrap();
    let error = store
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap_err();
    assert_eq!(sqlite_code(&error), Some(rusqlite::ErrorCode::ReadOnly));
    assert_eq!(store.job_count().unwrap(), 0);
}

#[test]
fn actual_commit_failure_rolls_back_job_files_and_reservations() {
    let fixture = Fixture::new();
    let mut db = Database::open(&fixture.db(), false).unwrap();
    // Inserts succeed. A real deferred FK violation fails COMMIT, exercising
    // the boundary at which acceptance would otherwise be acknowledged.
    db.connection.execute_batch("CREATE TABLE commit_guard(value INTEGER REFERENCES jobs(job_id) DEFERRABLE INITIALLY DEFERRED); CREATE TRIGGER fail_commit AFTER INSERT ON jobs BEGIN INSERT INTO commit_guard VALUES(-1); END;").unwrap();
    let error = db
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap_err();
    assert_eq!(
        sqlite_code(&error),
        Some(rusqlite::ErrorCode::ConstraintViolation)
    );
    assert!(db.connection.is_autocommit());
    for table in ["jobs", "files", "reservations", "commit_guard"] {
        let count: i64 = db
            .connection
            .query_row(&format!("SELECT count(*) FROM {table}"), [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 0);
    }
    db.connection
        .execute_batch("DROP TRIGGER fail_commit; DROP TABLE commit_guard;")
        .unwrap();
    drop(db);
    let store = Store::open(fixture.db()).unwrap();
    assert_eq!(store.job_count().unwrap(), 0);
    assert!(
        !store
            .accept(&input("a", "42", "video/camera"), &context())
            .unwrap()
            .replay
    );
}

#[test]
fn failure_mid_file_list_rolls_back_partial_acceptance() {
    let fixture = Fixture::new();
    let mut db = Database::open(&fixture.db(), false).unwrap();
    db.connection.execute_batch("CREATE TRIGGER fail_second_file BEFORE INSERT ON files WHEN NEW.file_index=1 BEGIN SELECT RAISE(ABORT,'injected second-file failure'); END;").unwrap();
    assert!(
        db.accept(&input("a", "42", "video/camera"), &context())
            .is_err()
    );
    for table in ["jobs", "files", "reservations"] {
        let count: i64 = db
            .connection
            .query_row(&format!("SELECT count(*) FROM {table}"), [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 0);
    }
    db.connection
        .execute_batch("DROP TRIGGER fail_second_file")
        .unwrap();
    assert!(
        db.accept(&input("a", "42", "video/camera"), &context())
            .is_ok()
    );
}

#[test]
fn incompatible_and_foreign_schemas_are_not_replaced() {
    let fixture = Fixture::new();
    {
        let db = Database::open(&fixture.db(), false).unwrap();
        db.connection
            .pragma_update(None, "user_version", 99)
            .unwrap();
    }
    assert!(matches!(
        Store::open(fixture.db()),
        Err(StoreError::UnsupportedSchema)
    ));
    let foreign = fixture.0.join("foreign.sqlite");
    {
        let db = Connection::open(&foreign).unwrap();
        db.execute_batch("CREATE TABLE valuable(value TEXT); INSERT INTO valuable VALUES('keep');")
            .unwrap();
    }
    assert!(matches!(
        Store::open(&foreign),
        Err(StoreError::UnsupportedSchema)
    ));
    let db = Connection::open(&foreign).unwrap();
    assert_eq!(
        db.query_row("SELECT value FROM valuable", [], |r| r.get::<_, String>(0))
            .unwrap(),
        "keep"
    );
}

#[test]
fn owner_thread_serializes_concurrent_replays() {
    let fixture = Fixture::new();
    let store = Arc::new(Store::open(fixture.db()).unwrap());
    let mut threads = Vec::new();
    for _ in 0..16 {
        let store = Arc::clone(&store);
        threads.push(thread::spawn(move || {
            store
                .accept(&input("a", "42", "video/camera"), &context())
                .unwrap()
        }));
    }
    let receipts: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert_eq!(receipts.iter().filter(|r| !r.replay).count(), 1);
    assert!(receipts.iter().all(|r| r.job_id == receipts[0].job_id));
    assert_eq!(store.job_count().unwrap(), 1);
}

#[test]
fn separate_process_reopens_committed_acceptance() {
    let fixture = Fixture::new();
    {
        let store = Store::open(fixture.db()).unwrap();
        store
            .accept(&input("a", "42", "video/camera"), &context())
            .unwrap();
    }
    let result = std::process::Command::new(std::env::current_exe().unwrap())
        .args([
            "--ignored",
            "--exact",
            "tests::child_reopens_committed_acceptance",
            "--test-threads=1",
        ])
        .env("FILE_MOVER_TEST_DB", fixture.db())
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(String::from_utf8_lossy(&result.stdout).contains("1 passed"));
}

#[test]
fn abrupt_exit_recovers_committed_work_from_uncheckpointed_wal() {
    let fixture = Fixture::new();
    let result = std::process::Command::new(std::env::current_exe().unwrap())
        .args([
            "--ignored",
            "--exact",
            "tests::child_reopens_committed_acceptance",
            "--test-threads=1",
        ])
        .env("FILE_MOVER_TEST_DB", fixture.db())
        .env("FILE_MOVER_TEST_ACCEPT_AND_EXIT", "1")
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(
        std::fs::metadata(fixture.0.join("state.sqlite-wal"))
            .unwrap()
            .len()
            > 32
    );
    let store = Store::open(fixture.db()).unwrap();
    let saved = store
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap();
    assert!(saved.replay);
    assert_eq!(store.job_count().unwrap(), 1);
    assert_eq!(saved.recording.handoff(), Handoff::Pending);
}

#[test]
fn incomplete_persisted_file_list_is_not_loaded_as_a_smaller_recording() {
    let fixture = Fixture::new();
    let mut db = Database::open(&fixture.db(), false).unwrap();
    let saved = db
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap();
    db.connection
        .execute(
            "DELETE FROM reservations WHERE job_id=?1 AND file_index=1",
            [saved.job_id],
        )
        .unwrap();
    db.connection
        .execute(
            "DELETE FROM files WHERE job_id=?1 AND file_index=1",
            [saved.job_id],
        )
        .unwrap();
    assert!(matches!(
        load(&db.connection, saved.job_id),
        Err(StoreError::CorruptState)
    ));
}

#[test]
fn invalid_source_context_does_not_reserve_or_accept() {
    let fixture = Fixture::new();
    let store = Store::open(fixture.db()).unwrap();
    let mut invalid = context();
    invalid.source_relative_directory = "../escape".into();
    assert!(
        store
            .accept(&input("a", "42", "video/camera"), &invalid)
            .is_err()
    );
    assert_eq!(store.job_count().unwrap(), 0);
    assert!(
        !store
            .accept(&input("a", "42", "video/camera"), &context())
            .unwrap()
            .replay
    );
}

#[test]
fn missing_reservation_blocks_startup_instead_of_allowing_a_second_owner() {
    let fixture = Fixture::new();
    let mut db = Database::open(&fixture.db(), false).unwrap();
    let saved = db
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap();
    db.connection
        .execute(
            "DELETE FROM reservations WHERE job_id=?1 AND file_index=0",
            [saved.job_id],
        )
        .unwrap();
    drop(db);
    assert!(matches!(
        Store::open(fixture.db()),
        Err(StoreError::CorruptState)
    ));
}

#[test]
#[ignore = "invoked by separate_process_reopens_committed_acceptance"]
fn child_reopens_committed_acceptance() {
    let path = std::env::var_os("FILE_MOVER_TEST_DB").expect("parent fixture");
    let store = Store::open(PathBuf::from(path)).unwrap();
    let saved = store
        .accept(&input("a", "42", "video/camera"), &context())
        .unwrap();
    if std::env::var_os("FILE_MOVER_TEST_ACCEPT_AND_EXIT").is_some() {
        assert!(!saved.replay);
        // Bypass Rust destructors, leaving the committed WAL uncheckpointed.
        std::process::exit(0);
    }
    assert!(saved.replay);
    assert_eq!(store.job_count().unwrap(), 1);
    assert_eq!(saved.recording.handoff(), Handoff::Pending);
}
