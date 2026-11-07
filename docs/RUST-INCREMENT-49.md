# Rust increment 49: enrolled and populated bootstrap coordinator death

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Add `--coordinator-death --death-scope bootstrap-existing-state` to the retained
fixture. Eight cases: enrolled-empty/populated × debug/release × blocked/following
local stop. Use an NFS source and local destination to isolate source bootstrap;
six normal baselines additionally cover destination-only and both-NFS layouts.
Keep production NFS/deletion off and preserve all runtime policies/dependencies.

Enrolled-empty starts with an active original source/database pair and no jobs.
Populated starts with a durable 202/Claimed job, a producer-reused path and a
1 MiB attempt-1 partial. Kill its seed coordinator first, then its paused copy
worker on healthy NFS, confirming both exit before the actual bootstrap test.
Require exactly the intended staging entry (1.part), no second allocation, and a
nonempty retained WAL; preserve database and all present/absent recovery sidecars.
This is explicit fixture preparation, not an operator recovery procedure.

Before outage, snapshot local database/WAL/shared-memory/journal, configuration,
destination marker, partial/final/manifest names and remote enrollment/binding/
source evidence using file metadata and SHA-256 only. Never open SQLite to inspect
it. Start normal bootstrap into unavailable NFS without a pause hook. Require one
actual bootstrap child in D, local Starting status, a connected/sent unanswered
health request and identical local evidence while blocked. The existing bootstrap
assignment deadline and configured shutdown behavior are unchanged.

Kill only the coordinator for blocked cases. Following-stop cases use a two-second
wait: distinguish prompt confirmed exit from ShutdownIncomplete/exit 2 with a live
D worker, killing the coordinator only in the latter case. Each surviving orphan
must remain D across three bracketed raw-flock/logical-status observations, report
OwnerUnavailable/exit 2 and refuse three competing effect commands. Preserve epoch
and original state; raw lock closure is observational here and does not replace
increment 47's separate strict regression.

Restore NFS and confirm old exit before recovery. Require identical local and
remote evidence before starting again. Restart with the original configuration,
database and enrollment receipt, without re-initialization, replacement state or
re-enrollment. Require the same database inode and immutable receipt afterward.
Enrolled-empty delivers its first recording on attempt 1. Populated replays job 1,
completes attempt 2 and retains the original partial's inode/size/hash, private
claimed source and producer-reused path. Verify destination SHA-256 and manifest.

Retain six normal transfers, twelve NFS-state-parent refusals, 184 file refusals,
inherited-lock/startup/interruption checks and clean teardown. Run both mandatory
GNU/glibc-2.22 zigbuild/ELF/pinned-SLES userspace gates; audit exact source/archive,
service/artifact hashes and scripts. No Rust runtime change is planned.

## Results

The first fixture `nfs-20261017T205820Z-1afa98b1` is preserved as
[initial evidence](RUST-NFS-ENROLLED-BOOTSTRAP-INITIAL-EVIDENCE.json). Both enrolled
cases passed; populated ownership and pre-recovery preservation passed, but its
recovery correctly entered review with staging-allocation EEXIST. The initial
seed killed the worker before its coordinator, allowing that live coordinator to
react/retry. The corrected seed kills the coordinator first, then its paused
worker, and requires only 1.part after confirmed exit. No allocations are deleted,
review cleared or application policy changed to pass.
Cleanup succeeded. The production Rust inputs remain unchanged.

Corrected fixture `nfs-20261017T210948Z-199f41fd` passed all eight cases; see
[complete existing-state evidence](RUST-NFS-ENROLLED-BOOTSTRAP-EVIDENCE.json).

| State | Debug blocked | Debug following stop | Release blocked | Release following stop |
|---|---|---|---|---|
| Enrolled-empty | Surviving D orphan retains ownership | Prompt confirmed exit | Surviving D orphan retains ownership | Prompt confirmed exit |
| Populated, WAL + 1 MiB partial | Surviving D orphan retains ownership | Prompt confirmed exit | Surviving D orphan retains ownership | Prompt confirmed exit |

Four surviving orphans retained ownership across three D-bracketed samples each,
returning OwnerUnavailable/exit 2. Twelve competing service/initialize/transfer
commands refused, maximum 1.047 seconds. Sampled orphan status and Starting status
took at most 0.969 seconds each. No ownership loss occurred. All four following-
stop cases exited promptly with the configured two-second wait, maximum 1.094
seconds including Podman overhead. These do not qualify a surviving terminating
orphan or the default-60 uninterruptible deadline branch for these states.
No new case observed raw flock closure; retain increment 47's separate strict
counterexample regression evidence.

All eight cases had a connected/sent unanswered health request during bootstrap.
The database, present/absent WAL/shared-memory/journal, configuration and local
staging/final/manifest evidence matched before outage, during blocked bootstrap
and after confirmed old exit. Remote receipt/binding/source evidence also matched
before recovery. No SQLite parser was used for these snapshots. Normal recovery
used the original database inode and immutable receipt in every case, without
re-initialization or replacement state; the old epoch stayed unchanged until exit
and normal startup replaced it with the new coordinator group under the same
boot, namespace and guard identity.

Each populated setup had a nonempty retained WAL, confirmed coordinator exit
before seed-worker kill, and exactly 1.part before bootstrap. All four replayed
job 1 to Committed on attempt 2 and retained the original partial inode, 1048576-
byte size and SHA-256. All four enrolled-empty cases delivered their first job on
attempt 1. Every case verified source/destination SHA-256, completion manifest,
private source retention, producer-reused path and stable root identities;
source cleanup remained false.

Retained regressions passed six normal NFS transfers, twelve NFS-state-parent
refusals and 184 file-owner/mount/control refusals across fourteen preserved
fixtures (maximum 1.188 seconds). Inherited-lock/interruption, isolated startup
and stable-root restoration checks passed. The retained global Starting status
took 0.984 seconds; SIGTERM confirmed bootstrap exit before restoration without
SQLite/readiness. All current script and service hashes match saved evidence.
Cleanup errors are empty. Independent inspection found no containers or fixture
volumes/networks, only the two existing toolchain/cache volumes and default network.

Exact fixture command:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T195308Z-0fbd983f --qualification-gate rust/validation/20261017T195309Z-ea5be268-nfs-qualification --isolated-startup --coordinator-death --death-scope bootstrap-existing-state
```

Future runs can use fresh passing gate directories; exact source/archive and
executable hash checks remain mandatory.

## Compatibility and exact artifacts

Fresh production `20261017T205538Z-a820f9e4` passed 204 tests per profile;
qualification `20261017T205538Z-83e00d79-nfs-qualification` passed 205 per profile.
Each passed twenty ELF audits and six negative controls in pinned SLES 12 SP5
userspace via GNU/glibc-2.22 cargo-zigbuild. The graph remains 42 external packages,
maximum GLIBC_2.18 and the standard GNU loader. No Rust source, Cargo dependency/
feature, schema, private protocol or runtime policy changed.

Complete 61-file source inventories, source-archive digests and all artifact
hashes match current inputs. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). Both gates
completed cleanup. The fixture ran with prior passing increment 48 gates
`20261017T195308Z-0fbd983f` and
`20261017T195309Z-ea5be268-nfs-qualification` while fresh gates ran. Their complete
source archives match current Rust files, and all four service binaries are
byte-for-byte identical to the fresh passing production/qualification × debug/
release binaries. Preserve those actual fixture gate IDs in the raw reports.

## Remaining scope

Publication/manifest coordinator death, both-NFS crash layouts, other durable
operation/synchronization boundaries, actual systemd/account policy, server/NAS
reboot/reclaim/power loss and delayed RPC settlement remain unqualified. SLES
containers share the modern runner kernel/CPU. Preserve earlier failed evidence,
the strict increment 47 regression and the fresh-bootstrap/source-read scope in
increment 48. FR-03/05 remain open; registration and offline repair remain deferred.
Maintain SC-029/034/036/064/092/093/095 and DOC-03/04/05 with stable IDs.
