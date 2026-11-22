# Increment 171: sustained sender load during missing-file retries

User authorization 2026-11-21; implementation 2026-11-22 from main `4282b74`.
This is separate from the L2 traceability batch. Test code and documentation only;
no retry scheduler, protocol, custody or other product-code changes.

**Status: implemented, not executed.** This cloud checkout has no Cargo/Rust
installation. Formatting, Clippy, the real-service test and target qualification
remain pending coordinator execution. No starvation or other runtime defect has
been reproduced here, and this document does not claim that the gap is qualified.

## Scenario and assertions

`file-mover/tests/api.rs` adds
`sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load`.
It reuses the existing real-service `Fixture`, `set_config`, `post_unbusy`,
`wait_status`, `handed_off` and HTTP exchange helpers. It runs in both ordinary
and qualification builds without qualification-only pauses or fault hooks.

- Four jobs start with eight missing files each (**32 late files**), each
  returning 409 `source_file_missing`. Their bodies are never resent before
  status proves the timer finished their handoff.
- A separate one-file job is confirmed `Committed` before load. Its replays
  provide genuinely completed-job traffic throughout the test.
- **Six producer threads** send continuously, without an intentional inter-request
  delay, for a **25-second** window. Each alternates unique complete one-file
  jobs (one initial 202 and a same-ID replay) with committed-job replays.
  To bound retained work, each thread has at most 64 new jobs, **384 total**;
  after its cap it continues committed replays until the common deadline.
  Fixture retention admits exactly the maximum 389 jobs (384 + 4 late + 1 seed),
  so normal retention exhaustion is not confused with request back-pressure.
- Only 503 `service_busy` and 429 `rate_limited` are retried and counted. Other
  replies from complete-job/replay traffic fail, including 500,
  `handoff_pending`, `recording_blocked` or unexpected missing-file errors.
  The only expected missing-file replies are the four initial late submissions.
- After about two seconds of load, the test writes the late files. All four
  handoffs must be observed within **20 seconds** measured conservatively from
  the beginning of writing. Every original late path must be absent **before**
  any resend. All four resends must then return 202 with their original IDs
  **while all six sender threads are still running**. A resend therefore cannot
  conceal timer starvation by claiming a late file itself.
- `/healthz` is checked repeatedly during load and must return 200 within a
  generous five-second per-check bound. Each sender must finish at least one new job and its replay. No rate target or
  nonzero back-pressure count is required; machine speed is measured, not assumed.
- A final real replay also checks claim-thread liveness: health alone could
  remain available after a worker-thread panic. Captured service stderr must
  contain neither a panic nor the debug retry-pass budget assertion text.
- After senders join and the service stops, the original store must contain
  exactly the expected unique recording/job IDs. Every job must retain handoff,
  with no missing files or delivery failures. Every file must have a completed
  claim, a distinct retained source inode, exactly one held link and the expected
  bytes; its sender path must be absent. Any started delivery remains attempt1.

The offered-load window is fixed; an already-started job/replay may finish for
at most ten additional seconds. Existing HTTP reads are bounded to 15 seconds,
shutdown uses the fixture's five-second bound, and the test asserts a total
successful-run duration below **60 seconds**, including setup and store checks.
Scoped sender threads are joined before fixture teardown, including on failure;
an abort flag releases threads if startup or monitoring unwinds.

## Metrics and observed results

A successful run prints one `SUSTAINED_MISSING_RETRY` line with sender count,
measured `load_seconds`, producer reply count and requests/second, initial 202 and
replay 202 counts, separate 503/429 counts, maximum late-handoff observation time,
health count/max latency and retained-job count. `load_seconds` includes joining
in-flight requests after the fixed window; rate uses that same measured interval.
Producer counts include the four in-load late confirmations and exclude health,
status, setup and final liveness requests. Observations may overestimate the
actual claim time by status-polling latency.

| Execution | Throughput and back-pressure | Late-claim time / total runtime | Result |
|---|---|---|---|
| Local WSL, gate environment | Not observed | Not observed | Pending coordinator run |
| SLES production, debug/release | Not observed | Not observed | Pending |
| SLES qualification, debug/release | Not observed | Not observed | Pending |

Record the actual emitted numbers and exact source/artifact provenance here
when those runs finish; none is inferred from the configured workload. An
unexpected response, lost/duplicate job, late claim or budget panic must be
preserved as failing evidence, not addressed by relaxing the test. A product
fix requires a separate coordinator/user decision.

## Checks and limits

- Source/diff review checks that only the new module was inserted in `api.rs`;
  existing tests/helpers and product code are unchanged.
- Attempted from `rust/`: `cargo fmt --all` (also the `--check` form),
  `cargo clippy -p file-mover --tests -- -D warnings`, and the focused test below.
  All three exit 127 (`cargo: command not found`); none compiled or ran the test.
- Coordinator invocation (with the existing gate-provided executable and
  environment, or through the required full gates):

  ```sh
  cargo test -p file-mover --test api sustained_sender_load::timer_retries_do_not_starve_under_sustained_sender_load -- --exact --nocapture
  ```

This exercises the real claim thread through the existing loopback HTTP fixture,
not TLS, protected producer UID/connection-cap enforcement or a production sender.
Six unpaced senders offer sustained contention; the finite new-job cap can leave
only committed replays for the rest of the window. There is no claim that a
particular queue occupancy, throughput or saturation level has been measured
before execution. Delivery need not drain all queued jobs before stop: the audit
requires durable handoff/claims for every accepted job, not completion of every
background delivery. No NFS, systemd, physical fault, operational state,
credential, deployment, deletion or release qualification is added. All release
gates remain open.
