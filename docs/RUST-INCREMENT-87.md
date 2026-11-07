# Rust increment 87: actual payload copy across NFS server recovery

## Scope and acceptance

Extend the proven retained native fixture to four actual supervised Rust mover
cases: debug/release × NFSD restart or NFSD quiescence followed by confirmed
same-container termination/start. This controlled sequence was selected after
repeated abrupt live-NFSD termination controls failed; abrupt recovery stays
unqualified and its failed acquisitions remain retained.
Both roots use buffered NMP-41B NFS exports on the same persistent backing volume;
state remains local. Interrupt the actual source read after copying the first
MiB, retain the live coordinator/assignment, refuse competing startup, recover
attempt 1 and verify original custody, staging inode, payload and manifest.
Rehearse clean original-state restart and same-ID committed replay afterward.

Run four independent native controls first. Freeze exact acquisition inputs,
retain raw proof, independently audit it and run both required SLES compatibility
gates. Follow [the complete procedure](NFS-SERVER-MOVER-LAB.md), including normal
unmount/cleanup and both-engine inventory. Keep production NFS/source deletion,
Rust inputs/dependencies, API, retry/review and shutdown deadlines unchanged.

## Results

Run `server-mover-recovery-20261020T163452Z-023afe5c` exits 0, status PASSED,
cleanup_errors=[]. Four native controls precede four actual mover cases:

| Build | Facility | Actual blocked operation | Delivery/replay |
|---|---|---|---|
| Debug | NFSD threads 2→0→2 | Claimed-source read, 1 MiB requested | Original worker/attempt 1; passed |
| Debug | NFSD zero, then same-container SIGKILL/exit 137/start | Claimed-source read, 1 MiB requested | Original worker/attempt 1; passed |
| Release | NFSD threads 2→0→2 | Claimed-source read, 1 MiB requested | Original worker/attempt 1; passed |
| Release | NFSD zero, then same-container SIGKILL/exit 137/start | Claimed-source read, 1 MiB requested | Original worker/attempt 1; passed |

Every worker is actually D-state in read(2) on its claimed-source FD after the
first 1,048,576 staged bytes, with the payload loop incomplete. The live
coordinator keeps unchanged Claimed/Intent status and its local epoch; health
takes 1.718–1.844 seconds. The local guard remains contended and a contender
using an ephemeral listener refuses specifically on ownership in 0.859–0.890
seconds. Port collision does not count as exclusion.

Each original worker finishes its 2,097,169-byte transfer on attempt 1. All
eighty traced synchronization calls return zero, including payload fsync after
restoration. All four workers subsequently exit with traced status 9, the
existing supervised retirement after a confirmed Committed receipt; this is
not a worker-death-during-copy test. The original staging inode becomes the
final allocation, with the expected source/final SHA-256 and complete manifest.
Private source backing inode/bytes, root identities, original local database
inode/configuration and enrollment remain unchanged. A clean original-state
restart and same-ID replay return the same committed job/manifest while newer
producer-path bytes remain untouched.

## Measured facility and filesystem scope

All four native original-FD probes complete normally, retaining opaque handles,
backing inodes and the expected A→B bytes. Their successful sessions and WRITE
verifiers change across each event. Container PID/StartedAt changes only for
container events; network namespaces and VM kernel boot ID remain unchanged.
The service windows retain successful full-count post-restoration WRITEs and
decoded status 10052/2 transactions. Unsupported compounds remain unknown,
not discarded or attributed to an unrelated synchronization interval.

The two configured export paths have distinct mount IDs 842/843 but both report
device `0:123`; source/staging/final st_dev is 123 and local state is 96. They
share one client NFS filesystem and one named backing volume/server. The actual
buffered-copy pause/read, distinct source/staging inodes and full digest checks
prove copying, but this does **not** qualify distinct client filesystems,
independent shares/NAS or an EXDEV path. The initial auditor incorrectly assumed
different mounts imply different devices. Its rejected source/assumption/input
hash is retained in [audit evidence](RUST-NFS-SERVER-MOVER-AUDIT-INITIAL-EVIDENCE.json);
the acquisition was preserved unchanged and the final audit checks the narrower
observed scope.

Four earlier acquisitions remain FAILED: a runner variable collision before
movers, a contender port collision before the intended guard diagnostic, and
two unreliable abrupt live-NFSD termination controls. Disabling backend cgroups
did not solve abrupt termination. Final tests restore default cgroups and first
confirm NFSD threads zero before terminating the same container. This controlled
restart does not qualify abrupt server death. The
[lab](NFS-SERVER-MOVER-LAB.md#retained-acquisition-failures-and-rescue) retains exact
available inputs/logs, the second attempt's missing final-wire limitation, both
normal-unmount rescues and their exact helpers/actions. Neither rescue promotes
a failed acquisition. No force/lazy-unmount, VM restart, host cgroup-policy/unit
reset or NAS change was used.

## Compatibility, audit and cleanup

- Production gate `20261020T155338Z-60cd625d`: 211 actual target tests per profile.
- Qualification gate `20261020T155338Z-6fcc6168-nfs-qualification`: 212 per profile.

Both exit 0 with no cleanup error. Locked cargo-zigbuild GNU/glibc 2.22,
formatting/Clippy, exact debug/release target execution in pinned SLES 12 SP5,
loader/library/symbol audits and six negative ELF controls per mode pass. The
42-package graph and all 62 Rust input entries remain unchanged. There is one
shipping executable; forty audited artifacts include tests and both modes/profiles.

The independent audit verifies fourteen captured acquisition inputs, the native
probe bytes/ELF, current Rust versus both exact source archives, all forty fresh
artifact hashes/ELF reports, exact shipping bytes used live, raw RPC redecoding,
pending syscall/FD/security/clock proof, original state/inode/manifest evidence
and all failed packs. All fifty deliberate proof corruptions are rejected,
including port-collision, changed state and unquiesced-container counterexamples.
Seven decoder regression tests pass. The lossless raw report is 14,536,558 bytes,
with 172 native and 11,890 mover wire records; 1,751 mover records remain unknown
to the bounded decoder. Relay capture errors and protocol status are separate.

Final inventory at `2026-10-20T16:50:43.770789+00:00` has no containers on either
engine, original rootful caches/default network, and unchanged default-engine
volume metadata/network names. All original fixture users exited before normal
unmount and owned-resource removal. Read the
[raw evidence](RUST-NFS-SERVER-MOVER-EVIDENCE.json),
[input/audit evidence](RUST-NFS-SERVER-MOVER-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json) and
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json).

## Remaining limits

This is a finite live-coordinator source-read test on a shared client filesystem.
Other phases, worker death/replacement during server recovery, distinct client
filesystems/independent endpoints, outstanding UNSTABLE data loss, delayed-effect
settlement, reliable abrupt termination, fresh namespaces, VM/NAS reboot,
physical power/disk durability and larger/concurrent workloads remain unqualified.
Pinned SLES userspace shares modern WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`; original SLES kernel/vendor-maintenance and
deployment/account behavior remain separate obligations. A local lock or timeout
never proves remote settlement. Keep all eight release gates open, production
NFS/source deletion off, runtime retry/review/deadlines unchanged and registration,
repair and DOC-06 deferred. The recorder still only retries JSON until 202;
consumers validate the manifest. Maintain SC-121 and DOC-01–05.
