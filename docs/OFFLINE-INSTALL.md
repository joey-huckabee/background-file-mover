# Produce and use the offline installation bundle

This bundle installs the current **Rust prototype**, not a production-approved
release. It is for Linux x86_64 with OS glibc >= 2.22 and the required OS
libraries. Exact userspace testing uses pinned SLES 12 SP5. Production NFS,
remote ingress, physical deletion and automatic cleanup remain disabled.
The systemd file is a candidate requiring deployment qualification; installing
the bundle does not enable/start a service or close any release gate.

## What is included

- The exact **production-mode release executable** from a passed debug/release
  Cargo-libc/SLES gate. Qualification executables are refused.
- Internal `SHA256SUMS`, an external archive digest, `bundle.json` provenance,
  the gate report and its validated Rust source archive.
- All locked external crate archives with Cargo.lock checksum verification,
  their available license/notice texts, project license and Rust toolchain
  copyright/license texts. Complete tracked project source is also included.
- Configuration and binding-marker examples; current documentation and recovery
  runbooks; a candidate native systemd template; verification/install scripts.

The bundle does **not** include a replacement glibc/loader, vendor RPMs, Podman,
Rust/compiler images, live configuration, credentials, enrollment receipts or
database/WAL files. The target OS supplies `libc`, `libm`, `libpthread`, `librt`,
`libdl`, `libgcc_s` and its standard x86_64 loader. `bundle.json` records the
executable's actual required SONAMEs. These are present in the tested SLES image.
If absent on another installation, provide compatible vendor packages using
approved offline installation media; verification refuses unresolved libraries.
Never copy a workstation's glibc over the target OS.

## Produce the bundle on the prepared build host

Use Python 3.11+, Git, Podman, the pinned cached builder/runtime and the existing
locked Cargo registry cache. No new Python packages or downloads are needed.
Use the native WSL clone described in [the agent workflow](AGENT-WORKFLOW.md).

1. Commit all packaging/source/documentation work. The builder requires a clean
   checkout so its recorded Git commit matches the included source and guides.
2. Run the required gates sequentially, or reuse retained passing reports only
   when their **entire Rust source inventory and pins** still match HEAD:

   ```sh
   python3 scripts/check-rust-sles.py --offline
   python3 scripts/check-rust-sles.py --offline --qualification
   ```

   Preserve both reports. The package command takes the **production** report;
   the qualification artifact must not be distributed as the service executable.
3. Build, substituting the actual production run directory:

   ```sh
   python3 scripts/build-offline-bundle.py \
     --gate-report rust/validation/PRODUCTION-RUN/report.json
   ```

   The default output is `rust/validation/bundles/`, ignored by Git. Use
   `--output-dir /absolute/output/directory` to place it elsewhere. `--registry`
   can specify an existing Cargo registry directory; otherwise its prepared
   Podman volume is used. The exact cached builder is opened without networking
   only to copy Rust license material; it must match the gate's image ID.
4. Save both the `.tar.gz` and `.tar.gz.sha256`. The command refuses existing
   output names. Repeating with the same committed inputs/report/cache in a
   different output directory must produce identical archive bytes. This is
   reproducibility of packaging retained artifacts, not a promise that arbitrary
   future toolchain/image rebuilds reproduce the executable.
5. Transfer the two files to the disconnected target. Send the digest through
   a trusted channel as well: a checksum supplied beside a compromised archive
   does not authenticate its publisher. No signing infrastructure is supplied.

Changing Rust source, pins or the retained binary requires fresh gate evidence.
Missing/corrupt cached crate archives fail packaging rather than fetching them.
Packaging does not copy or recreate historical ignored raw validation packs.

## Verify on the disconnected target

Required utilities are `/bin/sh`, tar/gzip, GNU coreutils (including sha256sum,
mktemp and mv), find, awk, grep, cmp, getconf and ldd. Installation needs no Rust,
Cargo, compiler, internet access or Python. Use a private trusted extraction
directory, as the executable will be run during verification.

```sh
sha256sum -c file-mover-VERSION-linux-x86_64.tar.gz.sha256
tar -xzf file-mover-VERSION-linux-x86_64.tar.gz
cd file-mover-VERSION-linux-x86_64
sh verify.sh
```

Replace `VERSION` with the actual filename printed by the producer. Verify the
external digest **before extraction**. The internal verifier rejects missing,
changed, extra or nonregular files, checks Linux/x86_64 and glibc, checks dynamic
relocation and runs the side-effect-free `--check-platform` smoke check. It does
not acquire source/destination roots or open SQLite. An architecture/library
failure is not permission to substitute another binary or remove checks.

## Install without changing service state

Choose a **new** absolute versioned directory whose parent already exists and
is writable by the installer. Paths must be canonical, without symlink parents,
spaces, shell characters or dot components. Example, with appropriate authority:

```sh
sh install.sh /opt/file-mover/releases/ACTUAL-BUNDLE-NAME
/opt/file-mover/releases/ACTUAL-BUNDLE-NAME/bin/file-mover --check-platform
```

The installer verifies first, copies into a temporary sibling, verifies again
and publishes without replacing an existing destination. It does not create
the parent, a service account, active configuration, state directories, source
markers or an enrollment receipt. It never invokes systemctl. Installed examples
are inert. Running `sh /absolute/install-directory/verify.sh` rechecks the install.
Protect the installation from modification by the service account.

Installation to an existing destination is an error; choose another versioned
directory. Do not use the installation path as the state directory. Logs/state
are not written beneath the installation by these scripts. Root access is only
needed when your chosen parent or later service administration requires it.

## First use on genuinely new local storage

Run the mover as the intended service account. Native deployment account and
filesystem permissions must be provisioned by an authorized administrator.
Existing installations must use the upgrade section instead; never create a
fresh database to take over previously used sources.

1. Copy `config/local.example.json` to a protected local configuration path and
   edit the bind port, generator, absolute roots, local state path and binding
   IDs. Retain loopback binding and `filesystem: local` for this prototype.
   Choose exclusive, genuinely unused source and destination scopes and exclude
   all old movers/writers. A sample's identity strings are examples, not proof
   of ownership. Use a private mode-0700 state parent on persistent local disk.
2. Provision each root's private `.file-mover` directory as mode 0700, owned by
   that account. Before doing so, establish that it is a new scope: do not replace
   or adopt an existing private namespace. Provision the role's binding JSON
   marker with exactly the corresponding configured binding, mode 0600, and an
   empty, new mode-0600 regular `coordinator.lock`. The package's
   `config/source-binding.example.json` and destination example match the
   unedited sample only. A service-account shell can create a **new** lock with
   noclobber: `(umask 077; set -C; : > /YOUR/ROOT/.file-mover/coordinator.lock)`.
   Do not truncate an existing lock or invent a source enrollment receipt.
3. Initialize **once**, for that unused source and new original database:

   ```sh
   /absolute/install-directory/bin/file-mover --initialize-source /local/config.json
   /absolute/install-directory/bin/file-mover /local/config.json
   ```

   Run the second command in the foreground for initial diagnosis. The mover
   creates its paired enrollment receipt. Preserve it with the original database.
   A created-but-unactivated receipt or any refusal needs diagnosis, not blind
   initialization retries. See [enrollment behavior](RUST-INCREMENT-27.md) and
   [enrollment failure handling](RUST-OPERATOR-GUIDE.md#diagnostics-and-situations-that-must-stay-blocked).
4. Check local status/readiness and follow the implemented prototype submission
   and consumer rules in the [operator guide](RUST-OPERATOR-GUIDE.md). The pending
   UUID/dashboard API schemas are not the executable's current producer format.
   A successful health check does not mean files are delivered.

There is no automatic repair, populated re-enrollment or cross-host takeover.
Storage continuity and private ownership remain provisioning prerequisites.

## Optional systemd activation

`systemd/file-mover.service.in` is a **candidate**, not the C++ reference unit or
a claim of production qualification. It uses unit-scoped signals, control-group
termination and no automatic final SIGKILL. It deliberately has `Restart=no` for
explicit prototype activation; the shipping restart/account policy remains open.
There is no global `ExecStop --stop`, which could stop a foreign owner on old
managers. `TimeoutStopSec=75` assumes the default 60-second application budget;
set it above the actual configured budget and review the chosen manager's behavior.
`Type=simple`/active does not establish mover readiness.

An authorized administrator must substitute the real immutable installation
path, existing service user/group and protected local config path for the three
`@...@` placeholders. Inspect the result; never install unresolved placeholders.
Install the reviewed unit under the actual service name, then run:

```sh
systemctl daemon-reload
systemctl start file-mover.service
systemctl status file-mover.service --no-pager
journalctl -u file-mover.service -n 100 --no-pager
```

Do not enable at boot until the chosen unit/account/storage profile has been
qualified. No installer action enables it. Exact vendor systemd/cgroup/kernel,
confinement and persistence qualification remain release work.

## Upgrade, failed restart, rollback and removal

- **Upgrade:** verify/install to another versioned directory first. Use the
  original service/account/config/state. Stop the old owner normally, confirm
  all old workers/threads exited and follow the
  [restart runbook](RUST-RESTART-RUNBOOK.md). Only then switch the unit's ExecStart
  to the new path, reload and start. Never mix old workers and new binaries.
  Preserve the old executable and all original state/custody.
- **Restart refuses or times out:** do not delete locks, epochs, WAL, receipts
  or partials. Restore the underlying problem; use the runbook's status, worker
  inspection and explicit manager recovery steps. A new binary cannot adopt a
  surviving worker. NoActiveOwner alone is not remote-effect settlement.
- **Rollback:** changing the executable back is allowed only for a separately
  verified compatible schema/protocol pair after old exit. Older binaries may
  reject schema 11. This package does not qualify arbitrary downgrade, reverse
  migration or restoring a stale database. Keep refused state for review.
- **Removal:** stop the service and confirm old exit before disabling/removing
  its unit or removing a retired code directory. Keep active configuration,
  original state/database/WAL/lifetime records, source/destination roots and
  enrollment. No automated uninstall deletes them. Removing code does not clear
  job history or delete data. Do not remove a path still referenced by a unit or
  running worker; preserve a needed compatible rollback binary.

For linked code/configuration references, extract `sources/project-source.tar.gz`
into a separate new directory and read its `docs/`. Historical raw packs remain
on the evidence host, not in this source archive. The binary's original validated
Rust source and locked external crate sources are separately included.

## Validation record

[Increment 109](RUST-INCREMENT-109.md) records actual packaging/installation tests,
artifact digests and remaining limits. Passing packaging tests does not freeze
the pending API or approve a production deployment. No target account, service,
mount or operational database is changed by building the bundle.
