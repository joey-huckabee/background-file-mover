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
