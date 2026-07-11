# Background File Mover

A durable, **standard-library-only** (Python 3.10) background transfer coordinator for
large simulation recordings.

Simulation orchestration on six Linux hosts records ~100 GB per run to a local NFS mount.
Moving that data synchronously stalls the hosts and delays the next run. Background File
Mover accepts a submitted recording set, atomically **claims** the files so the next run
cannot overwrite them, returns a durable acknowledgement immediately, and then moves the
data in the background with transaction-like semantics:

```
claim  →  copy (to temp)  →  verify  →  publish (atomic rename)  →  delete source
```

A source file is **never** deleted until its destination has been written, fsynced,
published, and verified against the configured integrity policy. Any failure retains the
claimed source.

## Highlights

- Runs under **systemd**; the `file-mover` CLI is a thin client over a Unix control socket.
- **SQLite** holds authoritative durable job/file state; the service recovers interrupted
  jobs after a crash or restart from observable filesystem state plus durable records.
- Configurable **integrity verification** (metadata / source-hash /
  source-and-destination-hash) via `hashlib`.
- Classified, bounded, durable **retry** with exponential backoff.
- Zero runtime dependencies — production code imports only the Python 3.10 standard library.
- Full **L1/L2/L3 requirement traceability** (`docs/TRACE-MATRIX.md`).

## Status

Under active construction. See **`docs/ROADMAP.md`** for the milestone plan (M1 Foundation
through M8 Packaging & Qualification). The CLI surface is in place today; transfer behavior
lands in later milestones.

## Quickstart (development)

```
poetry install
poetry run file-mover --help
poetry run pytest
```

## Documentation

- `docs/ARCHITECTURE.md` — how it is built and why.
- `docs/CLI-REFERENCE.md` — commands, flags, exit codes.
- `docs/CONFIG-REFERENCE.md` — configuration options (`config/file-mover.ini`).
- `docs/MAINTAINER-GUIDE.md` — dev setup and contribution workflows.
- `docs/L1-REQ.md` / `docs/L2-REQ.md` / `docs/L3-REQ.md` — requirements.

## License

Apache-2.0 — see `LICENSE`.
