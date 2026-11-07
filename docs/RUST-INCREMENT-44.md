# Rust increment 44: local SQLite state-file admission

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Behavior

Before source bootstrap or SQLite access, effect-capable starts inspect the actual
SQLite database and its `-wal`, `-shm` and `-journal` recovery names under the
private local state parent. This applies to normal service startup,
`--initialize-source` and `--transfer-one`. Existing candidates must be regular,
owned by the mover UID, single-link, owner-readable/writable, without special
permission bits or group/other write permission. Existing read permissions such
as 0644 remain accepted inside the protected 0700 directory; modes are preserved.
Symlinks, hard-link aliases, directories, sockets, unsafe modes and foreign owners
refuse. A refused start may create the normal permanent empty instance guard;
existing database/recovery candidates remain unchanged. Recovery files without
the database also refuse; they are never adopted, removed, truncated or used to
create replacement state.

Local `/proc/self/mountinfo` is read with a 4 MiB bound and decoded using the
kernel's escaped-path representation before candidate metadata/open calls.
Individually mounted files refuse, including local bind mounts; parent filesystem
checks alone cannot establish file locality. The same mount refusal covers
`instance.lock` and `control.sock`. Missing, unreadable, empty, oversized or
malformed inventory shape/path escapes fail closed. Open/named identities,
device and admitted local filesystem type are checked for existing SQLite candidates without reading
payload bytes. No openat2/new-kernel dependency or package is introduced.

After successful source bootstrap, immediately before Store::open, a missing
database is created exclusively with mode 0600 and file/parent synchronization.
Existing files are never chmodded, truncated or replaced. SQLite creates and
recovers its own sidecars. The store also enables native SQLITE_OPEN_NOFOLLOW for
read/write and read-only opens. Full layout admission belongs to guarded executable
entry points; the low-level Store API still requires caller-owned state custody.
Existing schema, transactions, acceptance/replay, delivery retries and review
rules are unchanged.

Preflight inspection descriptors are closed **before** SQLite opens the database.
There is no additional open/close of the database while SQLite holds POSIX locks:
closing an unrelated descriptor for that inode could invalidate process locks.
Local --status/--stop continue to inspect ownership/control only; they do not open
or validate SQLite files and do not become database repair commands.

## Acceptance and evidence

Production gate `20261017T111519Z-1ecdab26` passed, exit 0, with **200 tests
per profile**. Qualification gate
`20261017T111519Z-8fa9a462-nfs-qualification` passed, exit 0, with **201 tests
per profile**. Each gate audits 20 executables across debug/release, runs six ELF
negative controls, formatting and Clippy with warnings denied, and executes the
exact hash-checked target binaries as UID/GID 1000 with eager relocation in
pinned actual SLES 12 SP5 userspace. Builds use cargo-zigbuild for x86_64 GNU/glibc
2.22 on native container storage in root Podman/WSL2. Both gates retain maximum
GLIBC_2.18, the same 42 external packages/configuration/features, matching hashes
for all artifacts and the complete 60-file archived source inventory/content,
and no cleanup errors. No host-only Rust build/test is used.

[Production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json) preserve the
separate build modes and exact inputs/results. Initial pre-guard/control-mount
snapshots `20261017T111009Z-21e18760` and
`20261017T111149Z-60d70ee1-nfs-qualification` also passed, but are superseded by
the final runs above. An initial sandboxed attempt could not reach the local
Podman socket; the approved root connection completed the required gates.

The first fixture `nfs-20261017T113841Z-37a83b7a` passed six normal transfers
and 12 NFS-state-parent refusals, then failed during wrong-owner **setup**, before
the new admission matrix: fixture root has SYS_ADMIN but no DAC override/CHOWN,
so it cannot chown through the mover's private directory. Cleanup completed
without errors. The corrected harness prepares foreign files through engine-side
copy and uses temporary traversal permissions only during setup/cleanup; every
mover attempt keeps UID/GID 1000, private 0700 state and the existing capability
configuration. Separate disposable setup/audit and bind-mount cleanup probes pass.

Corrected fixture `nfs-20261017T114805Z-60f221d4` passed, exit 0, with no
cleanup errors. [State-layout fixture evidence](RUST-NFS-STATE-LAYOUT-EVIDENCE.json)
records the final audited artifacts and current driver/helper hashes:

| Admission situation | Cases | Result |
|---|---|---|
| Foreign UID for database/WAL/shared-memory/rollback-journal files | 48 | Refused before source/SQLite access |
| Individually NFS-mounted database/WAL/shared-memory/rollback-journal/guard/control names, server stopped | 72 | Refused from local mount metadata, without waiting for NFS restoration |

The full Cartesian matrix covers all three effect commands, both build modes and
both profiles. Maximum observed refusal time is **0.953 seconds**, including
Podman execution startup, below the eight-second fixture bound. Ten fixture
snapshots preserve SHA-256, device/inode, UID/GID, mode and link count; their local
parents remain private 0700 during every mover attempt. File contents and
identities/permissions match before and after all refusals. Six fixture-only bind
mounts are unmounted with RPC service restored; no mover capabilities are added.

The same run passes six normal NFS transfer/lifecycle cases (three directional
layouts in both profiles), 12 NFS-state-parent refusals, inherited OS-lock,
isolated hard-NFS startup/signal/interruption and restoration checks. Local status
reports Starting with one real bootstrap child in **0.829 seconds** including
Podman overhead; SIGTERM confirms child exit before restoration with no SQLite
or readiness. This run does not select the broader runtime-death/long-outage,
cross-client ownership or capacity suites. Both-NFS baselines use one export;
separate shares and actual NetApp/Isilon deployment remain pending. The fixture
uses hard NFSv4.1/noac and kernel `6.18.33.2-microsoft-standard-WSL2`, not an old
SLES kernel or physical NAS/power-loss qualification.

Tests cover all four SQLite names against symlink/hardlink/type/mode refusals,
orphan recovery names, reserved SQLite names, mount-path escape decoding, private
creation, preserved legacy modes, and all three effect entry points with missing
source paths. A real coordinator death retains WAL; original-state restart must
recover the accepted job and idempotent 202 replay. Native SQLite read/write and
read-only symlink opens are refused independently of the application guard.

The retained NFS fixture adds actual individually NFS-mounted database, WAL,
shared-memory, rollback-journal, ownership-guard and control names with the server
stopped, plus wrong-owner SQLite files. It checks all three effect entry points
in both profiles/build modes, prompt refusal, unchanged bytes/identity/permissions,
and no source/control effects. Existing normal-transfer/lifecycle and startup
boundary checks remain part of the fixture.

Documentation validation checks 442 local Markdown targets, unchanged/unique
95 SC, six DOC, 14 SH, 18 NF and eight FR identifiers, JSON/Python parsing,
trace-matrix freshness and whitespace. After all gates, fixtures and setup probes,
no validation containers remain; only the two pre-existing toolchain/registry
cache volumes and default Podman network remain.

## Scope and next work

This is cooperative same-host fixed-state admission, not an SQLite VFS replacement
or protection against a hostile same-UID/root process changing files or mounts
between inspection and use. Mount namespaces must expose truthful local proc
metadata. Default filesystem admission remains ext-family, tmpfs and overlay;
container tmpfs/overlay evidence does not establish production persistence.

Do not change permissions, remove recovery files, replace the lock or recreate
state to bypass refusal. Preserve the original database and sidecars, configuration
and private transfer areas; verify deployment provisioning while stopped. Repair,
backup restore, cloned-state adoption and takeover remain deferred.

Selected SH-01/13 cases gain evidence; actual systemd/account policy, remaining
guard/death/shutdown cases, physical storage/power loss, real hard-NFS operations
beyond stop deadlines, delayed effects and same/separate-share deployment remain
open. SLES userspace on the modern shared WSL kernel does not qualify an old kernel
or NAS durability. Production NFS and source deletion remain disabled. E6 and
registration remain deferred. Maintain SC-095 and DOC-03/04/05.

## References

SQLite documents [native no-follow open](https://sqlite.org/c3ref/open.html) and
[WAL recovery/lifetime](https://www.sqlite.org/wal.html). The service preserves
recovery files for SQLite rather than treating leftover WAL as disposable.
