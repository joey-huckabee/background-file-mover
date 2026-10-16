# AGENTS.md

## Current direction (2026-10-13)

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
SC-075–081 remain future; no config/API enforcement or qualification exists yet.
Preserve accepted replay/partial claims and existing limits; qualify bounded
source probes before implementation is called supported.
Do not auto-enroll missing/foreign
markers, treat directory locks as distributed fences, or enable automatic takeover.
Next qualify in-flight link/unlink RPCs, other sync boundaries, outages beyond
those selected cases, stable root/export
authorization and cross-client ownership. If Ubuntu user startup prevents rootless
Podman, use the documented Windows/Podman WSL2 gate fallback in
`docs/NFS-QUALIFICATION.md`; preserve all compatibility checks.
Keep production NFS and deletion disabled.
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
