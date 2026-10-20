# Controlled NFS recovery with distinct client filesystems

This is the increment 88 extension to [the mover recovery lab](NFS-SERVER-MOVER-LAB.md).
It tests four native controls, followed by four actual mover source-copy cases:
debug/release × NFSD stop/start or NFSD quiescence followed by confirmed same-container
SIGKILL/exit/start. Production NFS and post-delivery source deletion stay disabled.

## Infrastructure and prerequisites

Use the feature/rust-transfer-coordinator branch, cached pinned images and the two
Podman engines described in the parent lab. The default engine runs the required
SLES gates; the isolated rootful engine runs this fixture. Neither engine may have
unrelated containers. Preserve existing anonymous volumes, Rust caches and networks.

One internal network has a fixed private backend IP and no published ports. The
kernel NFS backend exports source and destination with root_squash, sync and fsids
68/69. Each export is a different Podman local-driver tmpfs volume, limited to
64 MiB and 4,096 inodes. A separate storage container retains references to both
volumes across backend termination/start. An ordinary parent volume holds the
export root. The observer mounts both role volumes read-only, has no network,
no active capabilities and NoNewPrivs. Its reads do not refill the NFS client cache.

The fixture verifies exact tmpfs mountpoints/devices in keeper, backend and reader,
reader read-only flags, distinct client NFS devices and a third local state device.
It retains keeper PID/start/mount namespace/full mountinfo before and after every
recovery. A different mount ID alone is insufficient. Two tmpfs superblocks do not
represent independent NAS machines, persistent disks or power-loss durability.
The storage container and VM remain alive throughout every controlled restart.

## Step-by-step execution

1. Inventory both engines; use only the owned resources and cached images from
   the parent lab. Check the exact branch and clean Rust source inputs. Do not
   alter acquisition scripts during an active run.
2. Start both required build/test paths, retain their printed output directories
   and wait for their actual successful exit before final evidence generation:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use locked cargo-zigbuild GNU/glibc 2.22, ELF checks and exact target tests
   in pinned SLES 12 SP5 userspace. Prior passing gates with identical Rust inputs
   may supply live binaries while fresh checks run; the auditor compares all
   source archives and exact shipping bytes rather than trusting run labels.
3. Run the fixture with both selected passing artifact directories:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The runner prints distinct-server-recovery-RUN and captures sixteen exact input
   scripts before resource creation. The distinct flag requires mover mode so
   container events use the qualified NFSD-quiesced sequence.
4. Create the owned internal network and parent volume, then the two tmpfs local
   volumes using type=tmpfs, device=tmpfs and
   o=size=64m,nr_inodes=4096,mode=1777. Start the keeper before backend/reader and
   mount these same named volumes into each. Verify actual mountinfo and client
   devices before any native or Rust recovery case. Do not use nosharecache to
   manufacture a difference on the same filesystem.
5. Run native controls for source/destination × both facilities. Each probe keeps
   its original open descriptor and opaque handle, writes/fsyncs 4 KiB A bytes,
   blocks in an actual syscall while the facility is down, then writes/fsyncs and
   reads back B bytes after restoration. Independently observe backing inode/bytes,
   raw RPC/session/verifier changes and actual process exit. All four must pass
   before proceeding to the service.
6. For each Rust case, provision roots/enrollment/local state once, start the
   qualified executable as UID/GID 1000 and submit JSON until confirmed 202/job 1.
   Reuse the producer path with newer data. Pause after the first MiB of a
   2 MiB + 17-byte payload; prove source/staging/local-state devices differ.
   Attach the external syscall observer and snapshot fresh relay wire checkpoints
   and storage/backend identity. Do not read claimed source via the client after
   cache preparation.
7. Stop NFSD and confirm zero threads. For the container facility, additionally
   SIGKILL the same backend, wait for exit 137/Status exited/PID 0, then eventually
   start that same container. The storage keeper remains live. Release the local
   copy rendezvous and require an actual D-state source read on the original
   claimed-source FD requesting 1 MiB, with no read-completed marker.
8. While down, require responsive local health, unchanged Claimed/Intent status,
   local state/epoch, contended guard and an ownership-specific contender refusal
   using an ephemeral listener. Do not confuse address-in-use with guard exclusion.
   Record restoration time in the common Linux monotonic clock domain. Restore
   original IP/exports/volumes without remounting or replacing the worker.
9. Require original-worker attempt-1 commitment, successful traced sync calls,
   actual worker exit, original staging inode as final payload, expected digest
   and complete manifest. Verify source backing identity/bytes, enrollment, local
   state/config/root continuity. Cleanly restart from original state and replay
   the same ID/body; require the same committed job/manifest and newer producer
   bytes untouched. Preserve all raw RPC records, including unknown compounds.
10. Wait for runner exit and cleanup_errors=[]. Restore the backend before draining
    blocked users; normally unmount both client mounts. Remove observers, reader,
    client and backend before the keeper, and verify its full identity/mountinfo
    one final time. Remove the keeper last so Podman can normally release the
    retained tmpfs mounts, then remove the two role volumes, parent volume and
    owned network. No force/lazy NFS unmount, VM restart or global policy change.
11. After both SLES gates and all lab processes exit, capture both engines and run
    the independent evidence audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-distinct-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require unchanged baseline volume metadata/network names, zero containers,
    all raw/source hashes, exact archive contents, forty artifact/ELF audits and
    rejection of every deliberately corrupted proof. Retain failed acquisitions
    before correcting any fixture input; they never count as passing support.

## Initial setup failure

The first acquisition attempted bind sources through /proc/keeperPID/root.
The OCI runtime rejected those mounts with EINVAL before backend startup. It ran
no native or Rust recovery case and created no client NFS mount. The exact report,
sixteen sources, cleanup helper/actions and error remain in
[initial failure evidence](RUST-NFS-DISTINCT-RECOVERY-INITIAL-EVIDENCE.json).
Cleanup verified the backend was still Created/PID 0, removed that exact container,
normally unmounted both keeper tmpfs filesystems and removed only owned resources.
The corrected fixture uses Podman's named local-driver volumes, not proc binds.

## Recorded result and namespace scope

[Increment 88](RUST-INCREMENT-88.md) records four native and four actual mover
passes, both fresh SLES gates, 63 rejected proof corruptions, 40 audited ELF
artifacts and final normal cleanup. Backing devices 0:141/0:142 map to client
NFS devices 0:186/0:191; local state uses st_dev 158. Twenty-five server-state
observations and final cleanup retain the same keeper identity/mountinfo.

One native container-source control observed a changed backend network namespace;
other native controls and all actual mover cases retained theirs. All shared the
same VM boot ID. Preserve those measured outcomes rather than assuming that a
same-container restart always retains or always replaces its namespace. The
single native change does not qualify actual mover fresh-namespace recovery.

## Limits

This is controlled same-kernel protocol-state recovery with storage deliberately
retained. NFSD is quiesced before backend termination. It does not qualify abrupt
live-NFSD termination, VM/NAS reboot, fresh network namespace, old SLES kernel/NFS
client behavior, physical stable storage, outstanding UNSTABLE-data preservation,
other phases/workloads/outage durations or worker death/replacement. Tests use
small prepared payloads and deliberate cache advice; no 100 GB performance or
endurance claim follows. Registration, S3 and offline repair remain deferred.
All eight release gates stay open and production NFS/source deletion stay off.
