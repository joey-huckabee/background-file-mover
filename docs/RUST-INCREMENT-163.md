# Increment 163: timer-driven missing-file retries

User request 2026-11-20: start the missing-file retries (roadmap: "timer-driven
missing-file retries, clock-anomaly diagnostics and bounded backoff").
User decision the same day: claim a late file on its own **once it is stable**,
with the size check configurable because the sender may not know sizes (the
existing `check_expected_sizes`). Implements the reviewed
[design](MISSING-FILE-RETRY-DESIGN.md).

## Change

- **Setting:** `missing_file_settle_seconds` (default 5, 1–300). The Settings
  page shows it.
- **Claim thread** (`lib.rs`):
  - It waits for producer requests with `recv_timeout`, and runs a retry pass
    when one is due, on timeout and after every request. Retries are
    serialized with producer claims, with `claim_active` set.
  - The request's whole-job checks moved into `claim_gates`, used unchanged by
    both requests and retries: cancellation, block, custody validation and the
    complete size-map policy.
  - A resend restarts its job's backoff.
- **Scheduler** (`missing_retry.rs`):
  - **Discovery:** jobs with a recorded first absence, an unfinished claim
    intent, or a partial claim, whose handoff is not complete.
  - **Fairness:** round-robin job and file cursors, resumable across passes.
  - **Budget:** 16 child operations per pass; a claim counts as 3, and the
    whole-job validation as 1.
  - **Backoff:** 2 s doubling to 30 s; a settling file is due at
    first-seen + settle; a reviewed reset (new missing-review epoch) is due at
    once.
  - **Recovery** of unfinished intents runs before the gates and is not gated
    by deadline, block or a pending cancellation. Only a settled cancellation
    leaves it as is.
  - **New claims:** absent files get their first-absence row. A present file
    is claimed only after two identical observations (device, inode, owner,
    size, mtime, links) at least the settle time apart, by monotonic time.
- **Claim worker** (`claim_worker.rs`):
  - `observe` (observe-only).
  - `claim_stable`: the claim's own Observe must return the stable identity.
    Fresh admission is checked before Allocate (`claim_admissible`) and again
    inside the transaction that records the intent (`begin_claim_admitted`).
    If refused after Allocate, a new `release` step removes exactly that empty
    area (`mover_fs::release_claim_allocation`, identity-checked `rmdir`);
    otherwise it is kept and later claims refuse as an allocation gap does.
- **Store:**
  - `missing_retry_jobs` (with epochs), `claim_admissible` and
    `begin_claim_admitted`.
  - Clock-jump lookups.
  - **Cancellation settlement now waits** while a job has an unfinished claim
    intent (uncertain effect, per the contract).
- **Clock:** wall/monotonic drift over 2 s is logged with the affected jobs and
  counted (`clock_jumps_since_start` on the Settings page).
- **Status and dashboard:**
  - Missing entries gain `last_seen_at` and `settling`.
  - The activity text reads "Waiting for … until …", "has appeared; the mover
    is checking it is complete", or "did not arrive by …; needs review".
  - The contract's `MissingStatus` gains the two optional fields.
- **Docs:** operator guide "Missing files: automatic retries" (and the
  reset-missing text), roadmap, design status and notes.

## Tests

- **Real service:**
  - `late_missing_files_are_claimed_once_stable_without_a_resend`:
    - a late file written in chunks every 300 ms is not claimed while it
      grows;
    - once stable it is claimed without any resend, delivered with its final
      bytes, and a later resend gets 202;
    - another job's replays are served throughout.
  - `retries_respect_deadlines_cancellation_and_reset`:
    - the deadline block is persisted by the timer with no request, and a
      file arriving afterwards is not claimed;
    - a job with a cancellation requested is not claimed;
    - after `reset-missing` the timer claims the file, and a resend gets 202.
  - `retries_recover_authorized_claims_despite_deadline_and_cancellation`:
    seeded lost receipts (file already moved, intent unfinished).
    - On an expired job, the claim is completed and the handoff finishes.
    - On a cancel-requested job, settlement waits, the claim is completed, and
      then the job settles Cancelled with the file in custody.
  - `retries_keep_the_whole_job_size_policy`, with checking on and none of the
    late files claimed:
    - no size map;
    - a wrong recorded size for the already-claimed file (accepted while
      checking was off);
    - a wrong expected size for the late file.
  - `many_waiting_files_are_claimed_across_bounded_passes`: 64 files appear
    and are all claimed across budgeted passes.
- **mover-fs**
  (`retry_admission_is_atomic_with_the_intent_and_unrecorded_allocations_are_released`):
  - a deadline passing between Allocate and recording is refused atomically:
    nothing is recorded and the block is persisted;
  - the empty allocation is released, and a repeat is a no-op;
  - after reset, the epoch moves and a fresh allocation is admitted and
    recorded;
  - an allocation that gained an entry is kept;
  - a cancellation refuses new authorization, and settlement waits for the
    unfinished intent, then proceeds.
- **Unit:** clock-jump detection (forward, backward, within 2 s) and
  scheduling (due, wait, a resend resets backoff). Dashboard node test for the
  missing-file wording.
- Contract checker, fmt and workspace clippy.

## Not covered

- No test drives a real race between Allocate and `begin_claim` in the
  running service. The store and mover-fs test covers the atomic refusal and
  the release on real files.
- Continuous producer traffic is exercised with one other job's replays every
  50 ms, not a saturating load.
- A writer pausing longer than the settle time can still be claimed mid-write
  (documented residual risk; mitigated by the settle setting and expected
  sizes).
