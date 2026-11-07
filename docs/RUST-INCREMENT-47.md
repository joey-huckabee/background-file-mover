# Rust increment 47: retain ownership through actual worker exit

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Problem and fix

[Increment 46](RUST-INCREMENT-46.md) found terminating verification workers in
kernel D state after coordinator death while their local flock was already free.
File-descriptor lifetime cannot by itself prove actual process exit.

Keep the existing persistent local `instance.lock` and add a protected local
`workers.json` epoch. Before any of the three worker launch paths spawns a child,
establish the coordinator's own process group and atomically publish/fsync its
boot ID, PID-namespace identity, group ID, coordinator start ticks and guard
identity. Workers inherit the group and validate that membership with the existing
explicit guard handoff before assignment. All six worker modes are covered by
those launch paths. The private descriptor-prefix version remains 1; matching
binaries are required, with no mixed-version or hot-upgrade support claim.

A new start first acquires the normal flock, then refuses before SQLite/source
access if the saved group still has a live process or thread. Status/stop use the
same logical ownership observation: a physically free flock with a live recorded
group is still Held, and an absent controller yields OwnerUnavailable/exit 2.
This is retained exclusion through process membership, not an assertion that the
kernel keeps the original flock open. No extra executable, helper process or
package is introduced. Process groups are identification/exclusion evidence here;
the fix does not send group-wide signals or kill an orphan from a new controller.

Group membership survives coordinator death and file-table teardown. Treat only
terminal Z/X/x thread states as exited; a zombie group leader alone is not enough
if another thread remains live. Check current boot and PID namespace, bound the
scan to 200 ms/16384 entries and bound stat/JSON reads. Inaccessible/unknown scan
observations retain ownership; invalid evidence refuses rather than declaring
NoActiveOwner. Namespace changes on the same boot refuse. A reboot ends the old
kernel tasks but is not NAS settlement proof. Reused group IDs conservatively
block while a current group exists; no PID-only kill/adoption policy is added.

Both epoch names (`workers.json`, temporary `workers.next`) must be owned 0600,
regular, single-link and local, with the original guard identity. Individual NFS
mounts refuse before candidate-path access. Publish uses a private temporary file,
file sync, atomic local rename and directory sync before spawning. A validated
abandoned temporary file can be replaced only after the published old epoch has
no live members; a partial/corrupt published record is never silently repaired.
Keep the original state directory protected and preserve all ownership files.

## Supervision and recovery

The coordinator still owns worker assignment, cancellation requests and reaping.
Workers still reject bad assignments, lost channels and unrecoverable errors.
Existing stop/timeouts attempt child termination and wait for confirmed exit.
A pending SIGKILL cannot make a blocked NFS syscall reliably cancellable, and a
worker cannot execute a self-timeout while stuck in the kernel. No new automatic
kill/replacement, idle timeout, retry classification, review reset or deletion
policy is introduced. No arbitrary process is killed based on a saved PID.

After storage restoration and confirmed old exit, normal same-state startup
replaces the inactive epoch and reconciles owned job evidence. The record is not
a completion receipt, remote fence or proof that delayed NAS RPC/writeback ended.
Preserve 3N integrity, original-source custody, private partials, producer-reused
paths and conservative unresolved-effect refusal. Production NFS and source
deletion remain disabled; registration and offline repair remain deferred.
The roadmap retains future worker-health/stall and lost-coordinator diagnostics
beyond existing limits, without promising that a timer can cancel kernel I/O.

## Tests and qualification

New local tests cover a live unguarded child refusing reacquisition, strict unsafe/
corrupt record refusal without database creation, interrupted temporary publication
and process-state parsing. Existing direct-worker fixtures now prepare the group
before spawn. The long-lived test harness retires only its own synthetic epoch
after guard reacquisition proves all other group members exited; it never clears
a real service epoch or adds a production repair operation.

The retained coordinator-death matrix requires logical ownership/status plus
actual competitor refusal while orphan D state is bracketed around observations.
It records physical flock closure separately. A passing matrix must observe that
original counterexample in both profiles: raw lock free, worker still D, logical
ownership retained, no competing effect command admitted. All cases restore NFS
and confirm old exit before original-state recovery. Extend actual NFS-file
admission to both new names; retain normal-transfer and startup/OS regressions.

The matrix has twelve core cases and at most three additional terminating-
verification repetitions per profile (eighteen cases maximum) to observe the
original kernel-exit condition. Prompt exits never satisfy closed-guard coverage.

The first fixed-code fixture run, `nfs-20261017T164541Z-f88063e6`, is retained in
[initial evidence](RUST-NFS-OWNERSHIP-EXIT-INITIAL-EVIDENCE.json). All twelve worker
cases preserved ownership and recovered safely, but none observed physical guard
closure, so that run did not qualify the original counterexample. Its expanded
state fixture also failed an incorrect precondition: an epoch without its guard
correctly refused before the intended foreign-owner check. The fixture now supplies
the valid companion guard and preserves both names. Move epoch inspection before
submission to retain the original outage/termination timing; use bounded repeats
without weakening pass criteria. No Rust change followed the passing SLES gates.

Final fixture `nfs-20261017T171335Z-f7f5c7e2` passed; see the
[complete lifetime evidence](RUST-NFS-OWNERSHIP-EXIT-EVIDENCE.json). Its thirteen
cases comprise twelve core cases plus one release terminating-verification repeat:
six blocked orphans, four terminating orphans and three prompt exits. Both
debug and release actually observed a terminating verification worker still D
with the raw flock free, while the local epoch retained logical ownership. All
three bracketed samples per orphan returned OwnerUnavailable/exit 2; no ownership
loss occurred. Thirty service/initialize/transfer competitors refused, maximum
1.062 seconds; sampled orphan status took at most 1.000 seconds.

All thirteen cases recovered to Committed only after NFS restoration and confirmed
old exit, preserving original state, claimed source and producer-reused paths.
Interrupted copies retained the old partial and used attempt 2; interrupted
verification retained attempt 1. Destination SHA-256/manifest checks passed. The
old epoch stayed unchanged until old exit; normal recovery replaced it with the
new coordinator group under the same boot, namespace and guard identity.

Retained regressions passed six normal NFS transfers, twelve mounted-NFS state-
parent refusals and all 184 file-owner/mount/control refusals across fourteen
fixtures (maximum 0.984 seconds), with bytes/identity/permissions preserved.
Blocked bootstrap local status completed in 0.891 seconds; SIGTERM confirmed its
child exit before restoration, without database creation or HTTP readiness.
OS inherited-lock/interruption and stable-root restoration checks passed. Exact
driver hashes match current scripts. Cleanup reported no errors; independent
inspection found no containers or fixture volumes/networks, only the two existing
toolchain/cache volumes and default network.

## Compatibility and interface scope

The production gate `20261017T162146Z-b28d902b` passed 204 tests in each profile,
20 executable ELF audits and six audit negative controls. Its complete 61-file
Rust snapshot and all artifact hashes match current sources; cleanup succeeded.
The external graph remains 42 packages with maximum GLIBC_2.18 under target
GNU/glibc 2.22 and the standard Linux loader.
Qualification `20261017T162159Z-32bce9a2-nfs-qualification` also passed: 205 tests
per profile, 20 audits, six negative controls, unchanged 42 packages and maximum
GLIBC_2.18. Its complete 61-file archive and artifact hashes match current inputs;
cleanup succeeded. Both gates use the pinned SLES 12 SP5 userspace and
cargo-zigbuild; no host-only Cargo validation is substituted. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

SQLite schema 11, version-3 bindings, source enrollment/manifest formats and the
version-1 private guard/control protocols remain unchanged. The new local epoch
format has its own strict version 1; no new crate or Cargo feature is introduced.
The process-group change needs no NAS or host-admin access. Actual-version
systemd and manual job-control integration remain part of later deployment gates.

## Remaining obligations

Keep the increment 46 failed evidence as history. A passing selected regression
does not close all SH-04 or FR-03/05 obligations: bootstrap/source-read/publication/
manifest death phases, actual systemd/account/group policy, same/separate shares,
late RPC reconciliation, NAS reboot/reclaim/durability and old-kernel/CPU behavior
remain unqualified. No cross-host operation, alternate-state takeover or hostile
same-UID/privileged mutation is supported by this cooperative single-host profile.


Design references: [Linux process-group inheritance](https://www.man7.org/linux/man-pages/man7/credentials.7.html)
and [kernel process state/group/start fields](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html).
The implementation uses the already-qualified Rustix process APIs; these references
explain the OS model, while the saved test evidence determines qualified scope.
