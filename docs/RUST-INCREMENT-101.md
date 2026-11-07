# Rust increment 101: claimed replay and bounded admission during joint NFS outage

## Scope and changes

SC-135 retains --joint-outage with --mover --distinct-filesystems. Four native
retained-FD prerequisites precede four debug/release x source-space admission
off/on cases. Both source and destination use distinct retained NFS filesystems
on one controlled NFSD backend. SQLite/ownership stay local. No shipping Rust,
package, API/retry/review or shutdown deadline changes. Production NFS and
postcommit private-source cleanup remain disabled.

The fixture uses existing verify_read, confirms original 202 before producer reuse,
and sets max_retained_jobs=1. Enabled source-space admission uses minimum one byte,
one-second sample age and probe timeout; off cases preserve the default disabled
policy. These are qualification settings, not production capacity recommendations.
After stopping NFSD, release the existing pause into an actual destination-staging
read. Age source metadata for at least 65 seconds, then require actual blocked
source authority revalidation during same-ID replay. The delay alone proves no
particular cache behavior. No global cache drop or mount-profile change is used.

## Measured results

Run `joint-outage-20261022T055804Z-115f4bb2` passes four native prerequisites and all four mover cases,
with seventeen frozen acquisition files. Before outage, job 1 is Claimed/Copied,
private source and staging are complete with matching original hash, and original
202 permits the recorder's 'next recording' replacement. During outage the actual
delivery read is D-state on destination staging. The replay's assigned claim worker
blocks in openat (syscall 257) at /tmp/recovery-source in all four cases. This is
source-authority preflight at the mount root, not a reread of the producer replacement.
Resolve the pathname against its directory descriptor. Capture local proc arguments, command,
FD or bounded pathname memory and original worker security; workers run UID/GID
1000 without capabilities and with NoNewPrivs. The privileged fixture reader only
inspects owned-child local proc memory, never traverses NFS for that observation.

| Profile | Space admission | Retained workers | service_busy replies | Pairs across restore |
|---|---|---|---|---|
| debug | off | 2 | 5 | 0 |
| debug | on | 2 | 5 | 0 |
| release | off | 2 | 5 | 0 |
| release | on | 2 | 5 | 0 |

Measured outages last 111.144–115.918 seconds; local health takes 1.765–1.860
seconds including fixture transport overhead. All four worker snapshots contain
two blocked data/validation children. No live space probe remains in either
enabled-case snapshot; enabled new-ID refusal takes 2.828–3.094 seconds. Across
the four cases, retain 28 non-release responses: eight handoff_pending and twenty
service_busy. This does not measure a probe's entire lifetime or unrestricted load.

Each case retains the initial replay and a six-request burst alternating original
and new IDs: all seven responses are retryable 503 handoff_pending/service_busy,
with source_paths_released=false and at least one service_busy. The enabled cases
first refuse a new ID with source_space_unavailable. A probe need not stay alive
after cancellation. The two blocked data/validation workers remain identical. Each sample permits no
probe when disabled and at most one when enabled; a probe may already have exited.
Check any observed disappearing probe for actual exit. Local health/status remain
responsive, local guard stays held, retention reports one job, independent original source/staging custody stays
unchanged and no completion manifest exists while NFSD remains stopped.

This is a finite bounded-queue observation, not a memory/throughput/endurance
benchmark. The existing single-slot submission queue can retain a command after
its HTTP waiter times out. HTTP timeout does not cancel queued work. Already
acknowledged custody is preserved even when a later replay cannot currently return
202 because source authority cannot be revalidated. The recorder has no new
post-202 polling or delivery-monitoring duty; consumers wait for a valid manifest.

Restore the backend before draining users. The same coordinator completes original
attempt 1 with verified destination and valid manifest, original delivery and
validation workers exit, and newer producer bytes survive. The unchanged one-job
limit refuses the new ID with retention_capacity, job 2 is absent, and retained
job count stays one. Original config/DB inode checks, clean stop/restart and same-ID
202/replay succeed. Source-name removal during initial claiming remains separate
from disabled postcommit private-source cleanup.

Independently inspect/redecode 13040 bounded relay records, retaining 1688
unsupported compounds with exact hashes/XIDs. Count captured request/reply pairs
spanning restoration separately; zero pairs
are possible when the relay reconnects to the restored backend before observing
queued client records. Do not infer wire continuity from pending workers. Temporal
pairs do not alone identify a particular file/syscall;
actual local proc evidence establishes the two blocked worker roles and paths.
No reply is deliberately withheld in this matrix.

## Required compatibility and independent audit

Fresh production `20261022T052425Z-2201a405` passes 211 exact-target tests per profile; qualification
`20261022T052425Z-ee79348b-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22,
pinned SLES 12 SP5 userspace, 42 packages and six negative ELF controls each.
Audit forty Rust ELF artifacts and all 62 unchanged Rust inputs. The final live rerun
uses these fresh passing gate artifacts; independently compare complete source
archives and shipping binary hashes. Earlier failed attempts used prior passing
identical-source artifacts. Host-only cargo tests are not substituted.

The independent auditor rejects 83 corrupted mover/storage proofs, checks
raw HTTP/NFS records, custody, worker identities/counts/security/paths, queue
refusals and original-state recovery, runs seven decoder regressions and two CLI
refusal controls, and verifies retained backing/client separation plus native
recovery prerequisites. Earlier evidence remains in its existing retained packs.

The [initial fixture failure](RUST-NFS-JOINT-OUTAGE-INITIAL-EVIDENCE.json) passed
all native prerequisites but stopped in the first mover case: od compressed repeated
local proc-memory lines into an asterisk, which fromhex rejected. Preserve exact
failed report, seventeen sources and empty rootful container inventory. Add od -v
and reconstruct descriptor-relative path arguments from the original directory FD;
repeat the complete native/mover matrix. The auditor checks retained source hashes
and that only the fixture module changed. No Rust/retry/deadline change is made.

The [second retained attempt](RUST-NFS-JOINT-OUTAGE-SECOND-EVIDENCE.json) passed
all four native controls and the debug/off case. The enabled case correctly
returned source_space_unavailable and seven bounded non-release 503s, but the
fixture required a probe to remain alive even though it had already exited. Two
blocked data/validation workers stayed identical; cleanup returned both engines
to baseline. Preserve exact report/code/inventory, require the two data workers
to remain stable with at most one optional probe, verify observed disappearing
probes have actually exited, and repeat the entire native/mover matrix. No runtime
termination, retry or admission policy is changed to satisfy the test.

Final inventory at 2026-10-22T06:20:42.258136+00:00 confirms zero
containers on both engines and unchanged baseline full volume metadata/network
names. Normally unmount NFS after restoration/drain, remove owned users/backend,
verify/remove keeper last, then owned role/parent volumes and network. No forced/
lazy unmount, VM reset or global NAS/cgroup/host change is used.

Read [step-by-step infrastructure](NFS-JOINT-OUTAGE-LAB.md),
[raw acquisition](RUST-NFS-JOINT-OUTAGE-EVIDENCE.json),
[input/audit evidence](RUST-NFS-JOINT-OUTAGE-INPUT-EVIDENCE.json),
[production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) gates.

## Limits and next work

One controlled shared backend and modern shared WSL2 kernel with retained bounded
tmpfs do not qualify independent server outages, abrupt NAS/VM reboot, disk/power
loss, old SLES kernel/client or maintenance systemd, NetApp/Isilon, 100 GB transfers,
unrestricted request flooding, larger queues or endurance. This matrix does not
kill the coordinator, substitute source authority, test partial/unacknowledged
claims or prove physical reservation. Local worker exit is not global remote-
settlement proof. Further sync recovery needs positively observed actual service
RPCs. Qualify pre-202/partial-claim replay and independent-endpoint/longer outage,
source-change refusal and broader concurrent capacity behavior separately.

Maintain SC-135/DOC-01–05. All eight release gates remain open; production NFS and
postcommit private-source cleanup remain disabled. Registration/S3/offline repair/
DOC-06 remain deferred.
