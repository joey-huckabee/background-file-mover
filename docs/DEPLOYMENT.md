# Deployment Guide

How to deploy Background File Mover as a systemd-managed service, and the NFS
qualification checklist to run before trusting it with production recordings.

The runtime is Python-3.10 standard library only; the steps below still install into a
dedicated virtualenv so the service has a stable, isolated interpreter.

## 1. Runtime layout

| Path | Purpose | Owner / mode |
|------|---------|--------------|
| `/etc/file-mover/file-mover.ini` | operator configuration | `root:mover` `0640` |
| `/opt/file-mover/venv/` | dedicated Python venv with the package | `root:root` |
| `/var/lib/file-mover/` | durable state: `jobs.db`, `manifests/` | `mover:mover` `0750` |
| `/run/file-mover/` | `control.sock`, pid (recreated each boot) | `mover:mover` `0750` |
| `/var/log/file-mover/` | log file (when `log_to_file = true`) | `mover:mover` `0750` |

`/run`, `/var/lib`, and `/var/log` subdirectories are created by systemd via
`RuntimeDirectory` / `StateDirectory` / `LogsDirectory` — do not pre-create them.

## 2. Service account

```bash
sudo groupadd --system mover
sudo useradd --system --gid mover --home-dir /var/lib/file-mover \
     --shell /usr/sbin/nologin mover
# Let the simulation orchestration account reach the control socket:
sudo usermod -aG mover "$SIMULATION_USER"
```

## 3. Install the package

```bash
sudo python3.10 -m venv /opt/file-mover/venv
sudo /opt/file-mover/venv/bin/pip install /path/to/background_file_mover-*.whl
sudo /opt/file-mover/venv/bin/python -m file_mover --version
```

Build the wheel from a checkout with `poetry build` (output in `dist/`).

## 4. Configure

```bash
sudo install -D -o root -g mover -m 0640 config/file-mover.ini \
     /etc/file-mover/file-mover.ini
sudoedit /etc/file-mover/file-mover.ini   # set allowed_source_roots / _destination_roots
```

`allowed_source_roots` and `allowed_destination_roots` must match the `RequiresMountsFor`
and `ReadWritePaths` in the unit file (step 5). See `docs/CONFIG-REFERENCE.md`.

## 5. Install and start the service

```bash
sudo install -m 0644 packaging/systemd/file-mover.service \
     /etc/systemd/system/file-mover.service
# Edit RequiresMountsFor / ReadWritePaths to match your mounts, then:
sudo systemctl daemon-reload
sudo systemctl enable --now file-mover
systemctl status file-mover
```

## 6. Validate

```bash
# Configuration and (later) filesystem checks, without contacting the service:
sudo -u mover /opt/file-mover/venv/bin/python -m file_mover \
     --config /etc/file-mover/file-mover.ini doctor
# Live service health over the control socket:
sudo -u "$SIMULATION_USER" file-mover health
```

The orchestration integration is a single subprocess call:

```python
subprocess.run(
    ["/opt/file-mover/venv/bin/python", "-m", "file_mover", "submit",
     "--scenario-id", scenario_id, "--source", str(source), "--destination", str(dest)],
    check=True, timeout=30,
)
```

## 7. Acceptance tests (run once per environment)

- **Small transfer.** Submit a handful of small files; confirm they appear at the
  destination, the claimed sources are deleted, `status` reports `completed`, the manifest
  exists under `manifests/`, and the SQLite job row is `completed`.
- **Restart recovery.** Submit a large set, `systemctl stop file-mover` mid-transfer,
  then start it again. Confirm the job survives, the claimed sources are still present,
  any partial destination is reconciled (no `.swit-partial-*` left, no premature or
  duplicate final files), and the transfer completes.
- **Idempotent submit.** Submit the same `request_id` twice; confirm one job and no
  duplicate claim.

## NFS qualification checklist

A local temporary directory cannot reproduce every NFS behavior. Before production, run
these against the real source and destination mounts:

- [ ] Temporary loss of the destination mount during a transfer (source retained; job
      retries or is retained, never lost).
- [ ] Stale NFS file handle (`ESTALE`) during copy (classified retryable).
- [ ] NFS server restart mid-transfer.
- [ ] Permissions changing on the destination during a transfer.
- [ ] Destination capacity exhaustion (`ENOSPC` retains the source for operator action).
- [ ] File visibility after an atomic rename across concurrent NFS clients.
- [ ] Downstream consumer never observes a `.swit-partial-*` file as a finished recording.
- [ ] Sustained ~100 GB transfer within the target window without stalling the
      simulation hosts.
- [ ] Multiple simultaneous scenario submissions.
- [ ] Large individual files (10–30 GB) copy and verify correctly.
