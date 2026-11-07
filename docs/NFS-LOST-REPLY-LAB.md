# Controlled lost NFS reply qualification lab

Use [increment 64](RUST-INCREMENT-64.md) for declared scope and results and
[testing limitations](TESTING-LIMITATIONS.md) for release implications.
Use [increment 65](RUST-INCREMENT-65.md) for the separate LINK extension and
section 8 below for its commands and evidence requirements.
Use [increment 66](RUST-INCREMENT-66.md) and section 9 for source-claim LINK/REMOVE
and the pending-202 acknowledgement boundary.
Production NFS and source deletion remain disabled. This is not a production
deployment or NAS administration procedure.

## 1. Verify the existing controlled backend

From the repository root, use Python 3.11+ and the rootful Podman VM:

```powershell
$env:CONTAINER_CONNECTION = 'podman-machine-default-root'
podman ps -a --format '{{.Names}} {{.Status}}'
podman image inspect localhost/background-file-mover-e2-nfs --format '{{.Id}}'
wsl -d podman-machine-default -u root -- ls -d /sys/module/nfs /sys/module/nfsd
```

Use the retained cached server and preloaded VM modules. Follow
[the fixture guide](NFS-TEST-FIXTURE.md) if provisioning is necessary; do not
automatically load modules, change VM boot settings, rerun package experiments
or point this driver at production mounts. No real SLES installation is needed.
The service/client uses pinned SLES 12 SP5 userspace; servers and the fixture
relay use their separately recorded images on the same modern VM kernel.

## 2. Prove the fixture before running mover lost-reply cases

The pinned builder and SLES runtime images must already be cached; see
[gate provisioning](RUST-SLES-GATE.md) if either is missing. Create the ignored
validation parent on a fresh checkout before this standalone command.

```powershell
New-Item -ItemType Directory -Force rust/validation | Out-Null
python scripts/check-nfs-reply-capability.py
if ($LASTEXITCODE -ne 0) { throw 'Reply capability unproven; inspect report and recovery resources' }
```

This command executes no Rust binary. It first runs six decoder/framing tests
including every truncation of the positive vectors, unsupported operations,
false opcodes embedded in opaque bytes, partial record reads and size/count
bounds. Then it creates an internal network with two controlled NFS servers,
two separate tmpfs exports, a SLES client and a Python relay. There are no
published ports. The client mounts source directly and destination only through
the relay, preventing an existing direct destination connection from bypassing
the interception. Both mounts use NFSv4.1/TCP hard mounts with `noac`, `timeo=10`
and `retrans=1`. Record actual mount, namespace and device identities.

The relay uses Python already present in the pinned builder image; no packages
or application dependencies are installed. It runs as UID/GID 1000 with no
capabilities and no-new-privileges. To preserve the existing server export's
reserved-port requirement, only its private network namespace sets
`net.ipv4.ip_unprivileged_port_start=0`; backend source ports are 601–1000. No host
network sysctl or export security option changes. Control is through local
mode-0700 container files, not a network control endpoint.

## 3. Establish the evidence chain

For each release/discard control, create a small sentinel with staging and final
hard links. Record both through the server's local filesystem, not the NFS client:
inode, device, link count, size and hash. Arm the relay for the exact staging name,
then start a normal client `unlink` and record its PID/command and actual D state.

The relay forwards requests and unselected replies unchanged. It holds only a
matched successful NFSv4.1 REMOVE reply. Evidence must simultaneously show:

1. The real server's old name is absent and its final name still has the original
   inode/content and one link.
2. A captured RPC success/COMPOUND success/REMOVE status zero matches the request
   by connection and transaction ID. Keep raw request/reply payloads, hashes,
   decoded operation/name/filehandle and NFS SEQUENCE identity.
3. That reply has not been forwarded or released, and the actual client remains
   in D state with its command still pending.

This is stronger than a pre-call pause, stopped server or D state alone.
Unsupported or truncated protocol data cannot establish positive evidence.

For **release**, forward the buffered success and require client exit zero.
For **discard**, permanently discard the buffered success and explicitly close
its connection. Require client exit zero and an observed reply on a new
connection/new receive ID with the same NFS SEQUENCE/filehandle/name request
identity. This is reply loss plus connection interruption/replay. The internal
`connection_resets` field records connection closure, not a packet-level RST
capture or proof of a particular TCP flag.

Do not promise bounded kernel replay when an RPC reply is silently discarded on
an otherwise healthy open TCP stream. The initial attempt timed out in precisely
that control; retain its failure and separate cleanup evidence. The refined
control does not convert the old result into a pass.

The bounded fixture decoder follows [RFC 5531 sections 9 and 11](https://www.rfc-editor.org/rfc/rfc5531.html#section-11)
and [RFC 8881 operation/XDR definitions](https://www.rfc-editor.org/rfc/rfc8881.html#section-16.2).
It is an observation tool and transparent byte relay, not a production NFS client
or server. Record framing, request maps, withheld bytes and connection counts
are bounded; an exceeded bound or unsupported target response fails qualification.

## 4. Run both mandatory compatibility gates

```powershell
python scripts/check-rust-sles.py
if ($LASTEXITCODE -ne 0) { throw 'Production SLES gate failed' }
python scripts/check-rust-sles.py --qualification
if ($LASTEXITCODE -ne 0) { throw 'Qualification SLES gate failed' }
```

Save the two printed directories as `$ProductionGate` and `$QualificationGate`.
Require PASSED reports and cleanup success. Use exact GNU/glibc-2.22 zigbuild
artifacts, ELF interpreter/import/library audits, locked sources/features and
debug/release tests in pinned SLES userspace. See [the gate](RUST-SLES-GATE.md).
These independent checks may run while the OS-only capability proof is performed.
No host-only cargo test or matching version label substitutes for them.

## 5. Run the finite mover matrix

```powershell
python scripts/check-nfs-boundaries.py $ProductionGate --qualification-gate $QualificationGate --isolated-startup --coordinator-death --death-scope lost-reply
if ($LASTEXITCODE -ne 0) { throw 'Lost-reply qualification failed; inspect report and retained resources' }
```

The driver checks exact current Rust inventories/archives and ELF hashes, runs
six normal transfer baselines, provisions a fresh relay layout and repeats both
capability controls. Failed capability prevents all mover lost-reply cases.
Application tests use the exact audited artifacts in SLES; the observer's syscall
inspection capabilities do not belong to the UID/GID-1000 mover/worker processes.

Four cases cover debug/release times file/manifest staging unlink. Each uses an
original local database/enrollment and a nested 2 MiB plus 17 byte recording.
After custody/202, write different data at the original producer path. Reuse the
qualification-only pre-unlink pause; capture client aliases and independent
server objects before arming. Require successful REMOVE with reply withheld,
actual worker D-state unlinkat syscall 263 and staging-parent descriptor, server
staging absent/final unchanged, both servers still at two NFSD threads and fresh
healthy I/O on both endpoints. Health/job/replay must stay bounded, with Claimed
state and same-ID custody 202 but no false SQLite commitment.

Kill only the coordinator. For any surviving worker, require OwnerUnavailable
and guard refusal by an alternate-port contender; distinguish actual prompt
exit rather than claiming a retained orphan. Kill only the known old worker,
discard held replies/close their connection and confirm every old thread exited.
Then recover using the original configuration/database without re-enrollment.
Require attempt one, original payload/publication inode/hash, source/database/
enrollment and producer-reused path, no staging alias or second allocation,
valid nested manifest and claimed source retained with cleanup disabled.

## 6. Retain regressions and perform safe cleanup

The full command retains twelve NFS state-parent refusals, 184 state-file checks
with fourteen preserved fixtures, inherited-lock and isolated-startup regressions.
Read final report status, individual cases and cleanup errors; a printed case
PASS is not the final matrix result.

On success or failure, resume any held replies before waiting on clients and
normally unmount the owned filesystems before stopping servers or removing
containers, volumes and network. A failed OS-only control terminates only its
recorded probe if necessary. No forced/lazy unmount is permitted. On cleanup
failure, keep recorded resources for recovery and preserve the failed report.
Verify final inventory; shared toolchain/registry caches and pre-existing modules
are retained:

```powershell
podman ps -a --format '{{.Names}} {{.Status}}'
podman volume ls --format '{{.Name}}'
podman network ls --format '{{.Name}}'
```

## 7. Interpret the limits

Selected successful REMOVE reply loss plus connection interruption is distinct
from LINK, COMMIT/fsync or every namespace/synchronization RPC. The live tmpfs
server's completion is not physical-media durability, reboot/grace/reclaim,
physical NAS isolation, old SLES-kernel behavior or production security support.
The fixture's controlled AUTH_SYS profile and transparent relay are not a
shipping deployment. Its connection closure is lab intervention, not a new mover
recovery command or a universal SIGKILL/shutdown-deadline guarantee. No arbitrary delayed-effect settlement or cross-host
takeover guarantee follows. All first-release gates stay open; production NFS
and source deletion remain disabled.

## Recorded execution

The independent capability run `reply-capability-20261018T190840Z-2467b9d6`
and full run `nfs-20261018T191725Z-ec359051` pass with no cleanup errors. The full run
repeats both controls before four debug/release worker cases and retained checks.
Read [the increment report](RUST-INCREMENT-64.md),
[capability proof](RUST-NFS-REPLY-CAPABILITY-EVIDENCE.json),
[worker evidence](RUST-NFS-LOST-REPLY-EVIDENCE.json) and
[initial failure](RUST-NFS-REPLY-CAPABILITY-INITIAL-EVIDENCE.json).
[Recovery/source evidence](RUST-NFS-REPLY-CAPABILITY-INITIAL-RECOVERY.json)
contains exact original driver bytes encoded as base64 with their recorded SHA-256;
these preserve provenance and are not instructions to run the failed variant.

All four worker cases in the recorded run retain a surviving worker after
coordinator death and refuse an alternate-port contender at the ownership guard.
Each captures/discards one successful reply and closes its affected connection;
every known old thread exits before original-state recovery. Independent final
inventory has no containers/fixture volumes/networks, only shared build caches
and default podman network. Pre-existing modules and the VM's `0::/` hierarchy
are retained.

## 8. LINK completion with a withheld success reply

Use the same prerequisites, private infrastructure and normal-unmount-first
cleanup as sections 1–7. First run a separate capability proof, without Rust:

```powershell
python scripts/check-nfs-reply-capability.py --operation link
if ($LASTEXITCODE -ne 0) { throw 'LINK capability unproven; inspect report and recovery resources' }
```

Each release/discard control starts with exactly one staging link and no final
name. The normal client runs `ln staging final`. Arm for LINK (11) and the exact
final basename. Before intervening require all three observations together:
server-local staging/final are the original inode with link count two and
unchanged size/hash; captured RPC/COMPOUND/LINK success matches connection/XID
and decoded request; the actual client is still D/pending and the target success
has not been forwarded. A local final name alone is insufficient evidence.
Release forwards that exact frame. Discard permanently drops it and closes the
affected connection; require native successful replay on a different connection
with identical SEQUENCE/filehandle/name identity and distinct receive ID.

The standalone proof must pass before the mover matrix. Run fresh production and
qualification SLES gates using section 4, then substitute their passing run paths:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --coordinator-death --death-scope lost-link-reply
if ($LASTEXITCODE -ne 0) { throw 'LINK worker qualification failed; preserve evidence' }
```

The driver repeats both LINK capability controls before any mover LINK case.
It runs debug/release × `file_link_rpc`/`manifest_link_rpc`. These qualification-only
rendezvous are immediately inside the exclusive-link namespace call, before
native linkat; they are absent from production builds. Arm the relay before
releasing the rendezvous. Require actual x86_64 syscall 265, flags zero and both
parent descriptors identifying the private staging and intended final parent.
Observe server completion while the worker remains D, both endpoints healthy,
API health/status and 202 custody replay responsive, and durable job phases
unchanged. A visible final manifest does not authorize SQLite commitment.

Kill only the recorded coordinator, require surviving-worker exclusion where
applicable, then kill only that known worker, discard held replies and interrupt
their connection. Confirm every recorded old thread exited before restarting
with original local state. Both owned aliases must still identify the original
inode before recovery; recovery must remove only staging, preserve file/manifest
inode/hash and attempt one, commit normally, retain claimed source and preserve
producer-reused paths. Keep exact source, artifact, driver and raw RPC hashes.

Do not infer LINK fsync/disk durability, source-claim LINK behavior, COMMIT reply
loss, physical NAS recovery or healthy-stream bounded silent-loss retry. The
connection interruption is a controlled fixture intervention, not a production
recovery command. Keep the increment-64 failed silent-loss control and recovery
records unchanged. The default capability command and `lost-reply` scope still
select REMOVE; the LINK selector does not replace their historical evidence.

### Recorded LINK results

Independent `reply-capability-20261018T200112Z-fb530318`, retained REMOVE regression `reply-capability-20261018T200427Z-a948eee5` and full mover `nfs-20261018T203516Z-eb5b56b7` pass with no cleanup errors. Both full-run capability controls precede all four worker cases; all recover on attempt one with original inode/content. See [increment 65](RUST-INCREMENT-65.md) for actual death outcomes, gates, raw evidence and remaining limits. Independent final inventory confirms no validation containers on either rootful or default rootless Podman. The rootful engine retains only the two shared Rust cache volumes and default network; the VM remains `0::/`. Normal unmount preceded removal; neither worker attempt required manual cleanup. The initial manifest-basename driver failure and exact executed sources remain retained separately in increment 65.

## 9. Source-claim LINK and REMOVE with success replies withheld

Use the pinned images, private infrastructure and normal-unmount-first cleanup
from sections 1–7. [Increment 66](RUST-INCREMENT-66.md) fixes the finite scope.
First prove both operations on the source endpoint without executing Rust:

```powershell
python scripts/check-nfs-reply-capability.py --role source --operation both --backend-restart
if ($LASTEXITCODE -ne 0) { throw 'Source claim capability unproven; inspect report and recovery resources' }
```

Require four controls: LINK release/discard and REMOVE release/discard. The source
mount must use the relay from its first connection; destination uses the separate
healthy server directly. Separate source sentinel directories include the opcode
to prevent collisions. LINK begins with one old name/no private alias and must
produce the original inode at both names with link count two. REMOVE begins with
two aliases and must leave only the private name with one link. For every control,
observe server-local inode/content and namespace, a matched captured RPC/NFS
success and actual client D state together before releasing or dropping anything.
Release must finish successfully; discard explicitly interrupts that connection
and must observe a new-connection/new-receive-ID successful native replay with
unchanged SEQUENCE/filehandle/name identity. Preserve raw payloads and hashes.

Run the fresh production and qualification SLES gates from section 4, then use
their passing run directories:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --coordinator-death --death-scope claim-lost-reply
if ($LASTEXITCODE -ne 0) { throw 'Source claim worker qualification failed; preserve evidence' }
```

The full driver routes even its initial `/tmp/nfs` base mount through the source
relay, before any direct source connection can exist. `/tmp/nfs-source` uses that
same proxy route; `/tmp/nfs-destination` stays direct to the other server. Record
actual mount addresses, distinct devices/export IDs/network namespaces and proxy
backend. Require no source backend address in the client's NFS mount rows. The
driver repeats all four source controls and the OS-only backend recovery probe
before entering the worker matrix.

Four cases are debug/release × `claim_link_rpc`/`claim_unlink_rpc`. These opt-in
qualification pauses are inside the existing relocation calls immediately before
native linkat/unlinkat. POST asynchronously and observe exactly one claim worker.
Arm LINK for `data`, or REMOVE for `data.bin`, before releasing the pause. Require
actual syscall 265/263, old parent `current/nested` and private LINK parent
`.file-mover/1-0`; flags must be zero. Observe the server-completed alias state,
withheld successful reply and D worker concurrently, with both servers healthy.

Health/job reads stay bounded by the existing five-second fixture check. The
existing submission deadline is ten seconds: allow fifteen seconds including
Podman overhead for a pending retry to return 503. Initial submission and same-ID
retry must be retryable 503 with `source_paths_released: false`; job status stays
Accepted and destination job storage is absent. The recorder still only submits
JSON and retries the identical ID/body until 202; it need not poll status.

Keep producer paths immutable until 202, even if the original name has already
vanished on the server after REMOVE. Claim REMOVE removes a producer binding
while preserving private custody; postcommit source cleanup remains disabled.
Kill only the recorded coordinator, require surviving-worker exclusion where
observed, kill only the known old worker, discard held replies and interrupt
their connection, then confirm every old thread has exited. Reconcile the same
job and original claim inode with the original configuration/local state. Require
202 for the same submission before recreating the producer path, then verify
attempt-one delivery/manifest, unchanged private payload and database/enrollment,
preserved producer-reused contents and no second job/claim allocation.

Do not infer COMMIT/fsync or media durability, server reboot/reclaim, physical NAS
isolation, old-kernel behavior, arbitrary loss on a healthy TCP stream, concurrent
load, separate producer-client cache visibility or all claim/export/security
cases. Producer writes and mover reads use one controlled NFS client. The syscall and proxy intervention do
not change production deadlines or guarantee universal termination/cancellation.
Retain failed reports and executed driver sources if any stage fails; a failed
fixture is not qualified service behavior. Normal unmount must precede removal
of owned servers, client, relay, volumes and network; retain resources and report
cleanup errors if it fails.

### Source relay teardown and recovery control

The source-capability command also stops only the owned source NFSD threads,
observes an actual D-state OS hash probe, records the relay's backend EOF/connect
failure path, restores source NFSD and requires that same probe to finish with
the original hash. The destination stays healthy. This is fixture transport
qualification with no live mover; it is not physical NAS reboot or service
server-recovery qualification. The probe has a sixty-second post-restore bound;
production submission and shutdown deadlines are unchanged.

The relay now shuts down both directions of both sockets before releasing file
descriptors. Before forwarding any RPC bytes, it retries failed backend connection
establishment on the same accepted frontend, with one-second pauses and a
600-second fixture-only deadline. This prevents kernel frontend reconnect storms
without generating or replaying RPCs in the relay. It records transport events
separately from malformed/invalid protocol evidence. Sixteen active and four
hundred lifetime connections remain bounded; backend ports 601–1000 satisfy the
same reserved-port export rule using only the private namespace sysctl. Historical
increment-64/65 evidence retains its original 601–616/16-total configuration.

Retain the initial increment-66 FAILED run and separate recovery/source snapshots.
Do not restart a disposable relay and assume Podman preserves its IP: inspect the
actual address and original mount route. The failed-run recovery restored only
that fixture's original unused private address/MAC, waited for its old probes to
drain, then used ordinary unmounts before removing owned resources. No forced or
lazy unmount or probe kill was used. This manual recovery does not turn the
initial experiment into a pass or define a production operator command.

### Recorded source-claim results

Independent `reply-capability-20261018T221446Z-6be218f4` and worker `nfs-20261018T221850Z-7e29f816` pass with no cleanup errors. Four independent and four repeated source LINK/REMOVE controls precede four passing claim-worker cases. Initial/same-ID requests remain retryable 503 before custody confirmation; original-state replay then returns 202 for job 1, allowing producer reuse and attempt-one delivery with the original claim inode/content retained. See [increment 66](RUST-INCREMENT-66.md) for actual outcomes, SLES artifacts, raw frames, recovery and remaining limits. Confirm final engine inventory separately after normal unmount and owned-resource removal.

Independent final inventory confirms no containers on either rootful or default
rootless Podman, only the two pre-existing rootful Rust cache volumes and default
network, and VM cgroup `0::/`. The final worker run normally unmounted all NFS
mounts before owned-resource removal and needed no manual cleanup. Retain the
earlier failed runs and their separate recoveries described in increment 66.

## 10. Synchronization is a separate capability

Use [the synchronization lab](NFS-SYNC-LAB.md) and [increment 67](RUST-INCREMENT-67.md) before claiming fsync/COMMIT reply loss. Actual service syscall/RPC observations and a separate buffered WRITE control have different scopes. WRITE uncached-reply recovery must not inherit the namespace tests' byte-identical successful-replay assumption. Production NFS/deletion remain disabled.
