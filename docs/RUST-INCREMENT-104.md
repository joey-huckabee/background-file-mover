# Rust increment 104: source-change refusal after a partial handoff

## Change and finite scope

SC-138 retains --source-change-refusal with --mover --distinct-filesystems.
Four native recovery prerequisites precede four debug/release x second-file inode
replacement/size-change cases. No Rust, dependency, production API, retry/review
policy or shutdown deadline change. Production NFS and postcommit private-source
cleanup remain disabled. Source-space admission stays off by default.

Submit earlier/first.bin (23 bytes) then nested/data.bin (2 MiB + 17 bytes), without
caller size assertions. The service uses its own durable observation. Existing
qualification claim_apply/CLAIM_INDEX=1 pause lets the first claim finish and the
second immutable intent persist before effects. Deliberately violate recorder
immutability: replace the second inode with an identical content/size/UID/mtime/
link-count copy, or append X on the same inode while preserving its old timestamp.
Keep the old inode/backup under fixture-original. Both faults occur on healthy
NMP-41B NFS; this is not a new outage/death/withheld-reply qualification.

## Actual results

Run `source-change-refusal-20261022T183501Z-32382412` passes all four native controls and four mover cases with
seventeen frozen acquisition scripts. Client stat/encoded immutable intent and
independent backing hashes/inodes prove the isolated difference. First/private
original remains intact with one link; second private data and destination job
remain absent. Neither violation permits whole-set 202 or producer path reuse.

| Profile | Isolated second-file change | Initial HTTP | Unpaused 409 refusals | Immutable claim snapshots |
|---|---|---|---|---|
| debug | inode | 503 | 6 | 4 |
| debug | size | 503 | 6 | 4 |
| release | inode | 503 | 6 | 4 |
| release | size | 503 | 6 | 4 |

The initial HTTP waiter can time out as retryable 503 handoff_pending while the
fixture prepares evidence; this is neither cancellation nor successful handoff.
After releasing the pause, the actual original worker exits and logs
apply: blocked: relocation object changed. Normal stop succeeds. Across two
unpaused restarts, six identical-ID/body requests per case return existing
non-retryable 409 recording_blocked, job 1, source_paths_released=false.
These refusals cannot be attributed to a stale one-shot qualification pause.

Durable status stays Accepted/AwaitingClaims with first file Claimed, second
Pending, one confirmed claim, no destination attempts/manifest and unchanged zero
review epochs. Existing API refusal does not automatically set ReviewRequired.
No automatic repair, new intent or delivery retry policy is added. First/private,
changed submitted file and saved original/backup stay unchanged across restarts.
Local database inode/config hash, private-root identities and healthy server/
keeper continuity remain unchanged; local ownership is held until normal stop.

Capture four quiescent/stopped local SQLite/WAL copies per case. Hash each source
before copying and recheck every source hash afterward; read only the copies.
Independent audit extracts and reopens all sixteen snapshots, requiring identical
complete original claim rows, done flags [1,0], one job/two files/two claims and
zero transfers/manifests. The pending second source identity is never replaced
by the changed file's identity. This is fixture evidence collection, not the
implementation of deferred product offline inspection/repair.

Independently re-decode 6724 bounded raw RPC records, retaining 1072 unsupported
compounds as non-positive evidence. First source LINK and first.bin REMOVE complete
before mutation. No decoded data.bin REMOVE appears. Wire decoding alone cannot
prove global absence of remote effects; actual unchanged backing custody, absent
private/destination data, refusal diagnostics and copied SQLite evidence establish
the selected result. No blocked-syscall, exact syscall interval, withheld-reply,
physical durability or global delayed-effect settlement claim is made.

## Compatibility, audit and cleanup

Production `20261022T182946Z-dfe48216` passes 211 exact-target tests per profile; qualification
`20261022T182945Z-5f06a0b5-nfs-qualification` passes 213 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22,
fmt/clippy and pinned SLES 12 SP5 userspace. Forty Rust ELFs are independently
audited; 42 locked packages and six negative ELF controls per gate stay unchanged.
The live run uses previously completed passing gate artifacts while fresh gates
run. Full used/fresh archives match 62 unchanged Rust inputs and shipping
binary hashes are byte-identical. No unfinished gate directory is used.

The audit rejects 105 corrupted case/storage proofs, passes seven RPC decoder
regressions and two finite CLI refusals before provisioning. The
[initial audit failure](RUST-NFS-SOURCE-CHANGE-AUDIT-INITIAL-EVIDENCE.json) preserves
exact raw acquisition/verifier dependencies/diagnostics: Windows sandbox permissions
refused default temporary-directory SQLite extraction. Use a workspace-owned
extraction directory and explicitly close SQLite handles before cleanup. The
corrected full audit uses identical raw acquisition; no fixture/Rust/policy changes.
Final inventory at
2026-10-22T18:54:54.974171+00:00 confirms zero containers on both engines
and unchanged baseline full volume metadata/network names. Restore before draining,
normally unmount NFS and remove owned users/backend; verify/remove keeper last,
then role/parent volumes/network. No forced/lazy unmount, VM reset or global changes.

Read the [step-by-step lab](NFS-SOURCE-CHANGE-LAB.md),
[raw acquisition](RUST-NFS-SOURCE-CHANGE-EVIDENCE.json),
[independent audit](RUST-NFS-SOURCE-CHANGE-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json) and [qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json).

## User meaning and remaining limits

Recorder must keep every submitted file/parent unchanged until confirmed whole-set
202. A 409 refusal requires investigation while preserving original local state,
private custody and submitted files; it is not permission to reuse paths or to
recreate the database/new ID to bypass the original intent. No automatic repair
procedure is supplied. Recorder gains no post-202 delivery-monitoring duty.

Selected pre-effect inode/size changes do not qualify other source/parent changes,
other timing windows, same-inode/same-size timestamp-preserving tampering, mutation
during outage/death, arbitrary file counts, independent NAS failure or unrestricted
load. Modern shared WSL2 kernel and retained tmpfs do not qualify old SLES kernel/
client/maintenance systemd, NetApp/Isilon, abrupt NAS/VM reboot, persistent disk/
power loss, 100 GB throughput or endurance. Metadata identity is not cryptographic
proof of producer immutability. Keep all eight release gates open and production
NFS/private-source cleanup disabled; registration/S3/offline repair/DOC-06 deferred.
