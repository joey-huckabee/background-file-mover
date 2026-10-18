# Rust increment 63: publication namespace and synchronization interruptions

Scope recorded 2026-10-18 before execution on `feature/rust-transfer-coordinator`.
Production NFS and source deletion remain disabled. No dependency, retry/review,
ownership or shutdown deadline change is intended. Only qualification builds
receive additional local pause points in owned file/manifest relocation.

## Finite cases and pass conditions

Twelve cases: debug/release times file/manifest times three boundaries:

1. Link returned, before opening/synchronizing the new name and directory.
2. Immediately before unlinkat, release into destination NFSD outage and require
   actual x86_64 unlinkat syscall 263, D state and staging-parent descriptor.
3. Unlink returned, before synchronizing the old parent directory.

Both source and destination use separate controlled NFSv4.1 endpoints; database,
control and epoch stay local. Measure owned aliases/inode/hash before outage.
After destination-only outage, preserve healthy-source access, Claimed state,
202 replay and exactly one delivery worker. Kill the coordinator. For actual
unlink stalls require surviving-owner refusal via local status and an alternate
port contender. Kill only the known worker, restore servers, and confirm every
old thread exited before original-state restart. Require exact owned publication
inode/hash, attempt one, correct manifest, no staging aliases/new allocation,
unchanged original database/enrollment/source custody and producer-reused path.
Retain baseline, local-state refusal, lock and isolated-startup regression checks.

Affected scenarios: new SC-097, supporting SC-018/039/040/050/092/093 and DOC-03/04/05.

## Evidence limits

An observed blocked unlinkat is a syscall boundary, not proof of a particular
NFS RPC reaching or settling at the server. The other eight cases crash while
paused after a namespace effect returned and before synchronization; they do
not interrupt an in-flight fsync RPC. Shared modern WSL2 kernel, controlled tmpfs
servers and one client do not qualify persistent disk, power failure, physical
NAS isolation, old SLES kernel or actual production mount/security policies.
All first-release gates remain open. In-flight link/sync RPCs remain outstanding.

## Results

`nfs-20261018T174712Z-059936f1` passes all twelve finite cases, without cleanup errors.
See [raw evidence](RUST-NFS-PUBLICATION-SYNC-EVIDENCE.json) and
[the step-by-step lab](NFS-PUBLICATION-SYNC-LAB.md).

| Profile | Point | Interruption evidence | Staging after old exit | Result |
|---|---|---|---|---|
| debug | `file_link_sync` | effect_returned_before_sync | present | PASS |
| debug | `file_unlink` | in_flight_unlinkat_syscall | present | PASS |
| debug | `file_unlink_sync` | effect_returned_before_sync | absent | PASS |
| debug | `manifest_link_sync` | effect_returned_before_sync | present | PASS |
| debug | `manifest_unlink` | in_flight_unlinkat_syscall | present | PASS |
| debug | `manifest_unlink_sync` | effect_returned_before_sync | absent | PASS |
| release | `file_link_sync` | effect_returned_before_sync | present | PASS |
| release | `file_unlink` | in_flight_unlinkat_syscall | present | PASS |
| release | `file_unlink_sync` | effect_returned_before_sync | absent | PASS |
| release | `manifest_link_sync` | effect_returned_before_sync | present | PASS |
| release | `manifest_unlink` | in_flight_unlinkat_syscall | present | PASS |
| release | `manifest_unlink_sync` | effect_returned_before_sync | absent | PASS |

Four actual unlinkat stalls and eight crashes after namespace effects before sync
recover on attempt one, preserving original publication/payload inode/hash,
source custody, local database/enrollment and producer-reused paths. Both NFS
roots remain on distinct controlled endpoints, with a healthy-source probe while
destination NFSD is zero. Each live coordinator remains ready, status Claimed
and same-ID replay 202, without false commitment. Four alternate-port contenders
reach the ownership guard and are refused after coordinator death; each blocked
orphan reports OwnerUnavailable/2. All known old threads exit before replacement.
Recovery removes only owned staging aliases and validates the nested manifest;
claimed source remains retained with cleanup false. Final status is NoActiveOwner.

In all four observed unlink stalls, the staging alias is still present after
old exit. All four worker leaders are already Z at the post-KILL/pre-restoration
sample; every known old thread is checked again after restoration. These cases
do not establish a surviving uncancellable post-KILL worker or shutdown-deadline
branch. They establish client-syscall interruption and owned alias recovery,
not an accepted server unlink whose reply was lost.

Health takes at most 1.796 seconds, job status 1.844 and claimed replay 1.828,
including Podman overhead; state-file refusals take at most 0.953 seconds.
These finite small-fixture measurements are not production latency guarantees.

The command also passes six transfer baselines, twelve NFS state-parent refusals,
184 state-file refusal checks with fourteen preserved fixtures, inherited-lock
and isolated source-bootstrap shutdown regressions. Production NFS refusal
remains enforced. Restoration precedes normal unmount and owned-resource removal.

Fresh production gate `20261018T172247Z-44e075c7` passes 204 tests per profile;
qualification gate `20261018T172302Z-f4ecf60d-nfs-qualification` passes 205 per profile. Each audits
20 ELF artifacts and six negative controls, pinned GNU/glibc-2.22 target, exact
SLES container tests, formatting/Clippy and the locked 42-package dependency graph.
Current 61-file source inventories and exact artifact/selected-driver hashes
are checked. The only Rust change adds compile-time qualification-only pauses;
production does not acquire new NFS support or cleanup authority. The production
release service is byte-identical to increment 62; the debug service has a newly
recorded hash.

The syscall observation identifies client unlinkat, not an on-wire RPC or server
settlement. Pre-sync crashes retain live-server tmpfs/cache state and cannot
establish disk/power-loss durability. No in-flight link/fsync RPC, server reboot,
actual NAS, old-kernel or systemd qualification is claimed. All eight release
gates remain open.


Independent final inventory confirms no containers, no fixture volumes/networks,
only the two shared Rust toolchain/registry caches and default podman network.
The VM remains `0::/`; pre-existing nfs/nfsd modules remain loaded. No systemd
bootstrap, VM boot change, new server image, module load or package experiment
was needed. The cached server image is
`90884509240d53671958810ac7ae1971b7cdfffda3d4135ce42cc39bf0bc3e69`.
