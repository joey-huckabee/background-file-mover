# Buffered source-claim lost-reply recovery lab

Read [finite acceptance/results](RUST-INCREMENT-84.md), the
[capability lab](NFS-CLAIM-CAPABILITY-LAB.md),
[fixture infrastructure](NFS-TEST-FIXTURE.md), [mount profiles](NFS-MOUNT-PROFILE.md)
and [testing limits](TESTING-LIMITATIONS.md). Production NFS/source deletion stay
disabled. This procedure changes no Rust, dependency, retry/review or deadline
policy. It uses the existing claim_link_rpc/claim_unlink_rpc pauses.

1. Work on feature/rust-transfer-coordinator and inspect both Podman engines:

   ```powershell
   podman ps -a
   podman volume ls
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root volume ls
   podman --connection podman-machine-default-root network ls
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Preserve unrelated containers, named caches and historical anonymous volumes.
   Use the approved rootful WSL2 Podman VM for the private NFS fixture, default
   engine for compatibility gates. See the linked infrastructure recipe for
   prerequisites and cached pinned images. No production mount/NAS/host policy
   or VM boot change is part of this increment.
2. Run and retain both mandatory gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require zigbuild GNU/glibc 2.22, locked dependencies, debug/release ELF audits
   and exact target tests in pinned SLES 12 SP5 userspace. Prior source-identical
   passing gates may supply fixture binaries while fresh gates run; final audit
   compares all 62 Rust files and forty exact artifacts to those used live.
3. Freeze acquisition/helpers/tests before creating the fixture:

   ```powershell
   python scripts/check-nfs-mount-profile.py --claim-loss --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   This mutually exclusive mode requires both gates, captures thirty exact source
   snapshots and repeats 43 inventory/model controls. The owned internal network
   has one privileged NFSD server, pinned SLES client and two unprivileged relays.
   Two synchronous root-squashed 128 MiB tmpfs exports retain all case data until
   teardown: twelve same-share cases plus twelve separate-share cases would
   exceed the earlier 64 MiB source export. Mount/export behavior is unchanged:
   hard NFSv4.1/TCP/sec=sys, ac,async,timeo=10,retrans=1 (NMP-41B).
   SQLite/configuration/ownership state stay local. Client setup/proc observation
   uses SYS_ADMIN/SYS_PTRACE/DAC_READ_SEARCH; workers and relays run UID/GID 1000,
   zero active capabilities, NoNewPrivs=1. One kernel/server is not two NASes.
4. On each layout run four hold/release controls first, then four live-drop and
   four death-drop cases: both claim operations and debug/release, 24 cases total.
   Each recording is one nested 2 MiB+17-byte file. Save original server inode,
   device, size, hash and one-link/absent-custody state. Submit asynchronously,
   pause the actual claim worker and observe/arm the named operation on both
   active transport relays. Do not infer carrier identity from mount addresses.
5. Every drop must first repeat successful server-completion proof. Require
   exact whole request/reply bytes, hashes, XID, status-zero results and no selected
   success forwarded. Sample actual linkat/unlinkat/D state and parent FDs; match
   their paths, mount IDs and independent server-parent inodes. Healthy NFSD
   stays at two threads. Server LINK must leave two aliases to the original
   inode; REMOVE leaves absent producer name and the original one-link custody
   object. Size/hash stay original. Require health/status within five-second
   fixture bounds, Accepted/unreleased status, retryable initial/same-ID 503 and
   absent destination job directory. Recorder paths remain untouched by the
   recorder until confirmed 202, even when the server producer name is absent.
6. Controls release the saved reply and proceed normally. Live cases instead
   discard that exact success and reset the carrier connection. Keep the same
   coordinator running. Retain raw forwarded requests/replies and require
   successful replay of the same cachethis=true namespace session operation on
   a new connection/receive ID. Preserve full operation/name/filehandle/session/
   sequence/slot/cache fields; only the existing highest-slot resource-hint
   normalization is allowed. The independent audit also compares complete raw
   request bytes, including metadata fields omitted by the summary decoder;
   only the RPC transaction ID and highest-slot hint are normalized. Each RPC
   transaction ID must still match its own raw reply. Reject missing, failed, differently targeted or
   unobserved replay evidence. Normal claim-worker retirement and assignment of
   a delivery worker are allowed after custody; this is not a promise that one
   process performs every phase. Sample health/status/same-ID responses through
   custody confirmation with the existing finite bounds.
7. Death cases kill the original coordinator while success is still withheld.
   Confirm coordinator exit and the orphan worker still in D. Verify the local
   lock identity is unchanged, nonblocking flock returns contention 73, the worker
   retains instance.lock without a SQLite descriptor, bounded status returns
   OwnerUnavailable, and a same-state contender is refused without changing the
   saved worker epoch. Recheck server aliases/held success, request worker KILL,
   discard/reset, then confirm actual worker exit (gone or single-thread zombie).
   Record post-KILL state without assuming KILL immediately cancels kernel work.
8. Before restarting, require server aliases/identity/hash unchanged. Freeze the
   pre-restart wire window, begin a separate new window and restart the exact
   original configuration/local database/enrollment. Preserve the original
   database inode and worker ownership rules. Confirm same-ID job 1/202 before
   producer-path reuse. This qualifies original-state reconciliation of the
   selected completed effect; no post-restart namespace RPC is required merely
   to manufacture a replay claim. Local exit/free guard is not remote settlement.
9. Every case must commit with payload attempt 1, verified destination manifest
   and hashes, original one-link private source, root/database/enrollment identity,
   retained newer producer-path bytes, retained claimed source and no job 2.
   Stop normally through the bounded controller. Never edit SQLite, re-enroll,
   manually publish/delete private objects or reset deadlines to force a pass.
10. Release armed relays before cleanup waits; normal-unmount, unexport and remove
    only owned containers/export volume/network. Preserve failed reports and exact
    snapshots before correcting/reacquiring. Use no lazy/forced unmount. Wait for
    the actual matrix and both gate processes to exit before final inventory.
11. Capture post-run-inventory.json with the
    [retained procedure](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Require zero containers on both engines, only the original two caches/default
    network on rootful, and unchanged unrelated default-engine volume metadata.
    Run the independent audit:

    ```powershell
    python scripts/verify-nfs-claim-capability.py rust/validation/<live-run> --loss --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    It validates raw hashes/decodes/capture bounds, held namespace/server/descriptor
    proof, live cached replay versus original-state death reconciliation, API/
    custody/state/source/manifest invariants, corruption controls, Python proof
    tests, thirty frozen sources, both live/fresh source archives, forty artifact
    comparisons and inventories. Retain the lossless compressed raw report/SHA,
    exact audit sources, fresh Rust archives, regression output and inventory in
    the CLAIM-LOSS evidence files. Update SC-118 and DOC-01–05; defer DOC-06.

The fixture discards a complete successful response and resets its TCP connection;
it does not model every packet loss, reconnect delay or silent half-open session.
Syscall sampling plus full raw relay traces is not complete ptrace entry/exit or
unique attribution of unrelated kernel traffic. Discrete API samples include
fixture transport overhead and do not establish continuous availability/SLA.
One modern shared kernel, one NFSD server and volatile exports cannot establish
physical NAS/old SLES kernel/maintenance-RPM or power durability, independent
appliance failover, server restart/verifier changes, delayed-effect settlement,
larger/many-file/cache/load/endurance regimes or pending source-sync RPC safety.
Producer-name REMOVE during claiming is distinct from disabled postcommit source
deletion. All eight first-release gates remain open.

The independent reply-side audit also decodes the successful SEQUENCE prefix and
checks its echoed session/sequence/slot identity against the request, following
[RFC 8881 sections 18.46.2–3](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.46).
This check uses retained raw bytes even though the summary decoder omits those
fields. A rehashed wrong reply-session control must fail. The acquisition and
Rust behavior remain unchanged.
