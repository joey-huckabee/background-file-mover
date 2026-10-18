# Rust increment 56: enrolled startup with both endpoints on NFS

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Add `--coordinator-death --death-scope both-nfs-bootstrap`: eight cases,
enrolled-empty/populated state, debug/release, blocked/following a two-second
local stop. Both private roots use distinct controlled NFSv4.1 hard mounts,
server containers/network namespaces/IPs and tmpfs exports. SQLite, ownership
and control state stay local. Stop only source NFSD; the destination must remain
usable. No source bootstrap pause hook or new observer capabilities are needed.

Enrolled-empty preserves the active original enrollment/database pair. Populated
state has a durable 202/Claimed job, producer-reused original path, retained WAL
and exactly one 1 MiB attempt-1 partial on NFS. Prepare that partial on healthy
NFS; kill and confirm the seed coordinator before killing/confirming its paused
worker so a live coordinator cannot create another attempt.

Snapshot local database/WAL/shared-memory/journal/configuration separately from
remote source/receipt and destination marker/staging/final/manifest evidence.
Never open SQLite for fixture inspection. Launch into an actual unavailable
source, require one D-state bootstrap child, bounded local Starting status and
an unanswered sent health request. Require local evidence unchanged while
blocked, with bounded fresh healthy-destination probes and unchanged destination
snapshots. Bracket observations with actual D state.

Kill only the coordinator for blocked cases; following-stop cases distinguish
prompt exit from a surviving terminating orphan. Surviving workers retain the
original local epoch across three bracketed guard/status samples and refuse
service/initialize/transfer competitors. Physical raw-lock closure is
observational; the separate strict increment 47 regression stays available.

Restore endpoints and confirm old exit before recovery. Preserve exact local,
source/receipt and destination evidence before restart, with no re-enrollment.
Recover using the original database/source inode and destination binding. Require
Committed, correct payload hashes and nested manifest semantics, private source
retained, cleanup false and producer-reused paths untouched. Enrolled-empty uses
attempt 1; populated recovery uses attempt 2 and retains the old partial's exact
inode/size/hash. All roots remain stable.

Retain six normal transfer baselines, twelve NFS-state-parent refusals, all 184
state-file refusals/fourteen preservation fixtures, OS/startup checks and clean
teardown. Run fresh production and qualification GNU/glibc-2.22 zigbuild/ELF/
pinned-SLES gates. Reuse increment 55's exact qualified service artifacts only
while all Rust input bytes match; verify the fresh gates' executable hashes
against those reused binaries. Capture executed driver hashes.

## Limits

This selects source-bootstrap interruption with an independently usable NFS
destination. Fresh unenrolled bootstrap, destination-only/later-startup failures,
joint outages and all storage-layout combinations remain outside this matrix.
Two server containers share one modern WSL2 kernel and physical host; tmpfs and
NFSD thread outages do not establish actual NAS/mount/security, partition/reclaim,
delayed RPC settlement, disk/power durability or old-kernel support. The payload
is one nested 2 MiB + 17-byte file; short stops do not qualify the default-60
uninterruptible branch. Systemd/account work and all first-release gates remain
open. No Rust/runtime/retry/review/shutdown/dependency change is intended.
Production NFS and source deletion remain disabled.

## Results

The [raw evidence](RUST-NFS-BOTH-BOOTSTRAP-DEATH-EVIDENCE.json) records `nfs-20261018T043705Z-456435eb`.
All eight cases passed: four blocked orphans retained ownership and four
following-stop cases exited promptly. All twelve competing effect commands
refused; no ownership loss occurred. No terminating orphan survived a stop.

| Profile | State | Death phase | Outcome | Attempt |
|---|---|---|---|---|
| debug | enrolled-empty | blocked | blocked orphan retains ownership | 1 |
| debug | enrolled-empty | terminating | prompt exit before coordinator kill | 1 |
| debug | populated | blocked | blocked orphan retains ownership | 2 |
| debug | populated | terminating | prompt exit before coordinator kill | 2 |
| release | enrolled-empty | blocked | blocked orphan retains ownership | 1 |
| release | enrolled-empty | terminating | prompt exit before coordinator kill | 1 |
| release | populated | blocked | blocked orphan retains ownership | 2 |
| release | populated | terminating | prompt exit before coordinator kill | 2 |

All eight bootstrap workers start without a pause hook and are actually D,
with bounded local Starting status and sent/unanswered readiness requests.
Local database/WAL/sidecar/config snapshots are identical before, during blockage
and after confirmed old exit. Source/receipt evidence matches after restoration;
healthy destination binding/staging/final/manifest snapshots match before,
during source outage and after old exit. No fixture SQLite inspection occurs.
Source NFSD=0/destination NFSD=2; all 20 fresh healthy-peer probes pass,
maximum 1.312 seconds. Mounts, client devices/mount IDs, server tmpfs
devices, namespaces and addresses distinguish the two endpoints; state is local.

Surviving orphans retain their original epoch across three bracketed guard/status
samples and refuse effect commands. Physical raw-lock closure is observational
(0 cases), not required; the strict increment 47 regression
remains separate. Prompt stop before coordinator kill is not surviving-orphan
or coordinator-SIGKILL coverage. Maximum observed orphan status is 1.406
seconds; two-second configured stop responses take at most 1.094 seconds,
including Podman overhead. No default-60 deadline or NAS-settlement claim.

All eight recover to Committed through the original database/source inode,
enrollment receipt and destination binding, without re-enrollment. Enrolled-empty
recovery uses attempt 1; populated recovery replays the accepted job on attempt 2
and retains the exact original 1 MiB partial inode/size/hash. All four populated
seeds retain WAL and exactly one partial after confirmed seed coordinator then
worker exit. Payload SHA-256, nested manifest semantics, root identity, retained
private source, cleanup false and producer-reused paths pass.

Six normal transfer baselines, twelve NFS-state-parent refusals, 184 state-file
refusals across fourteen preserved fixtures and retained OS/startup checks pass.
Cleanup errors are empty; raw evidence retains individual snapshots and logs.
A post-run Podman inventory confirms no temporary containers, fixture volumes
or fixture networks remain; only the two Rust cache volumes and default network
remain.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261018T034035Z-f07bc86c --qualification-gate rust/validation/20261018T034048Z-9fd95a19-nfs-qualification --isolated-startup --coordinator-death --death-scope both-nfs-bootstrap
```

## Compatibility and provenance

Fresh production `20261018T043528Z-c2d48e76` passes 204 tests per profile; qualification
`20261018T043539Z-c5a06856-nfs-qualification` passes 205 per profile. Both complete GNU/glibc-2.22 cargo-zigbuild,
twenty ELF audits, six negative controls and exact debug/release tests in pinned
SLES 12 SP5 userspace, with formatting, Clippy and locked package/feature checks.
The graph stays at 42 external packages, maximum imported GLIBC_2.18 and standard
`/lib64/ld-linux-x86-64.so.2`.

Both old/fresh 61-file Rust inventories match current bytes; archives match their
own report digests and fresh executable hashes are verified. All four reused
service binaries are byte-identical to fresh gates. Captured driver hashes match
executed working bytes and staged blobs after LF normalization. No Rust input,
package, runtime retry/review, shutdown deadline or production-enable change is
made. The fixture client adds no syscall-observer capabilities for this scope.
See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

All 95 SC and six DOC IDs remain stable. DOC-02/03/04/05 gain selected enrolled
both-NFS startup evidence. Fresh/destination-side/later startup, actual mount/
security, delayed RPC/remote settlement, NAS/disk durability and systemd/account
work remain pending. All eight release gates stay open. Production NFS and
source deletion remain disabled.
