# Increment 152: live transfer speed (parallel delivery, step 5)

User request 2026-11-14: transfer speeds on the dashboard, updated periodically
as part of the live event push. User requirement 2026-11-15: status and metrics
must not affect copy performance (acceptance: benchmark difference within
run-to-run noise, about 2%).

## Change

- **Advisory progress channel (mover-fs `progress`).** Each delivery session
  gets its own `SOCK_SEQPACKET` socket pair; the coordinator hands the child its
  end over the control channel (one marker byte with `SCM_RIGHTS`) right after
  the instance proof. An update is one whole 24-byte message or nothing, so the
  control channel's framing is never touched. The child sends without waiting
  (`MSG_DONTWAIT`), at most once a second plus each file's final sample; a full
  or closed channel drops the update. Malformed messages are ignored.
- **Copy and verify loops.** `copy_effect_observed` / `verify_effect_observed`
  call an observer with the bytes done after each 1 MiB chunk. The delivery
  child's observer is a counter plus a clock check; nothing else runs per
  chunk, and the loops are otherwise unchanged. The plain `copy_effect` /
  `verify_effect` keep their behavior (no-op observer).
- **Coordinator board (file-mover `progress`).** In memory only: the session
  drains updates in the loop where it already waits for the step's reply
  (every 100 ms), and the board keeps, per job, the file, phase (copying or
  verifying), bytes done/total and a smoothed speed (sampled over at least
  250 ms per file and phase; a transfer without an update for 5 s shows 0 B/s,
  "waiting for I/O"). A job's entry ends with its delivery attempt.
- **Live stream.** The admin event stream sends `event: progress` with a board
  snapshot every 2 s while transfers are active, plus one empty snapshot when
  they end; nothing while idle. The keepalive heartbeat is now its own fixed
  15 s interval. Integers are JSON strings (lossless in the browser).
- **Dashboard.** Overview's "Delivering" stage shows "N transfers · X MiB/s";
  Job history and Recent jobs show, under an active job's steps, e.g.
  "Copying file 2 of 4 · 45% · 52.09 MiB/s", updated in place on each event.

The live speed covers the copy and verify loops only. Flushing to disk
(`fsync`) between them is not counted, so the live figure can be higher than
the end-to-end average (benchmark below: about 186 MiB/s live while copying
cached data, 54 MiB/s end to end).

## Performance check

`fm-demo bench --jobs 1 --files 4 --size-mb 256`, page cache dropped before
each run, one worker, same machine and session:

| Build | Runs (MiB/s) | Median |
| --- | --- | --- |
| Without progress (step 4) | 27.8, 39.7, 42.9, 45.1, 46.0 | 42.9 |
| With progress (this increment) | 44.8, 45.0, 43.6, 46.9, 42.6 | 44.8 |
| With progress, dashboard open (live events) | 48.5 | - |

The first two runs without progress were the machine warming up; the settled
runs average 44.7 (without) and 44.6 (with), a 0.2% difference, within noise.
Requirement met.

## Tests

- mover-fs: updates round-trip; malformed, out-of-range or truncated messages
  are ignored; the sender is rate-limited, always sends a file's final sample,
  returns immediately when nobody reads (100,000 reports on a full channel) and
  when the coordinator is gone.
- file-mover: board speed estimate per file and phase, smoothing, staleness
  and removal.
- Admin UI node tests: speed and summary text from lossless JSON (including
  "waiting for I/O" and no active transfers).
- The API test harness hands delivery children the progress channel exactly
  as the coordinator does.
- Visual check on the demo during a benchmark: Overview stage speed and the
  Job history line for copying and verifying.
- Local: workspace clippy; admin and file-mover unit tests; API suite (all
  pass; worker-spawn tests that failed under machine load pass alone).
