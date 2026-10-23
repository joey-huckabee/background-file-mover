# Rust REST API contract draft

The 2026-10-23 [error-scenario review](REST-ERROR-SCENARIOS.md) records the
current discussion, approved error groups 1-14, remaining schema decisions and
implementation differences. Follow API-I01-06; resolve remaining schema and
persisted-state details before freezing OpenAPI or changing runtime responses.
The discussed global recording ID/full source directory/string-file form is
not the implemented wire format shown below. That document labels agreed
workflow decisions separately from pending field compatibility/error mappings.


This proposal extends the existing job-oriented REST interface to completed
recording sets and makes source-path release explicit. Review it alongside
[TRANSFER-PROTOCOL.md](TRANSFER-PROTOCOL.md). It is a starting point for producer
integration or a frozen schema. The minimal local generator form and health
route are implemented in [increment 04](RUST-INCREMENT-04.md); that document
defines the implemented subset and its limits. Automatic delivery/manifests are
implemented in [increment 06](RUST-INCREMENT-06.md); the read-only individual
`GET /api/v2/jobs/{job_id}` response is defined in
[increment 07](RUST-INCREMENT-07.md). That implemented status shape takes
precedence over examples below. [Increment 08](RUST-INCREMENT-08.md) defines the
implemented audited delivery-only resume request/receipt; the broader controls
below remain proposals. [Increment 09](RUST-INCREMENT-09.md) defines the
implemented exact-file `reset-missing` command.
[Increment 10](RUST-INCREMENT-10.md) defines read-only global and per-job
retention accounting. [Increment 15](RUST-INCREMENT-15.md) defines implemented
startup readiness: HTTP handling and `/healthz` begin after source singleton
custody and confirmed bootstrap child exit. A bound TCP port alone is not
readiness; pending startup responds to shutdown signals but serves no HTTP
response. NFS remains disabled. Remaining routes/forms are proposals.

## Reviewed producer shape (implementation pending)

The user confirms that no one uses the Rust prototype API. Replace its old
producer request format directly; an adapter, parallel old/new producer schema
or deprecation period is unnecessary. This does not waive stored-job/custody
preservation or the separate legacy C++ cutover gate.

```json
{
  "generator_id": "recorder-01",
  "recording_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_directory": "/mnt/nfs/recordings/run-0042",
  "files": [
    "camera1/video.bin",
    "camera2/video.bin",
    "metadata.json"
  ]
}
```

The source directory is absolute as visible to the mover, inside the generator's
approved scope. Recording IDs are globally unique; retry the same ID/request.
Destination selection belongs to startup configuration and subfolders are
preserved beneath the recording-ID destination folder. This minimal form does
not require file sizes when checking is disabled (the default). The approved
optional expected_sizes_bytes map is all-or-nothing. When checking is enabled,
require the complete map and compare all values; when disabled, a supplied
complete map is ignored for expected-size comparison. Partial/extra/invalid maps
are 400 invalid_submission in either mode. Actual claim-size measurement and
copy integrity checks remain mandatory. See
[group 14 and its concrete 100-versus-200-byte scenario](REST-ERROR-SCENARIOS.md#expected-size-policy-group-14)
for API-E61-66. Exact config spelling and persisted policy replay rules still
need design; no new toggle/map is implemented yet.

Examples below using submission_id/source_path/file objects describe the current
prototype and earlier proposals, not the reviewed replacement wire schema.
They remain reference material pending the P01 OpenAPI rewrite. Do not implement
both forms by default or treat these older examples as frozen compatibility.

## Existing interface and proposed changes

The C++ [submission handler](../cpp/src/router.cpp) accepts `POST /api/jobs`
with exactly `{"source":"/absolute/file","dest":"/absolute/file"}` and returns
`202 {"job_id":"..."}` after recording/queueing. The
[codec](../cpp/src/api_codec.cpp) rejects unknown fields and represents a job
with `id`, `source`, `dest`, `state`, timestamps, byte counters and a string error.
Pause/resume/cancel/retry handlers exist; retry allocates a new job. This contract
does not supply recording-set claims or idempotency keys.

[cpp/README.md](../cpp/README.md) lists GET job/list/status routes as a **target
shape**, rather than proof that all those read routes are implemented here.
The Rust proposal retains those resource concepts, under a versioned prefix
because the request/state/retry meanings change. Decide any legacy adapter
during cutover rather than silently accepting old requests with new semantics.

| Proposed route | Purpose |
|---|---|
| `POST /api/v2/jobs` | Durably accept and claim all files before returning 202 |
| `GET /api/v2/jobs/{id}` | Read milestones, claim release, progress and condition |
| `GET /api/v2/jobs/{id}/files?limit=...&cursor=...` | Bounded file details |
| `GET /api/v2/jobs?limit=...&cursor=...` | Bounded job summaries |
| `POST /api/v2/jobs/{id}/pause` | Persist desired pause; settle started effects |
| `POST /api/v2/jobs/{id}/resume` | Resume this retained job when safe |
| `POST /api/v2/jobs/{id}/cancel` | Stop new work without discarding owned data |
| `POST /api/v2/jobs/{id}/retry` | Request safe reconciliation/retry of this job |
| `GET /api/v2/status` | Bounded aggregate operational status |
| `GET /healthz` | Coordinator liveness, independent of NFS availability |

There is no separate client `claim` call. Claiming starts automatically after
acceptance under admission policy. A client cannot set a job to `Claimed`.

## Generator submission with a configured destination

The proposed first remote profile uses the
[remote access contract](REMOTE-API-ACCESS-CONTRACT.md): manually provisioned
client certificates verified by an external proxy, protected producer-only Unix
socket, peer/principal binding and no service-issued token. This is design only;
current loopback binding and Authorization rejection remain unchanged. The
[registration/token proposal](GENERATOR-REGISTRATION-DRAFT.md) remains deferred;
its future tokenless profiles are not anonymous remote permission.

The additive generator form identifies the recording generator and supplies a
source directory plus explicit file names. It contains no destination. The
service selects the destination from configuration loaded at startup.

The remote mover is confirmed to have access to the generator's source NFS
mount. It claims the files there before 202; submission transports metadata only.
Mount paths may differ between hosts, so confirm approved path mapping separately.

```http
POST /api/v2/jobs HTTP/1.1
Content-Type: application/json

{
  "generator_id": "recorder-host-a",
  "submission_id": "recording-0042",
  "source_path": "/mnt/recordings/current",
  "files": [
    {"name": "video/video.bin"},
    {"name": "telemetry/telemetry.bin"}
  ]
}
```

`source_path` names a directory **as visible to the mover**, inside a source root
approved for that generator. This is a metadata request, not an upload of file
contents or access to an arbitrary path on another computer. Each `name` is a
relative file path beneath that directory; subfolders are permitted. Reject
absolute paths, backslashes, empty components, `.`/`..`, NUL, duplicate paths
and invalid encoding. Use `/` between components. Resolve paths using the protocol's safe
descriptor traversal, not string-prefix checks. Persist both the supplied form
and the normalized root/relative-file mapping.

`submission_id`, `source_path` and `files` are required in the generator body.
Supply `generator_id` unless a valid token or explicitly configured tokenless
profile resolves it; any supplied identity must match the authorized identity.
`recording_id`, `producer_handoff` and file `file_key` remain optional
metadata/assertions. If omitted, the service uses its job ID as recording identity
and assigns stable file IDs. The completed/immutable producer contract still
applies when its assertion field is omitted; startup generator registration
establishes that contract. The recorder generates one unique `submission_id`
per recording and retains it, including across restarts, until it receives 202.
Retries reuse that ID and the identical submission details; new recordings use
new IDs even when their paths/names are reused. The body field is the generator
form's idempotency key, so no separate header is required. The advanced explicit
form retains its Idempotency-Key header. If both representations are supplied,
they must agree; reject conflicting values rather than choosing one silently.

For example, `video/video.bin` resolves beneath
`/mnt/recordings/current/video/`. List each file explicitly: this does not request
a recursive directory scan or relocation of its directory. Claiming preserves
the file's original relative-path mapping while moving it into private custody.
Parent/subfolder names must remain stable until the all-files release. The service
does not remove empty producer directories. **Agreed generator destination layout:**
preserve every submitted relative file path beneath a service-owned recording
folder. For example, `video/camera.bin` becomes
`recordings/<job-id>/video/camera.bin`. Only folders needed for listed files are
created; empty/unlisted source folders are not discovered or copied. A future S3
adapter preserves the same relative path in its object key beneath the configured
prefix and unique recording prefix; these are key prefixes, not actual directories.

Reject file/directory conflicts such as listing both `video` and `video/camera.bin`,
reserved control/staging/manifest paths, and collisions under the qualified
destination's filename semantics. Preserve paths rather than flattening them or
silently renaming a collision. Configured naming chooses the recording's container;
it does not change the generator's relative paths within that container. The
advanced explicit-destination form retains its separately configured mapping.

**Agreed configurable grouping:** startup `[delivery]` setting
`group_by_generator` chooses the container layout for generator submissions:

| Setting | Relative destination path |
|---|---|
| `false` | `<job-id>/<submitted-relative-path>` |
| `true` | `<generator-component>/<job-id>/<submitted-relative-path>` |

Paths are relative to the configured filesystem root or S3 prefix. False is the
compatibility default for the earlier flat recording-container layout; operators
may enable grouping. Neither setting flattens the submitted subfolders or makes
the generator choose a destination. Build generator components from validated
configured identities, never unchecked JSON path fragments, and reject component
collisions under destination semantics. Snapshot the chosen grouping and resolved
paths at acceptance; toggling it affects new jobs only, not pending-job retries.
The manifest remains inside each recording container. This option does not alter
the advanced explicit-destination form's separately configured mapping.

### Optional expected size

`size_bytes` is optional in both v2 forms. The service obtains the actual logical
byte size from the opened regular file during claiming, confirms the same object
and stable size after relocation, and durably records that size in the claim
receipt before reporting release. It does not read the payload to measure size.
Copying and verification must match this recorded claimed size.

When supplied, `size_bytes` is a nonnegative integer expected-size assertion,
including zero for an empty file, not authority to truncate/pad the transfer.
A mismatch blocks claim confirmation for the job and reports
`source_size_mismatch`, retaining any files already in custody. A changed size
during claim/copy also blocks advancement. Closed writers and immutability
remain required; measuring a size does not make a changing file safe.

Before inspection, actual sizes and `copy_bytes_total` may be `null`; expose
unknown sizes distinctly from zero. Declared expectations are separate from
observed claim sizes. Once all claims are confirmed, the actual total is known.

`generator_id` is a stable configured identity, not a credential. Bind it to the
authenticated caller where authentication exists, or an explicitly trusted local
deployment. An untrusted caller cannot gain another generator's source access by
putting its ID in JSON. Reject unknown/unauthorized generators and source roots
outside their scope before acceptance. Multiple generator instances on different
hosts receive distinct configured identities; do not infer identity from filenames.

### Additive request forms

Keep the previously drafted explicit-root/destination form below as an advanced
submission use case. The generator form is an additional alternative, not a
requirement added to every existing request. Select the generator form by
top-level `source_path`/`submission_id`; it requires file `name` fields and rejects
client destination fields. The explicit form requires `destination_root_id`
and each file's source root/path. Reject mixtures and unknown fields. Explicit
destination selection is allowed only within configured caller permissions;
the generator workflow always uses its configured route.

The historical C++ `/api/jobs` `{source, dest}` contract is unchanged by this
addition. Only the minimal local generator subset is currently implemented;
the advanced form and optional metadata remain proposals.

## Explicit destination submission

```http
POST /api/v2/jobs HTTP/1.1
Content-Type: application/json
Idempotency-Key: host-a-recording-0042

{
  "recording_id": "scenario-17-run-42",
  "producer_handoff": "completed_immutable",
  "destination_root_id": "archive",
  "files": [
    {
      "file_key": "video",
      "source_root_id": "recorder-a",
      "source_path": "current/video.bin",
      "size_bytes": 100000000000
    },
    {
      "file_key": "telemetry",
      "source_root_id": "recorder-a",
      "source_path": "current/telemetry.bin",
      "size_bytes": 12000000
    }
  ]
}
```

Root IDs identify administrator-approved locations; source paths are relative.
When provided, `file_key` identifies an entry within the recording; the service also assigns
internal file IDs. Destination names follow configured naming policy and are
resolved/persisted at acceptance. The service owns a unique recording directory
and never overwrites a collision. No `overwrite` option is available.

`completed_immutable` asserts that writes are finished and synchronized, writers
are closed, there are no writable aliases, and entries/parents remain unchanged
until all-files claim confirmation. A JSON field cannot prove that condition;
the recorder must enforce it in its lifecycle.

For filesystem delivery, SHA-256 during copying plus destination reread is mandatory initially. An optional
producer expected digest can be added during schema review; this request does
not require prehashing. Source-cleanup policy is service-controlled and returned
in status. Initial implementation keeps sources; a submission cannot enable
administratively disabled deletion or bypass verification.

## Acceptance response

**Agreed producer workflow:** submit, wait for `202`, optionally log the receipt,
then forget the transfer. The recorder leaves submitted files and folders untouched
until that response. No status polling or later completion acknowledgement is required.
Internally Accepted and Claimed remain separate durable facts, but the POST's
successful handoff response confirms both.

Example response for the generator submission:

```http
HTTP/1.1 202 Accepted
Location: /api/v2/jobs/job-0042
Content-Type: application/json

{
  "job_id": "job-0042",
  "generator_id": "recorder-host-a",
  "recording_id": "job-0042",
  "accepted": true,
  "claim": {
    "status": "Claimed",
    "files_total": 2,
    "files_claimed": 2,
    "source_paths_released": true
  },
  "status_url": "/api/v2/jobs/job-0042"
}
```

Return this only after acceptance and every required claim/receipt are durable.
It permits immediate reuse of all submitted paths, without waiting for destination
copying, verification or commitment. It does not release source disk capacity.

**Agreed outage behavior:** destination unavailability alone does not prevent
claiming or returning 202. If local state storage, source claiming and configured
retention/admission limits permit handoff, claim every file, return 202 and queue
delivery until the pinned destination recovers. The recorder has no further
responsibility. Operators see destination unavailability separately from handoff.

Retention limits cover pending jobs/bytes and source-filesystem free-space margins.
Measure optional-size submissions in bounded source inspection before authorizing
claims, reserve queue capacity durably, and account for partially claimed jobs.
Claim relocation does not free payload space; limits protect capacity for future
recordings rather than pretending a rename allocates another payload copy.
Reconcile reservations after restart and release them only at their defined
cleanup/archive boundary. External writers can consume space too, so checks
are admission controls, not guarantees of future free space.

If safe admission or claiming is unavailable, return a non-202 response and retain
any already claimed data for reconciliation. Do not delete claims, reroute a job
or issue false success to make room. The
[source-space admission policy](SOURCE-SPACE-ADMISSION-DESIGN.md) defines
optional/default-off byte and percentage thresholds, bounded fresh measurements
and new-key-only gating, implemented locally in [increment 36](RUST-INCREMENT-36.md).
503 `source_space_low` and `source_space_unavailable` create no job and release no
paths. Cold/expired new-key requests can await a shared probe asynchronously and
recheck once within the existing ten-second handoff budget; at most two waiters
are allowed. Missing/error/late results remain retryable unavailable. A recorder
need not retry faster than cache expiry. Existing-key replay/partial claims bypass
this gate but retain ordinary safety/ledger checks. Global retention reports the
separate cached source observation without doing filesystem I/O on GET. Delivery
retry timing and per-job status/epochs are unchanged; wider storage qualification
is still required.

Do not hold an unbounded HTTP request during an NFS outage. Use a bounded handoff
wait; if claiming cannot be confirmed in that time, return a non-202 transient
response such as `503 handoff_pending`, with Retry-After. Timeout/disconnection
does not cancel the accepted job. The recorder keeps paths untouched and retries
the identical request/key with backoff. Waiting HTTP requests and duplicate
requests are bounded independently of the durable claim operation.

Generator jobs return `generator_id` in acceptance/status/file ownership records
and include it in completion manifests. Explicit-form jobs may omit it until
an authenticated submission identity is supplied. Generator idempotency keys
are scoped to the authorized generator; define the explicit form's caller scope
before freezing authentication. Resolve replay against the original durable
request before selecting a new destination, so a configuration change cannot
reroute a replayed job. Current caller authorization still applies.

Repeat the same POST/key after any lost response. An equivalent normalized
request for an already claimed job returns `202` again with the same job ID and
release receipt, even if destination processing has since advanced or failed.
A still-unclaimed job uses the same bounded handoff wait and returns no 202
until claims are confirmed. Replay never opens the producer's reused paths.
A changed request returns `409 idempotency_conflict`. JSON member order does not
change request identity. Array normalization and recording-ID uniqueness remain
review items; the key is the authoritative submission identity in this draft.
Keep durable key tombstones when archiving jobs so retries cannot create another
transfer by silently reusing a pruned key.

A different key submitting a source path reserved by an unreleased job receives
`409 source_reserved`; it cannot create a competing claim. After all-files
release, a new key may submit the next recording at those same paths.

## Optional operator status

These read routes support operators and dashboards. The recorder does not need
to call them. The successful POST already carries the source-release receipt.

```http
GET /api/v2/jobs/job-0042 HTTP/1.1
```

```json
{
  "job_id": "job-0042",
  "generator_id": "recorder-host-a",
  "recording_id": "job-0042",
  "revision": 8,
  "accepted": true,
  "claim": {
    "status": "Claimed",
    "files_total": 2,
    "files_claimed": 2,
    "source_paths_released": true
  },
  "desired_execution": "Running",
  "condition": "Ready",
  "transfer_phase": "Copying",
  "recording_committed": false,
  "source_cleanup": "Disabled",
  "complete": false,
  "progress": {
    "copy_bytes_total": 100012000000,
    "copy_bytes_completed": 24000000000,
    "verified_files": 0,
    "published_files": 0
  },
  "error": null
}
```

`source_paths_released: true` permits reusing **all** source names from this
request. It requires every claim and its synchronization/receipt to be durably
confirmed, without waiting for copying, verification, manifest publication or
deletion. It does not mean occupied source disk space has been freed.

Release is a durable monotonic fact. A later destination failure/pause does not
revoke it. Retry uses claimed files, not the producer's newer `current/video.bin`.
If claimed data is later quarantined, report a separate blocked condition;
do not demand that the producer restore its old names.

Before release, claim status is `Pending`, `Claiming` or `Partial`. Errors and
`ReconcileRequired` belong to `condition`. One of two claimed files produces
`status: "Partial"`, `files_claimed: 1`, and `source_paths_released: false`.
This draft provides no per-file release permission; file details are diagnostic.

Operator polling uses bounded intervals/backoff. A failed GET never permits reuse. Status
responses carry `Cache-Control: no-store`; revisions help discard old snapshots.
A bounded long-poll/event stream is a possible later addition.

## Completion and errors

**Agreed consumer contract:** destination consumers wait for a valid supported
`COMMITTED.json` before using the recording. Publish that immutable marker only
after every listed file is verified and published. It lists the exact required
relative paths, actual sizes and integrity evidence, bound to generator/job/
recording identity. Consumers ignore uncommitted folders and temporary entries;
marker presence alone is insufficient if its contents are invalid. The future S3
adapter uses a completion object with the same consumer meaning, subject to its
separate publication/verification qualification.

**Agreed cleanup policy:** production operation automatically deletes claimed
source files after the entire recording is verified and its completion manifest
is durably committed, when startup configuration enables deletion. Configure
`delete_source_after_commit = true` or `false` under `[delivery]`; generators
cannot override this setting. First implementation/test profiles explicitly use
false until the cleanup failure gates pass. Production move profiles use true.

Record the selected policy with each accepted job. Deletion also requires the
currently loaded service setting to permit it: restarting with false inhibits
new cleanup authorizations for existing jobs as well. It does not restore files
already deleted. Jobs accepted in retention mode remain retained if a later
restart enables deletion; changing their recorded policy requires an explicit,
audited operator action, whose interface remains future work.

With deletion disabled, keep claimed sources in private custody and report
committed delivery with retained sources; never restore them automatically to
the producer's reused paths. Retained data remains part of source-space accounting.
With deletion enabled, cleanup failure is retried independently of delivery,
without recopying the committed recording or touching original producer paths.

`recording_committed: true` means manifest/file receipts have been reconciled
and recorded. Consumers may see a valid manifest earlier if filesystem
publication succeeds but SQL result persistence fails. Claim release is unaffected.

The same public commitment/cleanup milestones apply to future qualified S3
delivery. REST clients do not need to know whether publication used POSIX files
or objects. Backend-specific verification and receipts must support those facts;
they cannot be inferred from a successful HTTP upload alone.

With deletion enabled, cleanup progresses through `Pending`, `Running` and
`Complete`. Cleanup failures keep a committed recording with pending cleanup;
they do not recopy it. `Disabled` means claimed sources remain retained.
`complete: true` identifies a completed destructive move, after all enabled
cleanup obligations; retained-source commitment is reported separately.

```json
{
  "error": {
    "code": "source_unavailable",
    "message": "A required source could not be confirmed in mover custody",
    "job_id": "job-0042",
    "file_key": "telemetry",
    "phase": "Claiming",
    "retryable": true,
    "reconciliation_required": true
  }
}
```

Stable codes support clients; messages explain problems without exposing private
claim paths. `retryable` permits requesting controlled retry; it does not permit
rewriting handed-off files. After acceptance, transfer errors appear in job
status. HTTP 200 on GET means the query succeeded, not that the transfer did.

Malformed JSON, unknown/duplicate fields, invalid paths or bounds return 400;
oversized bodies 413; unknown jobs 404; conflicting submissions/invalid controls
409; admission/unavailable storage 503; unexpected internal errors 500.
An acceptance failure response cannot certify that SQL never committed; retry
with the same key. Later source problems remain attached to the accepted job.

For submission, only 202 certifies completed handoff. Transient failures/timeouts
are retried with the same key; malformed or conflicting submissions require
correction/operator intervention rather than an endless rapid retry loop.
**Agreed recorder behavior:** retry network timeouts/disconnections and temporary
service responses with the same submission ID and identical request, using bounded
backoff and Retry-After when provided. Stop automatic retries and log errors that
require correction or operator review, including invalid submissions, conflicting
IDs and `recording_blocked`. Non-202 responses carry a stable error code and
`retryable` indication; do not infer retryability from status class alone.
Authentication/authorization errors also require correction rather than blind retries.

A stop/log decision is not permission to reuse source paths. Without 202, the
recorder must leave the submitted files/folders untouched and escalate the
handoff problem. Already accepted jobs and partial claims remain durable; stopping
client retries does not cancel them. Operator resolution may safely resume the
same job, after which the recorder can retry the same ID to obtain its 202.
Define exact backoff timing and restart-persistent pending/error records before
implementation. A new submission ID must not be used to bypass a failed handoff.

Control acknowledgements persist desired execution and return 202 when effects
remain asynchronous. Pause/cancel do not promise syscall cancellation or automatic
restoration. Retry retains job ID, resolved names, claimed sources and ownership,
allocating new internal operation attempts only when safe. This changes the old
new-job retry behavior, which could reopen a newer recording at a reused path.

## Missing file retry and operator review

**Agreed missing-file behavior:** when a listed file is confirmed absent from
its expected source location, check again with bounded backoff for a configurable
period. Start/persist that file's retry deadline at its first confirmed absence.
Repeating the submission or restarting the service does not reset the deadline.
The overall job remains unacknowledged while any required file is unclaimed.

During the window, POST handoff attempts return a transient non-202 response
such as `503 handoff_pending` if their bounded wait expires. After the missing
file's window expires, persist `Blocked` with `source_missing_review_required`
and require an explicit operator retry/reconciliation decision. POST returns
`409 recording_blocked`, naming the original job for logging, rather than 202.
The recorder stops automatic retries and logs this review-required response;
repeating its JSON cannot silently reopen a blocked job.

Never omit the missing file, publish an incomplete set, discard already claimed
sources, release source-path reservations or restore files onto reusable names
to settle the error. An operator can inspect the exact missing entry and resume
the original job when safe; any reset of its retry window is explicit and audited.
Loss of mount access or uncertain NFS results is an endpoint/reconciliation
condition, not evidence that a file is absent. Do not certify absence from a
cached observation alone. The agreed startup default is
`missing_file_retry_window_seconds = 300` under `[delivery]`. Snapshot that
duration with each accepted job; later configuration changes apply to new jobs,
not existing deadlines. This five-minute window is independent of the shorter
bounded HTTP handoff wait and begins at confirmed absence, not request receipt.

## Remaining producer integration review

- Can the recorder enforce closed writers, synchronized completed files and
  unchanged entries/parents until all-files release?
- Is all-files release sufficient, or does preparation need individual release?
- Can generators provide mover-visible source directories and explicit names,
  and can consumers honor manifest visibility and retention through cleanup?
- Should `recording_id` be unique within a producer scope independently of keys?
  Define authentication/producer scope before remote use.
- Set filename encoding, naming/metadata policy, body/file/page bounds, key
  retention and detailed control semantics before freezing the schema.

Resolve relevant decisions before the dependent API/effect implementation;
independent pure-core and storage tests can proceed now. Registration/token work
is explicitly deferred, with a one-time setup key selected for later enrollment.
Preserve loopback by
default, external TLS and strict hostile-input tests while revising the REST
requirements for this contract.

## Startup destination configuration

Illustrative INI schema for a mounted file share; this is a design example,
not configuration accepted by the current C++ binary:

```ini
[delivery]
default_destination = archive
group_by_generator = false
delete_source_after_commit = true
missing_file_retry_window_seconds = 300

[destination:archive]
kind = filesystem
path = /mnt/archive/recordings

[generator:recorder-host-a]
source_root = /mnt/recordings
```

Every configured generator uses the default destination unless an administrator
sets an explicit per-generator `destination` override. The generator submits
the same request either way. Validate all references/source permissions at
startup. Unavailable storage is a readiness/health condition, not automatically
invalid syntax or permission to use an underlying local directory.

To route newly accepted jobs to S3, the future configuration could instead use:

```ini
[delivery]
default_destination = object-archive
group_by_generator = false
delete_source_after_commit = true
missing_file_retry_window_seconds = 300

[destination:object-archive]
kind = s3
bucket = recording-archive
region = us-east-1
prefix = recordings/
credential_profile = file-mover

[generator:recorder-host-a]
source_root = /mnt/recordings
```

Credentials are obtained by the service using an administrator-controlled
provider/reference, never submitted by generators or included in job responses.
Pin the nonsecret destination identity, backend kind, path or bucket/region/
endpoint/prefix, naming and integrity/cleanup policy at acceptance. Restarting
with a changed route affects new jobs only. Pending jobs keep their original
destination; if that destination can no longer be accessed, block rather than
reroute. Credential rotation may preserve access to the same pinned target.

Mounted shares use the POSIX claim/copy/verify/publish protocol after qualification
of their actual mount semantics. An S3 adapter needs multipart-upload ownership,
provider-validated checksum evidence, conditional object/manifest publication,
uncertain-completion recovery and version-bound receipts where available.
Amazon S3 supports `If-None-Match: *` on PutObject and CompleteMultipartUpload;
it checks the current object version and does not establish eternal immutability.
[AWS conditional write documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).
Retention/access policy must protect delivered objects through source cleanup.
Qualify S3-compatible providers separately and preserve the
[checksum distinctions](INTEGRITY-DESIGN.md#future-s3-adapter).

S3 is an additional destination design use case. Its adapter, SDK/TLS dependencies
and GNU/glibc 2.22 compatibility remain unqualified. A binary without a qualified
enabled adapter must reject `kind = s3` at startup; it must not silently fall back
to a file destination. No S3 package experiment is started by this contract update.

## Implemented prototype delivery-capacity status

[Increment 33](RUST-INCREMENT-33.md) adds
`destination_capacity_requires_review` to the existing
`details.delivery_retry.code` vocabulary. The JSON shape is unchanged. For a
confirmed ENOSPC during an owned payload copy, failures 1 and 2 remain `Retrying`
with persisted 30/60-second deadlines. Failure 3 becomes `ReviewRequired`; a saved
retry timestamp does not override that condition. This classification does not
apply to allocation, manifest, publication sync, custody or unknown worker outcomes.

Example pending-delivery fragment:

```json
{
  "state": "Claimed",
  "source_paths_released": true,
  "details": {
    "condition": "Retrying",
    "delivery_retry": {
      "failures": 1,
      "retry_after": 1800000030,
      "code": "destination_capacity_requires_review"
    }
  }
}
```

This is a partial illustrative status object; `retry_after` is an absolute Unix
seconds deadline, not an interval. A recorded pending deadline survives restart.
Restoring capacity before review permits automatic delivery at the saved deadline;
restoring capacity after review still requires audited resume. The recorder has no
new polling or recovery obligation after receiving 202. See
[the retry policy](DELIVERY-RETRY-POLICY.md) for scope and persistence limits and
the increment for actual validation; production NFS/deletion remain disabled.
