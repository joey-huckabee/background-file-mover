# Actual mover recovery across NFS server restart

This extension tests one finite payload-copy boundary using the infrastructure
proved in [the native capability lab](NFS-SERVER-RECOVERY-LAB.md). Keep production
NFS and post-delivery source deletion disabled. Registration remains deferred.

The [increment 88 extension](NFS-DISTINCT-RECOVERY-LAB.md) separately qualifies
the selected cases with two distinct retained tmpfs/client filesystems. Preserve
this original lab's observed shared-client-device scope and failed evidence.

## Acceptance and infrastructure

Run four native retained-FD controls first, then four actual mover cases:
debug/release × NFSD threads 2→0→2 or confirmed NFSD quiescence followed by
same-container SIGKILL/confirmed exit/start. The latter is a controlled restart,
not abrupt termination of a live kernel NFS server.
Both source and destination use buffered NMP-41B NFSv4.1 mounts on two exports
of one named volume, backing filesystem, server and kernel. SQLite and its
ownership/worker files remain local. This is neither independent NAS failure nor
a same-share/separate-share matrix. No ports are published.

In the passing acquisition, mount IDs 842/843 both have device `0:123`. Different
export paths/mount IDs do not prove different client filesystems. Source and
staging have different inodes on that shared client device; state uses local
device 96. The retained rejected audit initially assumed distinct devices.
Keep this shared-client-filesystem scope explicit; distinct filesystems and
independent shares remain unqualified by this lab.

Each service case uses the existing qualification-only `source_copy` rendezvous
after the first MiB of a 2 MiB + 17 byte file. Cache advice is only preparation;
accept an interruption only with an actual D-state `read(2)` on the claimed
source FD, requested length 1 MiB, and an absent read-completed marker. Keep the
coordinator alive. Require its health/status, one original assignment, competing
startup refusal, original state/custody and attempt-1 completion without restart.

## Step-by-step procedure

1. Use `feature/rust-transfer-coordinator`. Follow the inventory and cached-image
   prerequisites in the [native lab](NFS-SERVER-RECOVERY-LAB.md). Both Podman
   engines must have no unrelated containers; preserve their existing caches,
   anonymous volumes and network metadata. No real SLES installation is needed.
2. Run both required checks and retain their printed directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These are the only Rust build/test path: locked cargo-zigbuild GNU/glibc 2.22,
   exact debug/release target tests and ELF/loader/library checks in pinned SLES
   12 SP5 userspace. No host cargo test substitutes for them.
3. Freeze the acquisition inputs, then execute with the two passing gate paths:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The runner prints `rust/validation/server-mover-recovery-...`. It snapshots
   fourteen exact acquisition inputs before resource creation. It validates
   both source archives against all current Rust inputs and hashes the exact
   qualification executables copied into SLES. A prior matching-source gate may
   supply live artifacts while fresh checks run; the final audit must compare
   fresh shipping bytes and source archives to those actually used.
4. The runner creates an owned internal network, fixed backend private IP,
   named export volume, cached privileged kernel-NFS server, pinned SLES client,
   unprivileged relay, read-only volume reader, native Zig builder and bounded
   external ptrace observers. Exports use root_squash, sync and fixed fsids 68/69.
   The client mounts through the relay using hard,ac,async,vers=4.1,sec=sys,TCP.
   Native controls must pass before service cases begin. Probe/service/relay run
   as UID/GID 1000 with no active capabilities and NoNewPrivs; setup privileges
   are restricted to the disposable containers. Preserve actual mountinfo.

   The final `--mover` fixture retains default backend cgroups and records its
   complete HostConfig. An attempted `--cgroups disabled` backend did not make
   abrupt termination reliable and remains a failed acquisition. No VM cgroup
   policy was changed. Repeat native controls under the final exact sequence;
   do not infer its capability from the earlier abrupt-termination passes.
5. For each service case, provision private fixture markers once, initialize
   the source and retain local SQLite/config and source enrollment identities.
   Start the actual supervised service. Submit JSON and require 202/job 1 with
   confirmed path release; then write newer producer data at the reused path.
   At the source-copy pause, prove a 1 MiB staging file, retained claimed source,
   one assigned child, local worker epoch and Claimed/Intent status. Never read
   the claimed source through the NFS client after cache advice; observe its
   independent read-only backing volume instead.
6. Attach the existing external syscall observer to that child. Snapshot server
   identity and a fresh relay `checkpoint` before stopping the selected facility.
   For a container event, first stop NFSD and retain its observed zero threads
   with the original container PID/start identity. Then require
   `podman kill --signal KILL`, `podman wait`
   exit 137, Status=exited and PID=0 before starting the same container. A false
   Running flag alone does not prove exit. Preserve the independent source
   inode/size/hash while stopped. Release the local rendezvous into the actual
   blocked read; record `/proc/PID/syscall`, FD path, D state and worker security.
7. During the outage, require responsive health, unchanged Claimed status,
   unchanged local state/worker epoch, contended local guard and prompt contender
   refusal. Do not stat NFS paths during the outage. Record restoration time
   inside the relay's WSL clock domain. Restore the facility with its original
   IP/container/export volume, without remounting or replacing the worker.
8. Require attempt-1 Committed status from the same coordinator, actual old
   worker exit and successful traced synchronization calls. Verify retained
   claimed-source bytes, final payload digest, original staging inode, complete
   manifest, unchanged enrollment/local state and root identities. Stop cleanly,
   start using the original configuration/state, retry the same JSON and require
   the same committed job, stable manifest and untouched newer producer bytes.
9. Wait for the runner's actual exit. Cleanup restores the server before draining
   users, normally unmounts both NFS mounts, and removes only exact owned
   containers/volume/network. Never force/lazy-unmount. Preserve failed reports
   and sources before correcting them; a failed acquisition is not support.
10. Once both compatibility processes have exited successfully and all lab users
    are gone, capture both engines and run the independent audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-server-mover.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    It checks raw native and mover evidence, actual blocked reads, source/inode/
    manifest proof, exact source/archive/binary/ELF hashes, raw RPC redecoding,
    fifty deliberate proof corruptions and decoder regression tests. It retains
    compressed lossless acquisition evidence and exact verifier/build inputs in
    `RUST-NFS-SERVER-MOVER-{INPUT-,}EVIDENCE.json`, and updates both canonical
    SLES evidence files. Final inventory must match baseline volume metadata and
    network names and contain no containers in either engine.

## Testing limits and user meaning

This qualifies the selected source-read boundary with the live coordinator,
finite outage, small workload and two buffered exports on one server. It does
not qualify coordinator-death/replacement during restart, other claim/bootstrap/
verification/publication/sync phases, independent endpoints, fresh network
namespace, VM/NAS reboot, all lease/reclaim behavior, outstanding UNSTABLE data
loss, delayed-effect settlement, high load, physical storage or power durability.
Unknown RPC compounds remain retained and unknown; broader-window writes are
not attributed to a particular fsync or process without descriptor/handle proof.

Pinned SLES userspace shares the modern Podman/WSL kernel; this does not test an
original SLES kernel, vendor maintenance RPM/cgroup behavior or all CPU profiles.
The shortened mount retry settings are fixture settings, not production advice.
A local lock or timeout never authorizes uncertain-effect redispatch.

The recorder still submits/retries identical JSON until 202, then may reuse its
paths and has no monitoring duty. Consumers validate the complete manifest;
payload visibility alone does not establish recording commitment. All eight
release gates remain open. Maintain DOC-01–05; DOC-06 remains deferred.

## Retained acquisition failures and rescue

Four earlier acquisitions remain FAILED, with exact available files and input
snapshots in `RUST-NFS-SERVER-MOVER-{INITIAL,SECOND,THIRD,FOURTH}-EVIDENCE.json`:

- `server-mover-recovery-20261020T155528Z-8c83749d`: four native controls passed,
  then a runner variable collision (`args` held syscall fields instead of CLI
  options) prevented all mover cases. Normal cleanup completed. Correct the
  fixture variable; do not count native success as mover recovery.
- `server-mover-recovery-20261020T160217Z-a6ae253a`: four native controls passed
  and the first mover proved a D-state claimed-source read and local guard
  contention. Its contender reused the live API port, so AddrInUse occurred
  before the required ownership refusal. Normal cleanup completed; zero mover
  recovery cases passed. The pre-event wire checkpoint and incomplete observer
  output are retained, but the final failed-case wire window was not saved
  before cleanup. Do not infer complete-window RPC recovery from it. The runner
  now uses an ephemeral contender listener and saves a failed-case wire window.
- `server-mover-recovery-20261020T161123Z-b3b77cb2`: three native controls passed;
  final native SIGKILL timed out waiting for `/run/libpod/exits/ID`. Cleanup start
  met an existing VM systemd scope, leaving the probe and normal unmounts pending.
  Zero movers ran. Preserve this failed report, not just the later rescue.
- `server-mover-recovery-20261020T162326Z-190c2b69`: disabling only backend cgroups
  did not solve abrupt live-NFSD termination. Two NFSD controls passed, then the
  next SIGKILL/exit-file wait failed; actual exit 137/PID 0 took over two minutes.
  No mover ran. The same-server retry released the original probe; normal
  unmounts and exact resource removal are retained in `rescue-87-fourth.py` and
  its `rescue-and-cleanup.json`. No failed observer/cleanup deadline is called a
  pass. Restore default cgroups and qualify only the explicit NFSD-quiesced
  container sequence in this increment; abrupt termination remains unqualified.

For the third acquisition, read-only inspection used the existing Podman WSL
entry point. Its outer PID 1 was WSL init; the actual manager was PID 17 inside
nested mount/PID/network namespaces. Discover that manager rather than assuming
the PID on another boot:

```powershell
wsl -d podman-machine-default -u root -- ps -eo pid,ppid,stat,comm
wsl -d podman-machine-default -u root -- nsenter -t MANAGER_PID -m -p -n -- systemctl show libpod-OWNED_ID.scope -p ActiveState -p SubState -p ControlGroup -p Result
wsl -d podman-machine-default -u root -- nsenter -t MANAGER_PID -m -p -n -- ps -p RECORDED_PID,RECORDED_CONMON_PID -o pid,ppid,stat,comm
```

The exact owned scope was inactive/dead with no control group and both recorded
PIDs absent. Only then retry `podman start OWNED_ID`, verify its original private
IP/NFSD threads, let the original native probe finish, checkpoint the raw relay,
normally unmount both owned mounts, and remove only the report's exact resources.
The retained `rescue-87-third.py`/`rescue-and-cleanup.json` records these actions
and an empty rootful inventory. Read-only scope output was transcribed from tool
results with its provenance limitation stated. No unit reset, VM restart,
force/lazy-unmount or host cgroup-policy change was used. Unrelated SSH config
permissions and host-key verification prevented SSH access; neither was changed.
This rescue does not promote the acquisition into a passing test.
