# Route schemas and error registry candidate

2026-11-03. Engineering proposal for P01, **not frozen or implemented**.
Groups 1–52 remain the approval source. Completing a schema does not approve
the compatibility choices or qualify the runtime. The fifteen operations in
[OpenAPI](openapi.candidate.json) are the proposed supported inventory; each
JSON response and request references the accompanying strict object schemas.
The per-response `x-error-codes` entries are the route error registry candidate,
not declarations that every mapping is already approved.

Producer-only update: increment 116 fixes POST /api/v2/jobs and manifest v2 in
[the scoped engineering contract](PRODUCER-MANIFEST-CONTRACT.md), including
canonical response UUIDs, positive usable delays and optional producer UUID
header equivalence. The other fourteen route candidates and operator byte-exact
command headers below remain separate. Increment 115 supplies the bounded actual
migration/pair evidence; mixed UUID runtime/activation remain unimplemented.

## Read views and preserved operator wire

Detailed status preserves current fields and enum spellings. Unknown actual
size is null; it is never zero or an expected size. File custody and transfer
phases are separate. The outer review epochs are current versions; stored audit
epochs are the versions consumed by their commands. Legacy `submission_id`
and new UUID `recording_id` are mutually exclusive branches. Reading legacy
state must not assign a UUID or rewrite custody. Group 52 approves preservation with supported upgrades or safe refusal; the
exact supported predecessor/schema matrix remains engineering work.

The optional detailed-status `retry_review`, `cancellation` and `deletion`
fields, new summary views and cancellation states are **proposed extensions**.
They are not fields or states currently emitted by the prototype. The current
`source_cleanup_enabled` and `automatic_reclamation_enabled` values are false;
their boolean schema permits the separate future default-off cleanup deliverable.
No cleanup is enabled by this contract work.

Current local status/operator envelopes always contain `source_paths_released`
and `retryable`. Optional absent fields are omitted, not null; HTTP status is
not a JSON field. Operator errors retain this envelope rather than adopting the
producer five-field error body. Receipt schemas preserve current action names
and resulting epochs. Command IDs are bounded to 128 UTF-8 bytes; audit reasons
are 1–512 UTF-8 bytes, nonblank and control-free, without silent normalization.
The existing optional `Idempotency-Key` header must, if supplied, exactly match
the body command_id UTF-8 bytes; mismatch is 400 `idempotency_key_conflict`
before queueing. It neither replaces command_id nor adds another identifier.
Queued status, retention and operator commands return 409 `recording_blocked`
if instance validation fails, with no invented job_id when it is absent.
Reset windows are 1–86400 seconds. Exact commands replay before new eligibility
or audit-cap checks, without authorizing a later review.

Retention is reservation accounting, including every retained destination
attempt, not physical usage or free-space inspection. Ledger totals are u128
decimal strings. Per-job headroom is null; global headroom may also be null
when limits are not configured. Only the global HTTP view includes the cached
source-space observation. Reads do not start filesystem probes. Cleared jobs
have no status, accounting, ownership, action results or reconstruction route.

## Bounded list and confirmation read proposal

`GET /api/v2/admin/jobs` normally returns ascending original job IDs, with
`limit` default 50, maximum 256, and an opaque cursor of at most 1024 characters.
The cursor binds instance and pagination semantics; it is not a snapshot across
requests. Cleared rows disappear. Ordinary pages are limited to 1 MiB serialized.

The same route has a proposed confirmation mode: `confirm_action` is `cancel`,
`clear-history` or `delete-data`, paired with comma-separated `job_ids` in the
query. Decode 1–256 exact positive i64 integers in order, retaining duplicates.
Reject repeated query keys, limit/cursor in confirmation mode, incomplete pairs
and unknown query keys. Numeric parsing must not pass through binary64.
The response carries a complete preview and an opaque `Mover-Confirmation`
proof for the subsequent job_ids-only POST body. This supplies the existing
required confirmation UI; it does not add another confirmation dialog.

Candidate preview limits are 65536 deletion targets and 16 MiB serialized.
Never issue authority from a truncated preview. A preview exceeding either
limit returns candidate 413 `confirmation_preview_too_large`; the operator
selects fewer jobs, or leaves an individually oversized job for explicit review.
GET preview creation admits no cancellation/deletion/clear work and does not
renew inactivity unless the deliberate-activity rule is satisfied.

The proof is proposed to expire after five minutes and be authenticated by the
service. It binds the existing instance, authenticated account/session-revocation
generation, action and exact ordered IDs. Maximum header value is 6144 ASCII
bytes; the total raw HTTP head remains 8192 bytes. Reject multiple or comma-joined
proof headers. Wire codec/key storage remain implementation design, not an
encoding-fixture workstream. A valid proof is authorization context, not proof
that a person inspected the screen.

For deletion additionally bind the actual owned selected objects and their
state versions. Check recognized active/latest pass replay before considering
a new pass; an old proof cannot start a later pass after selection/state changes.
Changed selection requires a fresh preview and confirmation. No extra public
operation identifier is introduced. Missing/cleared IDs silently skip and cannot
be reconstructed from a proof. Any per-job stored proof/action material is
forgotten at clear. A self-contained proof must not become a hidden inventory.
Exact storage and transaction design still need review before implementation.

Cancel/clear use current eligibility for the selected original, nonreused job
IDs; the proof is not a frozen failed-work retry epoch. Clear requires completed
or safely cancelled work with all effects settled. It forgets all linkage while
leaving files untouched. Cancellation transport replay is still unresolved.

Deletion 202 exposes actual latest-pass deleted/failed counts and a pending
flag. Repeated entries are dispatched normally, but observing the same pass
twice must not double-count files. These counts are not bytes reclaimed or
guarantees of durable physical erasure. One active/latest pass behavior is
approved; the no-work deletion HTTP mapping remains a candidate. There is no
automatic retry. Committed output and producer originals remain protected.

## Access and error precedence

[Access-boundary rules](ACCESS-BOUNDARY.candidate.md) apply to every operation.
Dashboard mutations require cookie **and** CSRF token, plus exact configured
Origin. Marked GET activity requires CSRF and target-authority checks, accepting
normal browser omission of Origin; if Origin is present it must match. Polling
and exact transport replay do not renew activity. Authenticate before receipt
disclosure. Revocation does not stop service-owned transfers.

OpenAPI cannot describe Unix peer-UID authorization. Specialized resume/reset
operations therefore use an explicitly local-only documentation server and
`x-required-transport-authorization`, without inventing a trusted HTTP header.
Their `security: []` means no HTTP credential scheme, **not public access**.
Shared status/retention reads require the admin cookie over the dashboard
boundary, or separately authorized local transport. Producer ingress must deny
all these routes. The current loopback prototype is not proof of this boundary.
The document is unsuitable for production client generation or gateway import.

Error order is proposed as: transport/framing/aggregate limits; authentication;
Origin/CSRF/marked-activity checks; complete bounded syntax and selection/context
validation; authenticated exact receipt lookup; transactional per-occurrence
eligibility/effects. Malformed whole requests have no action effects. Failed
storage after earlier occurrence commits must not fabricate aggregate success;
retry with unchanged frozen intent, preserving uncleared receipts. Per-occurrence
revocation admission and all-settled clear are still runtime proof obligations.

The route registry distinguishes producer, local/operator and admin envelopes.
Login/session 401 keep their approved message schemas. A 405 supplies `Allow`.
Producer 429/rate limiting does not promise a new retry policy; concrete throttle
and Retry-After rules remain to settle. TLS failure has no HTTP body; proxy 502,
504, disconnection and parser rejection can lack mover JSON. The OpenAPI default
producer response covers only mover-generated errors, not transport failures.
Headers, URI/response byte limits, UTF-8 byte bounds, decimal range checks and
cross-object identity consistency are semantic constraints, not JSON Schema
assertions. Duplicate JSON keys must be rejected before object validation.

## Validation boundary

Run `python3 docs/api/check_contract_candidate.py` with the existing `jsonschema`
package. It checks the metaschema, fixture expectations, all schema references,
fifteen-operation inventory and selected access/error invariants. It is not a
full OpenAPI validator, semantic admission validator, HTTP test, transaction test
or release gate. Group 52 settles numeric/filename and legacy-preservation policy. Exact UUID
state migration/refusal, supported upgrade/rollback matrix, cancellation replay,
completed-retry count classification, durable
receipts/confirmation design and deployment/security proof remain open.
