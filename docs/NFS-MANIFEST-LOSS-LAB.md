# Manifest WRITE lost-reply and original-state recovery lab

Read [increment 82](RUST-INCREMENT-82.md), the
[capability lab](NFS-MANIFEST-CAPABILITY-LAB.md),
[fixture infrastructure](NFS-TEST-FIXTURE.md) and
[testing limitations](TESTING-LIMITATIONS.md). This is container-only qualification;
production NFS and source deletion stay disabled. Each recording contains one
2 MiB+17-byte file and a small version-1 manifest; this is not a production-scale
or many-file workload.

1. Inspect both Podman engines and the rootful fixture image using capability-lab
   step 1. Preserve unrelated containers, networks, caches and anonymous volumes.
   Work on feature/rust-transfer-coordinator. Keep SQLite, configuration and the
   ownership guard local; both private transfer roots use buffered NMP-41B NFS.
2. Run both required gates and retain their complete directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require cargo-zigbuild GNU/glibc 2.22, locked dependencies, exact debug/release
   target tests in pinned SLES userspace and ELF audits. Previous source-identical
   passing gates may supply fixture binaries while fresh gates run, but the final
   audit must compare every source and all forty artifact bytes.
3. Before starting the fixture, run evidence tests and freeze the acquisition
   sources. Use a SQLite-enabled Python with normal temporary-directory access.
   A failed acquisition remains evidence; retain its full report and
   captured sources before any revision. Do not change a running acquisition.

   ```powershell
   python scripts/test_nfs_manifest_recovery.py -v
   python scripts/test_nfs_manifest_capability.py -v
   python scripts/check-nfs-mount-profile.py --manifest-loss --production-gate rust/validation/<passing-production-run> --qualification-gate rust/validation/<passing-qualification-run>
   ```

   The mutually exclusive selector requires both gates and captures thirty exact
   acquisition/helper/test sources. It repeats 43 inventory/model controls. The
   fixture uses one NFSD server, two root-squashed synchronous 64 MiB volatile
   exports, a pinned SLES client and two unprivileged relays on a private network.
   Hard NFSv4.1/TCP/sec=sys mounts use ac,async,timeo=10,retrans=1. Same-share roots
   and separate-share roots are logical layouts on the same server/kernel.
4. Run sixteen cases: discovery, hold/release, live-drop and death-drop, each in
   debug/release on each layout. Repeat the healthy and positive controls before
   injecting loss on that layout. Use the existing publish checkpoint, after
   payload verification, so WRITE interception targets manifest creation. Reuse
   the producer name with different bytes after the initial custody/202 response.
5. Discover the exact manifest WRITE using actual-worker syscall observation,
   descriptor inode/mount, metadata fsid/fileid, application-buffer bytes and raw
   RPC request/reply. Require FILE_SYNC request/result and full returned byte
   count. Capture both transports; destination paths can use the source relay.
   Do not infer service COMMIT requests from payload tests or unknown traffic.
6. For hold and fault cases, withhold the matched successful server reply. Record
   the original worker's actual syscall/FD/D state, server-local complete private
   manifest bytes/inode, live NFSD, absent public manifest, API manifest phase 1,
   published payload, health and same-ID 202. Compare to discovery. Mere server
   bytes or a stopped client are insufficient proof of withheld success.
7. Positive controls release the exact saved reply and commit. Live-drop cases
   discard it and reset the connection. Sample health/status/replay with the same
   coordinator and original worker assignment until commitment; reject review,
   a second payload attempt or a replacement worker. Require raw FILE_SYNC
   replay on the same handle, complete byte range and verifier. Distinguish a
   cached session response from NFS4ERR_RETRY_UNCACHED_REP followed by a new write.
   Only highest_slotid resource hints may vary in retry identity comparison.
8. Death-drop cases kill the coordinator and confirm actual process exit before
   copying SQLite DB/WAL. The orphan must remain D with the unchanged local
   instance.lock held (independent flock exit 73), and no SQLite FD. Hash exact
   copies before/after acquisition. Query disposable copies read-only, verify
   quick_check, original instance ID and saved phase-1 manifest bytes/hash/inode.
   Never inspect a live coordinator's SQLite database with this helper.
9. Recheck held success, kill the old worker, drop reply/reset and confirm actual
   worker exit before restarting. Record server bytes/inode after exit. Retain
   the complete pre-restart wire window and forwarded receive IDs, then start a
   separate post-restart window. Remove only the two old local rendezvous files.
   Restart with the same config/local state and existing manifest_link_rpc checkpoint.
   At that checkpoint require phase 3, public manifest absent and the original
   staging inode/exact bytes. Release and commit. A later application write from
   immutable intent is separate from native replay; do not require a session
   retry response for an application rewrite or infer remote settlement from
   local lock availability, process exit or the observation window.
10. Verify final payload hashes and manifest content, original source/private
    inode, database inode, enrollment, producer-path reuse, same-ID 202 and no
    job 2. Payload attempt must remain 1. Stop normally; after confirmed
    coordinator exit, copy DB/WAL again and verify phase 4 with identical
    original manifest bytes/hash/instance ID. Preserve all raw wire records,
    including other-handle traffic and undecoded calls.
11. Allow runner restoration and normal unmount-first cleanup to finish. Require
    status PASSED, no cleanup errors, disarmed/error-free relays, no owned
    containers/networks. Wait for both gate processes to exit before capturing
    post-run-inventory.json, including both engines' containers, volume metadata
    and networks. Rootful storage must contain only the two original Rust caches
    and default network; preserve unrelated rootless anonymous volumes. Use the
    [exact retained inventory commands and JSON procedure](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
12. Independently audit using the fresh gates:

    ```powershell
    python scripts/verify-nfs-manifest-capability.py rust/validation/<live-run> --loss --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    Require recomputed raw RPC hashes/decodes and descriptor attribution, held
    success and loss/recovery proofs, read-only copied intent checks, all thirty
    source snapshots, source archives and artifact bytes, evidence rejection
    controls and final inventory. Retain losslessly compressed raw acquisition,
    independent audit inputs, verifier and shared wire auditor, plus fresh
    canonical SLES reports. Only then update SC-116 and the future-only roadmap.

The lab does not qualify physical NASes, independently failing servers, original
SLES kernels or maintenance RPM patches, persistent media/power recovery, verifier
changes, all sizes/cache/load/durations, or general remote settlement. Bounded API
samples do not prove continuous availability. Ptrace affects healthy scheduling.
UID/GID 1000, zero active worker/relay capabilities and NoNewPrivs=1 model only the
fixture account. Deployment/account/access and stronger fencing gates remain open.

The initial acquisition selected manifest_link, which is after durable LINK:
original bytes/inode remained but link count was two, so the private-only assertion
failed. Its full raw report and thirty source snapshots are retained separately in
[increment 82](RUST-INCREMENT-82.md#initial-failed-acquisition). The corrected mode
uses manifest_link_rpc before LINK and repeats all sixteen cases. Preserve this
checkpoint distinction when adapting or reproducing the lab; do not weaken the
one-link/private-only assertion to make a later pause look like an earlier phase.

The second acquisition reaches Committed in its first death case, then its evidence
selector refuses an observed WRITE+GETATTR compound. The retained report records
that tooling failure separately; no missing phase-4 copy or unexecuted case is
counted as a pass. Restart validation now explicitly allows the observed trailing
GETATTR while preserving the full compound/raw bytes. Live retry identity and the
initial withheld request keep the original exact shape; other appended operations
remain refused. Read increment 82 for retained hashes and the complete reacquisition.
