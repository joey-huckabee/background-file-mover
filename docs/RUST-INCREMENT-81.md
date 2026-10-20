# Rust increment 81: manifest-side reply-withholding capability

## Finite acceptance

Keep production NFS/source deletion disabled and preserve Rust behavior,
dependencies, retry/review and all assignment/shutdown deadlines. Use the existing
publish qualification checkpoint after payload verification to isolate later
manifest creation without a new Rust pause or executable.

Run exactly eight actual-worker cases: healthy discovery and successful-reply
hold/release, each on buffered NMP-41B same-share/separate-share layouts and
debug/release profiles. Healthy traces must precede hold controls on their layout.
Attribute the exact manifest WRITE using successful metadata/fsid/fileid and
local descriptor identity, application buffer bytes, raw request/reply and actual
syscall intervals. Record requested/returned stability and actual same-handle
COMMIT presence; do not substitute payload behavior or unknown traffic.

For controls, hold matching successful WRITE replies before forwarding. Prove
actual blocked syscall/FD/D state, server-local complete manifest bytes/inode,
full returned count, live NFSD and agreement with healthy discovery. The public
manifest must remain absent and coordinator status uncommitted while local health
and same-ID 202 replay work. Release replies and require attempt-1 commitment,
original source/database/enrollment, producer-path reuse, original manifest inode
and exact bytes, validated final payload/manifest and no job 2. Stop normally.
No reply loss, coordinator death, worker replacement or outage matrix is added.

Require 28 exact driver/helper/test snapshots, raw-proof rejection controls,
fresh production and qualification SLES/glibc 2.22 gates with forty-artifact and
62-entry source comparison, independent audit and final clean inventories.
Maintain SC-115/DOC-01–05; DOC-06 stays deferred. Container-only userspace tests
share a modern kernel; neither FILE_SYNC nor tmpfs demonstrates power durability,
original SLES kernel/maintenance packages, physical NAS interoperability or all
sizes/cache/load/phases. The results below record actual qualification.

## Actual results

The finite eight-case matrix **passes** with cleanup_errors=[]:
`mount-profile-20261020T003252Z-2b24f98a`. Four healthy actual workers establish
manifest-specific attribution before four positive successful-reply hold/release
controls. No native probe or new Rust checkpoint is used. All 43 inventory/model
controls pass; all 28 acquisition/helper/test sources match the final checkout.
The exact raw report is 68,913,130 bytes, retained losslessly with its SHA-256.

| Layout | Profile | Action | Actual relay | Manifest bytes | Requested/returned stability | Actual syscall | Decoded manifest COMMIT requests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same-share | debug | discovery | source | 348 | 2/2 | 91 | 0 |
| same-share | release | discovery | source | 350 | 2/2 | 91 | 0 |
| same-share | debug | hold-release | source | 351 | 2/2 | 91 | not inferred |
| same-share | release | hold-release | source | 353 | 2/2 | 91 | not inferred |
| separate-shares | debug | discovery | source | 353 | 2/2 | 91 | 0 |
| separate-shares | release | discovery | source | 355 | 2/2 | 91 | 0 |
| separate-shares | debug | hold-release | source | 356 | 2/2 | 91 | not inferred |
| separate-shares | release | hold-release | source | 358 | 2/2 | 91 | not inferred |

The operation/result values are observations. RFC 8881 section 18.32 defines
stable/committed=2 as FILE_SYNC; its server-side promise does not convert volatile
tmpfs into evidence of power durability. See
[RFC 8881 WRITE](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.32).
The COMMIT count covers decoded requests on the attributed manifest handle in
the captured window. Unknown/unmatched raw traffic remains explicit; zero does
not prove absence of every possible RPC, every sync or every server/kernel.
Healthy attribution requires successful metadata-derived
fsid/fileid and local descriptor identity, matching application-buffer and exact
server-final bytes, a full-range WRITE and paired successful raw RPC within the
actual descriptor-operation interval. The independent audit additionally binds
buffer inode/mount/position to those same witnesses and rejects malformed proof.

While successes are held before forwarding, every control proves actual target
FD/D state and pending syscall, full server-local manifest bytes/hash/size/inode,
live NFSD, responsive health and same-ID job 1/202. The payload is Published but
the job is uncommitted and public COMMITTED.json is absent. Releasing the saved
reply completes attempt 1 with the same manifest inode and exact bytes, validated
payload/manifest, original private source inode/hash, database inode/enrollment,
newer producer bytes, retained source and no job 2. No coordinator restart,
manual state edit, audited resume, deadline reset or reply-loss test is used.
Normal supervised worker retirement and bounded stop follow actual commitment.
The manifest body is 348–358 bytes for one 2 MiB+17 payload file. Healthy captures
retain 55/51 undecoded calls on same-share debug/release and 63/61 on separate-
share debug/release. They remain raw observations and cannot supply positive
identity or absence proof. The measured controls block in fchmod(0400), syscall
91, with manifest_phase=1; every selected request/reply uses stable=2/committed=2
and the source relay, including destination operations on separate logical shares.
This is not a many-file/large-manifest or 100 GB workload/performance qualification.

## Compatibility and independent evidence

Fresh mandatory production `20261020T002842Z-6d4269f8` and qualification
`20261020T002853Z-f8c942db-nfs-qualification` gates both pass. Locked
cargo-zigbuild GNU/glibc 2.22, debug/release exact target tests in pinned SLES 12
SP5 userspace, ELF/relocation and six audit-negative checks remain required.
Production passes 211 tests per profile; qualification passes 212. All 62 Rust
entries and forty ELF artifact bytes match current/live/fresh archives, including
the earlier source-identical gates supplying live binaries. All 42 locked
packages/features and the single shipping executable stay unchanged.

The independent audit passes raw RPC SHA/decoding/bounds, syscall/payload/
identity attribution, actual held-before-forwarding success, release, source/
state/202/manifest invariants, exact source snapshots and fresh artifact provenance.
It retains twelve additional held-byte/scoped-buffer rejection controls, one
invalid-selector refusal before fixture creation, seven decoder, eight I/O-analysis
and four manifest regression methods. The latter include 23 invalid variants
covering identity, bytes, interval, status, count, stability, XID and contract.
Exact verifier/shared wire-auditor bytes, fresh Rust archives, actual analysis,
regression output and final inventories accompany losslessly compressed exact
raw-report bytes and SHA-256:

- [Raw report](RUST-NFS-MANIFEST-CAPABILITY-EVIDENCE.json).
- [Inputs and independent audit](RUST-NFS-MANIFEST-CAPABILITY-INPUT-EVIDENCE.json).

Read [the step-by-step procedure](NFS-MANIFEST-CAPABILITY-LAB.md) for all setup,
commands, privileges, capability acceptance, evidence retention and normal cleanup.
Both engines are empty after both gates and the runner exit. Rootful retains only
two original cache volumes/default network; rootless retains original caches and
eleven unrelated September anonymous volumes with creation metadata. No uncertain
cleanup, forced/lazy unmount or unrelated-resource deletion is waived.

## Boundaries and next work

Maintain SC-115 and DOC-01–05, with 115 stable SC identifiers and six DOC IDs.
The recorder has no new post-202 monitoring duty; consumers still require the
validated public manifest. DOC-06 and other deferred work remain deferred.
All eight first-release gates stay open, with production NFS/deletion off.

This establishes manifest successful-reply holding/release, not manifest reply-loss,
uncached replay, coordinator-death, original-state restart or longer-outage safety.
Do not infer a pending manifest COMMIT from payload COMMIT evidence. Define and
qualify the next finite manifest loss/recovery matrix using the actual proven
WRITE/stability/descriptor boundary and unchanged policy/deadlines.

Pinned SLES/glibc 2.22 userspace shares modern WSL2 kernel 6.18.33.2. One server
with volatile tmpfs and two logical exports does not qualify physical media/power
loss, independent NAS failure domains, NetApp/Isilon interoperability or original
SLES kernel/maintenance packages. Ptrace changes scheduling; healthy intervals
and held-state API checks are finite observations, not continuous availability.
Earlier source sync/pre-checkpoint I/O, other sizes/cache/load/phases, authenticated
NAS identity and delayed-effect settlement stay open. Local worker exit or a free
local guard is not remote settlement.
