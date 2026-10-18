# Controlled destination-outage startup and recovery lab

This is a qualification procedure for [increment 62](RUST-INCREMENT-62.md), not a
production deployment guide. Keep production NFS and source deletion disabled.
The mover, workers and controllers use exact GNU/glibc-2.22 artifacts in pinned
SLES 12 SP5 userspace. The host kernel and CPU are those of the Podman VM.
Systemd is not involved in these cases; retain its separate
[lifecycle lab](SYSTEMD-LIFECYCLE-LAB.md) and [testing limits](TESTING-LIMITATIONS.md).

## 1. Check the controlled infrastructure

Use the repository root, Python 3.11+ and the existing rootful Podman VM/connection.
Do not run this against production mounts, NAS administration or real recordings.

```powershell
$env:CONTAINER_CONNECTION = 'podman-machine-default-root'
podman ps -a --format '{{.Names}} {{.Status}}'
podman image inspect localhost/background-file-mover-e2-nfs --format '{{.Id}}'
wsl -d podman-machine-default -u root -- ls -d /sys/module/nfs /sys/module/nfsd
```

The retained cached server image is
`90884509240d53671958810ac7ae1971b7cdfffda3d4135ce42cc39bf0bc3e69` in the
reference lab. Its source recipe is
[Nfs.Containerfile](../experiments/e2-rustix/Nfs.Containerfile) and
[nfs-server.sh](../experiments/e2-rustix/nfs-server.sh). If provisioning is needed,
follow [the fixture guide](NFS-TEST-FIXTURE.md), record changed image/package
identity and obtain appropriate VM-only authorization. Do not automatically
rerun E2/E6, load modules on a production host or change VM boot settings.
An unavailable backend is a blocker, not a passing test.

## 2. Run both mandatory compatibility gates

```powershell
python scripts/check-rust-sles.py
if ($LASTEXITCODE -ne 0) { throw 'Production SLES gate failed' }
python scripts/check-rust-sles.py --qualification
if ($LASTEXITCODE -ne 0) { throw 'Qualification SLES gate failed' }
```

Record the two `rust/validation/...` directories printed by the commands as
`$ProductionGate` and `$QualificationGate`. Require final PASSED reports and
successful cleanup. These builds use pinned cargo-zigbuild/toolchain and locked
offline application sources, ELF loader/library/symbol audits and exact target
test execution. Read [the SLES gate](RUST-SLES-GATE.md) for provisioning and scope.
Host-only cargo tests or a version label cannot replace these checks.

## 3. Run the finite destination-startup matrix

```powershell
python scripts/check-nfs-boundaries.py $ProductionGate --qualification-gate $QualificationGate --isolated-startup --coordinator-death --death-scope destination-startup
if ($LASTEXITCODE -ne 0) { throw 'Destination-startup qualification failed; inspect the report and retained resources' }
```

The driver validates the current 61-file Rust inventory/source archives and exact
service hashes against both passing gate reports. It creates an owned internal
network without published ports, a server volume and controlled source NFS server,
and a pinned SLES client with only the fixture's mount administration capability.
It records the kernel, image/packages and mounts. Application processes run as
UID/GID 1000, without effective capabilities and with no-new-privileges.

Six normal transfer baselines run first. The driver then creates a separate
destination server/volume/network namespace/IP. Source and destination exports
are separate 128 MiB/4096-inode tmpfs filesystems, mounted with
`vers=4.1,proto=tcp,port=2049,hard,timeo=10,retrans=1,noac`. Require distinct
namespace/IP/device/mount identities and actual NFS magic. State/SQLite remains
local. These disposable export permissions are not production provisioning rules.

## 4. Prepare empty and populated original state

Each debug/release profile has enrolled-empty and populated cases, each tested
at blocked coordinator death and after a two-second local stop. Paths are unique
owned fixture descendants, with controller socket names below the Unix path limit.

Initialize source enrollment and destination binding on healthy endpoints. For
populated state, submit the nested 2 MiB plus 17 byte file and require 202/Claimed;
reuse its producer path and pause only the seed worker after its first 1 MiB copy.
Capture the accepted job, retained WAL and partial inode/size/hash. Kill and
confirm seed coordinator exit before terminating/confirming its paused worker.
Require exactly the original staging allocation. Capture local files/database
inode, source/enrollment evidence and destination binding/partial separately.
No observer opens SQLite to inspect it.

## 5. Start with only the destination unavailable

Stop NFSD threads only in the owned destination server. Require destination
threads zero, source threads two and bounded fresh source write/read/metadata.
Launch the original configuration/state without a runtime pause or SIGSTOP.

Source bootstrap/enrollment can finish, so health 200 and Running are expected.
In the empty case, first verify idle readiness without a destination worker;
then submit, require actual claimed source custody and 202, and reuse the path.
The populated case replays its original accepted key. In both cases require
Claimed status, no false Committed, and identical-key replay returning the same
job/202 despite the destination outage. Readiness and custody do not mean delivery.

Observe exactly one real D-state internal delivery worker through local control
and procfs. Record command, wait channel, UID/GID/capabilities, epoch and every
known coordinator/worker thread. Require bounded health/job/local status while
the worker is blocked and a usable source. Never stat/hash the unavailable
destination through fixture observers. Record SQLite/WAL snapshots as evidence,
without requiring unchanged bytes after legitimate store open/acceptance/scheduling.

## 6. Qualify death, stop and exclusion

For blocked death, kill only the coordinator PID. For following-stop, invoke the
same-user controller with the loaded two-second application wait and distinguish
prompt Stopped/0 from ShutdownIncomplete/2 and a live worker. Kill the coordinator
only if it remains alive in the incomplete case. Keep runtime deadlines unchanged.

A surviving D worker must retain the original epoch and OwnerUnavailable/2
through three bracketed raw-flock/local-status observations. A free raw lock
does not authorize replacement. Only after proving retained logical ownership,
probe service on an alternate port, initialization and single-transfer commands;
all must refuse at the local guard. Confirm source health/custody separately.
Prompt clean exit is distinct evidence and cannot count as a retained-orphan test.

## 7. Restore and recover original state

Restore the controlled servers before attempting recovery or teardown. Confirm
all threads of the known old coordinator/worker exited and local status is
NoActiveOwner. Preserve database inode, source custody/receipt and producer-reused
path. Inspect destination only now; require no premature final payload/manifest
and exact preservation of the populated old partial.

Restart the original configuration/database without initialization/re-enrollment.
Require Committed with attempt 1 for newly accepted empty-state cases, attempt 2
for populated cases, original source/database/binding identity, unchanged old
partial, correct payload/manifest hashes, nested paths, retained source and cleanup
false. Stop the recovered service and require final NoActiveOwner. Local exit is
not proof of remote RPC settlement; this finite operation still requires owned
receipt/content reconciliation and does not authorize arbitrary uncertain replay.

## 8. Verify regressions and teardown

The same invocation retains twelve NFS-state-parent refusals, 184 state-file
refusals across fourteen preserved fixtures and the existing OS/inherited-lock/
isolated-source-startup checks. The new destination matrix does not replace them.

The driver restores servers, terminates/reaps only owned tasks, normally unmounts
all client shares, then removes owned containers, volumes and network. Any
unconfirmed restore/exit/unmount/cleanup fails the run and retains resources
listed in `recovery_resources`; inspect those rather than force-unmounting or
removing an unavailable server. Preserve failing reports alongside later fixes.

```powershell
podman ps -a --format '{{.Names}} {{.Status}}'
podman volume ls --format '{{.Name}}'
podman network ls --format '{{.Name}}'
```

Require no fixture containers/networks/volumes. Existing Rust caches/default
network and cached images are intentional. No systemd/cgroup bootstrap or module
change is part of this procedure. Audit exact driver/source/artifact hashes and
read the actual outcomes in increment 62. Two virtual servers on one kernel,
small files and NFSD-thread outages do not establish physical NAS independence,
disk/power durability, exact in-flight RPC settlement, old-kernel/CPU support or
full production deployment. All eight first-release gates remain open.

## Recorded increment-62 result

All eight selected records pass: four coordinator deaths leave D-state orphans
that retain ownership and refuse twelve competing effect commands in total;
four short-stop records exit promptly before restoration/coordinator kill.
No surviving terminating orphan is observed here. Health remains 200/Running,
new empty-state custody and claimed-job replay return 202, and status stays
Claimed until normal original-state recovery. Empty cases commit attempt 1;
populated cases commit attempt 2 while preserving the old partial exactly.

The six normal baselines, twelve state-parent refusals, 184 state-file refusals
and fourteen fixture-preservation checks, plus retained OS/startup checks, pass.
State-file refusal maximum is 1.219 seconds; prompt stops take 1.047–1.172 seconds
with the fixture wait 2. Independent inventory finds no fixture containers,
networks or volumes. Only the existing Rust caches/default network and cached
images remain. See [increment 62](RUST-INCREMENT-62.md) and its raw evidence for
exact inputs, artifact/driver hashes, every case and the remaining limits.
