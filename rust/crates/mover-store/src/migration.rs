//! Explicit offline conversion only. Never called by normal Store startup.
use super::*;
use inspection::{LEGACY_COLUMNS, compare_rows};

impl StateInspection {
    /// Caller MUST continuously hold InstanceGuard and its lifetime epoch through
    /// this call and every connection close. The snapshot must have been freshly
    /// verified and durably published under that same guard. No receipt from a
    /// prior process authorizes apply. Checkpoints permit guard revalidation and
    /// qualification-only faults; production callers must not inject failures.
    /// Any error may be postcommit: inspect original state, never auto-restore.
    pub fn migrate_legacy(
        self,
        path: impl AsRef<Path>,
        snapshot: impl AsRef<Path>,
        mut checkpoint: impl FnMut(&'static str) -> std::io::Result<()>,
    ) -> Result<InspectionSummary> {
        self.verify_snapshot(&snapshot)?;
        let backup = Self::open_mode(snapshot.as_ref(), false)?;
        if self.summary().schema_version != 11 {
            return Err(StoreError::UnsupportedSchema);
        }
        let mut c = Connection::open_with_flags(
            path.as_ref(),
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_FULL_MUTEX
                | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        c.busy_timeout(Duration::from_secs(5))?;
        c.execute_batch("PRAGMA trusted_schema=OFF; PRAGMA writable_schema=OFF; PRAGMA legacy_alter_table=OFF; PRAGMA synchronous=FULL; PRAGMA foreign_keys=OFF;")?;
        let fk: i64 = c.pragma_query_value(None, "foreign_keys", |r| r.get(0))?;
        if fk != 0 {
            return Err(StoreError::UnsupportedSqliteConfiguration);
        }
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let version: i64 = tx.pragma_query_value(None, "user_version", |r| r.get(0))?;
        let application: i64 = tx.pragma_query_value(None, "application_id", |r| r.get(0))?;
        let journal: String = tx.pragma_query_value(None, "journal_mode", |r| r.get(0))?;
        if version != 11 || application != APPLICATION_ID || journal != "wal" {
            return Err(StoreError::UnsupportedSchema);
        }
        check_sqlite_options(&tx)?;
        validate_schema_for(&tx, 11)?;
        validate_job_sequence(&tx)?;
        validate_contents(&tx, 11)?;
        compare_rows(&tx, &backup.connection, false)?;
        let sequence: Option<i64> = tx
            .query_row(
                "SELECT seq FROM sqlite_sequence WHERE name='jobs'",
                [],
                |r| r.get(0),
            )
            .optional()?;
        checkpoint("before_create")?;
        let (create, indexes) = include_str!("jobs.sql")
            .split_once("ALTER TABLE jobs_v12 RENAME TO jobs;")
            .ok_or(StoreError::CorruptState)?;
        tx.execute_batch(create)?;
        checkpoint("after_create")?;
        tx.execute_batch(&format!("INSERT INTO jobs_v12({LEGACY_COLUMNS},identity_kind,recording_uuid,request_identity_version,request_identity_sha256) SELECT {LEGACY_COLUMNS},0,NULL,NULL,NULL FROM jobs;"))?;
        checkpoint("after_copy")?;
        tx.execute_batch("DROP TABLE jobs;")?;
        checkpoint("after_drop")?;
        tx.execute_batch("ALTER TABLE jobs_v12 RENAME TO jobs;")?;
        checkpoint("after_rename")?;
        tx.execute_batch(indexes)?;
        checkpoint("after_indexes")?;
        tx.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('jobs','jobs_v12')",
            [],
        )?;
        if let Some(sequence) = sequence {
            tx.execute(
                "INSERT INTO sqlite_sequence(name,seq) VALUES('jobs',?1)",
                [sequence],
            )?;
        }
        checkpoint("after_sequence")?;
        validate_schema_for(&tx, 12)?;
        validate_identities(&tx)?;
        validate_job_sequence(&tx)?;
        validate_contents(&tx, 12)?;
        let integrity: String = tx.query_row("PRAGMA integrity_check", [], |r| r.get(0))?;
        if integrity != "ok" {
            return Err(StoreError::CorruptState);
        }
        compare_rows(&tx, &backup.connection, true)?;
        checkpoint("after_validation")?;
        tx.pragma_update(None, "user_version", 12)?;
        checkpoint("before_commit")?;
        tx.commit()?;
        checkpoint("after_commit")?;
        c.pragma_update(None, "foreign_keys", "ON")?;
        let fk: i64 = c.pragma_query_value(None, "foreign_keys", |r| r.get(0))?;
        if fk != 1 {
            return Err(StoreError::UnsupportedSqliteConfiguration);
        }
        drop(c);
        drop(self);
        let target = Self::open(path.as_ref())?;
        Ok(target.summary)
    }

    /// Explicit offline 12 -> 13: add the empty admin retry receipt tables in a
    /// single immediate transaction. Existing rows are untouched by construction
    /// (CREATE TABLE only); schema, identities, sequence and contents are validated
    /// before and after. Caller MUST hold InstanceGuard throughout and must have
    /// taken a fresh verified backup first. Any error may be postcommit: inspect
    /// the original state, never auto-restore.
    /// 12 -> 13: add the empty admin retry receipt tables.
    pub fn upgrade_retry_receipts(
        self,
        path: impl AsRef<Path>,
        checkpoint: impl FnMut(&'static str) -> std::io::Result<()>,
    ) -> Result<InspectionSummary> {
        self.additive_upgrade(path, 12, create_retry_receipt_tables, checkpoint)
    }
    /// 13 -> 14: add the empty per-job problem table.
    pub fn upgrade_job_problems(
        self,
        path: impl AsRef<Path>,
        checkpoint: impl FnMut(&'static str) -> std::io::Result<()>,
    ) -> Result<InspectionSummary> {
        self.additive_upgrade(path, 13, create_problem_tables, checkpoint)
    }
    /// 14 -> 15: add the empty admin cancellation table.
    pub fn upgrade_cancellations(
        self,
        path: impl AsRef<Path>,
        checkpoint: impl FnMut(&'static str) -> std::io::Result<()>,
    ) -> Result<InspectionSummary> {
        self.additive_upgrade(path, 14, create_cancellation_tables, checkpoint)
    }
    /// One guarded additive step `from` -> `from + 1` that only creates new,
    /// empty tables, validating schema, identities, sequence and contents on
    /// both sides in one immediate transaction.
    fn additive_upgrade(
        self,
        path: impl AsRef<Path>,
        from: i64,
        create: fn(&Connection) -> Result<()>,
        mut checkpoint: impl FnMut(&'static str) -> std::io::Result<()>,
    ) -> Result<InspectionSummary> {
        if self.summary().schema_version != from {
            return Err(StoreError::UnsupportedSchema);
        }
        let mut c = Connection::open_with_flags(
            path.as_ref(),
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_FULL_MUTEX
                | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        c.busy_timeout(Duration::from_secs(5))?;
        c.execute_batch("PRAGMA trusted_schema=OFF; PRAGMA writable_schema=OFF; PRAGMA legacy_alter_table=OFF; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON;")?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let version: i64 = tx.pragma_query_value(None, "user_version", |r| r.get(0))?;
        let application: i64 = tx.pragma_query_value(None, "application_id", |r| r.get(0))?;
        let journal: String = tx.pragma_query_value(None, "journal_mode", |r| r.get(0))?;
        if version != from || application != APPLICATION_ID || journal != "wal" {
            return Err(StoreError::UnsupportedSchema);
        }
        check_sqlite_options(&tx)?;
        validate_schema_for(&tx, from)?;
        validate_identities(&tx)?;
        validate_job_sequence(&tx)?;
        validate_contents(&tx, from)?;
        checkpoint("before_create")?;
        create(&tx)?;
        checkpoint("after_create")?;
        validate_schema_for(&tx, from + 1)?;
        validate_identities(&tx)?;
        validate_job_sequence(&tx)?;
        validate_contents(&tx, from + 1)?;
        let integrity: String = tx.query_row("PRAGMA integrity_check", [], |r| r.get(0))?;
        if integrity != "ok" {
            return Err(StoreError::CorruptState);
        }
        tx.pragma_update(None, "user_version", from + 1)?;
        checkpoint("before_commit")?;
        tx.commit()?;
        checkpoint("after_commit")?;
        drop(c);
        drop(self);
        Ok(Self::open(path.as_ref())?.summary)
    }
}
