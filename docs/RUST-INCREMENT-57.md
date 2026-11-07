# Rust increment 57: controlled systemd and manual coordination

Scope recorded 2026-10-18 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Run `scripts/check-systemd-boundaries.py` against exact passing production and
qualification artifacts, with no Rust input changes. Ten case records: four
production/qualification x debug/release baseline lifecycle combinations and
six qualification cases (two profiles x incomplete stop/manual orphan/managed
crash). Each baseline covers five checks: identity/permissions/verified delivery,
unit ownership excluding manual and a second unit, manual ownership with bounded
unit restart attempts, two armed simultaneous-start races, and clean default-60
stop plus subsequent same-state restart. Armed races and explicit second-port probes must report guard contention,
not merely fail to bind the TCP port. Ordinary same-config competitors may
report occupied port because listener binding precedes ownership acquisition.
Alternate-port configurations change only bind, keeping the same state/source/
destination, to test the guard directly. Source deletion remains false.

The pinned SLES base has no systemd/D-Bus packages or configured repositories.
Use a pinned Debian manager base with recorded systemd 252.39 package/image
identity and an unchanged pinned SLES 12 SP5 root under RootDirectory=/sles.
The mover, children and CLI controllers run with glibc 2.22 in that root and
share its original local configuration, state and PID namespace. Check actual
libc mapping, UID/GID 1000, zero capabilities, NoNewPrivs, mode/private state,
foreign-UID CLI refusal and unprivileged systemctl denial. Root fixture control
simulates administrator-provisioned system service control; it grants no caller
policy. Keep the inherited C++ deployment unit unchanged.

The disposable Rust fixture unit uses Type=simple (manager active is not app
readiness), an explicit bounded CLI ExecStop, KillMode=control-group,
SendSIGKILL=no, Restart=on-failure with finite start limits and root-owned fixture
environment. Confirm application health separately. Default omission loads 60;
clean shutdown confirms exit and permits restart. Qualification delayed drain
uses the unchanged two-second budget, an eight-second manager stop timer and
requires application ShutdownIncomplete/exit 2 with the original live owner, no replacement
and prompt competing-start refusals. Record the manager job result separately:
a successful systemctl stop reply is not application exit. The eight-second
manager timeout may apply to more than one stop phase; observe a finite
24-second fixture-command bound without changing the application budget.
Release the local pause, confirm exit and
recover normally. Do not extend application deadlines or delete ownership state.

A manual qualification copy worker is paused after a 1 MiB chunk and SIGSTOPped;
kill its coordinator, require surviving ownership, bounded failed unit restart
attempts and no storm. Restore its local release/CONT, confirm old exit and use
the original database/source/receipt to commit attempt 2, preserving old partial
and producer-reused paths. A managed crash instead kills only the unit main PID;
require old coordinator/worker exit when the replacement main PID is first
observed after manager group cleanup,
then normal original-state attempt-2 recovery. The observer polls through Podman;
this checks absence of old live PIDs at the observed replacement, not a kernel
trace proving absence of arbitrarily short overlap. Verify payload/manifest hashes,
original database/source inodes, roots and private source retention.

Run fresh production and qualification GNU/glibc-2.22 zigbuild/ELF/exact pinned
SLES test gates. Verify source inventories, exact artifact hashes and executed
driver/unit/container recipe hashes. Record actual outcomes, journal and cleanup.

## Limits

This is systemd 252 on a modern shared WSL2 kernel/cgroup v2, with glibc-2.22
SLES service userspace. It does not qualify native SLES systemd 228, cgroup v1,
actual host systemd/account authorization, production packaging/hardening, reboot
or persistent disk durability. Payload and state are local; SIGSTOP/local drain
are controlled fixture states, not uncancellable hard-NFS syscalls. Combined
NFS/systemd shutdown, delayed NAS effects, actual mounts/security and remaining
release gates stay open. Manager packages/capabilities belong only to the isolated
fixture and add no mover dependencies. Production NFS and source deletion remain
disabled; registration and repair stay deferred.

Primary references: [systemd execution/root directory](https://www.freedesktop.org/software/systemd/man/252/systemd.exec.html),
[process termination](https://www.freedesktop.org/software/systemd/man/252/systemd.kill.html),
[service restart/stop](https://www.freedesktop.org/software/systemd/man/252/systemd.service.html),
[Podman systemd container handling](https://docs.podman.io/en/latest/markdown/podman-create.1.html).

## Results

Run `systemd-20261018T053029Z-e9981052` passes all ten case records. The four
baseline combinations complete twenty named checks, including eight armed
simultaneous-start races. Each race has exactly one live owner and a guard-refused
loser; all eight winners happened to be manual starts. This is not a fairness or
exhaustive interleaving claim. Unit ownership and second-unit refusal are tested
separately. Thirty-two explicit competitor commands refuse; additional managed
start-limit refusals and race losers are retained in the journals.

Both incomplete stops return application ShutdownIncomplete/exit 2, loaded budget
2 and zero remaining time, with the same live owner and competing-start refusal.
Manager stop commands take 19.234 and 19.344 seconds and return exit 0 despite
ExecStop exit 2; systemd reports timed-out stop phases with SIGKILL skipped and
retains the original process even while MainPID reports 0. No replacement is
authorized. After releasing the
local pause, confirmed exit permits original-state delivery. Four clean default-60
unit stops take 1.031–1.141 seconds; manual restart afterward succeeds.

Both manual-orphan cases preserve the stopped worker and original ownership
while unit starts hit their finite limit, then commit attempt 2 only after old
exit. Both managed-crash cases find old coordinator/worker exited when observing
the replacement and commit attempt 2. The four recoveries preserve original
source/database inodes, enrollment receipts, old staging allocations and valid
partial contents, plus producer-reused paths. All ten cases verify payload and
manifest hashes, stable roots, retained private source and cleanup false; final
status is NoActiveOwner. The unprivileged identity/capability and control-denial
checks pass in all four baselines.

The manager is `252.39-1~deb12u2`, image
`b80bb3fcb9f91873ec0c451e9e7c2a21b2392271d1fdc205f0c07d581c9d2ed7`,
with cgroup v2 on `6.18.33.2-microsoft-standard-WSL2`. Exact OS/package/unit/journal
and case evidence is in [the raw report](RUST-SYSTEMD-EVIDENCE.json).
Cleanup errors are empty; a post-run engine inventory confirms no containers or
fixture volumes/networks remain, only the two existing Rust cache volumes and
default network. The manager image/recipe remains available for later tests.

Five [failed fixture reports](RUST-SYSTEMD-SETUP-FAILURE-EVIDENCE.json) remain
separate, never passing evidence. The corrections/findings were:

1. Unit verification checked executable paths in the manager root. Fixture-only
   path mirrors allow stat validation; actual execution remains RootDirectory
   SLES, with mapped libc 2.22 checked.
2. Resetting an unloaded new unit can fail before its first start; that preparatory
   reset is allowed to fail, while actual startup/readiness remains required.
3. Same-port service conflicts report AddrInUse before guard acquisition. Keep
   that real result and use explicit second-port/shared-state guard probes.
4. Start-limit enforcement retained Result=exit-code on this manager. Require the
   actual repeated-too-quickly journal, bounded guard refusals, MainPID 0 and
   unchanged state/no more attempts during a three-second observation.
5. A successful systemctl stop job is not application shutdown success. Require
   application exit-2 status, the unchanged live owner and competing-start refusal;
   record the manager reply separately. Application deadlines remain unchanged.

The command used was:

```powershell
python scripts/check-systemd-boundaries.py rust/validation/20261018T043528Z-c2d48e76 --qualification-gate rust/validation/20261018T043539Z-c5a06856-nfs-qualification
```

All 95 SC and six DOC IDs remain stable. The operator guide and SC-034/092/093/095
now explain this selected scope; DOC-04/05 retain actual-version/account,
persistence and combined hard-NFS obligations. All eight release gates stay open.
Production NFS and source deletion remain disabled.

## Compatibility and provenance

Fresh production `20261018T051247Z-3ef185bc` passes 204 tests per profile;
qualification `20261018T051258Z-97f50a4f-nfs-qualification` passes 205 per
profile. Each completes cargo-zigbuild GNU/glibc-2.22 builds, twenty ELF audits,
six negative controls and exact debug/release tests in pinned SLES 12 SP5
userspace, plus formatting, Clippy and locked package/feature checks. The graph
remains 42 external packages; maximum imported symbol is GLIBC_2.18 and the
interpreter is `/lib64/ld-linux-x86-64.so.2`.

Old/fresh 61-file Rust inventories match current bytes and archive digests.
Every fresh artifact hash is checked; all four service binaries reused from
increment 56 gates are byte-identical to the corresponding fresh artifacts.
Captured driver/unit/recipe hashes must match executed working bytes and staged
blobs after LF normalization. No Rust inputs, packages, retry/review behavior,
application shutdown deadlines or production-enable settings change.
See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).
