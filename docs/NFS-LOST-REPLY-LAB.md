# Controlled lost NFS reply qualification lab

Use [increment 64](RUST-INCREMENT-64.md) for declared scope and results and
[testing limitations](TESTING-LIMITATIONS.md) for release implications.
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
`net.ipv4.ip_unprivileged_port_start=0`; backend source ports are 601–616. No host
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
