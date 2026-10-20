# Manifest-side successful-reply withholding lab

Use the retained [fixture infrastructure](NFS-TEST-FIXTURE.md).
Read [increment 81](RUST-INCREMENT-81.md), the [mount profile](NFS-MOUNT-PROFILE.md)
and [testing limits](TESTING-LIMITATIONS.md). Production NFS/source deletion remain
disabled. This establishes actual manifest capability before future loss/death
recovery tests. It adds no Rust behavior, dependency, pause or executable.

1. Work on feature/rust-transfer-coordinator. Inspect both Podman engines for
   unrelated running containers. Use the approved rootful WSL2 Podman VM for the
   NFS fixture and the default engine for Rust gates. Preserve original caches,
   images, networks and unrelated September anonymous volumes.
   ```powershell
   podman ps -a
   podman volume ls
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root volume ls
   podman --connection podman-machine-default-root network ls
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

2. Run and retain both mandatory compatibility gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require locked cargo-zigbuild GNU/glibc 2.22, exact debug/release target tests
   in pinned SLES 12 SP5 userspace, ELF/relocation audits and negative controls.
   Source-identical previous passing gates may supply live binaries while fresh
   gates run; final audit must compare all 62 current/live/fresh Rust entries and
   all forty exact artifact bytes. No real SLES installation or host Cargo test
   substitutes for these container gates.
3. Freeze acquisition/helpers/tests before starting the mutually exclusive mode:

   ```powershell
   python scripts/check-nfs-mount-profile.py --manifest-capability --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   The runner captures 28 exact sources and repeats 43 inventory/model controls.
   Its private internal network contains one privileged NFSD server, a pinned
   SLES client and two unprivileged reply relays. Two synchronous root-squashed
   64 MiB tmpfs exports provide same-share disjoint roots and separate-share
   logical roots. Both share one server/kernel; they are not independent NASes.
   Mount hard NFSv4.1/TCP/sec=sys with buffered NMP-41B ac,async, timeo=10,
   retrans=1. State, SQLite, configuration and ownership guard remain local.
4. Run exactly eight actual-worker cases. On each layout, healthy debug/release
   discovery must precede both debug/release hold controls. Reuse the existing
   publish rendezvous after payload verification and before file publication;
   start the worker only after source custody/202. Reuse the producer path with
   different bytes after 202. The remaining worker window includes actual file
   publication, manifest allocation/write/permission change/sync/publication.
5. Healthy discovery attaches the bounded external networkless I/O observer to
   the real delivery worker. Inspect actual client/observer/both-active-relay
   clock namespaces. Capture syscall entry/exit/results, local proc descriptor
   metadata and bounded NFS application write buffers. The service/worker/relays
   run UID/GID 1000, zero active capabilities and NoNewPrivs=1; setup needs
   SYS_ADMIN and the observer needs SYS_PTRACE/DAC_READ_SEARCH. Change no host
   ptrace or NAS policy. Ptrace changes scheduling; this is no benchmark.
6. Capture both active transport windows. A destination mount address does not
   identify which session carries its RPCs. Require successful metadata/fsid/
   fileid and descriptor anchors, exact application-buffer and server-final bytes,
   full-range WRITE and paired successful request/reply in an actual descriptor
   syscall interval. Record requested/returned stability and every same-handle
   COMMIT request, even if none appears. Unknown/unmatched traffic stays raw and
   explicit. Timing or a visible filename alone cannot qualify the manifest.
7. Only after discovery on that layout, arm WRITE (38) on both active relays in
   each hold control. Match server status-zero success before forwarding. Require
   one complete manifest request/reply, actual blocked syscall/target FD/D state,
   local FD inode matching the controlled server object, complete server-local
   JSON bytes/hash/size/inode and live NFSD. Requested/returned stability and the
   pending syscall must agree with the actual discovery for that profile.
8. While the reply remains held, require health within the existing five-second
   fixture bound, job not Committed/review-required, payload Published, same live
   coordinator/assigned worker and same-ID job 1/202. Confirm server-side public
   COMMITTED.json is absent. Private complete bytes are not public commitment.
   Recheck that no selected success was forwarded, then release the saved reply.
   Do not drop/intercept further replies, kill/restart the coordinator, alter
   SQLite, reset deadlines, re-enroll or delete private staging to get a pass.
9. Require ordinary attempt-1 commitment, original manifest inode and exact bytes
   at COMMITTED.json, validated final payload/manifest, original private source
   inode/hash, database inode/enrollment, newer producer bytes, retained source,
   same-ID 202 and no job 2. Normal supervised worker retirement follows actual
   commitment; trace exit 0/9 must be interpreted with that receipt, not as an
   injected coordinator-death case. Stop normally through the bounded controller.
10. Release any armed relay before waiting during cleanup. Confirm actual exit,
    normal unmount, unexport and removal of only owned containers/export volume/
    network. No forced/lazy unmount. Keep uncertain cleanup FAILED with resource
    identities. Preserve complete failed reports and their exact source snapshots.
11. After the runner and both gates exit, capture post-run-inventory.json using
    the [retained inventory procedure](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Both engines must have zero containers; rootful must retain only its two
    original cache volumes and default network. Preserve unrelated volumes and
    their creation metadata. Run the independent audit:

    ```powershell
    python scripts/verify-nfs-manifest-capability.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    It verifies raw wire hashes/decodes/bounds, syscall/buffer/identity attribution,
    actual held-success proof and release, state/source/replay/final-manifest
    invariants, negative controls and exact source/forty-artifact provenance.
    Retain compressed exact raw report bytes, SHA-256, fresh Rust archives,
    acquisition/audit snapshots, regression output and inventories. Update SC-115
    and DOC-01–05 with actual results, preserving all earlier identifiers.

The finite workload uses one 2 MiB+17 recording file and its small version-1
manifest. It does not qualify many-file manifests or production-scale throughput.
This finite lab establishes successful-reply holding/release, not reply-loss,
uncached replay, coordinator-death, server reboot/verifier change or longer-outage
recovery for the manifest. Small FILE_SYNC writes do not establish a withheld
manifest COMMIT, unobserved source sync, all sizes/cache/load/phases or old SLES
kernel/maintenance-package support. Volatile tmpfs and server acknowledgements
are not physical power durability or NetApp/Isilon interoperability. Local exit
or guard availability is not remote settlement or authenticated NAS authority.
Health/status checks are discrete observations, not continuous availability.
All eight first-release gates remain open; DOC-06 and other deferred work stay
parked. Define the next finite loss/recovery matrix only from proven capability.

The finite manifest WRITE reply-loss/recovery extension is documented in
[the manifest loss lab](NFS-MANIFEST-LOSS-LAB.md) and
[increment 82](RUST-INCREMENT-82.md). Keep its live replay and post-restart
application recovery evidence distinct from these capability/release controls.
