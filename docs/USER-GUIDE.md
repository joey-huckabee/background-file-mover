# User Guide

How to install, deploy, and use Background File Mover: the deployment topology (what runs
where), the **system-service (root)** and **rootless (per-user)** models, a step-by-step
**Red Hat Enterprise Linux 9** tutorial, everyday CLI usage, and platform notes (including
SLES). For the bare systemd runbook and the NFS qualification checklist see
`docs/DEPLOYMENT.md`; for per-command detail `docs/CLI-REFERENCE.md`; for every configuration
option `docs/CONFIG-REFERENCE.md`.

## The mental model: one package, one config, a thin CLI

There is **one** installed package, and it provides **two** entry points from the **same**
virtualenv:

- **the service** — `python -m file_mover … service run`, a long-running daemon managed by
  systemd. It owns the SQLite job database, the transfer worker pool, crash recovery, and a
  local control socket. This is the process that actually moves the ~100 GB.
- **the CLI** — `file-mover <command>`, a short-lived client. It parses arguments, sends
  **one** length-prefixed JSON request to the service over the control socket, prints the
  result, and exits. It never moves data and never opens the database.

```
        you / orchestration script                 systemd
                    │                                  │
            file-mover submit …                 file_mover … service run
                    │                                  │
                    ▼          AF_UNIX socket           ▼
            file-mover (CLI)  ───────────────►  Background File Mover (daemon)
            short-lived        length-prefixed  ├── SQLite job database
                               JSON, per request├── transfer worker pool
                                                 └── recovery + control server
```

**So, answering the common question directly:** you do **not** need a second virtualenv for
the CLI, and you do **not** need a separate CLI configuration file. The CLI and the service
come from the same install and read the **same** configuration file — the CLI reads it only
to discover the control-socket path (`[service] socket_path`) so it can connect. All a CLI
user needs is (1) read access to that config file and (2) permission to open the socket.

There is exactly **one** configuration file per deployment. *Where* it lives depends on the
deployment model:

| | System service (root) | Rootless (per-user) |
|---|---|---|
| Config file | `/etc/file-mover/file-mover.ini` | `~/.config/file-mover/file-mover.ini` |
| Read by | the service **and** every CLI invocation | the service **and** every CLI invocation |

(A CLI user *may* pass `--config /path/to/other.ini`, but it must be a complete, valid config
whose `socket_path` matches the running service. Sharing the one file is simplest.)

## Deployment model 1 — system service (root), recommended for production

A dedicated system account runs the daemon under the **system** systemd instance; operators
and the orchestration account talk to it through a group-readable socket, and full systemd
sandboxing applies. Use this when the mover should run independently of any login session and
be centrally managed.

Paths (systemd creates the runtime/state ones from the unit's `RuntimeDirectory`/
`StateDirectory`):

| Path | Purpose | Owner / mode |
|------|---------|--------------|
| `/opt/file-mover/venv/` | the virtualenv with the installed package | `root:root` |
| `/etc/file-mover/file-mover.ini` | the one config file | `root:mover` `0640` |
| `/var/lib/file-mover/` | `jobs.db`, `manifests/` | `mover:mover` `0750` |
| `/run/file-mover/control.sock` | the control socket | `mover:mover` `0660` |
| `/etc/systemd/system/file-mover.service` | the unit | `root:root` `0644` |

**The permissions that matter:**

- The **`mover` service account** must be able to *read, rename, and delete* files on the
  **source** NFS mount (to claim into `.swit-moving/` and delete after a verified publish) and
  *write* to the **destination** NFS mount. On shared NFS this usually means adding `mover` to
  the group that owns the recordings, or granting ACLs — this is the main thing to get right.
- **Operators and the orchestration account** only run the CLI. Add them to the **`mover`
  group** so they can read `/etc/file-mover/file-mover.ini` (mode `0640`) and open the socket
  (`0660`). Nothing else.

The step-by-step below (the **RHEL 9 tutorial**) is this model end to end.

## Deployment model 2 — rootless / per-user (`systemctl --user`)

Run the whole thing as an ordinary user — no root, no dedicated account — under that user's
own systemd instance. This is the natural fit when the mover runs **as the same user that
produced the recordings**: filesystem permissions are then already aligned (that user can
read and delete its own recordings), so there is no service account or group juggling.

Everything lives under the user's XDG directories:

| Path | Purpose |
|------|---------|
| `~/.local/venvs/file-mover/` (or `pipx`) | the virtualenv |
| `~/.config/file-mover/file-mover.ini` | the one config file |
| `~/.local/state/file-mover/` | `jobs.db`, `manifests/` |
| `$XDG_RUNTIME_DIR/file-mover/control.sock` | the control socket (`/run/user/<uid>/…`) |
| `~/.config/systemd/user/file-mover.service` | the user unit |

Setup (as the user, no `sudo`):

```bash
python3.11 -m venv ~/.local/venvs/file-mover
~/.local/venvs/file-mover/bin/pip install background_file_mover-0.4.1-py3-none-any.whl
mkdir -p ~/.config/file-mover ~/.local/state/file-mover
install -m 0640 /path/to/file-mover.ini ~/.config/file-mover/file-mover.ini
# In that ini, point the paths at your home and runtime dir:
#   [service] state_directory    = %h/.local/state/file-mover
#             database_path       = %h/.local/state/file-mover/jobs.db
#             manifest_directory  = %h/.local/state/file-mover/manifests
#             socket_path         = %t/file-mover/control.sock
#   [paths]   allowed_source_roots / allowed_destination_roots = your NFS dirs
```

A user unit at `~/.config/systemd/user/file-mover.service`:

```ini
[Unit]
Description=Background File Mover (rootless)
After=network-online.target

[Service]
Type=notify
RuntimeDirectory=file-mover
StateDirectory=file-mover
ExecStart=%h/.local/venvs/file-mover/bin/python -O -m file_mover \
    --config %h/.config/file-mover/file-mover.ini service run
Restart=on-failure
WatchdogSec=30

[Install]
WantedBy=default.target
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now file-mover
loginctl enable-linger "$USER"     # keep it running with no active login session
file-mover --config ~/.config/file-mover/file-mover.ini health
```

`%t` is the user runtime dir (`$XDG_RUNTIME_DIR`) and `%h` is the home dir; the user systemd
instance sets `NOTIFY_SOCKET`, so `Type=notify` works unchanged. Because the same user runs
both the daemon and the CLI, the socket's default `0600` is enough — no group needed.

**Trade-offs vs. the system service:** rootless is simpler for permissions (no service
account, no NFS ACLs when you *are* the recording owner) but you get less sandboxing (a user
unit cannot use every hardening directive) and the service is tied to that user's linger
session. The system service is the more productionised, centrally-managed option.

## Tutorial — Red Hat Enterprise Linux 9 (system service)

RHEL 9's default `python3` is 3.9, but the mover needs **3.10+**. RHEL 9 ships newer Pythons
as separate packages — use 3.11 (or 3.12).

### 1. Install a supported Python

```bash
sudo dnf install -y python3.11
python3.11 --version        # 3.11.x
```

The package is a pure-Python wheel (`background_file_mover-<ver>-py3-none-any.whl`) with
**zero runtime dependencies**, so no compiler or `-devel` packages are needed. Build it from
a checkout with `poetry build` (output in `dist/`) or take it from the GitHub release.

### 2. Service account and install

```bash
sudo groupadd --system mover
sudo useradd --system --gid mover --home-dir /var/lib/file-mover \
     --shell /sbin/nologin mover

sudo python3.11 -m venv /opt/file-mover/venv
sudo /opt/file-mover/venv/bin/pip install /path/to/background_file_mover-0.4.1-py3-none-any.whl
sudo /opt/file-mover/venv/bin/python -m file_mover --version
```

### 3. Configuration

```bash
sudo install -D -o root -g mover -m 0640 config/file-mover.ini \
     /etc/file-mover/file-mover.ini
sudo -e /etc/file-mover/file-mover.ini
#   set [paths] allowed_source_roots      = /recordings    (your source NFS mount)
#       [paths] allowed_destination_roots = /processing    (your destination NFS mount)
```

Grant the `mover` account access to the NFS mounts (adjust to your site — group membership or
ACLs):

```bash
# Example: mover joins the group that owns the recordings and gets rwX on the trees.
sudo usermod -aG recording-group mover
sudo setfacl -R -m u:mover:rwX /recordings /processing     # if you use POSIX ACLs
```

### 4. Install and start the unit

```bash
sudo install -m 0644 packaging/systemd/file-mover.service /etc/systemd/system/
sudo -e /etc/systemd/system/file-mover.service
#   - set RequiresMountsFor and ReadWritePaths to your real mounts
#   - point ExecStart's interpreter at /opt/file-mover/venv/bin/python (the 3.11 venv)
sudo systemctl daemon-reload
sudo systemctl enable --now file-mover
systemctl status file-mover
```

Because the unit is `Type=notify`, `enable --now` returns only once the service is genuinely
serving (lock held, state open, recovery reconciled, socket bound) — orchestration can submit
the moment it returns, with no readiness race.

### 5. SELinux (enforcing by default on RHEL 9)

The `StateDirectory`/`RuntimeDirectory` paths get correct file contexts automatically, and
there is **no network port** to open (the control plane is a local Unix socket), so firewalld
needs no changes. A confined service reaching an **NFS** mount can, however, draw AVC denials.
After the first start, check for them:

```bash
sudo ausearch -m avc -ts recent          # or: journalctl -t setroubleshoot
```

If you see denials for the mover reaching `/recordings` / `/processing`, prefer a **scoped**
policy generated from the audit log over disabling SELinux:

```bash
sudo ausearch -m avc -ts recent | audit2allow -M file-mover-local
sudo semodule -i file-mover-local.pp
```

(Some sites instead mount NFS with an explicit `context=` or rely on a site NFS SELinux
policy — follow your local convention.)

### 6. Verify

```bash
# Pre-flight: validate config + runtime capabilities. Exits 8 if a REQUIRED one is missing.
sudo -u mover /opt/file-mover/venv/bin/python -m file_mover \
     --config /etc/file-mover/file-mover.ini doctor

# Live health over the socket (run as a user in the mover group):
file-mover --config /etc/file-mover/file-mover.ini health

# First small transfer:
file-mover --config /etc/file-mover/file-mover.ini submit \
    --scenario-id TEST-001 --source /recordings/test-001 --destination /processing/TEST-001
file-mover --config /etc/file-mover/file-mover.ini status <job-id>
```

Confirm the claimed source was renamed into `.swit-moving/` quickly, a `.swit-partial-` temp
appeared at the destination, the final file appeared only after verification, the source was
deleted only after publication, and the SQLite row reached `completed`.

## Everyday CLI usage

Every command takes `--config` (default `/etc/file-mover/file-mover.ini`) and talks to the
running service over the socket. See `docs/CLI-REFERENCE.md` for the full reference.

```bash
file-mover submit --scenario-id ID --source DIR --destination DIR   # or --file-list FILE
file-mover status <job-id>
file-mover list --state active
file-mover stats
file-mover pause <job-id>     # / resume / cancel  (cancel always retains the source)
file-mover throttle 50MB      # live throughput cap; 0 = unlimited
file-mover health             # live service status over the socket
file-mover doctor             # local: validate config + verify runtime capabilities
```

Orchestration integration is one subprocess call that returns after the files are durably
**claimed** (not after the ~100 GB transfer):

```python
subprocess.run(
    ["/opt/file-mover/venv/bin/file-mover", "--config", "/etc/file-mover/file-mover.ini",
     "submit", "--scenario-id", scenario_id, "--source", str(src), "--destination", str(dst)],
    check=True, timeout=30,
)
```

## Platform notes

| Platform | Status | Notes |
|----------|--------|-------|
| **RHEL 9** | ✅ Supported | `dnf install python3.11` (or `python3.12`); the default 3.9 is too old. SELinux enforcing — see step 5. systemd 252 supports every directive in the shipped unit. |
| **RHEL 8** | ✅ with a newer Python | `dnf install python3.11`; otherwise identical to the RHEL 9 tutorial. |
| **SLES 15 SP4+** | ✅ Supported | `zypper install python311`; systemd 249+ runs the shipped unit as-is. AppArmor rather than SELinux. |
| **SLES 12** | ⚠️ Not recommended | See below. |
| **Windows** | ❌ Service unsupported | No `AF_UNIX`/`fcntl`; `doctor` returns `ENVIRONMENT_UNSUPPORTED`. Cross-platform logic is tested on Windows, but the service runs on Linux only. |

### Will there be issues with SLES 12?

Yes — SLES 12 is a poor fit, for two concrete reasons:

1. **Python is too old.** SLES 12's default is Python 3.4 (3.6 on SP5 via a package); the
   mover requires **3.10+**, and there is no 3.10 package in the SLES 12 repositories. You
   would have to build Python 3.10+ from source or run the service in a container — both
   defeat "just install the wheel."
2. **systemd is too old (v228).** The `StateDirectory=`, `LogsDirectory=`, and several of the
   `Protect*`/`Restrict*` hardening directives in the shipped unit were added in systemd
   v235+. On v228 the directory directives are **not honoured** — you must create
   `/var/lib/file-mover` and `/run/file-mover` yourself with the right owner/mode — and the
   newer hardening directives are ignored (the unit still starts, just less sandboxed).
   `Type=notify` itself works.

Not a blocker, for the record: SLES 12's older kernel/glibc may not expose
`os.copy_file_range`, so kernel-assisted copy simply falls back to the buffered engine —
`doctor` reports it as an *optional*, `warn`-level capability and transfers are unaffected.

**Recommendation:** use **SLES 15 SP4+** (it has `python311` and a modern systemd), or on
SLES 12 run under a container / source-built Python 3.10+ and hand-create the state and
runtime directories. Either way, run **`file-mover doctor` on the target host first** — it
reports exactly which required capability (Python ≥ 3.10, `AF_UNIX`, `fcntl`, SQLite WAL, the
configured hash algorithm, POSIX signals) is missing before you rely on the service.
