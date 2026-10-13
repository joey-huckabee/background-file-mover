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
| `POST /api/v2/jobs` | Durably accept a recording set with an idempotency key |
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

## Submit a recording

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
`file_key` identifies an entry within the recording; the service also assigns
internal file IDs. Destination names follow configured naming policy and are
resolved/persisted at acceptance. The service owns a unique recording directory
and never overwrites a collision. No `overwrite` option is available.

`completed_immutable` asserts that writes are finished and synchronized, writers
are closed, there are no writable aliases, and entries/parents remain unchanged
until all-files claim confirmation. A JSON field cannot prove that condition;
the recorder must enforce it in its lifecycle.

SHA-256 during copying plus destination reread is mandatory initially. An optional
producer expected digest can be added during schema review; this request does
not require prehashing. Source-cleanup policy is service-controlled and returned
in status. Initial implementation keeps sources; a submission cannot enable
administratively disabled deletion or bypass verification.

## Acceptance response

```http
HTTP/1.1 202 Accepted
Location: /api/v2/jobs/job-0042
Content-Type: application/json

{
  "job_id": "job-0042",
  "recording_id": "scenario-17-run-42",
  "accepted": true,
  "claim": {
    "status": "Pending",
    "files_total": 2,
    "files_claimed": 0,
    "source_paths_released": false
  },
  "status_url": "/api/v2/jobs/job-0042"
}
```

Return this only after the acceptance transaction commits. It is a snapshot:
claiming may advance before the client receives it. Acceptance does not promise
successful source inspection or transfer. While release is false, the producer
keeps all submitted paths untouched.

Repeat the same POST/key after any lost response. An equivalent normalized
request returns `200 OK`, the same job ID and current acceptance/claim summary.
A changed request returns `409 idempotency_conflict`. JSON member order does not
change request identity. Array normalization and recording-ID uniqueness remain
review items; the key is the authoritative submission identity in this draft.
Keep durable key tombstones when archiving jobs so retries cannot create another
transfer by silently reusing a pruned key.

A different key submitting a source path reserved by an unreleased job receives
`409 source_reserved`; it cannot create a competing claim. After all-files
release, a new key may submit the next recording at those same paths.

## Poll for source release

```http
GET /api/v2/jobs/job-0042 HTTP/1.1
```

```json
{
  "job_id": "job-0042",
  "recording_id": "scenario-17-run-42",
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

Poll with bounded intervals/backoff. A failed GET never permits reuse. Status
responses carry `Cache-Control: no-store`; revisions help discard old snapshots.
A bounded long-poll/event stream is a possible later addition.

## Completion and errors

`recording_committed: true` means manifest/file receipts have been reconciled
and recorded. Consumers may see a valid manifest earlier if filesystem
publication succeeds but SQL result persistence fails. Claim release is unaffected.

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

Control acknowledgements persist desired execution and return 202 when effects
remain asynchronous. Pause/cancel do not promise syscall cancellation or automatic
restoration. Retry retains job ID, resolved names, claimed sources and ownership,
allocating new internal operation attempts only when safe. This changes the old
new-job retry behavior, which could reopen a newer recording at a reused path.

## Producer integration review

- Can the recorder enforce closed writers, synchronized completed files and
  unchanged entries/parents until all-files release?
- Is all-files release sufficient, or does preparation need individual release?
- Can producers use configured root IDs/explicit file lists and consumers honor
  committed-manifest visibility and destination retention through cleanup?
- Should `recording_id` be unique within a producer scope independently of keys?
  Define authentication/producer scope before remote use.
- Set filename encoding, naming/metadata policy, body/file/page bounds, key
  retention and detailed control semantics before freezing the schema.

Resolve these before generating OpenAPI or writing Rust. Preserve loopback by
default, external TLS and strict hostile-input tests while revising the REST
requirements for this contract.
