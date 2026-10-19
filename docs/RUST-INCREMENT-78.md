# Rust increment 78: qualify buffered payload COMMIT reply loss

## Scope and acceptance

Keep production NFS and source deletion disabled. Change only retained fixture,
evidence and documentation; preserve Rust behavior, retry/review policy and all
shutdown/assignment deadlines. Work on `feature/rust-transfer-coordinator`.

The finite acceptance matrix is:

- Six native controls: discovery, release and connection-interrupted reply drop
  on each NMP-41B same-share/separate-share layout. Reproduce payload fchmod
  COMMIT, not the earlier 4 KiB FILE_SYNC WRITE path. Require matched decoded
  server-success reply withheld before forwarding, actual pending fchmod target
  FD, server-local inode/size/hash, live NFSD, normal completion and real replay.
- Eight service cases: debug/release, both layouts, live reply release and
  coordinator death followed by worker termination/reply drop. Each starts at
  the existing copy checkpoint and proves an actual payload fchmod COMMIT stall.
  Check health/local durable Intent, unchanged same-ID 202, original local guard
  held by the orphan, confirmed worker exit before original-state restart,
  preserved uncertain partial, original claimed source/state/enrollment,
  producer-reused bytes and verified destination/manifest without job 2.
- Both fresh mandatory SLES/glibc 2.22 gates; exact current/live/fresh Rust input
  and forty artifact comparisons; independent raw proof audit, rejected proof
  mutations, exact acquisition/verifier snapshots and clean owned resources.

Native capability must pass before service injection on its layout. Unsupported
capability remains failed/unavailable; never replace it with unrelated controls.
Read [the step-by-step lab](NFS-BUFFERED-COMMIT-LAB.md) for infrastructure,
commands, proof boundaries and cleanup. Add SC-112 for this distinct situation
and feed DOC-01–05; keep DOC-06 deferred and all release gates open.

The fixture uses one controlled server and a modern shared kernel with pinned
SLES userspace. It does not qualify physical power durability, independent NAS
failure domains, original SLES kernel behavior, all synchronization boundaries,
or UNSTABLE WRITE reply-loss recovery.

## Live results

Run `mount-profile-20261019T173217Z-194661a2` **passes** all six native controls,
eight service cases and 43 inventory/model controls, with cleanup_errors=[].
The [raw evidence](RUST-NFS-BUFFERED-COMMIT-EVIDENCE.json) retains all 25 exact
acquisition/helper sources, wire records, native traces, clocks, pending-worker
proc records, server objects, guard probes and recovery snapshots. The
[input evidence](RUST-NFS-BUFFERED-COMMIT-INPUT-EVIDENCE.json) retains the final
independent audit, its exact source, native binary/auditor and fresh Rust archives.

On each layout, native discovery observes COMMIT inside successful target fchmod.
Both release/drop controls hold matching successful COMMIT replies while the
native process is D-state in syscall 91 on that FD, mode 0400. Server-local
inode/size/hash equals the expected 2 MiB+17-byte payload, NFSD threads=2. Release
completes normally. Drop plus explicit connection interruption produces decoded
`cached_exact_replay` on a new connection, followed by successful fchmod/fsync;
the server object remains unchanged. No COMMIT semantic-resend fallback was needed.

All eight service cases independently reach the actual same pending target
fchmod condition. Each capture contains successful UNSTABLE writes at offsets
0/1048576/2097152, counts 1048576/1048576/17, with expected range hashes and the
same verifier on the held COMMIT's filehandle. Capture both active relays: all
actual selected COMMIT traffic uses the source relay, including separate shares.
A destination mount address did not identify the actual transport.

| Layout | Profile | Live-release | Coordinator death / worker kill / drop |
| --- | --- | --- | --- |
| Same share | Debug | Committed, attempt 1 | Committed, attempt 2; first partial retained |
| Same share | Release | Committed, attempt 1 | Committed, attempt 2; first partial retained |
| Separate shares | Debug | Committed, attempt 1 | Committed, attempt 2; first partial retained |
| Separate shares | Release | Committed, attempt 1 | Committed, attempt 2; first partial retained |

While success remains withheld, health stays responsive, the local file receipt
remains Intent, one assigned worker remains, and same-ID replay still returns
202 for already-confirmed custody. The recorder's newer producer-path bytes are
preserved. In each death case, the helper kills/reaps the coordinator first,
then an independent local flock probe returns 73 while the actual orphan is
still D-state. It records the same guard inode, terminates that worker, drops
its reply/connection, and confirms actual exit before restart. Recovery uses the
same configuration/database/enrollment, preserves the original uncertain partial
inode/size/hash and chooses attempt 2; it does not reuse or delete that partial.

Every final recording validates its manifest and destination hash. The original
claimed source inode/hash, database inode/enrollment, newer producer bytes and
job ID 1 remain intact; job 2 is absent and source cleanup stays disabled. All
services stop normally after recovery. There are no Rust, dependency, API,
retry/review, assignment or shutdown-policy changes. The existing I/O/sync
verifiers accept the expanded 25-driver capture while retaining exact byte checks.

## Interpretation and remaining limits

This qualifies the finite controlled payload-fchmod COMMIT boundary above. A
live delayed reply is released; reply loss is combined with coordinator/worker
death. It does **not** qualify live COMMIT loss without that death, UNSTABLE WRITE
reply loss, all COMMIT ranges/phases or pending source synchronization. Native
controls and service pending `/proc` observations are distinct: only native
discovery uses ptrace here; service faults use actual pending syscall/FD/state
and server-local object snapshots. Matching protocol handles/ranges/verifiers,
local FD inode and controlled server objects are fixture correlations, not
unique kernel causality or authenticated global NAS identity.

Pinned SLES 12 SP5 glibc 2.22 userspace runs on
`6.18.33.2-microsoft-standard-WSL2`. Both logical exports share one controlled
server/kernel and volatile tmpfs; neither cached COMMIT success nor final hashes
prove physical persistence through power loss. Original SLES kernel/maintenance
packages, independent NAS failures, NetApp/Isilon behavior, larger workloads,
endurance, export changes and general delayed-effect settlement remain open.
Local worker exit/guard availability cannot establish remote settlement.
Keep all eight first-release gates open and production NFS/source deletion off.

## Compatibility, independent audit and cleanup

Both fresh mandatory gates **pass**:

| Build | Run | Debug/release tests |
| --- | --- | --- |
| Production | `20261019T173137Z-19b04219` | 211 / 211 |
| NFS qualification | `20261019T173137Z-494536dd-nfs-qualification` | 212 / 212 |

Each uses cargo-zigbuild GNU/glibc 2.22 and pinned SLES execution, runtime
relocations, six negative ELF controls and the unchanged 42-dependency graph.
The live artifacts came from passing source-identical increment-77 gates;
the final independent verifier compares all 62 current/live/fresh Rust archive
entries and all forty fresh/live artifact bytes. Native C fixture ELF is retained
separately: GNU loader, libc.so.6 only, maximum imported GLIBC_2.2.5. It adds no
Rust target, shipping executable or production dependency.

`verify-nfs-buffered-commit.py` **passes** full raw payload SHA/decoding/bounds,
matched request/reply/XID and held-before-forwarding proof, actual FD inode versus
server inode, successful UNSTABLE range/hash/verifier relationships, native replay,
service recovery/guard/state/manifest checks and exact acquisition-source audit.
Seven rejected proof mutations include unarmed/forwarded/wrong-operation state,
corrupted payloads and rehashed but mismatched request/reply XIDs. Seven decoder
and eight I/O-analysis regressions pass and their output is retained in input
evidence. The exact independent verifier, native probe/auditor and fresh Rust
archives are retained alongside the compressed full live report.

Final inventory is captured only after both gates and the live runner exit.
Both Podman engines have zero containers; rootful has only its two original
cache volumes/default network. Rootless retains its original caches and eleven
unrelated September anonymous volumes, with creation metadata preserved.
Cleanup uncertainty is not waived. The native/service matrix and final audit
pass on their first acquisition; no failed fixture run is promoted or discarded.

The maintained catalog now has 112 stable SC IDs and six DOC IDs. SC-112 feeds
DOC-01–05 through the complete lab/results; DOC-06 remains deferred. Next prove
matched server-success UNSTABLE-WRITE reply withholding before selected service
loss/recovery; retain live COMMIT loss without death and other unobserved phases
as separate future obligations. No complete first-release gate closes here.
