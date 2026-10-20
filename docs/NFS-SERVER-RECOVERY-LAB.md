# NFS server-recovery capability lab

Use this native fixture to establish what the approved container infrastructure
can reproduce before selecting mover recovery cases. Production NFS and
post-delivery source deletion remain disabled. This is not a NAS/VM reboot,
physical-media durability or Rust worker-recovery qualification.

The optional `--mover` extension is documented separately in the
[actual mover lab](NFS-SERVER-MOVER-LAB.md). The native-only invocation below
remains available. Native controls are prerequisites, not substitutes for the
extension's service cases and independent audit.

The original native-only invocation terminates a live kernel NFS server.
Repeated acquisitions in [increment 87](RUST-INCREMENT-87.md) encountered delayed
exit-file completion and a stale Podman scope. Its earlier four finite passes
do not establish reliable abrupt termination. The `--mover` extension explicitly
stops NFSD before container termination and qualifies that narrower sequence.
Keep abrupt recovery unqualified; preserve failures and restore users before
normal unmount/cleanup as described in the extension's rescue procedure.

## Infrastructure and exact steps

1. Work on `feature/rust-transfer-coordinator` in the existing approved Podman
   WSL2 VM. Inspect both engines, record existing volumes/networks and require
   no unrelated rootful fixture to be active:

   ```powershell
   git status --short --branch
   podman ps -a
   podman volume ls
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root volume ls
   podman --connection podman-machine-default-root network ls
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Retain the two Rust caches and unrelated default-engine anonymous volumes.
   Missing infrastructure follows [the fixture setup](NFS-TEST-FIXTURE.md).
   This extension requires no NAS access, host export configuration, VM restart,
   ptrace-policy change or real SLES installation.
2. Run both mandatory SLES compatibility gates and retain the printed paths:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use locked cargo-zigbuild GNU x86_64/glibc 2.22, exact debug/release
   target tests in pinned SLES userspace and ELF loader/library/symbol checks.
   The native capability runner can execute alongside those gates because it
   executes no Rust binary. It does not replace either compatibility gate.
3. Freeze the acquisition sources, then run:

   ```powershell
   python scripts/check-nfs-server-recovery.py
   ```

   The runner prints its unique `rust/validation/server-recovery-...` directory
   and snapshots nine exact acquisition sources before creating resources.
   Preserve a failed report and its source snapshots before correcting/repeating
   a run; do not edit captured sources while it runs.
4. The fixture creates an internal network, one owned named export volume,
   privileged cached kernel-NFS server, pinned SLES client, unprivileged relay,
   read-only volume observer and pinned Zig builder/external ptrace observers.
   No ports are published. `nfs_recovery_server.sh` provisions root-squashed
   synchronous exports with root fsid 0 and child fsids 68/69. Reserve the server's
   original private address using explicit `--ip` on the newly owned network;
   a dynamic address can change across container restart and strand the relay.
   Child directories
   use the named volume directly, not tmpfs. This preserves files across the
   selected server-container stop/start, but does not prove disk/power durability.
   Both exports share one backing filesystem/volume/server/kernel; they do not
   represent independent NAS appliances or a same/separate-share mover matrix.
5. Mount both roles through the one observed relay from the beginning with
   NFSv4.1/TCP/sec=sys, hard, ac,async,timeo=10,retrans=1. Preserve actual mountinfo,
   server exports, image, volume mounts, IP, kernel boot ID, network namespace,
   host PID and container StartedAt before/after every event. The short retry
   settings are fixture settings, not a production recommendation.
   Only the client setup/observer has SYS_ADMIN/SYS_PTRACE/DAC_READ_SEARCH.
   Probe and relay run as UID/GID 1000 with zero active capabilities and
   NoNewPrivs=1. The independent volume reader is read-only and has no active
   capabilities. Root privileges belong only to the isolated setup/server.
6. `nfs_recovery_probe.c` is built by pinned Zig for GNU/glibc 2.22 and audited
   using the unchanged SLES gate's ELF policy. It is a fixture-only native probe,
   not a new production executable/dependency. Each of four cases writes only
   one 4096-byte file: NFSD stop/start and container stop/start, each on source
   and destination export roles. No storage-fill or payload-scale claim is made.

## Per-case capability proof

1. Open a new mode-0600 file and keep that descriptor open. Attach the external
   bounded fsync tracer and verify actual clock-namespace identity among client,
   observer and relay. Start raw RPC capture before permitting the first write.
   Write 4096 `A` bytes, fsync and fstat, then wait at a local rendezvous.
2. Independently read the same file from the read-only volume observer. Retain
   backing device/inode/link-count/size/hash. Capture the initial successful raw
   WRITE request/reply, handle hash, session ID and write verifier. Use the
   relay's `checkpoint` command to persist the complete live trace without
   resetting it; reading its last state file alone can return a stale trace.
   Do not infer
   server state solely from client-visible bytes or a process exit.
3. For NFSD stop/start, execute `rpc.nfsd 0` inside only the owned server and
   require observed zero threads. Preserve its still-running container identity.
   For container termination/start, use `podman kill --signal KILL <owned-server>`,
   then `podman wait <owned-server>` and require exit 137, inspected Status=exited,
   Pid=0 and Running=false. Running=false alone does not prove a completed stop.
   This is intentional abrupt fixture termination, not a production shutdown
   recommendation. The final path does not use the failed `stop --time 0` controller.
4. While stopped, the separate read-only observer must still see exactly the
   original file identity and `A` bytes from the named volume. Permit the native
   probe to overwrite through its existing descriptor with 4096 `B` bytes.
   Require actual D state and pending pwrite (18) or fsync (74), matching FD and
   proc FD path. Record relay transport state; a local pause is not this proof.
5. Take the restoration timestamp inside the relay's observed WSL clock
   namespace; never compare Windows monotonic timestamps with WSL RPC times.
   Restart NFSD with the retained 10-second fixture lease/grace settings, or
   start the same server container and wait for its NFSD to have two threads.
   Do not remount the client, replace its process/FD or recreate the file.
   Allow native hard-mount recovery. Require successful write/fsync/readback,
   original device/inode/size, normal probe exit and two successful traced fsyncs.
   Native pread can use client cache; independent server-side hashing must prove
   the `B` bytes actually reached the backing file.
6. Capture complete raw RPC windows, including unknown compounds. Pair calls
   and replies by connection/XID; independently decode/hash every captured raw
   payload. Require successful initial/recovered full-count FILE_SYNC WRITEs on
   the same opaque handle and distinguish old/new session IDs and write verifiers.
   Record protocol errors as observed. Session, verifier and network-namespace
   changes are measured separately; do not assume all must change together.
   Successful WRITE compounds can include a trailing GETATTR; audit the complete
   observed operation vector and raw successful SEQUENCE reply echo, not just
   a three-operation summary or an assumed handshake.

The protocol meaning of sessions/errors and write verifiers is defined in
[RFC 8881](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.32), including
[BADSESSION](https://www.rfc-editor.org/rfc/rfc8881.html#section-15.1.11.1).
Changing a write verifier does not itself test recovery of outstanding UNSTABLE
data. These probes acknowledge the initial FILE_SYNC write before the event.

The native rendezvous budget is 120 seconds, post-restoration completion budget
90 seconds and external trace budget 180 seconds. These bound the lab, not the
mover's shutdown, retry or service response deadlines. Do not alter service
deadlines to make this capability run pass.

## Retained failed fixture attempts

Retain [the initial attempt](RUST-NFS-SERVER-RECOVERY-INITIAL-EVIDENCE.json).
Its dynamic backend changed from the relay's original private 10.89.0.2 to
10.89.0.5 after container restart. The probe timed out and cleanup retained the
owned resources. Manual observation identified the mismatch; restoring only
that owned server's original private address let the original native probe exit
and the NFS mounts unmount normally. Exact relay state before/after rescue,
failed report/acquisition sources, tracer logs and verified owned-only cleanup
are retained. The failed run is not relabeled as a passing recovery case.

Independent review also found a stale mid-run state snapshot and a Windows/WSL
monotonic-clock comparison, so its two earlier runner-reported NFSD successes
are not promoted as final qualification. The repeated run uses explicit private
IP reservation, live trace checkpoints, a relay-clock timestamp and actual
WRITE-with-GETATTR vectors. The verifier rejects missing checkpoints, wrong
clock boundaries and altered raw session echoes along with other false proof.

The [second attempt](RUST-NFS-SERVER-RECOVERY-SECOND-EVIDENCE.json) fixes IP/trace/
clock acquisition but retains another failed container transition. Podman's
`stop --time 0` reports a PID timeout and leaves Status=stopping. A premature
start is refused. Manual `podman wait` confirms exit 137; restarting the same
static-address server lets the native probe and pending normal unmounts finish.
Exact source, report, relay and owned-only cleanup records are retained. The
final acquisition uses explicit SIGKILL plus confirmed exit before restart;
neither failed attempt is retroactively promoted to a passing capability case.

## Cleanup and independent audit

Wait for the native run and both compatibility gate processes to exit. The
runner first restores a stopped owned server, releases the relay and lets probes
finish; then it normally unmounts NFS, shuts down/unexports the owned server and
removes only its containers, named volume and network. Cleanup exceptions fail
the report and retain resource identities. Do not force/lazy-unmount or delete
unrelated resources to conceal a failed cleanup.

```powershell
python scripts/capture-nfs-lab-inventory.py rust/validation/<live-run>
python scripts/verify-nfs-server-recovery.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
```

The collector records both engines after all processes exit. The verifier checks
the exact four event/role tuples, lifecycle identities, actual blocked FD,
retained backing file, raw protocol evidence, security/clocks, corrupt-proof
rejection controls, all acquisition sources, fixture ELF and both fresh Rust
archives/artifacts/tests/ELF audits. Both engines must have no containers and
their retained volume metadata/networks must match the preceding approved lab.
Only after all assertions pass does it publish the lossless report/input audit
and canonical fresh SLES evidence. Read [increment 86](RUST-INCREMENT-86.md) for
the actual result and qualification boundary.

## Limits and selecting the next cases

The VM kernel never reboots. Container restart and NFSD restart are different
events, and neither proves NAS power loss, failover, independent storage caches,
full lease/lock reclaim, all recovery grace cases or old SLES kernel behavior.
The decoder retains unsupported OPEN/session-creation compounds as unknown;
do not infer detailed reclaim semantics from them. Keep physical storage,
uncommitted-data recovery, delayed-effect settlement, server-completed reply loss,
large/concurrent workloads and shipping deployment separate.

No Rust mover, recording JSON/202, SQLite, local ownership guard, worker death,
manifest recovery or cleanup policy is exercised by these native cases. A
positive native capability permits selection of later service cases; it does
not qualify them. Preserve original-state/exclusion rules when those cases are
added. All first-release gates and production NFS/source deletion remain unchanged.


## Retained measured capability

[Increment 86](RUST-INCREMENT-86.md) passes four native probes after the two
retained failed acquisitions. Both facility events preserve the original FD,
opaque handle and backing inode on both export roles; each records BADSESSION,
a new successful session and changed write verifier. Container PID/start time
changes for its two termination/start cases, but network namespace and kernel
boot ID remain unchanged throughout. All eight native fsync calls, both fresh
SLES gates, 36 proof-rejection controls and the independent audit pass. Both
engines are cleaned normally with original unrelated resources retained.

Read [the lossless report](RUST-NFS-SERVER-RECOVERY-EVIDENCE.json) and
[exact inputs/audit](RUST-NFS-SERVER-RECOVERY-INPUT-EVIDENCE.json). These are
native capability results; no Rust mover recovery, outstanding UNSTABLE-data
recovery, fresh-netns/VM/NAS reboot or production support follows.
