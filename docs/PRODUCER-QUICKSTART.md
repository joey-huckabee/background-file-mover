# Producer quickstart and retry decision table (DOC-01)

For the program that records files and hands them to the file mover (the
**producer**, for example a recorder). It covers one request, its reply and
what to do with each outcome. The exact rules are in the
[producer contract](api/PRODUCER-MANIFEST-CONTRACT.md); the
[OpenAPI candidate](api/openapi.candidate.json) lists every code per status.

Status: describes the current `main` implementation (increment 166). It is
user documentation, not release qualification; all eight release gates remain
open.

## What the mover does

1. You write a recording's files into a folder under the mover's configured
   source root.
2. You send one request listing those files.
3. The mover takes the files into its own custody. It moves each one out of
   your folder into a private area on the same filesystem.
4. When it holds **every** listed file, it replies **202**. Then the original
   names are free: you may reuse or remove them.
5. Delivery to the destination happens later, on its own. A 202 says nothing
   about delivery; operators watch that on the dashboard.

## Before you start

The server administrator gives you:
- the URL, for example `https://mover.example.internal:8443/api/v2/jobs`;
- a client certificate and key approved for your **generator ID**, and the
  server's trust root;
- the source root your folders must be under.

Setup and certificate details: [server setup](NATIVE-HTTPS-SETUP.md) and
[HTTPS clients](NATIVE-HTTPS-CLIENTS.md).

## 1. Build the request

```json
{
  "generator_id": "recorder",
  "recording_id": "6f1c2c1e-9d2b-4e8a-a7f1-2b5d3c4e5f60",
  "source_directory": "/srv/recordings/current",
  "files": ["audio.wav", "video/cam-1.mkv"],
  "expected_sizes_bytes": {"audio.wav": "1048576", "video/cam-1.mkv": "73400320"}
}
```

| Field | Rule |
|---|---|
| `generator_id` | Your configured generator; must match your certificate. |
| `recording_id` | A new UUID for each recording (`8-4-4-4-12` hex). It identifies the recording **forever**: never reuse it for different contents. |
| `source_directory` | Absolute path of the folder holding the files, inside the source root. |
| `files` | 1–256 relative paths inside that folder; subfolders allowed. No `..`, no leading or trailing `/`, no backslash or control characters. Names `.file-mover`, `.control`, `.staging` and `COMMITTED.json` are reserved at any depth. No path may be a folder of another listed path. |
| `expected_sizes_bytes` | Optional. If present, every listed file, sizes as decimal **strings**. Required when the server has `check_expected_sizes` on. |

No other fields are accepted. The body is at most 64 KiB.

The request is **immutable**. Keep the original body and resend it for every
retry of that recording. The mover compares meaning, not bytes: the same
`generator_id`, `source_directory`, size map (present or absent, same values)
and the same **set** of files. File order, JSON whitespace, key order and UUID
letter case may differ. Any other change is `recording_id_conflict`.

## 2. Send it

`POST` it as `Content-Type: application/json` over HTTPS with your client
certificate. The tested `curl` command is in
[HTTPS clients](NATIVE-HTTPS-CLIENTS.md#submit-with-curl). An optional
`Idempotency-Key` header must equal the `recording_id`.

Write every file **completely** and close it before sending. Files present
when the request arrives are claimed **immediately**, as they are; the mover
does not wait for them to stop changing. Only a file that arrives later (after
`source_file_missing`) is claimed once it has stayed unchanged for the
server's settle time. Even then, a writer that pauses longer than that can be
claimed mid-write.

Expected sizes help only when the server has `check_expected_sizes` on. It is
**off by default**, and then supplied sizes are kept with the request but not
compared. Supplying sizes alone does not protect against incomplete files.

## 3. Read the reply

**202, success:**
```json
{"job_id":"42","recording_id":"6f1c2c1e-9d2b-4e8a-a7f1-2b5d3c4e5f60","accepted":true,"source_paths_released":true}
```
Check that `recording_id` is your UUID (compare as a UUID; the reply is
lowercase). Then the source names are released.

**Any other reply:**
```json
{"recording_id":"6f1c…","error":"source_file_missing","retryable":true,"retry_after_seconds":null,"source_paths_released":false}
```
- `source_paths_released` is always `false`: keep your files where they are.
  An error never undoes an earlier 202.
- `retryable` decides whether you retry automatically (see the table).
- `recording_id` is `null` when the request was too malformed to read it.

A reply with no JSON, a timeout, a dropped connection or a TLS failure tells
you **nothing** about whether the mover took the files. Retry the same
request.

## 4. Retry timing

For a retryable outcome, wait:
1. `retry_after_seconds` from the JSON, if it is a number. Today only
   `429 rate_limited` sets it, to 1;
2. otherwise a valid `Retry-After` header;
3. otherwise 5, 10, 20, then 30 seconds, staying at 30.

Always resend the **same** request (same UUID, same body). If `retryable` is
`false`, stop automatic retries, whatever the headers say. Raise an alert and
leave the files in place.

## 5. Decision table

**Done:**

| Status | Code | Meaning | Do |
|---|---|---|---|
| 202 | — | The mover holds every file. | Done; reuse the names if you want. While the job is still tracked, a repeat of the same request also gets 202 with the same `job_id`. |

**Retry the same request** (`retryable: true`):

| Status | Code | Meaning | Do |
|---|---|---|---|
| 409 | `source_file_missing` | A listed file is not there yet. The job is recorded and waits for it during the server's missing-file window (`missing_file_retry_window_seconds`, default 300 s). | Write the missing file. The mover claims it on its own once it is stable, so a resend is not required. A resend is harmless and returns 202 once all files are in custody. After the window it becomes `recording_blocked`. |
| 503 | `handoff_pending` | A claim is in progress or its outcome is not yet known. | Retry. |
| 503 | `service_busy` | The mover is briefly full. | Retry. |
| 503 | `service_stopping` | The service is shutting down. | Retry; it continues after restart. |
| 503 | `storage_unavailable` | The mover's state store is temporarily unavailable. | Retry; alert if it persists. |
| 503 | `source_space_low`, `source_space_unavailable` | The source filesystem is too full, or its free space could not be checked. New recordings are held back. | Retry; tell the operator if it persists. |
| 503 | `retention_capacity` | The mover's retained-data limit is reached. | Retry; the operator may need to free retained data. |
| 429 | `rate_limited` | Too many connections at once. | Wait 1 second and retry. |
| 408 | `request_timeout` | The request arrived too slowly. | Retry. |
| — | no JSON, timeout, connection or TLS error | Outcome unknown. | Retry the same request. Persistent TLS failures are a setup problem; see [HTTPS clients](NATIVE-HTTPS-CLIENTS.md). |

**Stop: the request is wrong** (`retryable: false`; fix the producer):

| Status | Code | Meaning |
|---|---|---|
| 400 | `invalid_json` | Not valid JSON: bad UTF-8, a BOM, duplicate keys and the like. |
| 400 | `invalid_submission` | A missing, extra or wrongly typed field; a bad UUID or source path; an empty or over-long file list; a bad size map. Also: the server checks sizes and the request has no size map. |
| 400 | `invalid_file_paths` | A file path breaks the rules above, is duplicated, or is a folder of another path. |
| 400 | `idempotency_key_conflict` | The `Idempotency-Key` header is not this request's UUID. |
| 400 | `invalid_http`, `unsupported_headers`, `incomplete_request`, `unexpected_body` | Malformed HTTP, including more than 64 headers. |
| 413 | `request_too_large` | The body is over 64 KiB. |
| 431 | `request_headers_too_large` | The request line and headers are over 8 KiB. |
| 415 | `unsupported_media_type` | Not `application/json`. |
| 404, 405 | `not_found`, `method_not_allowed` | Wrong path or method; only `POST /api/v2/jobs`. |

**Stop: not allowed** (`retryable: false`; fix the configuration with the
administrator):

| Status | Code | Meaning |
|---|---|---|
| 403 | `unknown_generator` | `generator_id` is not the configured generator. |
| 403 | `caller_not_authorized` | Your certificate is not approved for this generator. |
| 403 | `source_outside_scope` | `source_directory` is outside the source root. |
| 403 | `producer_route_forbidden` | This connection may not submit. |

**Stop: needs the operator** (`retryable: false`; files stay where they are):

| Status | Code | Meaning | Do |
|---|---|---|---|
| 409 | `recording_blocked` | The job needs review: a file did not arrive in time, or custody could not be proven safe. | Alert the operator. After they reset the missing-file deadline (`reset-missing`), resend the same request. |
| 409 | `recording_cancelled` | An operator cancelled this recording before handoff. | Do not resend; files the mover already took stay in its custody. Ask the operator. |
| 409 | `recording_id_conflict` | This UUID was already used with different contents (generator, folder, file list or size map). | Do not change the request. If you changed it by mistake, send the original. A genuinely new recording needs a new UUID. |
| 409 | `source_size_mismatch` | Size checking is on and a file's size differs from `expected_sizes_bytes`. | Alert the operator; check the writer and the sizes you sent. |
| 409 | `source_reserved` | Another unfinished recording already holds one of these source paths. | Alert the operator; do not reuse paths before their 202. |
| 500 | `internal_error` | Unexpected failure. | Alert; keep the files and the request. |

## Rules of thumb

- One recording, one UUID, one immutable request. Never reuse a UUID, even
  much later: that is your rule, not a promise of the mover. After an
  operator clears a job's history, the mover forgets its UUID. A resend is
  then treated as **new** work and could claim new files you have since put
  at the same paths.
- Only a valid 202 for your UUID releases the source names. Never assume
  success from silence, an error or a reply for another UUID.
- After a 202, you never need to send that request again. While the job is
  still tracked, doing so is harmless and returns the same 202. After history
  clear it is not (see above), so stop resending once you have a valid 202.
- Never start a second mover, delete its private folders or edit its state to
  get past an error. Ask the operator.

## Related

- Operators: [status and recovery guide](RUST-OPERATOR-GUIDE.md), including
  "Missing files: automatic retries" and "Reset a reviewed missing-file
  deadline".
- Consumers of delivered recordings: DOC-02 (not yet written).
