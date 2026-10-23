# AGENTS.md

## Current direction (2026-10-13)

2026-10-23: `docs/REST-ERROR-SCENARIOS.md` records API-E01-60 for user review
before P01 is frozen. Groups 1-13 (fifty mappings, error envelope and retry timing) are approved; other mappings
remain under review. Missing-file 409 is approved but current runtime is still
503. No one uses the Rust prototype API: replace its producer format directly,
without an old-wire adapter. Preserve persisted custody; global-ID state handling
and exact schema details still need design.


Current next work is the 2026-10-22 release-closure review in `docs/RUST-RELEASE-CLOSURE.md`: P01 freezes the versioned API/manifest and release behavior inventory.
Use RC-01-24 and P01-12 to bound remaining work; do not automatically select
another NFS experiment. All eight gates remain open. Keep production NFS and
source deletion disabled; default-off cleanup remains a release deliverable.
Earlier increment summaries below are evidence, not the current work order.

The user now wants a durable Rust transfer coordinator, not a C++-shaped port.
Work on `feature/rust-transfer-coordinator`; read `docs/RUST-DIRECTION.md`,
`CONVERSATION.md` and the roadmap handoff first. Experiments are stopped after
E1–E5; do not automatically start E6. Follow `docs/INTEGRITY-DESIGN.md`: hash the
source during copying and reread destination staging for verification (3N logical
data I/O). Develop short tested increments from the revised protocol in `rust/`.
Registration/token work is deferred; its enrollment choice is a one-time setup key.
See `docs/RUST-INCREMENT-01.md` and future-only `docs/ROADMAP.md`.
SQLite acceptance/replay is in `mover-store`; see `docs/RUST-INCREMENT-02.md`.
Protected local source claiming is in `mover-fs`; see `docs/RUST-INCREMENT-03.md`.
The local endpoint is in `file-mover`; see `docs/RUST-INCREMENT-04.md`.
The single-file transfer command is documented in `docs/RUST-INCREMENT-05.md`.
Automatic local delivery/manifests are documented in `docs/RUST-INCREMENT-06.md`.
Read-only operator job status is documented in `docs/RUST-INCREMENT-07.md`.
Audited delivery resume is documented in `docs/RUST-INCREMENT-08.md`.
Audited missing-file deadline reset is documented in `docs/RUST-INCREMENT-09.md`.
Read-only retention accounting is documented in `docs/RUST-INCREMENT-10.md`.
Offline inspection/repair is deferred by the user. Prioritize supervised workers
and controlled NFS testing. Increment 13 isolates runtime delivery filesystem
access in recording sessions and handoff scope checks in claim children.
Increment 14 measures hard-mount startup blocking and OS lock/interruption behavior;
see `docs/RUST-INCREMENT-14.md`. Increment 15 isolates source singleton bootstrap
and qualifies startup shutdown; see `docs/RUST-INCREMENT-15.md`.
Retain the opt-in NFS qualification feature and fixture capability permanently;
see `docs/NFS-QUALIFICATION.md` and `docs/RUST-INCREMENT-16.md`.
Increment 17 diagnoses the NFS no-clobber rename refusal and adds owned link/unlink
recovery; see `docs/RUST-INCREMENT-17.md`. Increment 18 adds deterministic
qualification-only pause controls and selected real-worker NFS outage/death cases;
see `docs/RUST-INCREMENT-18.md`. Increment 19 qualifies source-read/verification
interruption and introduces the maintained scenario catalog; see
`docs/RUST-INCREMENT-19.md`. Increment 20 qualifies durable two-name NFS claim/file
link interruption; see `docs/RUST-INCREMENT-20.md`. Increment 21 adds three-minute
blocked claim/verification and live-recovery checks, including submission backpressure;
see `docs/RUST-INCREMENT-21.md` and the separate long-outage evidence report.
Increment 22 adds two-client ownership/missing-mount diagnostics; see
`docs/RUST-INCREMENT-22.md` and `docs/ROOT-OWNERSHIP-DESIGN.md`. Diagnostic
completion is not protection or production approval. Increment 23 implements
required source_binding/provisioned marker checks, strict schema-8 enrollment,
source authorization in bootstrap/claim/delivery children and the single-file CLI;
see `docs/RUST-INCREMENT-23.md`. Existing populated unbound state refuses startup;
no rebind/override is provided. Increment 24 adds required destination_binding,
per-job schema-9 policy/observation pins, worker/CLI validation and immediate
binding review while preserving outage handoff; see docs/RUST-INCREMENT-24.md.
Legacy jobs without destination policy refuse startup. Increment 25 replaces
directory custody with a preprovisioned empty mode-0600 regular coordinator.lock,
version-2 bindings and bootstrap receipts, and actual worker descriptor checks;
see docs/RUST-INCREMENT-25.md. Two-client tests distinguish cooperative exclusion
from lost-lock/partition/reclaim fencing. Do not mix old/new lock protocols or
auto-rebind existing observations. Increment 26 defines fenced enrollment in
docs/FENCED-ENROLLMENT-DESIGN.md. Increment 27 implements explicit unused-scope
source/state pairing and matching restart: schema 10, version-3 bindings,
--initialize-source and a protected source-enrollment.json receipt. See
docs/RUST-INCREMENT-27.md for interrupted setup and fresh-state refusal evidence.
Populated rebind/takeover requires an independently qualified fence. Preserve the
original database; no automatic legacy enrollment or receipt repair is provided.
Cloned/stale database snapshots are not distinguished by persistent IDs alone.
Increment 28 adds qualification-only enrollment I/O faults, a file/parent sync
checkpoint, bounded stage diagnostics and actual blocked receipt-read startup
shutdown cases; see docs/RUST-INCREMENT-28.md for results and timing limits.
Schema 10, binding version 3 and the persisted receipt remain unchanged. Do not
interpret simulated ENOSPC/EIO or a signal as hardware durability/cancellation
proof. Keep the production controls inert and the qualification feature retained.
Increment 29 adds opt-in --enrollment-storage qualification with a bounded 4 MiB/
128-inode server tmpfs export; see docs/RUST-INCREMENT-29.md for actual results.
Distinguish no receipt creation from created-but-unactivated review, retain original
state/data, and do not generalize tmpfs ENOSPC to disk EIO or power-loss durability.
Increment 30 adds --delivery-storage for bounded destination-full payload copying
and live/original-state restart review/resume; see docs/RUST-INCREMENT-30.md for
actual results. Preserve old partials and claimed source, never edit state to
recover, and distinguish measured server capacity from generic worker diagnostics.
Increment 31 adds fixed operation/errno payload diagnostics and qualification-only
payload fault controls; see docs/RUST-INCREMENT-31.md for actual results. Keep
existing retry timing, three-failure review and audited resume unchanged. Error
messages never authorize effects; publication sync failure may leave a valid
final file while the job remains uncommitted. Preserve source/state/partials.
Increment 32 extends fixed diagnostics to staging allocation, relocation sync/open
and completion-manifest I/O; see docs/RUST-INCREMENT-32.md. Preserve the existing
retry/review policy: unreceipted allocations are not automatically repaired, and
COMMITTED.json can exist before coordinator commitment after a failed sync.
Increment 33 adds typed payload-copy ENOSPC backoff (30/60 seconds, still review
at three persisted failures); see docs/DELIVERY-RETRY-POLICY.md and
docs/RUST-INCREMENT-33.md for actual results. Schema 11 transactionally widens
retry codes while preserving original state, source pairing and recorded deadlines.
Private delivery sessions use version 2; persisted receipts and binding versions
are unchanged. Never infer classification from diagnostic text or extend capacity
backoff to sync/publication, allocation, custody or unknown worker outcomes.
Increment 34 delivers DOC-03 in docs/RUST-OPERATOR-GUIDE.md; maintain it with
future status/retry/review changes. See docs/RUST-INCREMENT-34.md for the
documentation-only checks. Other user guides remain in the scenario backlog.
Increment 35 defines docs/SOURCE-SPACE-ADMISSION-DESIGN.md: configurable byte/
percent margins, default-off/explicit off, new-key-only gating and SA-01–18.
Its original future-only scenarios are now refined by increment 36; retain all
remaining physical/NFS acceptance obligations without claiming them supported.
Increment 36 implements the default-off source-space guard; see
docs/RUST-INCREMENT-36.md and docs/SOURCE-SPACE-ADMISSION-DESIGN.md. New-key
admission uses bounded child observations and final SQLite replay/freshness checks;
accepted partial/replayed jobs bypass this guard but retain existing safety/limits.
Cached global status never probes. Preserve qualification-only failure/pause
controls, distinguish synthetic/local tests from hard NFS and physical exhaustion.
Do not auto-enroll missing/foreign
markers, treat directory locks as distributed fences, or enable automatic takeover.
Next qualify in-flight link/unlink RPCs, other sync boundaries, outages beyond
those selected cases, stable root/export
authorization and cross-client ownership. If Ubuntu user startup prevents rootless
Podman, use the documented Windows/Podman WSL2 gate fallback in
`docs/NFS-QUALIFICATION.md`; preserve all compatibility checks.
Keep production NFS and deletion disabled.
Increment 37 defines docs/RUST-FIRST-RELEASE.md: eight open release gates,
filesystem/NFS scope and deferred features. Use it to prioritize the broader
roadmap. Increment 38 adds --source-storage fixture qualification for bounded
native source fill, partial/claimed replay while Low and unchanged-policy live
restoration; see docs/RUST-INCREMENT-38.md for actual evidence and limits.
Increment 39 defines docs/REMOTE-API-ACCESS-CONTRACT.md: proposed external
mutual TLS with manually approved certificates, protected producer-only Unix
socket/peer UID and generator binding; RA-01–16 and SC-082–086 remain pending.
No ingress, tokens or registration are implemented. Increment 40's broad fencing
baseline is revised by increment 41 in docs/NFS-OWNERSHIP-FENCING-CONTRACT.md:
one mover, same host/account/config and fixed local state; private NFS work areas;
no host sudo/NAS administration assumed. Increment 42 implements the shared
host-local instance.lock and explicit SCM_RIGHTS handoff to all six worker modes,
with selected local evidence; see docs/RUST-INCREMENT-42.md. Guard admission
checks parent/guard. Increment 44 adds SQLite database/WAL/shared-memory/journal
file admission, individually mounted state/guard/control refusal, private new
database creation and retained-WAL crash recovery; see docs/RUST-INCREMENT-44.md.
No automatic repair or hostile concurrent same-UID/root mutation protection is
claimed. Increment 43 implements shutdown_wait_seconds (default 60,
integer 1–3600) and --status/--stop over private local control.sock, independently
of SQLite/NFS/the executor; see docs/RUST-INCREMENT-43.md. The running daemon owns
the first monotonic deadline; repeated stop/signal requests and config edits do
not reset it. Timeout exits 2 with ShutdownIncomplete/restart blocked while live
holders retain ownership. Qualification-only shutdown_drain is a bounded local
pause, not an uncancellable NFS call. Increment 45 adds opt-in --shutdown fixture
qualification with actual kernel-blocked claim/copy/verification workers, short
and default budgets, retained-copy exclusion, repeated requests and original-state
recovery; see docs/RUST-INCREMENT-45.md. Prompt kernel-assisted exit and retained
workers beyond the deadline are separate measured outcomes. Rust inputs/ABI,
retry/review and production gates are unchanged. Next qualify remaining guard/
death-phase, other NFS operation/drain and actual-version systemd/account cases.
Increment 46 adds --coordinator-death fixture cases for actual kernel-blocked
claim/copy/verification children and selected terminating orphans after local stop;
see docs/RUST-INCREMENT-46.md. Confirm parent exit, orphan D state and contended
local guard before competing effect commands. OwnerUnavailable is unsuccessful
and never authorizes killing/adopting an orphan. Restore storage and confirm old
exit before original-state recovery. Prompt stop before parent kill is a distinct
outcome. The increment 46 bracketed rerun exposed a terminating-worker
ownership gap: raw flock release/NoActiveOwner preceded actual kernel exit.
Keep that historical report failed; qualify independent lifetime retention with
increment 47 rather than erasing the counterexample or forcing a replacement.
No Rust/retry/review changes or production NFS/deletion enablement.
Increment 47 adds a durable local workers.json process-group epoch before every
worker launch, checks surviving group processes/threads independently of flock
closure, and validates worker group inheritance; see docs/RUST-INCREMENT-47.md.
The epoch pins boot/PID namespace/group/start/guard identity; workers.next is a
private atomic-publication temporary. A live epoch blocks all effect entry points
before SQLite/NFS and makes unserved control OwnerUnavailable even if flock is
free. Do not delete/replace lifetime files, change PID namespace or mix old/new
workers. Preserve increment 46's failed evidence; keep production NFS/deletion
off and remaining systemd/NFS settlement/death phases unqualified.
Local lock release/process exit is not NAS RPC settlement. SH-10–14 and actual
NFS version/mount/systemd qualification remain pending. Preserve the original NF
mapping and stronger deferred takeover/re-enrollment obligations. Keep production
NFS/deletion/remote ingress off and registration/repair deferred.
Maintain `docs/RUST-SCENARIOS.md` with every increment: stable user-situation IDs,
plain behavior/action explanations, actual evidence/scope and DOC-01–06 backlog.
Backfill prior scenarios and do not describe pending qualification as supported.
Preserve `docs/RETENTION-REPAIR-DESIGN.md` for later repair prerequisites.
Every Rust build/test must use `scripts/check-rust-sles.py` (or its WSL wrapper):
cargo-zigbuild target GNU/glibc 2.22, ELF audit and exact target tests in pinned
SLES 12 SP5 userspace. Host-only cargo tests are insufficient. Historical
C++ toolchain/scope/branch guidance below applies to the reference code, and
does not override this direction. Keep production glibc 2.22 and container-only
compatibility qualification. Future branch cleanup requires the branch review.

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

Increment 48 adds the retained `--coordinator-death --death-scope
bootstrap-source-read` fixture: selected fresh, unenrolled bootstrap and accepted
source-read cases, blocked or following local stop, in debug/release. See
`docs/RUST-INCREMENT-48.md` for actual results and limits. Bootstrap must remain
unready without SQLite, then explicitly enroll only after restoration/confirmed
old exit. Preserve source-read custody, old partials and producer-reused paths.
The default claim/copy/verification matrix and increment 47 raw-lock-closure
requirement remain intact. See increment 49 for the selected enrolled/populated
bootstrap extension and increment 50 for selected publication/manifest cases.
Other systemd/NFS/delayed-effect gates remain pending, with no production enablement.

Increment 49 adds `--death-scope bootstrap-existing-state` for selected enrolled-
empty/populated bootstrap deaths. Read docs/RUST-INCREMENT-49.md for actual scope
and results. The populated fixture requires an accepted job, retained WAL and
1 MiB partial; snapshot bytes/identities without opening SQLite, preserve all
original state/receipt/source evidence and recover without re-initialization or
replacement state. Keep prior selectors/strict increment 47 regression intact.
No runtime/dependency/policy change is intended; production NFS/deletion stay off.

Increment 50 adds `--death-scope publication-manifest`: selected pre-publication,
durable file-link and durable manifest-link deaths, debug/release, blocked or
following local stop. Read docs/RUST-INCREMENT-50.md and the raw evidence for
actual outcomes/limits. Release into unavailable NFS and require real D state;
preserve logical ownership through actual old exit, then recover original inode,
manifest hash and attempt 1 with the same local state. Keep older selectors and
strict increment 47 regression. Preserve the initial failed SLES qualification
report/log; see increment 51 for the bounded post-stop status test stabilization.
Runtime deadlines remain unchanged. No runtime/dependency/retry/review changes;
production NFS/source deletion stay disabled.

Increment 51 changes only the repeated-stop API test: bounded post-stop status
polling accepts valid Draining snapshots until the daemon reports its original
expiry, within the existing four-second test bound. Preserve identity, the loaded
two-second budget, nonincreasing remaining time, live ownership/refusal and
normal exit/restart checks. Run three rounds per qualification profile via the
required SLES gate. See docs/RUST-INCREMENT-51.md for actual evidence; keep
increment 50 failure history. No runtime timing or production NFS/deletion change.

Increment 52 retains `--coordinator-death --death-scope both-nfs`: 24 selected
claim/copy/verification/publication/manifest cases with two private NFS roots on
one controlled export and local state. See docs/RUST-INCREMENT-52.md and the raw
both-endpoint evidence. Preserve all prior scopes and strict increment 47 coverage;
separate exports, remaining both-NFS bootstrap/read, exact in-flight RPCs, NAS
settlement and actual systemd/account qualification remain open. Production NFS
and source deletion stay disabled. No runtime policy changed.

Increment 53 retains `--death-scope separate-exports`: 24 selected cases across
two distinct tmpfs-backed NFS exports/mounts on one controlled server, with local
state and a joint outage. Require distinct devices/mount IDs, cross-export link
refusal and original-state custody/publication recovery. See docs/RUST-INCREMENT-53.md.
Keep independent endpoint failures, delayed RPC/NAS settlement, persistent-disk
durability, remaining both-NFS bootstrap/read and systemd/account work pending.
Preserve prior selectors; production NFS and source deletion remain disabled.

Increment 54 retains `--death-scope independent-endpoints`: 28 selected cases,
source-only claim/read and destination-only copy/verification/publication on two
controlled server namespaces/IPs, with local state and fresh healthy-peer probes.
Source-read evidence must not hash/re-warm payload after worker cache invalidation.
See docs/RUST-INCREMENT-54.md and actual results/limits. Keep untested directions/
phases, bootstrap, actual NAS/security/durability, in-flight RPC/settlement and
systemd/account work open. Production NFS/source deletion stay disabled.

Increment 55 retains `--death-scope source-mid-copy`: four selected source-only
copy interruptions across independent controlled endpoints. See
`docs/RUST-INCREMENT-55.md` for actual outcomes/cache controls and limits. Preserve
blocked source read-syscall evidence, unchanged healthy-destination prefix and
original-state recovery. Production NFS/source deletion remain disabled.

Increment 56 retains `--death-scope both-nfs-bootstrap`: eight selected
enrolled-empty/populated startup death/stop cases, source outage with a healthy
NFS destination and local state. See `docs/RUST-INCREMENT-56.md` for actual
outcomes/limits. Preserve separate snapshots, original database/enrollment/
source/binding and populated WAL/partial evidence. Production NFS and source
deletion remain disabled.

Increment 57 retains `scripts/check-systemd-boundaries.py` and the disposable
`scripts/systemd/` fixture. See `docs/RUST-INCREMENT-57.md`: real systemd 252
manager outside a pinned SLES/glibc-2.22 service root, local payload/state only.
Keep native SLES manager/cgroups, actual account/persistence and combined
hard-NFS/systemd qualification open. Same-port starts can fail before guard
acquisition; alternate-port probes share the same state/storage bindings.
Production NFS/source deletion remain disabled.

Increment 58 retains `scripts/check-systemd228-preflight.py`, a pinned
`Containerfile.228` and candidate old unit. See `docs/RUST-INCREMENT-58.md`: the
private cgroup-v2 228-equivalent preflight is BLOCKED; ten lifecycle records
are NOT_RUN. Compiled directive names are not a parser/lifecycle pass. Exact
SLES-maintenance RPM qualification remains separate; no real SLES installation
is required. The initial broader bootstrap rejection is historical: on 2026-10-18
the user explicitly approved it in the Podman VM for increment 59. The retained
`--manager 228 --allow-host-cgroup-bootstrap` path creates only a fresh
controller-free hierarchy and a nonce-owned subtree, then narrows its namespace
view. Never attach to an unknown existing hierarchy or change unrelated process
membership/controllers. Verify empty-subtree and kernel-hierarchy cleanup.
See `docs/SYSTEMD-LIFECYCLE-LAB.md` for every infrastructure/test step and
`docs/TESTING-LIMITATIONS.md` for the evidence boundaries. Preserve the failed
58 preflight and 59 fixture attempts separately from actual lifecycle results.
Increment 59 passes ten local 228-equivalent records, eight armed races and 32
explicit competitor refusals, with verified hierarchy cleanup and fresh SLES
gates. The legacy unit omits global ExecStop: 228 can invoke it after a contender
fails the guard and thereby stop the legitimate foreign owner. Preserve
unit-owned SIGTERM and independent same-user controller checks. See
`docs/RUST-INCREMENT-59.md`; exact vendor patches/kernel, actual account and
persistence policy and combined hard-NFS lifecycle remain unqualified.
Production NFS/deletion remain disabled.

Increment 60 retains `--nfs` on the approved 228 lifecycle driver plus
`scripts/systemd_nfs.py`: four qualification-only actual hard-NFS mid-copy
managed stop/death cases with distinct controlled exports and local state pass.
See `docs/RUST-INCREMENT-60.md` for actual outcomes/limits. Inspect all old
threads, preserve epoch/original state, restore NFS before normal unmount and
remove only owned resources; retain fixtures on uncertain teardown. Maintain
the lab steps, scenario catalog and testing limits. Other phases, actual NAS,
RPC settlement/power durability, exact vendor/kernel and deployment/account
qualification remain open. Production NFS/source deletion stay disabled.

Increment 61 retains `--nfs --nfs-suite restart` for two selected debug/release
incomplete-stop/repeated-start/restoration cases, preserving the default matrix.
See `docs/RUST-INCREMENT-61.md` and lab section 13 for actual outcomes and finite
limits. Preserve original state, real D-worker exclusion through old-thread exit,
manager-versus-application refusal distinctions and explicit operator intervention
where required. Production NFS/deletion stay disabled; remaining SH/release scope
stays open. No Rust, dependency, unit template or shutdown-deadline change.

Increment 62 retains `--coordinator-death --death-scope destination-startup` on
`scripts/check-nfs-boundaries.py` and `scripts/nfs_destination_startup.py` for eight
selected empty/populated debug/release cases. Source startup can finish while
only destination is down; readiness/202 custody is distinct from delivery health.
Read `docs/RUST-INCREMENT-62.md` and `docs/NFS-DESTINATION-STARTUP-LAB.md` for actual
D-worker/death/stop/original-state recovery outcomes. Keep pre-open source-bootstrap
frozen-state evidence distinct from legitimately opened SQLite/WAL. Add SC-096
without renumbering: 96 SC/six DOC IDs. No Rust/policy/dependency/deadline or VM
boot/module change; production NFS/deletion remain disabled and release gates open.

## Project Overview

Background File Mover is a **C++11** durable transfer coordinator with a **REST**
control plane. Simulation orchestration on six Linux hosts records ~100 GB per run to a
local NFS mount; moving that data synchronously stalls the hosts. This service accepts a
submitted recording set, returns a durable acknowledgement immediately, and then moves
the data in the background under a single atomic commit point — disposable before it,
idempotent after (`L1-SEC-001`/`002`). A source file is never deleted until its
destination is durably in place.

Production code uses **only** the C++11 standard library, POSIX, and the vendored
dependencies recorded in `cpp/VENDORED.md`. It targets **SLES 12 SP5** (GCC 4.8.5,
glibc 2.22) and RHEL 9, runs under systemd, and carries full L1/L2/L3 requirement
traceability. See `docs/ROADMAP.md` for milestone status and `cpp/README.md` for build
commands.

**The Python implementation is gone from this branch.** It shipped through v0.4.2 and
remains on `main` and at the `v0.4.2` tag. Several documents still describe it and are
kept deliberately as the rewrite source; every one of them opens with a banner saying
so. **v1.0.0 is narrower than v0.4.2** — see the three easy-to-get-wrong items below.

## Reference docs

**Current — these describe this branch:**

- `cpp/README.md` — build commands, CI tiers, design rules, target REST API shape.
- `docs/L1-REQ.md` — Level 1 SHALL statements, each with a **v1.0.0 Status** annotation
  (Active / Deferred / Partial / Rewritten). The status drives the trace matrix's
  scope-adjusted coverage, so keep the value a bare word on that line.
- `docs/L2-REQ.md` — Level 2 architectural derivations (each with a single L1 `**Parent**`).
- `docs/L3-REQ.md` — Level 3 implementation obligations (`INT`/`EVT`/`CLI`) plus the C++
  constraints `L3-CPP-*`. The `L3-PY-*` section is **retired but retained** — read the
  banner on it before touching anything there.
- `docs/TRACE-MATRIX.md` — auto-generated by `scripts/build-trace-matrix.py`. Forward
  trace from L1 → L2 → L3 to test artifacts, reading **both** `@pytest.mark.requirement`
  markers in `tests/` and **Catch2 tags** in `cpp/tests/` (`TEST_CASE("...",
  "[json][L3-CPP-019]")`). Tagging a C++ test is how a requirement becomes traced.
  Single source of truth for live status; the source docs hold spec content only.
- `docs/CYBERSECURITY.md` — threat model, the v1.0.0 scope boundary, NFS design review.
- `docs/HAND-ROLLED-COMPONENTS.md` — the standard every hand-rolled parser is built to.
- `docs/MIGRATION-PROVENANCE.md` — what the inherited C++ design series contributed and,
  more usefully, what was rejected and why.
- `docs/ROADMAP.md` — **start here in a new session.** Opens with a *Where we left off*
  block (current milestone, live coverage figure, next action), then the **C1–C9 v1.0.0
  milestone plan**, then the merge cadence and the pinned "do not drop" decisions. The
  `M1–M8` section further down is Python history, not outstanding work.
- `docs/MAINTAINER-GUIDE.md` — repo layout, local dev setup, command cheat sheet, CI
  architecture. Start here when onboarding.

**Retired — these describe the Python implementation and are kept as the rewrite
source.** Each opens with a banner. Do not treat any of them as describing current
behavior, and do not "fix" them to match the C++ piecemeal — they get rewritten
wholesale as the corresponding C++ lands.

- `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/USER-GUIDE.md`,
  `docs/CLI-REFERENCE.md`, `docs/CONFIG-REFERENCE.md`, `docs/LOGGING.md`,
  `docs/FEATURE-INTERACTIONS.md`, and the reference config `config/file-mover.ini`.
- `docs/12-FACTOR.md` is **partly** superseded: factor VII inverted when the `AF_UNIX`
  socket became a REST port. Its banner says which parts still hold.

Increment 83 retains buffered actual source-claim LINK/REMOVE successful-reply
hold/release capability and its step-by-step lab in docs/NFS-CLAIM-CAPABILITY-LAB.md.
Keep this capability separate from increment 84 buffered discarded-reply/death recovery.
Maintain SC-117 and DOC-01–05; preserve pre-202 custody and production NFS/deletion
refusal. See docs/RUST-INCREMENT-83.md for finite acceptance and actual evidence.

Increment 84 qualifies selected buffered claim live/death reply-loss recovery;
see docs/RUST-INCREMENT-84.md and docs/NFS-CLAIM-LOSS-LAB.md. Keep full raw
replay proof distinct from original-state reconciliation and remote settlement.
Maintain SC-118/DOC-01–05, unchanged runtime policy and production NFS/deletion off.

Increment 85 isolates source-sync discovery and source-export native withholding;
see docs/RUST-INCREMENT-85.md and docs/NFS-SOURCE-SYNC-LAB.md. Thirty-two actual
source fsync intervals contain no captured RPC; native FILE_SYNC WRITE controls
do not qualify mover source-sync reply loss. Require a positive actual service
RPC before adding those fault cases. Maintain SC-119/DOC-01–05, remaining server
recovery/delayed settlement and production NFS/source deletion disabled.

Increment 86 establishes native NFSD/same-container recovery capability in
scripts/check-nfs-server-recovery.py; see docs/RUST-INCREMENT-86.md and
docs/NFS-SERVER-RECOVERY-LAB.md. Preserve two failed acquisitions, pinned private
IP, confirmed exit, live checkpoint and common-clock proof. Changed session/
write verifier with retained FD/handle is not fresh-netns/VM/NAS reboot or Rust
mover recovery qualification. Maintain SC-120/DOC-01–05 and production NFS/source
deletion disabled; actual worker results are recorded separately below.

Increment 87 extends that runner with --mover; read docs/RUST-INCREMENT-87.md and
docs/NFS-SERVER-MOVER-LAB.md for actual results. Its container sequence first
confirms NFSD threads zero, then SIGKILL/exit-137/start of the same container.
Keep this controlled sequence distinct from abrupt live-NFSD termination, whose
repeated failures and normal-unmount rescues are retained in four FAILED packs.
Do not promote native success, local exclusion or a quiesced restart to NAS/power
or production support. Maintain SC-121/DOC-01–05, audit the exact captured inputs
and run both SLES gates. Keep runtime policy unchanged and production NFS/source
deletion off.

Increment 88 retains --distinct-filesystems with --mover, two bounded tmpfs
local-driver volumes and a separate storage keeper through controlled backend
restart. See docs/RUST-INCREMENT-88.md and docs/NFS-DISTINCT-RECOVERY-LAB.md.
Require actual distinct keeper/backend/client devices, read-only observation and
keeper identity continuity; mount IDs alone do not prove separate filesystems.
Retain the initial proc-bind OCI failure and its exact normal cleanup evidence.
This is memory retained across controlled restart, not persistent disk/NAS/power
or abrupt live-NFSD failure. Maintain SC-122/DOC-01-05, both SLES gates and exact
input/raw-proof auditing. Keep runtime policy and production NFS/deletion unchanged.

Increment 89 retains --verify-recovery with --mover --distinct-filesystems for
actual destination staging reread across the same controlled facilities. See
docs/RUST-INCREMENT-89.md and docs/NFS-VERIFICATION-RECOVERY-LAB.md. Require
Copied/full staging, actual D-state destination read at offset zero, preserved
source/staging/state and absent publication during outage, full original-FD
reread through EOF, then payload/manifest publication and attempt-1 replay.
Use the bounded I/O observer; earlier copy sync precedes attachment. Preserve
unknown READ RPC records without claiming READ session replay, initial caller
artifact-path failure and seventeen exact acquisition sources. Maintain
SC-123/DOC-01-05, both SLES gates and all existing production/policy limits.

Increment 90 retains --publication-recovery with --mover --distinct-filesystems,
excluding --verify-recovery. See docs/RUST-INCREMENT-90.md and
docs/NFS-PUBLICATION-RECOVERY-LAB.md. At file_unlink require PublishIntent,
two complete same-inode payload aliases/two links and absent manifest, then actual
D-state unlinkat on staging FD/name 1.part. Preserve original worker/state/source;
correlate raw REMOVE success within that call, original final inode/one link,
staging absence, later manifest and committed replay. Earlier LINK/file/new-parent
sync precede attachment; no lost-reply, full reclaim or physical durability claim.
Maintain SC-124/DOC-01-05, seventeen frozen sources, both SLES gates and existing
runtime/production NFS/source-deletion limits.

## Git conventions

Do **not** add `Co-Authored-By: Codex ...` trailers to commit messages on this repo, even if the harness's default instructions suggest it. Commit messages are the human-authored record of intent; tool attribution belongs in tool logs, not history. This overrides the default trailer behavior.

Commit subjects use conventional commits with a **capitalized type and a capitalized
subject** — `Type(scope): Capitalized subject`. Merge commits use `Merge: <subject>`.

```
Docs(deploy): Add end-to-end RHEL 9 and SLES 12 platform runbooks
Feat(version): Derive __version__ from package metadata (single source)
Test(trace): Phase A -- mark existing tests for implemented-but-untraced reqs
Merge: Release v0.4.2
```

Bodies explain *why*, and record decisions that were reversed or premises that turned
out to be wrong — a future maintainer should not have to re-derive them.

## C++ / REST migration (in progress on the current milestone branch)

The service is being reimplemented in **C++11** with a **REST control plane** replacing
the `AF_UNIX` socket.

- **Branch**: one per milestone, cut from `main` and named `c<N>-<short-name>` —
  currently `c1-durable-store`. The long-lived `v2-cpp` branch was retired when C0
  merged; see *Merge cadence* in `docs/ROADMAP.md` before merging or branching. The
  Python tree was **removed** ahead of v1.0.0 and is preserved by the `v0.4.2` tag, on
  `origin` as well as locally. `cpp/` is the only implementation on `main` now.
- **`docs/adr/`** — MADR-format decision records, numbered `0001`+. Read these before
  changing the toolchain, the vendoring set, the JSON parser, or the HTTP surface.
- **`docs/MIGRATION-PROVENANCE.md`** — what the inherited C++ design series contributed
  and, more usefully, what was rejected and why. The eight milestone snapshots are fully
  triaged and deleted; `transcripts/` no longer exists. **Read this before
  re-introducing anything from that material, or before assuming a gap in `cpp/` is an
  oversight — several are deliberate.** If a new design conversation arrives, recreate
  `transcripts/` as scratch, follow the same triage rubric, and delete it again.

Three things that are easy to get wrong:

1. **v1.0.0 is narrower than v0.4.2.** `L1-SYS-002/003/004/005/006` — claim, integrity
   verification, conservative deletion, recovery-by-resumption — are **deferred to
   v1.1**, retained verbatim in `docs/L1-REQ.md` with a status annotation. Do not treat
   a Deferred requirement as implemented, and do not delete one to make the matrix
   look clean.
2. **Requirement IDs are reused, not reminted.** `L1-SYS-009` now means C++11/GCC 4.8.5,
   not Python-stdlib-only. The retired docs still describe the old meaning; that is
   expected and their banners say so. Do not reconcile them one line at a time.
3. **Inherited design material is not authoritative.** It came from a conversation that
   designed a standalone project without knowledge of this repo, and has already been
   caught carrying a fabricated premise. Triage it; the repo wins conflicts by default.

Production C++ uses only the C++11 standard library, POSIX, and vendored dependencies
recorded in `cpp/VENDORED.md`. Vendoring is governed by ADR-0004 and the license policy
in ADR-0007 (**BSD-2-Clause and BSD-3-Clause are excluded by internal policy**).

## Local development

The canonical checkout lives **inside WSL** at `~/GIT/background-file-mover`, on the
Linux-native filesystem. Do not clone or build under `/mnt/c`.

```
cd ~/GIT/background-file-mover/cpp
make check                # functional suite, -Werror
make check SANITIZE=1     # ASan + UBSan + LSan
make check-valgrind       # Valgrind memcheck
make verify-vendored      # vendored files match their recorded SHA-256
make locale-free          # parsers never use <cctype> (L3-CPP-052)
make check-ci             # every gate, in a container, as CI runs them
make toolchain            # print the resolved BUILD_DIR for this tier
cppcheck --enable=warning,portability --error-exitcode=1 --std=c++11 -Iinclude src/ tests/

cd ~/GIT/background-file-mover
python3 scripts/build-trace-matrix.py --check   # traceability gate
```

`make check-ci` pipes a long log; **read its tail rather than trusting the exit code of a
pipeline**. A `make ... | tail` reports `tail`'s status, which has silently masked a
failing gate more than once.

The gcc 4.8.5 fidelity tier runs in a container:

```
cd ~/GIT/background-file-mover/cpp && make check-gcc48
```

That target and the CI job pull the **same** image, `ghcr.io/joey-huckabee/gcc-4.8:4.8.5`
— a byte-identical mirror of `docker.io/library/gcc:4.8`, republished with a v2s2
manifest. Do not go back to the upstream tag: it carries a 2016 schema-1 manifest that
modern Docker refuses, which broke the CI job at the pull while podman kept accepting it
locally. Hand-writing the `docker run` invocation is what let those two drift apart.

From Windows, the repository is reachable at
`\\wsl.localhost\Ubuntu\home\joey\GIT\background-file-mover` — that is where new
transcripts and milestone zips get dropped. Edit via VS Code Remote-WSL, which runs a
server inside WSL and avoids the UNC path entirely.

**Why not `/mnt/c`.** Two independent reasons, both measured:

1. **Builds there are intermittently broken.** gcc fails with
   `Assembler messages: can't open /tmp/ccXXXX.s for reading` on some runs and
   succeeds on others — observed failing and passing within a single invocation.
   Root cause is not established; `TMPDIR` on the native filesystem was tried and is
   **not** a reliable fix. An unpredictable build is worse than a broken one.
2. **Small-file I/O over 9p is ~500× slower.** 300 files: 0.005s native versus 2.544s
   on `/mnt/c`. Compilation only pays ~30% because it is compile-bound, but the fuzz
   corpus (ADR-0008) is thousands of small files read on every run — exactly the
   pathological case.

**Build directories are keyed on toolchain** (`build/<machine>-<version>-<tier>`), so
the WSL, container, and sanitizer tiers cannot overwrite one another. Before this,
running the WSL build then the gcc:4.8 container left a glibc-2.34 binary for the
container to execute, failing with a wall of `GLIBC_2.xx not found` that reads as a
code fault and is not one. `make clean` removes only the current tier; `make clean-all`
removes every tier.

Increment 63 qualifies selected file/manifest unlink-syscall and pre-sync crashes;
see docs/RUST-INCREMENT-63.md and docs/NFS-PUBLICATION-SYNC-LAB.md. Four observed
unlinkat calls are client syscall evidence, not on-wire RPC/remote settlement.
Eight pre-sync crashes are not in-flight fsync or disk/power-loss tests. Preserve
original-state owned recovery and the 97-SC/six-DOC catalog. Keep production NFS
and source deletion disabled; remaining in-flight link/sync and SH gates stay open.

Increment 64 adds lost-reply qualification after real-server capability proof;
see docs/RUST-INCREMENT-64.md and docs/NFS-LOST-REPLY-LAB.md. Preserve the initial
failed healthy-TCP discard control and its recovered resources/source snapshots.
Selected REMOVE success replies are withheld/discarded with explicit connection
closure and verified session replay. This is not LINK/sync/power-loss or old-kernel
support. No Rust inputs/dependencies changed; maintain 98 SC and six DOC IDs.
Keep production NFS/deletion disabled and require both capability controls before
running real mover lost-reply cases.

Increment 65 adds server-completed publication LINK reply-loss qualification; see [results](docs/RUST-INCREMENT-65.md). Keep production NFS/deletion disabled and maintain SC-099, the step-by-step lab and remaining reply-loss/durability limits.

Increment 66 adds source-claim LINK/REMOVE success-reply-loss qualification; see [results](docs/RUST-INCREMENT-66.md). Keep production NFS/source deletion disabled, preserve SC-100 and the simple same-ID JSON-until-202 producer workflow, and maintain the step-by-step source lab and testing limits.

Increment 67 records synchronization RPC capability and actual worker observations; see [results](docs/RUST-INCREMENT-67.md) and [lab](docs/NFS-SYNC-LAB.md). No COMMIT/mover sync-loss support follows from buffered OS controls. Preserve SC-101/102, GNU/glibc-2.22 checks and production NFS/source deletion disabled.

Increment 68 defines docs/NFS-MOUNT-PROFILE.md and its step-by-step lab. NMP-41B
is the buffered first-release qualification candidate; NMP-41N retains earlier
noac diagnostic scope. In model-only mode, scripts/check-nfs-mount-profile.py
validates inventory decisions; explicit gate arguments enable the supervised
worker extensions described below. Matching pins can
survive remount with reused IDs and cannot prove server availability/settlement.
Increment 69 below adds supervised descriptor/enrollment-aware checks and selected
buffered worker evidence; keep production NFS/deletion disabled and maintain SC-103-105.

Increment 69 implements explicit per-binding nfs_mount declarations in mover-fs,
with bounded local mountinfo, actual opened-root fdinfo mnt_id cross-check and
before/after profile pins inside supervised authorization. Bindings/markers must
agree; local bindings omit the field and keep existing encodings. Old NFS bindings
without profiles refuse; do not auto-migrate markers/jobs/receipts or re-enroll.
Claims/enrollment/statistics/delivery check bound source before payload traversal;
legacy unbound payload workers refuse NFS. Keep production NFS/deletion off.
See docs/RUST-INCREMENT-69.md and the authorization extension in the mount lab;
increment 70 below adds selected same-share coverage; remaining buffered worker
interruption/sync qualification stays open.

Increment 70 adds scripts/nfs_same_share.py and --same-share in the retained
mount-profile runner: six buffered NMP-41B debug/release baseline and durable
claim/file LINK process-crash/recovery cases on disjoint roots of one mount.
See docs/RUST-INCREMENT-70.md and docs/NFS-SAME-SHARE-LAB.md. Maintain SC-104 and
DOC-03/04/05, original-state recovery and the distinction between returned
operations and pending/withheld RPCs. Keep production NFS/source deletion off;
remaining buffered fault/sync/deployment qualification stays open.

Increment 71 adds scripts/nfs_buffered_reads.py and --buffered-reads to the
mount-profile runner. Require actual blocked read(2)/descriptor evidence for
buffered source_copy/verify_read on same/separate shares, coordinator-death
exclusion through actual worker exit, original-state recovery and replay.
The isolated root observer gets SYS_PTRACE/DAC_READ_SEARCH only for this mode; workers stay
UID/GID 1000 with zero active capabilities. Preserve existing copy attempt-2/
old-partial and verification attempt-1 policy. See docs/RUST-INCREMENT-71.md and
docs/NFS-BUFFERED-READS-LAB.md; maintain SC-106 and DOC-01/03/04/05. Keep failed
capability evidence separate, production NFS/deletion off, and remaining buffered
RPC/bootstrap/publication/manifest/deployment work open.

Increment 72 adds --buffered-publication and scripts/nfs_buffered_publication.py:
buffered same/separate-share file/manifest returned-LINK/pre-sync and actual
pending unlinkat interruption, coordinator death, old-worker exclusion and
original-state attempt-1 recovery/replay. Observe live old threads before restart.
Use scripts/verify-nfs-buffered-publication.py for retained evidence; see
docs/RUST-INCREMENT-72.md and docs/NFS-BUFFERED-PUBLICATION-LAB.md. Keep SC-107
and DOC-01/02/03/04/05 current. Joint-outage POST replay has source revalidation;
do not require healthy replay semantics while both shares are offline. Preserve
failed initial evidence, unchanged retry/review/deadlines, production NFS/deletion
off and remaining bootstrap/claim/post-unlink/sync/RPC/deployment qualification.

Increment 73 adds --buffered-post-unlink and verifier --post-unlink using the
retained publication helper: eight file_unlink_sync/manifest_unlink_sync cases
across buffered same/separate shares and debug/release. Require absent staging
and the original one-link final allocation before death/after old-thread exit,
then original-state attempt-1 commitment and stable replay. No extra syscall-
observer capabilities are needed; workers remain UID/GID 1000 with zero active
capabilities. See docs/RUST-INCREMENT-73.md and
docs/NFS-BUFFERED-POST-UNLINK-LAB.md; maintain SC-108 and DOC-01/02/03/04/05.
Preserve earlier evidence, unchanged retry/review/deadlines, production NFS/deletion
off and remaining bootstrap/claim/actual-sync/RPC/deployment qualification.
Health/status requests each retain a five-second observation bound; combined
host copy/Podman launch cost is diagnostic. Preserve increment 73's failed initial
aggregate-timer report separately from the corrected eight-case qualification.

Increment 74 retains --buffered-claims and its helper/verifier for eight buffered
pre-202 source claim LINK/REMOVE cases; see docs/RUST-INCREMENT-74.md and
NFS-BUFFERED-CLAIM-LAB.md. Preserve original source files/parents until confirmed
202. Require actual D-state syscall/descriptor/flag evidence, retryable 503 with
paths unreleased, surviving-worker exclusion and original-state/inode recovery.
Claim producer-name removal is not post-delivery source deletion. Root syscall
observation needs both SYS_PTRACE and DAC_READ_SEARCH; worker privileges, retry/
review and shutdown deadlines stay unchanged. Maintain SC-109 and DOC-01–05;
production NFS and source deletion remain disabled.

Increment 75 retains --buffered-bootstrap and its helper/verifier for eight
buffered enrolled-empty/populated startup cases; see docs/RUST-INCREMENT-75.md
and docs/NFS-BUFFERED-BOOTSTRAP-LAB.md. Require ordinary 60-second attribute
maxima, fixture cache aging, actual D-state bootstrap with syscall/NFS-RPC wait
evidence, Starting/no false-ready response and surviving-worker exclusion.
Preserve original database/WAL/configuration/enrollment/source/partials through
old-thread exit and recovery; populated jobs retain the old partial and finish
attempt 2. Maintain SC-110 and DOC-01–05. No Rust, retry/review or service deadline
changes; production NFS and source deletion remain disabled.

Increment 76 retains --buffered-sync, scripts/nfs_buffered_sync.py and its
independent verifier: eight healthy NMP-41B claim/delivery traces on both share
layouts and profiles, actual live clock identity, raw RPCs and full mount-ID
synchronization accounting. See docs/RUST-INCREMENT-76.md and
docs/NFS-BUFFERED-SYNC-LAB.md. Withhold only an observed operation after native
capability proof; OS controls do not qualify service sync-loss recovery. Maintain
SC-111 and DOC-01–05; keep production NFS/deletion disabled.

Increment-76 results: 112 successful service NFS syncs contain no captured outgoing
call/incoming reply or captured pair spanning entry. Broader windows decode
WRITE/COMMIT; both native probes observe WRITE, but no service-matching operation
means zero new withholding controls. Capture both relays: actual separate-export
traffic can use the source relay. Next locate real worker I/O/RPC boundaries
before service sync-loss cases; preserve the initial rejected-scope evidence.

Increment 77 retains --buffered-io, scripts/nfs_io_trace.py and
scripts/nfs_io_analysis.py with an independent verifier. Observe eight healthy
buffered claim/delivery workers and capture bounded descriptor/memory evidence,
actual clock identity and both relays. Keep metadata/filehandle matches, byte/
range matches and plain overlap distinct; correctly track SAVEFH/RESTOREFH and
preserve the initial failed analysis. See docs/RUST-INCREMENT-77.md and
docs/NFS-BUFFERED-IO-LAB.md. Maintain SC-111 and DOC-01–05; production NFS/deletion,
Rust/retry/review behavior and deadlines remain unchanged.

Increment-77 result: all eight traces/112 syncs pass. All 20 delivery WRITE/COMMIT
requests match fchmod on the payload/manifest before fsync; 12 WRITE ranges match
earlier captured buffers. Claim-window traffic remains unattributed. Next prove
server-success COMMIT reply withholding at payload fchmod before service fault/
death/recovery tests; old 4 KiB FILE_SYNC controls are not this UNSTABLE path.

Increment 78 retains --buffered-commit: native payload-fchmod COMMIT discovery,
matched server-success reply-withholding release/drop controls, then a finite
same/separate-share debug/release service release/coordinator-death matrix.
Read docs/RUST-INCREMENT-78.md and docs/NFS-BUFFERED-COMMIT-LAB.md for actual
results and proof limits. Preserve original state, orphan guard, uncertain
partials and newer producer bytes. Keep Rust behavior, retry/review/deadlines,
production NFS and source deletion unchanged; UNSTABLE WRITE loss is separate.

Increment 79 retains --buffered-unstable using the shared payload-fchmod lab.
Native matched WRITE stable=0 / committed=0 withholding must precede service
faults. Verify all lost handle/range/hash sets and later COMMIT for UNSTABLE
resends; highest_slotid may change without changing session/slot/sequence identity.
Preserve the initial failed validator run, exact sources and counterexamples.
See docs/RUST-INCREMENT-79.md and docs/NFS-BUFFERED-UNSTABLE-LAB.md. Maintain
SC-113/DOC-01–05; keep production NFS/deletion and all existing policy/deadlines unchanged.

Increment 80 retains --live-loss for the separate --buffered-commit and
--buffered-unstable matrices: twelve native controls and eight short-loss service
cases across both layouts/profiles. Require the same live coordinator, bounded
local API/replay, original assignment/attempt 1 and actual payload RPC recovery.
Account for later other-handle traffic separately while retaining every raw
record; never filter mismatches on the original handle. See
docs/RUST-INCREMENT-80.md and docs/NFS-BUFFERED-LIVE-LOSS-LAB.md. Maintain
SC-114/DOC-01–05; keep all existing policy/deadlines and production NFS/deletion
unchanged. Qualify actual manifest-side RPC capability before defining its fault
matrix; do not assume a tiny manifest emits payload-style UNSTABLE/COMMIT.

Increment 81 retains --manifest-capability: four healthy manifest traces and
four matched successful-WRITE hold/release controls across both buffered layouts/
profiles. Reuse the existing publish checkpoint; add no Rust pause or native
fixture executable. Require exact manifest bytes, scoped descriptor/fsid/fileid,
raw RPC success and actual pending FD/D state, absent final manifest/uncommitted
status while held, then original-inode attempt-1 commitment after release.
See docs/RUST-INCREMENT-81.md and docs/NFS-MANIFEST-CAPABILITY-LAB.md; maintain
SC-115/DOC-01–05 and testing limits. Keep retry/review/deadlines, production NFS
and source deletion unchanged. Manifest reply loss/replay/death remains future
work; never infer manifest COMMIT capability from payload COMMIT observations.

Increment 82 retains --manifest-loss: eight repeated healthy/release controls,
then eight finite live/death manifest FILE_SYNC WRITE reply-loss recoveries on
both buffered layouts/profiles. See docs/RUST-INCREMENT-82.md and
docs/NFS-MANIFEST-LOSS-LAB.md. Preserve separate native live replay and
post-restart application recovery evidence, immutable DB/WAL intent copies acquired
only after confirmed coordinator exit, orphan guard exclusion until actual worker
exit, original state/inode/bytes, and payload attempt 1. Maintain SC-116/DOC-01–05,
testing limits and future-only roadmap; all eight release gates stay open.
Keep production NFS/source deletion, retry/review and deadlines unchanged.

Increment 91 retains --manifest-recovery with --mover --distinct-filesystems,
excluding other selected recovery phases. See docs/RUST-INCREMENT-91.md and
docs/NFS-MANIFEST-RECOVERY-LAB.md. At manifest_unlink require payload Published,
manifest_phase 3, complete same-inode manifest aliases/two links and unchanged
one-link published payload with payload staging absent. Require actual D-state
unlinkat named COMMITTED.part, original-call continuation, correlated raw REMOVE,
remaining sync order and original manifest inode/hash with one link before the
local Committed receipt and original-state replay. Initial manifest LINK/file/
new-parent sync precede tracing. Preserve the consumer's valid-manifest contract;
do not add recorder monitoring or consumer API-polling duties. Maintain SC-125/
DOC-01-05, seventeen frozen acquisition sources, both SLES gates and all existing
production/policy, retained-memory and controlled-termination limitations.

Increment 92 retains --payload-link-recovery with --mover --distinct-filesystems,
excluding other selected recovery phases. See docs/RUST-INCREMENT-92.md and
docs/NFS-PAYLOAD-LINK-RECOVERY-LAB.md. At file_link_rpc require PublishIntent,
complete verified one-link staging and absent final payload/manifest. Require
actual D-state linkat from 1.part to data.bin, both directory FD/path/mount/inode
observations, original-call continuation and successful raw LINK in its interval.
Require final-file/new-parent sync before staging removal, original staging inode/
hash as one-link final, later manifest and attempt-1 original-state replay.
Earlier copying/verification/original-file sync precede tracing. Maintain SC-126/
DOC-01-05, seventeen frozen acquisition sources, both SLES gates and existing
producer/consumer/policy, retained-memory and controlled-termination limits.
Keep production NFS and private-source deletion disabled.

Increment 93 retains --manifest-link-recovery with --mover --distinct-filesystems,
excluding other selected recovery phases. See docs/RUST-INCREMENT-93.md and
docs/NFS-MANIFEST-LINK-RECOVERY-LAB.md. At manifest_link_rpc require Published
payload, manifest_phase 3, one-link complete manifest staging and absent final
manifest, with unchanged one-link verified payload/no payload staging. Require
actual D-state linkat from COMMITTED.part to COMMITTED.json, both directory
FD/path/mount/inode observations, original-call continuation and successful raw
LINK in its interval. Require manifest-file/new-parent sync before staging removal,
remaining syncs, original manifest inode/hash as one-link final and attempt-1
original-state replay. Earlier payload effects/manifest write/original-file sync
precede tracing. Maintain SC-127/DOC-01-05, seventeen frozen acquisition sources,
both SLES gates and existing producer/consumer/policy, retained-memory and
controlled-termination limits. Keep production NFS/private-source deletion off.

Increment 94 retains --publication-sync-discovery with --mover
--distinct-filesystems, excluding other selected recovery phases. See
docs/RUST-INCREMENT-94.md and docs/NFS-PUBLICATION-SYNC-DISCOVERY-LAB.md.
Use the external I/O observer's optional exact-path fsync entry/exit gate; do
not change shipping Rust or substitute syscalls. Exclude artificial ptrace holds
from syscall/RPC intervals. Record actual stopped-NFSD completion versus D-state
syscall 74/expected FD before claiming recovery. Preserve two-name custody,
source/state/epoch, guard exclusion, attempt-1 commit and original-state replay.
Decode raw traffic, interval requests/replies and pairs spanning entry; wider or
unknown traffic/native controls do not establish service-sync capability.
Maintain SC-128/DOC-01-05, eighteen frozen acquisition sources, both SLES gates,
normal cleanup and existing producer/consumer/policy/durability limits. Production
NFS and private-source deletion remain off; directory sync and other profiles
remain separate.

Increment 95 retains --payload-link-death-recovery with --mover
--distinct-filesystems, excluding other phases; see docs/RUST-INCREMENT-95.md
and docs/NFS-PAYLOAD-LINK-DEATH-RECOVERY-LAB.md. Kill only the coordinator
while payload linkat is actually D. Require old-group logical ownership and
specific service/initialize/transfer contender refusal through actual worker exit;
physical flock closure is separate. Restore before draining, retain unfinished
old syscall traces as such, independently observe remote namespace/custody, then
recover original state/attempt/inode and preserve producer reuse. No automatic
uncertain-effect redispatch or remote settlement inference follows from local
exit. Maintain SC-129/DOC-01-05, seventeen frozen sources, both SLES gates,
normal cleanup and explicit retained-memory/controlled-restart limits. Next
qualify manifest-LINK coordinator-death cases. Production NFS/source deletion
off; blocked sync discovery and remaining phases/deployment remain open.

Increment 96 retains --manifest-link-death-recovery with --mover
--distinct-filesystems, excluding other phases; see docs/RUST-INCREMENT-96.md
and docs/NFS-MANIFEST-LINK-DEATH-RECOVERY-LAB.md. Require actual pending
COMMITTED.part-to-COMMITTED.json linkat, old-group exclusion/three contender
refusals through actual exit, independent original manifest/payload/source custody,
and original-state attempt-1 recovery/replay. Preserve exact local DB/WAL copies
after coordinator death and after old-worker exit; independently query copies
only. Manifest phase 3 is distinct from visible valid completion bytes; do not
add recorder post-202 monitoring or consumer API polling. Maintain SC-130/DOC-01-05,
seventeen frozen sources, both SLES gates and normal cleanup. Next qualify
source-claim LINK coordinator-death before 202. Keep production NFS/private-source
deletion off; local exit is not remote-settlement proof and all eight gates stay open.

Increment 97 retains --claim-link-death-recovery with --mover
--distinct-filesystems; see docs/RUST-INCREMENT-97.md and
docs/NFS-CLAIM-LINK-DEATH-RECOVERY-LAB.md. The fixture module uses actual
source claim_link_rpc, coordinator-only death and exclusion through actual exit.
Require non-202/connection-loss original HTTP evidence, no producer changes until
confirmed same-ID retry 202, independent original/private custody and exact copied
SQLite/WAL pending claim done=0/no transfer or manifest before replacement. Verify
original-state attempt-1 delivery/replay and preserve producer reuse. Maintain
SC-131/DOC-01-05, eighteen frozen acquisition sources, both SLES gates and normal
cleanup. Next qualify pending claim REMOVE before 202. Production NFS/postcommit
private-source cleanup stay off; claim-name removal is a separate operation and
local exit never proves globally settled delayed effects. Eight gates remain open.

Increment 98 retains --claim-remove-death-recovery with --mover
--distinct-filesystems; see docs/RUST-INCREMENT-98.md and
docs/NFS-CLAIM-REMOVE-DEATH-RECOVERY-LAB.md. Require same-inode two-name source
custody at claim_unlink_rpc, actual D-state unlinkat, coordinator-only death,
old-worker exclusion/three contender refusals through actual exit and independently
decoded preceding LINK/resumed REMOVE. Preserve original non-202 HTTP outcome,
raw local DB/WAL pending done=0/no transfer or manifest, original-state custody,
identical-ID retry 202 before producer reuse and attempt-1 commitment/replay.
Maintain SC-132/DOC-01-05, eighteen frozen sources, initial pre-mount SSH failure,
both SLES gates and normal cleanup. The observer attaches at REMOVE, excluding
earlier file/new-parent syncs. Next discover positively observed source-claim sync
RPC boundaries before selecting more synchronization cases. Keep production NFS/
postcommit private-source cleanup off; claim-name removal is separate and local
exit is not global delayed-effect settlement. Eight release gates remain open.

Increment 99 retains --claim-sync-discovery with --mover --distinct-filesystems;
see docs/RUST-INCREMENT-99.md and docs/NFS-CLAIM-SYNC-DISCOVERY-LAB.md. Eight
private-file/private-parent fsync debug/release x healthy/stopped-NFSD observations
follow four native prerequisites. nfs_io_trace permits only fixture source or
destination gate paths; actual syscall intervals exclude bounded artificial holds.
Require complete two-name custody/Accepted state and no 202 while held, then
confirmed same-ID 202 before producer reuse, attempt-1 delivery and original-state
replay. Maintain SC-133/DOC-01-05, eighteen frozen acquisition sources, both SLES
gates and normal cleanup. Retain the initial shared case-count assertion failure
and exact count-only correction/full rerun. Classify raw interval/spanning RPCs without causal
inference; successful local sync with stopped NFSD is not blocked-sync recovery.
Next discover original-file sync before LINK and remaining cache/workload RPC
boundaries. Production NFS/postcommit private-source cleanup stay off; all eight
release gates remain open. Registration/S3/offline repair/DOC-06 stay deferred.

Increment 100 retains --original-claim-sync-discovery with --mover --distinct-filesystems;
see docs/RUST-INCREMENT-100.md and docs/NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-LAB.md.
Four native prerequisites and four original-file fsync observations before LINK
pass; eighteen frozen acquisition files, exact observer intervals, complete one-link
original/private absence and no 202 while held are independently audited. Both
stopped-NFSD calls complete locally with no selected RPC; following successful LINK
pairs calibrate capture. Eight syncs per worker, confirmed same-ID 202 before reuse,
attempt-1 delivery/replay, both SLES gates and normal cleanup pass. Retain the initial
SSH setup failure and exact unchanged-source retry. Maintain SC-134/DOC-01-05;
prioritize remaining joint-outage replay/revalidation/admission. Positive actual
service RPC evidence remains required before further synchronization recovery.
Production NFS/private-source cleanup stay off; all eight release gates stay open.
Registration/S3/offline repair/DOC-06 remain deferred.

Increment 101 retains --joint-outage with --mover --distinct-filesystems;
see docs/RUST-INCREMENT-101.md and docs/NFS-JOINT-OUTAGE-LAB.md. Four native
prerequisites plus four debug/release x source-space admission off/on cases test
claimed replay and bounded requests on distinct source/destination NFS mounts
sharing one backend. Require actual blocked destination read and source validation,
complete original custody and confirmed initial 202 before producer reuse, bounded
non-release 503 queue refusals, two stable data workers and zero/off or at most
one/on observed probe, allowing actual probe exit.
One-job retention preserves new-ID refusal; original attempt-1 delivery/restart
replay, both SLES gates and normal cleanup pass. HTTP waiter timeout never proves
queued-command cancellation. Maintain SC-135/DOC-01-05 and seventeen frozen sources.
Next qualify pre-202/partial-claim replay, source-change refusal and independent/
longer outage or broader capacity cases. All eight release gates remain open;
production NFS/private-source cleanup stay off. Registration/S3/repair/DOC-06 defer.

Increment 102 retains --pre202-replay with --mover --distinct-filesystems;
see docs/RUST-INCREMENT-102.md and docs/NFS-PRE202-REPLAY-LAB.md. Four native
prerequisites plus four debug/release x pending source LINK/REMOVE one-file cases
qualify replay and finite queue refusal before 202. Keep producer paths untouched,
Accepted/non-release state, complete one-/two-name custody, no delivery and the same
actual D-state claim worker/epoch through retries. Require confirmed same-ID 202
before producer reuse, original private inode/attempt-1 delivery, valid manifest
and original-state restart/replay. Both SLES gates, seventeen frozen sources,
raw successful LINK/REMOVE/corruption/ELF audits and normal cleanup pass. Preserve
initial gate/fixture SSH failures and unchanged-code retries. Maintain SC-136/
DOC-01-05; multi-file partial handoffs and source-change/independent-endpoint/load
cases remain next work. All eight release gates remain open; production NFS/
private-source cleanup stay off. Registration/S3/repair/DOC-06 remain deferred.

Increment 103 retains --partial-handoff-replay with --mover --distinct-filesystems;
see docs/RUST-INCREMENT-103.md and docs/NFS-PARTIAL-HANDOFF-LAB.md. Qualification-only
FILE_MOVER_QUALIFICATION_CLAIM_INDEX=1 scopes existing LINK/REMOVE pause to second
file after first claim completes. Four native controls/four debug-release cases
preserve one confirmed claim, Accepted/non-release, no delivery, complete custody
and same actual D-state worker/epoch through retries. Confirm whole-set 202 before
any reuse; require original/private payloads, attempt-1 delivery, exact two-file
manifest and original-state restart with newer bytes preserved. Both SLES gates
(211 production/213 qualification per profile), forty ELFs, raw/corruption audits
and normal cleanup pass. Retain initial rustfmt and premature artifact-loading
failures; wait for both passing gate reports before the complete fixture run. Maintain SC-137/
DOC-01-05. Next qualify source-change refusal, remaining multi-file boundaries and
independent-endpoint/load cases. Eight gates stay open; production NFS/private-source
cleanup stay off; registration/S3/repair/DOC-06 defer.

Increment 104 retains --source-change-refusal with --mover --distinct-filesystems;
see docs/RUST-INCREMENT-104.md and docs/NFS-SOURCE-CHANGE-LAB.md. Four native controls
and four debug/release x second-file inode/size change cases on healthy NMP-41B NFS
retain first/private custody and original pending intent. Existing 409 recording_blocked
is non-retryable across two unpaused restarts; no whole-set 202 or delivery. Durable
status stays Accepted/AwaitingClaims, one confirmed claim and unchanged review epochs.
Retain the initial Windows temporary-directory audit failure and exact verifier/raw
report; corrected extraction stays in rust/validation and closes SQLite handles.
Independent audit reopens sixteen quiescent/stopped SQLite/WAL copies; original claims
remain [done,pending] with no transfers/manifests. No Rust/dependency/API/retry/review/
deadline changes or automatic repair. Both SLES gates (211/213 per profile), forty
ELFs, raw/corruption audit and normal cleanup pass. Maintain SC-138/DOC-01-05.
Other source/parent/timing boundaries and independent-outage/load cases remain open.
Keep production NFS/private-source cleanup off and eight release gates open;
registration/S3/offline repair/DOC-06 defer. Preserve original state/custody on refusal;
never bypass an old intent by recreating the database or using a new ID.
