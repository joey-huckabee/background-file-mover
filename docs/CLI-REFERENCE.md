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
throughput — see `docs/ARCHITECTURE.md` § *Bandwidth limiting*.

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
| 10 | `INTERNAL_ERROR` | Uncaught defect; traceback logged to stderr. |
