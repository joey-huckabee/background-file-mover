# L3 - Implementation obligations

The functional obligations below remain specified. Their Rust derivation and
verification mapping are unfinished under P10/RC-23; no generated coverage total
is claimed. Implementation-specific mechanisms and their retired identifiers
are not reused for new obligations.

Verification methods: T = Test, I = Inspection, A = Analysis, D = Demonstration.

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

`SingletonLock` shall hold the singleton lock with `flock(2)` on a lock file beside the
state database, and shall not use `fcntl(F_SETLK)` record locks. Record locks are owned
by the `(process, file)` pair, so a second lock taken by the same process replaces the
first rather than being refused — the case the lock exists to catch, made invisible.
`flock` is owned by the open file description, so a second open in the same process is a
different owner and conflicts correctly.

The lock file shall not be unlinked on release: between another process's open and its
`flock` there is a window in which unlinking would delete the object that process is
about to lock, leaving two instances holding exclusive locks on two different inodes
with the same name.

## JOB — Durable-state components

**L3-JOB-001** · Parent: L2-JOB-002 · Verification: T

Each database connection shall set a `busy_timeout`.

**L3-JOB-002** · Parent: L2-JOB-001 · Verification: T

The repository shall translate SQLite errors and corrupt stored values into a typed
`RepositoryError`.

**L3-JOB-003** · Parent: L2-JOB-007 · Verification: T

The submission service shall stamp one creation timestamp and record the configured
integrity mode and hash algorithm on both the `JobRecord` and the manifest, and the
repository shall persist and restore them (`hash_algorithm`, `integrity_mode` columns).

## SUB — Submission and claiming components

**L3-SUB-001** · Parent: L2-SUB-002 · Verification: T

The `FileClaimManager` shall claim each file with an atomic same-filesystem
`Path.replace` (os.replace) into the per-job staging directory.

**L3-SUB-002** · Parent: L2-SUB-004 · Verification: T

The `ManifestWriter` shall write manifests through a flushed, fsynced temporary file
that is atomically renamed over the final name.


## Required durability and readiness constraints

Under L2-POSIX-009, durability shall fsync both the destination file and the
directory containing it before the file is given its final name. Atomic rename
alone is not a durability guarantee. Publication and subsequent namespace
changes must retain the stronger ordering in TRANSFER-PROTOCOL.md.

Under L2-CTL-011, service-manager readiness notification shall be a no-op when
NOTIFY_SOCKET is unset, and failure to send shall not fail the service. This is
a retained requirement, not a claim that readiness integration is qualified.

L3-CTL-004 continues to require lifetime lock ownership and forbid unlinking
lock files. Removing source/tools does not waive any filesystem safety duty.
