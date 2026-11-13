use super::*;

impl Store {
    /// Forget completed jobs without any source/destination filesystem access.
    /// Requires open_for_history_clear and caller-held exclusive instance/lifetime
    /// admission. A committed manifest alone does not prove worker quiescence.
    /// Cancellation is not implemented yet: every noncommitted job is skipped.
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
                let Some(job) = load(&tx, id)? else {
                    continue;
                };
                if !job.recording.is_committed() {
                    continue;
                }
                // Children first: retain FK enforcement, shared enrollment,
                // instance identity and sqlite_sequence (old IDs never return).
                for sql in [
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
                cleared += tx.execute("DELETE FROM jobs WHERE job_id=?1", [id])? as u64;
            }
            tx.commit()?;
            Ok(cleared)
        })
    }
}
