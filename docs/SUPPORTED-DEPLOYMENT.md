# Supported deployment and qualification matrix (DOC-05)

What the current Rust mover is built and tested for, and what is not yet
qualified. Status as of 2026-11-21 ([increment 169](RUST-INCREMENT-169.md)).
This is a summary of existing evidence; each row links its source. It is not a
release approval: **all eight release gates remain open**, and no deployment is
authorized by this page.

**Status words:**
- **Gated:** checked automatically on every relevant change.
- **Tested:** bounded tests or lab evidence exist; see the limits.
- **Open:** not qualified; release work remains.

## Platform

| Area | What is supported | Status | Evidence and limits |
|---|---|---|---|
| CPU and OS | Linux x86_64, glibc 2.22 or newer, using the OS's own `libc`, `libm`, `libpthread`, `librt`, `libdl`, `libgcc_s` and loader. | **Gated** | Every build targets glibc 2.22 and runs all tests in pinned SLES 12 SP5 userspace (container): [SLES gate](RUST-SLES-GATE.md). A real SLES installation is not part of testing. |
| Toolchain | Rust 1.99.0, cargo-libc 0.2.4; locked, offline crate sources. | **Gated** | [rust-platform.json](../scripts/rust-platform.json), [SLES gate](RUST-SLES-GATE.md#pinned-inputs). |
| Build modes | Production and NFS-qualification executables, debug and release. | **Gated** | Both modes on every PR. Qualification executables are refused by the installer. |

## Storage

| Area | What is supported | Status | Evidence and limits |
|---|---|---|---|
| Mover state (SQLite, locks) | A private local directory (mode 0700) on ext-family, tmpfs or overlay. NFS state is always refused. | **Tested** | [Operator guide: local ownership](RUST-OPERATOR-GUIDE.md#local-ownership-and-refused-starts). Container admission does not prove persistence for a deployment. |
| Source and destination on local disks | Local filesystems for both roots. | **Tested** | Real-service API and SLES-gate tests. |
| Source or destination on NFS | Built and lab-tested in NFS-qualification builds only. | **Open** (P05) | **Production NFS is disabled.** [NFS qualification](NFS-QUALIFICATION.md) records the finite lab matrix; server durability, delayed RPC settlement and physical NAS behavior remain unqualified. |
| Power loss, host reboot, NAS restart | State and custody are designed to survive them. | **Open** | Not physically qualified: [restart runbook](RUST-RESTART-RUNBOOK.md), [release closure](RUST-RELEASE-CLOSURE.md). |

## Network and access

| Area | What is supported | Status | Evidence and limits |
|---|---|---|---|
| Producer ingress | Native HTTPS with TLS 1.2 or 1.3 and an approved client certificate per generator. | **Tested** | [HTTPS setup](NATIVE-HTTPS-SETUP.md), [clients](NATIVE-HTTPS-CLIENTS.md): tested with curl 7.88.1 and OpenSSL 3.0.22 on the client. Other clients need their own checks. Production remote exposure is open (P02-03). |
| Loopback HTTP producer | Explicit trusted-loopback mode for local use. | **Tested** | Never a fallback for TLS errors. |
| Protected Unix-socket ingress | Development-only transport. | **Tested** (development) | [Operator guide](RUST-OPERATOR-GUIDE.md#opt-in-protected-local-http-ingress); not a shipping profile. |
| Admin dashboard | A separate HTTPS listener, username/password sign-in, up to four browser connections. | **Tested** | [Admin HTTPS setup](ADMIN-HTTPS-SETUP.md), [account setup](ADMIN-ACCOUNT-SETUP.md). No formal browser support list; development checks used Microsoft Edge (headless). |
| Operator controls | Host-local status, stop and operator commands under the service account. | **Tested** | [Operator guide](RUST-OPERATOR-GUIDE.md). |

## Installation and lifecycle

| Area | What is supported | Status | Evidence and limits |
|---|---|---|---|
| Offline bundle | A verified bundle with the production executable, sources and checksums; installs without changing service state. | **Tested** | [Offline install](OFFLINE-INSTALL.md), [increment 109](RUST-INCREMENT-109.md). The shipping package, account and confinement are open (P09). |
| systemd | A candidate unit (`Restart=no`, no automatic SIGKILL); start by hand. | **Open** (P09) | Do not enable at boot until the unit, account and storage profile are qualified: [offline install](OFFLINE-INSTALL.md#optional-systemd-activation). |
| Restart and shutdown | A stop deadline (default 60 s), recovery from saved state, no adoption of old workers. The deadline does not bound actual worker exit: when it expires with workers still running (for example in blocked storage I/O), stop reports `ShutdownIncomplete` and the service keeps custody until they really exit. | **Tested** | [Restart runbook](RUST-RESTART-RUNBOOK.md) (DOC-04). |
| Upgrade | Schemas 11-17 migrate offline to 18; unfinished legacy handoffs must finish first. | **Tested** | [Offline migration](OFFLINE-STATE-MIGRATION.md). Rollback and reverse migration are not qualified. |
| Cutover from the old service | Planned. | **Open** (P09, P12) | [Release closure](RUST-RELEASE-CLOSURE.md). |

## Features that change data

| Feature | Default | Status | Notes |
|---|---|---|---|
| Move mode (`delete_source_after_commit`) | Off | **Tested** (implementation) | Enabling it on a production host deletes source copies and needs a separate decision: [operator guide](RUST-OPERATOR-GUIDE.md#move-mode-removing-the-source-after-delivery). NFS sources are not qualified, and the release closure still lists RC-18/19 cleanup obligations as open. |
| Confirmed data deletion from the dashboard (`admin_ingress.allow_data_deletion`) | Off | **Tested** | One job per confirmed request; see increments [143](RUST-INCREMENT-143.md) and [160](RUST-INCREMENT-160.md). |
| History clear | Available | **Tested** | Forgets job records and leaves files in place. |
| Expected-size checking (`check_expected_sizes`) | Off | **Tested** | [Producer quickstart](PRODUCER-QUICKSTART.md). |

## Related

- [First-release scope](RUST-FIRST-RELEASE.md) and
  [release closure](RUST-RELEASE-CLOSURE.md): the eight gates and remaining
  work.
- [Producer quickstart](PRODUCER-QUICKSTART.md) (DOC-01),
  [consumer guide](CONSUMER-GUIDE.md) (DOC-02),
  [operator guide](RUST-OPERATOR-GUIDE.md) (DOC-03),
  [restart runbook](RUST-RESTART-RUNBOOK.md) (DOC-04).
