# Rust increment 103: multi-file partial handoff replay

## Change and finite scope

SC-137 retains --partial-handoff-replay with --mover --distinct-filesystems.
Four native retained-FD prerequisites precede four debug/release x second-file
source LINK/REMOVE cases. Submit two complete files in different subfolders, in
order: earlier/first.bin (23 distinct bytes), nested/data.bin (2 MiB + 17 bytes).
The first finishes private claiming while the second still prevents HTTP 202.
Source/destination use distinct retained NFS filesystems on one shared backend;
SQLite/ownership/rendezvous stay local. max_retained_jobs=1 tests finite new-ID
refusal; source-space admission stays off. Production NFS and postcommit private
source cleanup stay disabled. API, retries, review and shutdown deadlines do not change.

The qualification-only FILE_MOVER_QUALIFICATION_CLAIM_INDEX selector scopes a
zero-based index to apply_claim_effect. Index 0 runs normally; index 1 pauses at
the existing claim_link_rpc/claim_unlink_rpc rendezvous. A thread-local guard
restores prior scope on drop. No selector preserves existing hooks; malformed or
out-of-range indices fail the selected qualification hook. The scope, selector
and regression test compile out of production. Dependencies and the existing
one-shot pause/60-second budget stay unchanged.

## Measured results

Run `partial-handoff-replay-20261022T165236Z-abbc4e46` passes four native controls and four actual mover cases;
seventeen acquisition scripts are frozen. First original name is absent, but its
complete original inode/hash stays in private 1-0/data with one link. Second-file
LINK starts with complete one-link original and absent private 1-1/data; REMOVE
starts with complete two-link original/private aliases. Both remain Accepted with
source_paths_released=false, one confirmed claim, zero destination attempts and
no destination recording directory. Independent read-only backing checks use
UID/GID 1000 and positive directory access before absence assertions.

Stop NFSD, release the artificial pause and prove actual D-state linkat/unlinkat
with the second source-parent descriptor and private 1-1 directory for LINK.
The same UID/GID-1000, capability-free, NoNewPrivs worker and ownership epoch stay
assigned through initial plus six-burst requests. Local health/status, held guard,
DB inode/config hash and complete custody stay unchanged. Every response is a
retryable non-release 503; service_busy proves finite queue refusal. HTTP waiter
timeout does not cancel an already queued command or authorize path reuse.

| Profile | Second pending effect | handoff_pending | service_busy | Outage seconds |
|---|---|---|---|---|
| debug | link | 2 | 5 | 46.256 |
| debug | remove | 2 | 5 | 44.96 |
| release | link | 2 | 5 | 47.14 |
| release | remove | 2 | 5 | 46.781 |

Health calls take 1.734-1.813
seconds including fixture overhead. These are finite observations, not general
concurrency or endurance bounds. New-ID requests use a missing relative name;
this does not qualify valid new-file acceptance during an outage.

Restore before draining. Identical JSON/ID yields confirmed 202/job 1 for the
complete set before either producer path is reused. The original worker actually
exits and the same coordinator delivers both originals on attempt 1, preserves
subfolders and original private inodes/hashes, and commits the exact two-file
manifest. Both newer producer files survive. New ID gets retention_capacity under
the fixed one-job limit; job 2 is absent. Normal stop/restart with original config/
state replays committed job 1/202 and preserves full manifest hash, both private
payloads and newer producer files. Recorder gains no post-202 monitoring duty;
consumers wait for the valid manifest. Source-name unlink while claiming is
separate from disabled postcommit private-source cleanup.

Independently re-decode 18276 bounded raw RPC records, retaining 2198 unsupported
compounds as non-positive evidence. Successful first-file REMOVE precedes outage;
distinct source LINK filehandle signatures distinguish the claims. Selected second
LINK/REMOVE requests follow outage start and successful replies follow restoration;
REMOVE-selected cases have preceding LINKs complete before outage. Combine wire
evidence with actual descriptors, backing custody and claim counts. This is not
withheld-reply proof, exact syscall entry/exit timing or global remote settlement.

## Compatibility, audit and cleanup

Production `20261022T162835Z-8d5858f4` passes 211 exact-target tests per profile. Qualification
`20261022T162835Z-9416b889-nfs-qualification` passes 213 per profile, including selector scoping/invalid-index coverage.
Both use locked cargo-zigbuild GNU/glibc 2.22 and pinned SLES 12 SP5 userspace;
fmt/clippy pass, forty Rust ELFs are independently re-audited, 42 locked packages
stay unchanged and six negative ELF controls per gate pass. Full source archives/
artifact hashes match 62 current Rust inputs. Independent audit rejects
113 corrupted case/storage proofs, passes seven RPC decoder regressions and
two finite CLI refusal controls before provisioning.

Initial gates rejected two rustfmt layouts before compilation/testing. Preserve
exact failed reports, source archives and diagnostics in the [initial evidence](RUST-NFS-PARTIAL-HANDOFF-INITIAL-EVIDENCE.json).
Audit reconstructs the exact two formatting corrections; failures are not passing evidence.

The [second acquisition](RUST-NFS-PARTIAL-HANDOFF-SECOND-EVIDENCE.json) passed native
controls before the concurrently running qualification release gate wrote its final
report. Artifact loading correctly refused; no Rust NFS case ran. Preserve the
failed report/seventeen sources, wait for both gates and verify baseline cleanup.
The complete unchanged-source retry supplies the final native/mover evidence.

Inventory at 2026-10-22T17:10:45.018640+00:00 confirms zero containers
on both engines and unchanged baseline full volume metadata/network names.
Restore before draining, normally unmount NFS, remove owned users/backend, verify/
remove keeper last, then owned role/parent volumes/network. No forced/lazy unmount,
VM reset or global NAS/cgroup/host changes.

Read the [step-by-step lab](NFS-PARTIAL-HANDOFF-LAB.md),
[raw acquisition](RUST-NFS-PARTIAL-HANDOFF-EVIDENCE.json),
[independent audit](RUST-NFS-PARTIAL-HANDOFF-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json) and [qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json).

## Limits and next work

Selected two-file cases with a live coordinator do not qualify arbitrary file
counts/boundaries, missing-file recovery, source changes, independent server
failures, coordinator death or unrestricted load. Shared modern WSL2 kernel and
bounded retained tmpfs do not qualify old SLES kernel/client/maintenance systemd,
NetApp/Isilon, abrupt NAS/VM reboot, persistent disk/power loss, 100 GB throughput
or endurance. Local exit is not global delayed-effect settlement proof.
Next qualify source-change refusal, remaining multi-file boundaries and independent
endpoint/outage-duration/capacity cases. Maintain SC-137/DOC-01-05 and eight open
release gates. Production NFS/private-source cleanup remain disabled;
registration/S3/offline repair/DOC-06 remain deferred.
