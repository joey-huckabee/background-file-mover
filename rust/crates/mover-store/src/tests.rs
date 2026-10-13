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
            .execute_batch("DROP TABLE claims; PRAGMA user_version=1;")
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
