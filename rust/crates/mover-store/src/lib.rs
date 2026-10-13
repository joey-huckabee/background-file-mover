//! Local SQLite acceptance/replay. One bounded-command owner thread holds SQL.
//! Calls block; dispatch them outside an async executor. Filesystem I/O is separate.

use mover_core::{
    ClaimIntent, DeliveryPolicy, FileSpec, ObjectIdentity, ProtocolError, Recording, Submission,
};
use mover_core::{ManifestRecord, Transfer, TransferPhase};
use rusqlite::{Connection, OpenFlags, OptionalExtension, TransactionBehavior, params};
use std::{
    fmt,
    path::{Path, PathBuf},
    sync::mpsc,
    thread,
    time::Duration,
};
mod operators;
pub use operators::{ResumeAudit, ResumeReceipt, ResumeRequest};

const APPLICATION_ID: i64 = 0x42464d52;
const SCHEMA_VERSION: i64 = 6;

#[derive(Debug)]
pub enum StoreError {
    Sqlite(rusqlite::Error),
    Io(std::io::Error),
    Protocol(ProtocolError),
    UnsupportedSchema,
    UnsupportedSqliteConfiguration,
    InvalidContext,
    CorruptState,
    SourceReserved,
    SourceRootChanged,
    WorkerStopped,
    AdmissionFull,
    NotFound,
    ReviewConflict,
    ActionConflict,
    AuditFull,
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Sqlite(error) => write!(f, "SQLite: {error}"),
            Self::Io(error) => write!(f, "I/O: {error}"),
            other => write!(f, "{other:?}"),
        }
    }
}
impl std::error::Error for StoreError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Sqlite(error) => Some(error),
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}
impl From<rusqlite::Error> for StoreError {
    fn from(e: rusqlite::Error) -> Self {
        Self::Sqlite(e)
    }
}
impl From<std::io::Error> for StoreError {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}
impl From<ProtocolError> for StoreError {
    fn from(e: ProtocolError) -> Self {
        Self::Protocol(e)
    }
}
pub type Result<T> = std::result::Result<T, StoreError>;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AcceptanceContext {
    pub source_root_id: String,
    pub source_root_path: String,
    pub source_relative_directory: String,
    pub destination_path: String,
    pub policy: DeliveryPolicy,
    pub missing_retry_seconds: u32,
}

impl AcceptanceContext {
    fn validate(&self) -> Result<()> {
        if self.source_root_id.trim().is_empty()
            || self.policy.destination_id.trim().is_empty()
            || !self.source_root_path.starts_with('/')
            || !self.destination_path.starts_with('/')
        {
            return Err(StoreError::InvalidContext);
        }
        if !self.source_relative_directory.is_empty() {
            FileSpec::new(&self.source_relative_directory, None)?;
        }
        Ok(())
    }
    fn source_name(&self, file: &FileSpec) -> String {
        if self.source_relative_directory.is_empty() {
            file.relative_path().to_owned()
        } else {
            format!(
                "{}/{}",
                self.source_relative_directory,
                file.relative_path()
            )
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Accepted {
    pub job_id: i64,
    pub recording: Recording,
    pub context: AcceptanceContext,
    pub replay: bool,
}

/// One database-owner snapshot; no filesystem observations or state changes.
pub struct JobStatus {
    pub job: Accepted,
    pub transfers: Vec<Option<Transfer>>,
    pub missing: Vec<(usize, i64, bool)>,
    pub delivery: Option<(u32, i64, String)>,
    pub manifest_phase: Option<i64>,
    pub review_epoch: u32,
    pub latest_resume: Option<ResumeAudit>,
}

/// Dedicated connection owner. Queue capacity bounds admitted commands, not
/// external request allocation. Never call blocking methods on Tokio's executor.
pub struct Store {
    commands: mpsc::SyncSender<Command>,
    worker: Option<thread::JoinHandle<()>>,
}
type Operation = Box<dyn FnOnce(&mut Database) + Send>;
enum Command {
    Run(Operation),
    Stop,
}

impl Store {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        Self::start(path.as_ref().to_owned(), false)
    }
    pub fn open_read_only(path: impl AsRef<Path>) -> Result<Self> {
        Self::start(path.as_ref().to_owned(), true)
    }
    fn start(path: PathBuf, read_only: bool) -> Result<Self> {
        let (commands, receiver) = mpsc::sync_channel(32);
        let (startup, ready) = mpsc::sync_channel(1);
        let worker = thread::Builder::new()
            .name("mover-sqlite".into())
            .spawn(move || {
                let mut database = match Database::open(&path, read_only) {
                    Ok(database) => {
                        if startup.send(Ok(())).is_err() {
                            return;
                        }
                        database
                    }
                    Err(error) => {
                        let _ = startup.send(Err(error));
                        return;
                    }
                };
                while let Ok(command) = receiver.recv() {
                    match command {
                        Command::Run(operation) => operation(&mut database),
                        Command::Stop => break,
                    }
                }
            })?;
        match ready.recv().map_err(|_| StoreError::WorkerStopped)? {
            Ok(()) => Ok(Self {
                commands,
                worker: Some(worker),
            }),
            Err(error) => {
                let _ = worker.join();
                Err(error)
            }
        }
    }
    fn call<T: Send + 'static>(
        &self,
        operation: impl FnOnce(&mut Database) -> Result<T> + Send + 'static,
    ) -> Result<T> {
        let (reply, result) = mpsc::sync_channel(1);
        self.commands
            .send(Command::Run(Box::new(move |db| {
                let _ = reply.send(operation(db));
            })))
            .map_err(|_| StoreError::WorkerStopped)?;
        result.recv().map_err(|_| StoreError::WorkerStopped)?
    }
    pub fn accept(&self, submission: &Submission, context: &AcceptanceContext) -> Result<Accepted> {
        let submission = submission.clone();
        let context = context.clone();
        self.call(move |db| db.accept(&submission, &context))
    }
    pub fn get(&self, job_id: i64) -> Result<Option<Accepted>> {
        self.call(move |db| load(&db.connection, job_id))
    }
    pub fn status(&self, job_id: i64) -> Result<Option<JobStatus>> {
        self.call(move |db| {
            let tx = db.connection.transaction()?;
            let count: Option<i64> = tx.query_row("SELECT file_count FROM jobs WHERE job_id=?1", [job_id], |r| r.get(0)).optional()?;
            let Some(count) = count else { return Ok(None); };
            if !(1..=256).contains(&count) { return Err(StoreError::InvalidContext); }
            let job = load(&tx, job_id)?.ok_or(StoreError::CorruptState)?;
            let transfers = (0..count as usize).map(|i| load_transfer(&tx, job_id, i)).collect::<Result<Vec<_>>>()?;
            let missing = {
                let mut s = tx.prepare("SELECT file_index,deadline,blocked FROM missing WHERE job_id=?1 ORDER BY file_index")?;
                s.query_map([job_id], |r| Ok((r.get::<_,u32>(0)? as usize, r.get(1)?, r.get(2)?)))?.collect::<std::result::Result<Vec<_>,_>>()?
            };
            let delivery = tx.query_row("SELECT failures,retry_after,code FROM delivery_failures WHERE job_id=?1", [job_id], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?))).optional()?;
            let manifest_phase = load_manifest(&tx, job_id)?.map(|m| m.phase);
            let review_epoch = operators::epoch(&tx,job_id)?;
            let latest_resume = operators::latest(&tx,job_id)?;
            tx.commit()?;
            Ok(Some(JobStatus { job, transfers, missing, delivery, manifest_phase, review_epoch, latest_resume }))
        })
    }
    pub fn claim_intent(
        &self,
        job_id: i64,
        file_index: usize,
    ) -> Result<Option<(ClaimIntent, bool)>> {
        self.call(move |db| load_claim(&db.connection, job_id, file_index))
    }
    pub fn begin_claim(&self, intent: &ClaimIntent) -> Result<()> {
        let intent = intent.clone();
        self.call(move |db| db.begin_claim(&intent))
    }
    /// Only a worker that validated custody and synchronized the completed
    /// effect may call this. SQLite cannot establish filesystem durability.
    pub fn finish_claim(&self, intent: &ClaimIntent) -> Result<Accepted> {
        let intent = intent.clone();
        self.call(move |db| db.finish_claim(&intent))
    }
    pub fn job_count(&self) -> Result<u64> {
        self.call(|db| {
            let count: i64 = db
                .connection
                .query_row("SELECT count(*) FROM jobs", [], |row| row.get(0))?;
            u64::try_from(count).map_err(|_| StoreError::CorruptState)
        })
    }
    /// Persist first confirmed absence. Replays never extend its deadline.
    pub fn note_missing(&self, job_id: i64, index: usize, now: i64) -> Result<bool> {
        self.call(move |db| {
            if now < 0 { return Err(StoreError::InvalidContext); }
            let tx = db.connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            let job = load(&tx, job_id)?.ok_or(StoreError::InvalidContext)?;
            if job.recording.file_phase(index) != Some(mover_core::FilePhase::Pending) { return Err(StoreError::InvalidContext); }
            let deadline = now.checked_add(i64::from(job.context.missing_retry_seconds)).ok_or(StoreError::InvalidContext)?;
            tx.execute("INSERT INTO missing(job_id,file_index,deadline) VALUES(?1,?2,?3) ON CONFLICT(job_id,file_index) DO NOTHING",params![job_id,index as i64,deadline])?;
            tx.commit()?;
            db.claim_blocked(job_id, now)
        })
    }
    pub fn claim_blocked(&self, job_id: i64, now: i64) -> Result<bool> {
        self.call(move |db| db.claim_blocked(job_id, now))
    }
    pub fn transfer(&self, job_id: i64, index: usize) -> Result<Option<Transfer>> {
        self.call(move |db| load_transfer(&db.connection, job_id, index))
    }
    /// Trusted synchronous worker results; caller proves custody/synchronization.
    pub fn save_transfer(&self, transfer: &Transfer) -> Result<()> {
        let transfer = transfer.clone();
        self.call(move |db| db.save_transfer(&transfer))
    }
    pub fn configure_limits(&self, jobs: u64, bytes: u64) -> Result<()> {
        self.call(move |db| {
            if jobs == 0 || bytes == 0 {
                return Err(StoreError::InvalidContext);
            }
            db.limits = Some((jobs, bytes));
            Ok(())
        })
    }
    pub fn claim_capacity(&self, extra: u64) -> Result<()> {
        self.call(move |db| {
            if let Some((_, bytes)) = db.limits {
                check_retained_bytes(&db.connection, extra, bytes, false)?;
            }
            Ok(())
        })
    }
    pub fn transfer_capacity(&self, id: i64, index: usize) -> Result<()> {
        self.call(move |db| {
            if let Some((_, bytes)) = db.limits {
                let claim = load_claim(&db.connection, id, index)?
                    .ok_or(StoreError::CorruptState)?
                    .0;
                check_retained_bytes(&db.connection, claim.source.size, bytes, true)?;
            }
            Ok(())
        })
    }
    pub fn instance_id(&self) -> Result<String> {
        self.call(|db| {
            db.connection
                .query_row(
                    "SELECT value FROM metadata WHERE key='instance_id'",
                    [],
                    |r| r.get(0),
                )
                .map_err(Into::into)
        })
    }
    pub fn manifest(&self, id: i64) -> Result<Option<ManifestRecord>> {
        self.call(move |db| load_manifest(&db.connection, id))
    }
    pub fn save_manifest(&self, m: &ManifestRecord) -> Result<()> {
        let m = m.clone();
        self.call(move |db| db.save_manifest(&m))
    }
    pub fn delivery_candidates(&self, now: i64, limit: u32) -> Result<Vec<i64>> {
        self.call(move|db| {
            if now<0 || limit==0 || limit>64 {return Err(StoreError::InvalidContext);}
            let mut s=db.connection.prepare("SELECT j.job_id FROM jobs j LEFT JOIN manifests m ON m.job_id=j.job_id LEFT JOIN delivery_failures d ON d.job_id=j.job_id WHERE j.file_count=(SELECT count(*) FROM claims c WHERE c.job_id=j.job_id AND c.done=1) AND coalesce(m.phase,0)<4 AND coalesce(d.failures,0)<3 AND coalesce(d.retry_after,0)<=?1 ORDER BY j.job_id LIMIT ?2")?;
            Ok(s.query_map(params![now,limit],|r|r.get(0))?.collect::<std::result::Result<Vec<_>,_>>()?)
        })
    }
    pub fn delivery_failed(&self, id: i64, now: i64) -> Result<()> {
        self.call(move|db| {if now<0 {return Err(StoreError::InvalidContext);}db.connection.execute("INSERT INTO delivery_failures VALUES(?1,1,?2,'delivery_requires_review') ON CONFLICT(job_id) DO UPDATE SET failures=min(3,failures+1),retry_after=excluded.retry_after",params![id,now.saturating_add(5)])?;Ok(())})
    }
    pub fn delivery_deferred(&self, id: i64, now: i64) -> Result<()> {
        self.call(move|db| {if now<0 {return Err(StoreError::InvalidContext);}db.connection.execute("INSERT INTO delivery_failures VALUES(?1,0,?2,'destination_unavailable') ON CONFLICT(job_id) DO UPDATE SET retry_after=excluded.retry_after,code=excluded.code",params![id,now.saturating_add(5)])?;Ok(())})
    }
}
impl Drop for Store {
    fn drop(&mut self) {
        let _ = self.commands.send(Command::Stop);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

struct Database {
    connection: Connection,
    limits: Option<(u64, u64)>,
}
impl Database {
    fn open(path: &Path, read_only: bool) -> Result<Self> {
        let flags = if read_only {
            OpenFlags::SQLITE_OPEN_READ_ONLY
        } else {
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE
        };
        let mut connection =
            Connection::open_with_flags(path, flags | OpenFlags::SQLITE_OPEN_FULL_MUTEX)?;
        connection.busy_timeout(Duration::from_millis(250))?;
        let version: i64 = connection.pragma_query_value(None, "user_version", |r| r.get(0))?;
        let application: i64 =
            connection.pragma_query_value(None, "application_id", |r| r.get(0))?;
        let fresh = version == 0 && application == 0 && !read_only;
        if fresh {
            let objects: i64 = connection.query_row(
                "SELECT count(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'",
                [],
                |r| r.get(0),
            )?;
            if objects != 0 {
                return Err(StoreError::UnsupportedSchema);
            }
        } else if (version != SCHEMA_VERSION && !((1..=5).contains(&version) && !read_only))
            || application != APPLICATION_ID
        {
            return Err(StoreError::UnsupportedSchema);
        }
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.pragma_update(None, "synchronous", "FULL")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        let journal: String = connection.pragma_query_value(None, "journal_mode", |r| r.get(0))?;
        let sync: i64 = connection.pragma_query_value(None, "synchronous", |r| r.get(0))?;
        let fk: i64 = connection.pragma_query_value(None, "foreign_keys", |r| r.get(0))?;
        if journal != "wal" || sync != 2 || fk != 1 {
            return Err(StoreError::UnsupportedSqliteConfiguration);
        }
        for option in [
            "THREADSAFE=1",
            "OMIT_LOAD_EXTENSION",
            "DQS=0",
            "DEFAULT_MEMSTATUS=0",
            "ENABLE_API_ARMOR",
        ] {
            let enabled: i64 =
                connection.query_row("SELECT sqlite_compileoption_used(?1)", [option], |r| {
                    r.get(0)
                })?;
            if enabled != 1 {
                return Err(StoreError::UnsupportedSqliteConfiguration);
            }
        }
        if fresh {
            let tx = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            tx.execute_batch(include_str!("schema.sql"))?;
            tx.execute_batch(include_str!("claims.sql"))?;
            tx.execute_batch(include_str!("missing.sql"))?;
            tx.execute_batch(include_str!("transfers.sql"))?;
            tx.execute_batch(include_str!("coordination.sql"))?;
            tx.execute_batch(include_str!("operators.sql"))?;
            initialize_instance(&tx)?;
            tx.pragma_update(None, "application_id", APPLICATION_ID)?;
            tx.pragma_update(None, "user_version", SCHEMA_VERSION)?;
            tx.commit()?;
        }
        if (1..=5).contains(&version) && !read_only {
            let tx = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
            if version == 1 {
                tx.execute_batch(include_str!("claims.sql"))?;
            }
            if version <= 2 {
                tx.execute_batch(include_str!("missing.sql"))?;
            }
            if version <= 3 {
                tx.execute_batch(include_str!("transfers.sql"))?;
            }
            if version <= 4 {
                tx.execute_batch(include_str!("coordination.sql"))?;
                initialize_instance(&tx)?;
            }
            tx.execute_batch(include_str!("operators.sql"))?;
            tx.pragma_update(None, "user_version", SCHEMA_VERSION)?;
            tx.commit()?;
        }
        // Persist the initial directory entries too; local Linux state storage
        // and a protected existing parent directory are deployment prerequisites.
        if !read_only {
            std::fs::File::open(
                path.parent()
                    .filter(|p| !p.as_os_str().is_empty())
                    .unwrap_or(Path::new(".")),
            )?
            .sync_all()?;
        }
        let damaged: bool = connection.query_row("SELECT EXISTS(SELECT 1 FROM jobs j WHERE j.file_count != (SELECT count(*) FROM files f WHERE f.job_id=j.job_id) OR (SELECT count(*) FROM reservations r WHERE r.job_id=j.job_id) != CASE WHEN j.file_count=(SELECT count(*) FROM claims c WHERE c.job_id=j.job_id AND c.done=1) THEN 0 ELSE j.file_count END) OR EXISTS(SELECT 1 FROM reservations r JOIN jobs j ON j.job_id=r.job_id JOIN files f ON f.job_id=r.job_id AND f.file_index=r.file_index WHERE r.source_root_id != j.source_root_id OR r.source_relative_path != CASE WHEN j.source_relative_directory='' THEN f.relative_path ELSE j.source_relative_directory || '/' || f.relative_path END)", [], |r| r.get(0))?;
        let foreign_key_errors: i64 =
            connection.query_row("SELECT count(*) FROM pragma_foreign_key_check", [], |r| {
                r.get(0)
            })?;
        if damaged || foreign_key_errors != 0 {
            return Err(StoreError::CorruptState);
        }
        let ids: Vec<i64> = connection
            .prepare("SELECT job_id FROM jobs")?
            .query_map([], |r| r.get(0))?
            .collect::<std::result::Result<_, _>>()?;
        for id in ids {
            load(&connection, id)?;
        }
        let instance: String = connection.query_row(
            "SELECT value FROM metadata WHERE key='instance_id'",
            [],
            |r| r.get(0),
        )?;
        if instance.len() != 32
            || !instance
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(StoreError::CorruptState);
        }
        Ok(Self {
            connection,
            limits: None,
        })
    }

    fn begin_claim(&mut self, intent: &ClaimIntent) -> Result<()> {
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let job = load(&tx, intent.job_id)?.ok_or(StoreError::InvalidContext)?;
        validate_claim(&job, intent)?;
        if let Some((prior, _)) = load_claim(&tx, intent.job_id, intent.file_index)? {
            if prior != *intent {
                return Err(StoreError::CorruptState);
            }
        } else {
            if let Some((_, bytes)) = self.limits {
                check_retained_bytes(&tx, intent.source.size, bytes, false)?;
            }
            tx.execute("INSERT INTO claims(job_id,file_index,root_path,source_name,private_name,root_identity,parent_identity,area_identity,source_identity) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)",
                params![intent.job_id, intent.file_index as i64, intent.root_path, intent.source_name,
                    intent.private_name, intent.root.encode(), intent.parent.encode(), intent.area.encode(), intent.source.encode()])?;
        }
        tx.commit()?;
        Ok(())
    }
    fn claim_blocked(&mut self, job_id: i64, now: i64) -> Result<bool> {
        if now < 0 {
            return Err(StoreError::InvalidContext);
        }
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        tx.execute(
            "UPDATE missing SET blocked=1 WHERE job_id=?1 AND deadline<=?2",
            params![job_id, now],
        )?;
        let blocked = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM missing WHERE job_id=?1 AND blocked=1)",
            [job_id],
            |r| r.get(0),
        )?;
        tx.commit()?;
        Ok(blocked)
    }
    fn finish_claim(&mut self, intent: &ClaimIntent) -> Result<Accepted> {
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let (prior, _) =
            load_claim(&tx, intent.job_id, intent.file_index)?.ok_or(StoreError::InvalidContext)?;
        if prior != *intent {
            return Err(StoreError::CorruptState);
        }
        tx.execute(
            "UPDATE claims SET done=1 WHERE job_id=?1 AND file_index=?2",
            params![intent.job_id, intent.file_index as i64],
        )?;
        tx.execute(
            "DELETE FROM missing WHERE job_id=?1 AND file_index=?2",
            params![intent.job_id, intent.file_index as i64],
        )?;
        tx.execute("DELETE FROM reservations WHERE job_id=?1 AND (SELECT count(*) FROM claims WHERE job_id=?1 AND done=1)=(SELECT file_count FROM jobs WHERE job_id=?1)", [intent.job_id])?;
        let result = load(&tx, intent.job_id)?.ok_or(StoreError::CorruptState)?;
        tx.commit()?;
        Ok(result)
    }

    fn accept(&mut self, submission: &Submission, context: &AcceptanceContext) -> Result<Accepted> {
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let prior: Option<i64> = tx
            .query_row(
                "SELECT job_id FROM jobs WHERE generator_id=?1 AND submission_id=?2",
                params![submission.generator_id(), submission.submission_id()],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(id) = prior {
            let mut saved = load(&tx, id)?.ok_or(StoreError::CorruptState)?;
            saved.recording.replay(submission)?;
            tx.commit()?;
            saved.replay = true;
            return Ok(saved);
        }
        context.validate()?;
        if let Some((jobs, _)) = self.limits {
            let count: i64 = tx.query_row("SELECT count(*) FROM jobs", [], |r| r.get(0))?;
            if count as u64 >= jobs {
                return Err(StoreError::AdmissionFull);
            }
        }
        let mut recording = Recording::new(submission.clone(), context.policy.clone())?;
        let previous_root: Option<String> = tx
            .query_row(
                "SELECT source_root_path FROM jobs WHERE source_root_id=?1 LIMIT 1",
                [&context.source_root_id],
                |r| r.get(0),
            )
            .optional()?;
        if previous_root
            .as_ref()
            .is_some_and(|root| root != &context.source_root_path)
        {
            return Err(StoreError::SourceRootChanged);
        }
        for file in submission.files() {
            let occupied: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM reservations WHERE source_root_id=?1 AND source_relative_path=?2)",
                params![context.source_root_id, context.source_name(file)], |r| r.get(0))?;
            if occupied {
                return Err(StoreError::SourceReserved);
            }
        }
        tx.execute("INSERT INTO jobs(generator_id,submission_id,source_directory,source_root_id,source_root_path,source_relative_directory,destination_id,destination_path,group_by_generator,delete_source_after_commit,missing_retry_seconds,file_count) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12)",
            params![submission.generator_id(), submission.submission_id(), submission.source_directory(), context.source_root_id,
                context.source_root_path, context.source_relative_directory, context.policy.destination_id,
                context.destination_path, context.policy.group_by_generator, context.policy.delete_source_after_commit,
                context.missing_retry_seconds, i64::try_from(submission.files().len()).map_err(|_| StoreError::InvalidContext)?])?;
        let job_id = tx.last_insert_rowid();
        for (index, file) in submission.files().iter().enumerate() {
            let index = i64::try_from(index).map_err(|_| StoreError::InvalidContext)?;
            tx.execute(
                "INSERT INTO files VALUES(?1,?2,?3,?4)",
                params![
                    job_id,
                    index,
                    file.relative_path(),
                    file.expected_size().map(|size| size.to_string())
                ],
            )?;
            tx.execute(
                "INSERT INTO reservations VALUES(?1,?2,?3,?4)",
                params![
                    context.source_root_id,
                    context.source_name(file),
                    job_id,
                    index
                ],
            )?;
        }
        tx.commit()?;
        recording.confirm_acceptance();
        Ok(Accepted {
            job_id,
            recording,
            context: context.clone(),
            replay: false,
        })
    }
    fn save_transfer(&mut self, t: &Transfer) -> Result<()> {
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let job = load(&tx, t.job_id)?.ok_or(StoreError::InvalidContext)?;
        validate_transfer(&job, t)?;
        let prior = load_transfer(&tx, t.job_id, t.file_index)?;
        if prior.as_ref().is_none_or(|p| p.attempt != t.attempt)
            && let Some((_, bytes)) = self.limits
        {
            let claim = load_claim(&tx, t.job_id, t.file_index)?
                .ok_or(StoreError::CorruptState)?
                .0;
            check_retained_bytes(&tx, claim.source.size, bytes, true)?;
        }
        if let Some(p) = &prior {
            if p == t {
                tx.commit()?;
                return Ok(());
            }
            let mut unchanged = t.clone();
            unchanged.phase = p.phase;
            unchanged.stage = p.stage.clone();
            unchanged.sha256 = p.sha256.clone();
            unchanged.attempt = p.attempt;
            if unchanged != *p {
                return Err(StoreError::CorruptState);
            }
            if t.attempt == p.attempt {
                if t.phase as i64 != p.phase as i64 + 1
                    || (p.phase != TransferPhase::Intent
                        && (t.stage != p.stage || t.sha256 != p.sha256))
                    || t.stage.device != p.stage.device
                    || t.stage.inode != p.stage.inode
                    || t.stage.uid != p.stage.uid
                {
                    return Err(StoreError::CorruptState);
                }
            } else if p.phase != TransferPhase::Intent
                || t.phase != TransferPhase::Intent
                || t.attempt != p.attempt + 1
            {
                return Err(StoreError::CorruptState);
            }
        } else if t.phase != TransferPhase::Intent || t.attempt != 1 {
            return Err(StoreError::InvalidContext);
        }
        tx.execute("INSERT INTO transfers VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12) ON CONFLICT(job_id,file_index,attempt) DO UPDATE SET stage_identity=excluded.stage_identity,sha256=excluded.sha256,phase=excluded.phase",params![t.job_id,t.file_index as i64,t.attempt,t.destination_root,t.relative_name,t.root.encode(),t.area.encode(),t.parent.encode(),t.staging_directory.encode(),t.stage.encode(),t.sha256,t.phase as i64])?;
        tx.commit()?;
        Ok(())
    }
    fn save_manifest(&mut self, m: &ManifestRecord) -> Result<()> {
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let job = load(&tx, m.job_id)?.ok_or(StoreError::InvalidContext)?;
        if (0..job.recording.submission().files().len())
            .any(|i| job.recording.file_phase(i) != Some(mover_core::FilePhase::Published))
        {
            return Err(StoreError::InvalidContext);
        }
        validate_manifest(m)?;
        if let Some(p) = load_manifest(&tx, m.job_id)? {
            if p == *m {
                tx.commit()?;
                return Ok(());
            }
            if m.bytes != p.bytes || m.sha256 != p.sha256 || m.phase != p.phase + 1 {
                return Err(StoreError::CorruptState);
            }
            if p.phase > 0 {
                let a = p.object.ok_or(StoreError::CorruptState)?;
                let b = m.object.as_ref().ok_or(StoreError::CorruptState)?;
                if a.device != b.device
                    || a.inode != b.inode
                    || a.uid != b.uid
                    || (p.phase >= 2 && a != *b)
                {
                    return Err(StoreError::CorruptState);
                }
            }
        } else if m.phase != 0 {
            return Err(StoreError::InvalidContext);
        }
        tx.execute("INSERT INTO manifests VALUES(?1,?2,?3,?4,?5) ON CONFLICT(job_id) DO UPDATE SET phase=excluded.phase,object_identity=excluded.object_identity",params![m.job_id,m.bytes,m.sha256,m.phase,m.object.as_ref().map(ObjectIdentity::encode)])?;
        tx.commit()?;
        Ok(())
    }
}

fn load(connection: &Connection, job_id: i64) -> Result<Option<Accepted>> {
    let header = connection.query_row("SELECT generator_id,submission_id,source_directory,source_root_id,source_root_path,source_relative_directory,destination_id,destination_path,group_by_generator,delete_source_after_commit,missing_retry_seconds,file_count FROM jobs WHERE job_id=?1",
        [job_id], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?, r.get::<_, String>(2)?, AcceptanceContext {
            source_root_id: r.get(3)?, source_root_path: r.get(4)?, source_relative_directory: r.get(5)?,
            policy: DeliveryPolicy { destination_id: r.get(6)?, group_by_generator: r.get(8)?, delete_source_after_commit: r.get(9)? },
            destination_path: r.get(7)?, missing_retry_seconds: r.get(10)?,
        }, r.get::<_, i64>(11)?))).optional()?;
    let Some((generator, submission, source, context, file_count)) = header else {
        return Ok(None);
    };
    let mut statement = connection.prepare("SELECT file_index,relative_path,expected_size FROM files WHERE job_id=?1 ORDER BY file_index")?;
    let rows = statement.query_map([job_id], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, Option<String>>(2)?,
        ))
    })?;
    let mut files = Vec::new();
    for row in rows {
        let (index, path, expected) = row?;
        if usize::try_from(index).ok() != Some(files.len()) {
            return Err(StoreError::CorruptState);
        }
        let size = expected
            .map(|value| value.parse::<u64>().map_err(|_| StoreError::CorruptState))
            .transpose()?;
        files.push(FileSpec::new(path, size)?);
    }
    if usize::try_from(file_count).ok() != Some(files.len()) {
        return Err(StoreError::CorruptState);
    }
    context.validate()?;
    let input = Submission::new(generator, submission, source, files)?;
    let mut recording = Recording::new(input, context.policy.clone())?;
    recording.confirm_acceptance();
    let mut result = Accepted {
        job_id,
        recording,
        context,
        replay: false,
    };
    for index in 0..result.recording.submission().files().len() {
        if let Some((intent, done)) = load_claim(connection, job_id, index)? {
            validate_claim(&result, &intent)?;
            if done {
                result.recording.confirm_claim(index, intent.source.size)?;
            }
        }
    }
    for index in 0..result.recording.submission().files().len() {
        if let Some(t) = load_transfer(connection, job_id, index)? {
            validate_transfer(&result, &t)?;
            if t.phase >= TransferPhase::Verified {
                result.recording.confirm_verification(index)?;
            }
            if t.phase == TransferPhase::Published {
                result.recording.confirm_publication(index)?;
            }
        }
    }
    if let Some(m) = load_manifest(connection, job_id)?
        && m.phase == 4
    {
        result.recording.confirm_commit()?;
    }
    Ok(Some(result))
}

fn validate_transfer(job: &Accepted, t: &Transfer) -> Result<()> {
    if t.job_id != job.job_id
        || t.file_index >= job.recording.submission().files().len()
        || job.recording.handoff() != mover_core::Handoff::Ready202
        || job.context.policy.group_by_generator
        || t.destination_root != job.context.destination_path
        || t.relative_name != job.recording.submission().files()[t.file_index].relative_path()
        || !(1..=100).contains(&t.attempt)
        || t.stage.links != 1
        || t.stage.device != t.root.device
        || t.area.device != t.root.device
        || t.parent.device != t.root.device
        || (t.phase == TransferPhase::Intent && (t.sha256.is_some() || t.stage.size != 0))
        || (t.phase != TransferPhase::Intent
            && (Some(t.stage.size) != job.recording.file_size(t.file_index)
                || t.sha256.as_ref().is_none_or(|s| {
                    s.len() != 64
                        || !s
                            .bytes()
                            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                })))
    {
        return Err(StoreError::CorruptState);
    }
    Ok(())
}
fn load_transfer(c: &Connection, job: i64, index: usize) -> Result<Option<Transfer>> {
    let row=c.query_row("SELECT attempt,destination_root,relative_name,root_identity,area_identity,parent_identity,staging_directory_identity,stage_identity,sha256,phase FROM transfers WHERE job_id=?1 AND file_index=?2 ORDER BY attempt DESC LIMIT 1",params![job,index as i64],|r|Ok((r.get::<_,i64>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,String>(3)?,r.get::<_,String>(4)?,r.get::<_,String>(5)?,r.get::<_,String>(6)?,r.get::<_,String>(7)?,r.get::<_,Option<String>>(8)?,r.get::<_,i64>(9)?))).optional()?;
    row.map(
        |(
            attempt,
            destination_root,
            relative_name,
            root,
            area,
            parent,
            staging,
            stage,
            sha256,
            phase,
        )| {
            let decode = |s: &str| ObjectIdentity::decode(s).ok_or(StoreError::CorruptState);
            Ok(Transfer {
                job_id: job,
                file_index: index,
                attempt,
                destination_root,
                relative_name,
                root: decode(&root)?,
                area: decode(&area)?,
                parent: decode(&parent)?,
                staging_directory: decode(&staging)?,
                stage: decode(&stage)?,
                sha256,
                phase: TransferPhase::decode(phase).ok_or(StoreError::CorruptState)?,
            })
        },
    )
    .transpose()
}

fn validate_claim(job: &Accepted, intent: &ClaimIntent) -> Result<()> {
    let file = job
        .recording
        .submission()
        .files()
        .get(intent.file_index)
        .ok_or(StoreError::CorruptState)?;
    if intent.job_id != job.job_id
        || intent.root_path != job.context.source_root_path
        || intent.source_name != job.context.source_name(file)
        || intent.private_name != format!("{}-{}", job.job_id, intent.file_index)
        || intent.source.links != 1
        || intent.source.device != intent.root.device
        || intent.parent.device != intent.root.device
        || intent.area.device != intent.root.device
        || file
            .expected_size()
            .is_some_and(|size| size != intent.source.size)
    {
        return Err(StoreError::CorruptState);
    }
    Ok(())
}

fn load_claim(
    connection: &Connection,
    job_id: i64,
    file_index: usize,
) -> Result<Option<(ClaimIntent, bool)>> {
    let row = connection.query_row("SELECT root_path,source_name,private_name,root_identity,parent_identity,area_identity,source_identity,done FROM claims WHERE job_id=?1 AND file_index=?2",
        params![job_id, i64::try_from(file_index).map_err(|_| StoreError::InvalidContext)?], |r| Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,String>(3)?,r.get::<_,String>(4)?,r.get::<_,String>(5)?,r.get::<_,String>(6)?,r.get::<_,bool>(7)?))).optional()?;
    row.map(
        |(root_path, source_name, private_name, root, parent, area, source, done)| {
            let decode = |s: &str| ObjectIdentity::decode(s).ok_or(StoreError::CorruptState);
            Ok((
                ClaimIntent {
                    job_id,
                    file_index,
                    root_path,
                    source_name,
                    private_name,
                    root: decode(&root)?,
                    parent: decode(&parent)?,
                    area: decode(&area)?,
                    source: decode(&source)?,
                },
                done,
            ))
        },
    )
    .transpose()
}

#[cfg(test)]
mod tests;

fn initialize_instance(c: &Connection) -> Result<()> {
    use std::io::Read;
    let mut bytes = [0; 16];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut bytes)?;
    let id: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    c.execute("INSERT INTO metadata VALUES('instance_id',?1)", [id])?;
    Ok(())
}
fn validate_manifest(m: &ManifestRecord) -> Result<()> {
    if m.bytes.is_empty()
        || m.bytes.len() > 131072
        || m.sha256.len() != 64
        || !m
            .sha256
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        || !(0..=4).contains(&m.phase)
        || (m.phase == 0) != m.object.is_none()
        || m.object.as_ref().is_some_and(|o| {
            o.links != 1
                || (m.phase == 1 && o.size != 0)
                || (m.phase >= 2 && o.size != m.bytes.len() as u64)
        })
    {
        return Err(StoreError::CorruptState);
    }
    Ok(())
}
fn load_manifest(c: &Connection, id: i64) -> Result<Option<ManifestRecord>> {
    let row = c
        .query_row(
            "SELECT bytes,sha256,phase,object_identity FROM manifests WHERE job_id=?1",
            [id],
            |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, i64>(2)?,
                    r.get::<_, Option<String>>(3)?,
                ))
            },
        )
        .optional()?;
    row.map(|(bytes, sha256, phase, object)| {
        let object = object
            .map(|s| ObjectIdentity::decode(&s).ok_or(StoreError::CorruptState))
            .transpose()?;
        let m = ManifestRecord {
            job_id: id,
            bytes,
            sha256,
            phase,
            object,
        };
        validate_manifest(&m)?;
        Ok(m)
    })
    .transpose()
}
fn check_retained_bytes(c: &Connection, extra: u64, limit: u64, destination: bool) -> Result<()> {
    let mut total = u128::from(extra);
    if destination {
        let mut s=c.prepare("SELECT c.source_identity FROM transfers t JOIN claims c ON c.job_id=t.job_id AND c.file_index=t.file_index")?;
        for row in s.query_map([], |r| r.get::<_, String>(0))? {
            total += u128::from(
                ObjectIdentity::decode(&row?)
                    .ok_or(StoreError::CorruptState)?
                    .size,
            );
        }
    } else {
        let mut s = c.prepare("SELECT source_identity FROM claims")?;
        for row in s.query_map([], |r| r.get::<_, String>(0))? {
            total += u128::from(
                ObjectIdentity::decode(&row?)
                    .ok_or(StoreError::CorruptState)?
                    .size,
            );
        }
    }
    if total > u128::from(limit) {
        return Err(StoreError::AdmissionFull);
    }
    Ok(())
}
