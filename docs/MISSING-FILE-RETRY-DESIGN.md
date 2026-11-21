# Timer-driven missing-file retries

Status: approved (independent review, 2026-11-20); implemented in
[increment 163](RUST-INCREMENT-163.md), with these implementation notes:

- **Discovery:** discovery also includes partly claimed jobs whose handoff is
  not complete. A first absence's `missing` row is removed once that file is
  claimed, while later files may still wait.
- **Cancellation settlement:** settlement leaves a cancellation pending while
  the job has an unfinished, authorized claim intent. Uncertain effects keep a
  cancellation pending, as the contract already requires. Claim recovery then
  reconciles it and settlement proceeds. A settled cancellation with an
  unfinished intent can therefore only come from earlier versions, and the
  retry leaves it as is.
- **Budget:** the whole-job custody validation before new claims, which is the
  request's own check with one worker call per completed file, counts as one
  budget unit. It runs at most once per job visit.

Original proposal: Roadmap item "Add
timer-driven missing-file retries, clock-anomaly diagnostics and bounded
backoff".

## Today

- Files are claimed only while a producer request is handled, one request at
  a time on the `mover-local-claim` thread.
- A file absent at its claim records its first confirmed absence (the
  `missing` row) with a deadline: now plus the job's recorded
  `missing_retry_seconds`, 300 by default. The reply is
  `409 source_file_missing` (retryable), and later files are not attempted.
- The sender must resend the same request until every file is claimed. Past
  the deadline, the job is blocked for review (`409 recording_blocked`) until
  an audited `reset-missing`.
- Nothing re-checks on its own. A sender that resends slowly or not at all
  leaves the job waiting, then blocked, even if the file appeared in time.

## User decision (2026-11-20)

The mover claims a late file **on its own once it is stable**. The size check
is configurable, because the sender may not know sizes: an expected size is
enforced only when `check_expected_sizes` is on and the sender supplied one
(legacy submissions always check, as today).

## What changes

**Retry pass.** Retries run on the `mover-local-claim` thread, serialized with
producer claims, with `claim_active` set as for a request. The thread waits for
a request with `recv_timeout` until the next pass is due. It also checks for
due passes **after every request it handles**, so a continuous request stream
can never starve retries, and the at most one pass between two requests is
bounded (see Scheduling).

**One shared path for requests and retries.** The per-job claim logic of a
producer request moves into one function, used unchanged by both. In order:
1. cancellation check;
2. `claim_blocked` (persists an expired deadline);
3. `validate_existing` (revalidates every completed claim's custody);
4. the whole-job size policy: with `check_expected_sizes` on, a request
   without a complete expected-size map is refused (`400 invalid_submission`);
5. then each file in order, where a completed claim still gets its recorded
   size checked against the expected size, as today.

A retry adds conditions; it never skips one. If any job-level check would
refuse the request, the retry claims nothing for that job this pass. Example:
file A was claimed with checking off and B is missing; after a restart with
checking on and a mismatching size for A, the retry stops at A's mismatch
exactly as a resend would.

**Two kinds of retry work.**
- **Recovery** of an authorized claim, meaning an unfinished claim intent
  already recorded (for example Apply succeeded but its receipt was lost, or a
  crash left both names). It runs through the normal claim recovery path,
  exactly as a resend would. It is **not** gated by the deadline, a persisted
  block or a pending cancellation request: the effect was authorized before
  any of those, and an authorized, possibly applied effect must be
  reconciled, never abandoned. The only exception is a job whose cancellation
  has **settled** (`Cancelled`). Settlement already promises "no further work;
  files stay where they are", so its unfinished intent is left as is, as
  today.
- **New claims**, for files without an intent. These are gated by
  eligibility (below) and by fresh admission at authorization.

**Eligible for new claims:**
- handoff not complete (`Handoff` not `Ready202`);
- at least one recorded first absence (`missing` row);
- not blocked, and the deadline not reached;
- no cancellation requested;
- the job's source root is still the configured one.

**Per file, in order** (resuming at the job's cursor; see Scheduling):
- **Completed claim:** the size check above, nothing else.
- **Unfinished claim intent:** recovery (above), even when the job is no
  longer eligible for new claims. It is never observed as a fresh file, never
  classified as absent, and needs no settle period: its identity is already
  recorded.
- **No intent yet:**
  1. **Observe** through the supervised claim worker, as a claim's first step:
     the same `Observe` assignment, custody, expected-size rule and
     diagnostics. Observing changes nothing.
     - Absent: an absent file with no `missing` row gets its first-absence row
       (`note_missing`), so its own deadline starts as on a request; then
       continue with the next file.
     - Present: compare with the previous observation of that file, kept in
       memory: device, inode, size, mtime (seconds and nanoseconds) and link
       count. If it changed, or there is none yet, remember it and wait at
       least `missing_file_settle_seconds` (new setting, default 5, 1–300).
  2. **Stable** means the same identity in two observations at least the
     settle time apart (monotonic time). The retry then claims through the
     shared path. The claim's steps in today's code are: Observe, capacity
     check, **Allocate** (create the private area), `begin_claim` (record the
     intent), Apply, receipt. Two extra preconditions are checked twice:
     **before Allocate** (so a refused claim normally creates nothing), and
     again in the same store transaction that records the intent
     (`begin_claim`), so nothing can slip between check and authorization:
     - **identity:** the claim's own `Observe` returned that same stable
       identity; otherwise nothing is recorded, and the new identity starts a
       new settle period;
     - **fresh admission:** the job is not blocked, no cancellation has been
       requested, and the file's deadline has not passed (wall clock now).
       Otherwise nothing is recorded, and the block is persisted if it is due.

     If the `begin_claim` check refuses after Allocate already created the
     private area (the deadline or a cancellation arrived in between), nothing
     is recorded and the retry **releases that exact allocation**. A new
     claim-worker step removes the area only if it is still the allocated
     directory (device, inode, uid) and empty (plain `rmdir`), then syncs the
     namespace. If it is not empty or not that directory, it stays; the next
     claim of that file then refuses, as an allocation gap does today, and the
     job needs review. After a `reset-missing`, a later retry can allocate
     again.

     Once the intent is recorded the claim is authorized. Its effects
     (allocation, Apply, receipt) complete or are reconciled by the normal
     path even if the deadline passes meanwhile, exactly as for a request.
     Uncertain authorized effects are always reconciled, never abandoned.
- When every file is claimed, the handoff completes. Delivery proceeds
  normally, and the sender's next resend gets 202 (the existing replay path,
  which revalidates custody). A sender that never resends still has its
  recording delivered.

**Deadlines and review:**
- The deadline semantics are unchanged; a retry never extends or resets a
  deadline.
- Past the deadline, the next pass persists the block (`claim_blocked`) and
  stops retrying that job. Status shows review required without another
  request.
- `reset-missing` makes the job eligible again with its new deadline.

**Scheduling, backoff and bounded work:**
- **Budget:** a pass has a budget of **16 child operations**. Each Observe,
  each claim step and each recovery reconciliation counts as one.
- **Cursors:** jobs are visited round-robin from a job cursor, and each job
  resumes at its own file cursor. A pass that runs out of budget stops, and
  the next due pass continues exactly there. A large waiting job (up to 256
  files) therefore progresses across passes without monopolizing one, and
  every eligible job is visited within a bounded number of passes.
- **Per-job backoff:** the next pass for a job is 2 s later, doubling to at
  most 30 s while nothing changes. When a file is settling, the next pass
  comes at `first seen + settle`. A job whose cursor was cut short by the
  budget is due again immediately (next pass).
- **Interference:** at most one budgeted pass runs between two producer
  requests, so a request waits for at most 16 child operations. A producer
  request for the job resets that job's backoff.
- **State:** observations, cursors and schedules live in memory. A restart
  starts fresh settle periods, which is safe.

**Producer requests:** behavior and responses are unchanged. A request claims
a present file immediately, without a settle period and without the
fresh-admission precondition, as today. The sender asserting the file is
complete is the existing contract.

## Clock-anomaly diagnostics

Deadlines are wall-clock times (persisted, so they survive restarts). On every
wake, the claim thread compares elapsed wall time with elapsed monotonic time:
- **jump of more than 2 s** (either direction): log
  `Wall clock jumped <+/-N> s; missing-file deadlines use wall time` and count
  it, reported in the Settings page's service section as "clock jumps since
  start". A backward jump only delays expiry, and the existing test already
  proves deadlines never move. A forward jump can expire a window early; the
  log names the jobs whose deadline passed within 2 s of the jump.
- **wall time before a persisted deadline's creation** (clock set back below
  `deadline - window`): log once per job. Nothing changes the deadline.

The settle check uses monotonic time only, so a clock jump never claims a file
early.

## Status and dashboard

- Job detail `missing[]` entries gain `last_seen_at` (wall time of the last
  observation of a present file, or null) and `settling` (bool, in memory).
  The dashboard shows "Waiting for <file>: appeared, checking it is complete"
  or "Waiting for <file> until <deadline>".
- The Settings page shows `missing_file_settle_seconds` and the clock-jump
  count.

## Safety

- No new filesystem effect: claiming is the existing reviewed path, plus a
  stricter precondition (identity unchanged).
- Never claims a file whose identity changed since the stable observation.
  Never claims after the deadline, or for a cancelled or blocked job.
- A slow writer that pauses longer than the settle time between writes could
  still be claimed mid-write. That residual risk is why the settle time is
  configurable and the expected-size check exists. The operator guide says
  so.

## Proof

- **Recovery:**
  - Apply succeeded but its receipt was lost (seeded), with the original path
    now absent: the retry completes the claim through recovery. No first
    absence is recorded and no settle wait happens.
  - A two-name relocation state is reconciled the same way.
- **Size policy:**
  - with checking on and no expected-size map, the retry claims nothing;
  - partial custody across a restart: A claimed with checking off, B missing,
    restart with checking on and a mismatching size for A. The retry stops at
    A exactly as a resend would, and B is never claimed.
- **Recovery despite gates:** a seeded authorized intent (Apply done, receipt
  lost) on a job whose deadline then expired, and on a job with a cancellation
  requested but not settled. The retry completes the claim in both. On a job
  whose cancellation has settled, the intent is left as is.
- **Allocation released:** the deadline expiring between Allocate and
  `begin_claim` (qualification pause or seeded). The empty area is removed and
  no intent is recorded. After `reset-missing`, the retry claims the file
  normally. An area that gained an entry is kept, and the next claim refuses.
- **Admission races:**
  - the deadline passing between the stable observation and the claim: no
    intent is recorded, and the block is persisted;
  - a cancellation requested during observation: no intent is recorded;
  - an intent recorded just before the deadline still completes after it.
- **Scheduling:**
  - a continuous stream of producer requests (a new request at least every
    50 ms) still lets a waiting job's file be claimed within its window;
  - a waiting job with 64 missing files that then appear: no pass exceeds the
    budget, and all are claimed across passes.

- **Claim worker / store:**
  - a claim that requires a specific identity refuses a changed file without
    any effect;
  - `note_missing` for a file absent during a pass starts its own deadline
    once.
- **Real service:**
  - **Late, never resent:** a job submitted with a missing file, the file
    created afterwards, and the sender never resending. The file is claimed
    after the settle time, the job is delivered, and a later resend gets 202.
  - **Growing file:** while the file keeps growing (written every second),
    it is not claimed; once writes stop it is claimed with its final size.
  - **Expected size:** with `check_expected_sizes` on and a wrong expected
    size, the file is never claimed and the job blocks at the deadline. With
    the setting off, the file is claimed.
  - **Deadline:** the block is persisted by the timer without any request,
    and no claim happens after it.
  - **Other cases:** a cancelled job is never probed, and `reset-missing`
    resumes probing.
  - **No interference:** producer requests are answered while passes run.
- **Clock:** the wall/monotonic comparison is a pure function, unit-tested
  with forward and backward jumps.
