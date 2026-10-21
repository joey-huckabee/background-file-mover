# Rust increment 90: controlled recovery at payload publication

## Scope and acceptance

Run four native prerequisites, then four debug/release live-worker publication
cases with NFSD restart or NFSD quiescence followed by same-container confirmed
termination/start. Use two retained bounded tmpfs/client NFS filesystems and a
third local state filesystem. Select file_unlink, immediately before removal of
the staging alias after establishing and synchronizing the final payload link.

Require PublishIntent, complete two-name same-inode payload, two links, expected
hash and absent manifest. Stop the facility, prove actual D-state unlinkat on
the staging directory FD/name 1.part, and preserve source/aliases/state/ownership.
Restore without replacement, require original syscall success and correlated raw
REMOVE, original final inode/hash with one link, staging absent, later manifest
publication, attempt-1 commitment and original-state replay preserving producer reuse.
Follow the [step-by-step lab](NFS-PUBLICATION-RECOVERY-LAB.md), both mandatory
SLES gates and independent source/raw/build/cleanup audit. Keep Rust/dependencies,
API/retry/review/deadlines, production NFS and source deletion unchanged.

## Results

Run publication-server-recovery-20261021T004154Z-2663618b exits 0 with status
PASSED and cleanup_errors=[]. Four native retained-FD controls pass before the
actual mover cases. Native probes preserve backing identity/A-to-B bytes,
complete eight successful sync calls and exit normally. All four retain original
opaque handles while successful sessions and WRITE verifiers change.

| Build | Facility | Actual pending operation | Outcome |
|---|---|---|---|
| Debug | NFSD 2 to 0 to 2 | unlinkat on staging directory FD, flags 0 | Original worker/attempt 1; commitment and replay pass |
| Debug | NFSD zero, same-container SIGKILL/exit 137/start | unlinkat on staging directory FD, flags 0 | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD 2 to 0 to 2 | unlinkat on staging directory FD, flags 0 | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD zero, same-container SIGKILL/exit 137/start | unlinkat on staging directory FD, flags 0 | Original worker/attempt 1; commitment and replay pass |

Every case reaches PublishIntent with two complete same-inode payload names,
link count two and matching 2,097,169-byte SHA-256, while COMMITTED.json is absent.
Independent read-only backing observation proves both aliases and private source
unchanged while stopped. The actual worker is D-state in syscall 263 on its
original staging-directory FD, flags zero. Health responds in 1.922-2.515 seconds;
a contender using an ephemeral listener refuses specifically on local ownership
in 0.984-1.093 seconds. Original coordinator/worker/epoch, PublishIntent status,
local database inode/configuration and enrollment stay intact.

After restoration the original worker completes attempt 1. Staging is absent and
the original final payload inode/hash remains with link count one. Each worker
has fifteen successful traced sync calls after restoration, sixty total; initial
final LINK/file/new-parent sync precede attachment and are not traced. Every
worker later exits with traced status 9, existing supervised retirement after a
confirmed Committed receipt. This does not test worker death during publication.
Complete payload/manifest validation and clean original-state same-ID replay
preserve the committed job/manifest, private source and newer producer-path bytes.

Backing tmpfs devices are source 0:89/destination 0:90. Client st_dev is 235/240,
with local state 208, proving actual distinct filesystems. Both backing mounts
retain observed 64 MiB/4,096-inode bounds. Keeper PID 2129437, start/mount namespace,
full mountinfo and devices remain identical throughout server observations and
final cleanup; independent role mounts stay read-only. The actual debug container
case changes backend network namespace; other mover cases and all native controls
retain theirs. VM boot ID remains unchanged. Preserve that selected observation
without inferring a general namespace/reclaim or reboot guarantee.

## Compatibility and independent evidence audit

- Production gate 20261021T004016Z-1a2c9253: 211 target tests per debug/release profile.
- Qualification gate 20261021T004015Z-9d622c3f-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Locked cargo-zigbuild GNU/glibc 2.22,
formatting/Clippy, exact target execution in pinned SLES 12 SP5, loader/library/
symbol checks and six negative ELF controls per mode pass. All 62 Rust inputs and
42 locked packages remain unchanged; there is still one shipping executable.
Live executables come from the preceding passing identical-source gates while
fresh checks run. The audit compares exact source archive contents and shipping
bytes across live/fresh gates, rather than requiring identical compressed tar hashes.

The independent audit verifies seventeen frozen acquisition sources, native
probe/ELF, actual pending unlink FD/path/mount/inode/arguments and clock interval,
two-name backing inode/hash/link count, unchanged source/state/ownership, subsequent
manifest order, sync/event consistency and original committed replay. In each
case, a successful raw REMOVE named 1.part with its PUTFH and request/reply hashes
lies inside the pending original unlinkat interval and completes after restoration.
This is a selected single-worker syscall/RPC correlation, not discarded-reply or
full cached-session/lease/reclaim proof. Post-restoration decoded WRITEs are small
manifest writes; they are not payload-copy or pre-attachment LINK/sync evidence.

All 110 mover-proof corruptions and five storage-proof corruptions are rejected.
Seven RPC decoder regression tests pass; forty fresh Rust artifacts/ELF reports,
all source archives and exact shipping bytes are checked. Native windows retain
196 raw records and service windows 11,646, including 1,619 unknown service
records and decoded 10052/2 statuses. Unknown compounds remain preserved. Keeper
identity/full mountinfo stays identical across twenty-five server-state
observations and final cleanup. No acquisition failure occurred in this increment;
the initial increment 88 proc-bind failure stays retained as fixture provenance.

After all fixture and gate processes exit, inventory captured at
2026-10-21T01:05:38.161780+00:00 confirms zero containers in both engines, original
Rust caches, unchanged baseline volume metadata/network names and no remaining
owned fixture resources. Both client mounts normally unmount before removal;
keeper removal occurs last so the local driver can release both retained tmpfs
mounts. No force/lazy NFS unmount, VM reset or host/NAS policy change is used.

Read [the raw acquisition](RUST-NFS-PUBLICATION-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-PUBLICATION-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and
[complete procedure](NFS-PUBLICATION-RECOVERY-LAB.md).



## Limits

This is a selected same-assignment continuation at staging-name removal. Initial
LINK/rename and other sync boundaries, manifest interruption, coordinator/worker
death/replacement and crash reconciliation remain separate. Prior file/link/parent
sync precedes tracing; do not claim to trace it. Controlled retained-memory restart
is not abrupt live-NFSD death, independent NAS, persistent disk/power, outstanding
UNSTABLE-data loss or old SLES kernel/client qualification. Measure actual namespaces;
a selected namespace change does not close full lease/reclaim/reboot obligations.
Pinned SLES userspace shares a modern WSL2 kernel, with deployment/account/remote
API and larger/concurrent workloads still unqualified. Removing destination staging
is not private-source cleanup. Keep all eight release gates open, production
NFS/source deletion off and registration/repair/DOC-06 deferred.
