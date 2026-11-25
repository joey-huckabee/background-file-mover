//! Move mode: automatic removal of the mover's held source copies after
//! verified delivery (schema 18; docs/MOVE-MODE-DESIGN.md).
//!
//! A file is eligible when its job was accepted as a move
//! (`delete_source_after_commit`), the job committed (manifest phase 4), the
//! file is Published, its claim is complete, and the job has no active
//! confirmed deletion pass. The currently loaded service setting is checked by
//! the caller (no work is discovered while it is off).
//!
//! One row per file. `authorized` is monotonic: set when intent is recorded
//! (before any removal is sent), never cleared. Replay validation treats a held
//! copy as released only once it is set. A failure before authorization (set
//! verification) keeps `authorized = 0`, so custody is still required.
use super::*;

/// Retry backoff after a failure: 30 s, doubling, capped at one hour.
pub fn backoff_seconds(attempts: u32) -> i64 {
    let shift = attempts.saturating_sub(1).min(7);
    (30_i64 << shift).min(3600)
}

/// One job's cleanup round, with the records the worker verifies against.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CleanupWork {
    pub job_id: i64,
    /// Eligible files of this round, ascending (at most the caller's limit).
    pub files: Vec<usize>,
    /// Every file's published attempt, in order (the intact set).
    pub published: Vec<Transfer>,
    /// The committed manifest (phase 4).
    pub manifest: ManifestRecord,
}

/// Move-job cleanup progress for status (None for copy jobs).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceCleanupView {
    pub removed: u32,
    pub pending: u32,
    pub failed: u32,
    pub next_attempt_at: Option<i64>,
    pub last_error: Option<String>,
}

pub(super) fn table_exists(c: &Connection) -> Result<bool> {
    Ok(c.query_row(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_cleanups')",
        [],
        |r| r.get(0),
    )?)
}

/// Files whose held copy was removed (for load: file phase SourceRemoved).
pub(super) fn removed(c: &Connection, job_id: i64) -> Result<Vec<usize>> {
    if !table_exists(c)? {
        return Ok(Vec::new());
    }
    let mut s = c.prepare(
        "SELECT file_index FROM source_cleanups WHERE job_id=?1 AND state='Removed' ORDER BY file_index",
    )?;
    Ok(s.query_map([job_id], |r| r.get::<_, i64>(0))?
        .map(|r| r.map(|i| i as usize))
        .collect::<std::result::Result<Vec<_>, _>>()?)
}

/// Whether one file is eligible now (see module docs).
fn file_eligible(c: &Connection, job: &Accepted, index: usize, now: i64) -> Result<bool> {
    if job.recording.file_phase(index) != Some(mover_core::FilePhase::Published) {
        return Ok(false);
    }
    if !load_claim(c, job.job_id, index)?.is_some_and(|(_, done)| done) {
        return Ok(false);
    }
    let row: Option<(String, Option<i64>)> = c
        .query_row(
            "SELECT state,next_attempt_at FROM source_cleanups WHERE job_id=?1 AND file_index=?2",
            params![job.job_id, index as i64],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()?;
    Ok(match row {
        None => true,
        Some((state, _)) if state == "Intent" => true,
        Some((state, Some(at))) if state == "Failed" => at <= now,
        _ => false,
    })
}

/// Job-level eligibility: move policy, committed, no active deletion pass.
fn job_eligible(c: &Connection, job_id: i64) -> Result<Option<Accepted>> {
    let Some(job) = load(c, job_id)? else {
        return Ok(None);
    };
    if !job.context.policy.delete_source_after_commit
        || !job.recording.is_committed()
        || load_manifest(c, job_id)?.is_none_or(|m| m.phase != 4)
        || deletions::active(c, job_id)?
    {
        return Ok(None);
    }
    Ok(Some(job))
}

fn round(c: &Connection, job: &Accepted, now: i64, limit: usize) -> Result<Option<CleanupWork>> {
    let mut files = Vec::new();
    for index in 0..job.recording.submission().files().len() {
        if files.len() < limit && file_eligible(c, job, index, now)? {
            files.push(index);
        }
    }
    if files.is_empty() {
        return Ok(None);
    }
    let mut published = Vec::new();
    for index in 0..job.recording.submission().files().len() {
        let t = load_transfer(c, job.job_id, index)?.ok_or(StoreError::CorruptState)?;
        if t.phase != TransferPhase::Published {
            return Err(StoreError::CorruptState);
        }
        published.push(t);
    }
    Ok(Some(CleanupWork {
        job_id: job.job_id,
        files,
        published,
        manifest: load_manifest(c, job.job_id)?.ok_or(StoreError::CorruptState)?,
    }))
}

pub(super) fn view(c: &Connection, job: &Accepted) -> Result<Option<SourceCleanupView>> {
    if !job.context.policy.delete_source_after_commit || !table_exists(c)? {
        return Ok(None);
    }
    let count = |state: &str| -> Result<u32> {
        Ok(c.query_row(
            "SELECT count(*) FROM source_cleanups WHERE job_id=?1 AND state=?2",
            params![job.job_id, state],
            |r| r.get(0),
        )?)
    };
    let removed = count("Removed")?;
    let failed = count("Failed")?;
    let total = job.recording.submission().files().len() as u32;
    let (next_attempt_at, last_error): (Option<i64>, Option<String>) = c.query_row(
        "SELECT min(next_attempt_at),(SELECT diagnostic FROM source_cleanups WHERE job_id=?1 \
             AND state='Failed' ORDER BY updated_at DESC,file_index LIMIT 1) \
             FROM source_cleanups WHERE job_id=?1 AND state='Failed'",
        [job.job_id],
        |r| Ok((r.get(0)?, r.get(1)?)),
    )?;
    Ok(Some(SourceCleanupView {
        removed,
        pending: total.saturating_sub(removed + failed),
        failed,
        next_attempt_at,
        last_error,
    }))
}

impl Store {
    /// The next job with eligible files (at most `limit` per round).
    pub fn next_source_cleanup(&self, now: i64, limit: usize) -> Result<Option<CleanupWork>> {
        if now < 0 || limit == 0 {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let c = &db.connection;
            let mut s = c.prepare(
                "SELECT j.job_id FROM jobs j JOIN manifests m ON m.job_id=j.job_id AND m.phase=4 \
                 WHERE j.delete_source_after_commit=1 \
                 AND NOT EXISTS(SELECT 1 FROM deletion_passes p WHERE p.job_id=j.job_id AND p.state='Active') \
                 AND EXISTS(SELECT 1 FROM files f WHERE f.job_id=j.job_id AND NOT EXISTS(\
                 SELECT 1 FROM source_cleanups s WHERE s.job_id=f.job_id AND s.file_index=f.file_index \
                 AND (s.state='Removed' OR (s.state='Failed' AND s.next_attempt_at > ?1)))) \
                 ORDER BY j.job_id",
            )?;
            let ids = s
                .query_map([now], |r| r.get::<_, i64>(0))?
                .collect::<std::result::Result<Vec<_>, _>>()?;
            for id in ids {
                if let Some(job) = job_eligible(c, id)?
                    && let Some(work) = round(c, &job, now, limit)?
                {
                    return Ok(Some(work));
                }
            }
            Ok(None)
        })
    }

    /// Admission recheck after the job was marked busy: still tracked, still
    /// a committed move job without an active pass, and every file of the
    /// round still eligible with the same records.
    pub fn source_cleanup_eligible(&self, work: &CleanupWork, now: i64) -> Result<bool> {
        let work = work.clone();
        self.call(move |db| {
            let c = &db.connection;
            let Some(job) = job_eligible(c, work.job_id)? else {
                return Ok(false);
            };
            for &index in &work.files {
                if !file_eligible(c, &job, index, now)? {
                    return Ok(false);
                }
            }
            if load_manifest(c, work.job_id)?.as_ref() != Some(&work.manifest) {
                return Ok(false);
            }
            for (index, t) in work.published.iter().enumerate() {
                if load_transfer(c, work.job_id, index)?.as_ref() != Some(t) {
                    return Ok(false);
                }
            }
            Ok(true)
        })
    }

    /// Record durable, authorized intent for one file before its removal is
    /// sent. Monotonic: `authorized` is never cleared afterwards.
    pub fn authorize_source_cleanup(&self, job_id: i64, file_index: usize, now: i64) -> Result<()> {
        if now < 0 || file_index > 255 {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let job = job_eligible(&tx, job_id)?.ok_or(StoreError::InvalidContext)?;
            if !file_eligible(&tx, &job, file_index, now)? {
                return Err(StoreError::InvalidContext);
            }
            tx.execute(
                "INSERT INTO source_cleanups VALUES(?1,?2,'Intent',1,0,NULL,NULL,?3) \
                 ON CONFLICT(job_id,file_index) DO UPDATE SET state='Intent',authorized=1,\
                 next_attempt_at=NULL,diagnostic=NULL,updated_at=excluded.updated_at",
                params![job_id, file_index as i64, now],
            )?;
            tx.commit()?;
            Ok(())
        })
    }

    /// Record one round's results in one transaction: `None` = removed (or
    /// already absent after sync); `Some(PRIVATE_LEFTOVERS)` = removed with a
    /// kept folder warning; any other `Some(diagnostic)` = failed. A failure
    /// keeps `authorized` as it was (0 if intent was never recorded).
    pub fn finish_source_cleanup(
        &self,
        job_id: i64,
        outcomes: &[(usize, Option<String>)],
        now: i64,
    ) -> Result<()> {
        if now < 0
            || outcomes.iter().any(|(i, d)| {
                *i > 255 || d.as_deref().is_some_and(|d| !problems::valid_diagnostic(d))
            })
        {
            return Err(StoreError::InvalidContext);
        }
        let outcomes = outcomes.to_vec();
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let job = load(&tx, job_id)?.ok_or(StoreError::InvalidContext)?;
            for (index, failure) in &outcomes {
                let row: Option<(String, i64, u32)> = tx
                    .query_row(
                        "SELECT state,authorized,attempts FROM source_cleanups WHERE job_id=?1 AND file_index=?2",
                        params![job_id, *index as i64],
                        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
                    )
                    .optional()?;
                match failure.as_deref() {
                    None | Some(PRIVATE_LEFTOVERS) => {
                        // Only an authorized removal can be recorded as done.
                        if row.as_ref().is_none_or(|(s, a, _)| s != "Intent" || *a != 1) {
                            return Err(StoreError::CorruptState);
                        }
                        let mut recording = job.recording.clone();
                        recording
                            .confirm_source_removed(*index, true)
                            .map_err(|_| StoreError::CorruptState)?;
                        tx.execute(
                            "UPDATE source_cleanups SET state='Removed',next_attempt_at=NULL,diagnostic=?4,\
                             updated_at=?3 WHERE job_id=?1 AND file_index=?2",
                            params![job_id, *index as i64, now, failure.as_deref()],
                        )?;
                    }
                    Some(diagnostic) => {
                        if row.as_ref().is_some_and(|(s, _, _)| s == "Removed") {
                            return Err(StoreError::CorruptState);
                        }
                        let attempts = row.as_ref().map_or(0, |(_, _, a)| *a).saturating_add(1);
                        let authorized = row.as_ref().map_or(0, |(_, a, _)| *a);
                        tx.execute(
                            "INSERT INTO source_cleanups VALUES(?1,?2,'Failed',?3,?4,?5,?6,?7) \
                             ON CONFLICT(job_id,file_index) DO UPDATE SET state='Failed',\
                             authorized=max(authorized,excluded.authorized),attempts=excluded.attempts,\
                             next_attempt_at=excluded.next_attempt_at,diagnostic=excluded.diagnostic,\
                             updated_at=excluded.updated_at",
                            params![
                                job_id,
                                *index as i64,
                                authorized,
                                attempts,
                                now.saturating_add(backoff_seconds(attempts)),
                                diagnostic,
                                now
                            ],
                        )?;
                    }
                }
            }
            tx.commit()?;
            Ok(())
        })
    }
}
