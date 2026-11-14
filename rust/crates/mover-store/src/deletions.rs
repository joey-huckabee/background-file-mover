//! Admin "delete retained data" (schema 16; contract group 22/50/51,
//! DeleteTarget and DeletionStatus).
//!
//! Scope: the mover's own retained source copies (private custody, claim done)
//! of jobs that stopped safely: delivered, or cancelled with the stop
//! confirmed. Originals, committed destination output and anything not owned
//! are never targets. (Unfinished destination kinds are reserved in the schema
//! for a later increment.)
//!
//! One pass per job at a time. Each pass records the confirmation it came from
//! (`proof_digest`): the same confirmation observes or replays that pass and
//! never starts another. A fresh confirmation starts a new pass on the remaining
//! (not deleted) targets. Counts are the latest pass's confirmed deletions and
//! failures; no automatic retry. Files are removed by the delivery thread, one
//! target at a time, through the supervised worker.
use super::*;
use sha2::{Digest, Sha256};

/// One deletable object, as previewed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeleteTarget {
    pub file_index: usize,
    /// Path relative to the job's recording (the original name).
    pub relative_path: String,
    pub size_bytes: u64,
}

/// Latest pass of a job (DeletionStatus).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeletionView {
    pub pass: i64,
    pub completion_pending: bool,
    pub deleted_count: u32,
    pub failed_count: u32,
}

/// Outcome of a confirmed delete request for one job.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeletionStart {
    /// A new pass started (or was observed/replayed): its current status.
    Pass(DeletionView),
    /// Valid request with nothing eligible: no pass, nothing removed.
    NoWork,
    /// Missing job or not safely stopped: skipped silently.
    Skipped,
    /// The deletable selection changed since confirmation; nothing started.
    Stale,
}

/// Eligible when delivered, or cancelled with the stop confirmed.
fn stopped(tx: &Connection, id: i64) -> Result<Option<bool>> {
    let Some(job) = load(tx, id)? else {
        return Ok(None);
    };
    Ok(Some(
        job.recording.is_committed()
            || cancellations::get(tx, id)?
                .is_some_and(|c| c.state == cancellations::CancelState::Cancelled),
    ))
}

pub(super) fn active(tx: &Connection, id: i64) -> Result<bool> {
    Ok(tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM deletion_passes WHERE job_id=?1 AND state='Active')",
        [id],
        |r| r.get(0),
    )?)
}

/// Remaining owned retained copies: completed claims not already deleted.
fn targets(tx: &Connection, id: i64) -> Result<Vec<(DeleteTarget, String)>> {
    let mut s = tx.prepare(
        "SELECT c.file_index,f.relative_path,c.source_identity FROM claims c \
         JOIN files f ON f.job_id=c.job_id AND f.file_index=c.file_index \
         WHERE c.job_id=?1 AND c.done=1 AND NOT EXISTS(SELECT 1 FROM deletion_targets d \
         WHERE d.job_id=c.job_id AND d.file_index=c.file_index AND d.kind='RetainedSource' AND d.state='Deleted') \
         ORDER BY c.file_index",
    )?;
    let rows = s
        .query_map([id], |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    rows.into_iter()
        .map(|(index, path, identity)| {
            let object = ObjectIdentity::decode(&identity).ok_or(StoreError::CorruptState)?;
            Ok((
                DeleteTarget {
                    file_index: index as usize,
                    relative_path: path,
                    size_bytes: object.size,
                },
                identity,
            ))
        })
        .collect()
}

/// Fingerprint of a job's exact deletable selection at its current pass
/// version. Binding the version means a confirmation issued before a later pass
/// can never start another pass, even if the same objects remain.
fn fingerprint(tx: &Connection, id: i64, selection: &[(DeleteTarget, String)]) -> Result<String> {
    let version: i64 = tx
        .query_row(
            "SELECT pass FROM deletion_passes WHERE job_id=?1",
            [id],
            |r| r.get(0),
        )
        .optional()?
        .unwrap_or(0);
    let mut h = Sha256::new();
    h.update(b"BFM-DELETE-TARGETS\0v1\0");
    h.update(id.to_be_bytes());
    h.update(version.to_be_bytes());
    for (t, identity) in selection {
        h.update(b"RetainedSource\0");
        h.update((t.file_index as u64).to_be_bytes());
        h.update((identity.len() as u32).to_be_bytes());
        h.update(identity.as_bytes());
    }
    Ok(format!("{:x}", h.finalize()))
}

pub(super) fn view(tx: &Connection, id: i64) -> Result<Option<DeletionView>> {
    let pass: Option<(i64, String)> = tx
        .query_row(
            "SELECT pass,state FROM deletion_passes WHERE job_id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()?;
    let Some((pass, state)) = pass else {
        return Ok(None);
    };
    let count = |s: &str| -> Result<u32> {
        Ok(tx.query_row(
            "SELECT count(*) FROM deletion_targets WHERE job_id=?1 AND pass=?2 AND state=?3",
            params![id, pass, s],
            |r| r.get(0),
        )?)
    };
    Ok(Some(DeletionView {
        pass,
        completion_pending: state == "Active",
        deleted_count: count("Deleted")?,
        failed_count: count("Failed")?,
    }))
}

impl Store {
    /// Preview: the job's current deletable targets and their fingerprint, or
    /// None when the job is missing, not safely stopped or already deleting.
    pub fn deletion_preview(&self, job_id: i64) -> Result<Option<(Vec<DeleteTarget>, String)>> {
        self.call(move |db| {
            let tx = db.connection.transaction()?;
            if stopped(&tx, job_id)? != Some(true) || active(&tx, job_id)? {
                return Ok(None);
            }
            let selection = targets(&tx, job_id)?;
            let digest = fingerprint(&tx, job_id, &selection)?;
            Ok(Some((
                selection.into_iter().map(|(t, _)| t).collect(),
                digest,
            )))
        })
    }

    /// Start (or observe/replay) a confirmed deletion pass for one job.
    /// `fingerprint` is the confirmed selection; `proof_digest` identifies the
    /// confirmation. Exact pass recognition comes before eligibility.
    pub fn start_deletion(
        &self,
        job_id: i64,
        principal: &str,
        proof_digest: &str,
        confirmed: &str,
        now: i64,
    ) -> Result<DeletionStart> {
        let valid_hex = |s: &str| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit());
        if now < 0
            || job_id <= 0
            || principal.trim().is_empty()
            || principal.len() > 128
            || principal.chars().any(char::is_control)
            || !valid_hex(proof_digest)
            || !valid_hex(confirmed)
        {
            return Err(StoreError::InvalidContext);
        }
        let (principal, proof_digest, confirmed) = (
            principal.to_owned(),
            proof_digest.to_owned(),
            confirmed.to_owned(),
        );
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            if load(&tx, job_id)?.is_none() {
                return Ok(DeletionStart::Skipped);
            }
            // 1. The active pass, or the pass this exact confirmation started.
            let existing: Option<(String, String)> = tx
                .query_row(
                    "SELECT state,proof_digest FROM deletion_passes WHERE job_id=?1",
                    [job_id],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .optional()?;
            if let Some((state, digest)) = &existing
                && (state == "Active" || *digest == proof_digest)
            {
                let v = view(&tx, job_id)?.ok_or(StoreError::CorruptState)?;
                return Ok(DeletionStart::Pass(v));
            }
            // 2. A new pass: eligibility, then the exact confirmed selection.
            if stopped(&tx, job_id)? != Some(true) {
                return Ok(DeletionStart::Skipped);
            }
            let selection = targets(&tx, job_id)?;
            if fingerprint(&tx, job_id, &selection)? != confirmed {
                return Ok(DeletionStart::Stale);
            }
            if selection.is_empty() {
                return Ok(DeletionStart::NoWork);
            }
            let pass = existing.map_or(Ok(0), |_| {
                tx.query_row(
                    "SELECT pass FROM deletion_passes WHERE job_id=?1",
                    [job_id],
                    |r| r.get::<_, i64>(0),
                )
            })? + 1;
            tx.execute(
                "INSERT INTO deletion_passes VALUES(?1,?2,'Active',?3,?4,?5,NULL) \
                 ON CONFLICT(job_id) DO UPDATE SET pass=excluded.pass,state='Active',principal=excluded.principal,\
                 proof_digest=excluded.proof_digest,requested_at=excluded.requested_at,finished_at=NULL",
                params![job_id, pass, principal, proof_digest, now],
            )?;
            for (t, _) in &selection {
                tx.execute(
                    "INSERT INTO deletion_targets VALUES(?1,?2,'RetainedSource',?3,'Pending',NULL) \
                     ON CONFLICT(job_id,file_index,kind) DO UPDATE SET pass=excluded.pass,state='Pending',diagnostic=NULL",
                    params![job_id, t.file_index as i64, pass],
                )?;
            }
            let v = view(&tx, job_id)?.ok_or(StoreError::CorruptState)?;
            tx.commit()?;
            Ok(DeletionStart::Pass(v))
        })
    }

    /// The next pending target of any active pass, with its claim.
    pub fn next_deletion_target(&self) -> Result<Option<(i64, usize, ClaimIntent)>> {
        self.call(|db| {
            let next: Option<(i64, i64)> = db
                .connection
                .query_row(
                    "SELECT job_id,file_index FROM deletion_targets WHERE state='Pending' \
                     ORDER BY job_id,file_index LIMIT 1",
                    [],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .optional()?;
            let Some((job, index)) = next else {
                return Ok(None);
            };
            let (intent, done) =
                load_claim(&db.connection, job, index as usize)?.ok_or(StoreError::CorruptState)?;
            if !done {
                return Err(StoreError::CorruptState);
            }
            Ok(Some((job, index as usize, intent)))
        })
    }

    /// Record one target's result; the pass finishes when none are pending.
    pub fn finish_deletion_target(
        &self,
        job_id: i64,
        file_index: usize,
        deleted: bool,
        diagnostic: Option<&str>,
        now: i64,
    ) -> Result<()> {
        if now < 0 || diagnostic.is_some_and(|d| !problems::valid_diagnostic(d)) {
            return Err(StoreError::InvalidContext);
        }
        let diagnostic = diagnostic.map(str::to_owned);
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let changed = tx.execute(
                "UPDATE deletion_targets SET state=?3,diagnostic=?4 \
                 WHERE job_id=?1 AND file_index=?2 AND kind='RetainedSource' AND state='Pending'",
                params![
                    job_id,
                    file_index as i64,
                    if deleted { "Deleted" } else { "Failed" },
                    diagnostic
                ],
            )?;
            if changed != 1 {
                return Err(StoreError::CorruptState);
            }
            tx.execute(
                "UPDATE deletion_passes SET state='Done',finished_at=max(?2,requested_at) WHERE job_id=?1 \
                 AND state='Active' AND NOT EXISTS(SELECT 1 FROM deletion_targets WHERE job_id=?1 AND state='Pending')",
                params![job_id, now],
            )?;
            tx.commit()?;
            Ok(())
        })
    }

    /// Whether a confirmed deletion has targeted this file's retained copy in
    /// any state (pending, deleted or failed). From that point its custody
    /// evidence is deliberately given up: the copy may be mid-removal or gone
    /// after an uncertain failure, so replay validation must not require it.
    pub fn retained_copy_released(&self, job_id: i64, file_index: usize) -> Result<bool> {
        self.call(move |db| {
            Ok(db.connection.query_row(
                "SELECT EXISTS(SELECT 1 FROM deletion_targets WHERE job_id=?1 AND file_index=?2 \
                 AND kind='RetainedSource')",
                params![job_id, file_index as i64],
                |r| r.get(0),
            )?)
        })
    }
}
