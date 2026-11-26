# Parallel-test flake analysis

Reliability push approved 2026-11-26. Analysis only, based on main `0725d606`.
The failures and successful isolated runs are coordinator reports; raw failure
packs were not provided. No Cargo run, reproduction, system change or product
fix was performed here. R3 waits for review and coordinator approval.

## Findings and confidence

- **Confirmed shared-resource hazard:** direct-worker tests publish worker
  epochs using the test executable's PID/process group. Different fixture
  directories do not isolate group membership. A live child of another test
  can correctly block reacquisition of a fixture whose own child has exited.
  This directly explains the reported ownership symptom; identifying the exact
  other PID in each historical failure still needs captured process evidence.
- **Confirmed product availability path:** a real admin/operator read can get
  `storage_unavailable` behind slow Store work because its reply deadline is
  two seconds. This is not inherently a test-only CPU-starvation artifact.
  However, the observed 503s do not identify which timeout/error path fired.
- **Unconfirmed causes:** specific manifest/HTTP failures without their error
  text cannot be assigned to host slowness, port reuse, leaked children or a
  product defect merely because they pass alone. They remain evidence to collect,
  not tests to retry until green.
- **Known prerequisites:** three mover-fs migration CLI tests depend on a
  supplied executable (one is qualification-only); five reload unit tests
  depend on supplied TLS fixtures. Their missing-prerequisite failures are
  distinct from intermittent parallel failures.

The SLES driver currently launches each test binary through
`/usr/bin/setsid --wait ... --test-threads=1`
([driver](../scripts/check-rust-sles.py)). The local four-thread run exercises
additional in-process concurrency. A passing serial gate does not establish
parallel fixture isolation; a failing parallel fixture does not authorize
weakening production ownership checks.

## Shared epoch mechanism

[`worker_epoch::prepare`](../rust/crates/mover-fs/src/worker_epoch.rs) calls
`setpgid(pid,pid)` if necessary and records the current process's group/start
identity in each fixture's `workers.json`. Its static PREPARE mutex protects
preparation, **not the lifetime of children** across tests. The direct workers
spawned by API `effect_child` inherit that process group.

[`InstanceGuard::for_database`](../rust/crates/mover-fs/src/instance.rs) refuses
both a contended physical flock and `worker_epoch::active(guard,true)` using
the same public message. The latter ignores the caller's own matching leader,
then rejects **any other live member of the recorded group**. It has no notion
of which test fixture owns that member. Thus:

1. Test A and B have different state/source/destination paths.
2. A publishes an epoch using the test executable's process group and starts
   a direct worker; B does the same using that same group.
3. A reaps its worker and drops its guard. B's worker is still alive.
4. A's next guard acquisition, or `Fixture::retire_test_epoch`, sees B's group
   member and refuses. Closing A's descriptors or waiting A's child alone is
   insufficient to drain the shared group.

A newly spawned ordinary service can also briefly inherit the harness group
before its own initialization makes it a group leader. Consequently a mutex
covering only the three named tests or only `prepare_workers()` is incomplete.
Standalone service executables establish their own groups; production is not
promising multiple independent coordinators inside one process.

There is a second limit: `group_alive` conservatively reports held if its local
`/proc` walk takes 200 ms, exceeds 16,384 observations, or encounters unknown
process evidence. Descheduling can trigger that even with separate groups.
This is fail-closed protection, not proof of a surviving child. Preserve the
failure evidence and retry only after actual ownership can be established;
do not remove epochs or treat elapsed time as proof of worker death.

## API cases

Sources: [api.rs](../rust/crates/file-mover/tests/api.rs), especially
`effect_child`, `child_reply`, `Fixture::retire_test_epoch`, `wait_manifest`,
`seed_legacy`, and each named body.

| Test | Shared resource or timing assumption found | Classification and proposed change |
|---|---|---|
| `claim_children_preserve_intent_receipt_order_and_reconcile_lost_reply` | Repeated direct Observe/Allocate/Apply children use `effect_child`'s synthetic harness epoch. Each child is waited, but another test's group member can remain when `f.start()` retires the epoch. | Test isolation defect for this symptom. Run the whole direct-worker scenario in a private test subprocess/group, or serialize all participating lifecycle/spawn scenarios. Keep durable-intent/lost-receipt assertions. |
| `delivery_session_checks_source_binding_and_rejects_authorization_downgrade` | Two sequential sessions call `effect_child`; its next `InstanceGuard::for_database` can observe another fixture's worker. | Same group hazard; isolate the whole scenario, not just each spawn. Keep binding/downgrade refusals. |
| `delivery_session_validates_the_copy_buffer_it_is_given` | Four session variants reap their own children, then reacquire the same synthetic epoch while other tests may have live children. | Same group hazard. Keep valid/default/invalid buffer cases and explicit child exit checks. |
| `publication_child_reconciles_file_and_manifest_effects_without_database_receipts` | Repeated direct payload/manifest children use the shared harness group. It also deliberately catches a checkpoint panic; that expected panic must not be confused with a leaked child or real test failure. | Same isolation hazard is present; exact historical failure location is unknown. Isolate the full publication scenario; retain phase-3 receipt/replay and exact bytes checks. |
| `background_multi_file_delivery_commits_after_202_without_more_requests` | Ordinary service, no direct helper in its body. Three files plus manifest must reach visible **and recorded** commit within `wait_manifest`'s 15 s; status uses the operator path. API client read is 15 s, startup 10 s, fixture stop 5 s. | Timing/Store availability candidate, not a proven group collision for this test. Capture the actual failed assertion, service stderr and status latency. Scale only functional harness waits if scheduler delay is demonstrated; a real 503, blocked recording or incomplete custody remains a product signal. |
| `seeded_uuid_looking_legacy_job_recovers_numeric_destination_and_v1_after_restart` | `seed_legacy` explicitly publishes an epoch in the test process, performs synchronous claims, then calls `retire_test_epoch`. It subsequently uses ordinary service restarts and 15 s manifest waits. | Confirmed group hazard in offline seeding; later timeout failures need separate evidence. Isolate the entire seed-and-restart scenario. Preserve numeric destination, v1 bytes and distinct new UUID namespace checks. |
| `timer_retries_do_not_starve_under_sustained_sender_load` | Old unpaced try_send admission assumed per-sender fairness; pending replies were rejected; late confirmations could cross the 45 s sender cutoff. Also affected by the separately approved allocation-directory defect. | R1 ([#120](https://github.com/joey-huckabee/background-file-mover/pull/120)) paces retries, counts pending, preserves attempted UUIDs and adds confirmation grace. Claim fix [#119](https://github.com/joey-huckabee/background-file-mover/pull/119) is separate product work. Keep timer progress, health, strict blocked/error rejection, replay/commit/source audits and #117 diagnostics. |

The API fixture's PID-plus-AtomicU64 paths are distinct within a binary and
between processes. The fixed labels/UUIDs refer to separate databases, not a
shared replay registry. No fixed-port collision explains the ownership messages.

## TLS/admin cases

Sources: [admin fixture/tests](../rust/crates/file-mover/tests/tls_listener/admin.rs),
[native fixture](../rust/crates/file-mover/tests/tls_listener/mod.rs),
[admin routes](../rust/crates/file-mover/src/admin.rs) and
[session admission](../rust/crates/file-mover/src/session.rs).

These fixtures have separate PID/counter roots, account/state/credential folders,
service processes, sessions and ports. Common generated TLS inputs are read-only;
server credentials are copied into each private fixture. Constant account names,
passwords and UUIDs are not global application state shared by these daemons.
The admin client read timeout is **20 s**, not five; its connect timeout is 5 s.
Producer TLS and private-operator helpers use 5 s I/O waits. Startup is 15 s,
stop is 10 s, and common delivery polling is 15 s.

| Test | Sensitive paths read | Assessment and proposed change |
|---|---|---|
| `admin_https_login_session_logout_and_boundary_precedence` | Many sign-ins, session/CSRF/boundary checks, unauthenticated read-boundary checks, private delivery polling and global logout. Login runs bounded password verification. | The login handler returns service_busy for verifier timeout, not storage_unavailable; session checks do not call Store. The body admits producer transfers, not admin mutations holding the logout admission guard. Its unauthenticated admin reads refuse before Store access. Thus do not assign this test’s failure to the common Store path without its exact route/line; private status polling and logout have different paths. Preserve boundary expectations. |
| `admin_retry_delivers_a_reviewed_job_and_replays_its_receipt` | Real foreign-file collision, 15 s delivery-failure wait, offline transition to review after stopping, restart, history/retry-context reads and retry action/replay. | CPU/storage delay and two-second observer deadlines are candidates; offline Store use is after stopping, not a demonstrated live competing SQLite writer. Preserve exact replay and review/collision semantics; add route/status/log diagnostics before timeout scaling. |
| `admin_delete_data_is_off_by_default_and_removes_only_retained_copies` | Off-by-default boundary, account login/restart, preview/instance-scope reads, serialized action decision and a 10 s deletion-completion poll. | A 503 on preview/read can be observer delay; one on an admitted mutation has outcome semantics and cannot be blindly retried. Preserve proof freshness, actual deletion counts, originals/committed output and live workers. Diagnose before proposing a product change. |
| `admin_clear_history_forgets_delivered_and_cancelled_jobs_but_keeps_files` | Delivery/commit wait, confirmation/scope reads, serialized clear/cancel, 10 s cancellation completion, restart/replay checks. | Same Store/observer risk. Keep clear forgetting and untouched-file assertions; do not resubmit actions just to hide a 503. Isolate failing route and whether it started/finished its decision. |
| `admin_file_name_search_matches_nested_paths_in_bounded_chunks` | Offline seeding of 34 jobs / 8,196 path rows; multiple authenticated searches across an 8,192-row / 1 MiB chunk boundary and query-bound cursors. | Concrete nontrivial Store read workload; a chunk is bounded in data, not guaranteed under two seconds on a busy host. Keep chunk/cursor assertions. Measure query duration versus queue wait; this is the strongest focused read-latency case, not evidence of shared UUIDs or mutable certificate fixtures. |

All five can compete for host CPU, disk, memory and child scheduling with other
fixture processes. Password work consumes resources, but that alone does not
identify a Store failure. Do not serialize all TLS tests and call the product
availability issue solved. Gate-only timing/performance/isolation assertions
must retain their intended bounds; a configurable local **functional harness**
wait scale should never alter service protocol deadlines or release criteria.

## `storage_unavailable`: product path versus observed attribution

**Decision from source: this cannot be classified as merely a test artifact.**
A real operator can receive it under load with healthy SQLite. This is a product
availability/diagnostic concern, although a retryable, bounded refusal is not
by itself data corruption or proof of broken custody. Host contention may be
the trigger in these local runs; the source path is the same for a real host.

- [`operator_reply`](../rust/crates/file-mover/src/lib.rs) enqueues on the shared
  observer and waits **2 s**. A timeout/dropped reply maps to storage_unavailable;
  observer enqueue failure instead maps to service_busy. The prototype's status
  path has the same two-second bound. `status_response` also maps any actual
  Store error to storage_unavailable. Admin reads forward these results.
- [`Store::call`](../rust/crates/mover-store/src/lib.rs) feeds a **32-slot**
  channel to one SQLite-owner thread. Calls wait synchronously for enqueue and
  completion. Admission, claim/transfer commits, retry discovery, searches and
  snapshots share it. One slow operation or enough queued work can outlast the
  operator deadline; the HTTP timeout does not remove an already queued task.
- SQLite's **250 ms busy timeout** is for database-lock contention. It does not
  bound queue residence, FULL-sync/checkpoint I/O, callback time or descheduling.
  Calls sharing this one owner are not multiple simultaneous SQLite writers.
  Increasing the busy timeout without proof can keep the entire owner blocked
  longer and worsen operator latency. An actual SQLITE_BUSY/LOCKED still needs
  its error code and competing-connection evidence; fixture CPU load is not proof.
- The unchanged change callback runs on the owner after changed operations and
  bumps a watch value. It contains no logging or filesystem I/O. Examined SSE
  handlers copy the version before awaiting network writes. No callback/watch
  deadlock was identified. The state/session mutex is released before an admin
  action's Store work; a separate admission guard deliberately spans that work.
- [`logout`](../rust/crates/file-mover/src/admin.rs) can independently return
  storage_unavailable after **10 s** waiting for `logout_all_serialized` to drain
  admitted actions. Revocation already happened. Do not interpret it as failed
  revocation, roll it back, or infer a SQLite busy error.
- `instance_scope` can emit the code for a malformed/missing high-water field;
  Store-owner failure/WorkerStopped and genuine storage errors are other paths.
  Exact method/route, safe typed cause and monotonic timing are required to
  distinguish them. A larger client read timeout cannot prevent the server
  deliberately sending a 503 at two seconds.

**Proposed product work (approval required):** first add bounded, secret-safe
attribution for observer queue wait, Store queue wait/operation/commit/callback
latency, deadline expiry and safe SQLite primary/extended codes. Then introduce
reviewed bounded scheduling/admission for read-only operator work and discard
expired **unstarted reads**, so stale timed-out reads do not extend the backlog.
Give reads a bounded share rather than unlimited priority that starves claims.
This changes queue ordering and avoids obsolete read work; it must retain actual
transaction completion, mutation admission/logout ordering and guard lifetime.
It cannot preempt a stalled active fsync. A separately owned read-only snapshot
connection/thread is a larger alternative needing lifetime/snapshot review,
not an automatic R3 implementation.

Retain present public error semantics initially. Any new code, retry policy or
protocol deadline requires contract review/approval. Never cancel/rollback a
mutation just because its HTTP observer timed out, infer action completion from
a read timeout, detach a custody-owning thread, or broadly whitelist 503s in
assertions. Instrumentation and load evidence should determine whether a later
latency-budget change is justified. No runtime fix is authorized by this PR.

## mover-fs process-group test

`worker_epoch::tests::live_group_member_blocks_reacquisition_without_any_inherited_guard`
in [worker_epoch.rs](../rust/crates/mover-fs/src/worker_epoch.rs) starts a plain
`/bin/sleep` inheriting the harness group, proves the physical flock is free,
checks the live group member still excludes ownership, kills/reaps that child,
and assumes the next acquisition succeeds immediately. A different test's live
member invalidates the last assumption. The test is meaningful alone; the
parallel fixture isn't isolated. Run its entire scenario in a dedicated process
with a private group and join its exact child on every exit path. An owned-child
RAII guard must also kill/reap the sleep if an earlier assertion panics.
Do not loosen `group_alive`, ignore arbitrary group members or delete an epoch.

## Missing gate prerequisites: name and skip policy

The source identifies these three executable-dependent mover-fs unit tests in
[backup.rs](../rust/crates/mover-fs/src/backup.rs):

1. `backup::tests::migration_cli_previews_converts_once_and_preserves_original_job_without_payload_roots`.
2. `backup::tests::migration_cli_requires_fresh_verified_backup_and_ignores_fault_controls_in_production`.
3. `backup::tests::migration_cli_kill_reopens_original_or_committed_state_without_restore`
   (**compiled only with nfs-qualification**).

All call `migrate_command`, which expects `FILE_MOVER_TEST_EXECUTABLE`. The first
two are in ordinary builds; the third is not. These are the three identifiable
gate-executable dependencies, not a claim that an ordinary non-qualification
run necessarily fails all three. If the reported three refer to a different
failure list, retain that log to reconcile it rather than guessing another name.
They are not inherently SLES-only: a matching local executable/configuration can
satisfy them, as in the coordinator's native checks.

These five file-mover unit tests in [reload.rs](../rust/crates/file-mover/src/reload.rs)
all call a Fixture/certificate helper expecting `FILE_MOVER_TLS_FIXTURES`:

1. `reload::tests::cancelled_session_registry_is_independent_of_stale_queued_work`.
2. `reload::tests::activation_before_first_future_poll_still_drains_the_registered_connection`.
3. `reload::tests::admitted_work_may_finish_but_deferral_cannot_authorize_a_later_attempt`.
4. `reload::tests::certificate_expiry_is_rechecked_at_actual_admission_without_changing_host_time`.
5. `reload::tests::rejected_replacement_and_shutdown_preserve_the_active_policy`.

`localhost:8443` in that unit fixture is policy data; those tests do not bind
that fixed TCP port. They need fresh fixture DER/key files with the required
private-parent modes/local filesystem and current certificate validity.

**Recommendation:** skip with an explicit missing-prerequisite reason **only
when a required fixture variable is absent in an explicitly non-gate run**.
Do not skip when a provided executable/file is missing, stale, unsafe or malformed.
Do not generate replacement keys silently. Gate preflight must require the
variables, audited executable/feature match and complete current fixtures;
missing gate inputs must fail, never become successful skips. Return-based
runtime skips otherwise look like passes to libtest: print/report their counts
outside captured output and do not count them as evidence. The gate runner must
check required execution before adopting this policy. This is proposed R3 work,
not a skip already applied. The current driver supplies both fixture variables.

## Other resource candidates and cleanup

- **Ports:** fixtures select loopback port zero then drop the reservation before
  the executable binds. There is a real reservation/bind gap, and producer/admin
  selections can overlap before either listener starts. No supplied error says
  EADDRINUSE, so this is a candidate, not the diagnosed cause of a valid HTTP 503.
  Prefer a test-scoped allocation/start lock and narrowly handled verified bind
  collision with a new fixture/authority. Do not retry arbitrary startup errors
  or add a production inherited-listener feature as an incidental test fix.
- **Mounts/identity:** the WSL helper hides the WSLg root mirror in a private
  namespace and runs the service user. Alias/custody refusal outside that setup
  is expected safety behavior. Preserve it; never chmod operational directories
  or weaken instance checks for developer convenience.
- **Children:** raw `std::process::Child` Drop does not kill/wait. Direct-worker
  helpers normally wait, but assertions can unwind before those waits. Fixture
  Drop kills/reaps its service coordinator only; this is not proof that every
  descendant exited. A leaked or still-exiting direct child can cause subsequent
  shared-group failures and CPU contention. Use test-only RAII owners for exact
  spawned children and IPC, retaining guards until actual exit; record PID/start,
  PGID and exit proof before retiring synthetic epochs. Never pkill, group-kill
  an unowned harness group, unlink stale custody, adopt workers or repair state.

## Proposed R3 sequence and local experiments

1. **Test isolation PR:** put each whole direct-worker/epoch/legacy-seeding
   scenario in a private subprocess/group. A global test mutex is an interim
   alternative only if it covers *all* shared-group lifecycle/spawn paths, for
   their full duration. Add owned-child cleanup on assertion/panic. No production
   ownership relaxation. Demonstrate the old interference by holding one owned
   sibling worker alive while another fixture reacquires; then show isolation
   permits only the unrelated fixture and still rejects the real live owner.
2. **Prerequisite PR:** explicit local skip reporting and mandatory gate
   preflight/execution accounting for the eight names above. Keep malformed
   supplied fixtures as failures. No runtime behavior change.
3. **Functional wait/diagnostics PR:** capture exact failed method/route, JSON,
   service logs, PID/group/start and current lifecycle before cleanup. Scale
   only measured scheduler-sensitive harness waits, with the chosen scale
   reported; do not scale protocol/security/performance bounds or conceal 503s.
4. **Product proposal, not implementation:** bounded Store/observer attribution
   first, then a read-admission/scheduling design based on measured causes.
   Coordinator approval is required before any runtime edits.

For the coordinator's existing WSL namespace, matching executable/TLS fixtures
and gate SQLite flags (same source/build/features for each pair), compare:

```sh
# From rust/, using the already prepared local environment:
cargo test -p file-mover --test api delivery_session_ -- --test-threads=4 --nocapture
cargo test -p file-mover --test api delivery_session_ -- --test-threads=1 --nocapture
cargo test -p mover-fs --lib worker_epoch::tests:: -- --test-threads=4 --nocapture
cargo test -p mover-fs --lib worker_epoch::tests:: -- --test-threads=1 --nocapture
cargo test -p file-mover --test tls admin_file_name_search_matches_nested_paths_in_bounded_chunks -- --test-threads=1 --nocapture
cargo test -p file-mover --test tls admin_ -- --test-threads=4 --nocapture
```

These are proposed runs, not results. Preserve the first failure and its source,
feature set, method/route, elapsed times and owned-process membership. A serial
pass helps separate interference, but does not prove an isolation fix or explain
a 503. Do not run a second heavy build/test suite alongside this comparison.
A later approved barrier-controlled Store-owner test can hold work for >2 s,
queue an operator read and distinguish a pure reply timeout from an actual
SQLite lock error; no such Store pause exists in the inspected source. Test a
separate disposable second connection holding a write lock beyond 250 ms only
as an independent SQLITE_BUSY experiment, never against operational state.

## Validation limits

Read the named bodies and shared helpers, worker epoch/guard acquisition,
Store queue and search code, admin routing/session admission, fixture-dependent
unit helpers and the SLES runner. Relative links and whitespace are checked.
No local Cargo, timing experiment, fixture generation, installation, process
kill, product edit or SLES execution was performed. All release restrictions
and independent review requirements remain in force.
