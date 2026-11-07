# Rust increment 46: coordinator death with blocked NFS workers

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Scope and acceptance

Extend the retained container fixture with `--coordinator-death`, independently
selected from `--runtime` and `--shutdown`. No Rust source, dependency, public
contract, schema, binding, worker wire format or retry/review policy changes.
Production NFS and source deletion remain disabled. Registration, repair,
cross-host replacement and production systemd operation remain deferred.

The finite matrix has 12 cases: debug/release, actual claim/copy/verification
workers and two death phases. Claim uses NFS source/local destination; copy and
verification use local source/NFS destination. One client and one controlled
export do not qualify both endpoints on NFS or separate-share deployments.

For every case, release the qualification rendezvous after stopping the NFS
server and require the assigned real child in kernel D state, bounded local
Running status and independent local guard contention. The rendezvous only
selects the operation; it is not the blocked-worker evidence.

- Blocked: SIGKILL only the coordinator PID, confirm its exit, then require the
  actual orphan to remain D with a contended guard through three observations.
- Terminating: request ordinary local stop with a short two-second budget. If
  stop returns ShutdownIncomplete with a D-state child, kill the still-live
  coordinator and require the same orphan/exclusion evidence. If the old daemon
  and worker exit promptly first, record that separately; this does not qualify
  coordinator death with a surviving terminating child.
- While an orphan retains ownership, independent local status must report bounded
  OwnerUnavailable/exit 2, and service, initialization and single-transfer
  competitors must refuse on the guard before SQLite or source bootstrap.
- Probe the local guard nonblockingly before starting competitors. Unexpected
  release with a live D-state child fails the case without starting a potentially
  conflicting replacement. Bracket each guard/status observation with child-state
  reads, repeat three times and retain the raw worker status. Known ownership-loss
  cases may complete safe restore/exit/recovery and remaining diagnostics, but
  remain failed; cleanup or unrelated failures still interrupt the matrix.
  No force, guard deletion, database edits or alternate state are used.
- Restore storage and confirm old worker exit before original-state recovery.
  Only then require free guard/NoActiveOwner, same-ID replay, Committed delivery,
  retained source, producer-reused path preservation and SHA-256/manifest matches.
  Interrupted copy retains its old partial and uses attempt 2; verification keeps
  attempt 1. Interrupted claim never falsely acknowledges path release.

These observations cover selected SH-04/08 and SC-092/093 behavior. A local
OwnerUnavailable result cannot identify or kill an orphan safely. A free guard
or process exit does not establish NAS RPC/writeback settlement (SC-094).

## Release-blocking finding

The [initial failed run](RUST-NFS-COORDINATOR-DEATH-INITIAL-EVIDENCE.json),
`nfs-20261017T145718Z-15712af3`, stopped at debug verification/terminating.
Ordinary stop returned ShutdownIncomplete/exit 2 with worker 1216 in D state.
Its pre-kill status showed pending SIGKILL and FDSize 0. After coordinator 1197
exited with code 137, a local probe acquired the guard although the preceding
worker observation was still D. The fixture started no competitors and cleaned
up without errors after restoring NFS.

This initial observation did not bracket the guard probe with another state read.
The diagnostic rerun strengthens that evidence and continues the finite matrix
without treating an observed ownership loss as success. Do not infer the exact
kernel close/syscall order solely from /proc status. Runtime ownership remains
based on the inherited flock description; no independent lifetime keeper has
been added. A qualified exclusion mechanism that survives worker kernel teardown
is the next implementation task; simply extending a timeout or checking whether
the local flock is free cannot repair an observed early release.

The stronger diagnostic rerun, `nfs-20261017T151430Z-61596339`, confirms this
failure in both debug and release verification termination. In each, all three
observations bracket successful local guard acquisition and NoActiveOwner/exit 0
with D-state reads before and after. This rules out worker exit between
measurements. No competing effect command is run after guard loss.
It is a local ownership-lifetime counterexample, not evidence of actual data loss
or a demonstrated overlapping writer. Preserve the failed result until fixed.

## Evidence

[Complete diagnostic evidence](RUST-NFS-COORDINATOR-DEATH-EVIDENCE.json):
`nfs-20261017T151430Z-61596339`, **FAILED**, exit 1, no cleanup errors.
All 12 cases completed: ten passed and two failed (debug/release verification
termination). Six blocked orphans and two terminating copy orphans retained
ownership; two claim-stop cases exited before the kill point. All 24 competing
effect commands in guarded-orphan cases refused. The two ownership-loss cases
started no competitors. Local worker-case status completed within 0.953 seconds;
the failed cases returned promptly but incorrectly for the required exclusion
contract. Bounded response time does not establish safe ownership.

| Profile | Operation selector | Death phase | Result |
| --- | --- | --- | --- |
| debug | claim_apply | blocked | PASS: blocked orphan retains guard |
| debug | claim_apply | terminating | PASS: prompt stop before kill |
| debug | copy_chunk | blocked | PASS: blocked orphan retains guard |
| debug | copy_chunk | terminating | PASS: terminating orphan retains guard |
| debug | verify_read | blocked | PASS: blocked orphan retains guard |
| debug | verify_read | terminating | FAIL: D-state orphan, guard free |
| release | claim_apply | blocked | PASS: blocked orphan retains guard |
| release | claim_apply | terminating | PASS: prompt stop before kill |
| release | copy_chunk | blocked | PASS: blocked orphan retains guard |
| release | copy_chunk | terminating | PASS: terminating orphan retains guard |
| release | verify_read | blocked | PASS: blocked orphan retains guard |
| release | verify_read | terminating | FAIL: D-state orphan, guard free |

All 12 cases reached Committed through original-state recovery after storage
restoration and confirmed old-worker exit, including the two failed ownership
cases. Private-source/final-file/manifest SHA-256 matched, source cleanup stayed
false, producer-reused paths and root identities survived. All four interrupted
copies used attempt 2 with old partials retained; all four verification cases
kept attempt 1. No overlapping replacement was attempted after a failed guard
observation, so this is not evidence of data corruption or demonstrated overlap.

Retained regressions passed: six normal NFS transfer/lifecycle cases, 12 NFS
state-directory refusals, 120 SQLite-file refusals across ten fixtures with original
bytes/identity/permissions preserved, inherited OS lock, isolated startup/local
status, signal interruption and restored metadata/lock checks. Fixture cleanup
removed its containers, mounts, volume and network without errors. The final
nonzero status is intentional and must remain until ownership qualification is
fixed; passing regressions do not clear it.

The controlled client mount was hard NFSv4.1/noac, one export/client, pinned SLES
12 SP5 userspace on WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`. No physical
NAS, old kernel, power-loss, server-reboot or actual systemd claim follows.

## Fresh SLES compatibility checks

Production `20261017T145042Z-b718db7b`: **PASSED**, exit 0, 200 debug and
200 release tests. Qualification `20261017T145053Z-11bb8adc-nfs-qualification`:
**PASSED**, exit 0, 201 debug and 201 release tests. Each audits 20 executables,
passes six ELF negative controls, formatting and Clippy with warnings denied,
and retains the same 42 external packages. Maximum required version is
GLIBC_2.18 under the GNU/glibc-2.22 ceiling and standard Linux loader.

The full 60-file source inventory/archive bytes and all artifact hashes match
current inputs. These are fresh mandatory cargo-zigbuild builds and exact target
tests in pinned SLES 12 SP5 userspace, unprivileged with eager relocation; no
host-only Cargo tests/builds were substituted. Both gate cleanups succeeded.
The entry point was Windows Python/Podman against the WSL2 Linux container engine.
See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

The first fixture used the previous passing gates with matching unchanged inputs;
the diagnostic rerun uses the fresh gates above. Compatibility passes do not
turn an ownership failure into supported behavior. No runtime dependency, feature,
schema, worker protocol, public API or Rust implementation was modified.

## Remaining obligations

Bootstrap, source-read, publication, manifest and synchronization death boundaries,
actual systemd process-group/restart/account behavior, actual mount/security and
same/separate-share deployments, delayed RPC reconciliation, server reboot/
reclaim, physical storage durability and the older SLES kernel/CPU remain outside
this selected matrix. Preserve all remaining SH/NF/FR obligations and the stable
95 scenario/six documentation identifiers. Production enablement requires the
release gates; no selected fixture result alone closes them.
