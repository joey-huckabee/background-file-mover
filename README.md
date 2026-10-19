# Background File Mover

For what the current tests prove and what remains unqualified, read
[testing limitations](docs/TESTING-LIMITATIONS.md). The
[systemd lifecycle lab guide](docs/SYSTEMD-LIFECYCLE-LAB.md) documents controlled
infrastructure setup, individual test steps, evidence and cleanup.

The [NFS mount-profile contract](docs/NFS-MOUNT-PROFILE.md) selects a buffered
first-release qualification candidate and preserves noac diagnostics separately.
[Increment 68](docs/RUST-INCREMENT-68.md) and its
[lab procedure](docs/NFS-MOUNT-PROFILE-LAB.md) validate read-only model decisions;
increment 69 adds Rust enforcement as described below. Matching mount pins cannot
prove continuity or server availability. Production NFS and source deletion stay off.

[Increment 64](docs/RUST-INCREMENT-64.md) proves selected server-completed NFS
REMOVE replies can be withheld, then tests file/manifest recovery after reply loss
and connection interruption. The [lab](docs/NFS-LOST-REPLY-LAB.md) records capability,
initial failure, exact evidence and cleanup; production NFS/deletion stay disabled.

[Increment 63](docs/RUST-INCREMENT-63.md) tests selected file/manifest unlink
interruptions and crashes before synchronization, preserving owned inode/content
on recovery. The [lab guide](docs/NFS-PUBLICATION-SYNC-LAB.md) explains the twelve
cases and syscall/RPC/durability limits; production NFS/deletion stay disabled.

[Increment 62](docs/RUST-INCREMENT-62.md) qualifies selected destination-outage
startup/early-recovery cases: source/control readiness and confirmed custody 202
can succeed while delivery waits. The [dedicated lab](docs/NFS-DESTINATION-STARTUP-LAB.md)
records each test/infrastructure step; production NFS/deletion remain disabled.

[Increment 61](docs/RUST-INCREMENT-61.md) adds selected restart-after-incomplete-stop
qualification with real hard-NFS workers, repeated manager requests and original-state
recovery. Read actual intervention outcomes and finite limits; production NFS and
source deletion remain disabled.

[Cooperative lock custody](docs/RUST-INCREMENT-25.md) now uses preprovisioned
regular lock files and version-2 bindings, including actual worker inheritance.
This is separate from the remaining takeover/partition fencing. Preserve old
state for explicit enrollment; mixed lock-protocol versions are unsupported.

[Destination binding](docs/RUST-INCREMENT-24.md) now pins policy at acceptance
and validates destination custody before effects, preserving source handoff
during outages. Provision both configured root markers; legacy jobs without a
destination policy require future explicit enrollment.

The [first Rust release checklist](docs/RUST-FIRST-RELEASE.md) defines the
bounded scope, eight remaining release gates and next qualification increment.
Production NFS and source deletion remain disabled pending those gates.
The [remote API access contract](docs/REMOTE-API-ACCESS-CONTRACT.md) defines a
proposed external client-certificate/protected-proxy profile; registration remains
deferred and current remote access is not enabled.
The [NFS ownership/fencing contract](docs/NFS-OWNERSHIP-FENCING-CONTRACT.md)
defines the confirmed single-host/local-state profile. [Increment 42](docs/RUST-INCREMENT-42.md)
implements its shared local guard and explicit worker handoff with selected local
evidence. [Increment 43](docs/RUST-INCREMENT-43.md) adds shutdown_wait_seconds
(default 60, integer 1–3600) and bounded local --stop/--status commands. Timeout
returns incomplete/restart-blocked while ownership remains held. Remaining SH
qualification and delayed-operation recovery stay pending; no takeover is enabled.
[Increment 44](docs/RUST-INCREMENT-44.md) adds SQLite file/sidecar safety and
individual mount checks, preserving existing state on refusal and normal WAL
recovery after process death. [Increment 45](docs/RUST-INCREMENT-45.md)
qualifies selected actual hard-NFS worker shutdown, retained-copy deadlines and
original-state recovery; other lifecycle/deployment gates remain open.
[Increment 46](docs/RUST-INCREMENT-46.md) extends selected coordinator-death
qualification to blocked and terminating NFS workers. It exposes an ownership
gap during termination. [Increment 47](docs/RUST-INCREMENT-47.md) adds a persisted
local process-group lifetime check alongside the lock so kernel cleanup cannot
hide a surviving worker. Production NFS and deletion remain disabled.
[Increment 48](docs/RUST-INCREMENT-48.md) extends the selected death-phase fixture
to fresh bootstrap and accepted source-read workers; see its results and limits.
[Increment 49](docs/RUST-INCREMENT-49.md) adds selected enrolled/populated
bootstrap cases with original database/WAL, receipt and partial preservation;
read its actual results and limits. [Increment 50](docs/RUST-INCREMENT-50.md)
adds selected file-publication and manifest coordinator-death cases, requiring
original inode/attempt and manifest preservation through normal recovery.
[Increment 51](docs/RUST-INCREMENT-51.md) stabilizes the post-stop status test
within its existing bound, preserving runtime shutdown deadlines and failure
history. [Increment 52](docs/RUST-INCREMENT-52.md) adds selected both-NFS
coordinator-death/recovery cases on one controlled export, preserving original
state, custody and publication evidence. [Increment 53](docs/RUST-INCREMENT-53.md)
adds selected distinct-export/filesystem death cases on one controlled server.
[Increment 54](docs/RUST-INCREMENT-54.md) adds selected independently interrupted
source/destination endpoints with healthy-peer probes and original-state recovery.
[Increment 55](docs/RUST-INCREMENT-55.md) adds selected source failure midway
through copying with the destination usable. Remaining endpoint directions/phases,
remote settlement, durability and systemd/deployment gates stay open.
[Increment 56](docs/RUST-INCREMENT-56.md) adds selected enrolled startup recovery
with both endpoints on NFS, preserving original state and retained partials.
[Increment 57](docs/RUST-INCREMENT-57.md) qualifies selected manual/systemd
coordination in a private systemd 252 container with the mover inside pinned
SLES 12 SP5/glibc 2.22 userspace. This is local lifecycle evidence; native SLES
systemd, hard-NFS/systemd, installation/account policy and durability remain open.
Production NFS and source deletion remain disabled.
[Increment 58](docs/RUST-INCREMENT-58.md) records a blocked private-container
systemd-228 preflight: compiled directive checks are separate from the ten
unexecuted lifecycle cases and pending SLES-maintenance RPM qualification.
[Increment 59](docs/RUST-INCREMENT-59.md) passes ten local 228-equivalent
lifecycle records using the separately approved Podman-VM bootstrap. Read its actual
results and limits, the [step-by-step lab guide](docs/SYSTEMD-LIFECYCLE-LAB.md)
and [testing limitations](docs/TESTING-LIMITATIONS.md). Historical blocked and
failed reports remain separate; production NFS and source deletion stay off.

[Increment 60](docs/RUST-INCREMENT-60.md) passes four selected managed
stop/death cases with actual hard-NFS blocking, separate controlled exports,
local state and the 228-equivalent manager. Read actual outcomes and remaining
limits; production NFS and source deletion stay disabled.

**Rust redesign work:** E1–E5 compatibility experiments and the next-session
direction are on `feature/rust-transfer-coordinator`. Read
[the handoff](docs/RUST-DIRECTION.md) and [CONVERSATION.md](CONVERSATION.md).
Experiments are stopped. The first dependency-free [Rust core slice](rust/README.md)
has executable protocol tests and [SQLite acceptance](docs/RUST-INCREMENT-02.md).
It now has [protected local claims](docs/RUST-INCREMENT-03.md) and a
[local submission endpoint](docs/RUST-INCREMENT-04.md), plus a
[verified single-file transfer command](docs/RUST-INCREMENT-05.md) and
[automatic local delivery/manifests](docs/RUST-INCREMENT-06.md) and
[operator job status](docs/RUST-INCREMENT-07.md), plus
[audited delivery resume](docs/RUST-INCREMENT-08.md) and
[audited missing-file deadline reset](docs/RUST-INCREMENT-09.md).
Read-only [retention accounting](docs/RUST-INCREMENT-10.md) is also implemented.
Use the current [Rust operator guide](docs/RUST-OPERATOR-GUIDE.md) for status,
audited resume/missing reset, command replay and capacity/recovery triage.
[Source-space admission](docs/SOURCE-SPACE-ADMISSION-DESIGN.md) is configurable
and off by default; it gates new keys while preserving existing-job recovery.
See [increment 36](docs/RUST-INCREMENT-36.md) for implementation and
[increment 38](docs/RUST-INCREMENT-38.md) for bounded native NFS source-space
refusal, accepted-job recovery and unchanged-policy restoration evidence.
Background copy/verification now uses [supervised child workers](docs/RUST-INCREMENT-11.md).
[Claim and publication operations](docs/RUST-INCREMENT-12.md) now use children too.
[Recording sessions](docs/RUST-INCREMENT-13.md) isolate runtime destination opening,
allocation, manifest writing and custody checks.
[Hard-mount boundary checks](docs/RUST-INCREMENT-14.md) exposed source bootstrap
blocking during outages. [Startup isolation](docs/RUST-INCREMENT-15.md) now keeps
signal handling responsive while custody is pending.
The [retained NFS qualification build](docs/NFS-QUALIFICATION.md) exercises the
same worker code in an isolated fixture; production NFS remains disabled.
[Owned no-clobber fallback and diagnostics](docs/RUST-INCREMENT-17.md) resolve
the fixture's rename refusals and retain explicit interrupted-link recovery.
[Runtime qualification](docs/RUST-INCREMENT-18.md) now exercises selected Rust
worker outages, partial-copy recovery and custody after coordinator death.
The maintained [Rust scenario catalog](docs/RUST-SCENARIOS.md) explains producer,
consumer and operator situations addressed so far and tracks the remaining user
guides. Update it as each increment adds or changes behavior.
[Source-read and verification-read qualification](docs/RUST-INCREMENT-19.md)
also passes in both profiles with observed blocked readers and validated recovery.
[Claim/file link interruption](docs/RUST-INCREMENT-20.md) now preserves and
reconciles the exact two-name NFS intermediates in both profiles; see catalog
scenarios SC-049/050 for producer and consumer behavior.
[Longer outage qualification](docs/RUST-INCREMENT-21.md) adds three-minute blocked
claim/verification checks, same-ID retry/backpressure observations and live recovery.
See SC-051/052 and the increment evidence for the qualified scope.
[Root/ownership diagnostics](docs/RUST-INCREMENT-22.md) add separate-client and
missing-mount startup probes; [the binding/fencing design](docs/ROOT-OWNERSHIP-DESIGN.md)
defines the next implementation steps. Diagnostic completion is not production approval.
[Source binding/enrollment](docs/RUST-INCREMENT-23.md) now requires explicit
source identity and a preprovisioned private marker, records strict pins in schema 8
and refuses changed bindings or populated unbound legacy state before readiness.
See its migration limits and provisioning instructions before using older configs.
Offline inspection and repair are deferred; prioritize remaining worker isolation
and controlled NFS qualification. Preserve [the repair design](docs/RETENTION-REPAIR-DESIGN.md).
Every build/test uses the zigbuild/SLES gate.
Registration/authentication is deferred while tested increments develop. The C++
implementation described below remains the reference, not the intended Rust architecture.

A durable background transfer coordinator for large simulation recordings, written in
**C++11** with a **REST** control plane.

Simulation orchestration on six Linux hosts records ~100 GB per run to a local NFS mount.
Moving that data synchronously stalls the hosts and delays the next run. Background File
Mover accepts a submitted recording set, returns a durable acknowledgement immediately,
and then moves the data in the background around a single atomic commit point: everything
before it is disposable, everything after it is idempotent. A source file is never
deleted until its destination is durably in place, so any failure retains the source.

It targets **SLES 12 SP5** — GCC 4.8.5, glibc 2.22 — and RHEL 9. That constraint shapes
the codebase more than any other decision; see `docs/LEGACY-PLATFORM-COST.md`.

## Highlights

- Runs under **systemd**, controlled over a hand-rolled HTTP/1.1 subset (ADR-0012).
- **SQLite** (WAL, `synchronous=FULL`) holds authoritative durable job state (ADR-0010).
- Filesystem work is **fd-relative** (`openat`/`renameat2`/`fstatat`), not path-based,
  so a racing adversary cannot swap a path between check and use.
- Every parser on untrusted input is fuzzed continuously with a committed regression
  corpus, and built to a written standard (`docs/HAND-ROLLED-COMPONENTS.md`).
- Fourteen independent CI gates, including a **GCC 4.8.5 fidelity tier** that runs the
  full test suite rather than just compiling.
- Full **L1/L2/L3 requirement traceability** (`docs/TRACE-MATRIX.md`), generated from
  both pytest markers and Catch2 tags.

## Status

**Under active construction — not yet shippable.** The JSON codec, configuration loader,
job state machine, rename template engine, and HTTP request parser are delivered and
tested. The durable store, job manager, transfer engine, socket server, and dashboard are
not yet built. In v1.0.0 scope, **48 of 226 requirements (21.2%)** carry test evidence.
`docs/TRACE-MATRIX.md` carries the live figure; `docs/ROADMAP.md` opens with where the
work stands and the **C1–C9** plan to v1.0.0.

The **Python implementation** (v0.4.2) was removed from this branch ahead of v1.0.0. It
remains on `main` and at the `v0.4.2` tag, and is still the version to deploy today.
v1.0.0 is deliberately **narrower** than v0.4.2 — claim semantics, integrity
verification, conservative deletion, and recovery-by-resumption are deferred to v1.1 and
retained verbatim in `docs/L1-REQ.md`.

## Quickstart (development)

```
cd cpp
make check                # build and run the suite, -Werror
make check-ci             # every gate, in a container, as CI runs them
```

See `CONTRIBUTING.md` for the full toolchain setup. The canonical checkout lives inside
WSL on a Linux-native filesystem — building under `/mnt/c` is unreliable and slow, and
`CLAUDE.md` records the measurements.

## Documentation

- `cpp/README.md` — build commands, CI tiers, design rules, REST API shape.
- `docs/L1-REQ.md` / `docs/L2-REQ.md` / `docs/L3-REQ.md` — requirements.
- `docs/TRACE-MATRIX.md` — generated forward trace, and the live coverage figure.
- `docs/CYBERSECURITY.md` — threat model and the v1.0.0 scope boundary.
- `docs/adr/` — architecture decision records.
- `docs/MAINTAINER-GUIDE.md` — dev setup and contribution workflows.

Documents describing the retired Python implementation are kept as the source material
for the rewrite and each opens with a banner saying so.

## License

Apache-2.0 — see `LICENSE`.

Increment 65 adds server-completed publication LINK reply-loss qualification; see [results](docs/RUST-INCREMENT-65.md). Keep production NFS/deletion disabled and maintain SC-099, the step-by-step lab and remaining reply-loss/durability limits.

Increment 66 adds source-claim LINK/REMOVE success-reply-loss qualification; see [results](docs/RUST-INCREMENT-66.md). Keep production NFS/source deletion disabled, preserve SC-100 and the simple same-ID JSON-until-202 producer workflow, and maintain the step-by-step source lab and testing limits.

Increment 67 records synchronization RPC capability and actual worker observations; see [results](docs/RUST-INCREMENT-67.md) and [lab](docs/NFS-SYNC-LAB.md). No COMMIT/mover sync-loss support follows from buffered OS controls. Preserve SC-101/102, GNU/glibc-2.22 checks and production NFS/source deletion disabled.

[Increment 69](docs/RUST-INCREMENT-69.md) adds supervised Rust mount-profile
enforcement alongside existing descriptor/enrollment custody. NFS qualification
bindings require explicit nfs_mount declarations; local bindings remain unchanged.
The [extended lab](docs/NFS-MOUNT-PROFILE-LAB.md#supervised-rust-authorization-extension)
checks real worker refusal/restoration/replay without enabling production NFS or
source deletion. Matching mount observations still prove neither continuity nor
remote settlement; remaining buffered interruption/synchronization gates stay open.

[Increment 70](docs/RUST-INCREMENT-70.md) adds selected buffered same-share transfer
and process-crash recovery qualification; the [lab](docs/NFS-SAME-SHARE-LAB.md)
documents exact steps and limits. Production NFS and source deletion remain
disabled; the remaining fault/synchronization and first-release gates stay open.

[Increment 71](docs/RUST-INCREMENT-71.md) adds buffered copy/verification
interruption and recovery qualification on same/separate shares; see the
[step-by-step lab](docs/NFS-BUFFERED-READS-LAB.md) for actual blocked-read proof,
original-state recovery and limits. Production NFS and source deletion remain
disabled.
