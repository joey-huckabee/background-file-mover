# Rust increment 69: supervised NFS mount authorization

## Scope and implementation

Implement the [mount-profile contract](NFS-MOUNT-PROFILE.md) in supervised Rust
startup and worker authorization. Keep production NFS and source deletion
disabled. No new dependency, executable, runtime mount management, registration,
takeover, repair or automatic re-enrollment is introduced.

- Source and destination bindings now carry strict `nfs_mount` declarations for
  NFS only. Local binding encodings omit the field and retain their old persisted
  representation. NMP-41B and NMP-41N remain distinct candidate/diagnostic profiles.
- `mover-fs/src/mount_profile.rs` reads bounded local proc metadata, checks kernel
  escaping/structure/duplicates and the deepest component-containing mount,
  validates declared endpoint/version/security/options, rejects nested/stacked
  mounts, and checks the actual opened root's fdinfo mnt_id against that record.
- Bound source bootstrap and source/destination observation check the inventory
  before traversal and again after remote marker/custody metadata. The selected
  record, declaration, root path and namespace fingerprint are appended to the
  existing authorization observation. Original SQLite/enrollment and per-job
  destination policy checks therefore retain those pins without a schema change.
- Claim, enrollment, source-statistics and delivery children validate bound source
  authorization before payload-lock traversal and around effects. The legacy
  unbound payload worker refuses NFS. All coordinator checks remain local; no
  payload metadata operation is added to the async executor.

Production still refuses NFS even with a matching declaration. A source-scope
refusal withholds unproven 202 using existing recording_blocked behavior. A
destination-scope refusal preserves valid source custody and uses the existing
review/audited resume path. No retry classification or shutdown deadline changes.

## Compatibility boundary

Old NFS bindings without profiles refuse instead of discovering a new policy,
rewriting markers, refreshing pins or upgrading jobs. Preserve original state and
binary for a separately qualified migration; do not delete state or edit receipts
to bypass it. Older binaries reject new NFS marker fields. Local prototypes keep
their original encodings and original-state tests.

Matching mount fingerprints still do not prove continuity, authenticated NAS
identity or remote settlement. Missing/invalid proc/fdinfo observations refuse.
Namespace/option changes can deliberately refuse restart; packaging must qualify
the manual/systemd namespace relationship. Existing root/marker/enrollment and
worker lifetime checks remain required. Check-to-effect races against an
administrator changing mounts are not made atomic by these observations.

## Validation

Both final GNU/glibc 2.22 SLES gates pass with no cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF |
|---|---|---:|---:|
| Production | `20261019T013332Z-b0301f9f` | 211 / 211 | 20 |
| NFS qualification | `20261019T013345Z-9af2676b-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json) record the exact
GNU target, pinned Rust 1.99/cargo-zigbuild toolchain, SLES 12 SP5/glibc 2.22
execution, formatting/Clippy, 42 locked dependencies and six negative ELF controls
per configuration. All 40 ELF hashes and both archives' 62 current Rust inputs
are independently verified. The six new filesystem tests cover profile variants,
retry/security/options, missing/nested/stacked/subtree mounts, bounded kernel-field
parsing/escaping, declaration rules and descriptor mismatch. One new API test
covers explicit NFS declarations and forbidden local downgrade.

Independent fixture run `mount-profile-20261019T014128Z-afce9bd4` passes with no
cleanup errors and no Rust executed. Its 43 model decisions/parser controls are
retained, and its new VFS capability changes/restores nosuid while keeping actual
NFS root identity, mount ID/device and all non-VFS mount fields unchanged. The
old model pin refuses the changed flag and matches exactly after restoration.
See [capability evidence](RUST-NFS-MOUNT-AUTH-CAPABILITY-EVIDENCE.json).

Live authorization run `mount-profile-20261019T020832Z-1bcbed6f` **passes** with
no cleanup errors. [Raw live evidence](RUST-NFS-MOUNT-AUTH-EVIDENCE.json) includes
four debug/release B/B and N/N cases, 20 rejected-before-SQLite initialization
controls, actual nmp enrollment receipts, configurations and exact binary hashes.
Every case proves source nested-mount refusal/409 with no path release or source
mutation, same-ID job-1/202 after original-scope restoration, destination profile
review without a manifest, audited resume, attempt-one commitment and original
claimed inode/hash retention. The producer reuses names only after 202; its newer
bytes survive original-database/enrollment restart and replay.

All four cases then change only per-mount VFS flags while root/namespace/receipt
device/inode/UID/mode remain unchanged. Original-state startup refuses with
SourceRootChanged. Restoring the exact original mount record permits same-job
restart/202/commitment without re-enrollment or touching producer-reused bytes.
The 43 model decisions, parser controls and VFS capability controls also pass in
this run; they remain distinct from actual Rust program evidence.

The retained broad run `nfs-20261019T015840Z-49e49051` passes its six noac transfer
baselines, 12 NFS-state-parent cases and 184 SQLite/state-file command cases, but
**the overall run remains FAILED**: its outage assertion expected production
startup to block on NFS metadata. Production now correctly refuses before remote
I/O. Preserve [that failed run](RUST-NFS-MOUNT-AUTH-BOUNDARY-INITIAL-EVIDENCE.json)
and [its exact fixture sources](RUST-NFS-MOUNT-AUTH-BOUNDARY-INITIAL-DRIVER.json).
Cleanup initially returned EBUSY after restoration; a later **normal** unmount
succeeded, followed by removal of only that run's resources. The
[separate recovery record](RUST-NFS-MOUNT-AUTH-BOUNDARY-RECOVERY-EVIDENCE.json)
preserves this outcome; no forced/lazy unmount was used.

The runner now uses the exact qualification binary for isolated NFS bootstrap,
while production must refuse early. The focused corrected run
`nfs-20261019T021731Z-41c53fb1` **passes**, cleanup errors `[]`; see
[startup evidence](RUST-NFS-MOUNT-AUTH-STARTUP-EVIDENCE.json). It records one blocked
bootstrap child, local Starting status in 1.031 seconds, SIGTERM plus actual
service/child exit before server restoration, no SQLite/readiness, restored root
identity and available source lock. This run explicitly marks transfer/state
scopes NOT_RUN; it does not relabel the prior overall failed run or repeat its
already passing subscopes.

[Final exact driver/Rust archive snapshots](RUST-NFS-MOUNT-AUTH-DRIVER-EVIDENCE.json)
retain SHA-256/Base64 source bytes and both final gate archives. All passed live
case assertions, 40 ELF hashes and current archived inputs are independently
verified. Both engines have no remaining containers; rootful fixture volumes and
networks are removed, leaving only the preexisting toolchain caches/default network.

The [extended lab procedure](NFS-MOUNT-PROFILE-LAB.md#supervised-rust-authorization-extension)
documents exact commands, private network/server/client privileges, declared
root-squashed child exports, ordinary account service/HTTP execution, pre-SQLite
refusals, nested-mount source/destination decisions, original-state retries,
audited resume, selected-flag change/refusal/restoration, and normal cleanup.

The initial production/qualification gates (`20261019T012744Z-b7ec9a6e` and
`20261019T012849Z-a1f597ee-nfs-qualification`) exercise an outdated regression
fixture that declares NFS without a profile. They are retained with raw reports,
failing test logs and exact checksum-verified archives in
[initial gate evidence](RUST-NFS-MOUNT-AUTH-INITIAL-EVIDENCE.json) as failed runs;
the fixture is corrected to provide an explicit declaration while preserving
its original local-fallback refusal assertion. Before final runs, a local newline
helper accidentally truncated edited Rust files; they were restored from the
checksum-verified initial build archive, the two subsequent edits reapplied and
the diff reviewed. No build/test executed the truncated files. Final gate archives
capture the restored, reviewed LF source.

The first live-lab attempt, `mount-profile-20261019T015542Z-b5fe60d7`, failed on
fixture chown after both gate/source checks: the client deliberately lacks CHOWN.
No Rust service case executed and cleanup succeeded. Preserve its
[raw setup failure and exact sources](RUST-NFS-MOUNT-AUTH-SETUP-INITIAL-EVIDENCE.json).
The fixture now creates private directories/configuration as UID/GID 1000 directly,
without adding capabilities.

The next attempt, `mount-profile-20261019T020046Z-201ec229`, completed all model
controls, gate/source checks, five initialization refusals, valid source enrollment
with an nmp fingerprint and actual service readiness. It then failed to insert the
nested tmpfs control: root-squashed/private UID-1000 ancestors prevented setup
lookup. The service stopped and cleanup succeeded; this is not passing live
qualification. Preserve [the raw attempt](RUST-NFS-MOUNT-AUTH-TRAVERSAL-INITIAL-EVIDENCE.json).
The fixture uses reversible execute-only traversal gates on its two owned
ancestors, restoring mode 0700 before program requests; no added capability or
private payload permission relaxation is used.

## Scenarios and remaining work

SC-103/104/105 and supporting custody/replay/review situations plus DOC-03/04/05
are updated without adding or renumbering IDs: 105 SC and six DOC IDs. The roadmap
removes completed integration and retains remaining buffered interruption/death/
synchronization RPC and same-share worker qualification. No earlier noac or
buffered OS-only evidence is relabeled.

FR-03/05 and all eight release gates remain open. The pinned SLES userspace still
shares the modern WSL2 kernel. No old SLES kernel/CPU, NAS firmware, other-client
cache visibility, storage failover/grace/reclaim, persistent media or power-loss
qualification follows from these finite private tmpfs/container cases.

Final non-Rust verification passes: Python syntax, trace-matrix parity, 1,414 local
documentation links, all 105 unique scenario rows and six DOC IDs, exact source
snapshot/archive hashes, JSON and per-file size checks. Staged LF, final newline,
whitespace and conflict-marker checks are required before commit. No Cargo lock
or dependency changes are present. All fixture failures remain explicitly failed
and their later recovery/pass evidence is separate.
