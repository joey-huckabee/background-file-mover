# Rust increment 43: configurable shutdown and bounded local control

Implementation increment on `feature/rust-transfer-coordinator`, 2026-10-17.
Implements the service controller slice of the [single-host contract](NFS-OWNERSHIP-FENCING-CONTRACT.md).
Production NFS and source deletion remain disabled. Registration, offline repair,
cross-host takeover, complete state-layout validation and systemd deployment
qualification remain deferred/open as previously recorded.

## Service lifecycle and local commands

`shutdown_wait_seconds` is now accepted by strict startup configuration. Omission
means 60; integer values 1 through 3600 are accepted. Zero, negative, fractional,
string/null/boolean and out-of-range values refuse. It changes lifecycle waiting,
not job retries, missing-file windows, admission sampling or cleanup authority.
No hot reload or unlimited/disabled wait exists.

The same executable provides `--status CONFIG.json` and `--stop CONFIG.json`.
They read/validate configuration and use the existing local state directory;
they do not create/open SQLite or traverse source/destination roots. A noncreating
nonblocking guard probe distinguishes absent/free/held ownership. No PID file,
client PID signal or new dependency is used for control.

The daemon creates mode-0600 `control.sock` under its protected local state parent,
only after acquiring the shared instance guard and before source bootstrap.
A separate native thread handles bounded, strict version-1 requests, independently
of the async executor and SQLite/transfer threads. It retains the guard through
normal draining and existing confirmed worker waits. Each request validates the
guard; unsafe/foreign/symlink/regular control names refuse startup and remain
untouched. A stale owned socket can be replaced only under exclusive local guard
ownership. Normal cleanup removes only the original matching socket, retaining
instance.lock permanently. Socket paths must fit the system Unix pathname limit.

The first stop request, SIGTERM or SIGINT fixes a monotonic deadline in the
running daemon. Repeated requests/signals never reset it. The client's current
config cannot replace that live budget. The coordinator stops admission/new
queued commands, requests existing supervised worker termination and drains;
in-flight work retains its existing uncertainty/retry/review rules. There is no
forced guard release, worker abandonment or conflicting replacement.

Stop observes the original coordinator's PID plus process-start identity and
release of the original unchanged local guard before reporting `Stopped` (including a reaped/dead process
or zombie with closed descriptors). Process identity is an observation, not
ownership authority. Subsequent polling is pinned to that controller instance;
it cannot stop a replacement daemon. At the first deadline, exit 2 reports
`ShutdownIncomplete`, remaining zero and **shutdown incomplete; restart blocked**.
The daemon/workers can remain live and keep ownership. A later independent status
can observe completion. The foreground daemon is not promised to return shell
control by that deadline; run the separate stop command.

Status reports `Starting`, `Running`, `Draining` or `ShutdownIncomplete`, with the
live configured budget, optional remaining milliseconds, coordinator identity
and up to 64 observed child PIDs (a bounded snapshot, not a complete worker
inventory). `NoActiveOwner` means an absent/free valid guard with no known active
instance, not settled NFS I/O or readiness. A held guard with no responding
controller, including orphan workers or a one-shot effect command, reports
`OwnerUnavailable`, exit 2, preserving the restart block. Unsafe state/IPC/config
errors exit 1. Successful status and clean/no-active-owner stop exit 0. Status on
an expired drain exits 2. Source initialization and single-file transfer retain
guard exclusion; they do not become managed daemon/controller instances.

Local request/response I/O has a 500 ms client budget (100 ms per server read/write and fixed frame limits).
Local configuration/metadata/process inspection assumes usable local config,
state and proc filesystems, with controller and daemon in the same PID namespace; it does not make arbitrary disk failures or misconfigured NFS state
cancellable. Stop polling is additionally bounded by the daemon's first deadline,
conservatively accounting for the initial exchange. No transport failure, elapsed
wait, free local lock or process exit proves NAS RPC/writeback settlement.

## Selected acceptance cases

SH-05 configuration omission/bounds/types; selected SH-06 clean stop and
same-state restart; SH-08 repeated stop plus signal/config-edit behavior; and
local delayed-drain portions of SH-07 are covered. The qualification-only
shutdown_drain rendezvous allows up to 90 seconds while the daemon retains
ownership and the executor is synchronously blocked. Production compiles this
control inert. Tests measure both a short two-second budget and the actual
omitted 60-second deadline, reject replacement after timeout, then release the
fixture and observe eventual exit/restart. This is a delayed local drain, not an
uncancellable NFS syscall or storage fence.

Other cases cover no-state observation without creating a guard/database, held
ownership without a controller, a silent endpoint with bounded refusal, invalid/
oversize/foreign-instance control messages and impossible response budgets/phases,
preservation of unrelated named files, and status/stop with the source path hidden and destination unavailable.
Existing guard inheritance, job retries/review and retained-source tests remain.

Actual uninterruptible NFS workers beyond the short/default deadlines, every
in-flight drain boundary, live default changes across failure/reboot and actual
SLES-version systemd/user authorization remain qualification obligations. SH-09,
full SH-06/07/08, slow/concurrent control-peer load and the remaining
ownership/remote-settlement gates stay open.
No service unit, new remote API, registration or production NFS profile is enabled.

## Validation

Production gate `20261017T045307Z-95a26796` passed, exit 0: 194 tests per
profile, 20 audited executables, six ELF negative controls, formatting and Clippy
with warnings denied. The dependency graph remains 42 packages; maximum required
symbol version is GLIBC_2.18, below the GNU/glibc-2.22 target. All 20 artifact
hashes match the report, the complete 60-file archived source inventory/content
matches current Rust sources, and cleanup has no errors.
[Production evidence](RUST-SLES-EVIDENCE.json) records the pinned inputs/results.

Qualification gate `20261017T045309Z-f98126bd-nfs-qualification` passed, exit 0:
195 tests per profile, 20 audited executables, six negative controls, formatting/
Clippy, the same 42 packages and maximum GLIBC_2.18. All artifact hashes and the
complete 60-file source inventory/content match current sources/report; cleanup
has no errors. [Qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json)
records the separate build mode/features. The actual omitted/default timeout
passes the asserted 59–63-second window in both profiles while the daemon remains
alive holding ownership, then exits only after the qualification release.

Both gates use root Podman in WSL2, cargo-zigbuild for GNU/glibc 2.22 and exact
audited target execution as UID/GID 1000 with eager relocation in pinned actual
SLES 12 SP5 userspace. No actual SLES host or host-only Rust build/test is used.
This does not qualify old kernels/CPUs, actual NAS hardware, storage durability
or systemd lifecycle.

Controlled fixture `nfs-20261017T051627Z-eca582e6` passed with these exact final
artifacts; [saved evidence](RUST-NFS-LIFECYCLE-EVIDENCE.json) records the binary
hashes, cases, mounts/kernel, controller snapshots and cleanup. All six transfer
cases (NFS source, NFS destination, both on NFS; debug/release) pass original
handoff/replay, producer path reuse, retained-source, payload/manifest hash checks,
then local `Running` status and clean `Stopped` for the same instance identity.
Files are bounded at 18 bytes, 2 MiB + 17 bytes and empty, with a nested name.
Both-NFS cases use one export; separate-share deployment remains unqualified.

While real hard-NFS metadata/bootstrap was pending and HTTP readiness/SQLite
were unavailable, production local status returned `Starting` with the actual
single bootstrap child in 0.859 seconds, including Podman execution overhead.
Retained SIGTERM/confirmed bootstrap child exit before server restoration,
OS inherited-lock/interruption/outage checks and all 12 mounted-NFS state-parent
refusals also pass. This is not an actual uncancellable-worker deadline test.
Runtime death/long-outage, two-client ownership and capacity-storage suites were
not selected. Earlier reports retain their original scope.

The fixture uses pinned SLES/glibc 2.22 userspace on kernel
`6.18.33.2-microsoft-standard-WSL2`. Recorded hashes of the final main, baseline
and binding drivers match. Cleanup has no errors: no containers or disposable
fixture networks/volumes remain; only the preexisting toolchain/registry caches
and default network remain. Production NFS and source deletion stay disabled.

Intermediate snapshots are superseded by response-budget/phase
validation and original-guard completion checks. An earlier production run also
hit a transient Podman SSH transport failure during artifact copy; engine health
recovered, and only complete final-source passing reports are promoted.

The [scenario catalog](RUST-SCENARIOS.md) and [operator guide](RUST-OPERATOR-GUIDE.md)
explain the local controller, retained ownership and distinct process/storage
outcomes. The future-only [roadmap](ROADMAP.md) retains remaining qualification
and deferred capabilities instead of completed implementation tasks.

Final documentation checks pass for 15 changed Markdown files, 474 local targets,
table structure and JSON examples. The 95 stable SC IDs, six DOC items, eight
release gates, 14 SH cases and 18 NF mappings are retained; requirement IDs and
status annotations are unchanged. Generated trace consistency, both fixture
scripts' syntax and Git whitespace pass. Complete final archives and all 40
artifact hashes were rechecked after the fixture; Rust sources still exactly
match both passing 60-file snapshots.
