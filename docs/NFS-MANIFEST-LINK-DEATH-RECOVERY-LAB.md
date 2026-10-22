# Manifest LINK coordinator-death recovery lab

Increment 96 extends the [retained-storage lab](NFS-DISTINCT-RECOVERY-LAB.md)
and [live-coordinator manifest LINK lab](NFS-MANIFEST-LINK-RECOVERY-LAB.md). Production NFS
and private-source deletion remain disabled. No shipping Rust, dependency,
API/retry/review policy or shutdown deadline changes are part of this increment.

## Finite matrix and pass conditions

Repeat four native retained-FD prerequisites, then four actual mover cases:
debug/release x NFSD restart/NFSD-quiesced same-container restart. Both source
and destination are hard NFS mounts with separate retained backing/client
filesystems; SQLite and ownership state use a third, local filesystem.

Require actual D-state x86_64 linkat(265), original directory descriptors and
exact COMMITTED.part/COMMITTED.json names, while the coordinator is initially alive. Kill only
that coordinator PID. While the original worker remains D, require three local
ownership observations and refusal of service, source initialization and transfer
contenders using the same protected state and a different ephemeral API port.
Physical flock closure is recorded, never interpreted as remote cancellation.
Preserve the epoch, claimed source, published one-link payload, complete manifest
staging and absent final manifest. Payload staging is already absent.

Restore the same backend and wait for actual old-worker exit before recovery.
Record the independently observed backing namespace (one-link staging, two-name
aliases, or one-link final with staging removed) and full content/inode
identities before replacement, then recover using the original local database,
configuration and enrollment. Require original-attempt commitment, original
manifest staging inode becoming the final manifest, unchanged published payload, retained source custody, a valid
manifest and same-ID 202 replay preserving the producer's newer source bytes.

## Step-by-step infrastructure and execution

1. Use feature/rust-transfer-coordinator. Inventory both Podman engines; retain
   existing volume metadata and network names. Use Python with its standard
   sqlite3/zlib modules for copied-database inspection; no Python dependency is
   added to the shipping service. Use the rootful engine only for
   the private fixture and default engine for the compatibility gates.
2. Start both mandatory gates and retain their output directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These run locked cargo-zigbuild GNU/glibc 2.22, exact-target tests in pinned
   SLES 12 SP5 userspace and ELF/loader/library/symbol audits. Earlier passing
   identical-source gates may provide live binaries while fresh gates run;
   independently verify archive contents and shipping executable bytes afterward.
3. Freeze acquisition sources before launching:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --manifest-link-death-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   This mutually exclusive mode captures seventeen exact acquisition files.
   Keep all raw outputs and source snapshots before any failed-run correction.
4. Follow the parent lab's fixed-IP backend/private internal network, unprivileged
   reserved-port relay, pinned SLES client and read-only backing reader. Publish
   no host ports. Keep two 64 MiB/4096-inode local-driver tmpfs volumes mounted by
   a separate network-none storage keeper, with unchanged PID/mount identities.
   Exports retain root_squash/sync and fsids 68/69. Fixture lease/grace are ten
   seconds; these settings are not production NAS policy. Mount buffered NMP-41B
   hard,ac,async,vers=4.1,TCP,sec=sys,timeo=10,retrans=1. Verify distinct backing
   and client devices and RO reader flags.
5. Repeat native source/destination x NFSD/container retained-FD controls. Require
   changed protocol session/write verifier, original backing inode/handle, exact
   read/write/sync evidence and normal exit. Native controls do not substitute
   for actual mover worker or synchronization evidence.
6. For each mover case provision once, submit JSON to confirmed 202/job 1, then
   write 'next recording' at the producer's reused original path. Pause at
   manifest_link_rpc with Claimed/Published, manifest_phase 3, complete
   one-link COMMITTED.part and no final manifest; retain the published payload
   and confirm payload staging is absent. Attach the bounded network-none external I/O observer.
7. Stop NFSD and confirm threads=0. For container cases only, then SIGKILL/wait
   exit 137, verify exited/PID zero, and later restart the same container/IP.
   Do not call this abrupt live-server recovery, VM reboot or NAS reboot.
8. Release the qualification pause into actual D-state linkat. Capture syscall
   arguments, both directory FD paths/mount/inode IDs, worker UID/GID 1000,
   zero capabilities and no-new-privileges. Require responsive health/status,
   unchanged local state, held guard and specific ownership refusal by a contender.
9. Kill only the coordinator PID. Confirm its exit, sample D-state before/after
   each local ownership observation, and require OwnerUnavailable/exit 2. Run the
   three ownership contenders only while exclusion remains positively established;
   abort safely if it is lost. Preserve unchanged epoch/custody through the outage.
10. After coordinator exit, copy only local jobs.sqlite and any existing WAL to
    a private host output folder. Retain exact compressed bytes and SHA-256 hashes,
    checking original hashes before/after copy. Open only the copied files through
    Python's read-only/query-only SQLite interface. Require job 1 manifest phase
    3, exact manifest bytes/hash, and payload attempt 1/Published (phase 4).
    Workers never write SQLite and the coordinator is already gone; no live
    database is opened by this observer. Repeat after actual old-worker exit and
    require byte-identical originals/snapshots and identical query results.
11. Restore the backend before draining workers. Confirm actual old-worker exit,
    finish its external trace, record independent RO namespace/content snapshots
    and NoActiveOwner, then start original-state recovery. If COMMITTED.json is visible, capture its
    full bytes independently and require the original valid manifest while SQLite
    still shows phase 3. Visibility does not fabricate a received phase-4 receipt. Do not substitute local
    exit/lock observations for remote completion evidence. Require exact custody,
    original inode/attempt, manifest and replay checks described above.
12. Stop normally, restart once more, replay identical JSON and require unchanged
    manifest/configuration/database identity and producer bytes. Cleanup restores backend
    before draining users, normally unmounts both NFS mounts, removes owned users,
    then keeper last and owned volumes/network. Never force/lazy-unmount or reset
    the VM. Wait for both gates and all fixture processes to finish.
13. Capture and audit the final inventory and proof:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-manifest-link-death-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require zero containers on both engines and unchanged baseline volume metadata
    and network names. The independent verifier redecodes every bounded raw RPC,
    validates source snapshots, native controls, ownership/namespace evidence,
    corrupted-proof controls, both gates and all forty Rust ELF artifacts. The
    input pack records the offline SQLite auditor runtime/version. Reconstruct
    under a fresh temporary directory in rust/validation, verify its resolved
    parent remains inside the workspace, close SQLite, then remove only that
    owned scratch directory. The Windows sandbox default temp may deny writes;
    preserve failed audit code/diagnostic/raw report before changing scratch paths.

## Interpretation and limitations

An orphan may complete its pending manifest LINK and remaining publication syncs after
restoration, then exit with an error when reporting to the lost coordinator.
Alternatively a killed orphan may never return from linkat to userspace. Keep that
unfinished trace as such; require actual exit and independent namespace/content
observations rather than fabricating a successful old-worker return or sync.
Raw successful manifest LINK after restoration and final original-manifest custody
are separate evidence from attribution to the old pending call. Attribute a
completed original call only with its successful return and a successful raw LINK
inside that exact interval; inspect old staging removal/sync ordering separately. An absent final
name at an observation is not a general proof that every delayed server effect
has settled. These finite controlled recoveries do not authorize arbitrary
uncertain-effect redispatch, cross-host takeover or a new automatic fencing rule.

Modern WSL2/Podman kernel, SLES userspace and synthetic tmpfs-backed kernel-NFS
server do not qualify a SLES kernel, SLES maintenance-patched systemd, NetApp or
Isilon behavior, persistent storage/power loss, independent server failures,
longer outages, every cache/load/size, directory/blocked-file fsync, other phases
or death while already terminating. All eight release gates remain open.
See [testing limitations](TESTING-LIMITATIONS.md) and
[increment 96](RUST-INCREMENT-96.md) for measured outcomes.


A visible valid completion manifest retains the consumer contract; consumers do
not acquire a new API-polling duty. The recorder still retries the identical
submission until confirmed 202 and has no post-202 monitoring duty. A lost local
receipt is recovered by the mover from original evidence. Source claiming and
private-source postcommit cleanup remain separate operations; cleanup stays off.
