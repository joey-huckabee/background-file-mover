//! Display-only SQL. No command closures, effects, migrations or authorizations.
use super::*;
use std::{
    os::unix::fs::MetadataExt,
    sync::atomic::{AtomicBool, Ordering},
    time::Instant,
};

#[derive(Clone, PartialEq, Eq)]
struct FileIdentity {
    device: u64,
    inode: u64,
    uid: u32,
    mode: u32,
}
impl FileIdentity {
    fn at(path: &Path) -> Result<Self> {
        let m = std::fs::symlink_metadata(path)?;
        if !m.is_file() || m.nlink() != 1 {
            return Err(StoreError::CorruptState);
        }
        Ok(Self {
            device: m.dev(),
            inode: m.ino(),
            uid: m.uid(),
            mode: m.mode(),
        })
    }
}

/// Opaque evidence obtained from the already validated writer, during quiescent
/// guarded startup. The service must retain the same instance guard throughout.
#[derive(Clone)]
pub struct Context {
    path: PathBuf,
    file: FileIdentity,
    instance: String,
    limits: Option<(u64, u64)>,
}
impl Context {
    pub fn path(&self) -> &Path {
        &self.path
    }
}
impl Store {
    /// Startup only, after configured limits and before command workers start.
    /// Filesystem locality/custody validation remains the guarded caller's job.
    pub fn read_context(&self) -> Result<Context> {
        self.call(|db| {
            validate_schema(&db.connection)?;
            let instance = db.connection.query_row(
                "SELECT value FROM metadata WHERE key='instance_id'",
                [],
                |r| r.get(0),
            )?;
            Ok(Context {
                path: db.path.clone(),
                file: FileIdentity::at(&db.path)?,
                instance,
                limits: db.limits,
            })
        })
    }
}

/// All query variants are display-only. Effect-gating reads stay on Store.
pub enum Query {
    Status(i64),
    Page {
        cursor: i64,
        limit: usize,
        descending: bool,
    },
    Search {
        needle: String,
        before: i64,
        until: i64,
    },
    Retention(Option<i64>),
}
pub enum Snapshot {
    Status(Option<Box<JobStatus>>),
    Page {
        instance: String,
        rows: Vec<(i64, JobStatus)>,
        more: bool,
    },
    Search {
        instance: String,
        chunk: FileSearchChunk,
    },
    Retention(Option<Box<RetentionSnapshot>>),
}

/// Shared cancellation state also checked by Rust row-processing loops.
pub struct Budget {
    until: Instant,
    cancelled: AtomicBool,
}
impl Budget {
    pub fn new(until: Instant) -> Self {
        Self {
            until: until.min(Instant::now() + Duration::from_secs(1)),
            cancelled: AtomicBool::new(false),
        }
    }
    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
    }
    pub fn expired(&self) -> bool {
        self.cancelled.load(Ordering::Acquire) || Instant::now() >= self.until
    }
    fn check(&self) -> Result<()> {
        if self.expired() {
            Err(StoreError::WorkerStopped)
        } else {
            Ok(())
        }
    }
}

/// Safe rusqlite handle; its own shared lifetime protects connection closure.
pub struct Interrupt(rusqlite::InterruptHandle);
impl Interrupt {
    pub fn interrupt(&self) {
        self.0.interrupt();
    }
}

pub struct Reader {
    connection: Connection,
    poisoned: bool,
    limits: Option<(u64, u64)>,
    #[cfg(test)]
    after_snapshot: Option<Box<dyn FnOnce() + Send>>,
}
impl Reader {
    /// Fast checks only. Never call the full-scanning offline read-only open.
    pub fn open(context: &Context) -> Result<Self> {
        if FileIdentity::at(&context.path)? != context.file {
            return Err(StoreError::CorruptState);
        }
        let mut connection = Connection::open_with_flags(
            &context.path,
            OpenFlags::SQLITE_OPEN_READ_ONLY
                | OpenFlags::SQLITE_OPEN_FULL_MUTEX
                | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        connection.busy_timeout(Duration::from_millis(250))?;
        connection.pragma_update(None, "trusted_schema", "OFF")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        connection.pragma_update(None, "synchronous", "FULL")?;
        connection.pragma_update(None, "query_only", "ON")?;
        connection.pragma_update(None, "cache_size", -4096)?;
        let application: i64 =
            connection.pragma_query_value(None, "application_id", |r| r.get(0))?;
        let version: i64 = connection.pragma_query_value(None, "user_version", |r| r.get(0))?;
        let journal: String = connection.pragma_query_value(None, "journal_mode", |r| r.get(0))?;
        let sync: i64 = connection.pragma_query_value(None, "synchronous", |r| r.get(0))?;
        if application != APPLICATION_ID
            || version != SCHEMA_VERSION
            || journal != "wal"
            || sync != 2
        {
            return Err(StoreError::UnsupportedSchema);
        }
        let query_only: i64 = connection.pragma_query_value(None, "query_only", |r| r.get(0))?;
        let foreign_keys: i64 =
            connection.pragma_query_value(None, "foreign_keys", |r| r.get(0))?;
        let trusted: i64 = connection.pragma_query_value(None, "trusted_schema", |r| r.get(0))?;
        if !connection.is_readonly(rusqlite::MAIN_DB)?
            || query_only != 1
            || foreign_keys != 1
            || trusted != 0
        {
            return Err(StoreError::UnsupportedSqliteConfiguration);
        }
        check_sqlite_options(&connection)?;
        let tx = connection.transaction()?;
        let instance: String = tx.query_row(
            "SELECT value FROM metadata WHERE key='instance_id'",
            [],
            |r| r.get(0),
        )?;
        if instance != context.instance {
            return Err(StoreError::CorruptState);
        }
        tx.commit()?;
        if FileIdentity::at(&context.path)? != context.file {
            return Err(StoreError::CorruptState);
        }
        Ok(Self {
            connection,
            poisoned: false,
            limits: context.limits,
            #[cfg(test)]
            after_snapshot: None,
        })
    }
    pub fn interrupt_handle(&self) -> Interrupt {
        Interrupt(self.connection.get_interrupt_handle())
    }
    pub fn healthy(&self) -> bool {
        !self.poisoned && self.connection.is_autocommit()
    }

    /// Exactly one transaction, including cursor instance identity. Never return
    /// partial results or keep a snapshot alive while a client formats/sends it.
    pub fn query(&mut self, query: Query, budget: &Budget) -> Result<Snapshot> {
        budget.check()?;
        let tx = self.connection.transaction()?;
        let outcome = (|| {
            let instance: String = tx.query_row(
                "SELECT value FROM metadata WHERE key='instance_id'",
                [],
                |r| r.get(0),
            )?;
            #[cfg(test)]
            if let Some(after_snapshot) = self.after_snapshot.take() {
                after_snapshot();
            }
            budget.check()?;
            let value = run(&tx, self.limits, query, budget, instance)?;
            budget.check()?;
            Ok(value)
        })();
        match outcome {
            Ok(value) => {
                tx.commit()?;
                Ok(value)
            }
            Err(error) => {
                if let Err(rollback) = tx.rollback() {
                    self.poisoned = true;
                    return Err(rollback.into());
                }
                Err(error)
            }
        }
    }
}
fn run(
    tx: &rusqlite::Transaction<'_>,
    limits: Option<(u64, u64)>,
    query: Query,
    budget: &Budget,
    instance: String,
) -> Result<Snapshot> {
    let check = || budget.check();
    match query {
        Query::Status(id) => Ok(Snapshot::Status(status_in(tx, id)?.map(Box::new))),
        Query::Retention(id) => Ok(Snapshot::Retention(
            retention::snapshot_in(tx, limits, id, &check)?.map(Box::new),
        )),
        Query::Page {
            cursor,
            limit,
            descending,
        } => {
            if !(1..=256).contains(&limit) {
                return Err(StoreError::InvalidContext);
            }
            let ids = {
                let mut statement = tx.prepare(if descending {
                    "SELECT job_id FROM jobs WHERE job_id<?1 ORDER BY job_id DESC LIMIT ?2"
                } else {
                    "SELECT job_id FROM jobs WHERE job_id>?1 ORDER BY job_id LIMIT ?2"
                })?;
                statement
                    .query_map(params![cursor, limit as i64 + 1], |r| r.get::<_, i64>(0))?
                    .collect::<std::result::Result<Vec<_>, _>>()?
            };
            let more = ids.len() > limit;
            let mut rows = Vec::with_capacity(limit);
            for id in ids.into_iter().take(limit) {
                check()?;
                rows.push((id, status_in(tx, id)?.ok_or(StoreError::CorruptState)?));
            }
            Ok(Snapshot::Page {
                instance,
                rows,
                more,
            })
        }
        Query::Search {
            needle,
            before,
            until,
        } => {
            if needle.is_empty() || until < 0 || before <= until {
                return Err(StoreError::InvalidContext);
            }
            let chunk = search::scan_checked(
                tx,
                &needle,
                before,
                until,
                SEARCH_CHUNK_ROWS,
                SEARCH_CHUNK_BYTES,
                &check,
            )?;
            Ok(Snapshot::Search { instance, chunk })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicU64;
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "mover-read-sql-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            Self(path)
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
    fn budget() -> Budget {
        Budget::new(Instant::now() + Duration::from_secs(1))
    }
    #[test]
    fn fast_reader_is_read_only_and_keeps_startup_limits() {
        let f = Fixture::new();
        let writer = Store::open(f.db()).unwrap();
        writer.configure_limits(77, 123456).unwrap();
        let mut reader = Reader::open(&writer.read_context().unwrap()).unwrap();
        assert!(
            reader
                .connection
                .execute("INSERT INTO metadata VALUES('forbidden','value')", [])
                .is_err()
        );
        assert_eq!(
            reader
                .connection
                .pragma_query_value::<i64, _>(None, "trusted_schema", |r| r.get(0))
                .unwrap(),
            0
        );
        assert_eq!(
            reader
                .connection
                .pragma_query_value::<i64, _>(None, "synchronous", |r| r.get(0))
                .unwrap(),
            2
        );
        match reader.query(Query::Retention(None), &budget()).unwrap() {
            Snapshot::Retention(Some(snapshot)) => {
                assert_eq!(snapshot.configured_limits, Some((77, 123456)));
                assert_eq!(snapshot.jobs, 0);
            }
            _ => panic!("retention shape"),
        }
        assert!(reader.healthy());
        assert!(matches!(
            reader.query(Query::Status(1), &budget()).unwrap(),
            Snapshot::Status(None)
        ));
        assert!(reader.healthy());
    }
    #[test]
    fn fast_open_rejects_changed_identity_instance_schema_and_symlink() {
        use std::os::unix::fs::symlink;
        let f = Fixture::new();
        let writer = Store::open(f.db()).unwrap();
        let context = writer.read_context().unwrap();
        let mut wrong = context.clone();
        wrong.instance = "wrong".into();
        assert!(Reader::open(&wrong).is_err());
        wrong = context.clone();
        wrong.file.inode += 1;
        assert!(Reader::open(&wrong).is_err());
        wrong = context.clone();
        wrong.path = f.0.join("alias.sqlite");
        symlink(f.db(), &wrong.path).unwrap();
        assert!(Reader::open(&wrong).is_err());
        writer
            .call(|db| {
                db.connection.pragma_update(None, "application_id", 0)?;
                Ok(())
            })
            .unwrap();
        assert!(Reader::open(&context).is_err());
        writer
            .call(|db| {
                db.connection
                    .pragma_update(None, "application_id", APPLICATION_ID)?;
                Ok(())
            })
            .unwrap();
        writer
            .call(|db| {
                db.connection.pragma_update(None, "user_version", 0)?;
                Ok(())
            })
            .unwrap();
        assert!(Reader::open(&context).is_err());
    }
    #[test]
    fn snapshot_does_not_mix_commits_and_the_next_transaction_is_fresh() {
        let f = Fixture::new();
        let writer = Arc::new(Store::open(f.db()).unwrap());
        let mut reader = Reader::open(&writer.read_context().unwrap()).unwrap();
        let command = writer.clone();
        reader.after_snapshot = Some(Box::new(move || {
            let submission = Submission::new(
                "g",
                "after-snapshot",
                "/mnt/recordings/current",
                vec![FileSpec::new("data", None).unwrap()],
            )
            .unwrap();
            let context = AcceptanceContext {
                source_root_id: "recordings".into(),
                source_root_path: "/mnt/recordings".into(),
                source_relative_directory: "current".into(),
                destination_path: "/mnt/archive".into(),
                destination_binding: None,
                missing_retry_seconds: 300,
                policy: DeliveryPolicy {
                    destination_id: "archive".into(),
                    group_by_generator: false,
                    delete_source_after_commit: false,
                },
            };
            command.accept(&submission, &context).unwrap();
        }));
        let query = || Query::Page {
            cursor: 0,
            limit: 256,
            descending: false,
        };
        match reader.query(query(), &budget()).unwrap() {
            Snapshot::Page { rows, .. } => assert!(rows.is_empty(), "page mixed snapshots"),
            _ => panic!("page shape"),
        }
        match reader.query(query(), &budget()).unwrap() {
            Snapshot::Page { rows, .. } => {
                assert_eq!(rows.len(), 1, "next transaction must be fresh")
            }
            _ => panic!("page shape"),
        }
        assert!(reader.healthy());
    }
    #[test]
    fn cancelled_and_invalid_queries_leave_no_live_transaction() {
        let f = Fixture::new();
        let writer = Store::open(f.db()).unwrap();
        let mut reader = Reader::open(&writer.read_context().unwrap()).unwrap();
        let cancelled = budget();
        cancelled.cancel();
        assert!(reader.query(Query::Status(1), &cancelled).is_err());
        let during = Arc::new(budget());
        let cancel = during.clone();
        reader.after_snapshot = Some(Box::new(move || cancel.cancel()));
        assert!(reader.query(Query::Status(1), &during).is_err());
        assert!(
            reader.healthy(),
            "cancellation after the first read must roll back"
        );
        assert!(matches!(
            reader.query(
                Query::Page {
                    cursor: 0,
                    limit: 0,
                    descending: false
                },
                &budget()
            ),
            Err(StoreError::InvalidContext)
        ));
        assert!(reader.healthy());
        assert!(matches!(
            reader
                .query(
                    Query::Page {
                        cursor: 0,
                        limit: 1,
                        descending: false
                    },
                    &budget()
                )
                .unwrap(),
            Snapshot::Page { more: false, .. }
        ));
        assert!(matches!(
            reader
                .query(
                    Query::Search {
                        needle: "data".into(),
                        before: i64::MAX,
                        until: 0
                    },
                    &budget()
                )
                .unwrap(),
            Snapshot::Search { .. }
        ));
        assert!(reader.healthy());
    }
}
