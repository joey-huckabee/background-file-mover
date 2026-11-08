//! Offline, existing-state-only inspection. Caller must hold InstanceGuard and
//! its lifetime epoch until this connection and all snapshot handles are closed.
use super::*;

#[derive(Debug, PartialEq, Eq)]
pub struct InspectionSummary {
    pub schema_version: i64,
    pub instance_id: String,
    pub retained_jobs: i64,
}
pub struct InspectedEnrollment {
    pub source_path: String,
    pub binding: String,
    pub observation: String,
    pub state_instance_id: String,
}
pub struct StateInspection {
    pub(super) connection: Connection,
    pub(super) summary: InspectionSummary,
}
impl StateInspection {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        Self::open_mode(path.as_ref(), true)
    }
    pub(super) fn open_mode(path: &Path, source: bool) -> Result<Self> {
        let c = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_ONLY
                | OpenFlags::SQLITE_OPEN_FULL_MUTEX
                | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        c.busy_timeout(Duration::from_secs(5))?;
        c.pragma_update(None, "trusted_schema", "OFF")?;
        let application: i64 = c.pragma_query_value(None, "application_id", |r| r.get(0))?;
        let version: i64 = c.pragma_query_value(None, "user_version", |r| r.get(0))?;
        if application != APPLICATION_ID || ![11, 12].contains(&version) {
            return Err(StoreError::UnsupportedSchema);
        }
        validate_schema_for(&c, version)?;
        if version == 12 {
            validate_identities(&c)?;
        }
        check_sqlite_options(&c)?;
        let journal: String = c.pragma_query_value(None, "journal_mode", |r| r.get(0))?;
        if source && journal != "wal" {
            return Err(StoreError::UnsupportedSqliteConfiguration);
        }
        c.pragma_update(None, "foreign_keys", "ON")?;
        c.pragma_update(None, "synchronous", "FULL")?;
        let integrity: String = c.query_row("PRAGMA integrity_check", [], |r| r.get(0))?;
        if integrity != "ok" {
            return Err(StoreError::CorruptState);
        }
        validate_job_sequence(&c)?;
        let instance_id = validate_contents(&c, version)?;
        let retained_jobs = c.query_row("SELECT count(*) FROM jobs", [], |r| r.get(0))?;
        Ok(Self {
            connection: c,
            summary: InspectionSummary {
                schema_version: version,
                instance_id,
                retained_jobs,
            },
        })
    }
    pub fn summary(&self) -> &InspectionSummary {
        &self.summary
    }
    pub fn enrollment(&self) -> Result<Option<InspectedEnrollment>> {
        Ok(self.connection.query_row("SELECT source_path,binding,observation,state_instance_id FROM source_enrollment WHERE singleton=1",[],|r|Ok(InspectedEnrollment {
            source_path:r.get(0)?,binding:r.get(1)?,observation:r.get(2)?,state_instance_id:r.get(3)?
        })).optional()?)
    }
    pub fn ownership(&self) -> Result<Option<SourceOwnership>> {
        Ok(self
            .connection
            .query_row(
                "SELECT receipt,object FROM source_ownership WHERE singleton=1",
                [],
                |r| {
                    Ok(SourceOwnership {
                        receipt: r.get(0)?,
                        object: r.get(1)?,
                    })
                },
            )
            .optional()?)
    }
    /// Stored paths only; never opens a source/destination filesystem.
    pub fn payload_roots(&self) -> Result<Vec<String>> {
        let mut s = self.connection.prepare("SELECT source_root_path FROM jobs UNION SELECT destination_path FROM jobs UNION SELECT source_path FROM source_enrollment UNION SELECT destination_root FROM transfers")?;
        Ok(s.query_map([], |r| r.get(0))?
            .collect::<rusqlite::Result<_>>()?)
    }
    pub fn visit_jobs(
        &self,
        mut visit: impl FnMut(&Accepted, Option<&ManifestRecord>, &[Option<Transfer>]) -> Result<()>,
    ) -> Result<()> {
        let mut s = self
            .connection
            .prepare("SELECT job_id FROM jobs ORDER BY job_id")?;
        let mut rows = s.query([])?;
        while let Some(row) = rows.next()? {
            let id = row.get(0)?;
            let job = if self.summary.schema_version == 11 {
                load_legacy(&self.connection, id)?
            } else {
                load(&self.connection, id)?
            }
            .ok_or(StoreError::CorruptState)?;
            let manifest = load_manifest(&self.connection, id)?;
            let transfers = (0..job.recording.submission().files().len())
                .map(|i| load_transfer(&self.connection, id, i))
                .collect::<Result<Vec<_>>>()?;
            visit(&job, manifest.as_ref(), &transfers)?;
        }
        Ok(())
    }
    /// Output must be a new empty private file, exclusively owned by the caller.
    /// VACUUM INTO includes committed WAL frames; copying the main file does not.
    pub fn snapshot_into(&self, path: &str) -> Result<()> {
        self.connection.execute("VACUUM main INTO ?1", [path])?;
        Ok(())
    }
    /// Compare typed values in deterministic primary-key order, including shared
    /// metadata and sequence high-water marks. Physical ROWIDs are not identity.
    pub fn verify_snapshot(&self, path: impl AsRef<Path>) -> Result<()> {
        let snapshot = Self::open_mode(path.as_ref(), false)?;
        if self.summary != snapshot.summary {
            return Err(StoreError::CorruptState);
        }
        compare_rows(&self.connection, &snapshot.connection, false)
    }
}

pub(super) const LEGACY_COLUMNS: &str = "job_id,generator_id,submission_id,source_directory,source_root_id,source_root_path,source_relative_directory,destination_id,destination_path,group_by_generator,delete_source_after_commit,missing_retry_seconds,file_count";

// Stream exact typed values. Target jobs project only the original columns;
// validate_identities separately validates the four new columns.
pub(super) fn compare_rows(
    source: &Connection,
    snapshot: &Connection,
    legacy_projection: bool,
) -> Result<()> {
    for (table, order) in [
        ("jobs", "job_id"),
        ("files", "job_id,file_index"),
        ("reservations", "source_root_id,source_relative_path"),
        ("claims", "job_id,file_index"),
        ("missing", "job_id,file_index"),
        ("transfers", "job_id,file_index,attempt"),
        ("metadata", "key"),
        ("manifests", "job_id"),
        ("delivery_failures", "job_id"),
        ("operator_resumes", "job_id,command_id"),
        ("missing_resets", "job_id,command_id"),
        ("source_enrollment", "singleton"),
        ("destination_bindings", "job_id"),
        ("source_ownership", "singleton"),
        ("sqlite_sequence", "name,seq"),
    ] {
        let columns = if table == "jobs" && legacy_projection {
            LEGACY_COLUMNS
        } else {
            "*"
        };
        let sql = format!("SELECT {columns} FROM {table} ORDER BY {order}");
        let mut a = source.prepare(&sql)?;
        let mut b = snapshot.prepare(&sql)?;
        let width = a.column_count();
        if width != b.column_count() {
            return Err(StoreError::CorruptState);
        }
        let mut ar = a.query([])?;
        let mut br = b.query([])?;
        loop {
            match (ar.next()?, br.next()?) {
                (None, None) => break,
                (Some(a), Some(b)) => {
                    for i in 0..width {
                        if a.get_ref(i)? != b.get_ref(i)? {
                            return Err(StoreError::CorruptState);
                        }
                    }
                }
                _ => return Err(StoreError::CorruptState),
            }
        }
    }
    Ok(())
}
