# L3 — Implementation Obligations

Level 3 requirements state component-level implementation behavior. Each L3 declares a
single L2 **Parent** and its verification method(s) on one compact line, followed by the
obligation text. Cross-cutting component obligations use category codes `INT`, `EVT`,
and `CLI`; C++ technology constraints use `CPP`. Live status is tracked in
`docs/TRACE-MATRIX.md`.

> **The `L3-PY-*` category was deleted on 2026-08-06.** Fourteen requirements
> specified Python mechanisms — `hashlib`, `argparse`, `os.replace`, `python -O` — for
> an implementation that no longer exists on this branch. They counted against the
> v1.0.0 denominator and could never be verified by C++ code.
>
> Each was inspected before deletion to be certain no *feature* left with the
> mechanism. Twelve carried nothing their L2 parent did not already require. Five
> carried a substantive constraint that the parent did **not** imply, and those were
> preserved rather than dropped:
>
> | Retired | Constraint that survived | Now lives in |
> |---|---|---|
> | `L3-PY-004` | fsync the containing **directory**, not only the file | `L3-CPP-053` |
> | `L3-PY-010` | readiness notification is a no-op when unrequested | `L3-CPP-054` |
> | `L3-PY-011` | a throughput limit forces the buffered copy strategy | `L2-BWL-001` |
> | `L3-PY-012` | resume truncates to the offset, never to zero | `L2-RSM-001` |
> | `L3-PY-006` | control-plane framing | superseded by `L2-CTL-002` (ADR-0012) |
>
> The directory-fsync case is the one that justifies the whole exercise. The code in
> `cpp/src/fsops.cpp` already does it, but `L2-POSIX-009` asks only for the *file* to be
> synced — so `L3-PY-004` was the only written requirement demanding the directory sync,
> and deleting it unexamined would have left that call with nothing to protect it. A
> rename is atomic, but atomicity is not durability.
>
> Identifiers are retired and shall not be reused. Do not add new `L3-PY-*`
> requirements.

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

**L3-CPP-013** · Parent: L2-ARC-007 · Verification: D, I

All core code shall compile warning-free under `-std=c++11 -Wall -Wextra -Werror` on
GCC 4.8.5.

Verification is by Demonstration, not Test. There is no runtime behavior here to
assert, so no test case can exist and the matrix would report a permanent hole
against a requirement that is in fact gated on every commit. The demonstration is
the `build & test (gcc 4.8.5)` job in `.github/workflows/cpp-ci.yml` and the
fidelity tier of `make check-ci`, both of which run the compiler with these exact
flags and fail the build on any diagnostic. This was previously marked `T`, which
was a modeling error rather than a missing test.

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

### REST API codec

Verified by `cpp/tests/test_api_codec.cpp`.

**L3-CPP-025** · Parent: L2-CTL-013 · Verification: T

`decode_submit_request` shall accept only a JSON object whose members are
exactly `source` and `dest`, both non-empty strings.

**L3-CPP-026** · Parent: L2-CTL-005 · Verification: T

`decode_submit_request` shall reject unknown members, missing members, wrong
member types, non-object top-level values, duplicate member names, trailing
content after the JSON value, and strings containing an embedded NUL.

**L3-CPP-027** · Parent: L2-JSON-002 · Verification: T

On rejection `decode_submit_request` shall return false, populate a non-empty
human-readable error, and leave the output parameter unmodified.

**L3-CPP-028** · Parent: L2-JSON-002 · Verification: T

The codec shall never terminate the process on malformed input, regardless of
input size, nesting depth, or byte content. Every prefix of a valid body shall
be rejected without crashing.

**L3-CPP-029** · Parent: L2-CTL-013 · Verification: T

`encode_job` shall emit members `id`, `source`, `dest`, `state`,
`created_at_ms`, `updated_at_ms`, `finished_at_ms`, `bytes_total`,
`bytes_moved`, and `error`, with the state rendered via `to_string`. Byte
counters exceeding the int64 range shall be clamped rather than wrapped.

**L3-CPP-030** · Parent: L2-JSON-003 · Verification: T

All emitted strings shall be JSON-escaped such that parsing the output
reproduces the original values exactly, including quotes, backslashes,
control characters, and multi-byte UTF-8.

**L3-CPP-031** · Parent: L2-JSON-004 · Verification: T

`decode_submit_request` shall reject a path member longer than PATH_MAX
(4096 bytes). A longer path cannot be opened, so accepting it only defers the
failure to a point with less context to report it.

**L3-CPP-032** · Parent: L2-JSON-001 · Verification: I

`filemover/json.hpp` shall be included only by `src/json.cpp`,
`src/api_codec.cpp`, the parser and codec test files, and the fuzz harness.
Every other translation unit shall reach JSON exclusively through the codec
interface, so the parser can be replaced without touching a caller.

### Configuration loader

Verified by `cpp/tests/test_config.cpp`.

Note on numbering: the inherited drop assigned these obligations
`L3-CPP-026..033`, colliding with the codec range already in use here. They
are renumbered; the content is otherwise preserved except where noted.

**L3-CPP-033** · Parent: L2-CFG-001 · Verification: T

The loader shall accept `[section]` headers, `key = value` entries with
whitespace trimmed from both sides (values may contain spaces and `=`),
full-line comments starting with `;` or `#`, and blank lines. Inline comments
shall not be supported: a `;` after a value is part of the value.

**L3-CPP-034** · Parent: L2-CFG-009 · Verification: T

Every rejection tied to a line shall be reported as
`<origin>:<line>: <message>`.

**L3-CPP-035** · Parent: L2-CFG-008 · Verification: T

The loader shall report all issues together rather than stopping at the first,
and shall leave the output `Config` unmodified when any issue is found.

**L3-CPP-036** · Parent: L2-CFG-002 · Verification: T

Unknown sections and unknown keys shall be rejected, as shall an empty
`http.bind`, a `bind` value containing whitespace, and a
`storage.database_path` containing an embedded NUL.

**L3-CPP-037** · Parent: L2-CFG-002 · Verification: T

Duplicate keys within a section, and duplicate section headers, shall be
rejected.

**L3-CPP-038** · Parent: L2-CFG-004 · Verification: T

Integer parameters shall parse strictly — base 10, entire token consumed, no
sign characters — with ranges enforced: `http.port` 1..65535,
`http.max_body_bytes` 1..16777216, `jobs.workers` 1..64.

**L3-CPP-039** · Parent: L2-CFG-003 · Verification: T

Every optional parameter shall take its documented default when absent
(`http.bind` = `127.0.0.1`, `http.port` = 8080, `http.max_body_bytes` = 65536,
`jobs.workers` = 4), and every missing required parameter shall be reported by
qualified name. The loopback default for `http.bind` is load-bearing: v1.0.0
ships no authentication, so the bind address is the only access control.

**L3-CPP-040** · Parent: L2-CFG-001 · Verification: T, I

`load_config_from_string` shall perform no I/O, so the whole validation matrix
is testable without a disk. The `L2-JOB-008` check that the state database is
not on a network filesystem therefore lives outside it, in
`storage_path_is_local`, called at service startup.

### Core extension consumed by persistence

**L3-CPP-041** · Parent: L2-CORE-001 · Verification: T

`from_string(token, state)` shall accept exactly the tokens produced by
`to_string`, writing the state and returning true; any other input shall
return false and leave the output unmodified.

Adopted from the inherited M4 journal work, which needed it to reconstruct
state during replay. It is kept because the need is not specific to that
mechanism — any durable store must turn a persisted token back into a state
on recovery — and it is placed in the core rather than in whichever storage
layer happened to want it first.

### Rename template expansion

Verified by `cpp/tests/test_rename_template.cpp`.

The template engine only. The filesystem operation that consumes it belongs to
the fd-relative layer specified in `docs/CYBERSECURITY.md`; section 10 of that
document records why the inherited path-based rename operation was not adopted
alongside this.

**L3-CPP-042** · Parent: L2-REN-001 · Verification: T

Template expansion shall support exactly the fields `{name}` (source
basename), `{stem}` (basename up to the last `.`, where a leading dot is not
an extension separator), `{ext}` (after the last `.`, empty if none), `{ts}`
(the caller-supplied millisecond timestamp rendered as UTC
`YYYYMMDD"T"HHMMSS"."mmm`), and `{seq}` (the caller-supplied sequence,
zero-padded to six digits and widening rather than truncating beyond that).

**L3-CPP-043** · Parent: L2-REN-001 · Verification: T

An unknown field, an unclosed `{`, or a stray `}` shall be an expansion error
naming the offending construct.

**L3-CPP-044** · Parent: L2-SEC-006 · Verification: T

An expansion **result** that is empty, `.`, `..`, or contains `/` or NUL shall
be rejected.

Validating the result rather than only the template is what makes directory
escape impossible: every field can be legal while the source filename flowing
through them produces `..` or a path separator.

**L3-CPP-045** · Parent: L2-CORE-004 · Verification: T, I

`expand_rename_template` shall perform no I/O and shall read no clock; the
timestamp is supplied by the caller, keeping the function deterministic and
testable without a fixture.

### HTTP/1.1 request parser (ADR-0012)

Verified by `cpp/tests/test_http_parser.cpp` and fuzzed by
`cpp/fuzz/fuzz_http.cpp`.

The parser only. Route handling and the socket server arrive with the job
manager; a parser that forces its consumers to include the configuration and
the job manager is doing more than one job
(`docs/HAND-ROLLED-COMPONENTS.md` §1.2).

Renumbered from the inherited `L3-CPP-079..092`, which collided with this
repository's sequence.

**L3-CPP-046** · Parent: L2-CTL-002 · Verification: T

The request line shall be METHOD SP target SP version CRLF, with METHOD 1..16
characters of `[A-Z]`, target beginning `/` and free of whitespace and control
characters, and version exactly `HTTP/1.0` or `HTTP/1.1`.

**L3-CPP-047** · Parent: L2-CTL-015 · Verification: T

Headers shall be `name: value` with token names lowercased on output and
values OWS-trimmed and free of control characters. obs-fold continuation lines
shall be rejected, more than 64 headers shall be rejected, and a duplicate
header name shall be rejected.

Duplicates are refused rather than resolved. A map assignment silently takes
the last value, and two parties disagreeing about which duplicate wins is the
mechanism behind request smuggling — the same reasoning that made duplicate
JSON member names an error in ADR-0009.

**L3-CPP-048** · Parent: L2-CTL-003 · Verification: T

Absence of CRLFCRLF within the configured head cap shall yield `TooLarge`, so
a client dribbling bytes without ever completing a head is bounded.

**L3-CPP-049** · Parent: L2-CTL-015 · Verification: T

Any proper prefix of a valid head shall yield `NeedMore`, and the output
request shall be left unmodified except on `Ok`.

Bare-LF framing is `NeedMore` rather than `Bad`: the head is incomplete, not
malformed, and the cap of `L3-CPP-048` or the socket timeout ends it. Treating
an unterminated prefix as permanently invalid is a judgment a streaming parser
is not entitled to make.

**L3-CPP-050** · Parent: L2-CTL-003 · Verification: T

An absent `Content-Length` shall mean zero. A present value shall be strict
base-10 digits consuming the whole token, accumulated with an explicit
overflow guard. Any `Transfer-Encoding` shall be rejected with 400, and a
value above the configured body cap with 413.

Any `Transfer-Encoding` is refused rather than ignored: no chunked decoder
exists to desync, but ignoring the header is what lets a TE/CL disagreement
smuggle a request past an intermediary.

**L3-CPP-051** · Parent: L2-CTL-013 · Verification: T

A serialized response shall carry the status line, `Content-Type`,
`Content-Length`, `Connection: close`, an `Allow` header when the response
supplies one, CRLF framing throughout, and then the body.

**L3-CPP-052** · Parent: L2-CTL-015 · Verification: T, I

Character classification in the parser shall use explicit ranges and shall not
use `<cctype>`.

`std::isalnum` and `std::tolower` are locale-sensitive. A parser on untrusted
network input must not change what it accepts because something elsewhere in
the process called `setlocale`, and a test asserts identical behavior under
two locales.

**L3-CPP-053** · Parent: L2-POSIX-009 · Verification: T

Durability shall `fsync` **both** the destination file and the directory
containing it, before the file is given its final name.

The directory fsync is the half that is easy to omit and impossible to notice.
A `rename` is atomic, but atomicity is not durability: until the containing
directory's own metadata is synced, a crash can leave a correctly-written file
under no name at all. The parent requirement asks only for the file to be
synced, which a reasonable implementer satisfies while still losing data.

Carried forward from the retired `L3-PY-004`, which was the only written
requirement demanding it. `cpp/src/fsops.cpp` already does both; before this
requirement existed, deleting either call would have broken nothing that any
gate could see.

**L3-CPP-054** · Parent: L2-CTL-011 · Verification: T

Service-manager readiness notification shall be a no-op when the environment
does not request it — when `$NOTIFY_SOCKET` is unset — and a failure to send
shall not fail the service.

Without this the service starts under a service manager and refuses to start
anywhere else, including in tests and at an operator's shell. Carried forward
from the retired `L3-PY-010`, whose parent requires the notification to happen
but says nothing about what happens when there is nothing to notify.
