# Buffered NFS recovery after staging removal, before directory sync

This eight-case extension uses the retained [publication fixture](NFS-BUFFERED-PUBLICATION-LAB.md)
and [mount-profile infrastructure](NFS-MOUNT-PROFILE-LAB.md). Production NFS and
source deletion remain disabled. See [increment 73](RUST-INCREMENT-73.md) for
measured results; these steps define the required observations.

## Infrastructure and commands

1. Use the existing approved Podman WSL2 VM and rootful connection
   `podman-machine-default-root`. Inspect existing containers and the cached
   `localhost/background-file-mover-e2-nfs` image as described in the
   [fixture setup](NFS-TEST-FIXTURE.md). No new host/NAS setup, kernel change or
   systemd bootstrap is introduced. Each run owns an internal network, export
   volume, privileged kernel-NFS server and pinned SLES 12 SP5 client.
2. Run both mandatory compatibility gates and keep the printed result directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use locked cargo-zigbuild GNU x86_64/glibc 2.22 builds, ELF loader/library/
   symbol-version auditing, negative controls and exact debug/release tests in
   pinned SLES userspace. Host-only Cargo tests cannot replace the gates.
3. Run the new matrix with both passing gates:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-post-unlink
   ```

   Select only one worker matrix. This option is mutually exclusive with
   `--same-share`, `--buffered-reads` and `--buffered-publication`. The outer
   runner repeats its independent model/inventory controls, checks both gate
   archives against current Rust input bytes/configuration and checks transferred
   executable hashes. It retains exact driver SHA-256/Base64 snapshots.
   Source-identical passing gates may supply live binaries while fresh gates run;
   record that distinction and compare all fresh artifacts afterwards.
4. The two root-squashed synchronous child exports have distinct fsids 68/69 and
   64 MiB tmpfs capacity each. Mount buffered NMP-41B NFSv4.1/TCP/sec=sys, hard,
   `ac,async`. Same-share uses disjoint private roots on `/tmp/profile-source`;
   separate-share also mounts `/tmp/profile-destination`. Record actual selected
   mount records/devices. Both shares use one server and a joint outage domain.
   Database, configuration, epochs and rendezvous remain local under a UID-1000
   mode-0700 parent on a different filesystem.
5. This matrix needs only SYS_ADMIN for the root client's mount setup. It adds
   no SYS_PTRACE/DAC_READ_SEARCH observer capabilities because it inspects no
   pending syscall. Ordinary service, worker, controller and HTTP processes run
   as UID/GID 1000, zero effective/permitted/inheritable capabilities, NoNewPrivs=1.
   Capture actual worker security status; no host ptrace policy is changed.

## Eight cases and acceptance

Run `file_unlink_sync` and `manifest_unlink_sync` in debug/release on both layouts.
Cases run serially because they interrupt one shared server.

| Point | Required namespace before crash | Coordinator job phase |
|---|---|---|
| `file_unlink_sync` | `.staging/1.part` absent; original `nested/data.bin` has one link; no manifest | Claimed / PublishIntent |
| `manifest_unlink_sync` | `.staging/COMMITTED.part` absent; original valid `COMMITTED.json` has one link; payload fully published | Claimed / payload Published |

1. Provision fresh protected role markers and initialize source enrollment once.
   Create the nested 2 MiB plus 17 byte recording. Capture source inode/size/hash,
   database inode and configuration/enrollment hashes. Start the audited
   qualification service with the selected local pause. Require job 1/202 with
   source paths released before writing `next recording` at the old producer path.
2. Require exactly one actual delivery worker and the matching ready checkpoint.
   In Rust relocation, `unlinkat` has returned, `unlink_effect` triggers the
   selected pause, and `relocate.old_parent_sync` has not been called. Record
   inode/link/size/hash evidence for the final file or manifest and require its
   staging name absent. Validate manifest/payload contents for manifest cases;
   payload cases must have no consumer manifest. Record durable job state,
   ownership epoch and healthy same-ID 202 replay.
3. Stop only the owned NFSD with `rpc.nfsd 0`; confirm zero server threads. Leave
   the local pause's `go` file absent and SIGSTOP the worker. Require T state,
   no replacement child, health 200 and unchanged job status, each measured
   independently below five seconds including its own host copy/Podman overhead,
   and bounded local
   Running status. No sync call is released into this outage.
4. Kill only the coordinator PID. Across two samples require the old worker
   remains stopped, the original epoch is unchanged, and bounded local status
   reports OwnerUnavailable/exit 2. Record raw flock separately. Try same-state
   service startup on an alternate listener, explicit initialization and direct
   transfer. All must promptly refuse with the surviving-worker diagnostic;
   listener occupancy is not exclusion evidence.
5. After those probes, SIGKILL the old worker. Restore the owned NFSD with
   `rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2`, wait eleven seconds and verify two
   threads. Confirm actual worker exit, no live old coordinator/worker threads,
   and NoActiveOwner before restart. A zombie proves exited/closed files, not
   PID-1 reaping or remote-effect settlement.
6. Reinspect after restoration/exit: staging is still absent, final is still the
   original one-link inode/size/hash, and payload-only work has no manifest.
   Restart with original database/configuration/enrollment. Same-ID replay must
   return job 1/202 and recovery must reach Committed on attempt 1 with the
   original final allocation; manifest cases retain the original manifest too.
   Retained source has its original inode/content, producer-reused bytes survive,
   source_cleanup_enabled stays false, and no policy/reset/re-enrollment or
   review bypass is used. Database content may legitimately change as recovery
   records progress; original-state identity is not a frozen-byte assertion.
7. Stop cleanly through the bounded controller, wait for exit, restart/replay
   again and require the same committed job and publication/manifest identities,
   hashes, configuration/enrollment and producer bytes. Stop cleanly and retain
   service logs and per-case evidence.

## Audit, cleanup and limits

After the live matrix and both fresh gates pass:

```powershell
python scripts/verify-nfs-buffered-publication.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run> --post-unlink
```

The verifier independently checks all eight tuples, absent staging before/after
death, original one-link allocation/content, security/exclusion/exit/recovery/
replay, exact driver bytes and all forty fresh ELF artifacts. It validates gate
archives by Rust entry bytes (gzip metadata can differ) and requires live/fresh
artifact byte equality. Only after all assertions pass does it write separate
post-unlink evidence and update canonical SLES reports. It retains source archives
and its own exact source in the input evidence; existing increment-72 evidence
is preserved separately.

Failure cleanup restores NFSD before its final termination/wait. Unmount normally
after all users exit, then unexport and remove only owned containers/export volume/
network. Keep cached images/toolchain volumes. Retain resources and mark FAILED
if cleanup is uncertain; use no forced/lazy NFS unmount or host/NAS changes.

These are returned-unlink, before-directory-sync process crashes with retained
server/cache state. They prove neither an in-flight fsync/COMMIT failure nor
server-completed RPC with a withheld reply, persistent-media/power durability,
server reboot/failover/reclaim, independent NAS/cache failures or old SLES kernel
behavior. Contender probes precede worker SIGKILL; afterwards the harness waits
for actual exit, adding no terminating/free-raw-guard contender branch. Workload,
other-client coherence, untested phases/directions and endurance remain open.
See [testing limitations](TESTING-LIMITATIONS.md). Production NFS/source deletion
remain disabled, and all first-release gates remain open.
