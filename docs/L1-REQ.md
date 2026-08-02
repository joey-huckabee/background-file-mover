# L1 — System Requirements

Level 1 requirements state *what* the Background File Mover system must accomplish.
Each is a single SHALL statement with a declared verification method. L1 requirements
decompose into L2 architectural derivations (`docs/L2-REQ.md`), which decompose into L3
implementation obligations (`docs/L3-REQ.md`). Live verification status is tracked in
the auto-generated `docs/TRACE-MATRIX.md`, not here.

Verification method codes: **T** = Test, **I** = Inspection, **A** = Analysis,
**D** = Demonstration.

## v1.0.0 scope

v1.0.0 is the C++11 / REST implementation. It is **deliberately narrower** than the
Python implementation shipped through v0.4.2: the claim-and-verify transfer semantics
are deferred to v1.1 so that the REST control plane, the transfer engine, and the
durability layer land first on a smaller, fully-tested surface.

Every requirement below carries a **v1.0.0 Status**:

| Status | Meaning |
|---|---|
| **Active** | In scope for v1.0.0 and verified by the trace matrix |
| **Deferred → v1.1** | Retained verbatim, **not** implemented in v1.0.0, **not** weakened |
| **Partial** | In scope, but a named clause is deferred |
| **Rewritten** | ID reused; text replaced for the C++ implementation |

> **Deferred requirements are not dropped.** `L1-SYS-002` through `L1-SYS-006` are the
> safety core of the Python implementation — claim, integrity verification, conservative
> deletion, and crash recovery. v1.0.0 does not provide them. This is recorded here
> rather than by deleting the requirements, so that the gap between what the system
> guarantees and what it once guaranteed stays visible in the trace matrix. Deployments
> that depend on those guarantees should remain on the Python implementation until v1.1.

---

## Platform & Runtime

### L1-SYS-009

The production application shall be implemented in C++11, shall compile with GCC 4.8.5
under `-Wall -Wextra -Werror` without warnings, and shall depend only on the C++11
standard library, POSIX interfaces, and vendored dependencies recorded in
`cpp/VENDORED.md`.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Rewritten — ID reused; supersedes the Python 3.10 stdlib-only
obligation. See ADR-0001, ADR-0004, ADR-0007.

### L1-SYS-011

The system shall deploy as a single executable, one configuration file, and one systemd
unit, with no interpreter or runtime package required on the target host.

**Verification Method**: Demonstration (D)
**v1.0.0 Status**: Active

### L1-SYS-012

The system shall run as an unprivileged user.

**Verification Method**: Demonstration (D)
**v1.0.0 Status**: Active

---

## Control Interface

### L1-API-001

The system shall accept transfer job submissions over an HTTP/1.1 REST interface.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — replaces the `AF_UNIX` control socket. See ADR-0002.

### L1-API-002

The system shall expose job status individually, as a collection, and as an aggregate
over the REST interface.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-API-003

The system shall serve all HTTP responses with `Connection: close` semantics.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-API-004

The system shall reject request bodies exceeding a configured maximum size with HTTP 413.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-API-005

The system shall not implement TLS in-process.

**Verification Method**: Inspection (I)
**v1.0.0 Status**: Active. See ADR-0003.

### L1-API-006

The system shall bind only to the interface and port specified in configuration, and
shall default to loopback when unspecified.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

> **Security note.** Replacing the `AF_UNIX` socket with a TCP listener removes the
> filesystem-permission authentication the Python implementation got for free. v1.0.0
> ships **no authentication and no authorization** — `L1-API-006` is the only access
> control. The loopback default is load-bearing, not cosmetic. Authentication is a
> roadmap item; until it lands, any deployment binding to a non-loopback address must
> place an authenticating reverse proxy in front.

---

## File Operations

### L1-SYS-001

The system shall transfer completed scenario recording files independently of the
simulation orchestration process.

**Verification Method**: Test (T), Demonstration (D)
**v1.0.0 Status**: Active

### L1-SYS-002

The system shall allow simulation preparation activities to resume after the recording
files have been claimed and the transfer job has been durably accepted.

**Verification Method**: Test (T), Demonstration (D)
**v1.0.0 Status**: Deferred → v1.1 (depends on claiming, `L1-SYS-004`)

### L1-SYS-003

The system shall prevent source recording data from being deleted until the
corresponding destination data has been successfully published and verified.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred → v1.1. v1.0.0 has no delete-source step at all, so no
source data is at risk; the requirement becomes substantive when deletion is introduced.

### L1-SYS-004

The system shall relocate submitted source files within the source filesystem to
prevent subsequent simulation runs from overwriting the submitted paths.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred → v1.1

### L1-SYS-006

The system shall provide configurable integrity verification for transferred files.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred → v1.1

### L1-SYS-013

The system shall rename each file according to a configured template before transfer,
applying a configured collision policy when the target name already exists.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — new capability, no Python-implementation equivalent.

### L1-SYS-014

The system shall guarantee that a destination file never becomes visible under its
final name in a partially written state.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-SYS-015

The system shall move files by same-filesystem atomic rename.

**Verification Method**: Test (T)
**v1.0.0 Status**: **Rewritten.** This originally required three strategies —
same-filesystem move, cross-filesystem copy, and an external command — carried
over from the inherited design's `L1-023`. Two of the three are gone:

- The **cross-filesystem copy** clause contradicted `L1-SEC-007`, which
  restricts v1.0.0 to a single filesystem. Both were Active simultaneously —
  an error introduced when the security invariants were added without
  reconciling them against this requirement. Deferred → v1.1.
- The **external-command** clause is removed outright. See ADR-0011: it would
  make the configuration file executable, and it voids the commit-point
  guarantees that justify the daemon existing. It was required here only
  because the inherited design required it, which is not a reason.

### L1-SYS-010

The system shall retain source data and provide actionable error information when a
transfer cannot be safely completed.

**Verification Method**: Test (T)
**v1.0.0 Status**: Partial — the actionable-error clause is Active. The retention clause
is trivially satisfied at v1.0.0 (nothing deletes source) and becomes substantive with
`L1-SYS-003` at v1.1.

---

## Job Management

### L1-SYS-021

The system shall process each job through the state sequence QUEUED, RENAMING,
TRANSFERRING, terminating in DONE or FAILED.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active. This is the v1.0.0 state model; the two-level job/file model
of the Python implementation returns with the v1.1 claim-and-verify semantics.

### L1-SYS-022

The system shall reject every state transition not defined by `L1-SYS-021`.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-SYS-023

The system shall record a per-job error description on any failure.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-SYS-017

The system shall process jobs concurrently using a configured number of workers.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-SYS-018

The system shall, on SIGTERM, stop accepting new jobs, drain in-flight work, and exit
cleanly.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

---

## Durability & Recovery

### L1-SYS-007

The system shall maintain a durable record of every submitted transfer job and every
file included in each job.

**Verification Method**: Test (T)
**v1.0.0 Status**: Partial — the per-job clause is Active. The per-file clause is
deferred → v1.1 with `L1-SYS-003`/`L1-SYS-006`.

> The durable-storage **mechanism** is deliberately unstated here and remains undecided
> pending an ADR reopening the journal-versus-SQLite question. L1 states the obligation;
> the mechanism belongs in L2.

### L1-SYS-005

The system shall recover incomplete transfer jobs following service termination, host
restart, NFS interruption, or process failure.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred → v1.1. **This is a genuine reduction in guarantee**, not a
restatement: v1.0.0 provides `L1-SYS-016` (mark interrupted jobs failed) rather than
resuming them. Recovery-by-resumption returns at v1.1.

### L1-SYS-016

The system shall, on startup, identify jobs interrupted by an unclean shutdown and mark
them FAILED with a descriptive reason.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — the v1.0.0 stand-in for `L1-SYS-005`.

---

## Observability

### L1-SYS-008

The system shall provide interfaces to submit, inspect, retry, and diagnose transfer
jobs.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — satisfied via the REST interface (`L1-API-001`,
`L1-API-002`) rather than the `AF_UNIX` control socket and thin CLI.

### L1-OBS-001

The system shall serve a browser dashboard displaying job states, source and destination
paths, throughput, and recent failures.

**Verification Method**: Demonstration (D)
**v1.0.0 Status**: Active — new capability, no Python-implementation equivalent.

### L1-OBS-002

The system shall provide aggregate statistics, including counts per state and bytes
moved, over the REST interface.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-OBS-003

The system shall timestamp job creation, every state change, and job completion.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

---

## Configuration

### L1-SYS-019

The system shall read all runtime parameters from a single INI configuration file.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-SYS-020

The system shall refuse to start on invalid configuration, reporting every issue found
together, each identified by file and line.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — **Corrected.** This originally said "the file and line of
the *first* error", carried over from the inherited design. That contradicted
`L2-CFG-008`, a pre-existing child requirement demanding all issues be reported
together — a parent contradicting its own child, introduced by porting the inherited L1
without checking it against the L2 already in the repository. The all-issues behaviour
wins: it is what the Python implementation already does, and it spares operators a
fix-one-restart-repeat loop.

---

## Robustness

### L1-ROB-001

The system shall handle arbitrary or malformed input to any interaction surface — the
REST interface, the configuration file, and command-line arguments — without panicking;
no unhandled exception shall terminate the service.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — Rewritten to name the REST interface in place of the
control protocol.

### L1-ROB-002

The system shall resist resource exhaustion on every untrusted-input path, bounding
recursion depth, allocation, and input size such that no input can exhaust the stack or
address space.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — new. `L1-ROB-001` covers unhandled exceptions but not stack
exhaustion or memory amplification, which are the realistic denial-of-service vectors
against a parser. See ADR-0008, ADR-0009.

---

## Security invariants

These derive from `docs/CYBERSECURITY.md`, which states the threat model they
answer. `L1-SEC-001` and `L1-SEC-002` are load-bearing: every other filesystem
requirement traces to one of them.

### L1-SEC-001

Every move operation shall have exactly one atomic commit point, implemented as
a single filesystem rename operation.

**Verification Method**: Analysis (A), Test (T)
**v1.0.0 Status**: Active

### L1-SEC-002

All state prior to the commit point shall be disposable, and all actions after
it shall be idempotent, such that recovery after interruption at any instant
produces a correct final state.

**Verification Method**: Analysis (A), Test (T)
**v1.0.0 Status**: Active

### L1-SEC-003

The durable record shall identify, at any instant, the location and phase of
every in-flight move, and shall record the identity of the source object —
device, inode, and size — captured at intent time.

That identity is what disambiguates "the source name exists" after a crash.
Without it, a new file written at the same path by the next simulation run is
indistinguishable from the original, and recovery can act on the wrong file.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active

### L1-SEC-004

The system shall treat interference by external privileged processes — endpoint
security, quarantine, and audit agents — as a modeled state rather than an
assumed impossibility.

**Verification Method**: Analysis (A), Test (T)
**v1.0.0 Status**: Active

### L1-SEC-005

The system shall operate under least privilege and shall function correctly with
platform mandatory access control — SELinux on RHEL, AppArmor on SLES — in
enforcing mode.

**Verification Method**: Test (T), Demonstration (D)
**v1.0.0 Status**: Active

### L1-SEC-006

The system shall never silently overwrite an existing destination file.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — strengthens `L1-SYS-014`, which forbids a partially
written file becoming visible; this forbids replacing a complete one.

### L1-SEC-007

The system shall move files within a single filesystem only, and shall reject a
cross-filesystem move and a directory move with distinct, actionable errors.

**Verification Method**: Test (T)
**v1.0.0 Status**: Active — a deliberate v1.0.0 constraint, not a limitation.
See section 0 of `docs/CYBERSECURITY.md`: it removes the staging directory and
the recursive walk entirely, and avoids depending on an atomic no-clobber
directory move that does not exist over NFS. Cross-filesystem support is a v1.1
item with its own design and fault-injection suite.
