# Rust increment 77: attribute buffered NFS I/O observations

## Scope and acceptance

Observe eight healthy NMP-41B qualification workers: claim/delivery, debug/release,
same/separate shares. Preserve all source/state/202/manifest invariants from
[increment 76](RUST-INCREMENT-76.md). Keep production NFS, source deletion,
Rust behavior, retry/review policy and shutdown/assignment deadlines unchanged.

Retain `--buffered-io` separately from `--buffered-sync`. The new networkless
external observer records open/read/write/close, descriptor metadata and sync
entry/exit, flags, offsets, mount IDs and inode identity. It reads only local
proc records and bounded worker memory, never stats/reads the NFS target to
observe it. Capture at most 8192 selected events and 8 MiB of NFS write payloads,
with at most 1 MiB per write. Truncation/overflow must fail, not prove absence.

Capture both active relays and actual client/observer/relay clock identity.
Preserve raw payloads and undecoded compounds. Decode optional GETATTR fsid/fileid
prefixes using [RFC 8881](https://www.rfc-editor.org/rfc/rfc8881.html#section-5.8),
without changing default decoder output. Correlate filehandle identity with
descriptor-relative stat pairs or WRITE range/bytes/inode/time. Distinguish those
proofs from plain interval overlap, unmatched traffic and unique causal claims.
No native withholding controls or service fault injection are added here.

Require eight complete tuples, successful syncs and unchanged attempt-1
delivery/validated manifest, source inode, database/enrollment and producer-reused
bytes after confirmed 202. Repeat model/inventory controls, meaningful decoder/
attribution counterexamples, both fresh SLES gates and independent exact-source/
artifact/evidence audit. Update SC-111 and DOC-01–05; no new user behavior requires
a new scenario ID. Use actual results to select the next finite service fault
matrix, leaving unsupported or unmatched cases explicit.

## Initial fixture failure

Run `mount-profile-20261019T170008Z-7f3ebe92` fails during first-claim trace analysis
with `conflicting filehandle identity`, cleanup_errors=[]. It preserves the
actual worker trace and all 24 exact driver snapshots in
[initial evidence](RUST-NFS-BUFFERED-IO-INITIAL-EVIDENCE.json); it is not passing
eight-case qualification. The analysis omitted current/saved handle transitions
for SAVEFH (32) and RESTOREFH (31), so GETATTR following a restored handle was
incorrectly associated with the latest PUTFH. The conflict guard correctly
refused to publish that identity map.

Implement those transitions, invalidate untracked LOOKUP/LOOKUPP/root handles,
and add a regression proving restored attributes cannot identify the other
handle. Also require successful descriptor-stat/open results before metadata
matching; retain a failed-call counterexample. The eight-case rerun must use new
exact source snapshots. No Rust, storage recovery or deadline change is needed.

## Results

Corrected run `mount-profile-20261019T170553Z-a1550460` **passes** all eight worker traces,
43 model/inventory controls, seven existing decoder tests and eight I/O-analysis
regressions, cleanup_errors=[]. The [raw evidence](RUST-NFS-BUFFERED-IO-EVIDENCE.json)
retains all 24 exact acquisition/helper/decoder/test sources, real clocks/security,
mounts, descriptors/arguments/results, compressed write buffers, raw RPCs and
handoff/commit/source-state acceptance. The client reports `glibc 2.22` on
shared modern kernel `6.18.33.2-microsoft-standard-WSL2`.

| Layout | Profile | Worker | I/O events | NFS syncs | Attributed WRITE / COMMIT |
|---|---|---|---:|---:|---:|
| same-share | debug | Claim | 723 | 8 | 0 / 0 |
| same-share | debug | Delivery | 6614 | 20 | 4 / 1 |
| same-share | release | Claim | 667 | 8 | 0 / 0 |
| same-share | release | Delivery | 5506 | 20 | 4 / 1 |
| separate-shares | debug | Claim | 948 | 8 | 0 / 0 |
| separate-shares | debug | Delivery | 6847 | 20 | 4 / 1 |
| separate-shares | release | Claim | 896 | 8 | 0 / 0 |
| separate-shares | release | Delivery | 5774 | 20 | 4 / 1 |

The key finding is **payload and manifest data flush during `fchmod`, before
subsequent fsync** in all four delivery traces. Actual x86_64 syscall 91 changes
the staging file to mode 0400; captured descriptor flags/position/inode and
GETATTR fsid/fileid connect its handle to three payload WRITEs and one COMMIT.
Payload requests cover offsets 0/1048576/2097152 with counts 1048576/1048576/17,
`stable=0` (UNSTABLE), and successful replies with `committed=0`. COMMIT uses
offset 0/count 0 and succeeds. A further manifest WRITE uses `stable=2`
(FILE_SYNC), succeeds with `committed=2`, and is associated with the manifest's
read-only permission change. All **20** delivery requests have matching
successful reply records. This describes the observed fixture behavior; it does
not replace application sync calls or qualify arbitrary kernels/NAS behavior.

All **112** NFS sync calls still return zero, with zero captured outgoing calls,
incoming replies or captured request/reply pairs spanning entry in their
intervals. Broader capture contains **6795** requests, **313** undecoded compounds,
32 decoded WRITE and eight COMMIT requests. Four claim windows contain the same
kinds of broader traffic but none is attributed to the selected claim worker;
other worker/background activity remains distinct. Do not conclude the claim
worker produced those requests or that pending source synchronization is qualified.

The [independent audit](RUST-NFS-BUFFERED-IO-INPUT-EVIDENCE.json) verifies 27,975
selected events, maximum 6847 per trace (limit 8192), and 4,195,726 captured NFS
write-buffer bytes overall. Each trace remains under 8 MiB and each write under
1 MiB. It preserves 2012 successful metadata matches; no WRITE request is inside
a matching write syscall interval. Instead, independently witnessed mount fsid
plus descriptor inode/filehandle identity and byte-range hashes connect **12**
network WRITE requests to earlier completed worker writes. The first 1 MiB was
written before `copy_chunk` attachment and has no captured buffer; it is not
invented as an observed write. Timing/identity evidence and buffer proof remain
separate, and unknown traffic stays explicit.

Both independent attribution methods identify the same 20 delivery operations
inside fchmod. Same-share mount witnesses identify fsid [68,0]; separate-share
witnesses distinguish source [68,0] and destination [69,0]. Ten independent audit
rejection controls cover wrong fsid/inode, missing mount witness/overlap/handle,
conflicting mount witnesses, and buffer byte/range/failure/order mistakes. The
original eight analysis tests include SAVEFH/RESTOREFH and failed metadata-call
regressions. This is fixture-local evidence, not authenticated filesystem identity
or universal unique kernel causality.

Every job commits on attempt 1 with validated payload manifest, unchanged original
private source inode/content, database inode/enrollment and preserved newer
producer bytes. Four claim cases initially return retryable 503 with paths
unreleased; four delivery cases initially return 202. All confirm identical-ID
job 1/202 before producer reuse, create no job 2, and stop cleanly. Delivery
retirement requires its already-Committed attempt-1 receipt; claim workers exit
zero. Retry/review, assignment and shutdown deadlines are unchanged. No native
withholding controls, service failure or coordinator death is injected.

Both fresh mandatory SLES gates pass without cleanup errors:

| Configuration | Run ID | Debug / release tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261019T165455Z-174a25c2` | 211 / 211 | 20 |
| Qualification | `20261019T165453Z-40a41e13-nfs-qualification` | 212 / 212 | 20 |

[Production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) retain locked cargo-zigbuild
GNU/glibc 2.22, exact target tests in pinned SLES userspace, loader/library/symbol
audits, six negative controls per configuration, formatting/Clippy and 42 locked
dependencies. One shipping executable remains; forty artifacts include tests
and both profiles. No Rust/Cargo.lock/schema or shipping dependency changes occur.

Live inputs are source-identical passing increment-76 gates
`20261019T145853Z-d68cd378` and
`20261019T145854Z-ed6461b6-nfs-qualification` while fresh gates run. Independent
verification checks all 62 current Rust entries in live/fresh archives and hashes
all forty fresh artifacts, requiring byte equality to live inputs. It retains
fresh archives, exact verifier source (including independent postprocessing and
rejection controls), raw-payload SHA/decoding/correlation, exact driver matching,
initial failed provenance and final inventory. Gzip metadata may differ; Rust
entries and executable/test bytes must match. Historical evidence remains intact.
The earlier sync mode stays available, its default decoder output unchanged;
its verifier accepts historical 21-source or expanded 24-source inventories.

Both Podman engines have no containers. Owned NFS export volumes/networks are
removed with normal unmount/unexport. Rootful retains only the two original
`file-mover-rustup-1-99`/`file-mover-cargo-registry` cache volumes and default
`podman` network. Default engine's eleven September anonymous volumes and caches
are retained; creation metadata confirms they predate this work. Cached images
remain available. No forced/lazy unmount or host/NAS configuration change occurs.

## Reproduction, limitations and next increment

Follow the [step-by-step lab](NFS-BUFFERED-IO-LAB.md), including raw evidence
compression, actual clock identity/privileges, current/saved handle semantics,
all-relay capture, bounds, inventories and independent audit. SC-111 and DOC-01–05
are updated without creating a duplicate user situation: 111 SC and six DOC IDs;
DOC-06 remains deferred. The roadmap retains future work only.

Ptrace changes timing; the observer is a modern-kernel fixture, not a SLES-host
installation component. Trace starts at the existing claim/copy checkpoint and
cannot establish earlier writes. Fixture prehash/stat preparation may settle
producer data before handoff; unobserved pending claim sync remains unqualified.
This one client/server, two logical exports and volatile tmpfs on modern WSL2
kernel does not qualify independent NAS/failover/cache, old SLES kernel,
physical-media/power durability or arbitrary sizes/load. Packet identity/timing
is evidence for these finite cases, not permission to delete/rebind/redispatch
uncertain data. All eight release gates remain open; production NFS and source
deletion stay disabled.

Next prove matched server-success reply withholding at the observed **payload
fchmod COMMIT boundary**, then select its finite service loss/death/recovery
cases. Native 4 KiB FILE_SYNC WRITE controls do not establish this UNSTABLE-WRITE/
COMMIT path. Keep remaining source-claim, manifest and other unobserved or untested
boundaries open; do not assume COMMIT must occur inside fsync.
