# Rust increment 74: buffered NFS source claims interrupted before HTTP 202

## Scope and acceptance

Qualify eight NMP-41B source claim cases: `claim_link_rpc` (custody LINK) and
`claim_unlink_rpc` (removal of the original producer name), debug/release, on
same-share and separate-share roots. Both endpoints are NFS; original local
state/configuration/enrollment must survive. Claim name removal relocates the
original source into private custody; it is not post-delivery source cleanup.
Production NFS and source deletion remain disabled.

The mount-profile runner gains `--buffered-claims` and a dedicated helper and
independent verifier. Existing Rust checkpoints suffice; there is no Rust,
dependency, schema, shipping executable, retry/review or shutdown-deadline change.
The isolated root observer needs SYS_PTRACE and DAC_READ_SEARCH in addition to
mount-setup SYS_ADMIN. Actual movers/workers/controllers/HTTP run UID/GID 1000,
zero effective/permitted/inheritable capabilities and NoNewPrivs=1.

Before LINK, require the original one-link producer inode and no custody data;
before REMOVE, require the same original inode at both names with two links.
Submit asynchronously and keep producer files/parents unchanged until 202.
After stopping the owned NFSD, release the checkpoint and prove actual D-state
`linkat`/`unlinkat` using syscall number, parent directory descriptors and flags.
Require Accepted/unreleased status, no destination recording, a retryable 503
for the original submission, responsive health/status and no replacement worker.

Kill only the coordinator; sample surviving-worker ownership twice and require
same-state service/initialize/direct-transfer refusal. Kill the worker only after
those probes, restore storage, confirm actual old-thread exit and NoActiveOwner,
then inspect surviving source aliases. At least one original inode/content alias
must remain. Recover using original state and the same submission ID: job 1/202,
then allow producer reuse and require normal delivery, valid manifest, attempt 1,
retained custody and no second job. Clean stop/restart/replay must preserve the
same publications, source inode and newer producer bytes.

## Results

Final run `mount-profile-20261019T122856Z-0866afa8` **passes** all eight actual worker cases,
43 independent model/inventory controls and 10 exact driver snapshots,
with cleanup_errors=[]. [Raw evidence](RUST-NFS-BUFFERED-CLAIM-EVIDENCE.json)
retains configuration/mount/device records, original source and custody namespace
observations, worker security, pending syscall descriptors/flags, HTTP responses,
local controls/guard/contenders, old-thread exit, recovery/replay and service logs.
The client reports `glibc 2.22` on shared modern kernel
`6.18.33.2-microsoft-standard-WSL2`; this is not the SLES 12 kernel.

| Point | Same-share debug | Same-share release | Separate-share debug | Separate-share release |
|---|---|---|---|---|
| claim_link_rpc | Passed | Passed | Passed | Passed |
| claim_unlink_rpc | Passed | Passed | Passed | Passed |

All four LINK cases prove D-state linkat 265 with original producer parent,
private custody parent and zero flags; all four REMOVE cases prove D-state
unlinkat 263 with original producer parent and zero flags. NFSD has zero threads.
All submissions remain Accepted with paths unreleased and return retryable 503,
never premature 202. No destination recording exists before recovery begins. All 24 competing service/initialize/direct-transfer commands refuse
while old workers survive coordinator death. Actual old-thread exit is confirmed
before restart. All eight original-state recoveries return job 1/202, then permit
producer reuse, commit on attempt 1, retain the original source inode/content,
validate the manifest and pass another clean stop/restart/replay without job 2.

Maximum observed individual outage requests, including host copy/Podman overhead:
health 2.391 seconds and job status
2.375 seconds; both remain below five seconds.
The maximum combined diagnostic cost is 4.766 seconds.
These finite observations are not universal workload/latency guarantees.
Raw flock is contended in 16/16 orphan samples; 0 cases observe early raw-lock
closure. Contender probes precede worker SIGKILL; afterwards the harness confirms
exit, adding no terminating/free-raw-guard contender or NAS-settlement scope.
Ordinary workers retain UID/GID 1000, zero active capabilities and NoNewPrivs=1;
only the isolated root observer has the two additional syscall-observation caps.

Both fresh mandatory SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T122734Z-bb8afef9` | 211 / 211 | 20 |
| Qualification | `20261019T122745Z-65ab87ea-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain cargo-zigbuild
GNU/glibc 2.22 builds, ELF interpreter/library/symbol auditing, six negative
controls per configuration, exact SLES-userspace target execution, formatting/
Clippy and 42 locked dependencies. There is one shipping executable; counts
include tests and both profiles.

The live matrix uses passing source-identical increment-73 gates
`20261019T112807Z-9869189f` and
`20261019T112807Z-23cb6dbb-nfs-qualification` while fresh gates run. The
[independent audit](RUST-NFS-BUFFERED-CLAIM-INPUT-EVIDENCE.json) verifies all 62
Rust entries in fresh/live archives, all forty fresh artifact hashes and byte
equality to live inputs, all ten driver snapshots/current bytes, complete tuple
coverage and acceptance invariants. It retains fresh source archives and the
exact verifier source; gzip metadata may differ while Rust entry and executable/
test bytes must match. Earlier evidence is preserved. No Rust or Cargo.lock
changes were needed.

Independent post-run inventory confirms both Podman engines have no containers.
The rootful engine retains only pre-existing `file-mover-rustup-1-99` and
`file-mover-cargo-registry` cache volumes and the default `podman` network.
Owned export volumes/networks are removed; cached images remain available.
Cleanup uses normal NFS unmounts without host/NAS data or configuration changes.

## Reproduction and limits

Follow the [step-by-step claim lab](NFS-BUFFERED-CLAIM-LAB.md). Retain exact
driver/verifier inputs, live/fresh source entry and artifact comparisons, actual
namespace/security/control/exit/recovery observations and cleanup results.

These are client syscall/outage/process-death cases, not server-completion-with-
reply-withheld proof. One client and one controlled kernel server share a modern
WSL2 kernel; two exports still have one joint outage domain and volatile tmpfs.
No pending-sync/COMMIT, server reboot/failover, physical-media/power, independent
NAS/cache, old SLES kernel, universal timing or production-scale claim follows.
Contender probes precede worker SIGKILL; afterwards the harness confirms exit.
A free raw lock, process exit or timer is not remote-effect settlement authority.

SC-109 feeds DOC-01–05; preserve all earlier IDs and DOC-06 deferral. All eight
first-release gates remain open; production NFS and source deletion stay off.
