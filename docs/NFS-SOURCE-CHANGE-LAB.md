# Source-change refusal during a partial handoff: controlled lab

Increment 104/SC-138 extends the [retained-storage lab](NFS-DISTINCT-RECOVERY-LAB.md)
and [partial-handoff lab](NFS-PARTIAL-HANDOFF-LAB.md). Production NFS and postcommit
private-source cleanup remain disabled. This increment changes fixture/evidence
code only; Rust, dependencies, API responses, retry/review policy and shutdown
deadlines stay unchanged.

## Finite matrix and expected behavior

Four native retained-FD prerequisites precede four mover cases: debug/release x
second-file inode replacement or size change. Source/destination use distinct
retained NFS filesystems on one backend; SQLite and ownership stay local. The Rust
source-change cases use healthy NFS throughout; they are not outage, blocked-syscall,
coordinator-death or reply-withholding tests.

Submit two completed files in order: earlier/first.bin (23 bytes), nested/data.bin
(2 MiB + 17 bytes). Neither request supplies a size assertion; the service uses
its own recorded observation. Existing qualification CLAIM_INDEX=1 and claim_apply pause
allow the first claim to finish and the second immutable intent to persist before
its filesystem effect. Deliberately violate producer immutability only in the fixture:

- Inode case: copy the second file with metadata preserved, retain the original
  inode under fixture-original, and replace its submitted name with the copy.
  Bytes, size, UID, timestamp and link count stay equal; inode differs.
- Size case: retain an untouched backup, append X to the same submitted inode,
  then preserve its original timestamp. Device/inode, UID, timestamp and link
  count stay equal; size and hash differ.

Neither mutation is permitted recorder behavior. The real recorder must keep every
submitted file and parent unchanged until confirmed whole-set 202. Source metadata
observations are not a cryptographic proof that a hostile writer never changed
content. Same-inode/same-size timestamp-preserving tampering and other mutation
windows remain outside this finite test.

Require existing non-retryable 409 recording_blocked on six exact-ID/body retries
across two unpaused restarts. The initial request may time out as retryable 503
handoff_pending during fixture preparation; it must never return 202/release.
Require the actual initial worker's relocation-object-changed diagnostic and exit.
API refusal does not automatically change the durable job to ReviewRequired:
it remains Accepted/AwaitingClaims, one confirmed claim and unchanged review epochs.
Do not add automatic retry, repair, replacement-intent adoption or a new review policy.

## Step-by-step infrastructure and test

1. Use feature/rust-transfer-coordinator. Preserve baseline full volume metadata
   and network names on default and rootful Podman engines. Use rootful connection
   podman-machine-default-root for the private fixture, default engine for gates.
2. Run both required compatibility gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   They use locked cargo-zigbuild GNU/glibc 2.22, fmt/clippy, exact-target tests in
   pinned SLES 12 SP5 userspace, ELF interpreter/library/symbol/relocation checks
   and negative controls. No host-only cargo tests or real SLES host is substituted.
   A live run may use prior completed passing gates only with exactly matching
   Rust inputs and final byte-identical shipping artifacts, audited against fresh
   gates afterward. Never pass unfinished gate directories to artifact loading.
3. Select the finite fixture mode; freeze seventeen acquisition scripts:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --source-change-refusal --production-gate rust/validation/COMPLETED_PRODUCTION_RUN --qualification-gate rust/validation/COMPLETED_QUALIFICATION_RUN
   ```

   The flag requires --mover --distinct-filesystems and excludes every other phase.
   Do not edit acquisition files while the run is active.
4. Follow the parent lab's owned internal network without published ports, NFSD
   backend, independent keeper, two retained tmpfs role filesystems bounded to
   64 MiB/4,096 inodes each, read-only backing reader, relay and pinned SLES client.
   Keep root_squash/sync exports, fsids 68/69, fixture lease/grace ten seconds and
   NMP-41B hard,ac,async NFSv4.1 TCP/sec=sys, timeo=10,retrans=1. These controlled
   fixture settings do not establish a NAS production configuration.
5. Repeat native source/destination x NFSD and quiesced-container recovery controls.
   Require actual pending retained-FD operations, original inode/filehandle,
   changed session/write verifier and successful sync/readback. They do not prove
   abrupt NAS reboot or power-loss durability.
6. Provision both complete files and start the qualified service with existing
   FILE_MOVER_QUALIFICATION_PAUSE=claim_apply,
   FILE_MOVER_QUALIFICATION_CLAIM_INDEX=1 and local rendezvous. Submit original JSON
   asynchronously. Require the one assigned internal claim child at the pause.
7. While that assignment is quiescent, copy local jobs.sqlite and existing WAL.
   Hash each original before copying and recheck all original hashes afterward.
   Read only the copies with SQLite query_only: exactly one job, two files/two
   claims, done flags [1,0], no transfers/manifests. Record the complete immutable
   claim rows, including the second source identity; compare it with client stat
   device/inode/UID/size/mtime seconds/nanoseconds/link count. This is fixture-only
   evidence extraction, not implementation of deferred product offline repair.
8. Record original independent backing snapshot and timestamps, inject the selected
   producer fault as UID/GID 1000, then prove the intended isolated difference.
   Use read-only backing checks as UID 1000 for actual content/inode custody.
   Positively check parent traversal before absence: first original absent, first
   private original intact, second private data absent and destination job absent.
   Retain the saved original/backup and changed submitted file without repairing either.
9. Release the existing pause within its unchanged 60-second budget. Require actual
   worker exit and non-release initial response; capture local Accepted status,
   one confirmed claim, zero destination attempts and held ownership guard. Stop
   normally, require Stopped/exit zero, and capture another copied database snapshot.
   Require apply: blocked: relocation object changed in the initial service log.
10. Restart original config/state without any qualification pause or selector. Send
    exact JSON/ID three times and require 409 recording_blocked, retryable=false,
    source_paths_released=false, job 1. Require unchanged status/review epochs,
    first/private and changed/saved custody, second identity and no delivery.
    Stop normally and copy the database again. Repeat this unpaused restart and
    three-refusal sequence once more. Require all four copied claim inventories
    exactly equal to the pending original and no transfers/manifests in any copy.
11. Check local database inode/config hash and source/destination private-root
    identities unchanged. Confirm the same healthy server/keeper throughout each
    Rust case. Inspect exact raw RPC hashes/XIDs/decoding: first source LINK and
    first.bin REMOVE successfully preceded mutation. No decoded second data.bin
    REMOVE may appear. Unsupported compounds remain retained non-positive evidence;
    do not infer global absence of effects from partial wire decoding.
12. Always restore backend before draining on failure. Normally unmount NFS, remove
    owned users/backend, verify/remove keeper last, then owned role/parent volumes
    and network. No forced/lazy unmount, VM reset or global host/NAS changes.
    Wait for both gates and the fixture to exit, collect inventory and audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-source-change.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Reopen extracted database/WAL copies independently, verify immutable original
    intents and zero delivery, reject corrupted proofs, audit all forty Rust ELFs,
    full source archives/used-fresh artifact hashes and unchanged baseline inventories.
    Preserve exact failed reports and code snapshots before correcting any failure.

## Retained audit failure

The [initial audit](RUST-NFS-SOURCE-CHANGE-AUDIT-INITIAL-EVIDENCE.json) preserves
exact raw acquisition, verifier/dependency sources and diagnostics. Windows sandbox
permissions refused extraction into the default temporary directory. Move extraction
into a temporary directory under rust/validation and explicitly close each SQLite
connection before temporary cleanup. The corrected full audit reuses exactly the
same raw acquisition; no Rust, fixture result, API/retry/review behavior or deadline
changes. A failed audit is not passing evidence. Keep this host-auditor limitation
separate from the successful container experiment and its kernel/NAS limits.

## Results, operator meaning and limits

Read [increment 104](RUST-INCREMENT-104.md),
[raw acquisition](RUST-NFS-SOURCE-CHANGE-EVIDENCE.json) and
[independent evidence](RUST-NFS-SOURCE-CHANGE-INPUT-EVIDENCE.json) for actual results.
409 is a refusal, not successful handoff or permission to reuse submitted paths.
Retain original local state/private custody and investigate the producer violation.
Do not delete/recreate the database or resubmit a new ID to bypass the old intent;
this test provides no automatic repair procedure. Registration/S3/offline repair/
DOC-06 remain deferred; the recorder gains no post-202 delivery-monitoring duty.

This qualifies two isolated changes before second-file claim effects on healthy
NMP-41B NFS. Other source/parent changes and timing windows, hostile metadata/content
manipulation, outages/death during changes, arbitrary file counts, independent
NAS failures, persistent disk/power loss and 100 GB throughput/endurance remain open.
The modern shared WSL2 kernel and retained tmpfs cannot qualify old SLES kernel/
client/maintenance systemd or NetApp/Isilon behavior. Keep all eight release gates
open and production NFS/private-source cleanup disabled.
