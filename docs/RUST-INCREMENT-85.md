# Rust increment 85: source-side synchronization discovery and withholding capability

## Scope and acceptance

Inspect four actual claim workers on buffered NMP-41B NFSv4.1: debug/release,
same-share/separate-share source and destination. Trace every fsync/fdatasync
and capture every active relay before selecting service reply-loss tests. Keep
production NFS and post-delivery source deletion disabled. Rust, dependencies,
schemas, recorder/API handoff, retry/review and shutdown deadlines are unchanged.

The retained runner adds `--source-sync`; other matrices remain available.
Repeat 43 inventory/model controls. Require actual mount/device/worker security,
clock identity, successful source synchronization and zero-exit claim workers.
Use exact mount-ID accounting, including root descriptors, and independently
decode raw RPC bytes. Account for requests and replies inside each sync interval
and captured request/reply pairs spanning its entry. Keep undecoded traffic and
broader-window WRITE/COMMIT observations distinct from interval attribution.

Separately trace a native dirty 4 KiB file fsync on the source export for each
layout. Select only an observed WRITE/COMMIT for native hold/release and drop/
TCP-reset controls. First prove successful raw server completion withheld while
the expected source fsync is blocked, with independent server inode/device/
size/link/hash and live NFSD evidence. Require successful recovery and preserved
server identity/content. Record actual-service/native operation intersection
separately: a native positive control never substitutes for service recovery.

Require same-ID job 1/202 before producer reuse, attempt-1 committed delivery,
validated manifest/hashes, retained original private source, database/enrollment
and newer producer bytes, no second job and normal stop. Preserve the normal
3N transfer path. Run both mandatory SLES compatibility gates and independent
raw-proof/build/inventory audit. See [the step-by-step lab](NFS-SOURCE-SYNC-LAB.md).

## Results

Run `mount-profile-20261020T052303Z-25849c5e` passed all four actual claim
workers, two native discoveries, four native withholding/recovery controls and
43 inventory/model controls, with cleanup_errors=[] and process exit 0.
The raw report is 51,733,723 bytes; 26 exact acquisition sources are captured.
No Rust source or Cargo.lock change was needed.

| Layout | Profile | Successful source fsync calls | Requests / replies inside sync | Captured pairs spanning entry |
|---|---|---:|---:|---:|
| Same-share | Debug | 8 | 0 / 0 | 0 |
| Same-share | Release | 8 | 0 / 0 | 0 |
| Separate-share | Debug | 8 | 0 / 0 | 0 |
| Separate-share | Release | 8 | 0 / 0 | 0 |

All 32 calls were actual syscall 74, returned zero and belonged to source
mount/path descriptors. Per worker they cover the original file, private custody
file (twice), private job directory (twice), original nested parent (twice) and
private source parent. All four workers exit zero. Broader transport windows
contain 3,982 outgoing calls, 184 undecoded compounds, 16 decoded WRITE operations
and four COMMIT operations. Those positive broader observations are retained;
they are not causally attributed to source fsync. No request/reply occurs inside
these sync intervals and no captured request/reply pair spans their entry.
This is not proof about RPCs outside the capture or other workloads/caches.

Both native source-export discoveries observe WRITE (38) inside fsync, with no
COMMIT selected. Each layout then passes matched-success hold/release and
hold/drop/TCP-reset controls. Every held compound is [53,22,38], writing 4096
expected bytes at offset zero with requested FILE_SYNC (2) and successful
committed FILE_SYNC (2). The actual native process is D-state, pending fsync on
the expected source FD; independent server inode/device/link/size/hash and two
running NFSD threads prove known server completion while its success is withheld.
Both active relays are observed on separate shares; the actual carrier is the
source relay for every native control.

In both drop cases cachethis=false produces an observed uncached-reply response,
then a successful semantic FILE_SYNC WRITE resend on the new connection. These
are not cached exact-success replays. The probe returns successful fsync and
server identity/content remains unchanged. Source-export transport withholding
is proved; the actual-service/native sync-operation intersection is empty on
both layouts. Consequently **zero mover source-sync reply-loss/death cases are
run or qualified**. Do not manufacture a COMMIT test from the function name or
substitute these native controls for service recovery. Selected source namespace
LINK/REMOVE loss evidence remains separately in increment 84.

All four service observations initially return retryable 503 with unreleased
paths while tracing. Identical-ID replay confirms job 1/202 before producer-path
reuse; each commits payload attempt 1 with validated manifest and retains the
original private source inode/content, local database/enrollment and newer
producer bytes. Job 2 is absent and normal stop succeeds. The recorder has no
new duty after 202, and normal transfer remains 3N logical I/O.

## Compatibility and independent audit

Both fresh mandatory SLES gates pass with actual process exit 0 and no cleanup
errors:

| Build mode | Run ID | Exact debug / release target tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261020T052240Z-1881a9ce` | 211 / 211 | 20 |
| Qualification | `20261020T052251Z-b68877ed-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain pinned locked
cargo-zigbuild GNU/glibc 2.22, exact target execution in SLES userspace, ELF
interpreter/library/symbol auditing, six negative controls per build mode,
formatting/Clippy and the 42-package locked dependency graph. There is one
shipping executable; artifact counts include tests and both profiles.

The live fixture uses source-identical passing increment-84 gates
`20261020T042206Z-929446e1` and
`20261020T042206Z-19f43768-nfs-qualification` while the fresh gates run. The
independent final audit compares all 62 current Rust entries against both
live/fresh archives, hashes and directly compares all forty fresh artifact
bytes to live inputs, and re-audits every fresh ELF report. It checks all 26
captured acquisition sources against current bytes, complete case coverage,
raw RPC hashes/decoding and interval/pair accounting, source/state/manifest/
security/clock preservation, native held success and raw replay/resend pairs.

All 16 actual-proof corruption controls reject invalid server bytes, wrong
pending FD, missing held state, premature forwarding, wrong operation, altered
request hashes/reply bytes or missing transport evidence. Seven RPC decoder and ten
WRITE/resend regression tests pass, as does missing-gate refusal before fixture
creation. The exact verifier, unchanged gate auditor, inventory collector, source
archives and fixture-probe binary/source/compiler/ELF evidence are retained.
The historical increment-76 transport-observation correction remains explicitly
referenced as historical evidence, not a failed increment-85 acquisition.

Final inventory captured at `2026-10-20T05:47:11.924524+00:00` confirms both
Podman engines have no containers. Rootful retains only the original two Rust
cache volumes and default network; unrelated default-engine volume metadata
and networks match the retained baseline. Normal NFS unmounts and owned-resource
cleanup succeed without force/lazy unmount, NAS/host-policy or VM-boot changes.

[Raw evidence](RUST-NFS-SOURCE-SYNC-EVIDENCE.json) preserves the exact raw report
bytes/SHA with lossless zlib/base64 encoding.
[Input/audit evidence](RUST-NFS-SOURCE-SYNC-INPUT-EVIDENCE.json) retains the
independent proof, source/build provenance and final inventory. All checks pass
before the canonical SLES reports are updated.

## Limits and next boundary

Read the [complete lab procedure](NFS-SOURCE-SYNC-LAB.md). The approved container
runs pinned SLES 12 SP5/glibc 2.22 userspace on shared modern WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`, not the original SLES kernel. Two volatile
64 MiB tmpfs exports on one server, one client, small files, fixed protected
roots and sec=sys do not qualify NetApp/Isilon firmware, physical media/power,
server restart/verifier changes, delayed-effect settlement, every cache/size/load
or deployment profile. A successful fsync and server-visible bytes are not
source-cleanup authorization or proof of namespace persistence through power loss.

The repeatable source-export native capability is retained for future positive
service discoveries. Further source-sync fault cases need an actual eligible
service RPC; do not keep rerunning this clean-source workload expecting a
fictional COMMIT. Remaining server-recovery/delayed-settlement and joint-outage
replay/backpressure qualification stay open. SC-119 feeds DOC-01–05; DOC-06,
registration and repair remain deferred. All eight first-release gates and
production NFS/source deletion remain unchanged.
