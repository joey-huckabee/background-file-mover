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

The unit uses `Type=notify`, so `systemctl start file-mover` (and any unit ordered
`After=file-mover`) blocks until the service has actually reconciled state and bound the
control socket — orchestration can start submitting the moment `start` returns, with no
readiness race. The `WatchdogSec=30` setting makes systemd restart the service if it hangs
(e.g. on a wedged NFS mount); keep `[service] poll_interval_seconds` below half of it.

## 6. Validate

**Run `doctor` as a pre-flight gate** — before (or right after) `enable --now`, as the
service account. It validates the configuration *and* verifies the runtime provides the
required capabilities (`AF_UNIX`, `fcntl`, SQLite WAL, the configured hash algorithm,
Python ≥ 3.10, POSIX signals). A missing required capability exits **`8`
(`ENVIRONMENT_UNSUPPORTED`)**, so a deploy script can hard-gate on it:

```bash
sudo -u mover /opt/file-mover/venv/bin/python -m file_mover \
     --config /etc/file-mover/file-mover.ini doctor \
  || { echo "doctor failed (rc=$?) — do not enable the service"; exit 1; }
# Live service health over the control socket:
sudo -u "$SIMULATION_USER" file-mover health
```

`doctor` also prints `warn` lines for absent *optional* capabilities (kernel-assisted copy,
`O_NOFOLLOW`) — informational, not failures. See `docs/CLI-REFERENCE.md` § `doctor`.

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

## 8. Logs

The service writes its **event stream to stdout/stderr and manages no log files** — the
environment routes them (twelve-factor). Under the shipped unit, journald captures both
streams:

```bash
journalctl -u file-mover -f              # follow live
journalctl -u file-mover -p warning      # WARNING and above (stderr)
journalctl -u file-mover | grep job_id=<id>   # trace one job across its lifecycle
```

`INFO`/`DEBUG` go to **stdout**, `WARNING`/`ERROR` to **stderr**. Set verbosity with
`[logging] level` (`DEBUG | INFO | WARNING | ERROR | OFF`). The unit runs `python -O`, which
removes DEBUG logging from the bytecode entirely; to troubleshoot at DEBUG **live**, drop
`-O` from the unit's `ExecStart`, set `level = DEBUG`, and `systemctl restart`. To ship logs
elsewhere, redirect the streams or point journald at your collector — do not add app-side
log files. Full detail: **`docs/LOGGING.md`**.

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
- [ ] **Copy-strategy benchmark.** Time a representative transfer with
      `[transfer] use_kernel_copy = true` and again with `false` on the real mounts.
      Keep whichever is faster; across two different NFS servers the kernel copy often
      falls back to buffered anyway, so confirm rather than assume. (The service always
      falls back safely, so `true` is a sound default.)
