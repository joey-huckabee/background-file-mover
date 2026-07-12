# Logging & output streams

The single reference for how the Background File Mover uses **stdout**, **stderr**, and
logging — for **operators** (how to consume and route logs) and for **developers** (how to
add log calls correctly). For the underlying mechanism see `docs/ARCHITECTURE.md`
§ *Logging & observability*; for the design stance see `docs/12-FACTOR.md`; for the
`[logging]` option see `docs/CONFIG-REFERENCE.md`.

## The output-stream contract

The two process types have **opposite** contracts for stdout — this is the single most
important thing to understand:

| Process | stdout carries | stderr carries |
|---------|----------------|----------------|
| **CLI** (`submit`, `status`, `list`, `--output json`, …) | the command **result** (machine-parseable; JSON with `--output json`) | diagnostics and errors |
| **service** (`service run` — a daemon) | the log **event stream**: `INFO` / `DEBUG` | the log event stream: `WARNING` / `ERROR` / `CRITICAL` |

Why they differ:

- The **CLI's output is its result**, so logs must never touch stdout — a JSON consumer
  would choke on a stray log line. The CLI keeps stdout for the result and writes any
  diagnostics to stderr.
- The **daemon has no result** — its logs *are* its output. So it writes them to the
  standard streams (twelve-factor) and lets the environment route them, splitting by level
  so the Unix convention (`WARNING`+ on stderr) still holds.

The service **manages no log files**. It never writes, rotates, or names a logfile — the
environment does routing and storage.

## For operators — using and routing logs

- **Under systemd (default deployment):** journald captures both streams. Read them with:
  ```
  journalctl -u file-mover          # recent logs
  journalctl -u file-mover -f       # follow live
  journalctl -u file-mover -p warning   # WARNING and above (from stderr)
  ```
- **Verbosity** is `[logging] level` in the INI (`DEBUG | INFO | WARNING | ERROR | OFF`),
  overridable on `service run` with `-v`/`-vv`/`--log-level`. `level = OFF` silences
  everything (a null handler is installed).
- **Route only errors to a file** (the split makes this trivial):
  ```
  ExecStart=… service run 2>>/var/log/file-mover.err   # WARNING+ only
  ```
  Ship **all** logs by redirecting both streams (`>>all.log 2>&1`) or by pointing journald
  at your log shipper — the app does not do this for you.
- **DEBUG in production is free**: the systemd unit runs `python -O`, which strips
  `if __debug__ and GATE.debug:` DEBUG blocks from the bytecode entirely (see the developer
  section). To watch DEBUG **live**, temporarily drop `-O` from the unit's `ExecStart` and
  set `[logging] level = DEBUG`.
- **Correlation:** job/file events carry structured fields rendered as
  `… [job_id=<id> file_id=<id>]`, so you can trace one job or file through its whole
  lifecycle with `grep`/`journalctl … | grep job_id=<id>`.

### What each level means here

| Level | Emitted for |
|-------|-------------|
| `DEBUG` | per-file / per-transition mechanism: copy strategy, resume offset, state transitions, dispatch |
| `INFO` | lifecycle milestones: submission accepted, job completed / paused / cancelled, recovery, throttle changes |
| `WARNING` | retained-and-actionable conditions: size/hash mismatch, destination collision, manual intervention, config advisories |
| `ERROR` | uncaught defects (via `logger.exception`, with a traceback) |
| `OFF` | nothing |

## For developers — how to add a log call

Follow these rules (enforced by convention and review). The goal: **structured
correlation** and **zero cost when the level is off**.

1. **Get a stable logger.** Use `logging.getLogger("file_mover.<area>")` (module-level, or
   stored on the instance in `__init__`). **Never** install handlers, and **never** use a
   per-instance or random logger name — correlation is by *fields*, not the logger name.

2. **Carry context with `bind`, not the name or the message.** Attach `job_id`/`file_id`
   as structured fields:
   ```python
   from file_mover.logging_config import GATE, bind

   log = bind(self._log, job_id=job.job_id, file_id=file.file_id)  # nested binds accumulate
   log.info("file published")            # record carries job_id + file_id
   ```

3. **Gate by cost — this is the convention:**

   | Call site | Write it as | Cost when off |
   |-----------|-------------|---------------|
   | **DEBUG** (anywhere) | `if __debug__ and GATE.debug: log.debug("copied %d", n)` | stripped by `python -O`; else one boolean |
   | **hot-path INFO** (inside a loop / per-item) | `if GATE.info: log.info(...)` | one boolean |
   | **cold-path INFO/WARNING/ERROR** (once per job / request / startup) | `log.info(...)` directly | negligible `isEnabledFor` |

   `if __debug__ and GATE.debug:` is the important idiom: under `python -O` the whole block —
   **argument evaluation included** — is removed from the compiled bytecode, so production
   DEBUG is literally free; without `-O` it is a single predicted branch and DEBUG stays
   runtime-toggleable.

4. **Use `%`-style args, never f-strings**, so formatting is skipped when the record is
   dropped: `log.debug("state=%s", state)` — **not** `log.debug(f"state={state}")` (the
   f-string is always evaluated).

5. **Choose the level by audience** (see the table above), and use `logger.exception(...)`
   only for an unexpected *defect* — a classified operational failure is a `WARNING`
   without a traceback flood.

### Worked example

```python
class FileMover:
    def __init__(self, ...):
        self._log = logging.getLogger("file_mover.transfer.file")

    def move(self, job, file, *, resume=False, ...):
        log = bind(self._log, job_id=job.job_id, file_id=file.file_id)
        if __debug__ and GATE.debug:                              # DEBUG: strippable + gated
            log.debug("move start: %s (resume=%s)", file.relative_path, resume)
        ...
        if outcome.bytes_written != source_identity.size_bytes:
            log.warning("size mismatch for %s; retaining source", file.relative_path)  # cold WARNING
            return self._integrity_failure(outcome)
```

## Where the code lives (three separated concerns)

All in `logging_config.py`:

- **Level policy** — `LogGate`: per-level booleans (`GATE.debug/info/warning/error`) set
  **once** by `configure_logging`, read at each guarded call site.
- **Emission + context** — `bind` / `ContextLogger`: a merging `LoggerAdapter` that carries
  accumulated context onto every record's `extra`.
- **Formatting** — `ContextFormatter`: appends bound fields to the line and leaves
  context-free records untouched.

Configuration is `[logging] level` **only** — destinations are not application config
(twelve-factor). `configure_logging` installs a stdout handler (records `< WARNING`) and a
stderr handler (`>= WARNING`); the CLI never calls it, so its diagnostics fall to stderr.
