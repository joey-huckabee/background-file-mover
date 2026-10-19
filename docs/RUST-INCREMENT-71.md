# Rust increment 71: buffered copy and verification interruption/recovery

## Scope

Qualify actual buffered NMP-41B source-copy and destination-verification reads
through joint NFS outage, coordinator death, surviving-worker exclusion and
original-state recovery, on same-share and separate-share layouts. Keep
production NFS/source deletion disabled. No Rust source, dependency, shipping
executable, retry/review policy or shutdown-deadline change is introduced.

The maintained mount-profile runner gains --buffered-reads, mutually exclusive
with --same-share. Its new helper reuses source/hash-verified audited binaries,
fresh fixture bindings, existing qualification-only read-cache advice/rendezvous,
and runtime Case helpers. An optional destination NFS fixture root selects the
second export while preserving existing default paths. Both exports are on one
server; separate shares do not mean independent failure domains.

## Acceptance and unchanged recovery policy

Eight cases cover same/separate-share, debug/release, source_copy/verify_read.
Record source hash before cache advice. Once paused, use metadata observations
only until the outage proof; hashing the target then would invalidate the test.
Require an actual D-state x86_64 read(2) on the correct open source/staging file,
one MiB requested, NFSD threads zero, absent read-completed marker, bounded local
control/health and no replacement worker. Copy pauses after its first MiB;
verification pauses before rereading the full destination staging allocation.

After coordinator SIGKILL, logical ownership must exclude starts/initialization/
direct transfer until actual worker exit, even if raw flock closes. Restore the
server and retain original state, enrollment, claim inode and valid partial
allocation. Copying uses attempt 2 while preserving its old partial; verification
retains attempt 1 and its publication inode. Preserve post-202 producer-path
reuse, source hash/retention, destination hash/manifest and committed replay.
Do not re-enroll, delete state, refresh pins or bypass review to obtain recovery.

## Results

Final run `mount-profile-20261019T034903Z-cdc1b1b3` **passes** with eight actual
worker cases, 43 independent model/inventory controls, seven exact driver
snapshots and cleanup_errors=[]. [Raw final evidence](RUST-NFS-BUFFERED-READS-EVIDENCE.json)
retains configurations, mount inventory/devices, actual read syscalls/descriptors,
UID/capabilities, local status/guard/contender results, original state, staging
identities/bytes, manifests and recovery/replay observations.

| Buffered layout | Debug copy | Debug verification | Release copy | Release verification |
|---|---|---|---|---|
| Disjoint roots on one mount/export | Passed | Passed | Passed | Passed |
| Two distinct mounts/exports on one server | Passed | Passed | Passed | Passed |

Each case proves D-state read(2), a 1 MiB request on the correct claimed-source
or destination-staging descriptor, zero NFSD threads and no read-completed marker.
Local health/control stay bounded. After coordinator death, all 24 competing
service/initialize/direct-transfer commands refuse while old workers remain D.
Old exit is confirmed after restoration before restart; original source and
state/enrollment survive, as do newer producer bytes and committed replay.
All four copy cases preserve the old partial and recover on attempt 2; all four
verification cases retain attempt 1 and their original publication allocation.

**Observed lock scope:** the raw local flock remains contended in all sixteen
orphan samples (zero cases with observed early raw-lock closure). OwnerUnavailable
and contender refusal here establish held-guard orphan exclusion. These results
do not add physically-closed-guard buffered qualification; retain the earlier
[lifetime-ownership regression evidence](RUST-INCREMENT-47.md) separately. No
free-lock or exited-process observation is treated as remote-settlement proof.

Both fresh required SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T033428Z-dca3f6f6` | 211 / 211 | 20 |
| NFS qualification | `20261019T033430Z-125e507b-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json) include pinned
cargo-zigbuild GNU/glibc 2.22 output, exact SLES target tests, formatting/Clippy,
42 locked dependencies and six negative ELF controls per configuration. There
is one shipping executable; the audit counts include test binaries and both
profiles. No Rust source or Cargo.lock change is introduced.

The live matrix runs alongside the fresh gates using the passing,
source-identical increment-70 gates `20261019T024518Z-217cc08d` and
`20261019T024519Z-8839b997-nfs-qualification`. All **40 artifact hashes** match
the corresponding fresh builds, including the exact debug/release service
binaries exercised live. Both fresh archives match all 62 current Rust inputs.
[Input/equivalence evidence](RUST-NFS-BUFFERED-READS-INPUT-EVIDENCE.json) preserves
those checksum-verified archives, hashes and exact verifier source. All seven
final fixture snapshots match current inputs byte for byte.

The initial run `mount-profile-20261019T033752Z-0a2651a3` fails to open the
owner-only syscall file without observer capabilities. The next run,
`mount-profile-20261019T034235Z-f51895cb`, has SYS_PTRACE but still lacks the
DAC_READ_SEARCH read/traversal capability. Both reach the first source-copy case
and fail before read-descriptor proof, then restore storage and clean up. Retain
[the initial failure](RUST-NFS-BUFFERED-READS-INITIAL-EVIDENCE.json) and
[the second observer failure](RUST-NFS-BUFFERED-READS-OBSERVER-INITIAL-EVIDENCE.json)
with their exact sources; neither is relabeled as passing qualification.

An independent, no-network pinned-SLES
[observer preflight](RUST-NFS-BUFFERED-READS-OBSERVER-EVIDENCE.json) then passes
with SYS_ADMIN for setup plus SYS_PTRACE/DAC_READ_SEARCH for the isolated root
observer. It reads an ordinary UID-1000 sleep process's syscall, verifies glibc
2.22, zero active ordinary-process capabilities and no-new-privileges, then
removes its container. This is an OS permission check, not a Rust/NFS read test.
The eight final actual workers independently retain UID/GID 1000, zero active
capabilities and no-new-privileges; no host ptrace policy is changed.

Final non-Rust checks cover Python syntax, trace-matrix parity, all 106 unique
scenario/six DOC rows, local documentation links, JSON, LF/newline/whitespace,
source/archive hashes and staged file-size checks. Both Podman engines have no
remaining test containers. The owned fixture network/volume are removed after
normal unmount; rootful storage retains only the preexisting toolchain/registry
caches and default network. Images remain available for future qualification.

## Scenarios, procedure and limits

SC-106 describes the user situation, with prior handoff/replay/publication/
ownership situations and DOC-01/03/04/05 kept consistent. Preserve earlier stable
IDs. The [step-by-step lab](NFS-BUFFERED-READS-LAB.md) describes exact commands,
privileges, cache-observation ordering, joint outage, read-descriptor proof,
orphan exclusion, original-state recovery and restore/unmount-first cleanup.

These finite cases do not prove independent NAS failures, other-client cache visibility, exact RPC identity or
success-reply withholding, NAS/server reboot/failover or explicit grace/reclaim, delayed mutating-effect
settlement, persistent-media/power durability, old SLES kernels, every cache/workload
or concurrent/endurance behavior. Pinned SLES userspace shares the modern kernel.
All eight first-release gates stay open; production NFS/deletion remain disabled.
