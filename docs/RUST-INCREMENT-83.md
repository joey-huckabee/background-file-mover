# Rust increment 83: buffered source-claim reply-withholding capability

## Finite acceptance

Run eight actual-worker hold/release controls: custody LINK and producer-name
REMOVE, buffered NMP-41B same-share/separate-share layouts, debug/release.
Use existing claim_link_rpc and claim_unlink_rpc pauses. Capture the pending
linkat/unlinkat syscall and directory descriptors, complete raw request/reply
compounds and independent server alias/inode/size/hash observations. Require
matched successful replies withheld while NFSD remains running and the worker
waits in D state. Observe both transport relays on separate shares; do not assume
that a logical source or destination determines which connection carries RPCs.

This is eight capability/release controls, with actual-worker syscall sampling
and relay traces in every case. It is not an additional healthy ptrace discovery
matrix, reply-discard test or coordinator-death/recovery test. Require responsive
health/status, Accepted/unreleased status, retryable initial and same-ID 503,
and no destination job directory until the withheld reply is released. The
recorder leaves its paths alone until confirmed custody returns 202. Then reuse
the producer path, complete attempt-1 delivery and verify private source and
destination hashes/manifests without changing database identity or enrollment.

Keep production NFS/source deletion disabled, Rust code/dependencies unchanged,
and preserve retry/review/assignment/stop behavior. Run both mandatory zigbuild
GNU/glibc 2.22 SLES gates; independently audit raw proof, exact driver snapshots,
62 Rust inputs, forty artifacts, rejection controls and final owned-fixture
cleanup/inventories. Maintain SC-117 and DOC-01–05; defer DOC-06. Successful
namespace operations in volatile fixture exports do not prove power survival,
physical NAS/old SLES kernel compatibility, delayed settlement or untested
workloads. Record results after actual process completion.

## Actual result

The complete matrix passed without a failed acquisition:
`mount-profile-20261020T031958Z-ba7907a6`, 22,153,203 exact raw report bytes,
28 source snapshots, 43 inventory/model controls, eight actual-worker successful
reply hold/release controls and `cleanup_errors=[]`. The runner exited 0 after
normal owned-fixture teardown. No reply was discarded and no coordinator death
was injected. No Rust source, crate, API, pause or runtime policy changed.

| Layout | Profile | Claim operation | Observed carrier | Result |
|---|---|---|---|---|
| same-share | debug | LINK | source | PASS |
| same-share | debug | REMOVE | source | PASS |
| same-share | release | LINK | source | PASS |
| same-share | release | REMOVE | source | PASS |
| separate-shares | debug | LINK | source | PASS |
| separate-shares | debug | REMOVE | source | PASS |
| separate-shares | release | LINK | source | PASS |
| separate-shares | release | REMOVE | source | PASS |

All LINK compounds were `[53,22,32,22,11,31,9]`; all REMOVE compounds were
`[53,22,28]`. Full raw request/reply bytes and successful results are retained,
including LINK's saved/current filehandle setup and trailing metadata operations.
Every worker waited in D at actual linkat/unlinkat with the expected directory
descriptors, matching mount and independent server-parent inode. While the
success was withheld, server-local LINK aliases had two links to the original
inode; REMOVE left only the one-link private original. NFSD stayed at two threads.

Initial submissions and same-ID retries returned retryable 503 without path
release, health/status stayed within the fixture bounds, and the destination
job directory remained absent. Confirmed same-ID job 1/202 followed reply release;
only then did the producer reuse its path. Every case committed payload attempt 1,
verified its manifest and source/destination hashes, preserved original private
source identity, root authority, database inode and enrollment, retained newer
producer bytes, refused a duplicate job 2 and stopped normally. This is selected
capability/release evidence for FR-03/05; all eight release gates remain open.

Retain the complete report in
[RUST-NFS-CLAIM-CAPABILITY-EVIDENCE.json](RUST-NFS-CLAIM-CAPABILITY-EVIDENCE.json)
and exact build/source/audit/inventory proof in
[RUST-NFS-CLAIM-CAPABILITY-INPUT-EVIDENCE.json](RUST-NFS-CLAIM-CAPABILITY-INPUT-EVIDENCE.json).
The [step-by-step procedure](NFS-CLAIM-CAPABILITY-LAB.md) explains acquisition,
server proof, recorder rules, audit, cleanup and limits. SC-117 and DOC-01–05
capture the user situation; DOC-06 stays deferred. Next select finite buffered
claim reply-discard/replay/death cases using these proven controls. Pending source
synchronization, remote settlement, server recovery, other workload/cache/load
and NAS/kernel/power/deployment qualification remain separate future obligations.

## Compatibility and independent audit

Both fresh mandatory gates exited 0: production
`20261020T031717Z-75c40674` (211 target tests/profile) and qualification
`20261020T031729Z-99b34e7c-nfs-qualification` (212 target tests/profile).
Each audited ten ELFs per debug/release profile; all forty fresh artifacts were
compared byte-for-byte with the source-identical passing gates used live, and
all ELF reports were re-audited. The 42-package locked graph, six ELF negative
controls per gate and all 62 exact current/live/fresh Rust inputs match.
No symbol/interpreter/library requirement beyond the glibc-2.22 gate was added.

The independent audit passed all eight retained actual-worker proofs, complete
raw wire hashes/decodes/bounds, alias/descriptor/mount identity and API/source/
state/manifest invariants. Twenty actual-proof corruption controls were rejected,
including rehashed wrong names/XIDs. Seven RPC decoder and three claim-proof
Python tests passed; missing-gate selection was rejected before fixture creation.
All 28 acquisition snapshots match current sources; exact audit/gate helpers,
fresh source archives and inventories are retained in the input evidence.

After every test process exited, both engines had zero containers. Rootful
retained only its two original cache volumes and default network; all eleven
unrelated September anonymous volumes and both default-engine caches, including
creation metadata, matched the prior clean inventory. No forced/lazy unmount,
NAS/host policy change or cleanup exception was needed. The qualification uses
shared WSL2 kernel 6.18.33.2 with pinned SLES/glibc 2.22 userspace, not the original
SLES kernel or a physical NAS. Timing samples include fixture transport overhead;
they are not service latency or continuous-availability guarantees.
