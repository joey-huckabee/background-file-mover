# Controlled NFS synchronization lab

This fixture qualifies bounded observations, not production NFS or source cleanup.
Use [increment 67](RUST-INCREMENT-67.md), the [base fixture](NFS-TEST-FIXTURE.md)
and [testing limits](TESTING-LIMITATIONS.md). Registration and repair stay deferred.

## 1. Infrastructure and privileges

Use the existing rootful Podman VM, `podman-machine-default-root`, and existing
`localhost/background-file-mover-e2-nfs` image. The runner records its image ID.
Builder and SLES userspace images are digest-pinned in
[`scripts/rust-platform.json`](../scripts/rust-platform.json). The shared modern
VM kernel supplies NFS, namespaces and ptrace; no real SLES installation, package
installation, new VM bootstrap or NAS-admin operation is part of this recipe.

The runners create only private internal networks, disposable server/client/
relay containers and owned volumes. Two tmpfs-backed server exports have distinct
mount devices and endpoints. Servers need the retained fixture privileges; the
client mounts NFS. The relay drops all capabilities and binds reserved backend
ports only through its private network-namespace sysctl. The OS probe and mover
workers run as UID/GID 1000. A separate observer joins the client's PID namespace,
uses the pinned builder's Python and SYS_PTRACE/DAC_READ_SEARCH with NoNewPrivs,
and has no network. Neither Python nor a tracer is installed in SLES or shipped
with the service. No time namespace is requested: timestamps use the shared
kernel monotonic clock; an independently introduced time namespace would invalidate
this correlation and must not be silently substituted.

The small C OS probe is fixture infrastructure. Zig compiles it inside the pinned
builder for x86_64 GNU/glibc 2.22 using explicit private local/global cache paths.
The runner audits its ELF interpreter, libraries and symbols using the SLES gate's
auditor and records compiler/source/binary hashes. It is not a Rust executable,
service component or production dependency.

## 2. Fresh mandatory SLES gates

From the repository root:

```powershell
python scripts/check-rust-sles.py
if ($LASTEXITCODE -ne 0) { throw 'Production gate failed' }
python scripts/check-rust-sles.py --qualification
if ($LASTEXITCODE -ne 0) { throw 'Qualification gate failed' }
```

Keep both passing run directories. These build with cargo-zigbuild GNU/glibc 2.22,
audit every ELF and run exact debug/release target tests in pinned SLES userspace.
Host cargo tests do not substitute for these checks.

## 3. Independent capability, before service traces

```powershell
python scripts/check-nfs-reply-capability.py --synchronization
if ($LASTEXITCODE -ne 0) { throw 'Sync capability failed; preserve its report and owned resources' }
```

This command executes no Rust binary. It first repeats the two legacy REMOVE
controls, then traces native clean-file, dirty-file and directory fsync in the
existing hard/noac mount profile. Separately it normally unmounts the destination
and mounts a buffered ac/async control, checking actual mount flags. A buffered
dirty-file trace discovers which WRITE/COMMIT operations occur during fsync.

Only a discovered candidate permits release/discard withholding controls. Require
matched RPC/NFS success withheld, the same process pending in native x86_64 fsync
74 on the recorded descriptor, independent server-local original content/identity
and two running NFSD threads on both servers before release/drop. A discard also
interrupts the connection and must observe native replay on a new connection;
it is not arbitrary silent loss on a healthy TCP stream. WRITE may first retry
the original SEQUENCE and receive NFS4ERR_RETRY_UNCACHED_REP (10068), then resend
with new SEQUENCE/stateid. Accept that path only with the exact original retry
and error captured, unchanged target filehandle/offset/stability/length/data hash,
a successful full FILE_SYNC WRITE and unchanged server inode/content afterward.
A namespace test's byte-identical successful-replay premise must not be imposed
on this distinct path. Every probe must finish
successfully. No candidate means an explicit unavailable boundary, not fabricated
COMMIT evidence or a silently skipped positive test.

Inspect `report.json`: `synchronization.observations`, `withholding`, actual mount
rows, `observed_sync_operations`, `withholding_available` and `cleanup_errors`.
A buffered control does not qualify the service's existing noac configuration.

## 4. Trace the actual service

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --sync-observe --sync-capability rust/validation/<capability-run>/report.json
if ($LASTEXITCODE -ne 0) { throw 'Service sync observation failed; preserve evidence' }
```

The driver prints `NFS sync observation output: <worker-run-directory>` at startup.
In a second terminal, start the read-only clock checker immediately, before the
four worker traces begin:

```powershell
python scripts/check-nfs-sync-clocks.py rust/validation/<worker-run>
if ($LASTEXITCODE -ne 0) { throw 'Clock identity coverage failed; do not qualify the correlation' }
```

Require `sync-clock-report.json` PASSED, common actual `/proc/self/ns/time` identity
and all four external observers. Starting late can miss short-lived workers and
must fail as incomplete coverage. Container disappearance during teardown is not
proof of a namespace. A passing main run alone does not replace this clock audit.

The independent report must pass without cleanup errors and match current shared
observer drivers. Source mounts use a source relay from their first connection;
destination uses another relay. The full fixture repeats normal transfer and
local-state/startup checks; these are not synchronization durability tests.

Four normal worker traces cover debug/release times claim_apply/copy_chunk. The
external tracer attaches to the actual single-thread worker at an existing
qualification pause, then the runner releases it. It observes fsync/fdatasync
entries/exits, return codes and descriptor path/inode/mount identity. Descriptor
inspection uses only local proc fdinfo/mountinfo/readlink, never a stat/open/read
of the target that could cause NFS I/O. Ptrace changes scheduling; these timings
are not latency or performance evidence.

Relay windows are bounded at 8,192 frames and 64 MiB of decoded RPC bytes,
compressed per record. Records stay in bounded memory until an acknowledged
control, successful held reply, connection event or error flushes the window.
The stop_observe acknowledgement is required; a crashed relay or unacknowledged
flush cannot prove absence. No whole-window JSON rewrite occurs per packet.
They capture calls/replies with connection/XID, monotonic
timestamps, hashes and compressed raw payloads. Decode
`payload_zlib_base64` with base64 then zlib; verify SHA-256 before RPC decoding.
Large committed raw reports use a lossless `report_encoding: zlib-base64-json`
envelope to respect the repository file-size limit. Decode `report_zlib_base64`
with base64 then zlib, verify `report_sha256`, then parse the original JSON.
For a `zlib-base64-json-parts` envelope, verify the hashes of the listed ordered
part files, concatenate their `data_base64_segment` strings, then decode and
verify the complete report hash. Local validation `report.json` files stay uncompressed.

The fixture decoder fails closed on unsupported compounds; unknown traffic must
not be treated as proof that no COMMIT occurred. Correlate all call timestamps
inside each sync interval. An empty interval has no observed outgoing RPC; a
nonempty unsupported interval remains unresolved. A failed/truncated/overflowed
trace is not evidence of absence.

The existing delivery Session is supervised: its owner kills/reaps it after
completion. Record that SIGKILL separately from natural exit. A delivery trace
requires an already-Committed job/attempt-one receipt immediately after exit and
before any recovery/replay call; killed alone is not a pass. Every observed sync
must have returned zero. Claim workers and C probes still require exit zero.

Require successful original-job/attempt-one commitment, retained source, unchanged
local database identity and producer reuse only after confirmed 202. A successful
normal trace does not claim crash/reply-loss recovery at an unproven sync boundary.

## 5. Cleanup, interpretation and limits

Release held replies and restore owned NFSD first. Wait for owned probes/workers
and observers, normally unmount every NFS mount, then remove only owned containers,
volumes and network. On cleanup failure retain resources and recovery identifiers;
do not prune globally, force/lazy-unmount or reboot the VM to manufacture a pass.
Inspect both rootful and default rootless container inventories afterward.

A server-reported WRITE stability/verifier or COMMIT success is protocol evidence;
server-local bytes on tmpfs are not persistent-media or power-loss durability.
An fsync can complete without a new COMMIT in the tested profile. Separate
producer-client caches, physical NAS, server restart/reclaim, old kernels and all
other mount/security profiles remain outside this experiment. Production NFS and
source deletion stay disabled; FR-03/05 remain open.

Protocol field interpretation follows [RFC 8881 COMMIT](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.3)
and [WRITE](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.32). [Uncached-reply semantics](https://www.rfc-editor.org/rfc/rfc8881.html#section-15.1.3.9)
explain the separately captured WRITE retry path. No RFC code
component is vendored into the service.

## Recorded results

Independent `reply-capability-20261018T235849Z-99eef171` and actual-service `nfs-20261019T000329Z-385f192f` pass with no cleanup errors. The buffered control withholds a successful FILE_SYNC WRITE while native fsync is pending; it is not COMMIT evidence. All four service traces and retained checks pass; see [increment 67](RUST-INCREMENT-67.md) for actual interval counts, initial failures, exact artifacts and limits. Confirm final engine inventory independently after normal unmount/owned-resource removal.

Independent final inventory confirms zero containers on rootful and default
rootless engines, only the two pre-existing rootful Rust caches and default
network, and VM cgroup `0::/`. Every fixture used normal-unmount-first cleanup;
no manual, forced/lazy unmount or VM reboot was needed.

## Buffered service observation follow-up

The historical noac matrix above remains separate. Use the
[buffered synchronization lab](NFS-BUFFERED-SYNC-LAB.md) and
[increment 76](RUST-INCREMENT-76.md) for eight actual buffered NMP-41B worker
traces, complete mount-ID interval accounting and conditional native controls.
That runner measures clock identity inside each live observer before releasing
the worker; an independently started clock monitor cannot replace it. Consult
the actual RPC/unknown counts rather than carrying forward the old noac totals.
Neither native FILE_SYNC WRITE nor a returned fsync proves service COMMIT-loss
recovery or physical durability. Production NFS/deletion remain off.

[Increment 77](RUST-INCREMENT-77.md) extends observation to worker file I/O,
retaining --buffered-sync and its default decoder output. Use the separate
[I/O attribution lab](NFS-BUFFERED-IO-LAB.md) to connect descriptors, bounded write
bytes and protocol identities where evidence permits. Neither timing alone nor
a decoded COMMIT in another worker's window proves the selected worker issued it.
Keep initial failed analysis, unknown compounds and remaining fault scope explicit.

[Increment 78](RUST-INCREMENT-78.md) and the
[payload COMMIT lab](NFS-BUFFERED-COMMIT-LAB.md) add a separate --buffered-commit
matrix at the observed fchmod boundary. Independent large-payload native
withholding controls must pass before selected service release/death recovery.
Keep COMMIT success/reply loss separate from UNSTABLE WRITE reply loss, physical
durability and unobserved pending source synchronization. Production NFS/deletion stay off.

The separate [UNSTABLE WRITE lab](NFS-BUFFERED-UNSTABLE-LAB.md) and
[increment 79](RUST-INCREMENT-79.md) use --buffered-unstable for operation 38 at
the observed payload fchmod boundary. Full-count UNSTABLE replies, every-range
retransmission and later matching COMMIT must be proven; successful sync or a
4 KiB FILE_SYNC control cannot substitute. Production NFS/deletion stay disabled.
