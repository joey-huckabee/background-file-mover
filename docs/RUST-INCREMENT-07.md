# Rust operator job status

`GET /api/v2/jobs/{job_id}` returns a read-only snapshot of one recording's
durable evidence. It is an operator interface; recorders still submit JSON and
wait for 202 without needing to poll. The trusted loopback profile remains in
effect. No dependency or schema change is required.

The response has `job_id`, `state` (`Accepted`, `Claimed`, or `Committed`),
`source_paths_released`, and `details`. Details contain generator/submission IDs,
ordered files with actual measured sizes (null before claim), protocol phase,
latest transfer phase/attempt, manifest phase, missing-file deadlines and
persisted delivery retry count/deadline/code. `source_cleanup_enabled` is false.
Private paths, inode observations and arbitrary underlying error text are omitted.

`details.condition` is `AwaitingClaims`, `Ready`, `Retrying`, `ReviewRequired`,
or `Committed`. These describe persisted scheduling evidence, not a live worker
assignment, filesystem health or proof of current custody. Committed takes
precedence over historical retry records. An elapsed missing deadline is shown
as review-required even if recorder retry has not yet persisted `blocked`;
observation never changes deadlines or unblocks work. Timestamps are Unix seconds.
Manifest phase is null before intent, then 0 (intent), 1 (allocation), 2 (written),
3 (publication authorized), or 4 (committed receipt).

A dedicated status thread has an eight-command queue and uses the existing
SQLite owner. A single read transaction produces the snapshot; bulk copying and
claiming do not hold it. API calls wait at most two seconds for status results,
using the existing eight-connection admission limit. Each query covers at most
256 files; listing/pagination remains future work. There are no filesystem calls
in the status path. It does not establish readiness or hard shutdown bounds.

IDs must be canonical positive decimal i64 values. Unknown jobs return 404;
invalid IDs or GET bodies return 400; non-GET methods return 405. Queue saturation
returns 503 `service_busy`; unavailable/timed-out storage returns 503
`storage_unavailable`. Existing submission responses keep their original shape.

Tests cover partial claims and measured sizes, destination deferral, automatic
manifest completion and restart, disabled cleanup/source retention, malformed
routes/bodies/methods, persistent missing-file review, and read-only database
snapshots preserving deadline and delivery review evidence. Platform results are
recorded in [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).

Next: audited operator resume and explicit orphan/retention repair contracts,
then supervised worker and NFS qualification. No automatic deletion, orphan
adoption, retry reset, remote authentication or NFS enablement is added here.

## Requirement derivation and evidence boundary

This slice contributes to the individual-status portion of `L1-API-002`.
Collection and aggregate queries remain unimplemented. Its Rust architectural
obligation is an isolated bounded read path through the authoritative SQLite
owner; implementation obligations are a consistent single-job transaction,
strict job-ID/request validation, and read-only rendering of durable claim,
transfer, deadline, review and manifest evidence. The two `operator_status_*`
API tests and `status_snapshot_preserves_deadlines_review_and_claims_across_restart`
storage test provide direct evidence. They do not promote historical C++ trace
coverage or establish filesystem readiness, repair correctness or listing support.
Formal Rust L2/L3 identifiers and automatic matrix discovery remain roadmap work.
