# Rust increment 58: systemd 228 container preflight

Scope recorded 2026-10-18 on `feature/rust-transfer-coordinator`.

**Outcome: BLOCKED. All ten old-manager lifecycle cases are NOT_RUN.**
The preflight records useful package/directive findings, not a lifecycle pass.

## Package provenance and scope

The user requires container-only testing, with no real SLES installation.
SUSE's [SP5 package announcement](https://www.suse.com/support/update/announcement/2026/suse-su-20260991-1/)
identifies systemd 228 with SUSE maintenance revisions. The pinned SLES root and
two older official SLES image generations omit the manager and have no usable
configured repositories. Anonymous official update access returns 403. No
installation media or authorized RPM mirror is available. An upstream build or
an openSUSE RPM cannot establish exact SLES-maintenance-package qualification.

Use the public official Leap 42.3 image, pinned by digest, as the explicitly
identified equivalent manager: systemd 228, glibc 2.22. Keep the mover, children
and local controllers inside the unchanged pinned SLES 12 SP5 service root.
Record both OS/package inventories, image identity, manager/service libc and
executed artifact hashes. Do not call the equivalent manager a SLES RPM.

## Finite matrix and pass conditions

Repeat the ten [increment 57](RUST-INCREMENT-57.md) records: four baseline
build-mode/profile combinations and six qualification fault cases. Baselines
cover identity/permissions and verified delivery, unit/manual/second-unit
exclusion, bounded unit restarts while a manual owner remains, two armed
shared-state/different-port start races, clean default-60 stop and same-state
restart. Preserve ordinary same-port AddrInUse outcomes and direct guard probes.

Qualification cases in both profiles cover a two-second local delayed drain
with unchanged deadline, manual coordinator death with a stopped copy worker,
and managed coordinator death followed by old-worker exit and attempt-2 recovery.
Preserve original database/source inodes, enrollment receipts, old partials,
producer-reused paths and verified payload/manifest contents. A successful
systemctl stop or MainPID 0 is not permission to replace a live owner. Record
actual old-manager stop/restart diagnostics rather than assuming v252 wording.

The v228 candidate unit uses Service.StartLimitInterval and StartLimitBurst;
the newer Unit.StartLimitIntervalSec spelling is not assumed supported. Require
the actual old parser to accept the candidate without unknown directives. Root
fixture administration does not grant the mover account system-service authority.

## Container isolation and blocked lifecycle scope

The engine uses cgroup v2. A temporary named v1 mount in an already private
cgroup namespace was denied. A standalone controller-free mount probe with a
host cgroup namespace briefly created a named hierarchy in the VM kernel,
succeeded and was unmounted. A subsequent proposed manager
bootstrap using that broader access was rejected by automatic approval review:
privileged host-cgroup access plus cgroup changes exceeded the user's isolated
controlled-container authorization. That manager bootstrap was not executed.
Its proposed boot/entry scripts were removed; they are not part of the retained
fixture. No VM boot settings, host mounts or existing controller hierarchies were
modified; no unrelated process was explicitly moved.

The retained recipe directly starts the unmodified old manager. The preflight
uses private cgroup/PID/mount/network namespaces, no network and no host volumes.
It records boot logs and control-bus probes, and removes its owned containers.
A process existing as PID 1 does not establish a functioning manager. Ten planned
lifecycle records remain NOT_RUN unless a separate full lifecycle run actually
passes; neither package-version checks nor unit parsing can replace that matrix.

The parser container drops all capabilities except SYS_CHROOT for reading the
nested SLES root. A first attempt omitted that capability and failed before unit
or lifecycle checks; retain that failed report separately. This is a fixture
correction and does not change mover privileges or behavior.

This remains a modern shared WSL2 kernel. It does not qualify the SLES-maintained
RPM patch revision, a native old kernel, production account/install policy,
persistent storage/reboot, or combined hard-NFS/systemd. Local SIGSTOP/drain pauses
would not be uncancellable NFS operations. All release gates remain open;
production NFS/source deletion stay disabled and registration/repair stay deferred.

Run fresh production and qualification cargo-zigbuild/glibc-2.22 ELF/exact SLES
test gates independently. No Rust input, dependency, retry/review or application
deadline change is intended. Update SC-034/092/093/095 and DOC-03/04/05 with actual
results only. Full old-manager qualification requires verified package provenance
and an approved suitable isolated container engine; no real SLES installation is
required.

## Proposed broader bootstrap: requires explicit approval

This is a review description, not a retained executable or an authorized action.
If approved, a disposable container would temporarily start with access to the
Podman VM's host cgroup namespace. It would refuse any existing name=systemd
hierarchy, create a new controller-free named hierarchy in its private mount
namespace, move only its own PID into a dedicated child, then unshare the cgroup
namespace and expose only that child's view to the old manager. Fixture exec
helpers would move only themselves into that owned child before joining the
private view. All mounts/processes would be removed with the owned container.
No VM boot settings, existing controller assignments, NAS mounts, host volumes
or unrelated process migrations are proposed.

The broader access still reaches shared VM cgroup state during setup. A mistake
could affect other VM workloads; it is outside the original private-container
boundary. Automatic approval review rejected it for that reason. Do not retry
without new explicit authorization. An approved engine that already offers an
isolated compatible hierarchy is the alternative. Neither choice supplies the
missing SLES-maintenance RPM provenance.

## Observed preflight results

Run `systemd228-20261018T060937Z-d102c85a` is BLOCKED, with empty cleanup errors.
The official Leap manager is `systemd-228-71.1.x86_64` with glibc 2.22; the nested
service root identifies SLES 12 SP5/glibc 2.22. The manager image is
`2aa94a5c78f9fed22d52182f469a5b5c7aa4828ead071d2174edfea9b25776b1`,
based on immutable Leap digest
`271c921a1c84d65467d565e3f1c754b75aa01ceed1a7ac39de4816683c355fd2`.
The shared kernel is `6.18.33.2-microsoft-standard-WSL2`.

Compiled `--dump-configuration-items` introspection as a child process finds all
candidate directive names and rejects the newer Unit.StartLimitIntervalSec and
Unit.StartLimitBurst names from the modern template. This checks section/key
availability only, not values, full parsing or behavior. Both actual
`systemd-analyze verify` commands return 1 with `Cannot determine cgroup we are
running in: Exec format error` and `Failed to initialize manager`. The candidate
and negative-control unit verification are therefore inconclusive, not passing.

The fully private boot container has PID 1 named systemd, `0::/` and cgroup magic
`63677270`. Six bounded manager-bus probes fail in 11.141 seconds. PID 1 remaining
alive is not readiness; all ten planned lifecycle cases stay NOT_RUN. The driver
returns BLOCKED/CLI exit 2. No source custody, transfer or shutdown-under-228 test
is claimed. Actual boot stdout/stderr are empty; do not invent a diagnostic from
those logs. The verifier supplies the recorded cgroup initialization error.

See [raw blocked preflight](RUST-SYSTEMD-228-PREFLIGHT-EVIDENCE.json),
[package/access and rejected-action evidence](RUST-SYSTEMD-228-ACCESS-EVIDENCE.json)
and [first setup failure](RUST-SYSTEMD-228-SETUP-FAILURE-EVIDENCE.json). The first
failure omitted SYS_CHROOT in the parser container and stopped while reading
SLES OS metadata. The corrected run adds only that capability there. A prior
corrected preflight also observed the same cgroup initialization failure; the
final run additionally records the compiled directive inventory.

The retained candidate unit/recipe and private-only preflight can be rerun when
an approved engine is available. The rejected host-cgroup bootstrap is not in
the retained source. Exact SLES-maintenance RPM provenance and the full old-manager
matrix remain pending, independently of the passing increment-57 modern-manager
matrix. All first-release gates remain open. Production NFS/deletion stay disabled.

## Compatibility and provenance

Fresh production `20261018T055313Z-e76f2957` passes 204 tests per profile;
qualification `20261018T055326Z-dc0ed271-nfs-qualification` passes 205 per profile.
Both complete GNU/glibc-2.22 cargo-zigbuild builds, twenty ELF audits, six negative
controls and exact debug/release tests in pinned SLES 12 SP5 userspace, plus
formatting, Clippy and locked package/feature checks. The graph stays at 42
external packages, maximum imported GLIBC_2.18 and interpreter
`/lib64/ld-linux-x86-64.so.2`. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Both old/fresh 61-file Rust inventories match current bytes and archive digests;
all fresh artifact hashes are checked. Four binaries copied into the preflight
are byte-identical to fresh gated service artifacts. Captured preflight/unit/recipe
hashes match executed working bytes and staged blobs after LF normalization.
No Rust input, package, retry/review, shutdown deadline or production-enable
change is made. Passing ABI/userspace checks do not qualify the blocked manager.

Documentation checks retain 95 SC and six DOC IDs, valid local links and the
reference traceability gate. The blocked outcome and first setup failure stay
separate from passing compatibility evidence. Source deletion and production
NFS remain disabled. The old-manager lifecycle request remains incomplete.

Post-run engine inventory confirms no remaining containers or fixture volumes/
networks; only the two existing Rust cache volumes and default network remain.
The safe private-only image is retained; the two unused broader-bootstrap images
and their draft boot/entry scripts were removed.
