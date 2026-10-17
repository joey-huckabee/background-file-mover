# Rust increment 45: hard-NFS worker shutdown qualification

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Purpose and scope

Exercise the existing local stop/status controller while a real claim, copy or
verification worker is blocked in the kernel on hard-mounted NFS. Keep production
NFS, deletion, remote ingress, registration, repair and takeover disabled/deferred.
This increment extends the retained fixture, not the NFS client implementation.
The host kernel still implements NFS.

The opt-in --shutdown matrix uses existing qualification rendezvous only to select
the operation. After stopping the server, it releases the rendezvous and requires
an actual D-state child, one assigned worker and local Running status before
requesting shutdown. Verification additionally requires the read loop's local
completion marker to remain absent. No stopped process or userspace pause is
substituted for kernel blocking.

Claim cases use NFS source/local destination. Copy and verification cases use
local source/NFS destination. They share one controlled export and one client;
this does not qualify shutdown with both endpoints on NFS or on separate shares.

Three worker situations x short two-second/default-omitted 60-second setting x
both debug/release profiles produce 12 cases. For each, local competitors using
the same state must refuse before SQLite/source access. Stop/status observations
record the live instance, budget, child state and time. Repeated stop plus SIGTERM
and an alternate next-start config with wait=3600 must not extend a live drain.
The alternate config is fixture-only, uses the same guarded state and a free port;
it does not authorize production alternate-state starts.

Kernel-assisted prompt exit and incomplete drain with a retained kernel-blocked
worker are distinct outcomes. Only an actually observed retained child beyond
the deadline can qualify that SH-07 branch. A prompt exit does not prove arbitrary
NFS syscalls cancellable. An incomplete exit race also does not prove that branch.

The fixture always restores NFS and confirms old process/worker exit before
starting original-state recovery, even if the local guard becomes free sooner.
It checks same-key replay, original private source, producer-reused paths, final
SHA-256/manifest, retained copy partials and unchanged retry/review behavior.
Neither guard release nor a successful local stop is NAS settlement proof.

## Evidence

[Full fixture evidence](RUST-NFS-SHUTDOWN-EVIDENCE.json): run
`nfs-20261017T140003Z-a5a59522`, **PASSED**, no cleanup errors.
All 12 selected cases passed. Five retained an actual D-state worker after the
first deadline: all four copy cases and release verification with default 60.
Seven exited promptly; prompt claim/read termination is an observed outcome,
not a general cancellation guarantee. No incomplete-exit-race case was observed.

| Profile | Operation selector | Wait seconds | Local stop outcome | Observed seconds |
| --- | --- | ---: | --- | ---: |
| debug | claim_apply | 2 | Stopped; prompt exit | 4.672 |
| debug | claim_apply | 60 | Stopped; prompt exit | 2.766 |
| debug | copy_chunk | 2 | Incomplete; worker retained | 3.766 |
| debug | copy_chunk | 60 | Incomplete; worker retained | 62.890 |
| debug | verify_read | 2 | Stopped; prompt exit | 4.578 |
| debug | verify_read | 60 | Stopped; prompt exit | 4.578 |
| release | claim_apply | 2 | Stopped; prompt exit | 4.531 |
| release | claim_apply | 60 | Stopped; prompt exit | 4.578 |
| release | copy_chunk | 2 | Incomplete; worker retained | 3.859 |
| release | copy_chunk | 60 | Incomplete; worker retained | 62.797 |
| release | verify_read | 2 | Stopped; prompt exit | 5.094 |
| release | verify_read | 60 | Incomplete; worker retained | 64.344 |

Times include host/container invocation and status polling (up to five-second
sampling for the default budget), not just the daemon's internal timer. Every
retained case remained blocked through its configured deadline; observed stop
completion stayed below budget plus eight seconds. Independent local status
completed within 1.250 seconds across these 12 cases. All 51 competing effect
commands refused: 36 while initially blocked and 15 after incomplete deadlines.
Repeated stop/SIGTERM and next-start wait=3600 preserved the active budget.

All 12 original-state recoveries reached Committed with matching private-source,
final-file and manifest SHA-256. Interrupted claims did not falsely acknowledge
release. Producer-reused paths survived, source cleanup stayed false, interrupted
copies used attempt 2 while retaining attempt-1 partials, and verification resumed
attempt 1. Root identities stayed stable. The fixture restored storage and
confirmed old process exit before every recovery; no SQL edits or ownership
bypass were used.

Retained regressions also passed: six normal NFS transfer/lifecycle cases,
12 NFS-state-parent refusals, 120 SQLite state-layout refusals across ten fixtures
with original bytes/identities/permissions preserved, inherited OS lock,
interrupted startup and restored metadata/lock checks. All fixture resources
were cleaned up.

The client used hard NFSv4.1 with noac against the controlled container server,
pinned SLES 12 SP5 userspace and WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`. This is not an old-SLES-kernel or physical
NetApp/Isilon durability test.

## Compatibility and retained capability

No Rust source, dependency, feature, schema, binding or worker/control wire format
is changed. The driver rejects stale Rust artifacts by comparing the complete
source archive and inventory with current inputs. It uses the exact existing
passing cargo-zigbuild GNU/glibc-2.22 gates, ELF-audited binaries and hash-checked
execution in pinned SLES 12 SP5 userspace. No host-only Rust test/build is used.

Reused production gate `20261017T111519Z-1ecdab26` passed 200 debug and
200 release tests; qualification gate
`20261017T111519Z-8fa9a462-nfs-qualification` passed 201 debug and 201 release.
Each audited 20 executables, passed six ELF negative controls and resolved
42 external packages. Highest required GLIBC version was 2.18, below the 2.22
ceiling. Both complete 60-file Rust input snapshots and artifact hashes still
match; these are existing passing builds, not newly run Cargo suites. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

The Python harness gains --shutdown and an explicitly selected runtime path;
existing full runtime and three-minute matrices remain independently selectable.
No new package experiment starts. Ordinary production code gains no test controls.
The setup uses the existing disposable NFS container, same unprivileged account,
private local state and protected working areas.

The handoff's three legacy ANSI dashes are repaired to valid UTF-8 without
changing their meaning. Maintain stable SC-093 and the DOC-03/04/05 backlog.

## Remaining obligations

Actual systemd/account control, old-kernel/CPU behavior, physical NAS durability,
server recovery/grace/reclaim, genuinely delayed RPC/writeback reconciliation,
same/separate-share deployment, broader death/sync boundaries, and any unobserved
kernel-held/default-deadline branch remain open. Do not generalize one modern
shared-kernel fixture into production NFS approval. Keep the NF/SH mapping and
all first-release gates truthful.
