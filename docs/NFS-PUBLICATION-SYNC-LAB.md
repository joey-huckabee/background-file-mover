# Controlled publication and synchronization interruption lab

This procedure implements the finite matrix in [increment 63](RUST-INCREMENT-63.md).
Production NFS and source deletion remain disabled. It is a qualification lab,
not a production deployment guide. See [testing limitations](TESTING-LIMITATIONS.md).

## 1. Verify the retained infrastructure

From the repository root, use Python 3.11+ and the rootful Podman connection:

```powershell
$env:CONTAINER_CONNECTION = 'podman-machine-default-root'
podman ps -a --format '{{.Names}} {{.Status}}'
podman image inspect localhost/background-file-mover-e2-nfs --format '{{.Id}}'
wsl -d podman-machine-default -u root -- ls -d /sys/module/nfs /sys/module/nfsd
```

Use the existing cached server and preloaded VM modules. Provisioning instructions
and the retained server recipe are in [the fixture guide](NFS-TEST-FIXTURE.md).
No real SLES installation, production NAS access, systemd bootstrap or VM boot
change is required. Record the actual image/kernel/package identities; unavailable
infrastructure must fail qualification rather than skip cases as passing.

## 2. Produce and audit both exact configurations

```powershell
python scripts/check-rust-sles.py
if ($LASTEXITCODE -ne 0) { throw 'Production SLES gate failed' }
python scripts/check-rust-sles.py --qualification
if ($LASTEXITCODE -ne 0) { throw 'Qualification SLES gate failed' }
```

Save the printed run directories as `$ProductionGate` and `$QualificationGate`.
Require PASSED reports and successful cleanup. These commands use locked sources,
cargo-zigbuild's GNU/glibc-2.22 target, ELF interpreter/import/library audits and
exact debug/release tests in pinned SLES 12 SP5 userspace. Host cargo tests cannot
replace [the mandatory gate](RUST-SLES-GATE.md).

## 3. Run the finite matrix

```powershell
python scripts/check-nfs-boundaries.py $ProductionGate --qualification-gate $QualificationGate --isolated-startup --coordinator-death --death-scope publication-sync
if ($LASTEXITCODE -ne 0) { throw 'Publication qualification failed; inspect report and recovery resources' }
```

The driver verifies current Rust inventory/archive bytes and artifact hashes,
then creates an owned internal network, source/destination servers and volumes,
and a pinned SLES client. There are no published ports. Both private roots are
on separate NFSv4.1 endpoints, with separate network namespaces/IPs and distinct
128 MiB/4096-inode tmpfs exports. Record mount identities and require hard TCP
NFSv4.1 mounts, distinct devices and local state/SQLite/epoch/control files.

The client observer has SYS_ADMIN for mounts and SYS_PTRACE/DAC_READ_SEARCH for
reading `/proc/<worker>/syscall`. This is fixture authority, not mover authority.
Application processes run as UID/GID 1000 with no effective capabilities and
no-new-privileges. The two server containers and client share the modern VM kernel.

Six normal transfer baselines run first. Twelve interruption cases then run:
debug/release times file/manifest publication times these three points:

| Point | State before interruption | Evidence required |
|---|---|---|
| `file_link_sync`, `manifest_link_sync` | Link returned; next open/file/directory sync has not run | Two owned names, identical inode/hash and link count two; local pause remains armed |
| `file_unlink`, `manifest_unlink` | New link synchronized and both names rechecked; next call is unlinkat | Release into destination outage; require D state, x86_64 syscall 263, staging-parent descriptor and flags zero |
| `file_unlink_sync`, `manifest_unlink_sync` | Unlink returned; old-parent sync has not run | Only final name remains, original inode/hash and link count one; local pause remains armed |

## 4. Prepare and interrupt one owned recording

Each case uses unique private directories and original local database. Enroll on
healthy storage, start with one selected qualification pause and submit one nested
2 MiB plus 17 byte recording. Require custody/202, then write a different recording
at the producer's original path. Await the actual supervised delivery child and
capture source custody, enrollment receipt, database identity and destination
aliases/inode/link count/hash. File cases remain PublishIntent without a manifest;
manifest cases have a Published payload but the job remains Claimed.

Stop only destination NFSD. Require destination thread count zero, source count
two and bounded fresh source write/read/metadata. For unlink points, release
the pause and observe the actual blocked syscall. For synchronization points,
leave the pause armed: these intentionally crash before sync, not within fsync.
Require health, Claimed status and identical-ID custody replay/202, with exactly
one assigned child and no false SQLite commitment.

## 5. Retain exclusion and recover original state

Kill only the coordinator PID. At blocked unlink points, require a surviving D
worker, unchanged local epoch, bounded OwnerUnavailable/2 status and refusal of
an alternate-port service contender at the local ownership guard. Kill the known
old worker, restore servers and confirm exit of every known coordinator/worker
thread before replacement. A timeout, process-group leader zombie or free raw
lock alone does not prove storage settlement.

Inspect destination objects after restoration/old exit. The authorized unlink
may or may not have removed the staging alias; any surviving aliases must still
name the exact owned inode/content. Never interpret a syscall interruption as
proof that the remote operation had no effect. No orphan file-publication step
may create a completion manifest. Restart with the original database/configuration,
without re-enrollment or deleting allocations. Require Committed on attempt one,
original payload/publication inode/hash, one final name per object, no staging
aliases or second payload allocation, original source/database/enrollment and
producer-reused path preserved. Validate the nested completion manifest and
retained claimed source with cleanup disabled.

## 6. Run retained checks and clean up

The same command retains production NFS refusal and normal transfer baselines,
local-state parent/file refusal checks, inherited-lock/OS outage probes and
isolated source-bootstrap shutdown. Read final report status, every case and
cleanup errors; successful process exit alone is insufficient.

Cleanup restores NFSD before terminating/reaping hard-mount users. It normally
unmounts each owned mount before stopping servers and removing owned containers,
volumes and the internal network. No forced/lazy unmount is used. On cleanup
failure the report keeps recovery resource IDs; preserve those until safe cleanup.
Check final inventory:

```powershell
podman ps -a --format '{{.Names}} {{.Status}}'
podman volume ls --format '{{.Name}}'
podman network ls --format '{{.Name}}'
```

Shared toolchain/registry caches and pre-existing VM modules are retained.

## 7. Interpret the limits

An observed unlinkat syscall proves the client is inside that syscall, not a
specific on-wire RPC, server execution or remote settlement. Eight pre-sync
crashes demonstrate owned reconciliation with the live server's retained state;
they do not simulate disk cache loss, power failure or in-flight sync RPCs.
In-flight link/sync RPCs, server reboot/reclaim, old kernels/CPUs, physical NAS
isolation, actual mount/account/security policy, systemd and production scale
remain separate qualifications. No release gate closes from this matrix alone.

## Recorded execution

Run `nfs-20261018T174712Z-059936f1` passes all twelve cases: four observed client unlinkat
stalls and eight pre-sync crashes. Both mandatory gates and all retained checks
pass, with no cleanup errors. See [the increment report](RUST-INCREMENT-63.md)
and [raw evidence](RUST-NFS-PUBLICATION-SYNC-EVIDENCE.json) for exact provenance.

In all four unlink syscall cases the staging alias remains after old exit, and
leaders are already zombies at the post-KILL/pre-restoration sample. These are
not observations of accepted server-side unlink with lost replies or surviving
uncancellable post-KILL tasks. All known threads are confirmed exited before
recovery. Final independent inventory has no containers or fixture volumes or
networks; only the two shared build caches/default podman network remain.
