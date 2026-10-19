# Rust increment 75: buffered enrolled and populated startup recovery

## Scope and acceptance

Qualify eight buffered NMP-41B startup cases: enrolled-empty and populated with
an unfinished transfer, debug/release, same-share and separate-share roots.
Source and destination are NFS; database, configuration, guard and epoch remain
local. Production NFS and post-delivery source deletion remain disabled.

The retained mount-profile runner gains `--buffered-bootstrap`, a dedicated
helper and independent verifier. Existing Rust behavior and qualification hooks
suffice; no Rust, dependency, schema, shipping executable, retry/review or shutdown
setting changes are introduced. Isolated root observation adds SYS_PTRACE and
DAC_READ_SEARCH to mount-setup SYS_ADMIN. Movers/workers/controllers/HTTP run as
UID/GID 1000, no active capabilities, NoNewPrivs=1.

Populate four fixtures by accepting job 1/202 and pausing copy after 1 MiB.
Only then reuse producer paths. Kill the seed coordinator before the worker,
confirm exit and retain the original WAL and one partial allocation. Record
original source/database/configuration/enrollment/destination evidence. The four
enrolled-empty fixtures retain their original initialized database and receipt.

Use hard buffered mounts with ordinary attribute maxima explicitly fixed at
60 seconds. Stop owned NFSD and age caches for at least 65 seconds before startup;
record mountstats and elapsed time without host cache flushing or remounting.
This is fixture cache aging, not a changed service shutdown/startup deadline.
Require an actual D-state bootstrap worker, pending syscall and NFS/RPC kernel
stack or wait-channel evidence, local Starting status and a connected health
request with no ready response. Do not infer blocking from a local pause.

Kill only the coordinator. Require surviving-worker ownership in two samples
and same-state service/initialize/direct-transfer refusal with an alternate
listener. Kill the worker only after probes; restore storage and confirm actual
old-thread exit and NoActiveOwner before restart. Local SQLite/WAL/sidecars and
configuration must match before/during/after blocked bootstrap; source/receipt/
binding/partial evidence must match before recovery begins. Do not re-enroll.

Recover using original state and IDs. Enrolled-empty reaches custody/job 1/202
before producer reuse and commits on attempt 1. Populated replay returns job 1/202,
commits on attempt 2 and retains the exact old partial inode/size/hash. Both must
preserve source inode/content, database inode, enrollment and destination binding,
newer producer bytes and valid manifest. A clean stop/restart/replay must retain
those publications and partials and create no second job.

## Results

Final run `mount-profile-20261019T130338Z-1a6b077c` **passes** all eight actual worker cases,
43 independent model/inventory controls and 12 exact driver snapshots,
with cleanup_errors=[]. [Raw evidence](RUST-NFS-BUFFERED-BOOTSTRAP-EVIDENCE.json)
retains cache/mount/device records, closed-state/source/destination snapshots,
actual bootstrap command/security/syscall/kernel wait, readiness/control/guard/
contender observations, old-thread exit, original-state recovery/replay and logs.
The client reports `glibc 2.22` on shared modern kernel
`6.18.33.2-microsoft-standard-WSL2`; this is not SLES 12's kernel.

| State | Same-share debug | Same-share release | Separate-share debug | Separate-share release |
|---|---|---|---|---|
| Enrolled-empty | Passed | Passed | Passed | Passed |
| Populated / unfinished transfer | Passed | Passed | Passed | Passed |

All eight launch after at least 65 seconds of fixture attribute-cache aging with
NFSD threads zero. They require actual D-state bootstrap and NFS/RPC kernel-wait
evidence, not a local pause. All eight pending syscalls are x86_64 `openat`
(257); the raw records retain actual arguments and kernel wait stacks. Local control remains Starting with one bootstrap worker; the connected
health request remains pending and never returns ready before coordinator death.
Closed local state is unchanged while blocked; all local/source/destination
snapshots match after old exit before recovery begins.

All 24 same-state service/initialize/direct-transfer contenders refuse while old
workers survive. Actual old-thread exit is confirmed before restart. All eight
recover with original database/configuration/enrollment and source inode, replay
job 1/202, validate delivery/manifest, retain newer producer bytes and pass a
further clean restart/replay without job 2. Four enrolled-empty cases finish
attempt 1. Four populated cases retain the original WAL for bootstrap and the
exact old 1 MiB partial inode/size/hash through recovery, finish attempt 2, and
keep that partial unchanged after another restart. No re-enrollment, manual
partial removal, review reset, retry/deadline change or source deletion is used.

Maximum measured Starting status is
0.938 seconds;
maximum orphan OwnerUnavailable status is
0.953 seconds,
including each command's host/Podman overhead. All remain below five seconds;
these finite observations are not universal timing/cancellation guarantees.
Raw flock is contended in 16/16 orphan samples; 0 cases observe early raw-lock
closure. Probes precede worker SIGKILL; after it the harness confirms exit,
adding no terminating/free-raw-guard contender or remote-settlement scope.
Movers/workers/controllers/HTTP remain UID/GID 1000, zero active capabilities,
NoNewPrivs=1; only the isolated root observer adds the two proc-inspection caps.

Both fresh mandatory SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T130033Z-364dcdf8` | 211 / 211 | 20 |
| Qualification | `20261019T130033Z-937f3a7c-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain locked cargo-zigbuild
GNU/glibc 2.22 builds, ELF interpreter/library/symbol auditing, six negative
controls per configuration, exact SLES-userspace target tests, formatting/Clippy
and 42 dependencies. There is one shipping executable; counts include tests and
both profiles.

The live matrix uses passing source-identical increment-74 gates
`20261019T122734Z-bb8afef9` and
`20261019T122745Z-65ab87ea-nfs-qualification` while fresh gates run. The
[independent audit](RUST-NFS-BUFFERED-BOOTSTRAP-INPUT-EVIDENCE.json) verifies all
62 Rust entries in fresh/live archives, all forty fresh artifact hashes and
byte equality to live inputs, all twelve driver snapshots/current bytes,
complete tuple coverage and acceptance invariants. It retains fresh source
archives and the exact verifier source. Gzip metadata may differ while Rust
entries and executable/test bytes must match. Earlier evidence is preserved;
no Rust source or Cargo.lock changes are needed.

Independent post-run inventory confirms both Podman engines have no containers.
The rootful engine retains only pre-existing `file-mover-rustup-1-99` and
`file-mover-cargo-registry` cache volumes and the default `podman` network.
Owned export volumes/networks are removed; cached images remain available.
Cleanup uses normal NFS unmounts without host/NAS data or configuration changes.

## Reproduction and limits

Follow the [step-by-step bootstrap lab](NFS-BUFFERED-BOOTSTRAP-LAB.md). Retain
exact driver/verifier inputs, live/fresh Rust entry/artifact comparisons, actual
startup/namespace/security/ownership/exit/recovery records and cleanup results.

These are enrolled-state source-bootstrap failures with expired attribute caches,
one client and one controlled server, a joint outage, volatile tmpfs and a modern
shared WSL2 kernel. The populated fixture uses a deliberately retained partial
and WAL; byte comparisons while the database is closed are not backup procedures.
No fresh first-enrollment, arbitrary warm-cache/destination-side startup phase,
pending-sync/COMMIT, server-completed RPC/reply loss, server reboot/failover,
physical-media/power, independent NAS/cache, old SLES kernel or production-scale
claim follows. Cache-only startup may behave differently; readiness describes
the control plane, not destination health or storage durability.

The unchanged bootstrap budget may request worker termination while kernel I/O
remains pending. No explicit stop, configurable-60-second deadline or terminating/
free-guard contender matrix is added: contender probes precede worker SIGKILL,
then actual exit is confirmed. A lock, timeout or process exit is not remote
settlement authority. Preserve finite timing and actual observed guard scope.

SC-110 feeds DOC-01–05, preserving earlier IDs and DOC-06 deferral. All eight
first-release gates remain open; production NFS and source deletion stay off.
