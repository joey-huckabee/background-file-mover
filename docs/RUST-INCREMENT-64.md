# Rust increment 64: lost NFS REMOVE replies

Scope declared 2026-10-18 before execution. Production NFS and source deletion
remain disabled. No Rust, dependency, retry/review, ownership or deadline change.

## Capability gate before worker tests

A disposable Python TCP relay, using the already pinned builder image, preserves
RPC record bytes and intercepts only successful matched NFSv4.1 REMOVE replies.
A bounded observation decoder follows RFC 5531 sections 9/11 and RFC 8881 XDR;
unsupported/truncated compounds are not positive evidence. Existing export
security options remain unchanged; the relay binds backend source ports 601-616
with net.ipv4.ip_unprivileged_port_start=0 only in its owned network namespace.
It runs as UID/GID 1000 without capabilities and has no published/control port.
Control files are local/private to that disposable container. No host/NAS packet
filter, VM boot setting, package install or production access change is intended.

First run six pure parser/framing rejection tests. Then run two real-server
capability controls: hold a successful REMOVE reply while the client remains
pending, independently observe the removed staging name and unchanged final
inode/content through the server's local filesystem, then either release the
captured reply or discard it, interrupt that connection and require observed
kernel replay on a new connection. Actual remote D-state and unchanged NFS
SEQUENCE/filehandle/name must be checked. Connection/XID, request/opcode/name/
filehandle hash, decoded successful reply and distinct
receive IDs must establish the causal chain. No target success may be forwarded
while armed. If either control fails, do not execute worker cases or claim a
lost-reply capability.

## Finite worker matrix, conditional on that proof

Four cases: debug/release times file/manifest staging unlink. Reuse the retained
qualification-only pre-unlink pauses. Source and destination remain on distinct
controlled NFSv4.1 endpoints with local state; destination routes only through
the relay and is never first mounted directly. Require both servers healthy,
server-side REMOVE completion/success with target reply withheld, client D-state
unlinkat syscall 263, bounded control/API status, Claimed/202 replay without
false commitment and exact server-side final inode/content while staging is absent.
Kill the coordinator; retain exclusion for any surviving worker and distinguish
prompt exit. Kill only the known old worker, discard held replies and close their
connection, confirm every old thread exited, then restart with original state. Require attempt-one recovery,
original payload/manifest inode/hash and source/database/enrollment, producer
reused path, no staging or allocation reuse, validated manifest and retained source.
Retain six transfer baselines and local-state/lock/startup regressions.

Scenario SC-098 and supporting SC-018/039/040/050/092/093/097; DOC-03/04/05.
Run fresh production and qualification SLES gates, audit exact sources/ELFs and
record full infrastructure, failure attempts, successful evidence and safe cleanup.

## Limits

This is controlled NFSv4.1 REMOVE acknowledgment loss plus explicit connection
interruption/replay on a shared modern WSL2 kernel and live tmpfs-backed servers. It does not qualify LINK/COMMIT/fsync
reply loss, server reboot/power/disk loss, physical NAS/network isolation, old
kernels, mount security or arbitrary delayed effect settlement. Connection closure
is lab intervention, not a new service recovery action or a universal signal/
shutdown-deadline guarantee. No release gate
or production NFS/deletion approval follows. Registration stays deferred.

## Results

`nfs-20261018T191725Z-ec359051` passes both repeated capability controls and all four mover
cases, with no cleanup errors. See [raw worker evidence](RUST-NFS-LOST-REPLY-EVIDENCE.json)
and [the step-by-step lab](NFS-LOST-REPLY-LAB.md).

| Profile | Publication | Death outcome | Recovery | Result |
|---|---|---|---|---|
| debug | file_unlink | surviving_worker_excludes_replacement | original inode, attempt 1 | PASS |
| debug | manifest_unlink | surviving_worker_excludes_replacement | original inode, attempt 1 | PASS |
| release | file_unlink | surviving_worker_excludes_replacement | original inode, attempt 1 | PASS |
| release | manifest_unlink | surviving_worker_excludes_replacement | original inode, attempt 1 | PASS |

Each real server removes staging and returns a successful matching REMOVE reply,
which the relay withholds while the actual mover child stays in D-state unlinkat.
Both servers remain at two NFSD threads and fresh source/destination I/O succeeds.
Health/job/replay stay bounded, the job remains Claimed and identical-ID custody
replay is 202 without false SQLite commitment. Read actual death outcomes above;
prompt worker exit is not a retained orphan. Surviving workers must exclude an
alternate-port contender and report OwnerUnavailable until actual thread exit.
Buffered replies are discarded with explicit connection closure; a later replay
frame is distinct from delivery of an intercepted original frame.

Original-state recovery preserves payload/publication inode/content, local
database/enrollment and claimed source, commits on attempt one, removes only owned
staging aliases and preserves producer-reused paths. No second payload allocation,
source deletion, new retry/review policy or re-enrollment is introduced.

Six transfer baselines, twelve NFS state-parent refusals, 184 state-file refusals
with fourteen preserved fixtures and inherited-lock/isolated-startup probes pass.
Fresh production gate `20261018T185200Z-dff8da3a` passes 204 tests/profile; qualification gate
`20261018T185211Z-1eb3bd24-nfs-qualification` passes 205/profile. Each audits 20 ELF artifacts and
six negative controls in pinned SLES 12 SP5/GNU glibc-2.22 userspace, with formatting,
Clippy, locked 42-package graph and exact current 61-file Rust inventory. No Rust
input changed and all four service binaries are identical to increment 63.

The independent proof is [recorded separately](RUST-NFS-REPLY-CAPABILITY-EVIDENCE.json).
The [initial failed control](RUST-NFS-REPLY-CAPABILITY-INITIAL-EVIDENCE.json) and
[its cleanup/exact source snapshots](RUST-NFS-REPLY-CAPABILITY-INITIAL-RECOVERY.json)
remain failures/recovery records, not passing capability. No real mover lost-reply
case was allowed before both refined real-server controls passed.


## Initial capability finding and refinement

`reply-capability-20261018T190256Z-ea2fb73d` is FAILED, not qualification support.
The release control proved server completion with a captured successful reply
withheld and a pending OS client. The discard-only control did not finish within
its 20-second wait; cleanup's further wait also timed out, and ordinary unmount
correctly refused while the owned probe remained live. No Rust binary ran.
Exact original drivers and failed raw evidence are retained; the known owned
unlink probe was killed, both normal unmounts confirmed, then only the recorded
containers/volumes/network were removed. Separate recovery-cleanup evidence
preserves the original failure report unchanged.

The refined loss control explicitly closes the affected TCP connection after
discarding buffered success replies. It must observe a new connection, a new
receive ID and the same NFS SEQUENCE/handle/name request identity before counting
kernel replay. It makes no bounded-retry claim for a healthy TCP stream with a
silently discarded RPC reply. The real mover cases remain gated on both controls.
Parser unit tests use deterministic in-memory partial streams; an initial Windows
socket-pair test stalled and was terminated. Real TCP evidence comes from the
container capability controls, not that uncompleted local socket test.

## Independent capability proof

`reply-capability-20261018T190840Z-2467b9d6` passes the release and refined
loss-plus-connection-interruption controls with no cleanup errors and no Rust
execution. Both clients are observed in D state; each first success reply is
captured while server staging is absent and final inode/content unchanged.
Release forwards that held frame. Discard drops it and closes connection 1;
replay is observed on connection 2 with a distinct receive ID and the same
NFS SEQUENCE/filehandle/name identity. Raw payload re-decoding and all six driver
hashes are independently verified. This establishes the gate for mover tests;
it does not promote the initial healthy-stream discard timeout into a pass.

## Measured outcomes and teardown

All four worker cases retain a surviving worker after coordinator death: four
OwnerUnavailable/2 observations and four alternate-port ownership-guard refusals.
Each case captures one successful REMOVE reply, discards that frame and explicitly
closes its connection before confirming every old thread exited. Read this order;
it does not prove that SIGKILL alone guarantees cancellation or server settlement.

Health and job status each take at most 1.781 seconds, custody replay 1.828;
state-file refusals take at most 1.234 seconds, including Podman overhead. These
are bounded observations for small fixtures, not production latency guarantees.
All jobs commit attempt one and retain source with cleanup false.

Independent final inventory confirms no containers or fixture volumes/networks
from either capability attempt or the full run. Only the two shared Rust caches
and default podman network remain. The VM remains `0::/` with pre-existing
nfs/nfsd modules loaded; no systemd bootstrap, module load, VM boot/global network
sysctl change, new server image or package experiment was required.
