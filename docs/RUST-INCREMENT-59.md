# Rust increment 59: approved systemd 228 lifecycle fixture

Scope recorded 2026-10-18 on `feature/rust-transfer-coordinator`.

The user explicitly approved the broader bootstrap described in
[increment 58](RUST-INCREMENT-58.md), then requested step-by-step infrastructure
and test instructions plus an explanation of ultimate testing limits. Keep
production NFS and source deletion disabled. This approval applies to the Podman
VM fixture; it is not authorization to change production or NAS configuration.

## Results

`systemd-20261018T070942Z-d22d7cb1` passes all ten lifecycle records with no cleanup errors.
See [raw lifecycle evidence](RUST-SYSTEMD-228-LIFECYCLE-EVIDENCE.json). The manager
is actual `systemd-228-71.1.x86_64` from pinned Leap 42.3, glibc 2.22; the mover,
workers and controllers use the unchanged pinned SLES 12 SP5/glibc-2.22 root.
The shared kernel is `6.18.33.2-microsoft-standard-WSL2`, not an old SLES kernel.

| Build/case | Debug | Release |
|---|---|---|
| Production baseline lifecycle | PASS | PASS |
| Qualification baseline lifecycle | PASS | PASS |
| Qualification incomplete stop | PASS | PASS |
| Qualification manual coordinator death / stopped copy worker | PASS | PASS |
| Qualification managed coordinator death | PASS | PASS |

Each of the four baseline records passes five check groups. All eight armed
start races have exactly one owner and a guard-refused loser (observed winners:
8 manual). This is not a fairness
claim. All 32 explicit competing effect commands refuse; ordinary same-port
service probes can fail at bind, while alternate-port/effect probes reach the
shared guard. Second-unit refusal preserves the legitimate main PID. Manual
ownership bounds managed restart attempts; clean default-60 stop/restart passes.

Incomplete-stop manager jobs return in 17.406 seconds (debug), 17.344 seconds (release);
their actual replies and manager state remain distinct from application status.
Both manager jobs return exit 0 with MainPID 0 and Result=timeout while the
original owner is still live. Neither manager field proves ownership release.
Independent same-user controllers return exit 2 within five seconds with the
loaded two-second wait and an exact epoch/snapshot match to live
ShutdownIncomplete. The original owner remains live and contenders refuse until
the controlled release and confirmed exit. No shutdown deadline changes.

Manual/managed coordinator-death cases recover attempt 2 with original database
and source inodes, enrollment/binding, retained old partials and producer-reused
paths preserved. Managed replacement is observed only after old main/worker exit;
polling does not prove absence of arbitrarily brief overlap. All ten records
validate committed manifests/hashes, stable roots, retained source, cleanup false
and final NoActiveOwner. Local SIGSTOP/pause cases are not hard-NFS blocking.

The corrected 228 unit uses unit-owned SIGTERM/control-group shutdown, with no
global ExecStop controller. This prevents the foreign-owner-stop failure retained
below. No Rust behavior, dependency, retry/review or production-enable change is
made. Production NFS and source deletion remain disabled; all eight release
gates remain open.

The approved image is `963fb250282f2f6c2d4d645c340373478d498db0f4620d65798fc783b2f89d5b`. Its base layer prefix, fifteen driver
hashes and four executed helper hashes are checked. Outer cgroup namespace
`cgroup:[4026531835]` differs from manager/helper
`cgroup:[4026532478]`. The controller-free v1 view has filesystem
magic `27e0eb`; no inherited global-root mount remains. Creation attestation,
owned-directory removal, bounded empty-root teardown and independent absence of
the legacy hierarchy all pass. This verifies the fixture boundary, not general
privileged-container isolation or production authorization policy.

## Finite cases and pass conditions

Run ten records: production/qualification by debug/release baseline lifecycle
combinations, plus both qualification profiles for incomplete stop, manual
coordinator death with a stopped copy worker, and managed coordinator death.
Baseline checks cover account/capability and delivery verification, shared-state
manual/second-unit refusal, bounded managed restart attempts with a manual owner,
two armed different-port/shared-state races and clean default-60 stop/restart.
Require guard contention for direct different-port probes and each race loser;
preserve ordinary same-port bind refusal as a distinct outcome.

Fault cases retain the two-second application wait and eight-second fixture
manager timeout. An incomplete stop must retain its original live owner and
refuse competitors; unit stop success/MainPID 0 is not ownership-release proof.
Manual orphans must block replacement through actual exit, then recover attempt
2 using original database/source/enrollment and retained partials. Managed crashes
must find old coordinator/worker exited at the first observed replacement, then
recover normally. Polling is not a trace proving absence of arbitrarily brief
overlap. Verify manifest/hash, stable roots, producer-reused paths and retained
source, cleanup false, original database inode and final NoActiveOwner status.

Use the actual 228 unit verifier with the legacy candidate; record old-version
diagnostics and results rather than requiring v252 wording. Preserve failed
attempts separately. Fresh production and qualification GNU/glibc-2.22 zigbuild,
ELF and exact pinned-SLES test gates are mandatory. No Rust/dependency/deadline
or retry/review change is intended.

## Infrastructure boundary

The approved bootstrap briefly starts in the Podman VM's host cgroup namespace,
in a private mount/PID/network namespace without network or host volumes. Refuse
an existing name=systemd hierarchy; create a controller-free hierarchy, move
only the fixture PID into its owned child, unshare the cgroup namespace and
remove the inherited global-root mount before starting the manager. Exec helpers
move only themselves into that owned child and join the private view before
dropping user identity. Record namespace IDs, cgroup roots, mount types, actual
manager/package/libc, kernel, exact image/artifact/driver identities and cleanup.
Do not change VM boot settings, existing controller assignments or unrelated
process membership. Only one such fixture can run at a time.

The manager remains the pinned official Leap 42.3 systemd-228 equivalent, not an
exact SLES-maintenance RPM. Mover/children/controllers use the pinned SLES 12 SP5
root and glibc 2.22. Native SLES package/kernel/account/storage and combined
hard-NFS/systemd qualification remain separate. Keep the increment-58 blocked
private-only report as historical evidence. No real SLES installation is required.

## Fixture findings retained separately

[Failed-attempt evidence](RUST-SYSTEMD-228-LIFECYCLE-FAILURE-EVIDENCE.json) retains
the original boot probe, its corrective empty-root cleanup and these failures:

- `systemd-20261018T063103Z-0f349f56` refuses the hierarchy left by the initial
  successful boot probe; no cases run and cleanup reports the remaining legacy
  hierarchy. Removing empty child directories is insufficient by itself.
  After all compatibility containers also exited, a verified empty-root
  mount/unmount released it without process migration/signals or controller
  changes. The maintained helper now bounds owned-directory removal and
  empty-root unmount retries and independently checks kernel-hierarchy absence.
- `systemd-20261018T065414Z-d478a598` reaches actual unit verification but fails
  launching at GROUP/216. Leap's default `useradd` assigns `users` (GID 100),
  not a matching `mover` group. The approved layer explicitly creates GID 1000
  and changes that fixture account's primary group; the driver checks both IDs.
  The pinned SLES root remains unchanged. Cleanup passes.
- `systemd-20261018T065623Z-213c7d48` launches and independently observes the
  expected live-owner ShutdownIncomplete result, but the unit-filtered journal
  omits the controller's JSON reply. The boot journal contains it. The fixture
  now requires the structured reply for the exact epoch to equal live status,
  recording its unit/boot source. Manager timeout wording alone is insufficient.
  This failed attempt remains failed; cleanup passes.
- `systemd-20261018T065827Z-1ac6587c` passes the debug incomplete-stop case but
  fails manual-orphan restart-limit diagnostics. The boot journal has two guard
  refusals absent from the unit query. Give each legacy fixture unit its own
  explicit SyslogIdentifier and query that alongside unit/manager metadata.
  The required guard-refusal count and stable start-limit checks remain intact.
  Both failure records remain failed overall; cleanup passes.
- `systemd-20261018T070226Z-6c2ec3fe` passes all three debug fault cases but
  fails the baseline second-unit exclusion check. Under 228, the rejected
  contender still invokes its global `ExecStop=... --stop`; that command stops
  the legitimate owner's epoch. This is a meaningful candidate-unit design
  defect, not merely a journal assertion. Remove global ExecStop from the
  legacy unit; normal manager SIGTERM/control-group behavior targets only that
  unit's processes. Exercise the bounded same-user controller independently in
  the incomplete-stop case and retain the normal baseline controller test.
  No Rust controller semantics or deadlines change. Cleanup passes.

The bootstrap also records a post-creation nonce attestation. Before creating
any fixture, the driver independently refuses an existing named hierarchy;
cleanup attaches only after the boot log attests this run's subtree creation
and requires that owned directory before empty-root teardown. A refused unknown
hierarchy is not cleanup authority. [Negative controls](RUST-SYSTEMD-228-BOOTSTRAP-CONTROLS-EVIDENCE.json)
pass for missing acknowledgment, mismatched manager/switch and existing-hierarchy
refusal before container creation; the active fixture inventory is unchanged.

The retained private-only preflight formatter now supplies the unit name needed
by the shared candidate template. Recheck `systemd228-20261018T072947Z-a3c48787`
still records BLOCKED, ten NOT_RUN cases and no cleanup errors; see
[separate private recheck](RUST-SYSTEMD-228-PRIVATE-RECHECK-EVIDENCE.json).
This preserves that diagnostic capability and its private boundary. It neither
overwrites the historical 58 report nor changes the ten passing broader-bootstrap
lifecycle records. All four recheck driver hashes are audited separately.

These are fixture findings, not passing lifecycle records or Rust service fixes.
Read the [step-by-step lab procedure](SYSTEMD-LIFECYCLE-LAB.md) for prerequisites,
images, bootstrap, all test steps, evidence and cleanup. Read
[testing limitations](TESTING-LIMITATIONS.md) for what each evidence layer proves,
what it cannot establish and the remaining release implications.

## Compatibility and provenance

Fresh production `20261018T062735Z-b652d2e4` passes 204 tests per profile;
qualification `20261018T062748Z-a7f2f84c-nfs-qualification` passes 205 per profile.
Both complete GNU/glibc-2.22 cargo-zigbuild builds, twenty ELF audits, six negative
controls and exact debug/release tests in pinned SLES 12 SP5 userspace, plus
formatting, Clippy and locked package/feature checks. The graph remains 42
external packages, maximum imported GLIBC_2.18 and interpreter
`/lib64/ld-linux-x86-64.so.2`. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Both old/fresh 61-file Rust inventories match current bytes and archive digests;
all fresh artifact hashes are checked. The four lifecycle binaries come from
increment-58 gates and are byte-identical to the fresh gated service artifacts.
No Rust input, package, retry/review, shutdown deadline or production-enable
change is made. Passing ABI/userspace checks alone do not qualify the manager.

All fifteen captured driver hashes match executed working bytes and staged
source after LF normalization; four helper hashes also match the actual image
files. The source/artifact audit checks all twenty ELFs in each fresh gate and
all four lifecycle service artifacts. Historical systemd-252 evidence remains
unchanged; its two stored incomplete-stop replies satisfy the structured
exact-owner check, without claiming new 252 execution in this increment.

The scenario catalog retains 95 SC and six DOC IDs. SC-034/092/093/095 and
DOC-03/04/05 link the actual outcomes, step-by-step guide and limitations matrix.
Local-link, Python/JSON, whitespace and reference traceability checks pass.
No remaining test containers or fixture volumes/networks remain; the two Rust
cache volumes, fixture images and default network are intentionally retained.
