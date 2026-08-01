# L3 — Implementation Obligations

Level 3 requirements state component-level implementation behavior. Each L3 declares a
single L2 **Parent** and its verification method(s) on one compact line, followed by the
obligation text. Cross-cutting component obligations use category codes `INT`, `EVT`,
and `CLI`; per-implementation technology constraints use `PY` for the Python
implementation and `CPP` for the C++ implementation. Live status is tracked in
`docs/TRACE-MATRIX.md`.

`PY` and `CPP` requirements describe two implementations of the same system and are not
expected to both be satisfied at once — see the v1.0.0 scope section of
`docs/L1-REQ.md`.

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

**L3-PY-011** · Parent: L2-BWL-001 · Verification: T

Copy-throughput limiting shall be implemented in userspace as a thread-safe token bucket
(no third-party or operating-system traffic-shaping dependency), paced in the buffered
copy loop; because kernel-assisted `copy_file_range` cannot be paced from userspace, a
non-zero limit shall force the buffered copy strategy.

**L3-PY-012** · Parent: L2-RSM-001 · Verification: T

Partial-file resume shall determine the resume offset from the fsynced partial's size
(`os.stat`/`os.fstat`), `os.lseek` both descriptors to it, and continue with either copy
strategy; the kernel-copy fallback shall truncate to the resume offset (never zero) so an
already-copied prefix is preserved.

**L3-PY-013** · Parent: L2-CLI-006 · Verification: T

The service shall configure logging from the `[logging] level` (an explicit CLI
`-v`/`--log-level` taking precedence) and write its event stream to the standard streams
without managing log files (twelve-factor): `INFO`/`DEBUG` to stdout and `WARNING` and above
to stderr, letting the environment route it. Valid-but-consequential option combinations
(a bandwidth limit with kernel copy; resume without full destination hashing) shall be
surfaced as advisories by `file-mover doctor` and logged once at service start, never
raised as errors.

**L3-PY-014** · Parent: L2-CLI-006 · Verification: T

Logging shall be gated and context-aware: job/file correlation shall be carried in
structured fields (`extra={"job_id", "file_id"}`) via stable `file_mover.<area>` loggers,
not logger names. A per-level gate (`LogGate`) computed once at configuration shall let a
call site skip a disabled level with a single boolean read — no `isEnabledFor`, argument
evaluation, formatting, or dispatch — and a level of `OFF` shall disable all logging. Hot
paths shall guard with `if __debug__ and GATE.debug:` so DEBUG is removed from the bytecode
under `python -O`; cold paths may call directly.

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

## CPP — C++ implementation details

Verified by `cpp/tests/`; requirement IDs appear in Catch2 tags and source comments.

**L3-CPP-001** · Parent: L2-CORE-001 · Verification: T

The job state enumeration shall contain exactly the states Queued, Renaming,
Transferring, Done, and Failed.

**L3-CPP-002** · Parent: L2-CORE-001 · Verification: T

`to_string(JobState)` shall return a stable, unique, uppercase token for each state.

**L3-CPP-003** · Parent: L2-CORE-001 · Verification: T

`is_legal_transition(from, to)` shall permit exactly Queued→Renaming,
Renaming→Transferring, Transferring→Done, Queued→Failed, Renaming→Failed, and
Transferring→Failed; all other pairs, including self-transitions, shall be rejected.

**L3-CPP-004** · Parent: L2-CORE-001 · Verification: T

`is_terminal(JobState)` shall return true for Done and Failed and false otherwise.

**L3-CPP-005** · Parent: L2-CORE-002 · Verification: T

A newly constructed `Job` shall be in Queued with `created_at_ms == updated_at_ms ==
now_ms`, `finished_at_ms == 0`, both byte counters zero, and an empty error string.

**L3-CPP-006** · Parent: L2-CORE-003 · Verification: T

`Job::transition` shall return false and leave the object unmodified when the requested
transition is illegal.

**L3-CPP-007** · Parent: L2-CORE-003 · Verification: T

`Job::transition` to Failed shall be rejected when the supplied error message is empty.

**L3-CPP-008** · Parent: L2-CORE-003 · Verification: T

`Job::transition` to any non-Failed state shall be rejected when a non-empty error
message is supplied.

**L3-CPP-009** · Parent: L2-CORE-002 · Verification: T

On success, `Job::transition` shall set the state to the requested value and
`updated_at_ms` to the supplied timestamp.

**L3-CPP-010** · Parent: L2-CORE-002 · Verification: T

On a successful transition into a terminal state, `Job::transition` shall set
`finished_at_ms` to the supplied timestamp.

**L3-CPP-011** · Parent: L2-CORE-002 · Verification: T

On a successful transition into Failed, `Job::transition` shall store the supplied error
message in the job's error field.

**L3-CPP-012** · Parent: L2-CORE-004 · Verification: I

Core headers shall include no I/O, threading, or clock headers; `<iostream>`,
`<fstream>`, `<thread>`, `<mutex>`, and `<chrono>` are prohibited in
`cpp/include/filemover/job.hpp`.

**L3-CPP-013** · Parent: L2-ARC-007 · Verification: T, I

All core code shall compile warning-free under `-std=c++11 -Wall -Wextra -Werror` on
GCC 4.8.5.

**L3-CPP-014** · Parent: L2-ARC-007 · Verification: I

Test assertions shall use natural order, `actual == expected`.

**L3-CPP-015** · Parent: L2-CORE-001 · Verification: T

The test suite shall exhaustively enumerate all 25 (from, to) state pairs against the
legal-transition table.

### JSON parser (ADR-0009)

Verified by `cpp/tests/test_json.cpp`.

**L3-CPP-016** · Parent: L2-JSON-003 · Verification: T

The parser shall accept exactly the subset defined in ADR-0009: a top-level
object whose member values are strings, int64 integers, booleans, or nested
objects and arrays within the configured depth limit.

**L3-CPP-017** · Parent: L2-JSON-003 · Verification: T

The parser shall reject non-object top-level values, duplicate member names,
trailing commas, comments, unquoted and single-quoted strings, a leading
byte-order mark, unterminated structures, empty input, and any literal other
than `true` or `false`.

**L3-CPP-018** · Parent: L2-JSON-003 · Verification: T

The parser shall reject strings containing an embedded NUL by either escape or
raw byte, unescaped control characters, lone or mispaired surrogates, malformed
escape sequences, and invalid, overlong, truncated, or surrogate-encoding UTF-8.

**L3-CPP-019** · Parent: L2-JSON-002 · Verification: T

On rejection the parser shall return false and populate a non-empty
human-readable error identifying the byte offset.

**L3-CPP-020** · Parent: L2-JSON-002 · Verification: T

The parser shall never terminate the process on malformed input, regardless of
input size, nesting depth, or byte content. Every prefix of a valid document
shall be rejected without crashing.

**L3-CPP-021** · Parent: L2-JSON-004 · Verification: T

The parser shall enforce configured bounds on nesting depth, total input size,
string length, object member count, and array element count. Depth shall be
checked before descending.

**L3-CPP-022** · Parent: L2-JSON-003 · Verification: T

The parser shall accept integers only, within the int64 range, rejecting
floating-point values, exponent notation, leading zeros, a leading `+`, bare
`.5` and `5.` forms, `NaN`, `Infinity`, hexadecimal, and out-of-range values.

**L3-CPP-023** · Parent: L2-JSON-003 · Verification: T

`escape` shall produce output that parses back to the original value exactly,
including quotes, backslashes, and control characters.

**L3-CPP-024** · Parent: L2-JSON-003 · Verification: T

The parser shall reject any input containing non-whitespace bytes after the
top-level value.
