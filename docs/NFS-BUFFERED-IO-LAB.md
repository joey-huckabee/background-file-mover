# Buffered NFS worker I/O attribution lab

Use the approved [fixture](NFS-TEST-FIXTURE.md) and
[buffered synchronization infrastructure](NFS-BUFFERED-SYNC-LAB.md). Read
[increment 77](RUST-INCREMENT-77.md) for actual results. Production NFS and
source deletion remain disabled; this is qualification infrastructure only.

1. On `feature/rust-transfer-coordinator`, inspect both engines' containers and
   rootful volumes/networks. Reuse the approved WSL2 VM and pinned images. Stop
   for unrelated active labs; delete no unrelated data or caches.
2. Run and retain both mandatory gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require locked cargo-zigbuild GNU/glibc 2.22, exact debug/release tests in pinned
   SLES userspace, ELF audit and negative controls. Source-identical prior passing
   gates may supply live artifacts while fresh gates run, provided the final
   audit compares current/live/fresh Rust entries and all forty artifact bytes.
3. Run the new, mutually exclusive matrix:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-io
   ```

   The runner repeats the 43 inventory/model checks and captures 24 exact driver
   files. One owned privileged NFSD server exports two 64 MiB tmpfs filesystems;
   the client uses hard buffered NFSv4.1/TCP/sec=sys `ac,async` mounts through two
   UID-1000 relays. Same-share roots are disjoint on one mount; separate-share
   roots use both exports. Both share one server/kernel/outage domain. State,
   SQLite, configuration and ownership guard stay on another local filesystem.
4. The root observer needs SYS_PTRACE and DAC_READ_SEARCH in addition to mount
   setup's SYS_ADMIN. The external tracer is networkless and joins the client's
   PID namespace. Workers/services/controllers/HTTP/relays remain UID/GID 1000,
   zero active capabilities, NoNewPrivs=1. Change no host ptrace policy or NAS
   administration. Inspect actual security and actual live time namespaces
   before releasing each qualification pause.
5. Run claim and delivery in both profiles/layouts. At the existing local
   `claim_apply`/`copy_chunk` rendezvous, attach `nfs_io_trace.py`, start both active
   wire windows and release the worker. The trace starts at this checkpoint;
   earlier worker I/O is outside capture. Linux x86_64 syscall numbers follow
   [the kernel table](https://github.com/torvalds/linux/blob/v6.6/arch/x86/entry/syscalls/syscall_64.tbl).
   Record open/read/write/close, stat/chmod/namespace and synchronization events,
   raw arguments, entry/exit/result and local proc descriptor snapshots. Capture
   only NFS write buffers, bounded to 1 MiB each/8 MiB total, with SHA-256 and
   lossless compression. No target-file observation I/O is injected.
6. Keep syscall execution intervals separate from descriptor inspection at
   stops. Ptrace still changes scheduling and can permit kernel background work;
   timestamps are observation intervals, not a performance benchmark. Preserve
   negative/unsupported results rather than inventing a successful operation.
7. Decode fsid/fileid only from fully decoded request/reply compounds and a
   supported ordered attribute prefix. Preserve exact raw bytes and the original
   decoder's default representation. Unknown attributes/compounds cannot make
   positive identity proof. Map a descriptor only with matching fileid and an
   unambiguous paired GETATTR inside successful descriptor-stat/open execution,
   or matching WRITE inode/range/bytes inside actual write execution. Retain evidence hashes and
   distinguish metadata matches from byte/range matches. Conflicting anchors
   refuse. Track SAVEFH/RESTOREFH current/saved handle state; GETATTR may describe
   a restored handle rather than the last PUTFH. Annotate WRITE/COMMIT requests
   with plain overlap and anchored overlap
   separately; neither proves universal unique kernel causality.
8. Require successful observed syncs, actual worker exit and already-Committed
   attempt-1 receipt before accepting normal delivery retirement. Accept initial
   retryable 503 only with paths unreleased; confirm identical-ID job 1/202 before
   reusing producer paths. Require validated manifest, original private source
   inode/hash, database inode/enrollment, newer producer bytes and no job 2.
   Stop cleanly. Source prehashes are fixture comparisons; shipping 3N I/O stays
   unchanged. No service reply loss, coordinator death or storage outage occurs.
9. After all users exit, unmount normally, unexport and remove only owned
   containers/export volume/network. Release any armed relay before waiting;
   this mode itself never arms one. Preserve uncertain resources and mark FAILED
   if cleanup fails. Use no forced/lazy unmount. Keep cached images/volumes and
   unrelated older anonymous volumes.
10. Capture `post-run-inventory.json` in the live directory using the exact
    command in the [sync lab](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Require both engines have no containers, rootful only the two original cache
    volumes and default network. Then run:

    ```powershell
    python scripts/verify-nfs-buffered-io.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    The verifier checks full tuples/security/clocks, all payload hashes/raw RPC
    decodes, event bounds and recomputed attribution, complete sync intervals,
    source/state/202/manifest invariants and forty fresh/live ELF bytes. Retain
    exact verifier, 24 driver snapshots, fresh source archives, actual analysis
    and inventory. The independent audit also derives mount-fsid witnesses from
    successful metadata matches, then qualifies descriptor inodes using both
    fsid and fileid before attributing a request to an overlapping file operation.
    It retains paired WRITE/COMMIT reply outcomes and ten rejection controls:
    wrong fsid/inode, missing mount witness, missing overlap, unknown handle and
    conflicting mount witnesses, plus wrong buffer bytes/ranges, failed writes
    and writes after the request. It also matches later network WRITEs to earlier
    successful captured buffers with the same fsid-qualified object and exact
    range/hash, keeping that proof distinct from RPCs inside a write syscall.
    This postprocessing uses only retained records;
    it injects no worker operation or target observation I/O.
    Preserve earlier reports separately. The raw evidence uses
    the same SHA-verified `zlib-base64-json` envelope as increment 76.

These finite observations share a modern WSL2 kernel and volatile tmpfs; they do
not qualify an old SLES kernel, independent NAS/appliance caches, failover,
physical-media/power durability, arbitrary file sizes/cache/load or production
NFS. Fileid/fsid correlation is fixture evidence, not authenticated NAS authority
or permission to reconcile/delete uncertain data. Unmatched operations and
unknown compounds remain future work. All first-release gates remain open.

## Actual manifest capability extension

[Increment 81](RUST-INCREMENT-81.md)/SC-115 establishes actual manifest-side
successful-reply withholding: four healthy worker traces, then four hold/release
controls across both buffered layouts/profiles. The
[step-by-step lab](NFS-MANIFEST-CAPABILITY-LAB.md) separates actual manifest
WRITE stability and pending permission change from earlier payload COMMIT/
UNSTABLE evidence. Complete private bytes do not imply public commitment.
All cases preserve original source/state/enrollment and commit attempt 1 after
release. Reply loss, replay and coordinator-death recovery at this boundary
remain future work; all eight release gates and production NFS/deletion remain
unchanged. Maintain DOC-01–05; DOC-06 stays deferred.
