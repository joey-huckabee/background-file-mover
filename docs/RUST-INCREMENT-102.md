# Rust increment 102: incomplete claim replay before HTTP 202

## Scope and changes

SC-136 retains --pre202-replay with --mover --distinct-filesystems. Four native
retained-FD prerequisites precede four debug/release x source LINK/REMOVE cases
for a one-file recording. Source and destination use distinct retained NFS
filesystems on one shared backend; SQLite/ownership stay local. Source-space
admission remains off by default. Set max_retained_jobs=1 only for this finite
new-ID refusal test. No shipping Rust, dependency, API/retry/review policy or
shutdown deadline changes. Production NFS and postcommit private-source cleanup
remain disabled. Multi-file partial handoffs remain unqualified by this increment.

Use existing claim_link_rpc/claim_unlink_rpc pauses. At LINK, complete original
current/nested/data.bin has one link and private data is absent. At REMOVE,
original and private data are complete two-link aliases of the original inode.
Both remain Accepted/non-release, with no destination recording directory.
Stop NFSD, release the existing bounded pause and prove actual D-state linkat/
unlinkat with exact source/private directory descriptors. Artificial test pauses
and HTTP waiter timeout alone are not NFS blocking or command cancellation.

## Measured results

Run `pre202-replay-20261022T122119Z-04f7bf67` passes all four native controls and four mover cases,
freezing seventeen acquisition sources. Same original claim worker/epoch remains
assigned through the outage and finite request burst. Worker UID/GID 1000, zero
capabilities, NoNewPrivs, held local ownership and actual syscall/FD paths are
retained. Original custody and local DB inode/configuration stay unchanged.
Status stays Accepted with source_paths_released=false; retention reports one
job, zero confirmed claims and zero destination attempts. Independent read-only
backing checks prove complete original/private custody and absent delivery.

| Profile | Pending effect | handoff_pending | service_busy | Successful source LINK / REMOVE pairs |
|---|---|---|---|---|
| debug | link | 2 | 5 | 1 / 1 |
| debug | remove | 2 | 5 | 1 / 1 |
| release | link | 2 | 5 | 1 / 1 |
| release | remove | 2 | 5 | 1 / 1 |

Each case retains seven retryable non-release 503 responses: the initial submission
plus six asynchronous requests alternating original and new IDs. At least one
service_busy proves queue refusal. The initial request can time out during the
artificial pause; its timing is not used as proof of NFS blockage. Actual D-state
and the six-request burst after NFSD stops establish the outage case. Timed-out
HTTP waiters do not cancel commands already queued in the existing one-slot queue.

Measured outage intervals are 43.110–46.669 seconds and local
health calls take 1.719–1.844 seconds including fixture overhead.
These finite observations do not establish unrestricted load or endurance bounds.

Restore NFSD before draining users. Retry identical JSON/ID until confirmed
202/job 1/source_paths_released; require original-name absence and only then write
'next recording'. Record confirmation before reuse. The same original worker
actually exits, original private inode/hash is preserved with one link, and the
same coordinator completes attempt-1 verified delivery with a valid manifest.
Newer producer bytes survive. The new ID receives retention_capacity under the
unchanged one-job limit; job 2 is absent. Normal stop/restart with original local
state returns same-ID 202 for committed job 1 and preserves the full manifest hash.
The recorder gains no post-202 polling duty; consumers still wait for the valid
completion manifest. Source-name unlink during claim is separate from disabled
postcommit private-source cleanup.

Independently inspect/redecode 12064 bounded raw RPC records, retaining 1512
unsupported compounds with exact hashes/XIDs. Require successful source LINK to
private 'data' and REMOVE of original 'data.bin'. LINK precedes the outage for
REMOVE-selected cases; selected operations have requests after outage start and
successful replies after restoration. A captured pending request may precede
restoration. Couple operation names/timing with actual directory descriptors and
independent custody. This does not claim exact syscall entry/exit wire intervals,
withheld replies, physical persistence or global delayed-effect settlement.

## Required compatibility, audit and cleanup

Production `20261022T120740Z-d57040d7` passes 211 exact-target tests per profile; qualification
`20261022T120248Z-f719327c-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22,
pinned SLES 12 SP5 userspace, 42 packages and six negative ELF controls each.
Audit forty ELF artifacts and all 62 unchanged Rust inputs. The final live run
references the completed fresh production gate and uses qualification executables
from the preceding identical-source gate while fresh qualification completes.
Independently compare complete source archives and shipping hashes across both sets. No host-only cargo checks
replace these gates.

The independent verifier rejects 89 corrupted mover/storage proofs, runs
seven decoder regressions and two pre-provisioning CLI refusal controls, and checks
native retained-FD recovery, storage continuity, exact descriptors/security,
HTTP/custody/ownership/handoff ordering, raw successful LINK/REMOVE pairs,
original-state recovery, exact live/fresh artifacts and normal cleanup.

The [initial infrastructure evidence](RUST-NFS-PRE202-REPLAY-INITIAL-EVIDENCE.json)
preserves Podman SSH handshake closures during a production-gate artifact copy
and fixture inventory before provisioning or native/mover cases. Retain exact
failed reports, gate source archive and seventeen acquisition files. Cleanup
reports no error; the fixture had created no resources. Retry unchanged code and
independently verify source identity; never rewrite failed reports as passing.

The [second retained acquisition](RUST-NFS-PRE202-REPLAY-SECOND-EVIDENCE.json)
passed native controls and self-reported debug LINK success, but REMOVE failed
before outage: the backing reader's presence test ran as root with all capabilities
dropped and could not traverse UID-1000 private directories. A false absent result
is not custody evidence. Retain exact failed report, seventeen sources and empty
rootful inventory. Use UID 1000 for backing presence/absence checks and a positive
destination-parent directory check, then rerun the complete native/mover matrix.
The auditor reconstructs the exact two-check-only source correction and validates
both failed snapshots. No runtime Rust, permissions policy, retry or deadlines
change. The final corrected cases supply the supported finite evidence.

Final inventory at 2026-10-22T12:39:11.884899+00:00 confirms zero
containers on both engines and unchanged baseline full volume metadata/network
names. Restore before draining, normally unmount NFS, remove owned users/backend,
verify/remove keeper last, then owned role/parent volumes and network. No forced/
lazy unmount, VM reset or global NAS/cgroup/host change is used.

Read the [step-by-step lab](NFS-PRE202-REPLAY-LAB.md),
[raw acquisition](RUST-NFS-PRE202-REPLAY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-PRE202-REPLAY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json) and
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json).

## Limits and next work

This qualifies selected one-file incomplete namespace effects and replay/queue
refusal with the coordinator alive. It does not qualify multi-file partial
handoffs, missing-file recovery, source substitution, independent server failures,
coordinator death or larger concurrent queues. Shared modern WSL2 kernel and
retained bounded tmpfs cannot establish old SLES kernel/client or maintenance
systemd, NetApp/Isilon, abrupt NAS/VM reboot, persistent disk/power-loss durability,
100 GB throughput or endurance. Local exit is not global remote-settlement proof.

Next qualify multi-file partial-handoff replay and broader source-change refusal,
independent endpoint/outage-duration and capacity/load cases. Keep SC-136/DOC-01–05,
all eight release gates open and production NFS/private-source cleanup disabled.
Registration/S3/offline repair/DOC-06 remain deferred.
