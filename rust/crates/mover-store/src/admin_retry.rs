//! Reviewed admin delivery retry with durable per-occurrence receipts
//! (schema 13; docs/api/API-CONTRACT-CLOSEOUT.md "Retry receipts").
//!
//! A receipt belongs to one existing job and stores only that job's exact own
//! command projection (principal, instance, frozen epoch, reason) plus one
//! outcome per occurrence position. It never stores other selected job IDs.
//! Accepted occurrences reuse the existing resume audit (operator_resumes), so
//! the 64-command audit cap and review epoch semantics are unchanged.
use super::*;

/// Bound on distinct canonical request contexts kept per tracked job.
pub const MAX_RETRY_CONTEXTS_PER_JOB: i64 = 64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RetryOccurrence {
    pub job_id: i64,
    /// Opaque 64-hex key derived from the canonical request context.
    pub context_key: String,
    /// Server-authenticated account principal; never client-supplied.
    pub principal: String,
    pub instance_id: String,
    /// Frozen review epoch; None is permanently nonauthorizing (skipped).
    pub review_epoch: Option<u32>,
    pub reason: String,
    /// Position of this occurrence in the submitted selection (0-255).
    pub occurrence: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RetryOutcome {
    Accepted,
    Failed,
    Skipped,
}
impl RetryOutcome {
    fn as_str(self) -> &'static str {
        match self {
            Self::Accepted => "accepted",
            Self::Failed => "failed",
            Self::Skipped => "skipped",
        }
    }
    fn parse(s: &str) -> Result<Self> {
        match s {
            "accepted" => Ok(Self::Accepted),
            "failed" => Ok(Self::Failed),
            "skipped" => Ok(Self::Skipped),
            _ => Err(StoreError::CorruptState),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RetryResult {
    pub outcome: RetryOutcome,
    /// True when an exact stored receipt was returned unchanged.
    pub replay: bool,
}

fn valid_text(s: &str, max: usize) -> bool {
    !s.trim().is_empty() && s.len() <= max && !s.chars().any(char::is_control)
}
fn lower_hex(s: &str, len: usize) -> bool {
    s.len() == len
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl Store {
    /// Highest job ID ever allocated (AUTOINCREMENT high-water mark); IDs are
    /// never reused, so a missing ID at or below it was cleared.
    pub fn job_id_high_water(&self) -> Result<i64> {
        self.call(|db| {
            Ok(db
                .connection
                .query_row(
                    "SELECT seq FROM sqlite_sequence WHERE name='jobs'",
                    [],
                    |r| r.get(0),
                )
                .optional()?
                .unwrap_or(0))
        })
    }

    /// Decide one occurrence in one immediate transaction: exact receipt replay
    /// first, then (for a new occurrence) capacity, frozen-epoch eligibility,
    /// audit and scheduling together with the persisted outcome.
    pub fn admin_retry(&self, request: &RetryOccurrence, now: i64) -> Result<RetryResult> {
        let o = request.clone();
        if now < 0
            || o.job_id <= 0
            || o.occurrence > 255
            || !lower_hex(&o.context_key, 64)
            || !lower_hex(&o.instance_id, 32)
            || !valid_text(&o.principal, 128)
            || !valid_text(&o.reason, 512)
        {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let instance: String = tx.query_row(
                "SELECT value FROM metadata WHERE key='instance_id'",
                [],
                |r| r.get(0),
            )?;
            if instance != o.instance_id {
                return Err(StoreError::ReviewConflict);
            }
            // 1. Exact receipt: return its original outcome, whatever changed since.
            let prior: Option<(String, String, String, u32, String)> = tx
                .query_row(
                    "SELECT o.outcome,c.principal,c.instance_id,c.review_epoch,c.reason \
                     FROM retry_outcomes o JOIN retry_contexts c USING(job_id,context_key) \
                     WHERE o.job_id=?1 AND o.context_key=?2 AND o.occurrence=?3",
                    params![o.job_id, o.context_key, o.occurrence],
                    |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
                )
                .optional()?;
            if let Some((outcome, principal, instance, epoch, reason)) = prior {
                if principal != o.principal
                    || instance != o.instance_id
                    || Some(epoch) != o.review_epoch
                    || reason != o.reason
                {
                    return Err(StoreError::ActionConflict);
                }
                tx.commit()?;
                return Ok(RetryResult {
                    outcome: RetryOutcome::parse(&outcome)?,
                    replay: true,
                });
            }
            // 2. Deterministic skips that need no historical row.
            let Some(frozen) = o.review_epoch else {
                return Ok(RetryResult {
                    outcome: RetryOutcome::Skipped,
                    replay: false,
                });
            };
            let Some(job) = load(&tx, o.job_id)? else {
                return Ok(RetryResult {
                    outcome: RetryOutcome::Skipped,
                    replay: false,
                });
            };
            // 3. Own context row (shared by this request's occurrences of the job).
            let context: Option<(String, String, u32, String)> = tx
                .query_row(
                    "SELECT principal,instance_id,review_epoch,reason FROM retry_contexts \
                     WHERE job_id=?1 AND context_key=?2",
                    params![o.job_id, o.context_key],
                    |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
                )
                .optional()?;
            match context {
                Some((principal, instance, epoch, reason)) => {
                    if principal != o.principal
                        || instance != o.instance_id
                        || epoch != frozen
                        || reason != o.reason
                    {
                        return Err(StoreError::ActionConflict);
                    }
                }
                None => {
                    let contexts: i64 = tx.query_row(
                        "SELECT count(*) FROM retry_contexts WHERE job_id=?1",
                        [o.job_id],
                        |r| r.get(0),
                    )?;
                    if contexts >= MAX_RETRY_CONTEXTS_PER_JOB {
                        return Err(StoreError::ReceiptCapacity);
                    }
                    tx.execute(
                        "INSERT INTO retry_contexts VALUES(?1,?2,?3,?4,?5,?6)",
                        params![
                            o.job_id,
                            o.context_key,
                            o.principal,
                            o.instance_id,
                            frozen,
                            o.reason
                        ],
                    )?;
                }
            }
            // 4. Classify against current state with the frozen epoch. A later
            // occurrence of an already-accepted context is a duplicate and fails,
            // even if delivery committed (or the service restarted) in between.
            let accepted_before: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM retry_outcomes WHERE job_id=?1 AND context_key=?2 AND outcome='accepted')",
                params![o.job_id, o.context_key],
                |r| r.get(0),
            )?;
            let outcome = if accepted_before {
                RetryOutcome::Failed
            } else if job.recording.is_committed() {
                RetryOutcome::Skipped
            } else if cancellations::requested(&tx, o.job_id)? {
                // A cancelled (or cancelling) job is ineligible for retry.
                RetryOutcome::Failed
            } else {
                let current = operators::epoch(&tx, o.job_id)?;
                let failure: Option<(u32, i64, String)> = tx
                    .query_row(
                        "SELECT failures,retry_after,code FROM delivery_failures WHERE job_id=?1",
                        [o.job_id],
                        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
                    )
                    .optional()?;
                match failure {
                    Some((3, retry_after, code))
                        if job.recording.handoff() == mover_core::Handoff::Ready202
                            && current == frozen
                            && current < 64 =>
                    {
                        // Same effect and audit as the trusted-local resume command.
                        let command_id = format!("admin-retry:{}:{}", o.context_key, o.occurrence);
                        tx.execute(
                            "INSERT INTO operator_resumes VALUES(?1,?2,?3,?4,?5,?6,?7,?8)",
                            params![
                                o.job_id,
                                command_id,
                                current,
                                o.principal,
                                o.reason,
                                now,
                                retry_after,
                                code
                            ],
                        )?;
                        tx.execute("DELETE FROM delivery_failures WHERE job_id=?1", [o.job_id])?;
                        RetryOutcome::Accepted
                    }
                    _ => RetryOutcome::Failed,
                }
            };
            tx.execute(
                "INSERT INTO retry_outcomes VALUES(?1,?2,?3,?4)",
                params![o.job_id, o.context_key, o.occurrence, outcome.as_str()],
            )?;
            tx.commit()?;
            Ok(RetryResult {
                outcome,
                replay: false,
            })
        })
    }
}
