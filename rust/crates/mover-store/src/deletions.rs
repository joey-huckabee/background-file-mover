//! Admin "delete retained data" (schemas 16-17; contract group 22/50/51,
//! DeleteTarget and DeletionStatus).
//!
//! Scope: the mover's own retained source copies (private custody, claim done)
//! of jobs that stopped safely: delivered, or cancelled with the stop
//! confirmed. Since schema 17 also unfinished destination data
//! (docs/dashboard/DESTINATION-DELETION-DESIGN.md): every recorded attempt and
//! the manifest staging of a cancelled job whose manifest never reached
//! publication intent, and a delivered job's superseded partial attempts.
//! Originals, committed destination output and anything not owned are never
//! targets.
//!
//! One pass per job at a time. Each pass records the confirmation it came from
//! (`proof_digest`): the same confirmation observes or replays that pass and
//! never starts another. A fresh confirmation starts a new pass on the remaining
//! (not deleted) targets. Counts are the latest pass's confirmed deletions and
//! failures; no automatic retry. Files are removed by the delivery thread, one
//! target at a time, through the supervised worker.
use super::*;
use sha2::{Digest, Sha256};

/// Which dashboard action a deletion preview/pass belongs to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeletionScope {
    /// "Delete source files": retained source copies.
    Source,
    /// "Delete partial destination files": a cancelled job's unfinished
    /// destination data.
    Destination,
}

/// Contract `DeleteTarget.kind`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeleteKind {
    RetainedSource,
    /// One attempt's `.part` (phase 0-2), or a delivered job's superseded one.
    DestinationStaging,
    /// One attempt moved into place (phase 3-4) of an uncommitted job.
    DestinationPayload,
    /// `.staging/COMMITTED.part` (manifest phase 1-2) of an uncommitted job.
    ManifestStaging,
}
impl DeleteKind {
    pub fn code(self) -> &'static str {
        match self {
            Self::RetainedSource => "RetainedSource",
            Self::DestinationStaging => "UnfinishedDestinationStaging",
            Self::DestinationPayload => "UnfinishedDestinationPayload",
            Self::ManifestStaging => "UnfinishedManifestStaging",
        }
    }
    fn decode(code: &str) -> Option<Self> {
        [
            Self::RetainedSource,
            Self::DestinationStaging,
            Self::DestinationPayload,
            Self::ManifestStaging,
        ]
        .into_iter()
        .find(|k| k.code() == code)
    }
}

/// One deletable object, as previewed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeleteTarget {
    pub kind: DeleteKind,
    /// `None` only for manifest staging.
    pub file_index: Option<usize>,
    /// Destination attempt; `None` for retained source and manifest staging.
    pub attempt: Option<i64>,
    /// Path relative to the job's recording (the original name), or
    /// `COMMITTED.json` for manifest staging.
    pub relative_path: String,
    /// `None` when unknown (a partial attempt, manifest staging).
    pub size_bytes: Option<u64>,
}

/// One pending destination target with the records the worker checks it
/// against. The worker trusts nothing it cannot re-observe.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DestinationWork {
    pub job_id: i64,
    pub kind: DeleteKind,
    /// Stored keys (`-1`/`0` for manifest staging), for the result.
    pub file_index: i64,
    pub attempt: i64,
    /// The attempt's record; for manifest staging, file 0's latest attempt.
    pub transfer: Transfer,
    /// File 0's latest attempt: its staging directory is `.staging`.
    pub anchor: Transfer,
    pub manifest: Option<ManifestRecord>,
    /// Delivered job: every file's published attempt (automatic cleanup only).
    pub published: Vec<Transfer>,
    /// Automatic cleanup of a delivered job's superseded attempt.
    pub delivered: bool,
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
    /// This request started a new pass (newly admitted work).
    Started(DeletionView),
    /// An active pass, or the pass this exact confirmation started, observed
    /// or replayed: nothing new was admitted.
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

/// Every remaining target of one action.
fn targets(tx: &Connection, id: i64, scope: DeletionScope) -> Result<Vec<(DeleteTarget, String)>> {
    match scope {
        DeletionScope::Source => source_targets(tx, id),
        DeletionScope::Destination => destination_targets(tx, id),
    }
}

/// Remaining owned retained copies: completed claims not already deleted.
fn source_targets(tx: &Connection, id: i64) -> Result<Vec<(DeleteTarget, String)>> {
    let mut s = tx.prepare(
        "SELECT c.file_index,f.relative_path,c.source_identity FROM claims c \
         JOIN files f ON f.job_id=c.job_id AND f.file_index=c.file_index \
         WHERE c.job_id=?1 AND c.done=1 AND NOT EXISTS(SELECT 1 FROM deletion_targets d \
         WHERE d.job_id=c.job_id AND d.file_index=c.file_index AND d.kind='RetainedSource' AND d.state='Deleted') \
         AND NOT EXISTS(SELECT 1 FROM source_cleanups s WHERE s.job_id=c.job_id AND s.file_index=c.file_index \
         AND s.state='Removed') \
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
                    kind: DeleteKind::RetainedSource,
                    file_index: Some(index as usize),
                    attempt: None,
                    relative_path: path,
                    size_bytes: Some(object.size),
                },
                identity,
            ))
        })
        .collect()
}

/// (file, attempt, relative name, stage identity, phase) of every attempt.
type Attempt = (i64, i64, String, String, i64);
fn attempts(tx: &Connection, id: i64) -> Result<Vec<Attempt>> {
    let mut s = tx.prepare(
        "SELECT file_index,attempt,relative_name,stage_identity,phase FROM transfers \
         WHERE job_id=?1 ORDER BY file_index,attempt",
    )?;
    Ok(s.query_map([id], |r| {
        Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?))
    })?
    .collect::<std::result::Result<Vec<_>, _>>()?)
}

/// Remaining unfinished destination data (design: Scope), for the manual
/// action: a cancelled job (stop confirmed, so not committed) with the
/// manifest below publication intent: every attempt (staging for phase 0-2,
/// payload for 3-4) and manifest staging (phase 1-2). Anything else: none.
/// (A delivered job's superseded attempts are cleaned up automatically.)
fn destination_targets(tx: &Connection, id: i64) -> Result<Vec<(DeleteTarget, String)>> {
    let Some(job) = load(tx, id)? else {
        return Ok(Vec::new());
    };
    let manifest = load_manifest(tx, id)?;
    let manifest_phase = manifest.as_ref().map_or(-1, |m| m.phase);
    let cancelled = !job.recording.is_committed()
        && cancellations::get(tx, id)?
            .is_some_and(|c| c.state == cancellations::CancelState::Cancelled);
    let deleted = |kind: DeleteKind, file: i64, attempt: i64| -> Result<bool> {
        Ok(tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM destination_deletion_targets WHERE job_id=?1 \
             AND kind=?2 AND file_index=?3 AND attempt=?4 AND state='Deleted')",
            params![id, kind.code(), file, attempt],
            |r| r.get(0),
        )?)
    };
    let mut out = Vec::new();
    let mut push = |kind: DeleteKind,
                    file: i64,
                    attempt: i64,
                    path: String,
                    identity: String,
                    size: Option<u64>|
     -> Result<()> {
        if !deleted(kind, file, attempt)? {
            out.push((
                DeleteTarget {
                    kind,
                    file_index: usize::try_from(file).ok(),
                    attempt: (attempt > 0).then_some(attempt),
                    relative_path: path,
                    size_bytes: size,
                },
                identity,
            ));
        }
        Ok(())
    };
    if cancelled && manifest_phase < 3 {
        for (file, attempt, path, identity, phase) in attempts(tx, id)? {
            let stage = ObjectIdentity::decode(&identity).ok_or(StoreError::CorruptState)?;
            let (kind, size) = match phase {
                0 => (DeleteKind::DestinationStaging, None),
                1 | 2 => (DeleteKind::DestinationStaging, Some(stage.size)),
                3 | 4 => (DeleteKind::DestinationPayload, Some(stage.size)),
                _ => return Err(StoreError::CorruptState),
            };
            push(kind, file, attempt, path, identity, size)?;
        }
        if let Some(m) = &manifest
            && (1..=2).contains(&m.phase)
        {
            let object = m.object.as_ref().ok_or(StoreError::CorruptState)?;
            push(
                DeleteKind::ManifestStaging,
                -1,
                0,
                "COMMITTED.json".into(),
                object.encode(),
                None,
            )?;
        }
    }
    Ok(out)
}

/// Fingerprint of a job's exact deletable selection at its current pass
/// version. Binding the version means a confirmation issued before a later pass
/// can never start another pass, even if the same objects remain.
fn fingerprint(
    tx: &Connection,
    id: i64,
    scope: DeletionScope,
    selection: &[(DeleteTarget, String)],
) -> Result<String> {
    let version: i64 = tx
        .query_row(
            "SELECT pass FROM deletion_passes WHERE job_id=?1",
            [id],
            |r| r.get(0),
        )
        .optional()?
        .unwrap_or(0);
    let mut h = Sha256::new();
    // Domain-separated per action: a proof for one can never start the other.
    h.update(match scope {
        DeletionScope::Source => b"BFM-DELETE-TARGETS\0v1\0".as_slice(),
        DeletionScope::Destination => b"BFM-DELETE-DESTINATION\0v1\0".as_slice(),
    });
    h.update(id.to_be_bytes());
    h.update(version.to_be_bytes());
    for (t, identity) in selection {
        if t.kind == DeleteKind::RetainedSource {
            // Unchanged encoding (schema 16 confirmations stay comparable).
            h.update(b"RetainedSource\0");
            h.update((t.file_index.unwrap_or(0) as u64).to_be_bytes());
        } else {
            h.update(t.kind.code().as_bytes());
            h.update(b"\0");
            h.update(t.file_index.map_or(-1, |i| i as i64).to_be_bytes());
            h.update(t.attempt.unwrap_or(0).to_be_bytes());
        }
        h.update((identity.len() as u32).to_be_bytes());
        h.update(identity.as_bytes());
    }
    Ok(format!("{:x}", h.finalize()))
}

/// A delivered job's superseded attempt without a cleanup record (the next
/// one, or exactly `only`): phase 0, below the file's published attempt, with a
/// committed manifest.
fn superseded(c: &Connection, only: Option<(i64, i64, i64)>) -> Result<Option<(i64, i64, i64)>> {
    let (job, file, attempt) =
        only.map_or((None, None, None), |(j, f, a)| (Some(j), Some(f), Some(a)));
    Ok(c.query_row(
        "SELECT t.job_id,t.file_index,t.attempt FROM transfers t \
         JOIN manifests m ON m.job_id=t.job_id AND m.phase=4 \
         WHERE t.phase=0 AND t.attempt < (SELECT max(p.attempt) FROM transfers p \
         WHERE p.job_id=t.job_id AND p.file_index=t.file_index AND p.phase=4) \
         AND NOT EXISTS(SELECT 1 FROM destination_deletion_targets d WHERE d.job_id=t.job_id \
         AND d.kind='UnfinishedDestinationStaging' AND d.file_index=t.file_index AND d.attempt=t.attempt) \
         AND (?1 IS NULL OR (t.job_id=?1 AND t.file_index=?2 AND t.attempt=?3)) \
         ORDER BY t.job_id,t.file_index,t.attempt LIMIT 1",
        params![job, file, attempt],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    )
    .optional()?)
}

/// The pass is Done once nothing is pending in either table.
fn finish_pass(tx: &Connection, job_id: i64, now: i64) -> Result<()> {
    tx.execute(
        "UPDATE deletion_passes SET state='Done',finished_at=max(?2,requested_at) WHERE job_id=?1 \
         AND state='Active' AND NOT EXISTS(SELECT 1 FROM deletion_targets WHERE job_id=?1 AND state='Pending') \
         AND NOT EXISTS(SELECT 1 FROM destination_deletion_targets WHERE job_id=?1 AND state='Pending')",
        params![job_id, now],
    )?;
    Ok(())
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
            "SELECT (SELECT count(*) FROM deletion_targets WHERE job_id=?1 AND pass=?2 AND state=?3) \
             + (SELECT count(*) FROM destination_deletion_targets WHERE job_id=?1 AND pass=?2 AND state=?3)",
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
    pub fn deletion_preview(
        &self,
        job_id: i64,
        scope: DeletionScope,
    ) -> Result<Option<(Vec<DeleteTarget>, String)>> {
        self.call(move |db| {
            let tx = db.connection.transaction()?;
            if stopped(&tx, job_id)? != Some(true) || active(&tx, job_id)? {
                return Ok(None);
            }
            let selection = targets(&tx, job_id, scope)?;
            let digest = fingerprint(&tx, job_id, scope, &selection)?;
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
        scope: DeletionScope,
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
            let selection = targets(&tx, job_id, scope)?;
            if fingerprint(&tx, job_id, scope, &selection)? != confirmed {
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
                if t.kind == DeleteKind::RetainedSource {
                    tx.execute(
                        "INSERT INTO deletion_targets VALUES(?1,?2,'RetainedSource',?3,'Pending',NULL) \
                         ON CONFLICT(job_id,file_index,kind) DO UPDATE SET pass=excluded.pass,state='Pending',diagnostic=NULL",
                        params![job_id, t.file_index.ok_or(StoreError::CorruptState)? as i64, pass],
                    )?;
                } else {
                    tx.execute(
                        "INSERT INTO destination_deletion_targets VALUES(?1,?2,?3,?4,?5,'Pending',NULL) \
                         ON CONFLICT(job_id,kind,file_index,attempt) DO UPDATE SET pass=excluded.pass,state='Pending',diagnostic=NULL",
                        params![
                            job_id,
                            t.kind.code(),
                            t.file_index.map_or(-1, |i| i as i64),
                            t.attempt.unwrap_or(0),
                            pass
                        ],
                    )?;
                }
            }
            let v = view(&tx, job_id)?.ok_or(StoreError::CorruptState)?;
            tx.commit()?;
            Ok(DeletionStart::Started(v))
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
            finish_pass(&tx, job_id, now)?;
            tx.commit()?;
            Ok(())
        })
    }

    /// The next pending destination target of any active pass, with the
    /// records the worker checks it against.
    pub fn next_destination_deletion(&self) -> Result<Option<DestinationWork>> {
        self.call(|db| {
            let c = &db.connection;
            let next: Option<(i64, String, i64, i64)> = c
                .query_row(
                    "SELECT job_id,kind,file_index,attempt FROM destination_deletion_targets \
                     WHERE state='Pending' ORDER BY job_id,kind,file_index,attempt LIMIT 1",
                    [],
                    |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
                )
                .optional()?;
            let Some((job_id, kind, file_index, attempt)) = next else {
                return Ok(None);
            };
            let kind = DeleteKind::decode(&kind).ok_or(StoreError::CorruptState)?;
            let job = load(c, job_id)?.ok_or(StoreError::CorruptState)?;
            let anchor = load_transfer(c, job_id, 0)?.ok_or(StoreError::CorruptState)?;
            let transfer = match kind {
                DeleteKind::ManifestStaging => anchor.clone(),
                _ => load_transfer_attempt(
                    c,
                    job_id,
                    usize::try_from(file_index).map_err(|_| StoreError::CorruptState)?,
                    Some(attempt),
                )?
                .ok_or(StoreError::CorruptState)?,
            };
            // Manual destination passes exist only for cancelled jobs.
            if job.recording.is_committed() {
                return Err(StoreError::CorruptState);
            }
            let (published, delivered) = (Vec::new(), false);
            Ok(Some(DestinationWork {
                job_id,
                kind,
                file_index,
                attempt,
                transfer,
                anchor,
                manifest: load_manifest(c, job_id)?,
                published,
                delivered,
            }))
        })
    }

    /// The next superseded attempt of a delivered job (committed manifest)
    /// that has no cleanup record yet: automatic cleanup after a successful
    /// delivery (design: Delivered jobs). Never the published attempt.
    pub fn next_automatic_cleanup(&self) -> Result<Option<DestinationWork>> {
        self.call(|db| {
            let c = &db.connection;
            let next = superseded(c, None)?;
            let Some((job_id, file_index, attempt)) = next else {
                return Ok(None);
            };
            let job = load(c, job_id)?.ok_or(StoreError::CorruptState)?;
            if !job.recording.is_committed() {
                return Err(StoreError::CorruptState);
            }
            let index = usize::try_from(file_index).map_err(|_| StoreError::CorruptState)?;
            let transfer = load_transfer_attempt(c, job_id, index, Some(attempt))?
                .ok_or(StoreError::CorruptState)?;
            let mut published = Vec::new();
            for i in 0..job.recording.submission().files().len() {
                let t = load_transfer(c, job_id, i)?.ok_or(StoreError::CorruptState)?;
                if t.phase != TransferPhase::Published {
                    return Err(StoreError::CorruptState);
                }
                published.push(t);
            }
            Ok(Some(DestinationWork {
                job_id,
                kind: DeleteKind::DestinationStaging,
                file_index,
                attempt,
                transfer,
                anchor: load_transfer(c, job_id, 0)?.ok_or(StoreError::CorruptState)?,
                manifest: load_manifest(c, job_id)?,
                published,
                delivered: true,
            }))
        })
    }

    /// Admission recheck for automatic cleanup, after the job was marked busy
    /// (no pass protects discovery): the job is still tracked and this exact
    /// attempt is still an eligible superseded attempt with no record.
    pub fn automatic_cleanup_eligible(&self, work: &DestinationWork) -> Result<bool> {
        let (job_id, file_index, attempt) = (work.job_id, work.file_index, work.attempt);
        let stage = work.transfer.stage.encode();
        if !work.delivered {
            return Ok(false);
        }
        self.call(move |db| {
            let c = &db.connection;
            if superseded(c, Some((job_id, file_index, attempt)))?.is_none() {
                return Ok(false);
            }
            let recorded: Option<String> = c
                .query_row(
                    "SELECT stage_identity FROM transfers WHERE job_id=?1 AND file_index=?2 AND attempt=?3",
                    params![job_id, file_index, attempt],
                    |r| r.get(0),
                )
                .optional()?;
            Ok(recorded.as_deref() == Some(stage.as_str())
                && load(c, job_id)?.is_some_and(|j| j.recording.is_committed()))
        })
    }

    /// Record one automatic cleanup result (no pass; never retried).
    pub fn finish_automatic_cleanup(
        &self,
        work: &DestinationWork,
        deleted: bool,
        diagnostic: Option<&str>,
    ) -> Result<()> {
        if !work.delivered
            || work.kind != DeleteKind::DestinationStaging
            || diagnostic.is_some_and(|d| !problems::valid_diagnostic(d))
        {
            return Err(StoreError::InvalidContext);
        }
        let (job_id, file_index, attempt) = (work.job_id, work.file_index, work.attempt);
        let diagnostic = diagnostic.map(str::to_owned);
        self.call(move |db| {
            let changed = db.connection.execute(
                "INSERT INTO destination_deletion_targets VALUES(?1,'UnfinishedDestinationStaging',?2,?3,NULL,?4,?5) \
                 ON CONFLICT(job_id,kind,file_index,attempt) DO NOTHING",
                params![
                    job_id,
                    file_index,
                    attempt,
                    if deleted { "Deleted" } else { "Failed" },
                    diagnostic
                ],
            )?;
            if changed != 1 {
                return Err(StoreError::CorruptState);
            }
            Ok(())
        })
    }

    /// Record one destination target's result.
    pub fn finish_destination_deletion(
        &self,
        work: &DestinationWork,
        deleted: bool,
        diagnostic: Option<&str>,
        now: i64,
    ) -> Result<()> {
        if now < 0 || diagnostic.is_some_and(|d| !problems::valid_diagnostic(d)) {
            return Err(StoreError::InvalidContext);
        }
        let (job_id, kind, file_index, attempt) =
            (work.job_id, work.kind, work.file_index, work.attempt);
        let diagnostic = diagnostic.map(str::to_owned);
        self.call(move |db| {
            let tx = db
                .connection
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let changed = tx.execute(
                "UPDATE destination_deletion_targets SET state=?5,diagnostic=?6 WHERE job_id=?1 \
                 AND kind=?2 AND file_index=?3 AND attempt=?4 AND state='Pending'",
                params![
                    job_id,
                    kind.code(),
                    file_index,
                    attempt,
                    if deleted { "Deleted" } else { "Failed" },
                    diagnostic
                ],
            )?;
            if changed != 1 {
                return Err(StoreError::CorruptState);
            }
            finish_pass(&tx, job_id, now)?;
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
            // A confirmed deletion targeted it, or move mode authorized its
            // removal (monotonic `authorized`; schema 18).
            Ok(db.connection.query_row(
                "SELECT EXISTS(SELECT 1 FROM deletion_targets WHERE job_id=?1 AND file_index=?2 \
                 AND kind='RetainedSource') OR EXISTS(SELECT 1 FROM source_cleanups \
                 WHERE job_id=?1 AND file_index=?2 AND authorized=1)",
                params![job_id, file_index as i64],
                |r| r.get(0),
            )?)
        })
    }
}
