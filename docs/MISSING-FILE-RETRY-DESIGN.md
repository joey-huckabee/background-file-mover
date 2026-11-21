# Timer-driven missing-file retries (design proposal)

Status: proposal for review before implementation. Roadmap item "Add
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

**Retry pass.** The `mover-local-claim` thread wakes on a short timer between
producer requests (`recv_timeout`) and runs a retry pass. Retries are
therefore serialized with producer claims on the same thread, and
`claim_active` is set exactly as for a request.

**Eligible jobs:**
- handoff not complete (`Handoff` not `Ready202`);
- at least one recorded first absence (`missing` row);
- not blocked, and the deadline not reached;
- no cancellation requested;
- the job's source root is still the configured one.

**Each due pass on a job,** for every still-unclaimed file in order:
1. **Observe** it through the supervised claim worker, exactly as a claim's
   first step: the same `Observe` assignment, custody, expected-size rule and
   diagnostics. Observing changes nothing.
   - Absent: continue to the next file. An absent file with no `missing` row
     gets its first-absence row (`note_missing`), so its own deadline starts as
     it would on a request.
   - Present: compare with the previous observation of that file, kept in
     memory: device, inode, size, mtime (seconds and nanoseconds) and link
     count. If it changed, or there is none yet, remember this one and wait at
     least `missing_file_settle_seconds` (new setting, default 5, 1–300).
2. **Stable** means the same identity in two observations at least the settle
   time apart. The pass then claims it through the normal claim path, with one
   extra condition: the claim's own `Observe` must return **that same
   identity**. A file that changed in between is not claimed; its new identity
   starts a new settle period. Claiming, receipts, accounting, the
   expected-size check and problem recording are otherwise unchanged.
3. When every file is claimed, the handoff completes. Delivery proceeds
   normally, and the sender's next resend gets 202 (the existing replay path,
   which revalidates custody). A sender that never resends still has its
   recording delivered.

**Deadlines and review:**
- The deadline semantics are unchanged; a retry never extends or resets a
  deadline.
- When a deadline passes, the next pass persists the block (`claim_blocked`)
  and stops retrying that job. Status then shows review required without
  waiting for another request.
- `reset-missing` (the audited operator reset) makes the job eligible again
  with the new deadline.

**Backoff:**
- Per job, the time until the next pass is 2 s, doubling to at most 30 s
  while nothing changes.
- When a file was seen and is settling, the next pass comes at
  `first seen + settle`.
- A producer request for the job resets the schedule.
- At most 8 jobs are probed per pass, oldest deadline first, so one pass
  stays short and producer requests are not delayed for long.
- Probe state (observations, schedule) is in memory only. A restart starts a
  fresh settle period, which is safe.

**Producer requests:** behavior and responses are unchanged. A request that
arrives while a pass is running simply waits for it (same thread). A request
can still claim a file immediately, without a settle period, as today. The
sender asserting the file is complete is the existing contract.

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
