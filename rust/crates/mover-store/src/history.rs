use super::*;

/// Result of one online clear occurrence.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClearOutcome {
    /// The job and all its linkage were forgotten.
    Cleared,
    /// Missing, or not (yet) safely completed or cancelled: nothing changed.
    Skipped,
    /// A worker may still be on the job; nothing changed, try again shortly.
    Busy,
}

/// Clear eligibility: delivered, or cancelled with the stop confirmed. Pending
/// cancellations and all other unfinished work are not eligible.
fn eligible(tx: &Connection, id: i64) -> Result<Option<bool>> {
    let Some(job) = load(tx, id)? else {
        return Ok(None);
    };
    // An active deletion pass is an unsettled file effect: wait for it.
    Ok(Some(
        (job.recording.is_committed()
            || cancellations::get(tx, id)?
                .is_some_and(|c| c.state == cancellations::CancelState::Cancelled))
            && !deletions::active(tx, id)?,
    ))
}

/// Forget one job: children first, retaining FK enforcement, shared
/// enrollment, instance identity and sqlite_sequence (old IDs never return).
/// No filesystem access: files stay in place and leave mover management.
fn forget(tx: &Connection, id: i64) -> Result<u64> {
    for sql in [
        "DELETE FROM deletion_targets WHERE job_id=?1",
        "DELETE FROM deletion_passes WHERE job_id=?1",
        "DELETE FROM cancellations WHERE job_id=?1",
        "DELETE FROM job_problems WHERE job_id=?1",
        "DELETE FROM retry_outcomes WHERE job_id=?1",
        "DELETE FROM retry_contexts WHERE job_id=?1",
        "DELETE FROM missing_resets WHERE job_id=?1",
        "DELETE FROM operator_resumes WHERE job_id=?1",
        "DELETE FROM delivery_failures WHERE job_id=?1",
        "DELETE FROM manifests WHERE job_id=?1",
        "DELETE FROM transfers WHERE job_id=?1",
        "DELETE FROM missing WHERE job_id=?1",
        "DELETE FROM claims WHERE job_id=?1",
        "DELETE FROM reservations WHERE job_id=?1",
        "DELETE FROM destination_bindings WHERE job_id=?1",
        "DELETE FROM files WHERE job_id=?1",
    ] {
        tx.execute(sql, [id])?;
    }
    Ok(tx.execute("DELETE FROM jobs WHERE job_id=?1", [id])? as u64)
}

impl Store {
    /// Offline clear: forget delivered or safely cancelled jobs without any
    /// source/destination filesystem access. Requires open_for_history_clear and
    /// caller-held exclusive instance/lifetime admission (no workers running).
    pub fn clear_completed_history(&self, job_ids: &[i64]) -> Result<u64> {
        if job_ids.is_empty() || job_ids.len() > 256 || job_ids.iter().any(|id| *id <= 0) {
            return Err(StoreError::InvalidContext);
        }
        let job_ids = job_ids.to_vec();
        self.call(move |db| {
            if !db.history_clear {
                return Err(StoreError::InvalidContext);
            }
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let mut cleared = 0;
            for id in job_ids {
                if eligible(&tx, id)? == Some(true) {
                    cleared += forget(&tx, id)?;
                }
            }
            tx.commit()?;
            Ok(cleared)
        })
    }

    /// Online clear of one job while the service runs. `busy(job_id)` reports
    /// whether a worker may still be on the job; it is evaluated inside this
    /// immediate transaction, which is serialized with every worker's own store
    /// calls, so once a job is forgotten no worker can continue with it.
    pub fn admin_clear(
        &self,
        job_id: i64,
        busy: impl Fn(i64) -> bool + Send + 'static,
    ) -> Result<ClearOutcome> {
        if job_id <= 0 {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            if eligible(&tx, job_id)? != Some(true) {
                return Ok(ClearOutcome::Skipped);
            }
            if busy(job_id) {
                return Ok(ClearOutcome::Busy);
            }
            forget(&tx, job_id)?;
            tx.commit()?;
            Ok(ClearOutcome::Cleared)
        })
    }
}
