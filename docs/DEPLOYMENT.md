# Deployment Guide

How to deploy Background File Mover as a systemd-managed service, and the NFS
qualification checklist to run before trusting it with production recordings.

The runtime is Python-3.10 standard library only; the steps below still install into a
dedicated virtualenv so the service has a stable, isolated interpreter.

Sections 1–8 are the generic runbook. Complete, distribution-specific walkthroughs for
**Red Hat Enterprise Linux 9** and **SUSE Linux Enterprise Server 12** are added at the end
(*End-to-end runbook — …*). For the deployment topology (one venv, one config, the thin CLI),
the system-service-vs-rootless models, and everyday CLI usage, see `docs/USER-GUIDE.md`.

## 1. Runtime layout

| Path | Purpose | Owner / mode |
|------|---------|--------------|
| `/etc/file-mover/file-mover.ini` | operator configuration | `root:mover` `0640` |
| `/opt/file-mover/venv/` | dedicated Python venv with the package | `root:root` |
| `/var/lib/file-mover/` | durable state: `jobs.db`, `manifests/` | `mover:mover` `0750` |
| `/run/file-mover/` | `control.sock`, pid (recreated each boot) | `mover:mover` `0750` |
| `/var/log/file-mover/` | created by the unit's `LogsDirectory`; unused under twelve-factor logging (journald captures stdout/stderr) | `mover:mover` `0750` |

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

## End-to-end runbook — Red Hat Enterprise Linux 9

A complete walkthrough on a fresh RHEL 9 host, as the system service. RHEL 9's default
`python3` is 3.9 (too old); RHEL 9 ships newer interpreters as separate packages, so we use
**python3.11**. SELinux is enforcing, and its systemd (v252) supports every directive in the
shipped unit.

### R1 — Install a supported Python

```bash
sudo dnf install -y python3.11
python3.11 --version          # 3.11.x
```

The package is a pure-Python wheel with **zero runtime dependencies**, so no compiler or
`-devel` packages are needed.

### R2 — Service account and group

```bash
sudo groupadd --system mover
sudo useradd --system --gid mover --home-dir /var/lib/file-mover \
     --shell /sbin/nologin mover
# Operators / the orchestration account only need the mover group (config + socket access):
sudo usermod -aG mover "$SIMULATION_USER"
```

`/var/lib/file-mover` and `/run/file-mover` are created by systemd (`StateDirectory` /
`RuntimeDirectory`) on start — do not pre-create them.

### R3 — Install the package into a venv

```bash
sudo python3.11 -m venv /opt/file-mover/venv
sudo /opt/file-mover/venv/bin/pip install /path/to/background_file_mover-0.4.1-py3-none-any.whl
sudo /opt/file-mover/venv/bin/python -m file_mover --version
```

(Build the wheel from a checkout with `poetry build`, or download it from the GitHub release.)

### R4 — Configure

```bash
sudo install -D -o root -g mover -m 0640 config/file-mover.ini \
     /etc/file-mover/file-mover.ini
sudo -e /etc/file-mover/file-mover.ini
#   [paths] allowed_source_roots      = /recordings
#   [paths] allowed_destination_roots = /processing
```

### R5 — Grant the `mover` account access to the NFS mounts

`mover` must read/rename/delete on the source and write on the destination — match your
site's model:

```bash
sudo usermod -aG recording-group mover                    # group membership, or:
sudo setfacl -R -m u:mover:rwX /recordings /processing    # POSIX ACLs
```

### R6 — Install and start the unit

```bash
sudo install -m 0644 packaging/systemd/file-mover.service /etc/systemd/system/
sudo -e /etc/systemd/system/file-mover.service
#   - point ExecStart's interpreter at /opt/file-mover/venv/bin/python (the 3.11 venv)
#   - set RequiresMountsFor and ReadWritePaths to your real mounts
sudo systemctl daemon-reload
sudo systemctl enable --now file-mover
systemctl status file-mover
```

`Type=notify` means `enable --now` returns only once the service is genuinely serving
(lock held, state open, recovery reconciled, socket bound).

### R7 — SELinux (enforcing)

There is no network port (the control plane is a local Unix socket), so firewalld needs no
changes. A confined service reaching an **NFS** mount can raise AVC denials — check and scope
them rather than disabling SELinux:

```bash
sudo ausearch -m avc -ts recent           # or: journalctl -t setroubleshoot
# If denials mention the mover reaching /recordings, /processing, or /run/file-mover:
sudo ausearch -m avc -ts recent | audit2allow -M file-mover-local
sudo semodule -i file-mover-local.pp
```

### R8 — Validate

```bash
sudo -u mover /opt/file-mover/venv/bin/python -m file_mover \
     --config /etc/file-mover/file-mover.ini doctor \
  || { echo "doctor failed (rc=$?) — do not enable the service"; exit 1; }
sudo -u "$SIMULATION_USER" file-mover health
```

Then run the **Acceptance tests** (§7) and, before production, the **NFS qualification
checklist** below. *(SLES 15 SP4+ follows this same runbook almost verbatim: use
`zypper install python311` in R1, and AppArmor instead of SELinux in R7.)*

## End-to-end runbook — SUSE Linux Enterprise Server 12

> ⚠️ **SLES 12 is a constrained target and is not recommended for new deployments** — prefer
> **SLES 15 SP4+** (`zypper install python311`, modern systemd), which follows the RHEL 9
> runbook above almost verbatim. If you must use SLES 12, this is a complete, working path. It
> assumes **SLES 12 SP2 or later** (systemd 228, glibc 2.22). Two SLES-12 realities drive the
> differences from RHEL 9:
>
> - **No Python ≥ 3.10 in the repositories** → build CPython 3.10 from source (S1–S2).
> - **systemd 228 predates `StateDirectory=`, `ReadWritePaths=`, `ProtectSystem=strict`, and
>   several `Protect*`/`Restrict*` directives** → create the state directory manually and use
>   a trimmed unit (S3, S6).

### S1 — Compiler and build dependencies

Enable the SDK module (it provides gcc and the `-devel` headers), then install the build
prerequisites:

```bash
sudo SUSEConnect -p sle-sdk/12.5/x86_64        # SLES 12 SP5 SDK module — adjust the SP
sudo zypper install -y gcc make \
     zlib-devel sqlite3-devel libbz2-devel readline-devel libffi-devel xz-devel ncurses-devel \
     libopenssl-devel
```

The two that matter for this application are **`sqlite3-devel`** (the `_sqlite3` module and
WAL) and a working C toolchain. The hash algorithms the mover uses (`sha256` / `sha512` /
`blake2b`) are **built into CPython** and need no OpenSSL.

### S2 — Build and install CPython 3.10 (isolated under `/opt`)

```bash
cd /usr/local/src
sudo curl -LO https://www.python.org/ftp/python/3.10.14/Python-3.10.14.tgz   # use the latest 3.10.x
sudo tar xf Python-3.10.14.tgz && cd Python-3.10.14
sudo ./configure --prefix=/opt/python3.10 --enable-optimizations   # drop --enable-optimizations for a faster build
sudo make -j"$(nproc)"
sudo make altinstall               # altinstall does not touch the system python3
/opt/python3.10/bin/python3.10 --version
```

> **OpenSSL note.** SLES 12's OpenSSL is 1.0.2, which is older than the 1.1.1 that Python
> 3.10's `ssl`/`_hashlib` modules require, so the build prints
> `The necessary bits to build these optional modules were not found: _ssl _hashlib` and
> skips them. **That is fine for this application:** it never uses `ssl`, its hash algorithms
> are the built-in (non-OpenSSL) implementations, and you install from a **local wheel** (no
> PyPI download, so `pip`/`venv` do not need `ssl`). Only build a newer OpenSSL and reconfigure
> with `--with-openssl=…` if you specifically need `ssl` for other reasons.

Verify the modules the mover depends on were built (sqlite3 with WAL, the hashes, `AF_UNIX`,
`fcntl`):

```bash
/opt/python3.10/bin/python3.10 - <<'PY'
import sqlite3, hashlib, socket, fcntl
conn = sqlite3.connect(":memory:")
assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() in {"wal", "memory"}
assert {"sha256", "sha512", "blake2b"} <= hashlib.algorithms_available
assert hasattr(socket, "AF_UNIX")
print("ok: sqlite3 (+WAL on-disk), sha256/sha512/blake2b, AF_UNIX, fcntl")
PY
```

(`os.copy_file_range` is absent because SLES 12's glibc predates 2.27; the mover falls back to
the buffered copy engine and `doctor` reports kernel copy as an optional `warn` — expected and
harmless.)

### S3 — Service account and **manual** state directory

```bash
sudo groupadd --system mover
sudo useradd --system --gid mover --home-dir /var/lib/file-mover \
     --shell /sbin/nologin mover
sudo usermod -aG mover "$SIMULATION_USER"
# systemd 228 does NOT support StateDirectory=, so create the state directory yourself:
sudo install -d -o mover -g mover -m 0750 /var/lib/file-mover
```

`/run/file-mover` is still created by the unit's `RuntimeDirectory` (which exists in systemd
228), and `manifests/` under the state directory is created by the service itself.

### S4 — Install the package on the built Python

```bash
sudo /opt/python3.10/bin/python3.10 -m venv /opt/file-mover/venv
sudo /opt/file-mover/venv/bin/pip install /path/to/background_file_mover-0.4.1-py3-none-any.whl
sudo /opt/file-mover/venv/bin/python -m file_mover --version
```

### S5 — Configure

Identical to RHEL 9 (R4): set `allowed_source_roots` / `allowed_destination_roots`, and grant
the `mover` account NFS access (group membership or ACLs, as in R5).

```bash
sudo install -D -o root -g mover -m 0640 config/file-mover.ini /etc/file-mover/file-mover.ini
sudo vi /etc/file-mover/file-mover.ini
```

### S6 — A systemd unit trimmed for systemd 228

The shipped `packaging/systemd/file-mover.service` uses directives newer than systemd 228
(`StateDirectory`, `ReadWritePaths`, `ProtectSystem=strict`, `ProtectClock`, …). systemd 228
warns on and ignores the unknown ones — but `StateDirectory` being ignored is why S3 creates
the directory manually, and `ProtectSystem=strict` is unavailable. Install this
v228-compatible unit at `/etc/systemd/system/file-mover.service` instead:

```ini
[Unit]
Description=Background File Mover (durable transfer coordinator)
After=network-online.target remote-fs.target
Wants=network-online.target
RequiresMountsFor=/recordings /processing
ConditionPathExists=/etc/file-mover/file-mover.ini

[Service]
Type=notify
NotifyAccess=main
User=mover
Group=mover
ExecStart=/opt/file-mover/venv/bin/python -O -m file_mover --config /etc/file-mover/file-mover.ini service run
Restart=on-failure
RestartSec=10
TimeoutStartSec=120
TimeoutStopSec=90
WatchdogSec=30
UMask=0007
RuntimeDirectory=file-mover
RuntimeDirectoryMode=0750
# Hardening available in systemd 228 (the newer Protect*/Restrict* directives do not exist here):
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=full
ProtectHome=true
ReadWriteDirectories=/var/lib/file-mover /recordings /processing

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now file-mover
systemctl status file-mover
journalctl -u file-mover | grep -i "unknown"   # confirm no warning concerns RuntimeDirectory or Type=notify
```

### S7 — AppArmor

SLES uses AppArmor, not SELinux, and ships no profile for the mover, so it runs unconfined by
default and NFS access needs no extra policy. If you add a profile, allow read/rename/unlink
under the source roots, write under the destination roots, and read-write on
`/var/lib/file-mover` and `/run/file-mover`.

### S8 — Validate

```bash
sudo -u mover /opt/file-mover/venv/bin/python -m file_mover \
     --config /etc/file-mover/file-mover.ini doctor
```

`doctor` confirms Python ≥ 3.10 (your source build), `AF_UNIX`, `fcntl`, SQLite WAL, the hash
algorithm, and POSIX signals are all present, and reports kernel-assisted copy as an optional
`warn` (expected on SLES 12). Then run the **Acceptance tests** (§7) and the **NFS
qualification checklist** below.

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
