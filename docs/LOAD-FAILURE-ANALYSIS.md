# Sustained-load failure analysis

Analysis only; no product change, new test or relaxation of existing assertions.
Source baseline: main `eb3ef9e`; logging comparison: #115 `6fda86f`;
diagnostics reference: #117 `d27d158`. No Rust execution or local reproduction
was performed by the cloud worker. The run counts below are coordinator-reported;
raw run packs were not supplied here. Logging remains on hold.

## Conclusions

1. **There is a concrete availability defect on main:** `allocate_claim` compares
   mutable directory metadata as if it were immutable identity. Creating a
   different file in the same source parent can refuse an unchanged payload.
   The test writes its late files while normal load claims run. This explains
   the reported diagnostic without simultaneous claims of the same file or a
   logging effect. It is a source-supported mechanism, not yet a reproduction
   proving which field differed in run 20.
2. **The reported error does not itself persist a block.** It becomes HTTP 409
   `recording_blocked`, `retryable=false`, but this allocation refusal neither
   records a claim nor sets a missing deadline/block. For a new present-only
   job, it also leaves nothing for timer discovery. The response classification
   can strand a well-behaved producer, even though a same-UUID resend after
   directory churn stops can succeed without operator intervention.
3. **`handoff_pending` and `storage_unavailable` do not prove a SQLite busy
   failure.** They also mean producer/observer reply deadlines expired. One
   SQLite-owner thread serializes this daemon's calls; its queue delay is not
   governed by SQLite's 250 ms busy timeout. The underlying cause of the paired
   503s and intermittent admin failures is unresolved.
4. **No logging-OFF store-thread regression was identified.** #115 does not
   change `mover-store`; its default OFF path creates no logging threads or
   sinks and retains legacy prints. Timing/frequency differences between builds
   are possible; the supplied sample does not establish logging causation or
   exonerate every #115 change. Resolve the directory defect and instrument the
   distinct timeout/error paths before unblocking logging qualification.

## Evidence supplied

| Scenario | Coordinator observations |
|---|---|
| Main + #117, logging OFF, WSL debug | 41 runs: 39 OK; one late-202/sender-window margin failure; one sender deadline, with job 19 AwaitingClaims; zero `recording_blocked`. |
| #115 + #117, local merge, logging OFF | 20 runs: run 20 returned `409 recording_blocked` for `b614c088-a45c-f3cc-9eb2-012a800fe730` (`load-new-2-0`). Stderr twice reported `allocate: blocked: claim observation changed before allocation`. Run 1 returned `503 handoff_pending`, then job 2 status returned `storage_unavailable`. |
| Earlier #115 runs | Another OFF `recording_blocked`; three admin TLS failures with `storage_unavailable`, passing alone and in two later full runs. |

The historical local merged source/hash, timestamps of the late writes versus
the failing Allocate, raw StoreError values and per-thread latency are not
available here. The OFF worker diagnostic itself has no job ID; two identical
lines do not prove two refusals of this UUID rather than different claim attempts.
Zero occurrences in 41 main runs is not evidence of absence.

## Claim observation: an unchanged file can fail

[ObjectIdentity](../rust/crates/mover-core/src/claim.rs) derives complete equality
across device, inode, UID, size, mtime seconds/nanoseconds and link count.
It has **no ctime or atime field**. In
[`mover-fs/src/lib.rs`](../rust/crates/mover-fs/src/lib.rs), `observation` creates
that same structure for files and directories; `owned_directory` validates
ownership/mode, then returns the full observation.

`observe_claim` captures four objects in a ClaimIntent:

- `root`: the configured source root;
- `parent`: the directory containing the original file;
- `area`: the shared `.file-mover` namespace, **before allocation**;
- `source`: the payload file, required to be a regular, owned, single-link file.

`allocate_claim` calls `observe_claim` again with the expected payload size,
then rejects **any** difference using `fresh != *observed`. That includes the
size/mtime/link count of all three directories. Only after this comparison does
it call `mkdirat` for the private area. `same_directory`, used elsewhere in the
same module, instead compares device/inode/UID and is preceded by fresh custody
checks; it illustrates the distinction between directory identity and contents.

A valid interleaving is therefore:

1. The claim thread observes `source/current/load-new-2-0` and its parent.
2. The test thread creates a different `source/current/load-late-…` file.
3. The load file's device/inode/size/mtime/link count remain unchanged, but the
   parent's mtime changes (and its size may change).
4. Allocate re-observes the unchanged load file and the changed parent, and
   returns the exact reported Blocked diagnostic, **before creating an area**.

The [sustained-load test](../rust/crates/file-mover/tests/api.rs),
`timer_retries_do_not_starve_under_sustained_sender_load`, prepares normal inputs
before starting senders, but deliberately writes 16 late files after about two
seconds of load. These files share the normal files' parent directory. The
statement that nobody modifies the normal file is consistent with this race.

Real producers can create unrelated sibling recordings while another submission
is being claimed. If files lie directly under the configured root, root metadata
can change too. In move mode or confirmed cleanup, a separate delivery worker's
removal of another private area can change namespace metadata while a claim is
between Observe and Allocate. That is another possible trigger on main, but
this copy-mode test supplies no evidence of such cleanup and does not require it.
Creating regular sibling files normally does not change directory link count;
creating/removing child directories can. Neither ctime nor atime can explain
this equality failure. Source link-count changes are separately validated by
`source_with_links`; a forbidden link count can fail with a different diagnostic.

### Same-file producer/timer/replay concurrency is not the mechanism found

[`Worker::start` and `handle_submission`](../rust/crates/file-mover/src/lib.rs)
run producer processing and `Retry::pass` synchronously on the single
`mover-local-claim` thread. A due pass runs after the request, not during it.
[`claim_file`](../rust/crates/file-mover/src/claim_worker.rs) waits for each
Observe/Allocate/Apply child before proceeding. A replay can queue while a claim
runs, but cannot enter another claim concurrently through this service path.
A producer response timeout does not cancel the original claim; the next queued
request still waits for that processing to finish.

[`missing_retry_jobs`](../rust/crates/mover-store/src/missing_retry.rs) does
include incomplete jobs with claim rows, even without missing rows. That permits
**sequential recovery**, not overlapping allocation with the producer. The
singleton guard is lifetime custody, not evidence that unrelated directory
contents cannot change. Claim's own link/unlink relocation is in Apply, after
Allocate; it cannot explain this comparison failure for its own fresh claim.

### Why the HTTP error looks permanent

The child maps this Blocked failure to `Failure::Blocked`; its parent decoder
returns `ClaimError::Blocked("claim operation blocked")` and retains the bounded
worker diagnostic. `claim_error` maps that to `409 recording_blocked`, not a
retryable pre-effect observation failure.

Crucially, `filesystem_failure` in
[`claim_worker.rs`](../rust/crates/file-mover/src/claim_worker.rs) records a job
problem for typed I/O failures or diagnostics containing `errno=`/` kind=`.
The reported `allocate: blocked: …` has neither. It does not record that problem.
[`Database::claim_blocked`](../rust/crates/mover-store/src/lib.rs) persists only
expired `missing` deadlines; it is not called to persist this allocation error.

For a new, single-file, present-only job in this interleaving:

- acceptance is durable, but `begin_claim` has not run;
- the original is intact and no private area was allocated;
- there is no missing row or claim row to select in timer discovery;
- a fresh same-UUID request can retry allocation, but `retryable=false` tells
  the producer not to do that. No operator requirement is established by this
  error alone. Existing deadline blocks or other custody failures are distinct.

**Proposed fix, requiring review:** keep full exact source-file checks and all
fresh directory custody/type/device/mount protections; compare directory
identity independently of mutable size/mtime/link count. Do not drop all
ClaimIntent validation, adopt an existing area, or turn every Blocked error into
a retry. Consider a narrowly typed retryable pre-allocation observation-change
outcome for genuine source instability; specify whether/how to schedule it when
no missing/claim row exists. Availability/protocol issue (P2), present on main,
with no data loss demonstrated by this refusal. Production NFS remains disabled.

## The two 503s: separate queues and deadlines

| Path | Actual behavior on main | What the reply establishes |
|---|---|---|
| Producer ingress | `submission_reply`: `try_send` to one-slot claim queue; rejected enqueue is `service_busy`. A successfully queued request has a 10 s outer reply timeout. Dropped reply also maps to `handoff_pending`. | A pending reply can time out while queued/processing; it does not prove failed admission or failed storage. A lost reply does not undo custody. |
| Claim child | `request_reported` maps failed exchange/unusable receipts to OutcomeUncertain, also `handoff_pending`. `process` has an additional incomplete-handoff fallback. | Need dispatch/receipt evidence to distinguish this from the outer 10 s timeout. |
| Status/operator | One observer thread handles requests, including `status_response` using Store. HTTP waits two seconds for the reply. Timeout or dropped reply becomes `storage_unavailable`; a Store error in `status_response` uses the same code. | The code alone does not distinguish slow observation from a real Store error. Admin reads use `operator_reply`, with the same two-second bound. |
| Store | `Store::call` uses a shared 32-slot command channel and blocking send/receive, with no per-call queue deadline. One `mover-sqlite` thread owns its connection and executes closures sequentially. | Saturation or a long operation can delay claim, delivery and observer callers together, without SQLITE_BUSY. |
| SQLite | 250 ms busy timeout, WAL, synchronous FULL. | Busy timeout handles SQLite lock contention with other connections; it does not bound queue residence, fsync/checkpoint latency, CPU descheduling or callback duration. |

Sources: [`submission_reply`, `status_response`, `operator_reply` and prototype
HTTP status dispatch](../rust/crates/file-mover/src/lib.rs),
[`claim_worker::request_reported`](../rust/crates/file-mover/src/claim_worker.rs),
[`payload::exchange_deadline`](../rust/crates/file-mover/src/payload.rs), and
[`Store::start/call`, `Database::open_mode`](../rust/crates/mover-store/src/lib.rs).

Producer admission/replay checks, missing-deadline transactions, claim receipts,
four delivery lanes and operator snapshots all feed that one Store. The
sustained test's repeated replay still opens an IMMEDIATE acceptance transaction,
even when it ultimately returns the existing job. Discovery also scans retained
missing/claim IDs and loads jobs in one Store operation. No transaction spans a
supervised payload syscall in the claim path read here, but SQLite durable I/O
and accumulated queued work can still be slow. The 250 ms timeout is not a
250 ms service latency promise.

Six callers to the same Store do **not** by themselves create six SQLite writers
contending on locks. This fixture does not open its final audit Store until the
service stops, and #117 diagnostics use HTTP rather than another live Store.
An external writer/lock, an actual SQLite error, an owner-thread failure, an
observer backlog, shared-host CPU/storage stalls or reactor delay remain
possibilities; none is proven by these response codes. There is insufficient
evidence to attribute the three admin failures to the same underlying cause.

### What #115 changes, and what it does not

The comparison found **no changes to `rust/crates/mover-store`**. In particular:

- The owner thread, channel, transactions, busy timeout and callback dispatch
  remain the same. Logger calls added around caller-side error handling occur
  after the Store operation, not inside its closure/transaction.
- The existing admin change listener calls `watch::Sender::send_modify` on the
  Store thread after an operation changes SQLite's total-change count. It is
  synchronous and can contend, but is unchanged. In `admin.rs` the examined SSE
  paths copy `*changes.borrow_and_update()` into a u64 before awaiting writes;
  they do not retain those watch read guards across the network await. This
  listener is not installed for the sustained fixture without admin ingress.
- `logging::start` runs on startup's caller before service loops. With default
  OFF it returns None immediately: no writer thread, file open, logging queue,
  limiter lock or callback on the Store thread. `context` and wrapper routing
  check the unset logger and keep the original OFF prints; detail closures are
  not evaluated. Extra branches/binary layout can change scheduling, not prove
  a store contention mechanism.
- There **is** an extra startup read-only `snapshot.payload_roots()` scan for
  logging path exclusions in `check_state_compatibility`, even when the file
  is absent. It is before daemon bootstrap, not a steady-state Store callback.
  Internal claim-worker dispatch returns before normal startup/config preflight.
  It does not explain a live transaction becoming longer under sender load.

Logging references are to the inspected #115 commit, not files on main:
[`logging.rs`](https://github.com/joey-huckabee/background-file-mover/blob/6fda86f05c917138892f75fc6e6903b6b7e34e48/rust/crates/file-mover/src/logging.rs)
and [`lib.rs`](https://github.com/joey-huckabee/background-file-mover/blob/6fda86f05c917138892f75fc6e6903b6b7e34e48/rust/crates/file-mover/src/lib.rs).

## Classification and proposed next work

| Observation | Classification / real-producer impact | Proposed fix or test |
|---|---|---|
| Parent/namespace metadata changes reject an unchanged source | Main product defect; ordinary producer directory churn can trigger a nonretryable refusal and strand accepted work. | Separate directory identity from content metadata; deterministic tests below, retaining adversarial identity/source-change refusals. |
| This refusal appears to require an operator | Main response-classification/discovery gap, **not proof of a persisted block**. | Test empty claims/missing tables and same-UUID recovery, then design a narrow pre-effect retry classification if still needed after identity fix. |
| Pending handoff / unavailable status | Reply codes and timeout mechanisms exist on main. These can be legitimate transient outcomes; the underlying latency/error may be a product availability defect, but is unclassified. Real producers must keep the UUID and retry/query without assuming a 202. | Distinguish Store error codes from observer/producer deadline expiry and measure queue/operation/callback time before proposing a throughput/deadline change. Do not just increase SQLite busy timeout. |
| Rejecting any handoff_pending in this load test | Stricter than checking that pending handoff eventually clears; not alone proof of incorrect custody. It remains useful qualification failure evidence. | If authorized later, separately test bounded eventual completion and keep a strict unexpected-error diagnostic; do not whitelist a persistent failure to pass this test. No assertion change is proposed in this PR. |
| Late confirmation/sender deadline failures on main | Finite-window test margin and unpaced try_send fairness can explain them; AwaitingClaims alone cannot identify whether queuing, a slow claim or a prior refusal delayed progress. No lost job or double claim established. | Separate admission fairness/latency from timer progress; future paced admission or longer diagnostic drain must not weaken timer-progress/exact replay/commit audits. User decision required for a service fairness promise. |

## Deterministic experiments to request locally

No experiment below has been run or added by this analysis. The first can be
implemented as a focused regression without a new product pause point. Run it
on main first, then the same audited configuration on #115; use disposable
fixtures and the qualification feature, not operational state.

1. **Small mover-fs regression, no timing:** use the existing claim-test Fixture,
   write `recording/a`, accept its job, and call `observe_claim` for that file.
   Record A's full metadata; create `recording/unrelated` (not A), confirm A is
   unchanged and parent mtime differs, then call `allocate_claim` with the saved
   observation. Current expected failure: the exact Blocked text above, no
   `<job>-0` directory, original A intact. After an approved fix, allocation
   should succeed with the same source identity. Add variants changing the
   shared namespace with an unrelated owned directory, and changing an actual
   source identity/size or substituting a directory (those must still refuse).
   If timestamp resolution hides the parent change, set the fixture parent's
   mtime explicitly after creating the sibling; no race or arbitrary sleep is
   required to test the comparator.
2. **Real-service proof of HTTP classification:** follow
   `retry_admission_reads_the_clock_after_a_slow_allocation` in
   [api.rs](../rust/crates/file-mover/tests/api.rs), but use a present single
   file A, a 300 s window and a producer POST on a helper thread. Start with
   `FILE_MOVER_QUALIFICATION_PAUSE=claim_allocate` and
   `FILE_MOVER_QUALIFICATION_RENDEZVOUS=<fixture>/allocate-pause` (existing 0700
   local directory). Wait for `ready`; before creating `go`, create unrelated
   sibling B in A's parent and confirm A's metadata is unchanged. Release `go`
   promptly, avoiding the separate 10 s response deadline. Expect the exact
   stderr and 409 on current main. Verify A remains, no private area exists,
   and status has no missing block. Stop cleanly and inspect claims/missing
   read-only: neither should exist for this new file. Restart **without the
   pause environment**, resend the identical UUID and verify 202/Committed
   without reset/resume. Do not reuse `ready` for another paused Allocate:
   the rendezvous creates it with O_EXCL. Always release and join the posting
   thread before fixture cleanup, including on assertion failure.
3. **Separate the pending timeout:** in a disposable qualification fixture,
   pause the first Allocate for longer than 10 s but well below the pause's
   60 s limit. Expect producer `handoff_pending` while paused; concurrently
   query status. With Store free, status should succeed. Release, join, and
   replay the same UUID to verify eventual 202/one claim. This uses the existing
   pause; it does not demonstrate SQLite busy or explain the paired status 503.
4. **Resolve unavailable status before a storage fix:** a future test should
   hold a barrier-controlled Store-owner operation for over two seconds, queue
   a status request behind it, observe the operator timeout, then release and
   verify subsequent reads/writes recover. There is **no existing Store-owner
   qualification pause** for this in the inspected source; it needs separately
   approved test injection. A separate disposable second SQLite connection
   holding BEGIN IMMEDIATE beyond 250 ms can test SQLITE_BUSY on a runtime
   write; under WAL it need not block status reads, so it is not a reproduction
   of both responses by itself. Do not hold an operational database lock.

For the next failing local run, retain request start/end times and job IDs,
Allocate ready/write/release times (for the focused case), exact bounded worker
diagnostic, and monotonic durations for Store enqueue/start/end, commit and
callback. Distinguish the HTTP deadline branches from Store errors with SQLite
primary/extended codes or safe typed categories, not raw credential/path-bearing
error strings. Obtaining that attribution needs a separate scoped diagnostic
change; this documentation does not add production logging or a bypass.

## Checks and limits

Read the cited implementation paths, the existing slow-allocation regression,
qualification rendezvous implementation, and #115's relevant diff. Verified the
store subtree is unchanged between inspected main and #115. Documentation links
and whitespace are checked for this PR. No Rust build, test, SLES gate, repeated
load run, filesystem experiment, production state access or product fix was run.
Neither existing release limits nor the logging acceptance criteria are changed.
