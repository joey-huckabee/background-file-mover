# L1 — System Requirements

Level 1 requirements state *what* the Background File Mover system must accomplish.
Each is a single SHALL statement with a declared verification method. L1 requirements
decompose into L2 architectural derivations (`docs/L2-REQ.md`), which decompose into L3
implementation obligations (`docs/L3-REQ.md`). Live verification status is tracked in
the auto-generated `docs/TRACE-MATRIX.md`, not here.

Verification method codes: **T** = Test, **I** = Inspection, **A** = Analysis,
**D** = Demonstration.

## v1.0.0 scope

Additive Rust requirements for generator submissions and configured delivery
appear at the end of this file. They are specified, unimplemented and outside
the historical v1.0.0 C++ coverage scope; existing SHALL statements are retained.

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
**v1.0.0 Status**: Rewritten — this originally required three strategies:
same-filesystem move, cross-filesystem copy, and an external command, carried
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
without checking it against the L2 already in the repository. The all-issues behavior
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

---

## Additive Rust generator and delivery requirements

These additions describe the Rust contract in
[REST-API-DRAFT.md](REST-API-DRAFT.md). **Rust Status: Specified, not implemented.**
The v1.0.0 Deferred annotation excludes them from historical C++ scope; it does
not schedule them for the old v1.1 release. L2/L3 derivation and Rust verification
remain future work. Earlier requirement IDs and C++ evidence are preserved.

### L1-API-007

The system shall provide an additive recording-set submission form containing
generator identity, a mover-visible source directory and explicit file names,
without requiring the generator to supply a destination.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust generator submission; preserve existing request forms.

### L1-API-008

The system shall return HTTP 202 for recording-set submission only after durable
acceptance and confirmed durable claiming of every listed file, permitting source
path reuse without requiring producer polling.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred — Rust 202 handoff; Accepted/Claimed remain separate internal facts, independent of destination commitment.

### L1-API-009

The system shall resolve repeated equivalent submissions under the same authorized
generator-scoped idempotency key to the original job and its pinned destination.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred — Rust durable replay; claimed-job replays return 202 and conflicts do not replace the original job.

### L1-SYS-024

The system shall select each generator submission's destination from validated
startup configuration using a default route or administrator-defined generator route.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust destination routing; no generator destination selection is required.

### L1-SYS-025

The system shall preserve an accepted job's resolved nonsecret destination identity,
file mapping and delivery policies across retries, restarts and configuration changes.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred — Rust routing snapshot; unavailable original destinations block rather than reroute.

### L1-SYS-026

The system shall expose the same acceptance, source-claim and recording-commit
milestones for each enabled destination backend, supported by that backend's
qualified integrity, publication and recovery evidence.

**Verification Method**: Test (T), Analysis (A)
**v1.0.0 Status**: Deferred — Rust delivery contract; mounted filesystems first, S3 as a separate future adapter.

### L1-SYS-027

The system shall reject startup configuration selecting a destination backend
that the deployed binary does not implement and qualify for the production target.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust backend capability gate; no silent fallback, including unqualified S3 delivery.

### L1-SEC-008

The system shall authorize a generator identity and its source scope independently
of the identity string supplied in the submission body.

For the proposed remote producer profile, the system shall bind the caller to
an operator-approved transport identity and source scope before replay/admission
or claim effects, shall deny producer ingress access to operator/read/control
routes, and shall not fall back to body identity or anonymous permissions after
credential/context refusal. Credential rotation for the same authorized generator
shall preserve submission idempotency; current revocation shall prevent replay
without cancelling accepted work. See [the remote contract and pending RA cases](REMOTE-API-ACCESS-CONTRACT.md).
These are Rust design obligations, not evidence of current remote support.
Registration and token issuance remain deferred.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust caller binding or explicitly trusted local deployment boundary.

### L1-SEC-009

The system shall require independently enforced exclusive execution authority
for each approved NFS source and destination scope, and shall not resume effects
after ownership uncertainty until old writers are excluded and previously issued
operations are settled under a qualified fencing mechanism.

The authority shall cover all affected pinned endpoints and the original local
state writer, not only current routing. Lock acquisition, marker/instance IDs,
timeouts, signals or operator assertions alone shall not authorize activation.
Unknown/incomplete authority shall preserve original state and uncertain effects
and refuse new affected work. Prior valid 202 acknowledgements and committed
manifests shall remain valid; source paths reused by the recorder shall not be
reclaimed. Destination-only unavailability with proven source authority shall
retain L1-SYS-030 handoff behavior subject to its limits.

See [the first-release contract](NFS-OWNERSHIP-FENCING-CONTRACT.md) and NF-01–18.
This new Rust-specific obligation is separate from L1-SEC-008 caller binding;
existing requirement IDs and historical C++ meanings are unchanged. Provider,
L2/L3 derivation and Rust evidence remain future work. It grants no automatic
takeover, re-enrollment, repair or source-deletion authority.

**Verification Method**: Analysis (A), Test (T), Demonstration (D)
**v1.0.0 Status**: Deferred — Rust NFS authority design; no production support or fencing provider implemented.

### L1-SYS-028

The system shall determine and durably record each submitted file's actual logical
size during claiming without requiring a producer-supplied size.

**Verification Method**: Test (T)
**v1.0.0 Status**: Deferred — Rust claim evidence; optional expected sizes are validated assertions, including zero.

### L1-SYS-029

The system shall accept explicitly listed regular files in source subfolders using
safe relative paths without recursively submitting, relocating or deleting directories.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust component traversal within approved source scopes; no symlink or mount escape.

### L1-SYS-030

The system shall permit durable claiming and HTTP 202 handoff during destination
outages when source, local persistence and configured retention/admission limits
allow safe custody, retaining files until delivery to the pinned target resumes.

The source-space margin gate shall be startup-configurable with an explicit
off switch, defaulting off when omitted. When enabled it shall gate only new
submission keys against configured byte/percentage margins using fresh authorized
source observations; unavailable measurements shall not permit new admission.
Accepted-job replay and partial-handoff recovery shall remain subject to existing
safety and reservation limits without being blocked by this additional gate.
Disabling it shall not disable those limits, reset review or authorize deletion.
See [the policy and acceptance scenarios](SOURCE-SPACE-ADMISSION-DESIGN.md) and
[increment 36](RUST-INCREMENT-36.md) for implemented local behavior and exact test
scope. [Increment 38](RUST-INCREMENT-38.md) adds bounded native tmpfs source
exhaustion/restoration evidence only; physical-disk/quota, hard NFS statistics and
broader storage qualification remain outstanding. Historical scope is unchanged.

**Verification Method**: Test (T), Analysis (A)
**v1.0.0 Status**: Deferred — Rust outage admission; unsafe capacity or claiming does not authorize 202.

### L1-SYS-031

The system shall preserve generator-submitted relative file paths within each
destination recording container, creating only directories or object-key prefixes
needed for explicitly listed files.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust generator hierarchy; reject prefix/reserved-name collisions without flattening paths.

### L1-SYS-032

The system shall automatically delete claimed source files after verified durable
recording-set commitment only when the job's recorded cleanup policy and the
currently loaded startup configuration authorize source deletion.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust configurable cleanup; disabled deletion retains/accountably protects claims, and cleanup failures do not restart delivery.

### L1-SYS-033

The system shall retry confirmed missing submitted files for a configurable,
durably bounded period and then require operator review while retaining existing
claims and withholding HTTP 202 until every required claim is confirmed.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust missing-file recovery; default 300 seconds, configurable at startup and recorded per job; submission replay/service restart do not reset the window.

### L1-API-010

The system shall identify whether a non-202 submission response is temporarily
retryable or requires correction/operator review using stable machine-readable
error information.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust recorder retry contract; no non-202 response grants source-path release.

### L1-SYS-034

The system shall publish an immutable recording completion manifest only after
every required file is verified and published, identifying the exact required
relative paths, actual sizes and integrity evidence for consumer validation.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust confirmed consumer contract; consumers wait for a valid COMMITTED.json before using a set.

### L1-SYS-035

The system shall support startup-configurable grouping of generator recordings
by validated generator identity while preserving each recording's submitted
relative file paths and accepted destination mapping.

**Verification Method**: Test (T), Inspection (I)
**v1.0.0 Status**: Deferred — Rust optional generator grouping for filesystem paths and future S3 prefixes; default false preserves the flat-container layout.

Delivery acceptance examples and proposed startup INI keys are design artifacts,
not behavior of the current C++ service. Filesystem deletion still requires the
[transfer protocol](TRANSFER-PROTOCOL.md); future S3 cleanup needs separate
validated object/manifest receipts and retention assumptions.
