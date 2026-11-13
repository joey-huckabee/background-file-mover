//! Admin job cancellation (schema 15; API-CONTRACT-CLOSEOUT.md group 53,
//! ROUTE-SCHEMAS "CancellationStatus").
//!
//! A request records `Pending`. Workers stop taking the job immediately (no new
//! claim, no delivery pickup, delivery stops between steps). The service marks
//! it `Cancelled` only after confirming no worker is still on the job. If the
//! delivery committed first, the request is dropped: the job is delivered and
//! verified output is preserved. Files are never moved or deleted by cancel.
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelState {
    Pending,
    Cancelled,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cancellation {
    pub state: CancelState,
    /// Server-authenticated account principal that requested it.
    pub principal: String,
    pub requested_at: i64,
    pub stopped_at: Option<i64>,
}

/// Per-occurrence result, counted into the admin AttemptCounts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelOutcome {
    Accepted,
    Failed,
    Skipped,
}

pub(super) fn get(tx: &Connection, job_id: i64) -> Result<Option<Cancellation>> {
    let row: Option<(String, String, i64, Option<i64>)> = tx
        .query_row(
            "SELECT state,principal,requested_at,stopped_at FROM cancellations WHERE job_id=?1",
            [job_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .optional()?;
    row.map(|(state, principal, requested_at, stopped_at)| {
        Ok(Cancellation {
            state: match state.as_str() {
                "Pending" => CancelState::Pending,
                "Cancelled" => CancelState::Cancelled,
                _ => return Err(StoreError::CorruptState),
            },
            principal,
            requested_at,
            stopped_at,
        })
    })
    .transpose()
}

/// True when any cancellation (pending or settled) exists: no new work starts.
pub(super) fn requested(tx: &Connection, job_id: i64) -> Result<bool> {
    Ok(tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM cancellations WHERE job_id=?1)",
        [job_id],
        |r| r.get(0),
    )?)
}

impl Store {
    /// One cancel occurrence in one immediate transaction. Missing, completed and
    /// already cancelled jobs skip; a still-pending duplicate fails; otherwise
    /// the request is recorded as Pending.
    pub fn admin_cancel(&self, job_id: i64, principal: &str, now: i64) -> Result<CancelOutcome> {
        if now < 0
            || job_id <= 0
            || principal.trim().is_empty()
            || principal.len() > 128
            || principal.chars().any(char::is_control)
        {
            return Err(StoreError::InvalidContext);
        }
        let principal = principal.to_owned();
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let Some(job) = load(&tx, job_id)? else {
                return Ok(CancelOutcome::Skipped);
            };
            if job.recording.is_committed() {
                return Ok(CancelOutcome::Skipped);
            }
            let outcome = match get(&tx, job_id)? {
                Some(c) if c.state == CancelState::Cancelled => CancelOutcome::Skipped,
                Some(_) => CancelOutcome::Failed,
                None => {
                    tx.execute(
                        "INSERT INTO cancellations VALUES(?1,'Pending',?2,?3,NULL)",
                        params![job_id, principal, now],
                    )?;
                    CancelOutcome::Accepted
                }
            };
            tx.commit()?;
            Ok(outcome)
        })
    }

    /// Whether workers must not start or continue work on this job.
    pub fn cancellation_requested(&self, job_id: i64) -> Result<bool> {
        self.call(move |db| requested(&db.connection, job_id))
    }

    /// Settle pending cancellations. Call only from the delivery thread between
    /// jobs (so no delivery is in progress); `claim_active` is evaluated inside
    /// the transaction, which is serialized with every claim's own cancellation
    /// check, so a claim in flight defers settlement until it stops.
    /// Uncommitted jobs become Cancelled; jobs whose delivery committed first
    /// drop the request. Returns rows changed.
    pub fn settle_cancellations(
        &self,
        now: i64,
        claim_active: impl Fn() -> bool + Send + 'static,
    ) -> Result<usize> {
        if now < 0 {
            return Err(StoreError::InvalidContext);
        }
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            if claim_active() {
                return Ok(0);
            }
            let pending: Vec<i64> = tx
                .prepare("SELECT job_id FROM cancellations WHERE state='Pending' ORDER BY job_id")?
                .query_map([], |r| r.get(0))?
                .collect::<std::result::Result<_, _>>()?;
            let mut changed = 0;
            for id in pending {
                let job = load(&tx, id)?.ok_or(StoreError::CorruptState)?;
                changed += if job.recording.is_committed() {
                    tx.execute("DELETE FROM cancellations WHERE job_id=?1", [id])?
                } else {
                    tx.execute(
                        "UPDATE cancellations SET state='Cancelled',stopped_at=max(?2,requested_at) WHERE job_id=?1",
                        params![id, now],
                    )?
                };
            }
            tx.commit()?;
            Ok(changed)
        })
    }
}
