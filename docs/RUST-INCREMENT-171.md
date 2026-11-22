# Increment 171: sustained sender load during missing-file retries

User authorization 2026-11-21; implementation from main `4282b74`, revised
2026-11-22 after coordinator WSL diagnostics on PR98. Test and documentation
changes only; no retry, shutdown, protocol or custody product changes.

**Status: revised test awaiting coordinator rerun.** Earlier revisions failed
locally for the reasons below. None of those runs or diagnostic variants are
passing qualification evidence. SLES production/qualification results remain
pending; no starvation defect has been established by those failures.

## Scenario and assertions

`file-mover/tests/api.rs` adds
`sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load`.
It uses the existing real-service `Fixture`, `set_config`, `post_unbusy`,
`wait_status`, `handed_off` and HTTP exchange helpers. It runs in ordinary and
qualification builds without qualification-only pauses or fault hooks.

1. Prepare all 384 one-file load inputs and confirm a separate seed job is
   `Committed` **before** submitting any late jobs. Bulk writes and waiting for
   seed delivery therefore cannot age a missing job's retry backoff.
2. Submit four jobs with four missing files each (**16 late files**), each
   returning 409 `source_file_missing`. Start load directly after those replies.
   Do not resend these bodies before status proves timer-driven handoff.
3. **Six producer threads** run unpaced for a **45-second** window. Each
   alternates a unique complete one-file job (initial 202 and same-ID replay)
   with replays of the already-committed seed. Each sender has at most 64 new
   jobs, 384 total; after its cap it continues seed replays to the deadline.
   Retention admits the maximum 389 jobs, avoiding incidental capacity refusal.
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
   commit drain has one shared deadline: 20 seconds from drain start, capped
   at 60 seconds from test start. It does not grant a separate timeout per job.
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
load window** provides completion slack for 16 files, estimated at **12–13
seconds** from that host's baseline; the estimate is not a measured result for
the revised test. Compare baseline and loaded runs of this same scenario before
interpreting a failure. These local test bounds do not qualify NFS or arbitrary
slow I/O.

A request already started at the end of load may finish for up to ten more
seconds. Existing HTTP reads are bounded to 15 seconds, fixture shutdown has its
five-second bound, and the test asserts total successful runtime at most
**70 seconds**, including setup, delivery drain and audit. Scoped senders join
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

| Revised execution | Throughput / back-pressure | Baseline or loaded late-claim time | Result |
|---|---|---|---|
| WSL baseline, 0 senders | Pending | Pending | Awaiting rerun |
| WSL load, 6 senders | Pending | Pending | Awaiting rerun |
| SLES production, debug/release | Pending | Pending | Not qualified |
| SLES qualification, debug/release | Pending | Pending | Not qualified |

## Reproduce and checks

With the existing real-service executable, gate SQLite flags and environment:

```sh
# Same preparation, 16 late files and progress/completion checks; no senders.
FILE_MOVER_TEST_SUSTAINED_SENDERS=0 cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
# Default is six senders; other values besides 0 and 6 are rejected.
FILE_MOVER_TEST_SUSTAINED_SENDERS=6 cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
```

The selector affects this test only, never production configuration. The baseline
still prewrites all 384 load files before late submissions, so it removes sender
traffic without removing the setup that previously caused backoff aging.
The coordinator reported fmt and workspace Clippy clean at `2e883b2`; its
baseline and loaded runtime failures are recorded above. On this revision,
`cargo fmt --all` was applied and
`cargo fmt --all -- --check` passes, using the repository-pinned Rust1.99.0
Cargo/rustfmt and its compiler library from official distribution components,
verified against their manifest SHA-256 hashes. This installs host tools only,
without changing workspace dependencies. Diff/local-link and source-preservation
checks pass. Revised Clippy/runtime/SLES results await the coordinator rerun; no
new baseline or loaded runtime is claimed here.

## Not covered

- **Open user question:** shutdown currently can charge a delivery failure when
  `delivery dispatch stopped` falls through to `delivery_failed` in `lib.rs`.
  The coordinator is taking that behavior to the user. This test now waits for
  commitment before stopping; it does not fix, approve or qualify shutdown
  interruption behavior. A separate product decision/change is required.
- Loopback HTTP exercises the actual claim thread, not TLS or protected producer
  UID/connection-cap enforcement. Six unpaced senders offer contention; after
  the finite new-job cap, traffic can consist only of committed replays.
- No NFS, systemd, physical faults, operational credentials/state, deployment,
  deletion or release qualification. All release gates remain open.
