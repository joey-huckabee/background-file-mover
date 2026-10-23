# REST error scenarios: review draft

Recorded 2026-10-23. **Partially approved contract draft; implementation unchanged.**
The user asked to review the scenarios and agree on codes before implementation.
This document supports P01/RC-01-03 of the
[release plan](RUST-RELEASE-CLOSURE.md); it does not add new release gates.
No runtime, persistence, retry/review policy or NFS/deletion switch changes here.

## Approved groups (2026-10-23)

The user approved the following thirteen groups in successive review replies.
These fifty outcome mappings, the group-12 error envelope and group-13 retry
timing are contract decisions, not new runtime capabilities.
Other rows and unresolved response/identity/compatibility details remain under
review. An approval here does not approve every variant of its broader API-E row.

| Group | Situation | Approved HTTP / application code | Automatic retry |
|---|---|---|---|
| 1 | Listed file confirmed missing, including partial custody | 409 `source_file_missing` | Yes, within persisted missing window |
| 1 | Missing-file window expired | 409 `recording_blocked` | No; operator review |
| 1 | Claim still running, outcome uncertain | 503 `handoff_pending` | Yes; identical request |
| 1 | Recording ID reused with changed request | 409 `recording_id_conflict` | No; investigate original submission |
| 2 | Invalid JSON | 400 `invalid_json` | No |
| 2 | Missing/invalid fields | 400 `invalid_submission` | No |
| 2 | Invalid file paths | 400 `invalid_file_paths` | No |
| 2 | Valid source path outside generator scope | 403 `source_outside_scope` | No |
| 2 | Expected size differs from observed file | 409 `source_size_mismatch` | No; review |
| 3 | Enabled source-space check confirms insufficient margin | 503 `source_space_low` | Yes |
| 3 | Enabled source-space check cannot obtain reliable sample | 503 `source_space_unavailable` | Yes |
| 3 | Retained-job/byte admission limit reached | 503 `retention_capacity` | Yes |
| 3 | Mover request queue full | 503 `service_busy` | Yes |
| 3 | Mover shutting down | 503 `service_stopping` | Yes |
| 4 | Source already reserved by another recording | 409 `source_reserved` | No; review |
| 4 | File identity/size changes during claim | 409 `recording_blocked` | No; review |
| 4 | Source mount/root identity or ownership no longer matches | 409 `recording_blocked` if HTTP response possible | No; review |
| 4 | Service lacks filesystem permission to claim a file | 409 `recording_blocked` | No; correct permissions and review |
| 5 | Local database temporarily unavailable | 503 `storage_unavailable` | Yes; corruption/unsafe ownership remain stop/review |
| 5 | Request receive deadline expires | 408 `request_timeout` | Yes; fresh connection |
| 5 | Proxy cannot obtain valid backend response | 502; proxy code/body not guaranteed | Yes |
| 5 | Proxy times out waiting for mover | 504; proxy code/body not guaranteed | Yes |
| 5 | Connection drops or recorder times out | No reliable response/code | Yes |
| 6 | Wrong API endpoint | 404 `not_found` | No |
| 6 | Wrong HTTP method | 405 `method_not_allowed`, with Allow | No |
| 6 | Missing/unsupported Content-Type | 415 `unsupported_media_type` | No |
| 6 | Request body exceeds bound | 413 `request_too_large` | No |
| 6 | Request headers exceed bound | 431 `request_headers_too_large` | No |
| 6 | Malformed HTTP framing | 400 `invalid_http` | No |
| 7 | Unknown generator | 403 `unknown_generator` | No |
| 7 | Caller not authorized for supplied generator | 403 `caller_not_authorized` | No |
| 7 | Producer attempts operator-only route | 403 `producer_route_forbidden` | No |
| 7 | Producer exceeds request limit | 429 `rate_limited` | Yes; indicated delay |
| 7 | TLS certificate validation fails | TLS failure; no guaranteed HTTP code/body | No; correct certificate/trust configuration |
| 8 | Destination unavailable/full after confirmed 202 | Operator status 200 with delivery retry/review condition | No recorder action |
| 8 | Verification fails/publication blocked after confirmed 202 | Operator status 200 with existing retry/review condition | No recorder action |
| 8 | Source cleanup disabled/fails after commitment | Operator status 200 with retained/cleanup condition when implemented | No recorder action |
| 9 | Invalid local operator job ID/command fields | 400 `invalid_job_id`, `invalid_resume` or `invalid_missing_reset` | No |
| 9 | Unknown operator job | 404 `not_found` | No |
| 9 | Stale review epoch or action ineligible | 409 `review_conflict` | No; inspect status |
| 9 | Operator command ID reused with changed parameters | 409 `command_conflict` | No |
| 9 | Operator audit capacity reached | 409 `operator_audit_capacity` | No; review |
| 9 | Operator queue/database temporarily unavailable | 503 `service_busy` or `storage_unavailable` | Yes; same command ID/body |
| 10 | Body on bodyless GET | 400 `unexpected_body` | No |
| 10 | Optional idempotency header conflicts with request/command ID | 400 `idempotency_key_conflict` | No |
| 10 | Unsupported headers, including bearer authorization in this profile | 400 `unsupported_headers` | No |
| 10 | Incomplete HTTP request with valid rejection received | 400 `incomplete_request` | No; correct sending problem |
| 11 | Worker finished, source effect cannot be safely reconciled | 409 `recording_blocked` | No; operator review |
| 11 | Unexpected internal server error | 500 `internal_error` if reply possible | Yes; backoff and persistent-failure alert |
| 11 | Success reply has missing/wrong recording ID or invalid 202 body | Invalid acknowledgement; no trusted code | No; preserve paths and alert |

Retries retain the same recording ID/body and follow the supplied delay.
No error response grants path reuse or reverses an earlier valid 202. Existing
accepted-job retries remain exempt from the new-job source-space admission
check; custody/authority checks still apply. Do not bypass partial custody by
correcting under a new ID. The new global-ID namespace and exact wire schema
still require compatibility/persistence design before implementation.

## Decisions carried forward from the discussion

- Recorder submits generator identity, a globally unique recording ID, the full
  source directory as the mover sees it, and every file explicitly. Preserve
  subfolders; do not recursively discover files. Destination is configured.
- Generate the recording ID once; reuse it and the same request on retries.
  Same ID with a changed generator, source folder or file list conflicts.
- Submission 202 confirms durable custody of every file and permission to reuse
  original paths. A partial claim, saved request or timeout is not that permission.
  The recorder has no delivery-monitoring duty after confirmed 202.
- Identical successful replay returns 202, including after delivery finishes,
  subject to the authorized replay boundary. Authentication revocation does not
  reverse an already received valid 202.
- One missing file can leave the submission pending while other claims remain
  protected. Temporary conditions should be distinguishable from correction or
  review conditions. Missing input is now approved as 409 `source_file_missing`
  with retry allowed within the existing missing-file window.

The discussed minimal JSON uses `recording_id`, `source_directory` and string
file names. The current implementation instead requires `submission_id`,
`source_path` and file objects containing `name`, with optional `size_bytes`.
Global recording-ID enforcement and recording-ID destination layout also differ
from the implemented model. Do not describe the discussed JSON as usable today.
Optional size assertions remain an existing capability; their representation in
the new minimal form needs a compatibility decision, not silent removal.

## Approved error envelope (group 12) and recorder retry policy (group 13)

HTTP describes the broad outcome. `error` is a stable application code;
`retryable` gives the recorder its action. Human diagnostic text is not parsed.
A retryable result means repeat the **same ID and unchanged request**, not create
a new recording. Review/correction means log/alert and preserve remaining source
paths; never try a new ID to bypass a partial handoff.

Approved shape for mover-generated errors; the example is an advertised delay,
not a universal constant for all server replies:

```json
{
  "recording_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": "source_file_missing",
  "retryable": true,
  "retry_after_seconds": 5,
  "source_paths_released": false
}
```

`recording_id` is null when unavailable or unsafe to disclose. A malformed ID
is not echoed as a trusted identity. `retry_after_seconds` is null when automatic
retry is disallowed. All five envelope fields are present on mover-generated
errors; no null/omission ambiguity. Optional bounded diagnostic fields remain
under review; they must not disclose another generator's IDs/job existence,
absolute private paths or credentials. Proxy/TLS outcomes may lack this JSON.

The approved `source_paths_released:false` means **this response grants no new
release**, not that no file was claimed or that a previous 202 is revoked. Only
the submission's valid, matching 202 grants the recorder release. Operator status
or command replies are not a substitute. Error responses cannot authorize
putting previously claimed files back under their original names.

### Approved retry timing and precedence

The user approved the following recorder guidance as group 13:

1. Honor a usable mover `retry_after_seconds` when `retryable:true`.
2. Without usable JSON timing, honor a valid `Retry-After` header for an otherwise
   retryable result. The body flag `retryable:false` takes precedence and stops
   automatic retries; a header cannot turn a refusal into permission to retry.
3. If neither supplies a usable delay, use fallback waits of **5, 10, 20, then
   30 seconds**, staying at 30 seconds for further fallback retries.
4. Log a persistent-failure warning after **five minutes**, while continuing
   permitted retries. The warning does not authorize abandonment or path reuse.
5. Make these timing defaults configurable. Configuration belongs to the
   component performing the retries; do not imply the mover controls an external
   recorder's implementation. Publish this as the supported integration guidance.

All retries keep the same recording ID and unchanged request. Timing never
extends the mover's persisted missing-file window, resets review, cancels a
worker, authorizes replacement or overrides custody checks. Existing background
delivery retry intervals/budgets are unchanged. The five-minute warning and the
mover's missing-file deadline are independent even if defaults happen to match.

For controlled retryable mover replies, define positive bounded delay values in
the final schema. A server's explicit valid delay takes precedence over fallback;
30 seconds is the fallback cap, not a cap on a longer valid advertised delay.
For 429/503 the implementation plan also includes consistent Retry-After.
409 retry timing uses the JSON field rather than assuming generic HTTP clients
honor that header. Exact config names/ranges and diagnostic bounds belong in the
remaining schema work; do not silently add a new server missing-file timeout.

### Transport/protocol boundaries

Absent/unusable JSON does not make every HTTP result retryable. The reviewed
transport/temporary cases (connection loss, 408/429/500/502/503/504) permit
same-request retries using the timing precedence above. Valid rejection such as
400 incomplete_request requires correction. TLS certificate validation failures
require correction; never disable verification to continue retries.

Wrong/missing recording ID or malformed 202 is an invalid acknowledgement:
preserve paths and alert, without accepting success. Unexpected success codes
and redirects remain protocol errors, not evidence of custody; no automatic
redirect-following behavior is introduced. Exact response validation and safe
non-JSON fallback handling must be covered by the implementation case manifest.
No delay or local warning proves a previous POST transaction failed.

`retryable:false` stops automatic recorder retries for that condition. It does
not cancel retained work, authorize deletion, or declare the job unrecoverable.
Operator recovery uses the original state and existing audited procedures.

## Submission outcomes and source conditions

The approval table above governs reviewed mappings; other rows below remain
proposed acceptance scenarios. **None is a new passing test.**
`Current` records code paths inspected in `file-mover/src/lib.rs` and `http.rs`
under `rust/crates/`, plus the linked operator/remote contracts. It does not
assert that every listed variant has been separately qualified. Scenario IDs
API-E01-60 are review keys, not replacement requirements or SC IDs.

| ID | Situation | Proposed HTTP / code | Retry? / recorder or operator action | Current behavior / difference |
|---|---|---|---|---|
| API-E01 | First submission, every file durably claimed | 202; no error | Success; all original paths may be reused | Implemented, but current body uses numeric job ID and `Claimed`; discussed recording-ID response remains pending. |
| API-E02 | Identical retry after lost 202, or after delivery completed | 202; no error | Same confirmation; never claim reused leaves | Existing replay uses generator/submission identity and custody validation. Global recording ID and exact post-delivery response need agreement/mapping. |
| API-E03 | Same recording ID, changed source directory/file list/size assertion or other immutable request data | 409 `recording_id_conflict` | No; retain original body/custody, investigate | Current 409 `submission_conflict`; proposed naming/global key differs. File order currently matters; equivalence rules are open. |
| API-E04 | Same recording ID submitted by another generator | 409 `recording_id_conflict` only after allowed authorization; otherwise 403 generic denial | No; no cross-generator job/detail disclosure | Global namespace change is not implemented. Authorization must precede existence disclosure; settle exact denial with the remote contract. |
| API-E05 | One explicitly listed file is confirmed absent on an accessible authorized source | 409 `source_file_missing` | Yes, within the persisted missing-file window; preserve already claimed files | **Approved change, not implemented:** current 503 `handoff_pending`. A missing RPC reply/timeout is not absence proof. |
| API-E06 | Several files already claimed, another listed file confirmed missing | 409 `source_file_missing` | Yes within window; whole-set release remains withheld | Same current 503 pending behavior; no change to partial-custody safety. No per-file permission for producer reuse. |
| API-E07 | Missing-file deadline expires or persisted missing review block exists | 409 `recording_blocked` | No; operator reviews original job and, if appropriate, audited exact-file reset | Current 409 false. Restart/recorder retry never resets the deadline. Proposed dedicated code, if desired, needs evidence/schema discussion. |
| API-E08 | A file appears after missing deadline expired | 409 `recording_blocked` | No automatic clearing; same operator workflow | Existing review boundary must remain; presence alone does not reset review. |
| API-E09 | Expected size assertion differs from observed file size | 409 `source_size_mismatch` | No; inspect original request/object; no new ID bypass | Current 409 false; service measures actual size even when no assertion provided. |
| API-E10 | Source inode/size/parent identity changes during a pending claim | 409 `recording_blocked` | No; review custody/producer immutability violation | Current generic false refusal; selected cases in SC-138. More specific codes require typed proven causes. |
| API-E11 | Actual source leaf is symlink/nonregular or descriptor traversal/alias checks fail | 409 `recording_blocked` | No; inspect source and configured scope | Current claim refusal is broad; syntactically invalid paths are separate API-E25. No follow-links fallback. |
| API-E12 | Submitted source is reserved by another accepted recording | 409 `source_reserved` | No blind retry/new ID; investigate original reservation | Current 409 false; never steal custody or disclose another generator's job. |
| API-E13 | NFS access times out or claim worker has not returned before HTTP handoff budget | 503 `handoff_pending` | Yes with same request; retain original state and exclusion through actual worker exit | Current 10-second handoff timeout returns pending. This is uncertain progress, not failure/cancellation or confirmed missing input. |
| API-E14 | Source mount/root/enrollment identity changes, private namespace is foreign/ambiguous, or ownership guard validation fails | 409 `recording_blocked` if serving; otherwise startup refusal/no HTTP | No; preserve state, inspect configuration/custody; never rebind automatically | Current broad refusal. Root/mount availability is distinct from authority; timeout alone cannot downgrade this to a safe retry. |
| API-E15 | Source-space admission enabled and confirmed below configured margin | 503 `source_space_low` | Yes; restore capacity; no new-job admission or false 202 | Existing; default off. Existing accepted-key replay bypasses this new-job check, not custody checks. |
| API-E16 | Enabled source-space probe unavailable/stale/blocked | 503 `source_space_unavailable` | Yes; no unknown-as-zero/positive guess | Existing; preserve current probe wait/admission behavior and existing-job retries. |
| API-E17 | Source metadata allocation/write/sync fails; completed worker effect cannot be safely reconciled | 409 `recording_blocked` | No; preserve original intent/custody and obtain review. Still-running worker remains pending, not this refusal. | Group 11 approves conservative initial handling; no new source-capacity-specific code or automatic effect retry. This is distinct from sampled admission margin. |
| API-E18 | Service account cannot access source files/private areas | 409 `recording_blocked` | No blind retry; operator fixes approved permissions then reconciles | Current broad claim refusal; this is filesystem permissions, distinct from caller 403. No arbitrary-path disclosure. |
| API-E19 | Retained job/byte accounting reaches configured admission bound | 503 `retention_capacity` | Yes; operator addresses retained capacity; preserve partial state | Existing; no cleanup is implied while deletion is disabled. |
| API-E20 | Local SQLite transaction cannot complete; commit outcome may be unknown | 503 `storage_unavailable` | Yes with same ID; alert operator on persistent failure | Current broad retryable result. Does not prove rollback/no job; if DB is corrupt/ownership unsafe, stop effects and require review/startup refusal instead. |
| API-E21 | Mover handoff queue is full | 503 `service_busy` | Yes with backoff; bounded queues remain | Existing. Separate from caller rate limiting (API-E39); no new 429 mapping here without review. |
| API-E22 | Mover is draining/stopping | 503 `service_stopping` if response possible; otherwise lost connection | Yes against original owner/profile when available; no new effects after stop admission | Existing result; a stop timeout does not permit replacement while old workers/effects remain uncertain. |

## Request validation, caller boundary and transport

| ID | Situation | Proposed HTTP / code | Retry? / action | Current behavior / difference |
|---|---|---|---|---|
| API-E23 | Invalid JSON, duplicate/unknown fields, wrong field types, missing required fields, invalid recording ID | 400 `invalid_json` for decoding failures; 400 `invalid_submission` for invalid structure/values | No; correct integration without bypassing any previously accepted ID | Existing decoder uses these codes. Exact UUID syntax/new field compatibility pending; do not require a specific UUID version yet. |
| API-E24 | Empty file list, too many files, duplicate file paths, malformed/negative/overflow size assertions | 400 `invalid_submission` or `invalid_file_paths` according to frozen schema mapping | No; correct request; unchanged accepted request remains authoritative | Existing bounded validation, but detailed code precedence is not yet frozen for the new form. HTTP body size is API-E30. |
| API-E25 | Relative source directory, invalid encoding, absolute file name, empty component, backslash, NUL, `.`/`..` or invalid normalized path | 400 `invalid_file_paths` for file paths; 400 `invalid_submission` for source-directory syntax | No; correct request | Existing input validation has these broad codes. No lexical string-prefix authorization. |
| API-E26 | Well-formed source path outside configured generator scope | 403 `source_outside_scope` | No; operator-approved configuration/identity required | Existing 403; cannot grant access by changing JSON identity or supplying destination. |
| API-E27 | Unknown generator or caller/body generator mismatch | 403 `unknown_generator` or generic `caller_not_authorized`, with non-disclosing mapping | No; fix identity/authorization | Unknown generator already 403. Remote caller binding and exact mismatch code not implemented. |
| API-E28 | Client supplies destination or mixes old/advanced/new request forms | 400 `invalid_submission` | No; use approved form; destination is configured | Minimal generator form already rejects destination/unknown fields; explicit advanced form remains proposed. Compatibility/version choice pending. |
| API-E29 | Missing/unsupported Content-Type for JSON endpoint | 415 `unsupported_media_type` | No; correct request | Existing exact application/json check. Charset/media parameter policy needs explicit freezing. |
| API-E30 | Declared or actual request body exceeds bounded maximum | 413 `request_too_large` | No unchanged retry; correct request/approved limits, never split an accepted recording blindly | Current framing uses 413 `invalid_http`; more specific code proposed. Both proxy and backend must enforce bounds. |
| API-E31 | Header bytes/count exceed bounded maximum | 431 `request_headers_too_large` | No unchanged retry; correct headers | Current oversized header bytes produce 431 `invalid_http`; header count parser failures can produce 400. Proposed precise mapping requires parser evidence. |
| API-E32 | Malformed framing, contradictory/duplicate length, unsupported transfer encoding, duplicate header, pipelined extra bytes or bad HTTP syntax | 400 `invalid_http` | No automatic replay of malformed bytes; fix integration | Existing strict framing; no transfer-encoding fallback/request smuggling. Connection may close without a reply. |
| API-E33 | Request read deadline expires | 408 `request_timeout` | Yes on a fresh connection with unchanged complete body | Existing five-second backend read timeout; distinguish proxy timeouts and stalled NFS handoff. |
| API-E34 | EOF/incomplete body or connection reset during sending | 400 `incomplete_request` if obtainable; otherwise no reliable response | Correct persistent framing faults; if transport loss is uncertain, unchanged retry | Current EOF code false. Transport fallback must distinguish received valid rejection from absent/malformed response; no handoff release either way. |
| API-E35 | Unknown API route or unknown local operator job | 404 `not_found` | No unchanged retry; correct endpoint/ID; do not reinterpret missing source files as endpoint 404 | Existing; producer remote ingress must not expose job existence. |
| API-E36 | Wrong HTTP method on an allowed route | 405 `method_not_allowed` with required Allow header | No; correct method | Current status/code exist; required Allow header is not emitted by current response writer. |
| API-E37 | Body on bodyless GET; conflicting optional Idempotency-Key header | 400 `unexpected_body` or `idempotency_key_conflict` | No; correct integration; header must match the authoritative request/command key | Existing. New recording-ID/header equivalence and canonicalization pending. |
| API-E38 | Missing Host or unsupported Expect/Authorization headers on current endpoint | 400 `unsupported_headers` locally; remote auth/header-spoof mapping per RA contract | No; correct integration | Existing local behavior; bearer tokens/registration are deferred. Do not silently turn this into a new 401 challenge scheme. |
| API-E39 | Authenticated producer exceeds per-caller/global remote connection/request budget | 429 `rate_limited` plus Retry-After when known | Yes with backoff; preserve local operator/control capacity | Remote contract RA-13 is pending; current local queue saturation uses 503, not 429. Exact rate/concurrency distinction needs package design. |
| API-E40 | TLS server identity invalid or client certificate absent/untrusted/expired | TLS failure; no guaranteed HTTP status/body | No blind retry; correct provisioning/clock/trust, never bypass certificate verification | Remote profile design only. Do not promise JSON/401 for a TLS-handshake rejection. |
| API-E41 | Verified client certificate unmapped/revoked, or injected identity/Authorization/reserved headers | 403 `caller_not_authorized` for caller denial; 400 `unsupported_headers` for rejected header syntax/policy | No; correct provisioning/header behavior; original work continues | Pending RA-03-06/09/10; exact non-disclosing split must be frozen with proxy selection. |
| API-E42 | Wrong local proxy UID, missing/duplicate principal, foreign/replaced backend socket | OS/socket denial, or 403 `caller_not_authorized` if an HTTP reply is safe | No; operator fixes trusted proxy/socket boundary | Pending protected producer ingress; default unsafe configuration fails startup. No direct TCP/anonymous fallback. |
| API-E43 | Remote producer tries status/retention/operator/registration route, path alias or query bypass | Generic 403 `producer_route_forbidden` recommended at both hops | No; producer ingress exposes exact POST only; no job existence disclosure | Pending RA-08/13; choose consistent deny status with proxy. Local authorized 404/405 behavior stays separate. |
| API-E44 | Proxy cannot connect to backend or gets invalid upstream reply | Proxy 502, or 503 for known backend unavailability; body may be proxy-generated | Yes unchanged request with capped backoff/alert; no automatic proxy POST replay | Pending proxy qualification; preserve distinctions between transport and mover JSON. |
| API-E45 | Proxy waits too long for backend | Proxy 504; body may not follow mover schema | Yes unchanged request; old claim work may still run | Not evidence of cancellation/no effects. Backend handoff deadline should be shorter than proxy/recorder budgets. |
| API-E46 | Process/proxy dies, network disconnects or recorder times out after any claim phase or after 202 generation | No reliable HTTP outcome | Same-ID unchanged retry; preserve all remaining paths until confirmed 202 | Existing local durable replay; remote end-to-end qualification pending. |
| API-E47 | Unexpected server bug returns 500 or a non-JSON failure | 500 `internal_error` if response possible | Group 11 approves same-ID retry with backoff and persistent-failure alerting; unsafe state still stops effects | No deliberate generic 500 contract in current handler; never expose stack traces/secrets or fabricate success. |
| API-E48 | HTTP redirect, unexpected 2xx, wrong recording ID or malformed purported 202 | Protocol violation, no accepted handoff | Preserve paths; alert; do not follow POST redirects or accept a partial success indication | Proposed client contract validation/fallback; retry details need agreement. |

## Local operator API and failures after handoff

These routes are local operator operations; the recorder need not implement them.
Their errors must not be exposed through the remote producer socket. Successful
operator HTTP 200 does not grant a new recorder handoff. Background failures are
reported in job state/diagnostics, not pushed back to a recorder that already left.

| ID | Situation | Proposed HTTP / code | Retry? / action | Current behavior / difference |
|---|---|---|---|---|
| API-E49 | Invalid numeric job ID, resume/reset body, epoch, reason, command ID or window | 400 `invalid_job_id`, `invalid_resume` or `invalid_missing_reset` | No; correct operator request | Existing codes and bounded command validation. |
| API-E50 | Operator reads/resumes/resets an unknown job | 404 `not_found` | No; inspect correct original state/ID | Existing; do not restore a stale DB to make the lookup succeed. |
| API-E51 | Resume/reset uses stale review epoch, ineligible job/file or unmet review prerequisites | 409 `review_conflict` | No blind retry; inspect current status before a new audited command | Existing; wrong epoch does not reset failure budget or missing deadline. |
| API-E52 | Reuse command ID with changed parameters | 409 `command_conflict` | No; keep original command for uncertain retry | Existing. Exact command replay succeeds with original receipt, without changing later state. |
| API-E53 | Operator audit-record capacity reached | 409 `operator_audit_capacity` | No blind retry; operator investigates supported retention | Existing; no unaudited bypass/deletion. |
| API-E54 | Operator queue/status storage unavailable or timeout | 503 `service_busy` or `storage_unavailable` | Yes; read retries are safe, command retries preserve command ID/body | Existing. Timeout does not prove command transaction failed. |
| API-E55 | Destination unavailable/full after valid 202 | Status GET 200 containing retry/review condition; no new submission error | Recorder does nothing after confirmed 202; operator follows retained delivery policy | Existing destination deferral and payload ENOSPC schedules; do not change those intervals/budgets through API mapping. |
| API-E56 | Verification mismatch, collision, changed destination/custody or uncertain publication after 202 | Status GET 200 with blocked/retrying/review diagnostic | Recorder has no duty; operator investigates original receipts/state | Existing delivery policy/receipt rules; never translate failure into revoked path release or overwrite permission. |
| API-E57 | Source cleanup disabled or later fails after committed manifest | Status GET 200 with retained/pending/review cleanup accounting when implemented | No recorder retry; independent operator cleanup workflow | Cleanup runtime currently hard-disabled. Future effect errors do not revoke delivery/202 or trigger recopy. |
| API-E58 | Service not ready, bootstrap blocked or startup config/ownership/state refusal | No listening/served HTTP response; supervisor/startup diagnostic | Fix unsafe config/state; for temporary startup wait retry original submission with backoff | Existing startup readiness boundary; not a guaranteed 503/readiness endpoint. No second mover takeover on timeout. |
| API-E59 | Stop/status controller times out, owner unavailable or worker survives coordinator death | Local lifecycle protocol/exit status, not REST HTTP code | Existing bounded incomplete/restart-blocked workflow | Do not invent REST status codes for the separate Unix operator controller; preserve actual-exit exclusion. |
| API-E60 | Consumer sees payload/manifest absent or invalid, or only a staging/partial name | Consumer contract condition, not a new mover REST endpoint/status | Wait for valid COMMITTED.json; report invalid manifest/collision to operator | Filesystem destination has no implemented artifact HTTP endpoint. Never infer completion from a visible payload alone. |

## Missing-file mapping: approved, implementation pending

API-E05/E06 use 409 `source_file_missing` with `retryable:true` within the
persisted window; API-E07/E08 retain 409 `recording_blocked` with
`retryable:false` after expiry. Keep 503 `handoff_pending` for unresolved claim
progress. The user approved this split in group 1. Current code still returns
503 handoff_pending for a confirmed missing file before its deadline.

This is our API mapping, not an HTTP-mandated choice. 409 does not inherently
mean permanent failure. Earlier 503 missing-file examples are superseded as a
contract recommendation, without changing the existing implementation/evidence.

## Decisions still needed before freezing OpenAPI

| Decision | Question to settle | Affected scenarios |
|---|---|---|
| ER-D01 | **Resolved:** group 1 approves missing-file 409/true within the window and 409 recording_blocked/false after expiry. Preserve existing deadline/review semantics; implementation pending. | E05-08 |
| ER-D02 | **Initial mappings approved:** groups 1-11 select stable codes; retain broad recording_blocked for unsafe source reconciliation, without a new source-capacity-specific code. Finalize exact validation precedence/typed evidence in OpenAPI. | E03/09-18/23-24/30-31 |
| ER-D03 | **Envelope/timing approved (groups 12-13):** five fields and null rules; honor JSON delay, then valid header, then configurable 5/10/20/30-second fallback; configurable five-minute warning while permitted retries continue. Finalize schema bounds/config names, diagnostics and response/fallback validation. | E01-02/33-34/39/44-48 |
| ER-D04 | Resolve new recording-ID global uniqueness, persistence/legacy replay, UUID syntax, file order/equivalence and idempotency-key retention. IDs cannot become reusable merely because delivery completed or cleanup ran. | E02-04/23/37 |
| ER-D05 | Resolve compatibility/versioning for discussed field names/string files and existing optional size assertions/advanced proposal. No automatic silent wire change. | E03/09/23-25/28 |
| ER-D06 | Freeze safe remote denials, proxy codes and disclosure rules alongside RA-01-16; no bearer/registration implementation. | E04/26-27/38-45 |
| ER-D07 | Confirm destination failures must not block source handoff when original source authority/custody are independently proven; if destination affects admission, document that exact existing policy rather than invent a generic destination HTTP failure. | E13-22/55-57 |

Groups 1-13 above are approved: fifty outcome mappings, the shared error
envelope and recorder retry timing. Global-ID persistence/compatibility and
precise OpenAPI schema/validation details remain separate P01 work.
Agreement on one group does not freeze remaining rows or their broader variants.

## Consolidated implementation plan

The error-group review is complete for the mappings/envelope/timing listed
above. This does not freeze the entire REST API. Use the following finite work
sequence inside P01/P02/P03 and existing release gates; remote rows remain
pending until their protected ingress/proxy exists.

| Step | Deliverable | Dependency / acceptance |
|---|---|---|
| API-I01 | Versioned OpenAPI plus stable error registry; map API-E01-60 to approved outcomes or explicit remaining detail/non-HTTP disposition. Freeze exact schemas, response validation and precedence. | Resolve remaining request/wire compatibility, ID retention/equivalence and field/config bounds first; no silent removal of size assertions or existing state. |
| API-I02 | Durable globally unique recording-ID ownership and compatible new request/layout mapping. | API-I01; transactional concurrent-duplicate handling, upgrade/legacy replay and original custody/route preservation. Do not rename/reclaim accepted data casually. |
| API-I03 | Typed source missing/pending/refusal mapping, common error envelope, reviewed 400/409/413/431/500 vocabulary, Allow/retry headers and recorder examples. | API-I01/02; keep missing deadlines, existing-job replay and background retry/review behavior. No string-parsed cause or new effect authorization. |
| API-I04 | Protected producer ingress and selected authenticated proxy, caller binding/denials/rate limits and transport/credential tests. | P02/P03 and proxy decision; complete RA-01-16, preserve operator separation. No registration or unrestricted TCP shortcut. |
| API-I05 | Operator/post-202 response consistency and DOC-01/03/04/05 guidance covering every reviewed action, delay/fallback and original-state recovery. | Maintain alongside API-I01-04; successful status is not delivery, and no failure revokes a confirmed 202. Cleanup remains separately scheduled/default-off. |
| API-I06 | Exact acceptance-case manifest/results for the sixty situations, both SLES gates and changed NFS/remote boundaries. | Test incrementally with each change; audit final affected artifact set. Missing fixture/remote support stays pending, never claimed as passing. |

No recorder executable is part of this repository's deliverable by assumption;
its retry algorithm is integration guidance/examples unless separately requested.
The mover's implementation must advertise actionable delays consistently.

Implementation details and safety checks for those steps:

1. Record reviewed decisions and freeze an OpenAPI response/error registry with
   request/success schemas. Give each application code one defined condition,
   status, retry rule, permitted details and evidence needed to select it. Define
   precedence: framing/size, authentication/route boundary, schema/source scope,
   identity replay/admission, then claims. Retain stronger fail-closed checks.
2. Design durable global recording-ID ownership and wire compatibility before
   changing keys/paths. Qualify migration, concurrent duplicate submissions,
   legacy replay and state preservation. Freeze recorder retry/retention rules.
3. Add typed missing/pending/refusal facts through workers/store where needed;
   select codes from proven facts, not message strings or inferred ENOENT after
   a timeout. Keep existing missing deadlines, review, capacity and delivery
   policies unless separately approved. No new filesystem effect authorization.
4. Implement reviewed HTTP mapping/envelope, Allow and retry headers, and exact
   local producer/authorized-operator route behavior. Do not expose remote TCP
   as a shortcut; protected ingress and proxy remain P02/P03.
5. For each approved API-E row, retain an exact fixture/input/outcome assertion
   or explicit non-HTTP/manual disposition. Test conflicting and identical
   concurrent requests, missing-before/after-deadline and partial claims, lost
   response/continued work, replay after commit, malformed input and error-body
   fallback. Assert no false 202, no new path release, original state preserved,
   no duplicate unsafe effects, no cross-generator leakage and bounded load.
6. Run every Rust build/test through the production and retained qualification
   [SLES/glibc-2.22 gates](RUST-SLES-GATE.md). Execute required controlled NFS
   cases for changed source/error boundaries, not a fresh unbounded fault suite.
   Update SC evidence, DOC-01 retry instructions, DOC-03 operator explanations
   and DOC-04/05 limits. Mark pending remote cases until P02/P03 qualify them.

This is an error-mapping plan within P01 and dependent implementation packages,
not authorization to skip unresolved request/schema decisions or qualify all
remote scenarios by local tests. All eight FR
gates remain open. Production NFS and source deletion stay disabled.

## Standards and review evidence

The recommendations were checked against
[HTTP semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-status-codes)
and [429/431 definitions, RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html).
These specify status meanings; application names, missing-file treatment and
retry policy above are design decisions for this service, not RFC prescriptions.

Current-code review covers `lib.rs`/`http.rs`,
[missing reset](RUST-INCREMENT-09.md), [resume](RUST-INCREMENT-08.md),
[delivery retry policy](DELIVERY-RETRY-POLICY.md),
[remote contract](REMOTE-API-ACCESS-CONTRACT.md) and
[scenario catalog](RUST-SCENARIOS.md). No runtime or fixture tests were run for
this document. Existing scenario evidence remains scoped to its original inputs.
