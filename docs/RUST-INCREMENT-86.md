# Rust increment 86: establish NFS server-recovery fixture capability

## Scope and acceptance

First prove what the approved container fixture reproduces. Add a retained
native capability runner with an owned named-volume export, separate from the
earlier volatile tmpfs child exports. Test NFSD stop/start and abrupt stop/start
of the same server container, each on source and destination export roles.
Keep production NFS and post-delivery source deletion disabled. Rust source,
dependencies, API/202, retry/review, ownership and shutdown deadlines are unchanged.

Each native probe retains its open FD across the event. Independently prove
initial FILE_SYNC data, retained backing file while stopped, actual blocked
pwrite/fsync and resumed original-handle write/sync/readback. Measure container,
namespace, kernel boot, session and write-verifier continuity independently.
Record raw success/errors and unknown compounds; do not infer server-reboot,
physical durability, unstable-data recovery or mover fault safety from labels.

Run both mandatory SLES/glibc 2.22 gates, retain exact acquisition/probe sources
and perform independent raw-proof/build/cleanup audits. Follow the
[step-by-step lab](NFS-SERVER-RECOVERY-LAB.md).

## Results

Final run `server-recovery-20261020T125911Z-b656baec` passes all four native
cases and exits 0 with cleanup_errors=[]. It retains 336,081 exact raw report
bytes and nine acquisition-source snapshots. No Rust mover is executed by the
capability runner and **zero mover server-recovery cases are qualified here**.

| Facility event | Export role | Original FD / opaque handle / backing inode | Successful session and write verifier | Result |
|---|---|---|---|---|
| NFSD threads 2 → 0 → 2 | Source | Retained | Both changed | Passed |
| NFSD threads 2 → 0 → 2 | Destination | Retained | Both changed | Passed |
| Same container SIGKILL / exit 137 / start | Source | Retained | Both changed | Passed |
| Same container SIGKILL / exit 137 / start | Destination | Retained | Both changed | Passed |

All four probes are observed D-state in actual fsync (74) on the original FD
while the selected facility is stopped. Independent read-only volume observation
retains the exact original 4096 `A` bytes and backing device/inode/link/size while
stopped. Each original process resumes without remount/reopen/replacement,
completes write/fsync/readback with unchanged client identity, and the independent
backing file contains 4096 `B` bytes at the same original inode. All eight traced
fsync calls return zero and all four probes exit normally.

All four wire windows prove initial and recovered full-count FILE_SYNC WRITE
success on the same opaque handle. Actual vectors are SEQUENCE/PUTFH/WRITE,
optionally followed by GETATTR. The raw successful SEQUENCE reply echoes its own
request's session/sequence/slot. Each event records two BADSESSION (10052)
responses, then a successful new session and changed write verifier. The 174
raw records include 82 unsupported/unknown records retained explicitly; no
complete OPEN/reclaim/session-creation decoding or full lease-recovery claim
is inferred from them. See [RFC 8881](https://www.rfc-editor.org/rfc/rfc8881.html#section-15.1.11.1)
for BADSESSION and [WRITE verifiers](https://www.rfc-editor.org/rfc/rfc8881.html#section-18.32).

Both NFSD cases preserve container PID/start time; both container cases prove
SIGKILL exit 137 and changed PID/start time before recovery. In **all four cases
the network namespace inode and VM kernel boot ID remain unchanged**. The
container lifecycle therefore does not establish fresh-network-namespace or
VM/NAS reboot behavior. Session/verifier changes are independently observed
protocol state changes, not guessed from a process/container label.

## Failed acquisitions and fixture corrections

Retain initial `server-recovery-20261020T123719Z-15e3fab8` and second
`server-recovery-20261020T124744Z-49eec43d` as FAILED, including their exact
sources, raw relay state, traces, cleanup failures and manual rescue records.
[Initial evidence](RUST-NFS-SERVER-RECOVERY-INITIAL-EVIDENCE.json) records the
original private backend 10.89.0.2 versus manually observed restarted 10.89.0.5,
and native timeout. Restoring only the owned server's original address lets its
probe exit and hard mounts unmount normally. Independent review also rejects
its stale mid-run state file and Windows/WSL monotonic-clock comparison.

The repeated acquisition pins the private IP, checkpoints the complete live
trace without reset and timestamps restoration from the observed relay clock.
[Second evidence](RUST-NFS-SERVER-RECOVERY-SECOND-EVIDENCE.json) retains a separate
Podman stop-controller PID timeout/stopping-state failure. Explicit wait confirms
exit 137 before manual restart; original native I/O and normal unmounts recover.
All owned resources are then removed after verified probe exit and normal
unmounts, without forced/lazy unmount or host/NAS configuration changes.

The final run uses SIGKILL plus explicit confirmed exit before restart. Neither
failed acquisition, including its earlier runner-reported NFSD successes, is
retroactively accepted as final qualification. No service deadline is changed.
The fixture relay gains a read-only checkpoint control; normal observation and
withholding behavior remain available. New native C and server-shell helpers
are fixture-only, not shipping executables or Rust dependencies.

## Mandatory compatibility and independent audit

| Build mode | Fresh run | Exact debug / release target tests | Audited ELF artifacts |
|---|---|---:|---:|
| Production | `20261020T123438Z-001c4e03` | 211 / 211 | 20 |
| Qualification | `20261020T123450Z-1941e981-nfs-qualification` | 212 / 212 | 20 |

Both processes exit 0 with no cleanup error. The
[production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) gates retain locked
cargo-zigbuild GNU/glibc 2.22, exact target execution in pinned SLES userspace,
loader/library/symbol audits, six negative controls per build mode,
formatting/Clippy and the unchanged 42-package dependency graph. There remains
one shipping executable; counts include tests and both profiles.

The independent audit verifies all 62 current Rust entries in both fresh
archives, all forty fresh artifact hashes and ELF reports, all nine captured
acquisition sources, exact fixture-probe bytes/ELF policy and the complete raw
request/reply evidence. It checks lifecycle and actual exit of the stopped server
process, security, clock identity, trace prefix checkpoints, original file
identity, full-count stable writes and raw session echo before comparing
sessions/verifiers. All 36 actual-proof corruption controls reject invalid
server bytes/identity, pending FD/state, wire hashes, missing recovery writes,
missing checkpoints, wrong restore clocks or altered omitted session fields.
Seven RPC decoder regression tests pass. Both failed acquisition/rescue packs
are independently hash-checked and remain labeled FAILED.

Final inventory at `2026-10-20T13:05:27.418181+00:00` confirms no containers on
either engine, only original rootful cache volumes/default network and unchanged
unrelated default-engine volume metadata/networks. No resource is silently
force/lazy-unmounted or left as a passing cleanup. The exact verifier, unchanged
SLES auditor, inventory collector, native probe and fresh source archives are
retained with [raw evidence](RUST-NFS-SERVER-RECOVERY-EVIDENCE.json) and
[input/audit evidence](RUST-NFS-SERVER-RECOVERY-INPUT-EVIDENCE.json).

## Next selection and limits

This establishes repeatable native NFSD and same-container termination/start
capability on two root-squashed buffered exports sharing one named volume,
server and modern WSL2 kernel `6.18.33.2-microsoft-standard-WSL2`. The volume
survives these lifecycle events; disk/power persistence is unproved. Initial
FILE_SYNC data is acknowledged before the event. Outstanding UNSTABLE buffers,
server-completed lost replies, delayed effects, complete grace/lock reclaim,
independent NAS firmware/cache/failover, physical reboot/power, old SLES kernel,
large/concurrent workloads and deployment remain unqualified.

Select later actual supervised mover cases using these observed classes,
preserving original local state, ownership through worker exit, source custody
and validated manifests. Do not call native success Rust worker recovery or
enable cleanup. Maintain SC-120 and DOC-01–05; registration/repair/DOC-06 remain
deferred. All eight first-release gates and production NFS/source deletion stay
unchanged.
