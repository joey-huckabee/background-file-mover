# Rust increment 79: qualify buffered UNSTABLE WRITE reply loss

## Finite scope and acceptance

Keep production NFS and source deletion disabled. Preserve Rust behavior,
dependencies, retry/review policy and all assignment/shutdown deadlines.

The accepted finite scope is six native controls and eight service cases on
NMP-41B same-share/separate-share layouts, debug/release service profiles:

- Native discovery/release/drop on each layout, before service faults there.
  Require actual payload-fchmod WRITE stable=0, successful reply committed=0,
  full count, matched request/reply held before forwarding, actual pending
  descriptor/D state and server-local complete payload inode/size/hash with
  live NFSD. FILE_SYNC cannot substitute. For drop plus connection interruption,
  require successful retransmission of every original handle/range/byte set,
  and a later successful matching COMMIT if the resend remains UNSTABLE.
- Four live-release cases commit on attempt 1. Four coordinator-death/worker-kill/
  reply-drop cases preserve orphan ownership, confirm actual exit before original-
  state restart, retain the uncertain first partial and complete a new attempt.
  Preserve original source/state/enrollment, newer producer bytes, same job/202
  replay and final verified manifest, without manual state edits or job 2.
- Both fresh mandatory SLES/glibc 2.22 gates, current/live/fresh Rust/archive and
  forty-artifact comparison, raw proof/negative controls, exact snapshots and
  clean final inventories. Maintain SC-113 and DOC-01–05; DOC-06 stays deferred.

Read [the complete lab](NFS-BUFFERED-UNSTABLE-LAB.md) for setup, commands,
infrastructure, proof distinctions and cleanup. Preserve any failed acquisition
with its exact drivers; qualify service cases only after native capability passes.
No original-kernel/NAS/power durability or live-loss-without-death support is implied.

## Initial qualification failure

Run `mount-profile-20261019T180234Z-e444c48b` fails at native drop validation,
with cleanup_errors=[] and **zero service cases**. The complete original failed
report and all 26 exact acquisition/test sources remain in
[initial evidence](RUST-NFS-BUFFERED-UNSTABLE-INITIAL-EVIDENCE.json); it is not
passing service qualification. The validator required the full SEQUENCE argument
bytes to be identical for an uncached retry. Captured retries preserve the same
session, slot, sequence, stateid, filehandle, range and bytes but update the
highest_slotid hint as three requests become outstanding.

The [NFSv4.1 specification, section 2.10.6.1](https://www.rfc-editor.org/rfc/rfc8881.html#section-2.10.6.1)
distinguishes session/slot/sequence retry identity from the highest-slot usage
hint. The corrected comparison permits only that hint to vary while preserving
all other decoded arguments; it also checks the hint covers the current slot.
Counterexamples reject changed session, sequence, slot, cache policy, ranges,
bytes, verifier, incomplete success sets and unrelated/earlier COMMIT. Eight
regression methods pass before rerunning the full finite matrix. No Rust or
service retry/deadline fix is required.

The failed-run wire records contain three RETRY_UNCACHED_REP replies, then three
successful new UNSTABLE WRITEs covering all original ranges with the original
verifier, followed by matching successful COMMIT. This explains the validator
failure; it does not relabel the failed acquisition as a complete passing run.

## Passing results

Corrected run `mount-profile-20261019T180934Z-a6179534` **passes** all six native
controls, eight service cases, 43 inventory/model controls and eight new resend
regression methods, cleanup_errors=[]. The [complete raw evidence](RUST-NFS-BUFFERED-UNSTABLE-EVIDENCE.json)
retains the exact original report bytes in a lossless compressed envelope,
including all 26 acquisition/helper/test sources, RPC payloads, native traces,
clocks, pending-proc evidence, server objects and recovery snapshots.
The [input evidence](RUST-NFS-BUFFERED-UNSTABLE-INPUT-EVIDENCE.json) retains the
independent verifier, native binary/auditor, regression output and fresh archives.
The initial failed acquisition remains failed and separate.

Each layout proves all three server-completed UNSTABLE ranges held before
forwarding: offsets 0/1048576/2097152 and counts 1048576/1048576/17. Actual native
and service processes are D-state in fchmod syscall 91, mode 0400, on the expected
target FD. That FD inode matches the controlled server object; server-local full
size/hash is correct while all successes remain withheld, with two live NFSD
threads. Requests stable=0 and replies committed=0 are decoded, full-count and
checksum verified. FILE_SYNC is not substituted.

Both native drops explicitly interrupt the connection. Each captures three
RETRY_UNCACHED_REP responses, including two with updated highest-slot hints,
then three new WRITEs on the same original handle/ranges/bytes. All actual
resends request UNSTABLE and receive UNSTABLE success with the original verifier;
one subsequent matching successful COMMIT covers all three ranges on each
layout. The verifier requires it to follow the successful resend replies.
Native fchmod/fsync return zero and server inode/size/hash remains unchanged.
The synthetic stronger-stability test is not claimed as an observed live resend.

Capture both active relays. All selected native/service WRITE traffic uses the
source relay, including separate shares; the destination mount address does not
identify the actual transport. Both shares use one controlled server/kernel.

| Layout | Profile | Live release | Coordinator death / worker kill / drop |
| --- | --- | --- | --- |
| Same share | Debug | Committed, attempt 1 | Committed, attempt 2; first partial retained |
| Same share | Release | Committed, attempt 1 | Committed, attempt 2; first partial retained |
| Separate shares | Debug | Committed, attempt 1 | Committed, attempt 2; first partial retained |
| Separate shares | Release | Committed, attempt 1 | Committed, attempt 2; first partial retained |

While replies remain withheld, health stays responsive, the local durable file
receipt stays Intent, one assigned worker remains and identical-ID replay still
returns 202 for confirmed source custody. The recorder reuses its producer path
only after 202; newer bytes survive every case. In each death case, the actual
coordinator PID and nonzero exit are recorded, an independent nonblocking local
flock probe returns 73 while the original orphan is D-state, and guard identity
is unchanged. Kill that worker, drop replies/connection and confirm actual exit
before original-state restart. Preserve the original uncertain partial inode,
size and hash; recovery allocates attempt 2 without deleting/adopting that partial.

All final manifests and destination hashes validate. Original claimed source
inode/hash, database inode/enrollment, reused producer bytes and job 1 remain
intact; job 2 is absent and source cleanup remains disabled. Recovered services
stop normally. There is no Rust, dependency, API, retry/review, assignment or
shutdown-policy change. Keep the shared COMMIT mode and earlier I/O/sync modes;
their verifiers accept the expanded 26-driver capture with exact byte checks.

## Compatibility, independent audit and cleanup

Both fresh mandatory gates **pass**:

| Build | Run | Debug/release tests |
| --- | --- | --- |
| Production | `20261019T175931Z-e1557bde` | 211 / 211 |
| NFS qualification | `20261019T175932Z-5a3a166d-nfs-qualification` | 212 / 212 |

Locked cargo-zigbuild GNU/glibc 2.22, pinned SLES userspace execution, relocation
checks, six negative ELF controls and the unchanged 42-dependency graph pass.
The independent audit compares all 62 current/live/fresh Rust archive entries
and all forty live/fresh artifact bytes. Live binaries come from passing source-
identical increment-78 gates. Native fixture ELF is retained separately: GNU
loader, libc.so.6 only and maximum GLIBC_2.2.5 imports. It adds no shipping target.

The independent --unstable audit **passes** raw payload SHA/decoding/bounds,
matched held-before-forwarding proof, full three-range coverage, pending FD/server
inode, retransmission and later-COMMIT ordering, native/service outcomes, guard,
state/source/replay/manifest invariants and exact acquisition/verifier snapshots.
Eleven negative proof mutations pass; seven decoder, eight I/O-analysis and eight
resend regression methods pass with output retained. The full initial failed
report/source snapshots are independently checksum-verified and remain failed.
Streaming retention hashes/compresses the exact report file without another full
in-memory JSON serialization; no observation is dropped.

Final inventory is captured after both gates and the NFS runner exit. Both Podman
engines have zero containers; rootful has only its two original cache volumes and
default network. Rootless keeps its original caches and eleven unrelated September
anonymous volumes, with creation metadata preserved. No cleanup uncertainty is waived.

## Scope and next work

SC-113 feeds DOC-01–05 through the [complete procedure](NFS-BUFFERED-UNSTABLE-LAB.md);
preserve 113 SC IDs and six DOC IDs. The recorder gains no post-202 monitoring duty.
Live WRITE/COMMIT loss without coordinator death, other ranges/phases/cache/load/
size/outage cases, server restart/changed verifier and delayed-effect settlement
remain future work. DOC-06 remains deferred.

Pinned SLES 12 SP5/glibc 2.22 userspace runs on
`6.18.33.2-microsoft-standard-WSL2`. One server and volatile tmpfs exports do not
establish original SLES kernel/maintenance-package behavior, independent NAS
failure domains, NetApp/Isilon interoperability or physical power durability.
UNSTABLE success is not persistence proof; COMMIT on this server is not power-loss
proof. Protocol/FD/server correlations are controlled fixture evidence, not unique
kernel causality or authenticated global NAS identity. Local worker exit/guard
availability is not remote settlement. Keep production NFS/source deletion disabled
and all eight first-release gates open.
