# Increment 156: final benchmark and recommended settings (parallel delivery, step 9)

Step 9, the last step of the parallel delivery plan (increment 148): benchmark
the finished set (steps 1-8 on main at a6f1894) and recommend settings. No
service change.

## Change

- **Operator guide:** new section "Delivery speed settings" with the three
  settings (`delivery_concurrency`, `delivery_file_concurrency`,
  `copy_buffer_bytes`), their ranges and defaults, a ready-to-paste table of
  buffer sizes, and the memory rule (up to jobs x files x buffer at once).
- **`fm-demo bench`:** stops with a clear message when the service refuses
  submissions for capacity instead of retrying until its timeout, with separate
  guidance: `retention_capacity` (the configured job/byte accounting limits:
  clearing history frees slots but deletes no files) versus
  `source_space_unavailable` (physical source free space low or not
  observable: free disk space; `fm-demo setup` removes all demo data); a busy status reply (503 from the
  bounded status queue under load) is polled again instead of failing the run.
- **Demo README:** each benchmark keeps about twice its size on the WSL disk
  and four jobs of history; `fm-demo setup` starts over.

## Results (WSL demo, local ext4 virtual disk)

`fm-demo bench --jobs 4 --files 4 --size-mb 256` (4 GiB per run), page cache
dropped before each run, 1 MiB buffer, three runs per setting:

| Jobs at once | Files per job at once | Runs (MiB/s) | Median | vs. 1 x 1 |
| --- | --- | --- | --- | --- |
| 1 | 1 | 40.6, 39.9, 38.5 | 39.9 | - |
| 4 | 1 | 44.0, 50.4, 52.3 | 50.4 | +26% |
| 1 | 4 | 67.3, 46.9, 57.9 | 57.9 | +45% |
| 4 | 4 | 69.0, 56.8, 60.3 | 60.3 | +51% |

Two first-round runs (4 x 1, 4 x 4) were lost to the benchmark treating a busy
status reply as a failure (fixed above) and re-run. Run-to-run spread on this
shared host is large (up to about 20 MiB/s), so medians are the comparison.
Earlier measurements: NFS destination, 4 jobs x 256 MiB, 39.8 MiB/s at one
worker and 58.1 MiB/s at four (increment 153); copy buffer sizes 256 KiB to
4 MiB within noise, 16 MiB slower (increment 155); progress reporting without
measurable cost (increment 152).

### Disk exhaustion observed during the benchmarks

Repeated runs filled the WSL disk (the demo keeps every delivered and held
copy). Observed: copies failing with `ENOSPC` were scheduled as destination
capacity backoff (their initial, retryable classification; partial staging
writes may remain, and by policy the third persisted delivery failure requires
review). Source custody and existing delivered output were preserved. Once
SQLite itself could not write, the service stopped; restart and demo reset
were refused because the worker lifetime record could not be written or
verified ("worker lifetime evidence unavailable"). After confirming no mover
process remained, the stale lifetime records were moved aside (not deleted)
and the disposable demo state was reset.

## Recommendation

Production defaults stay 1 / 1 / 1 MiB (user decision, increment 148): with
these, delivery behaves exactly as before parallel delivery. For a site that
wants the speed-up, a starting point is:

```json
{
  "delivery_concurrency": 2,
  "delivery_file_concurrency": 4,
  "copy_buffer_bytes": 1048576
}
```

- `delivery_file_concurrency` gives the largest single gain for jobs with
  several large files (median +45% here); it also applies when only one job is
  waiting.
- `delivery_concurrency` helps when several jobs queue at once; 2 keeps the
  disk less contended for new submissions (takeover of new files slowed from
  about 14 s to 30-50 s at four jobs here) while still overlapping jobs.
- Keep `copy_buffer_bytes` at 1 MiB unless a site measurement shows a gain.
- Measure on the site's own storage before keeping a change; NFS results are
  expected to gain more than this single local disk.

Parallel delivery on NFS is qualified only in the local lab (increment 153);
production enablement is a separate operational decision.
