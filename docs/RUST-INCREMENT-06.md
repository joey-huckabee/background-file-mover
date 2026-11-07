# Rust automatic local recording delivery

The local service now delivers fully claimed recordings automatically. The recorder
still sends one JSON request and waits for 202; no subsequent request or transfer
command is needed. 202 releases source names after durable claiming, independently
of destination delivery. Consumers wait for the valid `COMMITTED.json` manifest.
Source deletion is disabled throughout this increment.

## Workers, recovery and admission

A dedicated delivery thread discovers at most one eligible job per scan from
SQLite. There is no volatile delivery queue to lose on restart. It copies files
serially, verifies each destination staging object, publishes each file without
clobbering, then commits the recording manifest. Claiming keeps its own one-slot
queue/thread; both communicate with the existing bounded SQLite owner. Bulk data
I/O holds no SQLite transaction and does not occupy the network executor.

The workers share the held local source namespace guard. Delivery also acquires
the pinned destination's namespace lock. Each file has its own staging namespace:
file 0 retains `.staging/<attempt>.part` for prior-record compatibility; subsequent
files use `.staging/<file-id>/<attempt>.part`. Their published relative names stay
unchanged beneath the recording directory. Shared parent folders are traversed
only within the already recorded private recording directory.

Discovery requires every claim receipt; partial/missing recording submissions
cannot begin delivery. Completed manifests exclude jobs from discovery. Missing
destination roots/private namespaces defer delivery five seconds and remain
eligible across restarts. Other failed/uncertain attempts receive up to three
reconciliation attempts, five seconds apart, before a persistent review condition.
Review blocks do not reset on service restart or recorder replay. There is no
operator unblock/repair endpoint yet. Errors are logged, with retry state in
`delivery_failures`; health is liveness, not delivery/storage readiness.

Startup settings `max_retained_jobs` (default 64) and `max_retained_bytes`
(default 1 TiB) bound this retention-mode prototype. New acceptance checks the
job count transactionally; known source size is checked before private allocation
and again before recording claim intent. All accepted jobs and observed claim
sizes count, including committed recordings whose sources remain retained.
Replay remains available when admission is full. Refusal returns non-202
`503 retention_capacity`; it never releases source paths.

The byte limit applies independently to retained claimed source bytes and
destination attempt reservations. Each destination attempt conservatively charges
its full claimed size, including partial attempts and published files. Capacity
is checked before allocation and before intent commit. Old staging is preserved
and no automatic archival/deletion releases these budgets. Explicit operator
retention/repair tooling and filesystem free-space margins remain production work.

## Manifest protocol

Schema 5 adds a durable 128-bit local instance identifier, manifests and delivery
retry/review records. Existing schemas 1–4 migrate transactionally without
replacing jobs, claims or transfer evidence. The identifier comes from the local
OS random device and survives restart; it is an ownership label, not a credential.

Manifest version 1 contains `instance_id`, `job_id`, `generator_id`,
`submission_id` and the exact ordered required files. Each entry contains stable
`file_id`, relative `path`, actual `size_bytes`, `algorithm:"sha256"` and digest.
It has no timestamp or private source path. Exact serialized UTF-8 bytes and their
SHA-256 are stored before filesystem allocation. Manifest size is bounded to
128 KiB. Strict parsing rejects unknown/duplicate fields; recovery compares exact
bytes with the immutable published-file mapping, rather than accepting an arbitrary
equal-looking manifest. File data remains under the qualified custody contract.

The durable boundaries are intent, allocation receipt, completed write,
publication intent and committed receipt. Staging is exclusively created at
`.staging/COMMITTED.part`, then synchronized before its identity is recorded.
Only that recorded staging inode may be rewritten after an interrupted write;
the exact bytes are already durable in SQLite. The completed manifest becomes
owner-read-only, is synchronized and verified before publication authorization.

Publishing uses NOREPLACE to `COMMITTED.json`, synchronizes the manifest and
affected directories, then records commitment. A manifest visible before a failed
SQL result is reconciled by recorded ownership/identity, exact bytes and required
synchronization. It is never replaced. Foreign collisions, ambiguous two-name
effects, changed published objects or lost namespace custody block commitment.
An allocation effect without an allocation receipt remains an orphan and blocks
adoption; creation-intent/orphan tooling is still required for production.

Every required file must have a durable verified publication receipt and unchanged
protected identity before manifest authorization. Normal completion checks
custody/metadata without adding another payload hash pass, preserving 3N normal
logical I/O. Uncertain file publication recovery can add a digest reread as before.
Commitment hydrates the recording's committed fact; all claims remain retained,
and the actual startup/job deletion policy remains disabled.

## Running and evidence

Use [local.example.json](../rust/config/local.example.json) and provision both
source/destination roots and their private service-owned 0700 `.file-mover`
directories. Start `file-mover CONFIG.json`, submit the minimal generator request,
and consume data only after validating the manifest. Missing destinations may be
provisioned later: the same accepted job resumes on its pinned route. The manual
single-file command remains for stopped-service diagnostics and now reports the
actual committed fact. Shared consumer permissions are not implemented; current
private recording directories are accessible to the service UID only.

This is still a protected local-filesystem prototype. Registration, remote REST,
NFS, S3, process-isolated workers, guaranteed bounded shutdown, production mount/
instance namespace authorization, metadata permissions and destructive cleanup
remain deferred. SIGINT/SIGTERM stop admission and join local authorized work;
local syscalls can still delay shutdown. Killing a remote worker would not fence
an outstanding NFS request; do not enable NFS through this thread implementation.

The mandatory GNU/glibc 2.22 gate runs actual executable HTTP/background tests,
library faults and exact debug/release artifacts in pinned SLES userspace. No
dependency/version/feature graph expansion is needed: serialization reuses the
already-qualified Serde/JSON configuration. E6 remains paused. Current evidence
is in [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).
The passing run has 67 tests in each profile, twenty audited executables and
maximum imported version GLIBC_2.18. No package or shared-library requirement is added.

Tests cover three-file automatic delivery after 202, same-parent nested names and
empty files, producer reuse, restart discovery without resubmission, pinned route
changes, retention refusal/recovery, persistent retry/review state, instance/schema
migration, incomplete-set withholding, foreign manifest collisions, receipt failure
after manifest publication, and process exits at every manifest boundary. A write
effect before its receipt recovers the recorded owned staging; an allocation gap
preserves the orphan and withholds commitment. Sources are retained in every case.
Containers/process exits do not qualify storage/server power-loss durability or
an old kernel. Historical C++ trace coverage is unchanged; Rust evidence supports
L1-SYS-031/034, outage handoff intent and configurable admission obligations.
