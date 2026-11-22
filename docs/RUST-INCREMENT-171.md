# Increment 171: sustained sender load during missing-file retries

User authorization 2026-11-21; implementation from main `4282b74`, revised
2026-11-22 after coordinator WSL diagnostics on PR98. Test and documentation
changes only; no retry, shutdown, protocol or custody product changes.

**Status: coordinator WSL debug checks passed at `1416575`: three loaded runs
and two zero-sender baselines, using the gate SQLite flags.** The reviewer passed
the test. Earlier failed diagnostics are retained below and are not counted as
passing evidence. These local runs are not SLES qualification; SLES production
and qualification results belong to [PR98 CI](https://github.com/joey-huckabee/background-file-mover/pull/98/checks).

## Scenario and assertions

`file-mover/tests/api.rs` adds
`sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load`.
It uses the existing real-service `Fixture`, `set_config`, `post_unbusy`,
`wait_status`, `handed_off` and HTTP exchange helpers. It runs in ordinary and
qualification builds without qualification-only pauses or fault hooks.

1. Prepare all 24 one-file load inputs and confirm a separate seed job is
   `Committed` **before** submitting any late jobs. Bulk writes and waiting for
   seed delivery therefore cannot age a missing job's retry backoff.
2. Submit four jobs with four missing files each (**16 late files**), each
   returning 409 `source_file_missing`. Start load directly after those replies.
   Do not resend these bodies before status proves timer-driven handoff.
3. **Six producer threads** run unpaced for a **45-second** window. Each
   submits at most **four** unique complete one-file jobs (initial 202 and
   same-ID replay), interleaving seed and own-job replays. After the cap,
   traffic continues with seed replays and a rotation through that sender's
   accepted jobs; those own jobs need not yet be committed. There are at most
   24 new load jobs. `delivery_concurrency` is **4** for this test. Retention
   admits at most **29 jobs** (24 load + 4 late + 1 seed), avoiding incidental
   capacity refusal; the exact audited count depends on completed submissions.
4. About two seconds into load, write the late files. Count claims by the
   disappearance of their original source paths, rejecting lookup errors.
   Only the claim worker removes those names in this disposable fixture. The
   count must never decrease. While any late source files remain, fail if
   **no new claim is observed for 10 seconds**, starting the progress clock at
   the beginning of the writes and resetting it only when the count increases.
5. All late handoffs must be observed **within the 45-second load window**,
   before any resend. Their original paths must already be absent. Confirm
   all four original IDs with 202 while the window remains open and every
   sender is still running. A resend cannot conceal timer starvation by
   performing the claim itself. Once every source path has disappeared, the
   no-progress check ends; the handoff/202 completion deadline still applies.
6. Only 503 `service_busy` and 429 `rate_limited` are retried and counted. Other
   complete-job/replay replies fail, including 500, `handoff_pending`,
   `recording_blocked` and unexpected missing-file errors. Every new job has
   one successful initial request and a same-ID replay. Health repeatedly
   returns 200 within a generous five-second per-request bound; no rate target
   or nonzero back-pressure count is required.
7. Join senders, allow all accepted load, late and seed jobs to reach
   **Committed before `f.stop()`**, then perform the strict store audit. The
   commit drain has its own shared **30-second** deadline from drain start
   after load and sender joins, with no cap tied to test start. It does not
   grant a separate timeout per job.
   This avoids injecting a delivery interruption through the test's own stop.
8. The audit requires exactly the expected unique job/recording IDs, committed
   handoff, no missing files or delivery failures, and attempt 1 for each
   transfer. Every file has a completed claim, a distinct held source inode,
   one retained link and expected bytes; its sender path is absent. A final
   replay checks claim-thread liveness; captured stderr must contain no panic
   or retry-budget assertion. **The no-delivery-failure check remains strict.**

### What the progress and completion bounds mean

The [retry design](MISSING-FILE-RETRY-DESIGN.md) resumes immediately (`due = now`)
when the pass budget is exhausted and resets backoff to two seconds after
progress. Empty passes instead double backoff up to 30 seconds. Preparing load
files first and writing late files shortly after their missing replies avoids
aging an empty job through bulk setup.

The coordinator measured **32 files taking 25.04 seconds (about 25.0 seconds)
without load** at revision `2e883b2`. Each file requires roughly five supervised
child operations: first observation, stable observation and three claim steps.
At about 0.15 seconds per exchange on that host, 32 × 5 × 0.15 is about 24
seconds, consistent with that measurement. This throughput cost applies to both
timer retries and producer resends, with or without sender load. Converting a
bounded number of operations into a fixed wall-clock completion assertion does
not isolate starvation across hosts.

The revised starvation assertion instead monitors continued claims: ten seconds
without a new claim while source files remain is a failure, even if the overall
window has time left. Polling samples progress; it does not measure each worker
operation or establish a product latency guarantee. The separate **45-second
load window** provides completion slack for 16 files. The recorded revised
runs observed late handoff at **16.686 seconds without load** and **17.643 seconds
with load**. Compare baseline and loaded runs of this same scenario before
interpreting a failure. These local test bounds do not qualify NFS or arbitrary
slow I/O.

A request already started at the end of load may finish for up to ten more
seconds. Existing HTTP reads are bounded to 15 seconds, fixture shutdown has its
five-second bound, and delivery has its independent 30-second post-load drain.
The test asserts total successful runtime at most
**90 seconds**, including setup, delivery drain and audit. Scoped senders join
before teardown even on failure; an abort flag releases threads during unwind.

## Metrics and observations

Successful output starts `SUSTAINED_MISSING_RETRY` and reports actual sender
count, `load_seconds`, request count/rate, initial 202 and replay 202 counts,
separate 503/429 counts, late-handoff time, oldest missing age at write completion,
commit-drain time, health count/max latency and retained-job count. `load_seconds`
includes joining in-flight requests after the fixed window; rate uses that same
interval. Producer counts include the four in-load late confirmations, excluding
health/status, setup and final liveness requests. Polling can overestimate claim
time. Configured workload sizes are not measured results.

### Coordinator-reported diagnostics of the original test

Reported WSL debug runs used the gate SQLite flags. These were local diagnostic
modifications of the original PR98 test, not finalized SLES packs or successful
runs of the revised scenario:

| Original diagnostic variant | Late handoff observation | Result / interpretation |
|---|---|---|
| Zero senders, 60-second window | **23.6 seconds**; one job remained unhanded at 20 seconds | The original 20-second assertion failed without load. Late submissions preceded 384 load-file writes, allowing backoff to grow. This did not isolate starvation. |
| Six senders, 60-second window | All late handoffs succeeded; exact late-claim time was not supplied | Failed after stop: job 14 had `delivery_requires_review` following `Delivery 14 requires reconciliation: delivery dispatch stopped`. Stop interrupted an in-flight delivery. No loaded time is invented; record it on rerun. |

### Coordinator-reported diagnostics at `2e883b2`

After setup was moved before the missing submissions and the pre-stop commit
wait was added, WSL debug runs with gate SQLite flags still failed the absolute
25-second assertion:

| Variant with 32 late files | Observation | Result / interpretation |
|---|---|---|
| Zero senders | Late handoffs took **25.04 seconds** | Fails even without load; the fixed bound does not distinguish starvation from child-operation throughput. |
| Six senders, two runs | **Two of four late jobs** were not handed off within 25 seconds in each run | Both failed that bound. Full loaded completion times were not supplied; no starvation defect is established. |

In earlier diagnostics, the coordinator observed `Wall clock jumped +3 s` twice
under load,
possibly from WSL clock adjustment. This explanation is an inference, not a
confirmed cause. Preserve the diagnostics; do not assert on the presence or
absence of clock jumps. Timing uses monotonic clocks; the missing window remains
300 seconds and wall-clock expiry semantics are unchanged.

### Coordinator-reported results at `1416575`

These are **local WSL debug runs with the gate SQLite flags**, not SLES runs.
The coordinator reported fmt and Clippy clean. Loaded runs passed **3 of 3**
(total times **55.05 s, 53.18 s, 54.48 s**); zero-sender baselines passed **2 of 2**
(**50.26 s, 49.76 s**). The following supplied metrics describe one loaded and
one baseline run; they are not averages over the repeated runs.

Loaded:

```text
senders=6 load_seconds=49.228 requests=162582 requests_per_second=3302.634 initial_202=21 replay_202=67 service_busy=162494 rate_limited=0 late_files=16 late_claim_seconds=17.643 late_age_at_write_seconds=2.491 drain_seconds=0.417 health_checks=276 health_max_seconds=0.003 retained_jobs=26
```

Baseline:

```text
senders=0 load_seconds=45.028 requests=4 late_files=16 late_claim_seconds=16.686 late_age_at_write_seconds=2.473 drain_seconds=0.017 health_checks=379 health_max_seconds=0.001 retained_jobs=5
```

Late handoff under saturating load (**17.6 s**) was close to baseline (**16.7 s**).
There was **no observed starvation** in these runs: the single claim thread was
saturated, nearly every sender request received `service_busy`, and timer retries
still interleaved fairly. Throughput is bounded by supervised child-operation
cost. The loaded sample accepted 21 new jobs and retained 26 total, below the
29-job maximum; the baseline retained only the four late jobs and seed.

| Execution | Evidence / result |
|---|---|
| WSL baseline, 0 senders | Passed 2/2; local debug with gate SQLite flags |
| WSL load, 6 senders | Passed 3/3; local debug with gate SQLite flags |
| SLES production, debug/release | [PR98 CI checks](https://github.com/joey-huckabee/background-file-mover/pull/98/checks); separate from the WSL evidence |
| SLES qualification, debug/release | [PR98 CI checks](https://github.com/joey-huckabee/background-file-mover/pull/98/checks); production NFS remains disabled |

## Reproduce and checks

With the existing real-service executable, gate SQLite flags and environment:

```sh
# Same preparation, 16 late files and progress/completion checks; no senders.
FILE_MOVER_TEST_SUSTAINED_SENDERS=0 cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
# Default is six senders; other values besides 0 and 6 are rejected.
FILE_MOVER_TEST_SUSTAINED_SENDERS=6 cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
```

The selector affects this test only, never production configuration. The baseline
still prewrites all 24 load files before late submissions, so it removes sender
traffic without removing the setup that previously caused backoff aging.
The coordinator reported fmt and Clippy clean and the successful real-service
runs above at `1416575`. This follow-up changes documentation and clarifies only
the sender timeout message, without changing test behavior.
`cargo fmt --all -- --check`, diff/local-link and trace checks pass for this
follow-up. No new local
runtime, Clippy or SLES runs are claimed by the documentation worker.

## Decided shutdown behavior

**User decision, 2026-11-21: "keep it the way it is today".** A delivery
interrupted by service shutdown continues to be recorded as a delivery failure.
[`delivery_worker.rs`](../rust/crates/file-mover/src/delivery_worker.rs) returns
`delivery dispatch stopped` when stop interrupts a worker exchange;
[`lib.rs`](../rust/crates/file-mover/src/lib.rs) handles that error through
`delivery_failed`. This is decided, not an open product question. The load test
waits for every accepted job to commit before stopping so its strict audit
measures failures during the workload rather than its own shutdown.

## Not covered

- Shutdown-interrupted delivery behavior remains as decided above; this load
  test drains accepted deliveries and does not qualify interruption behavior.
- Loopback HTTP exercises the actual claim thread, not TLS or protected producer
  UID/connection-cap enforcement. Six unpaced senders offer contention; after
  the finite new-job cap, traffic consists of seed and own-job replays, with
  own jobs potentially still delivering.
- No NFS, systemd, physical faults, operational credentials/state, deployment,
  deletion or release qualification. All release gates remain open.
