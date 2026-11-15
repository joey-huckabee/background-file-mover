# Increment 155: configurable copy buffer (parallel delivery, step 8)

Step 8 of the parallel delivery plan (increment 148); implements L2-COPY-002
("a configurable and validated copy buffer size").

## Change

- **`copy_buffer_bytes`** (configuration; default 1 MiB): the buffer of the
  copy loop and of the verification re-read. Valid: 64 KiB to 64 MiB in whole
  4 KiB pages (`mover_fs::valid_copy_buffer`). Startup refuses anything else.
- The coordinator passes it to each delivery session in Open
  (`copy_buffer_bytes`); the child validates it again and refuses the Open
  otherwise (absent means the default, so the existing protocol is unchanged).
  In-process copies (`copy_effect`, `verify_effect`) use the default.
- The loops are otherwise unchanged: same steps per chunk, one allocation per
  copy or verification.
- **Settings page.** The Transfers card now shows "Jobs delivered at once",
  "Files per job at once" and "Copy buffer". (Increments 151 and 154 added
  `delivery_concurrency` and `delivery_file_concurrency` to the settings API
  only; the page did not show them until now.)

## Measurements (WSL demo, local ext4 virtual disk)

`fm-demo bench --jobs 1 --files 4 --size-mb 256`, one worker, one file at a
time, page cache dropped before each run:

| Buffer | Runs (MiB/s) |
| --- | --- |
| 256 KiB | 41.8, 43.9 |
| 1 MiB (default) | 43.3, 44.2 |
| 4 MiB | 44.1, 42.0 |
| 16 MiB | 34.9, 40.5 |

No measurable gain from a larger buffer on a local disk; 16 MiB is slower.
The default stays 1 MiB. Over NFS the buffer interacts with the mount's
`rsize`/`wsize` (commonly up to 1 MiB), so it is a per-site tuning knob.

## Tests

- Config: `copy_buffer_bytes` 0, 60 KiB, 64 KiB + 512 and 64 MiB + 4 KiB are
  refused; 64 KiB, 1 MiB and 64 MiB are accepted. `delivery_file_concurrency`
  bounds are covered too.
- Delivery session: Open with 64 KiB or no buffer is accepted; 1000 bytes and
  64 MiB + 4 KiB are refused and end the session.
- API: a 3 MiB + 12,345 byte file (a partial last chunk) delivered with a
  64 KiB buffer is byte-for-byte identical.
- Local: workspace clippy; the new and related API tests; mover-fs transfer
  tests.
