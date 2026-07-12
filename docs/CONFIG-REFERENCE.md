# Configuration Reference

Configuration is a single INI file (default `/etc/file-mover/file-mover.ini`), loaded
once at startup with the standard-library `configparser` (L2-CFG-001). The fully
commented reference copy lives at `config/file-mover.ini`.

The loader (Milestone 2) is strict: it **rejects unknown sections and options**
(L2-CFG-002), rejects missing required values (L2-CFG-003), validates numeric ranges and
cross-field constraints before the service starts (L2-CFG-004), and reports *all* issues
together (L2-CFG-008) — each naming the section, option, offending value, and reason.
A misspelled key fails loudly rather than silently disabling a feature.

## `[service]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `state_directory` | path | `/var/lib/file-mover` | Durable state root; must not sit on a source tree. |
| `database_path` | path | `…/jobs.db` | Authoritative SQLite job/file state. |
| `manifest_directory` | path | `…/manifests` | Human-readable per-job manifests. |
| `socket_path` | path | `/run/file-mover/control.sock` | Control socket (recreated each boot). |
| `shutdown_timeout_seconds` | int > 0 | `60` | Grace period for in-flight work to checkpoint. |
| `poll_interval_seconds` | float > 0 | `2` | Transfer scheduler poll interval. |

## `[control]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `socket_mode` | octal | `0660` | Owner+group read/write only. |
| `max_concurrent_requests` | int ≥ 1 | `8` | Control thread pool size (separate from transfer workers). |
| `request_timeout_seconds` | int > 0 | `30` | Per-request timeout. |
| `maximum_message_bytes` | int > 0 | `1048576` | Oversized messages rejected before allocation. |

## `[paths]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `allowed_source_roots` | path list | `/recordings` | Absolute; must not overlap destinations. |
| `allowed_destination_roots` | path list | `/processing` | Absolute; on a different filesystem than sources. |
| `claim_directory_name` | name | `.swit-moving` | Single path component; SWIT-prefixed. |
| `temporary_file_prefix` | string | `.swit-partial-` | Non-empty; no path separators. |
| `reject_symbolic_links` | bool | `true` | Recommended default; reject symlinks during inventory/claim. |

## `[transfer]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `max_concurrent_jobs` | int ≥ 1 | `1` | One active job; tune after measuring load. |
| `max_concurrent_files` | int ≥ 1 | `2` | Files copied concurrently within a job. |
| `copy_buffer_size_bytes` | int ≥ 65536 | `8388608` | Bounded copy buffer (64 KiB floor, 8 MiB default). |
| `max_bytes_per_second` | int ≥ 0 | `0` | Aggregate copy-throughput ceiling in bytes/sec across all concurrent copies (0 = unlimited). A non-zero limit forces the buffered copy path (`copy_file_range` cannot be paced). Adjustable at runtime with `file-mover throttle`; current value shown by `file-mover health`. |
| `retry_limit` | int ≥ 0 | `10` | Max automatic attempts (0 disables retries). |
| `retry_initial_delay_seconds` | float > 0 | `10` | Backoff floor. |
| `retry_max_delay_seconds` | float | `900` | Must be ≥ `retry_initial_delay_seconds`. |
| `use_kernel_copy` | bool | `true` | Attempt kernel-assisted copy (`copy_file_range`) with a safe buffered fallback; set `false` to always use the buffered loop. |
| `resume_partial_files` | bool | `true` | Resume an interrupted copy from its fsynced `.swit-partial-` offset instead of restarting from byte zero; `false` restarts interrupted files and drops stale partials during recovery. See `docs/ARCHITECTURE.md` § *Partial-file resume*. |

## `[integrity]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `enabled` | bool | `true` | Master switch. |
| `mode` | enum | `source-and-destination-hash` | `metadata` \| `source-hash` \| `source-and-destination-hash`. |
| `algorithm` | enum | `sha256` | `sha256` \| `sha512` \| `blake2b` (all via `hashlib`). |

Even with hashing disabled, identity and size are still verified before source deletion —
"metadata" mode verifies, it does not skip verification.

## `[stability]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `enabled` | bool | `true` | Defensive check that a source is not still being written. |
| `poll_count` | int ≥ 2 | `2` | Number of metadata observations. |
| `poll_interval_seconds` | float > 0 | `5` | Seconds between observations. |

Stability validation is defensive only; it does **not** replace the orchestration
system's responsibility to submit only completed recordings.

## `[logging]`

| Option | Type | Default | Notes |
|--------|------|---------|-------|
| `level` | enum | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. |
| `log_to_journal` | bool | `true` | Emit to the systemd journal (stderr). |
| `log_to_file` | bool | `false` | Emit to a log file. |
