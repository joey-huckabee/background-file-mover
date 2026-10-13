# Rust REST API contract draft

This proposal extends the existing job-oriented REST interface to completed
recording sets and makes source-path release explicit. Review it alongside
[TRANSFER-PROTOCOL.md](TRANSFER-PROTOCOL.md). It is a starting point for producer
integration, not an implemented API or a frozen schema.

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

The additive generator form identifies the recording generator and supplies a
source directory plus explicit file names. It contains no destination. The
service selects the destination from configuration loaded at startup.

```http
POST /api/v2/jobs HTTP/1.1
Content-Type: application/json
Idempotency-Key: recording-0042

{
  "generator_id": "recorder-host-a",
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

Only `generator_id`, `source_path` and `files` are required in the generator
body. `recording_id`, `producer_handoff` and file `file_key` remain optional
metadata/assertions. If omitted, the service uses its job ID as recording identity
and assigns stable file IDs. The completed/immutable producer contract still
applies when its assertion field is omitted; startup generator registration
establishes that contract. The idempotency header remains required for safe replay.

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
`generator_id`; it requires `source_path` and file `name` fields and rejects
client destination fields. The explicit form requires `destination_root_id`
and each file's source root/path. Reject mixtures and unknown fields. Explicit
destination selection is allowed only within configured caller permissions;
the generator workflow always uses its configured route.

The historical C++ `/api/jobs` `{source, dest}` contract is unchanged by this
design-only addition. Both v2 forms remain proposals, not implemented compatibility.

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
or issue false success to make room. Thresholds and retry timing remain startup
configuration decisions to finalize before implementation.

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
The exact recorder retry/backoff and permanent-error handling remain to be settled.

Control acknowledgements persist desired execution and return 202 when effects
remain asynchronous. Pause/cancel do not promise syscall cancellation or automatic
restoration. Retry retains job ID, resolved names, claimed sources and ownership,
allocating new internal operation attempts only when safe. This changes the old
new-job retry behavior, which could reopen a newer recording at a reused path.

## Producer integration review

- Can the recorder enforce closed writers, synchronized completed files and
  unchanged entries/parents until all-files release?
- Is all-files release sufficient, or does preparation need individual release?
- Can generators provide mover-visible source directories and explicit names,
  and can consumers honor manifest visibility and retention through cleanup?
- Should `recording_id` be unique within a producer scope independently of keys?
  Define authentication/producer scope before remote use.
- Set filename encoding, naming/metadata policy, body/file/page bounds, key
  retention and detailed control semantics before freezing the schema.

Resolve these before generating OpenAPI or writing Rust. Preserve loopback by
default, external TLS and strict hostile-input tests while revising the REST
requirements for this contract.

## Startup destination configuration

Illustrative INI schema for a mounted file share; this is a design example,
not configuration accepted by the current C++ binary:

```ini
[delivery]
default_destination = archive
delete_source_after_commit = true

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
delete_source_after_commit = true

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
