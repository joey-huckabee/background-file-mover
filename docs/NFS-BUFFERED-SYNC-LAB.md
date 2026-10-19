# Buffered NFS synchronization observation lab

This retained extension observes actual service synchronization before selecting
reply-loss tests. Use [increment 76](RUST-INCREMENT-76.md) for measured results,
the [mount-profile lab](NFS-MOUNT-PROFILE-LAB.md) for inventory controls and the
[fixture guide](NFS-TEST-FIXTURE.md) for approved VM setup. Production NFS and
post-delivery source deletion remain disabled.

## Infrastructure and execution

1. Use `feature/rust-transfer-coordinator` and the existing approved Podman WSL2
   VM. Check for unrelated active labs and the cached server image:

   ```powershell
   git status --short --branch
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Record existing volumes/networks. Do not remove other runs' resources, change
   host ptrace policy or silently replace pinned images. Missing infrastructure
   follows the fixture setup procedure.
2. Run both mandatory compatibility gates and retain their printed directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require locked cargo-zigbuild GNU x86_64/glibc 2.22, exact debug/release target
   tests in pinned SLES userspace, ELF interpreter/library/symbol audits and
   negative controls. Host Cargo tests cannot replace these gates.
3. Run the eight healthy service traces:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-sync
   ```

   This is mutually exclusive with other worker matrices. The runner first
   repeats 43 model/inventory controls, verifies gate archives against current
   Rust entries and hashes transferred binaries. Source-identical prior passing
   gates can supply live binaries while fresh gates run; retain that distinction
   and compare all forty fresh artifact bytes afterwards. Snapshot all 21 driver
   files exactly, including tracer, relay, decoder and native probe sources.
4. The run owns an internal network, named export volume, privileged kernel-NFS
   server and pinned SLES client. Root-squashed synchronous child exports use
   fsids 68/69 on separate 64 MiB tmpfs devices. Two unprivileged relay containers
   forward to that one server; they do not model independent NAS appliances.
   Mount through the relays from the beginning using NFSv4.1/TCP/sec=sys, hard,
   `ac,async,timeo=10,retrans=1`. Check actual mountinfo, absence of `noac`/`sync`,
   NMP-41B bindings and filesystem identities. Same-share uses disjoint private
   role roots on the source mount. Separate-share uses both source and destination
   mounts/relays. Capture both relays for separate-share service and native
   observations: the initial fixture observed both exports' traffic through the
   source relay while the destination relay was idle. A mount address does not
   establish which transport actually carries an operation. Select a withholding
   relay only from positive decoded discovery records.
   State/configuration/SQLite/guard remain on a different local
   filesystem. The short retransmission settings are fixture settings, not a
   shipping-mount recommendation.
5. Root setup needs SYS_ADMIN; the client observer additionally needs SYS_PTRACE
   and DAC_READ_SEARCH. An external, networkless ptrace container joins the
   client's PID namespace with only the two observer capabilities. Service,
   worker, controller, HTTP and relay processes run as UID/GID 1000 with zero
   active capabilities and NoNewPrivs=1. Relays have no host-published ports and
   use private reserved source ports. The native C probe is fixture-only, built
   by pinned Zig for GNU/glibc 2.22 and audited; it is not another Rust executable
   or production dependency.

## Eight worker observations

Run `claim_apply` and `copy_chunk` in debug/release on same/separate shares.
These hooks are local observation rendezvous, not injected storage failures.

1. Initialize fresh protected roots and enrollment; create nested 2 MiB plus
   17 byte input. Retain fixture source inode/size/hash and local database and
   enrollment identity. Fixture prehashes are diagnostic comparisons; normal
   delivery still hashes during copy and rereads staging, preserving 3N I/O.
2. Start the qualification service, POST asynchronously and wait for the actual
   single-threaded assigned worker. Require UID/GID/capability evidence. Attach
   the tracer before releasing the local pause. Read `/proc/self/ns/time` from
   the live client, that actual observer and active relays; require identical
   clock namespaces. A separately launched monitor cannot substitute for this
   actual-process proof. Same-share has three actors, separate-share four.
3. Start bounded relay capture, then release the worker. The external tracer
   records actual x86_64 fsync (74)/fdatasync (75) entry/exit, return values,
   descriptor paths and mount IDs using local proc records. It does not stat or
   read target files to discover descriptors, avoiding observer-induced target
   I/O. Capture raw RPC request/reply payloads with monotonic timestamps, hashes
   and lossless compression; decoder errors/unknown compounds remain explicit.
4. Require worker exit and successful sync returns. Delivery supervision may
   retire an idle worker with SIGKILL; require the recording already Committed
   on attempt 1 before treating that as normal retirement. A claim worker must
   exit zero. This is not coordinator-death or worker-fault testing.
5. Independently decode retained wire bytes and correlate every captured call
   timestamp with each actual syscall interval. Authoritative NFS totals use
   mount IDs, including syncs on the exact root directory. The helper's
   `nfs_syncs` convenience field selects primary-role descendants and excludes
   exact roots; do not use it alone to claim all-RPC absence. Keep full `trace`
   and `wire` records. The independent audit also counts replies inside sync
   and captured request/reply pairs spanning entry, so a request sent just before
   entry is not mistaken for an empty pending-operation history. Requests outside
   the capture or without a captured reply remain outside that pair analysis.
   Correlation does not establish unique causal attribution
   when kernel/background or other role traffic shares a window.
6. Observation setup can exceed the existing handoff response budget. An initial
   retryable 503 with unreleased paths is acceptable; require identical-ID replay
   to return job 1/202 with released paths before writing `next recording` at the
   producer name. Require normal Committed/attempt 1, validated manifest, original
   private source inode/hash, unchanged database inode/enrollment, newer producer
   bytes retained and job 2 absent. Stop cleanly with the bounded controller.

## Conditional native withholding controls

After four healthy worker cases on each layout, run a native buffered 4 KiB
dirty-write/fsync discovery with the same tracer and actual clock-identity proof.
Select only a decoded WRITE (38) or COMMIT (5) actually observed inside both
service and native sync windows, counting all NFS mount IDs in service traces.
Capture both active relays for separate shares and correlate their combined
records. If none exists, record an unavailable service-matching capability
with its reason; do not invent a COMMIT or arm an unobserved service operation.

For an available operation, perform separate `release` and `drop` controls:

1. Arm the relay before allowing the native process into fsync. Match request
   and successful server reply by XID and operation, withholding the reply before
   forwarding it. Require actual native D state, syscall 74 and the expected FD
   path. Require NFSD still has two threads and server-local inode/size/link/hash
   evidence equals all 4096 expected bytes while the success remains withheld.
2. Recheck the held state. Release the saved success, or discard it and interrupt
   that connection. In either case require native fsync to return zero and
   server-local identity/content to remain unchanged.
3. For discard, validate actual retransmission: exact replay, or the protocol's
   uncached-reply error followed by equivalent handle/range/data WRITE on a new
   connection with a new sequence/state ID. Do not call semantic resend a
   byte-identical RPC replay. Retain raw wire proof and stability/commit fields.

These are independent OS controls, not Rust service reply-loss/recovery cases.
FILE_SYNC WRITE success does not establish COMMIT capability, physical-media
persistence or power-loss safety.

## Independent audit, retained evidence and cleanup

After live and both fresh gates pass, complete cleanup and capture the
post-run inventory using the command below. Then run:

```powershell
python scripts/verify-nfs-buffered-sync.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
```

The verifier checks all eight tuples, driver bytes, actual clock identities,
security, raw payload SHA/decoding/capture bounds, complete mount-ID sync counts,
correlation, acceptance/commit invariants and conditional native controls. It
compares all current Rust entries to live/fresh archives and all forty fresh
artifacts to live input bytes. It retains the exact verifier, gate auditor source,
probe binary and fresh archives in input evidence. No Rust source is modified.

`RUST-NFS-BUFFERED-SYNC-EVIDENCE.json` is a lossless `zlib-base64-json` envelope:
Base64-decode `report_zlib_base64`, zlib-decompress, verify `report_sha256` against
those decompressed bytes, then parse JSON. The input evidence remains ordinary
JSON. Compression keeps all raw observations; it is not a summary substitute.
Canonical SLES evidence updates only after every independent assertion passes.
Preserve failed attempts and exact inputs if any, separately from passing results.

Always release held replies before waiting for processes. After all users exit,
unmount normally, unexport, and remove only owned containers/export volume/network.
Keep cached toolchain volumes/images. If cleanup is uncertain, retain exact owned
resources and mark FAILED; use no forced/lazy NFS unmount or host/NAS changes.
Independently inspect both Podman engines for containers and compare rootful
volumes/networks to the pre-run inventory. Save the structured result as
`post-run-inventory.json` in the live run directory before running the verifier;
it retains this inventory in input evidence and requires empty container lists,
the two pre-existing rootful cache volumes and only the default rootful network.

For this approved fixture baseline, capture the inventory after both fresh gates
and the live matrix exit, then run the verifier command above:

```powershell
@'
from datetime import datetime, timezone
import json, subprocess
from pathlib import Path
def inventory(extra):
    base = ['podman', *extra]
    def rows(*args):
        return subprocess.check_output(base+list(args), text=True).splitlines()
    volumes = rows('volume','ls','--format','{{.Name}}')
    metadata = json.loads(subprocess.check_output(
        base+['volume','inspect',*volumes], text=True)) if volumes else []
    return dict(containers=rows('ps','-a','--format','{{.ID}}'),
                volumes=volumes,
                volume_metadata=[{k:v.get(k) for k in ('Name','CreatedAt','Anonymous','Labels')}
                                 for v in metadata],
                networks=rows('network','ls','--format','{{.Name}}'))
result = dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),
              default=inventory([]),
              rootful=inventory(['--connection','podman-machine-default-root']))
Path('rust/validation/<live-run>/post-run-inventory.json').write_text(
    json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps(result, indent=2))
'@ | python -
```

## Limits and follow-up

One client, one controlled server, two logical exports, volatile tmpfs and shared
modern WSL2 kernel do not qualify NetApp/Isilon behavior, independent appliance
failover, SLES's old kernel, disk/controller power loss or arbitrary cache/load/
file-size regimes. Ptrace changes scheduling; timings are not performance claims.
Unknown/nonempty or overflowed windows cannot prove RPC absence. A returned
directory fsync need not send a packet; no observed COMMIT does not mean the
service omitted synchronization. Keep historical noac NMP-41N evidence separate.

Use positive observations to define the next finite service fault matrix; this
increment injects no service synchronization reply loss, coordinator death or
storage outage. No new retry/review/shutdown policy or recorder monitoring duty
is introduced. All eight first-release gates remain open. SC-111 feeds DOC-01–05;
DOC-06 remains deferred.
