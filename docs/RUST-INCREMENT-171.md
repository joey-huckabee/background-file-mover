# Increment 171: sustained sender load during missing-file retries

User authorization 2026-11-21; implementation from main `4282b74`, revised
2026-11-22 after coordinator WSL diagnostics on PR98. Test and documentation
changes only; no retry, shutdown, protocol or custody product changes.

**Status: revised test awaiting coordinator rerun.** The original test failed
locally for the reasons below. Neither that run nor the diagnostic variants are
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
2. Submit four jobs with eight missing files each (**32 late files**), each
   returning 409 `source_file_missing`. Start load directly after those replies.
   Do not resend these bodies before status proves timer-driven handoff.
3. **Six producer threads** run unpaced for a **30-second** window. Each
   alternates a unique complete one-file job (initial 202 and same-ID replay)
   with replays of the already-committed seed. Each sender has at most 64 new
   jobs, 384 total; after its cap it continues seed replays to the deadline.
   Retention admits the maximum 389 jobs, avoiding incidental capacity refusal.
4. About two seconds into load, write the late files. Check that the oldest
   first-missing reply is at most **6 seconds old after all writes finish**.
   An older fixture fails explicitly as setup aging, not evidence of starvation.
5. All late handoffs must be observed within **25 seconds** of beginning those
   writes, before any resend. Their original paths must already be absent.
   Confirm all four original IDs with 202 while the load window remains open and
   every sender is still running. A resend cannot conceal timer starvation by
   performing the claim itself.
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

### What the late bound means

The [retry design](MISSING-FILE-RETRY-DESIGN.md) has two-second discovery and
initial backoff, with empty passes doubling backoff up to 30 seconds. With the
freshness guard above, reserve 2 seconds for discovery, up to 8 seconds for early
empty-pass backoff, 1 second for settling, and 14 seconds for the small local
fixture's budgeted child operations, packing and producer/I/O interference:
**2 + 8 + 1 + 14 = 25 seconds**.

For scale, 32 first observations plus 32 stable observations and three claim
operations per file, with up to 32 completed-claim validations, is about 192 child
operations, or 12 full 16-operation pass equivalents. Packing, additional validation
cycles and request interference can require more passes; the 14-second allowance
is regression-test slack, not a conversion of the operation budget into a
product wall-time guarantee. The bound is meaningful only for this fresh local
fixture; compare the same zero-sender baseline before interpreting a load-only
failure as starvation. It does not bound arbitrary old backoff, NFS or slow I/O.

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

The coordinator also observed `Wall clock jumped +3 s` twice under load,
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
# Same preparation, late jobs, freshness guard and deadline; no load senders.
FILE_MOVER_TEST_SUSTAINED_SENDERS=0 cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
# Default is six senders; other values besides 0 and 6 are rejected.
FILE_MOVER_TEST_SUSTAINED_SENDERS=6 cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
```

The selector affects this test only, never production configuration. The baseline
still prewrites all 384 load files before late submissions, so it removes sender
traffic without removing the setup that previously caused backoff aging.
The coordinator reported workspace Clippy clean on the original test and a
required rustfmt diff. On this revision, `cargo fmt --all` was applied and
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
