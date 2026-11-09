# API contract closeout and remaining approval

2026-11-08, increment 120. The user authorizes proceeding with the release-check
recommendations: close P01, then define the next protected-producer ingress
increment. This document is the current engineering authority over conflicting
candidate wording. **Engineering contract frozen as v2.0.0 on 2026-11-08 after group53 approval.**
The user explicitly approved the four defaults and proceeding with protected ingress.
This freeze does not implement admin/access features, select a proxy,
publish a release or authorize operational changes. Groups 1-53 are the approval baseline.

## Approved closeout defaults (group 53)

The user accepted all four defaults with "Approved, Proceed":

| Situation | Approved behavior | Operator-visible result |
|---|---|---|
| Retry selects a completed job | Skip it. | `skipped_count` increases; nothing is scheduled. The approved second duplicate after an accepted retry still counts as failed. |
| Retry has a frozen null review epoch | Always skip that occurrence. | It stays skipped even if the job later becomes retryable. A fresh deliberate Retry must capture an eligible review epoch. |
| A cancellation response is lost | Dispatch the same IDs against current state. | Pending duplicate cancellation counts as failed; completed, safely cancelled and missing IDs skip. No automatic cancellation of new/replacement jobs. |
| A valid deletion request finds no eligible files/jobs | Return 202 with actual zero counts and `completion_pending:false`. | No removal starts. This does not turn validation, stale confirmation, authorization or storage errors into success. |

No extra confirmation dialog, job identifier, post-clear inventory, deletion
retry workflow or producer monitoring obligation is introduced. The written engineering baseline is now `2.0.0`. Candidate suffixes on existing
artifact filenames remain stable for provenance/reference compatibility. Admin
behaviors still require separate implementation/qualification; this authorization
starts only the bounded protected-producer ingress increment.

## Engineering dispositions

### Supported surface and identity

Keep exactly the fifteen operations in `openapi.candidate.json`, with the
producer/admin/probe/trusted-local audiences in `ACCESS-BOUNDARY.candidate.md`.
No historical draft route is added. Retain specialized local resume/reset,
their existing command IDs and envelopes. No producer access to job reads,
retention, health, admin actions or specialized controls is granted.

The producer/manifest contract remains increment 116 as implemented in 117/118.
Keep all seven identity vectors and existing serialization fixtures unchanged.
The executable compatibility matrix is increments 115/118/119: explicit guarded
11-to-12 migration, legacy v1/numeric paths, partial-legacy refusal followed by
predecessor handoff, UUID/mixed-state support and incompatible predecessor
refusal. Unsupported state refuses; there is no reverse migration, arbitrary
working downgrade, invented legacy UUID or stale snapshot restore.

Consumer acceptance and shipping qualification are release evidence obligations;
neither is claimed by adopting a written schema. Existing trusted-loopback
runtime also does not implement the audience/security boundary of the future
release routes.

### Retry receipts: per-job identity, not a retained batch inventory

This explicitly replaces the earlier engineering requirement to persist and
compare the full ordered cross-job selection in every receipt. It is not
equivalent redaction of that old design.

Validate the complete ordered body/header, selection digest, instance and frozen
epochs before any occurrence. Keep duplicate entries. Derive an internal command
key from canonical immutable request context and occurrence position, using the
existing internal command facility; no key is public. A receipt belongs only to
its existing original job and stores the exact own-command projection: trusted
account principal, instance, action, original job ID, frozen epoch, exact reason
and occurrence position, plus its outcome. It must not store other selected job
IDs, epochs, paths or a reconstructible cross-job selection.

The opaque key locates a receipt; compare its exact own-command projection
before using the result. A digest alone cannot authorize scheduling or substitute
for epoch/custody checks. Changing another selected job may produce a different
internal key and a fresh eligibility check; it cannot make this job's old epoch
authorize a later review. An exact valid uncleared request replays its original
occurrence outcomes. Cleared jobs skip, so original aggregate counts are not
promised after clear. Clearing one job removes all its receipts and leaves
other jobs' receipts/protection intact.

For each new occurrence, reserve storage capacity, authorize against the current
session revocation generation, check frozen epoch/eligibility/custody, then commit
outcome, audit and scheduling together. Persist failed/skipped outcomes for
tracked jobs too. Never append the batch result after scheduling has committed.
Recognize authenticated exact receipts before current eligibility or capacity.
Existing accepted-command audit limits remain unchanged.

Bound new receipt storage to 64 distinct canonical request contexts per tracked
job, each with at most 256 occurrence outcomes. Store shared own context once;
ordinals are bounded by the request's 256-entry limit. No expiry, eviction or
automatic history purge. If a new outcome cannot be retained, stop dispatch and
return 503 `service_busy` without fabricated final counts. Earlier committed
occurrences remain valid. Retrying unchanged context replays them before capacity
checks and attempts only uncommitted occurrences. A storage failure similarly
returns 503 `storage_unavailable`. These errors never prove batch rollback.

The approved null outcome is deterministic and permanently nonauthorizing; it
needs no historical row. A missing ID at or below the durable job-ID high-water
mark also skips permanently because IDs are never reused. A non-null epoch for
a never-allocated future ID fails whole-request validation with 400
`invalid_retry_context`, before any occurrence. **Invalid requests have no exact
replay guarantee:** clients must discard a rejected context and obtain a fresh
review. The high-water check does not make formerly invalid bytes permanently
invalid after later allocation. No authenticated human-inspection proof or
durable rejection-history feature is promised.

Per-occurrence stale epoch, ineligible tracked work and exhausted accepted-command
audit capacity count as failed, with persisted outcomes when capacity permits.
Completed/null classifications are the approved skipped defaults above. Missing IDs
silently skip. Account revocation wins before a new occurrence or receipt
disclosure; previously admitted service work can finish independently.

### Confirmation, reads and forgetting

Adopt the existing bounded read proposal: ascending original job IDs, page size
50 by default/256 maximum, 1024-character cursor, 1 MiB ordinary page. A cursor
authenticates instance and pagination parameters; it is not a cross-request
snapshot. Invalid/wrong-instance cursor returns 400 `invalid_cursor`; clearing
rows between pages is normal and does not reconstruct them.

Confirmation mode stays on the list route, binds exact ordered IDs/action/account
revocation generation/instance, expires after five minutes and has the existing
6144-byte token and 8192-byte aggregate header bounds. Session renewal does not
extend a proof or change its scope. Expired, wrong-action/account/instance proofs
are 400 `invalid_confirmation`; changed selected owned objects/state are 409
`stale_confirmation`. Do not issue authority from an incomplete/truncated preview.
Retain 65536-target/16 MiB preview limits and 413 `confirmation_preview_too_large`.

Deletion confirms exact safe owned objects and state versions. Authenticate and
validate the proof before inspecting action results; recognize the same active
or latest pass before considering a new pass. An old proof returns that pass's
result, or stale refusal when it no longer matches; it never starts another pass.
A fresh deliberate confirmation is required for remaining failures. Counts refer
to unique file targets in that pass, not repeated observations or reclaimed bytes.
One active/latest pass exists per tracked job. No public operation ID or automatic
retry is added. Exact proof codec and SQL layout remain implementation details
that must meet these rules and receive review before activation.

Clear processes current completed/safely-cancelled eligibility after proof checks,
serializes against effects/actions and skips ineligible/missing IDs. It removes
all job/file/action/receipt/accounting linkage and leaves files untouched. A
repeated clear counts only current actual removals. No confirmation or cursor
can recover a cleared job or redirect its ID to a reused UUID.

### Session and resource bounds

Keep the existing HTTPS origin/cookie AND CSRF contract, browser-compatible
marked GET rules, global logout/password/restart invalidation and monotonic
inactivity. Transfers remain independent of credentials and sessions.

Use exact UTF-8 credentials without trimming/normalization: username 1-128 bytes,
password 1-4096 bytes, each valid Unicode scalars. These are transport bounds,
not a new password-complexity policy. Host-local account provisioning must apply
the same bounds. Store a salted adaptive password verifier using a reviewed
library; algorithm/dependency approval and target cost qualification belong to
the separate authentication implementation, not hand-written crypto here.

Session and CSRF values each require at least 256 bits from the OS random source,
are opaque, and are never logged or returned as session JSON. Keep at most 64
active sessions and 64 live confirmation contexts per instance, with at most
64 KiB of retained proof context each (4 MiB total). Never silently
evict a valid session to admit another; exhaustion returns 503 `service_busy`.
Expired/revoked ephemeral entries may be removed. Every restart invalidates them.
Proof storage must separate per-job bindings: clear erases that job's bindings,
not other jobs' action receipts. Shared metadata must contain no cleared job IDs,
paths or reconstructible selection. Cancel/clear proof validation must still
allow repeated valid requests to skip already-cleared IDs. Final proof/SQL design
must demonstrate these properties before implementation; a bounded token by
itself is not evidence that all server-side storage is bounded or forgotten.
No request body or proof is written into an unbounded queue or temporary file.

Serialize password verification through one bounded slot; admit at most five
login attempts per rolling 60 seconds per instance. Excess login attempts return
429 `rate_limited` with integer `Retry-After: 60` and no cookie/session issuance.
This bound applies before password verification regardless of supplied username;
there is no permanent account lockout. Incorrect admitted credentials retain the
approved 401 and exact message. Proxy-level client throttling can add protection
but cannot relax this backend bound or claim qualified availability here.

Retain six producer requests within the shared eight-connection budget, five-
second input read and ten-second claim/probe handoff bounds. Producer saturation
returns 429 `rate_limited`, retryable true, JSON delay and `Retry-After: 1`.
Framing/custody/replay rules still govern; the proxy never synthesizes a 202.
The selected TLS proxy and its 30-second upstream/45-second client budget are
qualified separately. No external proxy package is selected in this increment.

## Acceptance and next step

The existing reference/schema checks remain required, with semantic byte limits
and no encoding-only fixture expansion. Admin implementation must prove lost
responses/later epochs, duplicates, partial transaction crashes, capacity,
revocation admission, clear of one job from a multi-job selection, stale deletion
proofs, idle polling and route segregation using actual HTTP/SQL tests.

The next bounded implementation is [protected producer ingress](PRODUCER-INGRESS-INCREMENT.md).
It does not include sessions, admin actions, TLS proxy deployment or missing
cleanup. Protected ingress implementation is now authorized; remote TLS exposure and
admin/action activation remain separate. All eight release gates remain open; production NFS/deletion stay off.
