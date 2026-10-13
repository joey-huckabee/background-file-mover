# Rust local submission endpoint increment

`file-mover` is now an executable local handoff service. It implements
`POST /api/v2/jobs` and `GET /healthz` on a configured loopback listener. This is
the minimal generator form, with one configured generator and source root.
Registration, tokens, remote access, advanced request forms, status/control
routes, destination copying and source cleanup remain future work.

## Test contract

Start the qualified Linux binary with one JSON configuration path:

```sh
file-mover /path/to/local.json
```

Use [the example configuration](../rust/config/local.example.json). Provision
the source root and its `.file-mover` directory as described in
[increment 03](RUST-INCREMENT-03.md), and a protected existing local state parent.
The source must be service-owned; claim storage is private 0700. State must be
outside source and destination roots, which must not overlap. Paths must be
canonical absolute paths without symlinks under the qualified local custody
contract. The destination is pinned metadata only: it need not be online, and
no transfer starts yet. Use disposable local recording fixtures for this slice.

Send the following request, substituting the mover-visible source directory:

```http
POST /api/v2/jobs HTTP/1.1
Host: localhost
Content-Type: application/json

{
  "generator_id": "recorder-host-a",
  "submission_id": "recording-0042",
  "source_path": "/srv/file-mover/source/current",
  "files": [{"name": "video/camera.bin"}, {"name": "events", "size_bytes": 0}]
}
```

HTTP framing requires the correct Content-Length and CRLF line endings; a client
such as curl supplies these. Content-Type must be `application/json`.
Generator identity must match startup configuration. Source directory containment
uses path components, then the qualified descriptor traversal validates filesystem
effects. Optional `size_bytes` must be an unsigned JSON integer, including zero;
null, fractions and negative values are rejected. Unknown/duplicate fields,
unsafe paths, mixed request forms and extra metadata not implemented here are
rejected. File-list order remains part of exact replay identity.

After every claim receipt commits, the response is:

```json
{"job_id":"1","state":"Claimed","source_paths_released":true,"retryable":false}
```

Its HTTP status is **202**. Until 202, leave submitted files, writers and parents
untouched. After 202, producer paths can be reused. Retry a lost response using
the same generator/submission IDs and identical body; completed replay returns
the original job without inspecting a reused source entry. The optional
Idempotency-Key header must agree with the body submission ID. No authentication
header is supported in this explicitly trusted local profile.

Errors contain `error`, `retryable`, `source_paths_released:false`, and `job_id`
when known. Malformed requests return 400, unknown generator/out-of-scope source
403, unsupported media 415, and source/key conflicts or review-required claims
409. Size assertion failure reports `source_size_mismatch`. Queue/storage/handoff
wait failures return transient 503. Only 202 releases paths; retryable errors
use the same ID/body with backoff. A nonretryable error requires correction or
operator review, without forgetting any already accepted/claimed job.

## Persistence, bounds and shutdown

Schema 3 adds per-file missing deadlines and a persistent review-blocked flag.
Explicit migrations from versions 1 and 2 preserve acceptance and claim receipts.
Confirmed local absence starts the job's pinned retry duration (default 300s).
Replays/restarts/configuration changes do not extend the deadline. Expiry observed
on submission/retry persists a blocked condition, even if the clock subsequently
rolls backward or the file appears. Existing partial claims/reservations remain.
Missing requests return 503 `handoff_pending` during the window, then 409
`recording_blocked`. Only a confirmed source leaf/parent absence qualifies;
lost root/namespace custody is blocked rather than fabricated as missing.

There is no timer-driven retry scheduler or operator unblock endpoint yet; a
generator's retries drive reconciliation and deadline checks. Operator-review
tooling is required before deployment. Deadline calculation uses Unix wall time;
system clock correctness remains an operational prerequisite.

Tokio owns network I/O, timeouts and signals. A serialized local claim thread
executes SQLite calls/filesystem effects off the executor, through a one-slot
queue and oneshot results. SQLite retains its separate owner thread. One active
and one queued handoff are admitted; excess requests receive service_busy 503.
Source namespace flock excludes another local service owner; the held directory
identity is revalidated before accepting work. It is not an NFS worker fence.

At most eight connections are active. Headers are limited to 8 KiB/64 entries,
body to 64 KiB, files to 256 and generator/submission IDs to 128 bytes. Request
read deadline is 5s, handoff wait 10s and response write 2s. Duplicate headers,
Transfer-Encoding, Expect, bare-LF HTTP and unsupported framing are rejected;
one request per connection uses Connection: close. Connection saturation closes
excess sockets rather than allocating more tasks. Health remains independent of
claim-worker progress; it is liveness, not storage/transfer readiness.

SIGINT/SIGTERM stop admission and abort network handlers. Already authorized
local effects finish and retain durable receipts before the worker joins. A
lost/aborted response does not undo acceptance/claiming. Local syscall shutdown
is not guaranteed bounded: supervised processes, blocked-worker bounds and NFS
fencing remain production work. Deletion stays disabled and no bytes are copied.

## Evidence and next slice

The platform gate now audits/smokes the real service binary before exposing it
to test subprocesses. HTTP tests launch that exact relocated executable inside
pinned SLES/glibc 2.22 userspace in both profiles. Tests cover source release,
restart/reuse, conflicting bodies, lost responses, JSON/header/framing rejection,
scope boundaries, partial missing claims, expiry/restart blocking, concurrent
bounded replay, health during a slow connection and both shutdown signals.
Storage tests independently prove migration, pinned deadlines and persistent
expiry; filesystem tests prove singleton exclusion and changed namespace detection.
See [current platform evidence](RUST-SLES-EVIDENCE.json) for actual counts/imports.
The passing run has 47 tests per profile: 10 core, 21 store, 10 filesystem and
6 executable HTTP tests. All eighteen emitted executables import at most
GLIBC_2.18 and use the expected GNU loader; six negative audit controls pass.

Dependencies reuse the E5 cumulative graph/configurations: Tokio 1.53.2,
httparse 1.10.1, Serde 1.0.229, serde_json 1.0.154, plus prior SQLite/rustix.
No package experiment resumes. No Axum, musl, new loader or new target dependency
version is introduced. Containers share the runner kernel; local process tests
do not qualify NFS, server/storage power loss or a historical SLES kernel.

Rust evidence supports the handoff intent of L1-API-007/008/009 and actual-size/
explicit-path requirements L1-SYS-028/029. L1-SYS-033 missing retry behavior gains
deadline persistence and review blocking; operator resume remains unfinished.
Historical C++ trace statuses/matrix are not promoted by these Rust tests.
Next is one copied-file transfer with streamed source hash, destination reread,
no-clobber publication and recovery, keeping deletion disabled.
