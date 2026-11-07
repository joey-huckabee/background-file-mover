# Rust increment 84: buffered source-claim reply-loss recovery

## Finite acceptance

Run 24 actual-worker cases on NMP-41B buffered mounts: custody LINK and
producer-name REMOVE, same-share/separate-share layouts and debug/release.
On each layout repeat four successful-reply hold/release controls before four
live-coordinator reply drops and four coordinator-death reply drops. Keep all
case data until normal fixture teardown; use two 128 MiB volatile exports to
hold the finite matrix, preserving the existing mount/export policy.

Before every drop require the actual matched status-zero reply withheld, complete
raw compounds/hashes/XID, pending real-worker linkat/unlinkat/D state, descriptor
parent/mount identity, original server inode/size/hash and completed LINK/REMOVE
aliases. NFSD remains healthy. Require responsive health/status, initial and
same-ID retryable 503 with no source-path release and absent destination job 1.
The recorder leaves submitted paths alone until confirmed same-ID custody/202.

Live drops discard the saved success and reset its TCP connection. Require
successful replay of the same cachethis=true namespace session operation on a
new connection/receive ID; preserve all operation fields except the existing
highest-slot resource hint normalization. Retain complete raw replies and trace
matches. Keep the original coordinator alive through custody and delivery;
ordinary claim-worker retirement and delivery-worker assignment remain allowed.

For death, confirm coordinator exit, orphan D state, retained local guard, no
SQLite descriptor, bounded OwnerUnavailable status and a refused same-state
contender without epoch mutation. Request termination of the old worker, discard
the saved success/reset the connection, and confirm actual old-worker exit.
Require unchanged completed server aliases before restarting the original
configuration/database/enrollment. Keep distinct pre/post restart wire windows.
This is original-state reconciliation, not automatically native session replay
or proof that a local free lock establishes remote settlement.

After release/recovery, require same-ID job 1/202 before producer-path reuse,
attempt-1 verified commitment, original private source inode/hash, database inode,
enrollment/root authority and newer producer bytes, retained source, no job 2
and clean bounded stop. Keep production NFS/source deletion disabled; no Rust,
dependency, retry/review, assignment or shutdown-policy changes are planned.

Freeze all 30 acquisition/helper/test snapshots before live execution. Run both
mandatory cargo-zigbuild GNU/glibc-2.22 SLES gates and independent raw-proof,
negative-control, source/forty-artifact and final two-engine inventory audits.
Maintain SC-118 and DOC-01–05; defer DOC-06. Preserve any failed acquisitions
and their exact sources before correction. Shared modern WSL2 kernel, one NFSD
server and volatile exports do not qualify physical NAS/power behavior, original
SLES kernel/maintenance packages, server reboot, delayed remote settlement or
other workloads/cache/load/outage durations. Record actual results after exit.

## Actual result

The complete matrix passed without a failed acquisition:
`mount-profile-20261020T042611Z-6249dd19`, 61,395,141 exact raw report bytes,
thirty frozen source snapshots, 43 mount inventory/model controls and
`cleanup_errors=[]`. All 24 actual-worker cases passed: eight repeated release
controls, eight live drops and eight coordinator-death drops. The runner exited
0 after normal owned-fixture teardown. No Rust, crate, API, pause or runtime
retry/review/assignment/stop-policy change was needed.

| Layout | Profile | Claim | Release control | Live loss | Death/restart loss |
|---|---|---|---|---|---|
| same-share | debug | LINK | PASS | PASS | PASS |
| same-share | debug | REMOVE | PASS | PASS | PASS |
| same-share | release | LINK | PASS | PASS | PASS |
| same-share | release | REMOVE | PASS | PASS | PASS |
| separate-shares | debug | LINK | PASS | PASS | PASS |
| separate-shares | debug | REMOVE | PASS | PASS | PASS |
| separate-shares | release | LINK | PASS | PASS | PASS |
| separate-shares | release | REMOVE | PASS | PASS | PASS |

Before each drop, independent server aliases/inode/size/hash and matched raw
status-zero replies proved the selected effect completed with its acknowledgement
withheld. Actual workers waited in D at linkat/unlinkat, with matching parent
paths/mount IDs/server inodes. NFSD remained at two threads. Initial submissions
and same-ID retries returned retryable 503 without source-path release; health/
status stayed responsive and destination job directories remained absent.

All original LINK compounds were `[53,22,32,22,11,31,9]`; REMOVE compounds
were `[53,22,28]`. The observed carrier was the source relay in every case,
including separate shares; both active transport windows are retained.

Every live case proved cachethis=true successful namespace session replay on a
new connection and receive ID. Full raw request bytes, including metadata omitted
by the summary decoder, match after normalizing only the RPC transaction ID and
highest-slot hint; transaction IDs still match their own replies. The original
coordinator remained alive. Normal claim-worker retirement and delivery-worker
assignment are distinct from forced replacement or coordinator restart.
Successful SEQUENCE replies also echoed their own request's session, sequence
and slot identity in the raw reply prefix, following
[RFC 8881](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.46).

Every death case proved coordinator exit, a surviving D worker, unchanged local
lock identity/contention 73, inherited lock with no SQLite descriptor, bounded
OwnerUnavailable status, and a refused contender without worker-epoch mutation.
After KILL/drop/reset the original worker exited before restart. Server aliases
and original custody identity/hash remained unchanged before the original
configuration/database/enrollment restarted. Distinct pre/post restart wire
windows distinguish old kernel replay from original-state reconciliation; restart
is not automatically native namespace replay or general remote-settlement proof.
All eight orphan workers were observed exited as Z before restart: their file
descriptors were closed, but the minimal container PID 1 had not reaped them.

All cases confirmed same-ID job 1/202 before producer-path reuse, committed
payload attempt 1 with verified manifest/hashes, retained original one-link private
source, database/enrollment/root identity and newer producer bytes, refused job 2
and stopped normally. This supplies selected FR-03/05 evidence; all eight release
gates and production NFS/source deletion remain unchanged.

## Compatibility and retained audit

Fresh production `20261020T042206Z-929446e1` and qualification
`20261020T042206Z-19f43768-nfs-qualification` gates both exited 0, with 211 and 212
exact target tests per profile respectively. Each audited ten ELFs per profile;
all forty fresh artifact bytes match the source-identical passing gates used
live. All 62 Rust entries, the 42-package locked graph and six ELF negative
controls per gate match; all ELF reports were independently re-audited.

The independent audit passed all raw-proof/replay/death and custody/source/state/
manifest invariants, 43 actual-proof corruption controls,
seven RPC decoder tests, three claim-proof tests and two replay-proof tests.
It also checked missing-gate refusal, all thirty acquisition snapshots, exact
verifier/wire/gate helpers, full live/fresh Rust archives and final inventories.
Both engines have zero containers. Rootful retains only its original two cache
volumes/default network; unrelated default-engine volume identities and creation
metadata are preserved. No forced/lazy unmount, cleanup exception, NAS/host-policy
or VM-boot change was needed.

Retain the lossless raw report/SHA in
[RUST-NFS-CLAIM-LOSS-EVIDENCE.json](RUST-NFS-CLAIM-LOSS-EVIDENCE.json) and exact
build/source/audit/inventory proof in
[RUST-NFS-CLAIM-LOSS-INPUT-EVIDENCE.json](RUST-NFS-CLAIM-LOSS-INPUT-EVIDENCE.json).
The [step-by-step lab](NFS-CLAIM-LOSS-LAB.md) explains infrastructure, controls,
injections, replay versus reconciliation, cleanup and limits. Maintain SC-118 and
DOC-01–05; defer DOC-06. Shared WSL2 kernel 6.18.33.2-microsoft-standard-WSL2 and volatile exports
cannot qualify original SLES kernel/maintenance RPMs, physical NAS/power behavior,
server restart/verifier changes, delayed effects, pending source synchronization,
other sizes/file counts/cache/load/endurance or every network-failure pattern.
Discrete API samples include fixture command overhead and are not an SLA.
