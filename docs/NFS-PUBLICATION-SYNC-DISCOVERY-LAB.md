# Exact publication file-sync discovery lab

This increment 94 procedure extends the [retained-storage recovery lab](NFS-DISTINCT-RECOVERY-LAB.md).
It tests actual mover file fsync behavior before selecting more server-recovery
cases. Production NFS and private-source deletion stay disabled; no shipping Rust,
dependency, API/retry/review or shutdown deadline changes.

## Finite matrix and evidence rules

Repeat four native retained-FD recovery prerequisites. Then run eight actual mover
cases: debug/release x payload/manifest first final-file fsync x healthy/stopped
NFSD. Subsequent sync calls are observed but are not independently fault-selected.
This is not a directory-sync or abrupt/container-restart recovery matrix.

Start from existing file_link_rpc/manifest_link_rpc qualification pauses. After
healthy LINK completion, the external observer intercepts syscall 74 on the exact
final-file descriptor, records its path/mount/inode/arguments and holds before
kernel execution. For payload, final/staging are complete aliases with two links,
PublishIntent and no manifest. For manifest, payload is already Published and
one-link final without staging; manifest aliases contain complete bytes with two
links and durable manifest_phase 3. Private source and original state remain held.

The observer runs with bounded local entry/exit rendezvous, no network, no service
package changes and no syscall substitution. Ptrace states t/T are artificial
stops, not NFS D-state. The syscall enter timestamp is reset after entry release;
its exit timestamp precedes the exit hold. Neither artificial hold belongs to the
actual syscall/RPC interval. A stopped-NFSD fsync may return successfully without
waiting for the server; record that measured outcome rather than inventing a
blocked sync. Only actual D-state syscall 74/expected FD plus raw evidence and
post-restoration completion can support a selected blocked-sync recovery claim.

## Step-by-step procedure

1. Use feature/rust-transfer-coordinator and cached pinned images. Inventory both
   Podman engines and preserve baseline volumes/networks. The rootful engine owns
   the private fixture; the default engine runs the mandatory SLES gates. No real
   SLES installation, NAS credentials or NAS-admin operation is required.
2. Start and retain both compatibility gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   They use locked cargo-zigbuild GNU/glibc 2.22, exact target tests in pinned SLES
   12 SP5 userspace and ELF/loader/library/symbol/negative audits. Passing identical-
   source earlier gates may supply live executables while fresh gates run; audit
   exact archive contents and shipping bytes across both sets afterward.
3. Validate the selected gate paths/report status before provisioning. Freeze
   acquisition scripts and run:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --publication-sync-discovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   This flag excludes the other recovery phases and captures eighteen exact
   acquisition sources. Do not edit them during the run. The separate input pack
   retains the independent verifier and its transitive auditors.
4. Follow the parent lab's private fixed-IP backend/internal network, separate
   storage keeper, two local-driver tmpfs volumes bounded to 64 MiB/4,096 inodes,
   read-only backing reader, unprivileged relay and pinned SLES client. Publish no
   ports. Verify distinct backing/client devices and local state, RO flags and
   keeper continuity. Keep root_squash/sync exports, fsids 68/69, fixture lease/
   grace ten seconds, and buffered NMP-41B hard,ac,async NFSv4.1 TCP/sec=sys mounts
   with timeo=10,retrans=1. These fixture settings are not a NAS production policy.
5. Repeat native NFSD/source, NFSD/destination, quiesced-container/source and
   quiesced-container/destination controls. Require actual pending original-FD
   operations, retained backing inode/handle, expected A-to-B bytes, successful
   sync/readback and normal exit. These remain distinct from mover-sync evidence.
6. For each actual case provision private roots and local state once. Submit
   identical JSON until confirmed 202/job 1, then reuse the source path with newer
   bytes. At the qualification pause attach the bounded external I/O observer with
   an exact target path, then release the Rust pause while the backend is healthy.
7. Wait for /tmp/sync-gate/entry.json in the observer. Require actual syscall 74,
   final-file path and worker t/T. Through an independent read-only backing mount,
   capture source/aliases and manifest bytes where applicable in one command.
   Record API phase, worker epoch, guard contention, worker UID/GID 1000, no active
   capabilities, NoNewPrivs and common Linux time namespace. No contender port
   collision is used as ownership evidence; this increment uses flock contention.
8. For stopped controls set NFSD to zero and confirm it, preserving server process/
   container/storage identity. Independently recheck custody. Retain a fresh relay
   checkpoint, timestamp entry release in the common Linux monotonic clock and
   touch the observer-local entry-go file.
9. Observe actual exit.json or D-state while only the selected syscall may run.
   If it blocks, record /proc syscall 74 and expected FD; if it exits, retain zero
   result and the completed interval before restoration. Hold the worker at exit
   so a later NFS access cannot be misidentified as the selected sync. Check local
   health/status, same worker/epoch and no duplicate child.
10. Timestamp restoration, restore NFSD if stopped and confirm original server/
    exports/storage and two threads. Wait for selected fsync exit if necessary.
    Recheck complete aliases/source/payload unchanged before releasing exit-go.
    Then require remaining successful syncs, same-worker attempt-1 commitment,
    actual worker exit, original final inode/hash with one link and staging absent.
11. Validate full manifest, retained private source/enrollment, unchanged original
    database inode/config and newer producer bytes. Stop cleanly, restart original
    state and replay identical JSON; require the same committed job/manifest and
    no producer-path changes. Keep the consumer's valid-manifest contract and no
    post-202 recorder monitoring duty.
12. Wait for the actual runner exit and cleanup_errors=[]. Restore before draining
    blocked users; normally unmount both NFS mounts, remove owned users/backend,
    verify keeper identity and remove it last. Release/remove role/parent volumes
    and the private network. Never force/lazy-unmount NFS, reset the VM or change
    global host/cgroup/NAS policy. Preserve failed acquisitions and exact observer
    sources before any correction.
13. After all lab and gate processes exit, capture final inventory and audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-publication-sync-discovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Verify raw RPC hashes/decoding, all sync intervals and captured pairs spanning
    entry, entry/exit gate ordering, classification before/after restoration,
    custody/phase/security/replay, proof corruptions, exact live/fresh artifacts,
    forty ELF reports and unchanged two-engine baseline metadata/networks.

## Results and limits

Read [increment 94](RUST-INCREMENT-94.md) and its retained raw/input packs for
eight successful observations: all four stopped-NFSD selected file fsyncs return
before restoration, with no captured selected-interval RPC records or pairs
spanning entry. No blocked file-sync recovery case is qualified. All 92 observed
sync calls return zero; two GETATTR pairs span later directory-sync entries with
replies after exit and are retained without causal attribution. Both SLES gates,
181 corrupted-proof controls, forty ELF audits and final normal cleanup pass.
The initial verifier schema failure and unchanged acquisition are preserved in
the result/input evidence. A zero-return call with no interval traffic is not proof of no
RPC under all workloads/caches, nor of physical persistence. Native dirty-write
recovery does not establish service clean-file fsync recovery. Unknown compounds
and wider-window RPC activity remain separate from interval attribution.

The keeper and modern WSL2 kernel retain bounded tmpfs memory. NFSD quiescence
precedes native container termination. No abrupt live-server, independent NAS,
persistent disk/power, outstanding UNSTABLE-data, full lease/reclaim/session or
old SLES kernel/client guarantee follows. Workload/cache/size/concurrency and
shipping deployment/access remain open. Artificial ptrace holds are test controls,
not service stop/deadline behavior. All eight release gates remain open. Keep
production NFS/private-source deletion disabled and registration/S3/repair/DOC-06
deferred. No source cleanup or consumer API-polling obligation is introduced.
