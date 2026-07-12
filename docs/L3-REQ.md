# L3 — Implementation Obligations

Level 3 requirements state component-level implementation behavior. Each L3 declares a
single L2 **Parent** and its verification method(s) on one compact line, followed by the
obligation text. Cross-cutting component obligations use category codes `INT`, `EVT`,
and `CLI`; per-implementation Python technology constraints use `PY`. Live status is
tracked in `docs/TRACE-MATRIX.md`.

Verification method codes: **T** = Test, **I** = Inspection, **A** = Analysis,
**D** = Demonstration.

---

## INT — Integrity verifier and manifest

**L3-INT-001** · Parent: L2-DPR-004 · Verification: T

The `IntegrityVerifier` shall support SHA-256, SHA-512, and BLAKE2b using `hashlib`.

**L3-INT-002** · Parent: L2-DPR-004 · Verification: T

The `IntegrityVerifier` shall read files using a configurable bounded buffer.

**L3-INT-003** · Parent: L2-DPR-004 · Verification: T

The `ManifestWriter` shall persist the completed source hash before the coordinator
begins copying that file when pre-copy hashing is configured.

**L3-INT-004** · Parent: L2-DST-005 · Verification: T

The `ManifestWriter` shall write manifests through a temporary file and atomically
replace the prior manifest.

**L3-INT-005** · Parent: L2-DPR-002 · Verification: T

The transfer worker shall calculate the destination hash only after all destination
bytes have been flushed.

**L3-INT-006** · Parent: L2-DPR-004 · Verification: T

The `IntegrityVerifier` shall compare hash values using `hmac.compare_digest`.

**L3-INT-007** · Parent: L2-DPR-007 · Verification: T

A hash mismatch shall transition the file to an integrity-failed state, retain both the
source and temporary destination, and prevent publication.

## EVT — Event publisher

**L3-EVT-001** · Parent: L2-EVT-004 · Verification: T

The event publisher shall take a snapshot of registered subscribers before invoking
callbacks.

**L3-EVT-002** · Parent: L2-EVT-004 · Verification: T

The event publisher shall not hold its subscriber lock while invoking callbacks.

**L3-EVT-003** · Parent: L2-EVT-002 · Verification: T

The event publisher shall catch and log subscriber exceptions without propagating them
into the coordinator.

**L3-EVT-004** · Parent: L2-EVT-001 · Verification: T

The event publisher shall reject duplicate subscriber registrations.

**L3-EVT-005** · Parent: L2-EVT-001 · Verification: T

The `unsubscribe` operation shall indicate whether a subscriber was removed.

## CLI — Command-line structure

**L3-CLI-001** · Parent: L2-CLI-011 · Verification: T

The `create_parser` function shall perform no I/O, database access, or thread creation.

**L3-CLI-002** · Parent: L2-CLI-002 · Verification: T

Each subcommand shall delegate to a dedicated handler function.

**L3-CLI-003** · Parent: L2-CLI-002 · Verification: T

Handlers shall convert the parsed argument namespace into typed request objects.

**L3-CLI-004** · Parent: L2-CLI-004 · Verification: T

Result rendering shall be separate from command execution.

**L3-CLI-005** · Parent: L2-CLI-001 · Verification: T

The parser shall reject invalid arguments and choices before any service is invoked.

## PY — Python implementation details

**L3-PY-001** · Parent: L2-CFG-001 · Verification: T, I

The runtime package shall import only Python 3.10 standard-library modules.

**L3-PY-002** · Parent: L2-DPR-004 · Verification: T

Hashing shall be implemented with `hashlib`.

**L3-PY-003** · Parent: L2-DPR-005 · Verification: T

Atomic destination publication shall use `os.replace`.

**L3-PY-004** · Parent: L2-POSIX-009 · Verification: T

Durability shall use `os.fsync` on both the file and its containing directory.

**L3-PY-005** · Parent: L2-POSIX-008 · Verification: T

Exclusive temporary-file creation shall use `os.open` with `O_CREAT | O_EXCL |
O_NOFOLLOW`.

**L3-PY-006** · Parent: L2-CTL-002 · Verification: T

The control protocol shall frame each message with a 4-byte big-endian length prefix.

**L3-PY-007** · Parent: L2-JOB-002 · Verification: T

Durable state shall use `sqlite3` with `journal_mode=WAL` and `synchronous=FULL`.

**L3-PY-008** · Parent: L2-CLI-001 · Verification: T, I

The command-line interface shall be implemented with `argparse`.

**L3-PY-009** · Parent: L2-COPY-011 · Verification: T

Kernel-assisted copy shall use `os.copy_file_range` and fall back to the buffered loop on
an unsupported errno (e.g. `ENOSYS`, `EOPNOTSUPP`, `EXDEV`) or when the syscall is
unavailable, while propagating genuine I/O errors.

**L3-PY-010** · Parent: L2-CTL-011 · Verification: T

Service-manager notification shall use a standard-library `AF_UNIX` datagram sent to
`$NOTIFY_SOCKET` (handling the abstract-namespace `@` prefix) and shall be a no-op when
the variable is unset or the send fails.

## CTL — Control-plane components

**L3-CTL-001** · Parent: L2-CTL-002 · Verification: T

`receive_exactly` shall loop on `recv` until the full frame arrives or the peer closes
the connection.

**L3-CTL-002** · Parent: L2-CTL-005 · Verification: T

The `CommandDispatcher` shall route via an explicit command-to-handler map and shall not
dispatch dynamically on a user-supplied name.

**L3-CTL-003** · Parent: L2-CTL-001 · Verification: T

Every control response shall echo the request's `request_id`.

**L3-CTL-004** · Parent: L2-CTL-008 · Verification: T

The `ProcessLock` shall use `fcntl.flock` for the singleton lock.

## JOB — Durable-state components

**L3-JOB-001** · Parent: L2-JOB-002 · Verification: T

Each database connection shall set a `busy_timeout`.

**L3-JOB-002** · Parent: L2-JOB-001 · Verification: T

The repository shall translate SQLite errors and corrupt stored values into a typed
`RepositoryError`.

## SUB — Submission and claiming components

**L3-SUB-001** · Parent: L2-SUB-002 · Verification: T

The `FileClaimManager` shall claim each file with an atomic same-filesystem
`Path.replace` (os.replace) into the per-job staging directory.

**L3-SUB-002** · Parent: L2-SUB-004 · Verification: T

The `ManifestWriter` shall write manifests through a flushed, fsynced temporary file
that is atomically renamed over the final name.
