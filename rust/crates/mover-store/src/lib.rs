//! Local SQLite acceptance/replay. One bounded-command owner thread holds SQL.
//! Calls block; dispatch them outside an async executor. No claims or 202 yet.

use mover_core::{DeliveryPolicy, FileSpec, ProtocolError, Recording, Submission};
use rusqlite::{Connection, OpenFlags, OptionalExtension, TransactionBehavior, params};
use std::{
    fmt,
    path::{Path, PathBuf},
    sync::mpsc,
    thread,
    time::Duration,
};

const APPLICATION_ID: i64 = 0x42464d52;
const SCHEMA_VERSION: i64 = 1;

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
    pub fn job_count(&self) -> Result<u64> {
        self.call(|db| {
            let count: i64 = db
                .connection
                .query_row("SELECT count(*) FROM jobs", [], |row| row.get(0))?;
            u64::try_from(count).map_err(|_| StoreError::CorruptState)
        })
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
        } else if version != SCHEMA_VERSION || application != APPLICATION_ID {
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
            tx.pragma_update(None, "application_id", APPLICATION_ID)?;
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
        let damaged: bool = connection.query_row("SELECT EXISTS(SELECT 1 FROM jobs j WHERE j.file_count != (SELECT count(*) FROM files f WHERE f.job_id=j.job_id) OR j.file_count != (SELECT count(*) FROM reservations r WHERE r.job_id=j.job_id)) OR EXISTS(SELECT 1 FROM reservations r JOIN jobs j ON j.job_id=r.job_id JOIN files f ON f.job_id=r.job_id AND f.file_index=r.file_index WHERE r.source_root_id != j.source_root_id OR r.source_relative_path != CASE WHEN j.source_relative_directory='' THEN f.relative_path ELSE j.source_relative_directory || '/' || f.relative_path END)", [], |r| r.get(0))?;
        let foreign_key_errors: i64 =
            connection.query_row("SELECT count(*) FROM pragma_foreign_key_check", [], |r| {
                r.get(0)
            })?;
        if damaged || foreign_key_errors != 0 {
            return Err(StoreError::CorruptState);
        }
        Ok(Self { connection })
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
    Ok(Some(Accepted {
        job_id,
        recording,
        context,
        replay: false,
    }))
}

#[cfg(test)]
mod tests;
