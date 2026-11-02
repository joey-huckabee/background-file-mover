# Consolidated REST contract proposal

2026-11-01. Review draft for P01; updated 2026-11-02 for approved group 49.
This is a proposal, not a frozen API, runtime change or qualification result.
The [approved error review](REST-ERROR-SCENARIOS.md) remains authoritative for
accepted behavior. This document replaces older draft examples as the next
review entry point; historical examples are not additional release requirements.

Machine-readable [candidate schemas, fixtures and acceptance map](api/README.md)
now accompany this proposal. Their structural checks do not freeze P01.
The [admin replay design](api/ADMIN-REPLAY.candidate.md) gives the concrete
reviewed-state context recommendation; group 49 approves the header transport on 2026-11-02, with exact wire pending.

## What needs approval

Review the four decision packages below together. The recommended direction is:

1. Ship the reviewed producer API, simple authenticated admin dashboard and
   bounded operational reads. Retain specialized local operator controls; defer
   unrelated draft features.
2. Preserve existing jobs, paths, receipts and ownership. Add global UUID
   recognition without automatically translating or relocating legacy custody.
   History clear forgets UUID recognition but preserves retained-data addressing
   under the original job ID. Existing destination collisions remain refusals.
3. Serialize actions against stored job state and process every listed
   occurrence. Preserve audited retry replay so an old request cannot release a
   later review. Expose asynchronous outcomes through the same job ID and
   confirm deletion against the actual files selected.
4. Introduce a versioned recording manifest using recording_id, actual measured
   sizes and SHA-256. Preserve existing manifests and stable file identities;
   use strict UTF-8 paths without silent filename normalization.

All route spellings, schema spellings, limits and recommendations marked
**Proposed** below remain reviewable. No new approval group is recorded here.
Approved behavior is not reopened by the outstanding implementation design.

## Approved constraints carried forward

- Producer recording_id is a globally unique UUID. File-list permutation alone
  is identical replay; preserve durable file identities by path. Changed
  membership or assertions still conflict. No old Rust producer adapter is needed.
- A producer 202 grants source-path release only after durable custody of the
  complete set. Replay preserves an established 202 even after delivery or
  cancellation. Partial claims grant no release. Timeout is not cancellation.
- expected_sizes_bytes is optional only when comparison is disabled. A supplied
  map must be complete and exactly match the file keys in either mode. Disabled
  comparison ignores complete assertions for size comparison; actual size and
  integrity checks remain. The current startup setting governs unfinished work;
  do not snapshot that setting per recording.
- History remains until explicit admin clear. Only completed or safely cancelled
  jobs may be cleared. Clear forgets UUID recognition and preserves files and
  separate ownership/accounting. A subsequent use of that UUID is new work.
- Cancellation preserves files in place and remains pending until safe stop.
  Safely cancelled jobs cannot resume. Retry of eligible failed work is separate.
- Manual deletion is separately confirmed, best effort, and limited to owned
  retained source and unfinished destination after safe stop. Protect unclaimed
  originals and committed output. No automatic retry or dedicated recovery flow.
- One host-local-configured admin account; remote dashboard access is required.
  Browser session cookie, configurable 30-minute inactivity, global manual logout,
  password-change invalidation and restart invalidation. Transfers belong to the
  service and have no dependency on dashboard credentials or sessions.
- Login succeeds with 200 and cookie. Incorrect credentials return 401 with
  "Invalid username or password." Missing/expired admin sessions return 401.
  Successful global logout returns 204 without a body after invalidation.
- Four separate admin action endpoints accept job_ids. Missing IDs are silently
  skipped; repeated entries are dispatched again without batch deduplication.
  A duplicate cancel is a failed cancel attempt. Cancel and retry return 202
  accepted_count/failed_count/skipped_count for attempts, not finished work.
  Clear returns 200 and actual cleared count. Deletion returns 202 and reports
  deleted/failed file counts without claiming asynchronous work has finished.

## Package 1: release routes and session wire

**Proposed route inventory.** Existing means implemented prototype behavior,
not that its current response schema already satisfies the reviewed contract.
The public producer boundary must never expose admin or trusted-local controls.

| Method and path | Audience | Scope/status |
|---|---|---|
| POST /api/v2/jobs | Authenticated producer | Existing route; replace unused producer body with reviewed shape |
| GET /healthz | Deployment probe | Existing; freeze bounded readiness disclosure, not storage probing |
| POST /api/v2/admin/login | Dashboard | New; username/password, 200 and cookie |
| POST /api/v2/admin/logout | Dashboard | New; invalidate every session, 204 |
| GET /api/v2/admin/session | Dashboard | New; authenticated 200 or 401; no secret material |
| GET /api/v2/admin/jobs | Dashboard | New; bounded history list, pagination |
| GET /api/v2/jobs/{job_id} | Admin or trusted local operator | Existing; reviewed status extension |
| GET /api/v2/retention | Admin or trusted local operator | Existing; persisted accounting, not free-space proof |
| GET /api/v2/jobs/{job_id}/retention | Admin or trusted local operator | Existing; preserve ownership lookup after history clear |
| GET /api/v2/admin/retained-data | Dashboard | New; bounded retained-owner list, including cleared history, same job_id |
| POST /api/v2/admin/jobs/cancel | Dashboard | New; selected-job confirmation, 202 attempt counts |
| POST /api/v2/admin/jobs/retry | Dashboard | New; no confirmation, 202 attempt counts |
| POST /api/v2/admin/jobs/clear-history | Dashboard | New; UUID-forgetting/file-preservation confirmation, 200 |
| POST /api/v2/admin/jobs/delete-data | Dashboard | New; explicit file-scope confirmation, 202 |
| POST /api/v2/jobs/{job_id}/resume | Trusted local operator only | Retain audited specialized command, not a second dashboard retry flow |
| POST /api/v2/jobs/{job_id}/reset-missing | Trusted local operator only | Retain audited exact-file deadline reset |

Defer general pause/resume, standalone file-detail endpoints, advanced producer
routing, arbitrary metadata and new public operation identifiers. The existing
specialized controls keep their review epochs, command receipts and limits as
specified in [increment 08](RUST-INCREMENT-08.md) and
[increment 09](RUST-INCREMENT-09.md). Whether retaining this exact release
surface is acceptable is the first decision; older draft routes do not become
mandatory by appearing in a historical table.

**Proposed session wire:** login body has exactly username and password strings;
200 body is {"authenticated":true}. Credential failure body is
{"error":"invalid_credentials","message":"Invalid username or password."}.
Protected session failure uses {"error":"authentication_required"}.
Do not force the producer error envelope onto login responses. Session GET
returns authenticated:true and inactivity_timeout_seconds. Never return the
password, cookie value or server session key in JSON.

Use an opaque server-side session cookie named __Host-mover_admin, Secure,
HttpOnly, Path=/, SameSite=Strict, no Domain and no persistent Expires/Max-Age.
Treat server-side expiry/revocation as authoritative; browser restoration is
not proof of a live session. Require HTTPS for remote access and an explicit
same-origin CSRF defense for cookie-authenticated mutations, including logout.
A CSRF token is security material, not a new job/operation identifier. Define
and test its exact transport in the OpenAPI/security implementation design.

**Proposed edge behavior:** a request without a valid logout session returns
401; a successful logout returns 204. Authorize mutations against the session
revocation state when admitting them. Work already durably admitted before
logout can finish; subsequent authorizations fail. Define which authenticated
requests renew inactivity, excluding background dashboard polling so an idle
open tab does not keep the session alive forever. These are proposals, not
previously approved in-flight or timeout semantics.

Producer TLS identity and admin cookie authentication are separate boundaries.
Carry forward [RA-01-16](REMOTE-API-ACCESS-CONTRACT.md), fail closed on identity
mismatch, and never trust a public caller's generator header. Proxy product,
packages and deployment qualification remain P02/P03 work; this draft does not
select an unqualified proxy or enable remote ingress.

**Proposed read contracts:** lists take limit (default 50, maximum 256) and an
opaque continuation cursor, return items and next_cursor, and never promise a
cross-request snapshot. A cursor is pagination state, not a job identifier.
Bound stale cursor behavior in the schema. History excludes cleared jobs;
retained-data lists preserve original job_id selection for owned remnants.
Status retains persisted condition, measured file evidence, attempts/deadlines,
and cancellation/deletion progress; distinguish facts from live storage health.
Retain detailed existing job status and retention fields until an explicit
replacement schema is reviewed. Cached/read-only requests must not probe NFS.
Final field-by-field read schemas are part of the next OpenAPI deliverable,
not silently supplied by the broader historical examples.

## Package 2: producer identity, retained data and existing state

The reviewed producer body is:

```json
{
  "generator_id": "recorder-01",
  "recording_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_directory": "/mnt/nfs/recordings/run-0042",
  "files": ["camera1/video.bin", "camera2/video.bin", "metadata.json"]
}
```

**Proposed successful receipt:** HTTP 202, Content-Type application/json,
with the following minimum body. Location may identify the authenticated admin
status route but does not impose producer polling or grant operator access.

```json
{
  "job_id": "42",
  "recording_id": "550e8400-e29b-41d4-a716-446655440000",
  "accepted": true,
  "source_paths_released": true
}
```

Validate the echoed UUID and complete release confirmation before reusing
paths. An identical replay returns the same custody meaning and original job
ID; it never implies destination completion. Missing/malformed acknowledgement
means preserve paths and alert under the approved retry/protocol rules.

The approved producer error envelope has exactly these five required fields;
optional diagnostics, if any, need bounded schema review:

```json
{
  "recording_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": "source_file_missing",
  "retryable": true,
  "retry_after_seconds": 5,
  "source_paths_released": false
}
```

This example uses HTTP 409; the shown delay is illustrative. Use null for an
unavailable/unsafe recording_id and for retry_after_seconds when retryable is
false. A false release field grants no new permission and never revokes an
earlier confirmed 202. Retain every approved typed error mapping and recorder
JSON-delay/header/fallback order; publish all codes and precedence in the later
registry rather than substitute generic errors here.

**Proposed lexical rules:** accept canonical hyphenated UUID text in either
hexadecimal case, store/compare lowercase; reject braces, URN and unhyphenated
forms. Do not impose a new UUID-version restriction. Compare file membership
by exact validated relative path bytes, retaining original durable indices.
Reject duplicate, absolute, empty, dot/dot-dot and reserved internal paths,
backslashes and controls. Require UTF-8; do not case-fold or normalize Unicode.
Do not resolve filesystem aliases to make a changed request appear identical.
A lexical source-directory rule must be explicit, distinct from authorized
source binding and filesystem identity; propose absolute slash-separated paths
without dot/dot-dot, repeated separators or trailing slash except root.
Existing binding/ownership checks still decide whether that path is authorized.

Propose rejecting unknown top-level fields and using current bounded admission
as the starting point: 64 KiB request body, 8 KiB headers, at most 256 files,
4095-byte relative paths. Publish final per-field and configuration limits in
the schema, including source-directory length, identifier bounds and batch/list
limits. No new mandatory optional metadata or producer-supplied hashes.

Replay must separate immutable request identity, existing custody evidence,
current expected-size comparison policy and new-key admission. Disabled size
comparison must not accidentally erase changed-assertion conflicts. Adding,
removing or changing the supplied map is already a request conflict,
including when comparison is disabled. Finalize only the conditional validation
ordering when the setting changes. Preserve established whole-set 202;
never reopen producer-reused original paths to revalidate an accepted replay.
Destination unavailability alone does not prevent the approved source handoff
when source authority, custody and admission are independently proven. ER-D07
still requires exact binding/admission precedence; it does not reopen that
outage behavior or authorize a generic destination HTTP failure.

**Proposed persistence approach:** design an explicit transactional upgrade for
new global UUID ownership alongside original job/file identifiers. Preserve old
source/destination paths, database evidence, enrollment, worker epochs, receipts
and manifest bytes. Legacy non-UUID jobs remain legacy operational records;
do not invent UUIDs or reinterpret their paths. If an upgrade cannot prove safe
preservation, refuse startup before effects with documented operator guidance.
This is a migration design requirement, not permission to discard old state or
claim that a migration has already been implemented or qualified.

After clear, retain only the separate operational ownership/accounting necessary
to manage the old files by original job_id, without consulting that record for
producer UUID replay recognition. Reusing a cleared UUID creates a new job ID.
It grants no rights over old files: refuse occupied/conflicting destination
names using existing no-clobber protections; do not adopt old output or silently
add suffixes. The retained-data list must not restore forgotten UUID recognition
or require another public identifier. Exact retained record fields and access
rules are part of the persisted-state design review.

## Package 3: actions, request replay and observable results

Approved compact request shape, illustrated with numeric existing job IDs:

```json
{"job_ids":[42,43,42]}
```

**Proposed schema:** positive signed-64-bit integers, nonempty list, maximum
256 entries. Preserve current decimal-string job_id responses and decimal path
parameters unless deliberately replaced during schema review; document this
existing wire asymmetry rather than invent another identifier. Serialize each
job's decisions against its persisted state, in submitted order within a batch;
concurrent batches may interleave between jobs. No batch-wide atomic success.
A storage failure must not fabricate successful attempt counts.

Example cancel/retry acceptance body (counts of dispatched occurrences):

```json
{"accepted_count":1,"failed_count":1,"skipped_count":1}
```

Example completed clear body:

```json
{"cleared_count":2}
```

**Whole-request replay is a remaining decision, with audited retry semantics
preserved.** Cancellation, clear and deletion need explicit lost-response and
repeated-request outcomes against current stored state. Do not generalize that
behavior to failed-work retry: an old accepted retry request must replay its
original result and must never release a later review epoch. Duplicate entries
inside one request remain separately dispatched under the approved rules; this
does not settle transport replay of that request.

Keep the existing exact-command replay and review safeguards from
[increment 08](RUST-INCREMENT-08.md), including stale-review refusal and recorded
receipts. Atomically reading the latest review epoch does not prove fresh admin
intent. The job_ids-only bulk body and prohibition on another identifier scheme
mean the exact replay/intent mechanism still needs design. Options must preserve
the existing job ID and compact body while proving the operator acted on the
specific reviewed state, for example through protected precondition context;
group 49 selects an immutable request header for the existing review version
and audit context, while keeping the job_ids-only body. Exact header spelling,
encoding/bounds and transactional receipt design remain pending. No new public
command identifier or confirmation dialog is added. Complete that design and
the later-epoch replay cases before implementation.

Propose that duplicate retry within one batch fails eligibility after an earlier
entry schedules it; missing or completed entries skip. This rule is still a
proposal, unlike the already approved duplicate cancel failure. The complete
eligibility/count table must include ineligible review states, repeated whole
requests and partial durable storage failures. Preserve ownership/binding checks
and the audit trail; compact input is not permission to bypass them.

Deletion needs special care: a 202 is acceptance, not a completed count. Propose
initial deleted_count/failed_count as actual observations so far, plus
completion_pending:true; later authenticated retained-data/job status exposes
actual final counts under that same job_id. No fabricated zeros meaning final
success, new deletion-job identifier or automatic resubmission. Decide whether
counts are per latest admitted request or cumulative, and how a lost reply is
reconciled, before freezing these fields.

Bind deletion confirmation to the displayed owned file set. Prefer a server-side
snapshot of existing job/file identities with revalidation at admission and
safe stop; reject changed selection instead of widening deletion. The exact
confirmation transport and stale-confirmation response remain a design decision,
not an excuse for an extra job identifier or a general repair workflow.

Clear/cancel/delete/retry races must preserve these invariants: no clear before
completed safe cancellation; no deletion of committed output or producer-reused
originals; no retry of safely cancelled work; no stale job ID redirected to a
new job sharing a forgotten UUID; no file disposal from a count or error alone.

## Package 4: consumer manifest and compatibility

**Proposed manifest v2:** COMMITTED.json contains version:2, instance_id, job_id,
generator_id, recording_id, request_identity and files. Proposed request_identity
is a versioned canonical-request SHA-256 binding, distinct from a job identifier:
include generator, canonical UUID, source directory, sorted file membership and
the complete original expected-size map, distinguishing its absence. Freeze
canonical encoding, digest representation and known-answer fixtures before
implementation. UUID/job identity alone is insufficient to bind these assertions.
Each file entry retains stable file_id, path, measured size_bytes,
algorithm:"sha256" and lowercase full sha256. Keep
strict bounded parsing, exact membership and immutable serialized bytes across
replay. Never use an expected size as measured evidence or claim POST 202 means
this manifest is ready. Keep source-read hashing plus destination staging
reread verification and no-clobber durable publication.

Existing v1 manifests contain submission_id. Preserve those bytes and continue
recognizing their recorded ownership during recovery; do not rewrite committed
output to v2. New recordings use v2 only after explicit consumer compatibility
approval. Freeze JSON numeric precision for byte sizes (current u64 numbers
versus exact decimal strings), byte encoding, maximum manifest size and complete
schema before producing fixtures. Recording metadata remains excluded from the
minimal producer schema unless separately approved; the ordinary metadata.json
file above is simply a transferred payload.

## Coverage and execution order

| Existing acceptance rows | Proposal coverage / work still required |
|---|---|
| API-E01-60 | Producer framing, identity, custody, replay, typed errors and remote boundary; retain every approved mapping, finalize precedence |
| API-E61-74 | Size-map/current-policy behavior, unordered replay and UUID lexical rules; package 2 |
| API-E75-99 | Clear/cancel/ownership/deletion safety and asynchronous observations; packages 2-3 |
| API-E100-105 | Remote admin, host-local account and session lifecycle; package 1 |
| API-E106-122 | Confirmations, action bodies, repeated entries, statuses/counts; package 3 |
| API-E123-128 | Cookie sign-in, global logout and approved auth responses; package 1 |
| API-E129 | Approved reviewed-state retry header; exact encoding, bounds and receipt design pending; package 3 |

This table indexes all 129 cases; it is not an executed-test manifest or a claim
that the remaining fields are approved. SC-001-180 and DOC-01-06 retain their
existing evidence and pending status. Do not add passing evidence from review.

After these decisions are settled, produce versioned OpenAPI, the complete
error/precedence registry, manifest schemas/fixtures, and a one-row-per-case
acceptance map, then freeze P01. Implement short slices in this order: durable
identity/migration; producer mapping/replay; protected ingress; session/dashboard
reads; audited actions; separately gated deletion. Maintain operator guidance
alongside each slice. Required Rust validation is both pinned cargo-libc/SLES
gate modes, followed by the finite affected NFS/remote/systemd cases and P04-P12
closure. Old ABI passes do not qualify changed artifacts or physical effects.

No Rust source, dependency, service state or release gate changes are authorized
by this draft. All eight release gates remain open; production NFS, source
deletion and unrestricted remote ingress remain disabled.
