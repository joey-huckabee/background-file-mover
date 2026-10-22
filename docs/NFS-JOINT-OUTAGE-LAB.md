# Joint source/destination outage lab

This increment 101/SC-135 procedure extends the
[retained-storage lab](NFS-DISTINCT-RECOVERY-LAB.md). Production NFS and postcommit
private-source cleanup stay disabled. No shipping Rust, package, API, retry/review
policy or shutdown deadline changes are intended.

## Matrix and pass conditions

Four native retained-FD recovery controls precede four mover cases: debug/release
x source-space admission off/on. Source and destination have distinct retained NFS
filesystems on one controlled NFSD backend; SQLite and ownership remain local.
Set max_retained_jobs=1. The enabled source-space policy uses min_available_bytes=1,
max_sample_age_seconds=1 and probe_timeout_seconds=1. This is a fixture policy,
not a production capacity recommendation; the service default remains off.

Initially claim job 1 and confirm 202 before the recorder writes replacement bytes.
Pause destination verification after a first chunk with complete copied staging.
Stop NFSD, release that pause and prove an actual D-state read on destination
staging. Age source metadata for at least 65 seconds without traversing NFS from
the controller. The delay does not prove cache expiry: require actual blocked
source revalidation when replaying the already claimed job.

The same-ID request is allowed to return retryable 503 while source authority
cannot be revalidated. It must not reinterpret the replacement producer file as
job 1. The original 202 remains the recorder's custody handoff; no post-202 polling
or delivery-monitoring duty is introduced. Consumers wait for a valid manifest.

## Step-by-step infrastructure and execution

1. Use feature/rust-transfer-coordinator and cached pinned images. Inventory both
   Podman engines; preserve their baseline full volume metadata and network names.
   The default engine runs compatibility gates; the rootful engine owns this lab.
   No real SLES installation or NAS administrator access is required.
2. Run both required gates and retain their reports:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   They use locked cargo-zigbuild GNU/glibc 2.22, exact-target tests in pinned SLES
   12 SP5 userspace and ELF loader/library/symbol audits. Live cases may use prior
   passing identical-source artifacts while fresh gates run; verify complete
   source archives and shipping binary hashes against both sets afterward.
3. Freeze acquisition sources and start the selected finite matrix:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --joint-outage --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The selected flag excludes other phases and freezes seventeen acquisition files.
   Do not edit them during a run. Preserve raw failed acquisitions and exact code
   before fixing infrastructure, harness or audit mistakes.
4. Follow the parent lab's private internal network/fixed-IP backend, independent
   storage keeper, two local-driver tmpfs volumes (64 MiB/4,096 inodes per role),
   read-only backing reader, unprivileged relay and pinned SLES client. Publish
   no ports. Keep root_squash/sync exports, fsids 68/69, fixture lease/grace ten
   seconds and NMP-41B hard,ac,async NFSv4.1 TCP/sec=sys with timeo=10,retrans=1.
   These controlled settings do not define NAS production policy.
5. Repeat native NFSD/source, NFSD/destination, quiesced-container/source and
   quiesced-container/destination prerequisites. Require retained backing/FD/file
   handle, actual pending operations and successful original-inode completion.
   These do not establish abrupt NAS restart or power-loss durability.
6. For each mover case, provision roots/state and the selected capacity policy.
   Start at existing verify_read, submit the original JSON and require confirmed
   202/job 1/source_paths_released. Only then write 'next recording' at the original
   producer path. Require Claimed/Copied state and complete same-hash private source
   and destination staging. Keep original config and DB inode.
7. Set NFSD threads to zero and release the qualification pause immediately;
   its existing 60-second limit is unchanged. Require actual worker D-state,
   read syscall 0 and expected destination staging descriptor. Let source metadata age for at least 65 seconds while this worker is
   actually blocked, rather than extending the artificial pause.
8. With admission enabled, submit a new ID first. Require retryable
   source_space_unavailable without path release (under 15 seconds including
   fixture transport overhead) and at most one observed supervised
   probe child. A cancelled probe may already have exited; it need not stay alive.
   Probe timeout alone must not allow replacement before actual exit.
9. Replay original JSON/ID asynchronously. Identify the assigned claim worker and
   require actual D-state source revalidation. Read only that owned child's local
   proc syscall/FD information. For openat/newfstatat, the privileged fixture reader
   reads the pathname argument from that child's local proc memory using dd/od -v
   and resolves relative arguments against that child's directory descriptor;
   it never reads an NFS pathname for this observation. Record original security,
   syscall arguments, exact path and command. Service workers remain UID/GID 1000,
   without capabilities and with NoNewPrivs. This is fixture instrumentation.
10. Launch a finite six-request burst alternating original and new IDs. Retain
    complete HTTP logs and process exits for these plus the first replay. Require
    retryable non-release 503s and at least one service_busy refusal. Queued requests
    may outlive their HTTP timeout; a timeout is not command cancellation. Require
    two unchanged blocked data/validation workers plus at most one optional probe
    when admission is enabled; confirm exit of any observed disappearing probe, local
    health/status responsiveness, one retained job, held local guard, unchanged
    independent source/staging custody and no completion manifest while NFSD stays
    stopped. This is a finite queue test, not an endurance or memory benchmark.
11. Restore two NFSD threads before draining users. Require the original coordinator
    and attempt-1 verified delivery, actual original delivery/validation worker exit,
    complete valid manifest and intact newer producer bytes. Replay identical ID
    until confirmed 202. A new ID must still receive retention_capacity under the
    unchanged one-job limit; job 2 must not exist. Stop cleanly, restart original
    local state and confirm same-ID 202/replay, manifest/hash and producer bytes.
12. Wait for runner and gate exit codes, restore before draining, normally unmount
    both NFS mounts, remove owned users/backend, verify keeper continuity and remove
    it last, then owned volumes/network. No forced/lazy unmount, VM reset or global
    NAS/cgroup/host changes. After all processes exit, capture and audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-joint-outage.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Audit exact source and executable hashes, native controls, distinct storage,
    request logs, custody, worker counts/security/paths, recovery and corrupted-proof
    controls. Independently redecode the bounded raw relay records, retain unsupported
    compounds and count captured request/reply pairs across restoration. Zero pairs
    may occur when backend reconnection precedes observation of buffered requests;
    actual blocked workers do not prove wire continuity. Require capture before
    outage and after restoration. Temporal pairs alone do not identify a particular
    file or syscall. Verify forty ELF
    artifacts and zero final containers with unchanged baseline volumes/networks.

## Retained instrumentation failure and full rerun

The [initial run](RUST-NFS-JOINT-OUTAGE-INITIAL-EVIDENCE.json) passed all four
native prerequisites but failed in the first mover case while decoding local
proc memory. od abbreviated repeated lines with an asterisk. Retain exact failed
report, seventeen acquisition sources and empty post-cleanup rootful inventory.
Add od -v so the hex bytes remain complete, and resolve descriptor-relative open
pathnames against the recorded directory FD. Rerun every native/mover case and
independently verify hashes/source changes; no runtime Rust or retry policy changes.

The [second run](RUST-NFS-JOINT-OUTAGE-SECOND-EVIDENCE.json) passed the native
controls and debug/off case but failed an overstrict enabled-case assertion: the
probe had exited and only the two expected blocked data/validation workers remained.
All seven requests correctly returned retryable non-release 503s. Preserve exact
report/code and clean baseline inventory. Permit zero or one observed probe when
enabled, keep the two data workers stable, check actual exit of any observed
probe that disappears, and rerun the complete matrix without runtime changes.

## Results and limits

See [increment 101](RUST-INCREMENT-101.md) and retained raw/input evidence for actual
results, acquisition/audit corrections and measured scope. Do not promote pending
qualification as production support.

Both shares use one NFSD backend on a modern shared WSL2 kernel with retained
memory-backed storage. This does not qualify independent simultaneous server
failures, NAS/VM reboot, disk/power loss, old SLES kernel/client or maintenance
systemd, NetApp/Isilon, 100 GB throughput, unrestricted request flooding, large
queues or endurance. This matrix does not kill the coordinator, change enrollment
or test source substitution. D-state and local worker exit are not global remote-
settlement proof. The admitted original job stays recoverable; the recorder's
post-202 duties and consumer manifest contract remain unchanged.

All eight release gates remain open. Registration/S3/offline repair/DOC-06 remain
deferred; production NFS and postcommit private-source cleanup remain disabled.
