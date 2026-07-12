# Twelve-factor alignment

The Background File Mover is a **stateful, single-instance, local systemd daemon** — not a
stateless, horizontally-scaled cloud web app. Several [twelve-factor](https://12factor.net/)
factors fit it well and we follow them; a few deliberately do **not** apply, and forcing
them would harm the design. This document records that stance so the deviations are
intentional and reviewable rather than accidental.

## At a glance

| # | Factor | Stance |
|---|--------|--------|
| I | Codebase | ✅ **Follow** — one git repo, many deploys. |
| II | Dependencies | ✅ **Follow (strong)** — Poetry; **zero runtime dependencies**; standard-library-only production code (L1-SYS-009). |
| III | Config | ⚠️ **Deliberate deviation** — a strictly-validated INI file (`--config`), not env vars. |
| IV | Backing services | 〜 **Partial** — the "attached resources" are the local NFS mounts and SQLite, not network services. |
| V | Build, release, run | ✅ **Follow** — Poetry build; systemd deploy; distinct stages. |
| VI | Processes (stateless) | ⚠️ **Deliberate deviation** — durable SQLite job/file state is intentional and central. |
| VII | Port binding | ⚠️ **Deliberate deviation** — a local `AF_UNIX` control socket, not a network port. |
| VIII | Concurrency | 〜 **Partial** — bounded thread pools + an enforced singleton; horizontal scale is deferred. |
| IX | Disposability | ✅ **Follow (strong)** — fast start, signal-driven graceful drain, crash recovery (L1-SYS-005). |
| X | Dev/prod parity | ✅ **Follow** — CI matrix (Python 3.10–3.14 + Windows smoke); `doctor` verifies the runtime. |
| XI | Logs | ✅ **Follow (strong)** — event stream to stdout/stderr; the environment routes it; no app-managed files. |
| XII | Admin processes | ✅ **Follow (strong)** — the CLI one-off commands are the admin-process model. |

## The deliberate deviations, and why

- **III Config — an INI file, not the environment.** Operators manage one file at
  `/etc/file-mover/file-mover.ini`, versioned alongside the systemd unit, validated as a
  whole with a single `OptionSpec` schema (unknown keys rejected, ranges and cross-field
  constraints checked, all issues reported at once). Splitting that across environment
  variables would fragment the schema and lose the validation for no benefit on a
  fixed-host daemon. The `--config` flag still keeps config out of the code.

- **VI Stateless processes — durable state is the product.** The whole point is
  transaction-like `claim → copy → verify → publish → delete-source` semantics that survive
  a crash, which *requires* durable state (SQLite, WAL). Twelve-factor says to externalise
  state into a backing service — which is exactly what this app *is*; the process that owns
  that state is therefore correctly stateful, and startup recovery reconciles it.

- **VII Port binding — a local socket, not a network port.** Control is local to the
  systemd host, so an `AF_UNIX` stream socket is simpler and safer than exposing an HTTP
  port. The CLI is a thin local client, not a network caller.

## What twelve-factor gave us

The factors we follow drove real, deliberate decisions — they are not accidental:

- **II** — a zero-dependency, standard-library-only runtime.
- **IX** — signal-driven graceful drain plus crash-recovery reconciliation.
- **X** — `file-mover doctor` verifies the runtime provides the required capabilities, so a
  dev box and a production host are held to the same bar (see `docs/CLI-REFERENCE.md`).
- **XI** — the service writes its event stream to stdout/stderr and manages no log files;
  `[logging]` exposes only `level`. See **`docs/LOGGING.md`** for the full contract.
- **XII** — `submit` / `doctor` / `config validate` / `recover` are one-off admin processes
  run against (or alongside) the durable service.

Partial factors (**IV** backing services, **VIII** concurrency) are honoured where they fit
and consciously bounded where they do not — the enforced singleton (`fcntl` lock) is
deliberate, and multi-host active/active concurrency is tracked in `docs/ROADMAP.md`.
