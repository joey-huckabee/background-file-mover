//! Timer-driven missing-file retries (docs/MISSING-FILE-RETRY-DESIGN.md): the
//! store side. Discovery of jobs to visit, fresh admission before a new claim
//! is authorized, and clock-anomaly lookups. No new state: the `missing` and
//! `claims` tables already record first absence, deadlines, blocks and
//! intents.
use super::*;

/// Persist an expired deadline as a block and report whether the job may
/// authorize a **new** claim now: not blocked, no cancellation requested.
pub(super) fn admissible(tx: &Connection, job_id: i64, now: i64) -> Result<bool> {
    tx.execute(
        "UPDATE missing SET blocked=1 WHERE job_id=?1 AND deadline<=?2",
        params![job_id, now],
    )?;
    let blocked: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM missing WHERE job_id=?1 AND blocked=1)",
        [job_id],
        |r| r.get(0),
    )?;
    Ok(!blocked && !cancellations::requested(tx, job_id)?)
}

impl Store {
    /// Jobs a retry pass may visit, ascending, with their missing-review epoch
    /// (a reviewed reset makes a job due again): handoff not complete, and a
    /// recorded first absence, an unfinished claim intent, or a partial claim
    /// (a first absence's row is removed once that file is claimed, while
    /// later files may still wait). Further gates (settled cancellation,
    /// blocks, recovery vs new claims) are the caller's.
    pub fn missing_retry_jobs(&self) -> Result<Vec<(i64, u32)>> {
        self.call(|db| {
            let mut s = db
                .connection
                .prepare("SELECT job_id FROM missing UNION SELECT job_id FROM claims ORDER BY 1")?;
            let ids = s
                .query_map([], |r| r.get::<_, i64>(0))?
                .collect::<std::result::Result<Vec<_>, _>>()?;
            let mut out = Vec::new();
            for id in ids {
                if let Some(job) = load(&db.connection, id)?
                    && job.recording.handoff() != mover_core::Handoff::Ready202
                {
                    out.push((id, missing_resets::epoch(&db.connection, id)?));
                }
            }
            Ok(out)
        })
    }

    /// Fresh admission for a new claim (before allocation): persists an
    /// expired deadline as a block; false when blocked or a cancellation was
    /// requested.
    pub fn claim_admissible(&self, job_id: i64, now: i64) -> Result<bool> {
        if now < 0 {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let ok = admissible(&tx, job_id, now)?;
            tx.commit()?;
            Ok(ok)
        })
    }

    /// `begin_claim` with fresh admission in the same transaction: Ok(false)
    /// (nothing recorded, an expired deadline persisted as a block) when the
    /// job is blocked or a cancellation was requested.
    pub fn begin_claim_admitted(&self, intent: &ClaimIntent, now: i64) -> Result<bool> {
        if now < 0 {
            return Err(StoreError::InvalidContext);
        }
        let intent = intent.clone();
        self.call(move |db| db.begin_claim_inner(&intent, Some(now)))
    }

    /// Jobs whose missing-file deadline lies in `(after, until]` (clock-jump
    /// diagnostics: windows a forward jump may have ended early).
    pub fn missing_deadlines_between(&self, after: i64, until: i64) -> Result<Vec<i64>> {
        self.call(move |db| {
            let mut s = db.connection.prepare(
                "SELECT DISTINCT job_id FROM missing WHERE deadline>?1 AND deadline<=?2 ORDER BY 1",
            )?;
            Ok(s.query_map(params![after, until], |r| r.get::<_, i64>(0))?
                .collect::<std::result::Result<Vec<_>, _>>()?)
        })
    }

    /// Jobs whose first recorded absence lies after `now` (wall clock set back
    /// below a window's start): `deadline - window > now`.
    pub fn missing_recorded_after(&self, now: i64) -> Result<Vec<i64>> {
        self.call(move |db| {
            let mut s = db.connection.prepare(
                "SELECT DISTINCT m.job_id FROM missing m JOIN jobs j ON j.job_id=m.job_id \
                 WHERE m.deadline - j.missing_retry_seconds > ?1 ORDER BY 1",
            )?;
            Ok(s.query_map([now], |r| r.get::<_, i64>(0))?
                .collect::<std::result::Result<Vec<_>, _>>()?)
        })
    }
}
