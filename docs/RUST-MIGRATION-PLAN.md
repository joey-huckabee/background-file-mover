# Rust migration plan for Background File Mover

**Direction update, 2026-10-13:** [RUST-DIRECTION.md](RUST-DIRECTION.md) and the
user's [CONVERSATION.md](../CONVERSATION.md) supersede the earlier release scope
and implementation schedule below. Experiments are stopped after E1–E5; E6 is
unrun. Next work is protocol/requirements design, not another experiment or a
component-for-component port. Reconcile the fifteen milestones with claiming,
cross-filesystem transfer, manifests and process isolation before implementation.

**Status:** E1–E5 passed, including Tokio runtime/signals; E6 and R0–R14 are pending.
Rust, x86_64 only, GNU/glibc 2.22, and a
ZigBuild-like build project are the user's chosen direction. Compatibility will
be tested in a pinned container with SLES 12 SP5 userspace or the closest verified
glibc 2.22 equivalent. No musl target or actual SLES host test is planned.

Replace the C++ implementation with Rust built on a modern development host,
while preserving the service's durable job acknowledgement, filesystem safety,
REST contract, and unprivileged operation on SLES 12 SP5. Prove deployment
compatibility before porting the components whose correctness matters most.

The user has changed scope: claiming, cross-filesystem copying and content
verification belong in the redesigned transfer protocol. The integrity I/O
strategy is unresolved because the user rejects the proposed 4N workflow.
Partial-copy resumption and optimization follow a correct recovery baseline.
The remaining detailed milestone lists retain useful obligations from the older
plan; their sequence and same-filesystem-only scope require revision.

## Current baseline

The reference implementation is `main` at `a6efb3d`. C6 is delivered; the earlier
C++ roadmap next called for C7, the dashboard. The active roadmap now begins
with requirements and transfer-protocol design. The generated trace matrix reports
109 of 214 in-scope requirements with test markers and 134 of 214 verified
including inspection, analysis, and demonstration. Those are C++ evidence,
not Rust coverage or proof that deployment qualification is complete.

Implemented components include configuration, JSON, HTTP request parsing, job
transitions, rename templates, SQLite storage, fd-relative filesystem operations,
the move engine, worker scheduling, REST command handling, events, singleton
locking, signals, readiness, and watchdog notification. The router implements
health, submission, and pause/resume/cancel/retry commands. Job listing, job
detail, aggregate status, and the dashboard still need delivery.

The C++ move engine handles regular files on the same filesystem. It tries
`renameat2(RENAME_NOREPLACE)` and supports `linkat` followed by `unlinkat`, the
important NFS path. This is a metadata move; the recording size does not imply
that the existing engine copies 100 GB of content.

Several onboarding statements are obsolete: the root README describes a much
earlier implementation, `cpp/README.md` still mentions an external-command
strategy rejected by ADR-0011, and `CLAUDE.md` contains old branch and config
guidance. Establish the new direction explicitly so these do not steer the port.

## Build and runtime contract

Use a pinned modern stable Rust toolchain with `std`, Cargo, and a GNU Linux
target. SLES runtime compatibility does not require using its GCC to compile
Rust. Rust documents `x86_64-unknown-linux-gnu` with a Linux 3.2 and glibc 2.17
baseline; SLES 12 SP5 is documented with Linux 4.12, and the repo records glibc
2.22, independently confirmed by SUSE's [package update record](https://www.suse.com/support/update/announcement/2026/suse-su-20260680-1/).
Verify the final link and container runtime behavior, and record the container's
limits when assessing kernel compatibility. [Rust platform support](https://doc.rust-lang.org/stable/rustc/platform-support.html),
[SUSE release notes](https://www.suse.com/releasenotes/x86_64/SUSE-SLES/12-SP5/index.html).

The initial build specification is:

| Item | Proposed contract |
|---|---|
| Build machine | Modern Linux CI or development host |
| Production architecture | x86_64, conservative CPU baseline |
| Rust target | `x86_64-unknown-linux-gnu` |
| Target glibc | Explicit 2.22 |
| Compatibility runtime | Pinned SLES 12 SP5 or documented equivalent container, glibc 2.22 |
| Build integration | User's build project, modeled on cargo-zigbuild |
| Rust application libraries | Linked into the executable through the normal Cargo build |
| SQLite | Bundled C amalgamation, statically linked, explicit compile settings |
| Host libraries | Target glibc/loader and a measured, documented allowlist of system libraries |
| Deployment | Executable, config, systemd unit, license notices, and installation metadata |
| Target prerequisites | No Rust, Cargo, Zig, compiler, or new SQLite package |

For illustration only, the equivalent cargo-zigbuild command is:

```sh
rustup target add x86_64-unknown-linux-gnu
cargo zigbuild --release --locked --target x86_64-unknown-linux-gnu.2.22
```

The `.2.22` suffix is build-tool syntax, not a separate rustup target. The
production wrapper will use the user's project's actual CLI. Its version,
target handling, C compiler forwarding, sysroot, and offline behavior must be
qualified in R1 and R2. Do not assume exact compatibility with cargo-zigbuild.

Specify the glibc version on every production invocation. cargo-zigbuild documents
that an unspecified GNU target can select a newer glibc baseline, and that invalid
versions and linker overrides have caveats. The artifact's ELF metadata and a
execution in the pinned glibc 2.22 container are therefore required. [cargo-zigbuild documentation](https://github.com/rust-cross/cargo-zigbuild#specify-glibc-version).

Production checks must inspect both the executable and every packaged shared
object for architecture, interpreter, required symbol versions, `DT_NEEDED`,
and unintended RPATH/RUNPATH. Reject required `GLIBC_*` versions above 2.22,
`GLIBC_PRIVATE`, unexpected libraries, and build-machine paths. Check other
symbol namespaces such as `GCC_*` against the target's installed libraries too.
Record the exact allowlist after the probe rather than guessing it in advance.
Apply the conservative CPU baseline to native C dependencies as well as Rust;
never use `target-cpu=native` for release artifacts.

E1 verified the cached SLES 12 SP5 image and glibc 2.22 inventory pinned in
[image evidence](E1-SQLITE-EVIDENCE.json). Reuse it for E3–E6; its
[result](E1-SQLITE-EVIDENCE.json) records toolchain, artifact,
and userspace evidence. If unavailable, a reproducible openSUSE Leap 42.3 rootfs
is an initial approximation; its official [package archive](https://cdn.opensuse.org/update/leap/42.3/oss/src/)
contains glibc 2.22. Inventory and document differences rather than claiming
that equal glibc versions make the distributions identical.

Keep build and runtime containers separate. Pin the runtime digest or rootfs
inputs, assert its glibc version is exactly 2.22, verify the loader/package set,
and run copied artifacts unprivileged without build-host library mounts or added
compatibility libraries. Share this runtime across the six experiments and
provide compatible systemd and controlled NFS fixtures for later milestones.

A container shares the runner's kernel and CPU. Record them separately, audit
consumed syscalls against the SLES Linux 4.12 baseline, and use targeted injected
errors or seccomp tests to exercise fallbacks for unavailable operations. These
tests cannot reproduce every old-kernel, CPU, NFS-server, or MAC-policy behavior.
State precisely which dimensions are exercised by the container setup; the plan
does not require an actual SLES host. SUSE documents kernel-related container
compatibility limits in its [Container Guide](https://documentation.suse.com/en-us/container/all/html/Container-guide/index.html).

## Dependency policy and proposed architecture

Few crates and few host dependencies are separate objectives. A crate incorporated
in the executable does not automatically add a target-host package requirement.
Audit the complete enabled dependency graph, build scripts, native libraries,
licenses, and runtime imports; direct dependency count alone is insufficient.

Start with one application package containing a library and a thin binary under
`rust/`. Use modules for `job`, `config`, `codec`, `store`, `fsops`, `mover`,
`manager`, `http`, `service`, and `events`. Keep the core deterministic, use typed
errors, own descriptors with Rust RAII, and pass clocks and fault seams explicitly.
Use Tokio for async signal, timer and socket coordination after E5 qualification.
Begin with a current-thread executor. Retain separately bounded blocking work
for moves and SQLite, outside both the executor and manager lock. Bound task
admission and blocking queues explicitly; drain started operations during stop.
`std` threads, synchronization and collections remain suitable for blocking cores.

Introduce six package families in experiments E1–E6 before the full application
port: SQLite, Unix operations, JSON, HTTP parsing, signals, and typed errors.
R1 consolidates their compatibility evidence; R2 adopts the qualified versions
and features. Resolving a candidate graph does not establish compatibility.

| Need | Initial candidate | Boundary and rationale |
|---|---|---|
| Filesystem and Unix operations | `rustix` with narrowly enabled features | Prefer safe descriptor and syscall wrappers; verify old-kernel fallbacks |
| Runtime and signal integration | `tokio`, defaults disabled; rt/signal/sync/time/net/io-util | Qualify reactor, timers, stop wakeups and blocking drain; audit mio/libc/socket2 and transitive signal-hook-registry |
| Durable state | `rusqlite`, default features disabled, bundled SQLite | Avoid a target SQLite installation and broad optional integrations |
| JSON | `serde` and `serde_json` | Apply the existing strict profile through typed decoding and checked visitors |
| HTTP head parsing | `httparse` | Use an established parser plus explicit framing policy and bounded socket handling |
| Typed errors | `thiserror` | Preserve phase-sensitive errors; audit procedural macros and target code separately |
| Config, CLI, templates, logs, tests | `std` plus small project modules | Present grammars and flags are narrow; retain behavior without adding frameworks |

`rusqlite` supports bundled SQLite; `httparse` provides an HTTP/1.x parser; and
`rustix` provides safe Unix/Linux syscall wrappers. These are candidates, not a
claim that their default settings meet this repo's policy. [rusqlite](https://github.com/rusqlite/rusqlite),
[httparse manifest](https://raw.githubusercontent.com/seanmonstar/httparse/master/Cargo.toml),
[rustix manifest](https://raw.githubusercontent.com/bytecodealliance/rustix/main/Cargo.toml).
Signal handling and typed errors are represented by the upstream
[Tokio manifest](https://raw.githubusercontent.com/tokio-rs/tokio/master/tokio/Cargo.toml)
and [thiserror manifest](https://raw.githubusercontent.com/dtolnay/thiserror/master/Cargo.toml);
their SLES compatibility remains an experiment result to establish.

Tokio replaces the direct signal-hook candidate at the user's request and is
the initial async runtime candidate. Its Unix signal feature still uses
signal-hook-registry transitively. Do not enable full, macros, rt-multi-thread,
fs, process, parking_lot, io-uring or unstable features in the initial experiment.
Keep large web frameworks, ORMs, TLS stacks, external transfer commands, and
allocation-heavy logging systems outside the initial dependency set.
Add a crate when it removes meaningful correctness or maintenance cost,
and record the resulting graph change. Build and test tools are tracked separately
from production libraries; development-only dependencies still receive the
repo's license review.

Preserve ADR-0007's existing license policy. Review transitive crates and embedded
native sources, and inspect the pinned Rust release's standard-library notices.
Rust publishes separate standard-library copyright information; Cargo.lock does
not describe that entire component set. Resolve any conflict with the existing
policy explicitly before making it a foundational dependency. [Rust copyright information](https://raw.githubusercontent.com/rust-lang/rust/main/COPYRIGHT).

## Six dependency experiments beginning with SQLite

The experiment design covered six package families: E1 `rusqlite` with bundled
SQLite, E2 `rustix`, E3 `serde`/`serde_json`, E4 `httparse`, E5 `tokio`, and
E6 `thiserror`. E1 passed with Rust 1.99.0 using the reference cargo-zigbuild
builder. E2 also passed; its [result](E2-RUSTIX-RESULTS.md) records the isolated,
cumulative, injected-error, and controlled NFS checks. The reusable
[NFS fixture note](NFS-TEST-FIXTURE.md) preserves its setup. E3 passed; its
[result](E3-JSON-RESULTS.md) records strict JSON and cumulative qualification
with no new shared libraries. E4 passed; its [result](E4-HTTP-RESULTS.md) records
strict HTTP, bounded TCP, verified normal/SWAR variants and cumulative checks.
E5 passed with Tokio; its [result](E5-TOKIO-RESULTS.md) records the minimal runtime,
signals, blocking drain, async TCP and forced entropy fallbacks. E6 is pending.
Experiments remain paused. Resume from the forward-looking
[roadmap](ROADMAP.md#next-work), not by automatically starting E6.
The detailed [E1 report](E1-SQLITE-RESULTS.md)
limits its result to the pinned inputs and exercised APIs.

Every proposed production dependency must pass a small, retained experiment
before application integration. Test the exact version, enabled features, native
build settings, and release profile that will be adopted. Repeat the experiment
when any of those inputs or the compiler/build project changes. Re-run it in the
combined application too: dependencies can unify features or select different
native build settings when composed.

Start with `rusqlite` and bundled SQLite. Keep the experimental crate separate
from the application so a rejected dependency can be removed without affecting
the port. The first experiment has these steps:

1. Build a small `std`-only executable as the control using the pinned modern
   toolchain and the user's GNU build project with an explicit glibc baseline.
   Record its hash, build inputs, ELF interpreter, libraries, and versioned symbols.
2. Add only a pinned `rusqlite` with default features disabled and bundled SQLite
   enabled. Resolve and record its complete enabled graph, including native sources
   and build dependencies. Use the target C compiler settings for SQLite.
3. Exercise the real storage path: create a local database, enable and read back
   WAL/FULL/foreign-key settings, write a transaction, close, reopen, and verify
   the row. Exercise multiple connections, a busy database, and rollback. Check
   extension loading and the other required SQLite compile settings explicitly.
4. Inspect the final release artifact and compare it with the `std` control.
   Report added imports and version requirements, changed `DT_NEEDED` entries,
   the exact ELF interpreter, RPATH/RUNPATH, and any native library additions.
   Diagnose unexpected changes rather than accepting a green compilation.
5. Execute that exact binary in the pinned glibc 2.22 runtime container as the
   intended service account, using local state storage. Prove database creation,
   transaction and reopen behavior with the container's loader/libraries. Install no
   compatibility packages to make the experiment pass.
6. Preserve the source, lockfile, commands, compiler forwarding evidence, ELF
   report, artifact hash, container inventory/digest, and results. Accept it after the
   checks pass; otherwise adjust its features/build settings or evaluate an
   alternative binding to the existing SQLite amalgamation and repeat the test.

The loader concern is the executable's ELF `PT_INTERP` entry and the runtime
dynamic linker, not the machine's bootloader. The executable must request an
interpreter already present on SLES; introducing a new loader or packaging a
replacement glibc is outside this migration's runtime contract.

| Check | SQLite experiment acceptance criterion |
|---|---|
| Architecture and CPU | x86_64 artifact with the agreed conservative instruction baseline |
| Dynamic loader | Exact `PT_INTERP` path exists and works in the verified runtime container |
| glibc symbols | No required `GLIBC_*` version above 2.22 and no `GLIBC_PRIVATE` |
| Other symbols | Every imported/versioned symbol is resolved by the runtime's allowed libraries |
| Shared libraries | No unexpected `DT_NEEDED`; no system SQLite or unintended C++/crypto dependency |
| Search paths | No build-host RPATH/RUNPATH or accidental host library lookup |
| Native compilation | SQLite uses the target headers/compiler/baseline and required compile settings |
| Behavior | WAL, durability settings, transactions, contention, and reopen tests pass in the container |
| Provenance | Inputs, feature graph, artifact hash, image digest/inventory, and runtime evidence are retained |

After SQLite passes, apply the same control-and-candidate comparison to Unix
wrappers, JSON, HTTP parsing, and signal handling in turn. Account for existing
approved dependencies in the control artifact, and test the candidate APIs the
service will actually call so linker dead-code elimination does not hide a
compatibility problem. Include typed errors in E6. Repeat import and container checks
after the dependencies are combined and on the final packaged binary.

## Safety contracts to retain

1. A successful submission response follows a durable job record, never only an
   in-memory queue insertion. Job identifiers remain monotonic across restarts.
2. Durable intent precedes filesystem mutation. A store failure before the commit
   point aborts safely; a store failure after it requires the specified fatal
   response, diagnosis, and recovery. Do not silently treat both as retryable.
3. Destination publication never overwrites an unrelated file. Preserve both the
   no-replace rename and link/unlink protocols, including recovery between the
   link and unlink where two names can refer to the same inode.
4. Hold directory descriptors, reject symlink traversal component by component,
   compare opened-file identity, verify trusted ownership, and refuse unsupported
   file types. Rust's memory safety does not prevent filesystem races.
5. Preserve file and directory flush ordering and exercise NFS behavior in the
   controlled client/server fixture. Record its differences from deployment;
   process kills do not establish server-side durability under power loss.
6. Keep SQLite state on local storage with WAL and `synchronous=FULL`, validate
   returned settings, reject corrupt or unknown schemas, and retain SQL isolation.
7. Bound workers, requests, headers, bodies, queues, and retries. A stalled client
   or move must not lock the control plane or authoritative state processing.
8. Treat expected operational failures as typed results. Define how a panic,
   poisoned mutex, or worker loss stops admission and initiates safe shutdown or
   restart; catching a panic must not imply a partially mutated job is safe to retry.
9. Events follow durable transitions and cannot control them. Preserve escaped
   log output, job identifiers, severity gating, and subscriber failure isolation.
10. Keep loopback binding, proxy-terminated TLS/authentication, singleton locking,
    real readiness, watchdog semantics, and unprivileged deployment.

Two inherited claims require explicit review. The fallback is a multi-syscall
protocol, so its crash states must be documented rather than described as a single
atomic rename. Also, a thread timeout or async timeout does not by itself interrupt
a filesystem syscall stuck in kernel I/O. R1 must decide how `L2-SEC-009` and
`L2-SEC-010` are satisfied in the NFS fixture; isolation, admission limits,
operator-visible failure, and target probes may be required. Preserve the safety
requirements and record any justified implementation change.

## Delivery sequence

Use one branch and reviewable merge per milestone, following the existing repo's
milestone convention. Retain the C++ implementation and its CI until Rust parity
and release qualification are complete. Run implementations against separate test
trees and databases; do not run two services against production recordings to
compare their behavior.

| Milestone | Deliverable | Completion evidence |
|---|---|---|
| R0 | Baseline, scope, and architecture decisions | Reference fixtures and approved technical contract |
| R1 | GNU platform and experiment qualification | E1–E6 evidence accepted; container inputs and NFS isolation documented |
| R2 | Dependency and offline build foundation | Audited graph and reproducible build inputs |
| R3 | Requirements and Rust CI | Rust evidence cannot inherit C++ implementation status |
| R4 | Core types, config, and templates | Deterministic contract tests |
| R5 | JSON and HTTP parsing policies | Existing hostile corpora and strictness tests pass |
| R6 | SQLite repository | Schema compatibility, real write faults, durable sequence |
| R7 | Filesystem layer | Race, no-clobber, and both move-strategy tests |
| R8 | Move engine and crash recovery | Kill-at-phase tests and post-commit failure handling |
| R9 | Scheduler, workers, and events | Deliberate interleavings and safe shutdown |
| R10 | REST service and read endpoints | Bounded hostile-client tests and complete status API |
| R11 | Daemon and systemd lifecycle | Real process and compatible systemd container tests |
| R12 | Dashboard and operator workflows | Self-contained page and XSS regression tests |
| R13 | Packaging and target qualification | SLES-equivalent/RHEL container and controlled NFS evidence |
| R14 | Cutover, documentation, and retirement | Release evidence, rollback procedure, Rust default |

### R0 Establish the migration baseline

- [ ] Record the reference C++ commit and its reproducible build environment;
  preserve its source and existing test inventory throughout the port.
- [ ] Capture the implemented REST/config contracts, job states, schema version 3,
  sequence allocation, `.swit-partial-<job_id>` naming, error categories, and
  filesystem ordering in versioned fixtures and a parity checklist.
- [ ] Classify existing requirements as language-neutral, C++-specific, deferred,
  implemented, or still outstanding. Inventory actual behavior before copying
  commentary that may be stale. Inventory any deployed Python instances too:
  their broader features and database format are not automatically compatible
  with the narrower C++ baseline or the first Rust release.
- [ ] Write a new Rust/platform ADR superseding ADR-0001. Retain license,
  durability, no-external-command, proxy TLS, and bounded-handler decisions.
  Amend parser and vendoring ADRs where modern Rust changes their rationale.
- [ ] Record the release scope and the R0-R14 sequence in the roadmap. Retain the
  C++ milestone history, and fix the stale onboarding statements.

**Done when:** the parity checklist identifies what Rust must preserve and what
it must still implement; no deferred feature becomes an accidental port requirement.

### R1 Consolidate the experiments and platform qualification

- [ ] Consolidate E1–E6 results, runtime digest/rootfs hashes, glibc 2.22 package
  inventory, loader, systemd version, runner kernel/CPU, and NFS fixture settings.
  Document differences from SLES 12 SP5 and all unexercised platform dimensions.
- [ ] Verify that every isolated candidate and the accumulated six-package probe
  passed the shared compatibility gate. Reuse retained evidence instead of
  rebuilding unchanged experiments without a new concern.
- [ ] Review SQLite's native build and compile settings and each package's exact
  version, feature graph, licenses, consumed syscalls, and target imports.
- [ ] Confirm the user's build-project revision accepted the explicit 2.22 target
  and forwarded the target C settings. Retain the allowlist and pass/fail records.
- [ ] Probe rename-without-replacement support, forced link/unlink fallback,
  directory fsync, and stalled NFS behavior. Decide how filesystem timeouts and
  forward-progress requirements will be met before fixing the worker model.

**Done when:** E1–E6 pass in the pinned runtime container without compatibility
package additions, the evidence states its platform coverage precisely, and the
filesystem isolation decision is recorded. This precedes the full implementation.

### R2 Lock the toolchain and dependency graph

- [ ] Create the Rust package under `rust/` with a library and thin executable.
  Pin Rust, edition, minimum supported Rust version, build-project revision,
  compiler/sysroot inputs, and the builder image or environment.
- [ ] Adopt the versions/features qualified by E1–E6. Record direct/transitive
  packages, licenses, build scripts, native sources, and target-specific graph
  differences using Cargo metadata and feature trees. Apply the experiment gate
  to further additions or changes and recheck the combined application.
- [ ] Select bundled SQLite's version deliberately. Preserve the current
  amalgamation where practical, or document and characterize a version change.
  Do not allow the Rust wrapper to silently replace the native library contract.
- [ ] Verify `SQLITE_THREADSAFE=1`, `SQLITE_OMIT_LOAD_EXTENSION`, `SQLITE_DQS=0`,
  `SQLITE_DEFAULT_MEMSTATUS=0`, and `SQLITE_ENABLE_API_ARMOR`. Test the effective
  settings; disabling a Rust API alone does not remove SQLite's native capability.
- [ ] Commit Cargo.lock, vendor dependencies, preserve provenance and notices,
  and provide all external builder inputs needed for an offline build. Prove
  the build works with networking disabled and dependency resolution frozen.

**Done when:** the resolved graph and native configuration are reviewed, and the
same production build works from pinned inputs without network access. Cargo
supports vendoring and frozen dependency resolution. [Cargo vendor documentation](https://doc.rust-lang.org/stable/cargo/commands/cargo-vendor.html),
[Cargo feature tree documentation](https://doc.rust-lang.org/cargo/commands/cargo-tree.html).

### R3 Establish Rust evidence and CI

- [ ] Extend `scripts/build-trace-matrix.py` to distinguish C++ and Rust evidence.
  Keep a baseline C++ report and a separate Rust implementation report; a passing
  C++ test cannot mark the Rust implementation verified.
- [ ] Preserve requirement IDs for reusable obligations, including reusable
  `L3-CPP` obligations where appropriate. Retain C++-only obligations as historical
  evidence and add Rust-specific obligations with explicit mappings and parents.
- [ ] Choose a checked-in requirement-to-test manifest or another dependency-light
  marker format. Validate referenced Rust tests against the discovered test
  inventory, including integration tests and target-specific applicability.
- [ ] Add formatting, Clippy, functional tests, a production-target build, ELF
  checks, license/dependency gates, and frozen-build CI. Include docs, requirement,
  build-script, and deployment changes in workflow triggers.
- [ ] Define reviewed unsafe boundaries and panic policy. Test pure code with
  Miri where useful and native/unsafe integration with supported sanitizers.
  Keep analysis jobs separate from the artifact that is deployed.

**Done when:** CI reports Rust evidence honestly and fails on target, dependency,
or contract drift before new modules accumulate.

### R4 Port the deterministic core

- [ ] Implement job identifiers, state transitions, commit phases, command results,
  and phase-sensitive errors as Rust types with exhaustive matching.
- [ ] Port configuration defaults, accepted sections/keys, unknown-key rejection,
  numeric bounds, accumulated errors, and validation that creates nothing.
- [ ] Port rename-template validation, sequence formatting, boundary cases,
  path/name validation, and the intended UTF-8 API versus filesystem-byte policy.
- [ ] Port the relevant Catch2 scenarios as native Rust tests using injected
  clocks and deterministic fixtures. Do not claim parity by assertion count.

**Done when:** the core produces the same meaningful results for the reference
fixtures, including failures and boundaries, without filesystem or network I/O.

### R5 Replace parsing while retaining strict policies

- [ ] Implement the JSON boundary with Serde and explicit validation for top-level
  objects, whole-input consumption, unknown/missing fields, duplicate keys,
  signed 64-bit integer bounds, rejected floats/exponents, NUL, and UTF-8 rules.
- [ ] Enforce the existing depth, token, string, and member limits during decoding.
  Do not deserialize into a generic map first and then try to detect duplicates
  that the map has already discarded. Derived field validation alone is insufficient.
- [ ] Wrap `httparse` with the HTTP subset policy: request line, CRLF, duplicate
  headers, Content-Length, Transfer-Encoding rejection, size limits, and one
  request per connection. Own response framing and serialization explicitly.
- [ ] Reuse the JSON and HTTP seed corpora, port rejection tests, and add Rust
  fuzz targets for the policy adapters. Use the C++ parser as a comparison oracle
  while documenting intentional differences; the written contract wins conflicts.

**Done when:** hostile and valid corpora retain the required accept/reject behavior,
and fuzzing finds no unbounded resource growth or panic in the exposed boundary.

### R6 Port the durable repository

- [ ] Implement the repository over rusqlite with prepared statements and confined
  SQL. Define connection ownership without sharing a connection unsafely across
  workers or holding the manager mutex during database work.
- [ ] Run synchronous repository calls on separately bounded workers, reached
  through bounded admission/channels from Tokio. A canceled async waiter must
  not imply cancellation or rollback of a started transaction.
- [ ] Preserve schema version 3, constraints, sequence allocation, transition
  timestamps, retry lineage, attention flags, indexes, and existing migrations.
- [ ] Set and read back WAL, FULL synchronization, foreign keys, and busy timeout.
  Reject remote storage, corrupt files, unknown schema versions, and invalid rows.
- [ ] Port real SQLite write-refusal/full/corruption scenarios and kill-at-write
  tests. Verify abort-before-commit versus fatal-after-commit handling.
- [ ] Test opening copies of C++-created databases in Rust and Rust-created
  compatible databases in C++. Record any difference that affects rollback;
  never reset a nonempty state database to simplify the migration.

**Done when:** durable acknowledgement and monotonic identifiers survive restart,
and compatibility fixtures can cross the implementation boundary safely.

### R7 Port the filesystem safety layer

- [ ] Own directory and file descriptors with RAII, use operations relative to
  held descriptors, and preserve per-component no-follow directory traversal.
- [ ] Preserve entry classification, opened-file identity checks, trusted UID,
  regular-file restriction, same-filesystem checks, and no-clobber behavior.
- [ ] Use a syscall-capable no-replace rename wrapper that does not import a
  glibc symbol newer than the target. Handle unsupported kernel/filesystem cases
  with the existing link/unlink protocol and precise error classification.
- [ ] Port deterministic symlink/entry-swap injection, destination races,
  disappeared files, hard-link identity, interrupted fallback, and fsync faults.
  Force both strategies in tests rather than relying on the local filesystem.

**Done when:** safety/recovery classifications pass on local storage and the
controlled NFS fixture, with no unexpected newer-glibc imports and platform
differences recorded.

### R8 Port the move engine and recovery protocol

- [ ] Implement validation, durable RENAMING intent, commit, durable moved state,
  publication, and DONE recording with explicit commit-phase state.
- [ ] Preserve staging names, no-clobber publication, file/directory flushes,
  failed-external handling, and idempotent recovery decisions for every observable
  source/staging/destination combination.
- [ ] Kill subprocesses at each phase and inside the link/unlink fallback. Test
  restart, write failures, destination collision, quarantine, and both-missing
  states using fresh independent test trees and databases.
- [ ] Compare existing post-commit fatal requirements with actual C++ behavior.
  If they disagree, implement and document the required safe response rather
  than duplicating a defect under the name of parity.

**Done when:** every exercised interruption leaves recoverable or explicitly
diagnosed state, and no failure path loses the sole valid file or replaces an
unrelated destination.

### R9 Port scheduling and events

- [ ] Implement bounded scheduling, worker ownership, pause/resume/cancel/retry
  semantics, injected monotonic time, retry limits, and backoff.
- [ ] Keep SQLite/filesystem work off Tokio's executor. Bound blocking admission
  as well as thread count; stop new work and join started operations on shutdown.
  Treat spawn_blocking abort and runtime timeout as insufficient to cancel a
  running operation, particularly at or beyond the move commit point.
- [ ] Enforce the no-store-I/O-under-manager-lock rule structurally. Retain the
  per-entry isolation decision made in R1 and ensure admission stays bounded
  when underlying NFS operations do not return.
- [ ] Define worker panic and poisoned-lock handling, supervisor notification,
  admission shutdown, and safe draining. Test failures after the commit point;
  avoid a catch-and-continue policy that hides incomplete durable transitions.
- [ ] Emit events after durable transitions and outside coordination locks.
  Preserve severity gating, control-character escaping, subscriber isolation,
  and correct behavior with no subscribers.
- [ ] Port deliberate submit/cancel/shutdown interleavings and worker-loss tests
  using barriers/latches. Reassess the C++ timed-condvar prohibition: it was a
  toolchain workaround, not a Rust requirement.

**Done when:** the pool remains bounded, command results are deterministic, and
events cannot change authoritative job behavior.

### R10 Build the REST service and remaining read API

- [ ] Use qualified Tokio socket/timer drivers with explicit connection permits
  and absolute deadlines. Keep route/database/filesystem work outside the async
  executor and bound the handoff queues; enabling a runtime does not bound tasks.
- [ ] Implement a bounded accept/handler model with socket timeouts, head/body
  limits, bounded admission, and deterministic connection shutdown.
- [ ] Port health, durable submission, and pause/resume/cancel/retry routes,
  including status codes and manual retry creating a new job identifier.
- [ ] Implement the remaining job list, job detail, and aggregate status endpoints
  required by `L1-API-002`. Bound/paginate list responses and document the
  contract before connecting the dashboard.
- [ ] Run the hostile-client battery before a successful real job on the same
  server: slow clients, exhausted handlers, malformed/oversized heads, oversized
  bodies, duplicate lengths, transfer encoding, and extra request bytes.
- [ ] Specify when extra bytes can actually be detected and bound socket waits;
  a live TCP connection cannot promise that no more bytes will ever arrive.
  Preserve the no-pipelining policy without inventing an impossible EOF guarantee.

**Done when:** clients can submit, inspect, and control jobs while other clients
stall, without unbounded memory or blocking the move/state layers.

### R11 Integrate the real daemon lifecycle

- [ ] Keep `main` thin and preserve `--config` and `--check` behavior. Set process
  signal policy before spawning threads and provide reliable stop wakeups.
- [ ] Register Tokio SIGTERM/SIGINT listeners before admission, retain one sticky
  shutdown state, and drain blocking operations before dropping the runtime.
  Test signal coalescing and retained process-global handlers across lifecycle
  reuse; dropping a stream does not restore default termination behavior.
- [ ] Preserve lock, store/recovery, manager, listener startup ordering, reverse
  teardown, single-instance refusal, and restart of the same service object.
- [ ] Implement notify datagrams, real READY/STOPPING timing, watchdog environment
  handling, and log stream flushing. Define what watchdog pings prove about
  progress; a separate timer thread alone cannot establish worker health.
- [ ] Parameterize and reuse `scripts/smoke-readiness.py` and the unit gates against
  the Rust binary. Test real process exit, startup failures, signals, and restart.
- [ ] Exercise start/stop and the unit in a systemd-enabled runtime container with
  a verified SLES-equivalent version. Audit each hardening directive and record
  whether the runner enforces it; use supported equivalents or unit variants
  where needed. Unknown directives must not silently weaken deployment.

**Done when:** the Rust daemon is usable at READY, drains correctly, refuses a
second instance, and operates as the intended account in the compatible systemd
container, with the exercised sandbox coverage recorded.

### R12 Finish the dashboard and operator workflows

- [ ] Serve one self-contained page from the binary with no CDN, frontend runtime,
  or externally hosted assets. Use the R10 read endpoints and bounded polling.
- [ ] Render dynamic paths, job IDs, errors, and events through `textContent` or
  `createTextNode`. Test markup, control characters, long names, and failed requests.
- [ ] Complete required operator commands and diagnostics according to the
  requirement inventory. Keep optional convenience CLI/framework work separate
  from the required daemon and REST workflows.
- [ ] Test restart visibility, retries, queue state, attention flags, and failure
  diagnosis from an operator's view. Preserve event formatting where applicable.

**Done when:** operators can observe and control the service without external
web assets, and filenames cannot execute code in their browser.

### R13 Package and qualify the production artifact

- [ ] Package the executable, notices, config, compatible unit, account/state
  directory setup, and writable source/destination roots. Add install/uninstall
  and upgrade instructions that retain recordings and job state.
- [ ] Repeat ELF/library/CPU checks on the final packaged executable, preserving
  artifact hashes and build provenance. Test the same artifact in the pinned
  SLES-equivalent and RHEL 9 userspace containers.
- [ ] Test unprivileged permissions, singleton locking, readiness, shutdown,
  watchdog, and supported hardening. Test AppArmor/SELinux through capable runners
  and record unexercised enforcement dimensions when unavailable.
- [ ] Run the NFS qualification checklist in the controlled client/server fixture
  with both strategies. Exercise network interruption, stale handles, server
  restart, client crashes, and storage failures; document deployment differences.
- [ ] Measure throughput, submission latency, status responsiveness, resource
  bounds, and recovery time. Establish practical thresholds from the C++ baseline
  and the recording workload, including prolonged NFS stalls.
- [ ] Validate offline installation and building separately. Include the build
  project's toolchain/sysroot inputs in the offline build procedure; Cargo
  vendoring alone does not supply them.

**Done when:** release evidence demonstrates the final artifact in the verified
container userspaces and NFS fixture, with kernel, CPU, MAC, and durability limits
recorded. No actual-SLES-host qualification milestone is required.

### R14 Cut over and retire C++ deliberately

- [ ] Complete the Rust-only trace review for the retained in-scope requirements.
  Review inspection/analysis/demonstration evidence directly, and account for
  changed requirements rather than presenting the old percentage as Rust progress.
- [ ] Rewrite README, build/contributor guidance, architecture, deployment,
  config/API/CLI references, logging, security, and migration provenance for the
  final Rust behavior. Retain clearly marked historical artifacts.
- [ ] Rehearse a maintenance-window cutover on copied state and test recordings:
  stop admission, drain, stop the old service, capture a consistent database
  backup including WAL state, install Rust, validate, start, and check recovery.
- [ ] Rehearse rollback of binary/config/unit and compatible state. Preserve a
  qualified previous artifact; the unfinished C++ build is not automatically
  a production rollback candidate. Do not restore an old database over moves
  that have already occurred; reconcile filesystem and state before rollback.
- [ ] Make Rust the default build/release path only after qualification. Archive
  the reference C++ source and evidence in Git, then remove its active tree and
  compiler-specific CI in a dedicated retirement change.

**Done when:** Rust is the supported release, rollback is actionable, the docs
describe the shipped behavior, and C++ removal does not erase requirements or
the history of safety decisions.

## Release gates and ongoing maintenance

Every milestone adds the tests needed for its contract. Modern Rust unit tests
alone are insufficient: execute the GNU-target test binaries or a comprehensive
target integration harness in the pinned glibc 2.22 runtime container. Use the
same release artifact that passed ELF inspection. Containers test old userspace
against the runner kernel; include syscall fallback tests, compatible systemd
and controlled NFS fixtures, and an explicit record of unexercised behavior.

Keep the existing 85% line-coverage floor as the starting overall target where
the measurement is comparable, while requiring explicit crash and failure cases
for the storage and move boundaries regardless of the percentage. Retain parser
fuzz corpora, real SQLite fault injection, deterministic concurrency scenarios,
deployment smoke tests, and a trace-matrix consistency gate. Rust makes several
C++ gates obsolete, but it does not replace native SQLite testing or filesystem
durability tests.

On every dependency, compiler, or builder upgrade: review the enabled graph and
notices, rebuild the production target, repeat ELF and runtime-library checks,
run the SLES compatibility harness, and requalify affected native/filesystem
behavior. Update intentionally and preserve evidence of which exact artifact
ran in the pinned runtime container.

Resume from [RUST-DIRECTION.md](RUST-DIRECTION.md): reconcile requirements and
the transfer/integrity protocol, then revise the milestone schedule. E6 remains
unrun and experiments must not automatically resume. Retain E1–E5 evidence,
glibc 2.22 and the pinned-container contract throughout the redesign.
