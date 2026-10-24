# REST contract shutdown handoff

Saved 2026-10-23 on `feature/rust-transfer-coordinator`.
Reviewed documentation through `d0dc013` before this checkpoint. This handoff
adds no runtime implementation, dependency or qualification result.

Resumed 2026-10-23: file ordering is now resolved. Permuting the same file list
is an identical retry (group 16, SC-141/API-E71-72), with all other values
unchanged. UUID recording_id is also now required (group 17, SC-142/API-E73-74).
The user selects detailed history until admin dashboard clear (group 18,
SC-143/API-E75), not automatic compaction/permanent compact receipts. Prototype
behavior is unchanged. The user now resolves clear semantics (group 19,
SC-144/145/API-E76-80): forget cleared UUIDs, treat later submissions as new,
and require cancellation before clearing unfinished/errored jobs. Only completed
or safely cancelled jobs are eligible. Cancellation now preserves files in place
(group 20, SC-146/API-E81-86), including source claims, partial staging and valid
published recordings. Blocked workers/uncertain publication keep it pending.
History clear now also preserves files and separate ownership/accounting while
forgetting UUID recognition (group 21, SC-147/148/API-E87-91). Physical retained-data deletion needs a separate explicit admin action. Its
scope is now approved in group 22 (SC-149/150/API-E92-98): owned retained source
and unfinished destination only, after safe stop and confirmation. Protect
unclaimed originals and completed output. Deletion failure is best effort: failed
files remain, other safe selected files can still be attempted, and failures are
reported. No dedicated pause/resume or automatic retry workflow. Next settle
admin access and exact wire/bulk/concurrency. Group 23 resolves cleanup
independence: manual deletion works even when automatic cleanup is disabled;
Group 24 requires dashboard access from another computer (SC-152/API-E100).
Group 25 selects simple admin username/password (SC-153/API-E101), with SSO
and advanced account features deferred. Keep ordinary HTTPS/password/session
hygiene in implementation; finalize minimal credential setup/login/logout
and exact wire details without an expanded security-design review. Producer credentials alone
do not grant admin powers. Do not ask file ordering, UUID-versus-free-form or
local-versus-remote dashboard access or SSO-versus-password login again.

## Where we stopped

We are completing P01/API-I01: agree the REST contract before freezing OpenAPI
or starting the dependent Rust changes. The user wants simple questions, one
manageable decision/group at a time. Do not restart the error-code review or
add another NFS experiment automatically. Read
[the error/acceptance review](REST-ERROR-SCENARIOS.md) and
[the API draft](REST-API-DRAFT.md) for exact decisions and implementation gaps.

Twenty-five reviewed groups are recorded, including confirmed owned-data disposal: fifty initial outcome mappings, a shared
error envelope, recorder retry policy and ten size/restart cases. The catalog
now has 153 stable SC IDs and six DOC IDs; API-E01-101 are contract/acceptance
situations, not new passing tests. All eight release gates remain open.

## Decisions to preserve

- No one uses the Rust prototype API. Replace its producer wire format directly;
  do not build a compatibility adapter or deprecation system for it. Preserve
  stored jobs/custody and the separate C++ cutover obligations.
- Request: generator_id, globally unique recording_id, full mover-visible
  source_directory and explicit relative file names in files. Preserve folders;
  destination comes from configuration, beneath a recording-ID container.
  No recursive discovery. Retry the same ID and unchanged request.
- Whole-set 202 means durable custody and original-path reuse permission. Before
  it, recorder leaves files/parents unchanged. After it, recorder has no delivery
  monitoring duty. Authorized identical replay confirms 202, including lost
  response/completed delivery; no reclaiming reused source names.
- Confirmed missing input is approved as 409 source_file_missing/true within the
  persisted window; expiry is 409 recording_blocked/false. Uncertain running
  claim is 503 handoff_pending/true. **Current runtime still returns 503 pending
  for missing files; the approved mapping has not been implemented.**
- Approved error envelope: recording_id, error, retryable, retry_after_seconds,
  source_paths_released. Null ID when unavailable/unsafe; null delay when retry
  is false; error responses grant no new release. Proxy/TLS may lack this JSON.
- Recorder honors valid JSON delay, then valid Retry-After without usable JSON
  timing, then configurable fallback 5/10/20/30 seconds, remaining at 30. Warn
  after configurable five minutes of persistent failure while permitted retries
  continue. False retry flag stops automatic retries. No timing resets missing
  deadlines or authorizes effect replacement.
- expected_sizes_bytes is all-or-nothing: omitted or a complete map matching
  every listed filename. Partial/extra/invalid entries are 400 invalid_submission.
  Checking is default-disabled. **When off, ignore a supplied complete map even
  if expected 100 differs from actual 200 bytes** (SC-139/API-E61-66). When on,
  require the complete map and compare every assertion; mismatch is 409
  source_size_mismatch/false. Actual size measurement/hash/verification always run.
- **Latest correction:** current startup size-check configuration governs
  existing unfinished recordings after restart. The user rejected per-recording
  setting snapshots as too complex. Do not introduce them. Off-to-on can block
  missing/mismatching expectations; on-to-off removes an expected-size-only
  barrier on the next original-ID/body retry. Preserve private custody, actual
  evidence, unrelated safety review and already confirmed 202 replay
  (SC-140/API-E67-70). No hot reload, new repair endpoint or autonomous claiming
  was requested. Working config name check_expected_sizes is not yet frozen.

## Next work when we resume

1. Finalize minimal username/password login/session details and exact endpoints/transactions/bulk
   and confirmation details. Group 22 resolves deletion scope and simple failure
   behavior: best effort, leave failed files and report them; no dedicated
   pause/resume state or automatic retry machinery. Preserve safe-stop,
   ownership, confirmation and original/committed-output protections. No
   destructive code yet. Group 23 approves manual deletion with automatic cleanup
   disabled (SC-151/API-E99). Do not re-open failure-policy or independence design.
2. Finalize exact schema/config bounds, response validation/precedence and
   persisted global-ID/state handling. Size-policy snapshotting is resolved
   against; only its implementation/replay ordering remains. Review any remaining
   remote disclosure/proxy and destination-admission details against the existing
   agreements before asking questions again.
3. Produce versioned OpenAPI/error registry and final manifest contract, then use
   API-I02-06/P02-P03 for short tested implementation increments. Reconcile
   active requirements; do not silently remove optional sizes or add proposed-only
   list/control/UI endpoints as mandatory new scope.
4. Maintain [the scenario catalog](RUST-SCENARIOS.md), DOC-01-05 guidance and
   [future-only roadmap](ROADMAP.md). Keep completed evidence/history outside
   the roadmap. Use [the release plan](RUST-RELEASE-CLOSURE.md) as the finite
   work scheduler, not increment counts or an unbounded new fault matrix.

## Verification and shutdown state

This contract discussion changed documentation only. Local link/anchor, JSON,
identifier and diff-whitespace checks passed. Prior scenario IDs are preserved;
SC-139/140 and their ten size/restart cases are explicitly unimplemented and
unqualified. Both retained SLES evidence source archives were checked against
unchanged current runtime inputs; their existing passes are not new tests.

No build, fixture service or background worker was started by this contract-review
session, so it introduces no running experiment needing cleanup. Do not infer
unrelated machine-wide container/process state from that statement.

Every future Rust build/test must use the production and retained qualification
GNU/glibc-2.22 cargo-zigbuild, ELF audit and exact-target SLES userspace gates.
Keep container-only compatibility qualification; no real SLES installation
requirement. Production NFS and source deletion remain disabled. Registration,
S3, cross-host takeover and offline repair remain deferred; experiments stay
stopped after E1-E5. No runtime change is authorized merely by this handoff.
