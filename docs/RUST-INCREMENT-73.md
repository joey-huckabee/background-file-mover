# Rust increment 73: buffered recovery after staging removal, before directory sync

## Scope and acceptance

Qualify eight NMP-41B process-crash cases at `file_unlink_sync` and
`manifest_unlink_sync`, across same/separate-share and debug/release. These
existing Rust hooks run after staging unlink returns and before the old staging
directory's following sync. The final owned name has one link and the staging
name is already absent. Manifest cases must have a valid manifest and complete
payload; payload-only cases must not expose a manifest.

The retained mount-profile runner gains `--buffered-post-unlink`. It reuses the
publication helper and verifier through explicit mode parameters; the earlier
sixteen-case matrix remains available. This pause-only matrix adds no syscall-
observer capabilities: the root client has mount-setup SYS_ADMIN and ordinary
workers remain UID/GID 1000, zero active capabilities and NoNewPrivs. No Rust,
dependency, schema, shipping executable, retry/review or shutdown-deadline change
is introduced. Production NFS and source deletion remain disabled.

Require original source/database/configuration/enrollment evidence and 202 before
producer-path reuse. During joint NFSD outage keep the pause unreleased, stop
the worker, check local health/status and kill only the coordinator. Require
old-worker ownership and prompt same-state service/initialize/direct-transfer
refusal, then kill the worker and restore storage. Confirm actual old-thread exit
before any restart. Staging must remain absent and the final one-link inode and
content unchanged. Original-state recovery must complete on attempt 1; a further
clean stop/restart/replay must preserve the job, original publications/manifest,
source custody and newer producer bytes without re-enrollment or policy bypass.

## Results

Final run `mount-profile-20261019T113736Z-cdc838f9` **passes**: eight actual worker cases,
43 independent model/inventory controls, 9 exact driver snapshots and
cleanup_errors=[]. [Raw evidence](RUST-NFS-BUFFERED-POST-UNLINK-EVIDENCE.json)
retains configuration/mount/device records, absent staging and final one-link
inode/content observations, worker security, local controls/guard/contenders,
old-thread exit, recovery, replay and service logs. The client reports
`glibc 2.22` on shared kernel `6.18.33.2-microsoft-standard-WSL2`; the kernel is not SLES 12's.

| Point | Same-share debug | Same-share release | Separate-share debug | Separate-share release |
|---|---|---|---|---|
| file_unlink_sync | Passed | Passed | Passed | Passed |
| manifest_unlink_sync | Passed | Passed | Passed | Passed |

All eight cases retain the unreleased after-unlink pause and a T-state stopped
worker while NFSD is down. Staging is absent and the original final name has one
link before coordinator death and after old-worker exit. All 24 competing
service/initialize/direct-transfer commands refuse. Actual old coordinator/worker
thread exit is confirmed before restart. All eight recover on attempt 1, preserve
original final allocation/content (including manifests in manifest cases), retain
source custody and newer producer bytes, and pass another clean restart/replay.
Payload-only interruptions expose no completion manifest before normal recovery.

Maximum observed individual outage requests, including host copy/Podman overhead:
health 1.937 seconds and job status
1.922 seconds. Each is below five seconds;
their maximum combined diagnostic cost is 3.750 seconds.
This is finite measured behavior, not a universal workload/latency guarantee.

Raw flock is contended in 16/16 orphan samples; 0 cases observe early raw-lock
closure. These probes occur before worker SIGKILL; after it the harness waits for
exit. No new terminating/free-raw-guard or NAS-settlement branch is claimed.
The client adds no syscall-observer capabilities; ordinary workers have UID/GID
1000, zero effective/permitted/inheritable capabilities and NoNewPrivs=1.

Both fresh mandatory SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T112807Z-9869189f` | 211 / 211 | 20 |
| Qualification | `20261019T112807Z-23cb6dbb-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) reports retain pinned
cargo-zigbuild GNU/glibc 2.22 builds, ELF interpreter/library/symbol auditing,
six negative controls per configuration, exact SLES-userspace target execution,
formatting/Clippy and 42 locked dependencies. There is one shipping executable;
artifact counts include tests and both profiles.

The live matrix uses passing source-identical increment-72 inputs
`20261019T043611Z-20b3d700` and
`20261019T043611Z-3152e430-nfs-qualification` while fresh gates run. The
[independent input audit](RUST-NFS-BUFFERED-POST-UNLINK-INPUT-EVIDENCE.json)
verifies all 62 Rust entries in fresh/live archives, all forty fresh artifact
hashes and byte equality to live inputs, all nine driver snapshots/current bytes,
complete tuple coverage and acceptance invariants. It retains fresh source
archives and the exact verifier source; gzip metadata may differ while Rust
entry and executable/test bytes must match. Earlier increment-72 final/initial
and input evidence is preserved. No Rust source or Cargo.lock changed.

Independent post-run inventory confirms both Podman engines have no containers.
The rootful engine retains only pre-existing `file-mover-rustup-1-99` and
`file-mover-cargo-registry` cache volumes and the default `podman` network.
Owned export volumes/networks are removed; cached images remain available.
Cleanup uses normal NFS unmounts with no host/NAS data or configuration changes.

Initial run `mount-profile-20261019T112925Z-55fc2173` remains **FAILED** in
[the original report](RUST-NFS-BUFFERED-POST-UNLINK-INITIAL-EVIDENCE.json), with
cleanup_errors=[]. Its debug same-share payload case passes, but the following
manifest case fails before coordinator-death acceptance because the harness
compares two sequential HTTP requests, including separate host copy/Podman
launch overhead, to one five-second aggregate budget. The measured aggregate is
5.344 seconds; the initial script does not retain individual timings, so it does
not prove whether either request exceeded five seconds. The corrected harness
measures and requires each request independently below five seconds and retains
their sum as diagnostic cost. No Rust timeout, shutdown deadline or recovery
behavior is changed. The initial partial matrix is not complete qualification.

## Reproduction and limits

Follow the [step-by-step post-unlink lab](NFS-BUFFERED-POST-UNLINK-LAB.md) for
infrastructure, exact gate/runner/verifier commands, checkpoint ordering,
ownership/recovery/replay observations and normal cleanup.

Same/separate-share roots use one controlled server, a joint outage, volatile
tmpfs and the shared modern Podman/WSL2 kernel. A returned unlink paused before
sync is a process-crash boundary with live server/cache retained. No actual
pending fsync/COMMIT, successful RPC reply withheld, server/power persistence,
independent NAS/cache, old-kernel or production-scale/endurance claim follows.
Contender probes precede worker SIGKILL; after it the harness confirms old-thread
exit before starting anything. Raw guard observations are reported as measured,
not remote-settlement authority or new terminating/free-guard qualification.

SC-108 feeds DOC-01/02/03/04/05. Preserve earlier IDs and the separate increment-72
evidence. Keep remaining buffered bootstrap/claim, actual sync/RPC failure,
capacity/load and deployment qualification open. All eight release gates stay
open; production NFS and source deletion remain disabled.
