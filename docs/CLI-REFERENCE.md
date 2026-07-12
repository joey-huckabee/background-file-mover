# CLI Reference

`file-mover` is a thin, short-lived client of the durable background service. It parses
arguments, sends one framed request to the service over the control socket, renders the
result, and exits with a documented code. It never performs transfers itself.

> **Milestone 1 status:** the parser surface below is complete and `--help` / `--version`
> work today. Every subcommand currently reports "not yet implemented" and returns
> `OPERATION_FAILED` (1); behavior is filled in across Milestones 2–7. See
> `docs/ROADMAP.md`.

## Synopsis

```
file-mover [global options] <command> [command options]
```

## Global options

Accepted before or (where applicable) after the subcommand:

| Option | Default | Meaning |
|--------|---------|---------|
| `--config PATH` | `/etc/file-mover/file-mover.ini` | Configuration file to load. |
| `-v`, `-vv` | WARNING | Verbosity: `-v` = INFO, `-vv` = DEBUG. |
| `--log-level LEVEL` | (from `-v`) | Explicit `DEBUG`/`INFO`/`WARNING`/`ERROR`; overrides `-v`. |
| `--output {human,json}` | `human` | Result rendering. JSON goes to stdout with no log noise. |
| `--version` | | Print version and exit 0. |
| `-h`, `--help` | | Print help and exit 0. |

Machine output is written to **stdout**; diagnostics and logs to **stderr**
(L2-CLI-005/006).

## Commands

| Command | Purpose |
|---------|---------|
| `submit` | Submit a completed recording set (directory or explicit file list). |
| `status <job_id>` | Show one job. |
| `list [--state S]` | List jobs, optionally filtered by state (default `active`). |
| `retry <job_id>` | Retry a retained failed job. |
| `stats` | Show durable service statistics. |
| `throttle <bytes-per-second>` | Set the live copy-throughput limit (`0` = unlimited). |
| `pause <job_id>` | Pause a queued or in-flight job (stops it at a safe point). |
| `resume <job_id>` | Resume a paused job (returns it to the queue). |
| `cancel <job_id>` | Cancel a job; retains the source, discards any partial. |
| `doctor` | Validate configuration and filesystem access. |
| `recover` | Reconcile durable state after an interruption. |
| `service run` | Run the service in the foreground (systemd entry point). |

### `submit`

```
file-mover submit --scenario-id ID (--source DIR | --file-list FILE) --destination DIR
```

`--source` and `--file-list` are mutually exclusive and one is required. `submit`
returns success **only after** the job and its complete claimed file inventory are
durably recorded (L2-CLI-008); it does **not** wait for hashing, copying, verification,
or source deletion (L2-CLI-009). Submission is idempotent by client-generated
`request_id`: re-submitting the same request returns the original job.

Example orchestration call:

```python
result = subprocess.run(
    ["/usr/bin/file-mover", "submit",
     "--scenario-id", scenario_id,
     "--source", str(source),
     "--destination", str(destination)],
    check=False, capture_output=True, text=True, timeout=30,
)
if result.returncode != 0:
    raise RuntimeError(f"mover rejected {scenario_id}: {result.stderr.strip()}")
```

### `throttle`

```
file-mover throttle BYTES_PER_SECOND
```

Sets the aggregate copy-throughput ceiling on the running service, live, without a
restart — the new limit applies to the next copy-loop write, including copies already in
flight (L2-BWL-002). `BYTES_PER_SECOND` accepts a bare byte count or a suffixed value:
`K`/`M`/`G` are powers of 1000 and `Ki`/`Mi`/`Gi` are powers of 1024 (an optional trailing
`B` is allowed), so `50MB`, `1GiB`, and `52428800` are all valid. `0` removes the limit
(unlimited). The applied value is echoed back and is also visible as `max_bytes_per_second`
in `file-mover health`.

```
$ file-mover throttle 50MB
throughput limit set to 50000000 bytes/sec
$ file-mover throttle 0
throughput limit removed (unlimited)
```

A non-zero limit forces the buffered copy path (kernel-assisted `copy_file_range` cannot be
paced from userspace), so throttling trades the kernel-copy fast path for controllable
throughput — see `docs/ARCHITECTURE.md` § *Bandwidth limiting*. Note that a live `throttle`
change does **not** slow a file already being kernel-copied; it applies from the next file.
For how throttling, resume, and pause/cancel combine, see `docs/FEATURE-INTERACTIONS.md`.

### `pause` / `resume` / `cancel`

```
file-mover pause  JOB_ID
file-mover resume JOB_ID
file-mover cancel JOB_ID
```

Operator lifecycle control over a durable job (L2-LIF-001..005):

- **`pause`** stops a job. A queued or retry-waiting job is transitioned to `paused`
  immediately; an in-flight copy is signalled and stops at the next buffer boundary
  (cooperative — there is no OS primitive to pause a file copy), leaving an fsynced
  partial. Pausing an already-paused job is a no-op.
- **`resume`** returns a `paused` job to the runnable queue; the next scheduler tick
  continues it from its partial (see `docs/ARCHITECTURE.md` § *Partial-file resume*).
- **`cancel`** ends a job at the terminal `cancelled_retained` state. The claimed **source
  is always retained** — cancel never deletes source data — and only the incomplete
  temporary destination is discarded. An in-flight copy is cancelled cooperatively.

Each command prints the accepted job and its resulting state, or a typed rejection
(`NOT_FOUND` → `JOB_NOT_FOUND`; an invalid state → `OPERATION_FAILED`). With `--output
json` the full response object is emitted on stdout.

```
$ file-mover pause 4f2a…
pause accepted for 4f2a… (state: paused)
$ file-mover cancel 4f2a…
cancel accepted for 4f2a… (state: cancelled_retained)
```

`pause`/`resume` rely on `[transfer] resume_partial_files = true` (the default): pausing keeps
the fsynced partial and resume continues it. With resume disabled, a resumed job cannot
continue its partial cleanly — see `docs/FEATURE-INTERACTIONS.md`.

### `doctor`

```
file-mover doctor [--config PATH] [--output human|json]
```

Validates the configuration, reports **advisories** for consequential-but-valid option
combinations, and **verifies the runtime environment** — the capabilities the service
depends on. Each capability is reported as `pass` / `warn` / `fail`:

- **Required** (`fail` if missing): `af-unix-socket`, `fcntl-lock`, `sqlite-wal`,
  `hash-algorithm[<configured>]`, `python-version` (≥ 3.10), `posix-signals`.
- **Optional** (`warn` if missing, never a failure): `o-nofollow`, and `kernel-copy` (only
  when `[transfer] use_kernel_copy` is enabled).

A missing **required** capability returns `ENVIRONMENT_UNSUPPORTED` (exit 8), so a
deployment can gate on it before enabling the service (see `docs/DEPLOYMENT.md`). Human
output lists each check on stdout with `configuration valid`; advisories and any
"environment unsupported" summary go to stderr. `--output json` emits one object:

```
$ file-mover doctor --config /etc/file-mover/file-mover.ini --output json
{"status": "ok", "message": "configuration valid", "advisories": [],
 "environment": [{"name": "af-unix-socket", "requirement": "required",
                  "status": "pass", "detail": "socket.AF_UNIX available"}, …]}
```

`status` is `ok`, or `environment_unsupported` when a required capability failed.

## Exit codes

Stable and machine-consumable (`file_mover.jobs.models.ExitCode`):

| Code | Name | Meaning |
|------|------|---------|
| 0 | `SUCCESS` | Command succeeded. |
| 1 | `OPERATION_FAILED` | Command ran but the operation failed. |
| 2 | `INVALID_ARGUMENT` | Bad arguments / missing subcommand (argparse). |
| 3 | `CONFIGURATION_ERROR` | Configuration invalid or unreadable. |
| 4 | `SERVICE_UNAVAILABLE` | No service listening; the CLI starts no transfer of its own. |
| 5 | `JOB_REJECTED` | Submission rejected by policy or validation. |
| 6 | `JOB_NOT_FOUND` | No such job id. |
| 7 | `PARTIAL_SUCCESS` | Some but not all items succeeded. |
| 8 | `ENVIRONMENT_UNSUPPORTED` | `doctor`: a required runtime capability is missing (deploy gate). |
| 10 | `INTERNAL_ERROR` | Uncaught defect; traceback logged to stderr. |
