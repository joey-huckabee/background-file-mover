# Roadmap

Forward-looking milestone plan for the Background File Mover. Each milestone is a
vertical, CI-green, fully-tested slice that advances the requirements in
`docs/L1-REQ.md` / `L2-REQ.md` / `L3-REQ.md`. Completed work lives in `CHANGELOG.md`
and the trace matrix (`docs/TRACE-MATRIX.md`), not here.

---

# WHERE WE LEFT OFF

**Date:** 2026-08-06 · **Branch:** `c4-job-manager` · **Current milestone: C4 — the job
manager and worker pool are built. C3 is merged. C4 is ready to merge.**

**Every tier is green**, including the ones that were not when C4 started:

```
In v1.0.0 scope:  109 of 214 requirements verified (50.9%)
Tests:            8,519 assertions / 208 cases
Line coverage:    87.5% overall (floor 85%)
Tiers:            default, GCC 4.8.5 fidelity, ASan/UBSan/LSan,
                  ThreadSanitizer, Valgrind, coverage, clang-tidy,
                  seven source gates -- all green
```

**The denominator moved and the numerator did not.** 226 → 214 because three
scoping defects were corrected, not because work was verified. Do not read 44.2% → 50.9%
as six points of progress; roughly half of it is the denominator being made honest.

**Read `docs/C4-TSAN-RESOLVED.md` before writing any threaded code.** The headline:
`std::condition_variable::wait_until` breaks ThreadSanitizer's accounting for the mutex
passed to it — it then believes the mutex is held after an explicit unlock, reports a
phantom double lock, and treats everything that mutex guards as unsynchronised. Correct
C++, unusable under TSan. Do not reach for a timed wait on a mutex that also guards data.

**The rule the manager now follows: no store call happens with the manager mutex held.**
A durable write can block on `busy_timeout` for five seconds, and that mutex is what every
worker takes to pick up its next job. Commands claim an id, write outside the lock, then
publish. `store_mutex` may be held while taking the manager mutex; the reverse is never
done.

### Decisions taken during C4 (previously open)

1. **`L2-COPY-001/002/003/011` reparented** from `L1-SYS-001` to the already-deferred
   `L1-SYS-003`. `L2-COPY-004` deliberately stayed: despite the prefix it constrains
   concurrency generally and applies to the C4 worker pool.
2. **Decorative `v1.0.0 Status` annotations removed.** Deferral is expressible only at L1,
   where the generator enforces it.
3. **The `L3-PY-*` category deleted** — with each of the fourteen inspected first so no
   feature left with its mechanism. Five substantive constraints were preserved; see the
   table in `docs/L3-REQ.md`.
4. **Manual retry submits a new job** rather than reviving the failed one, because FAILED
   is terminal and the record of the failure is what an operator needs.
5. **Schema migrations dropped until v1.0.0 ships** — see *Owed* below.

`docs/C2-PLAN.md` remains worth reading for the constraint it established: `renameat2`,
`RENAME_NOREPLACE` and `SYS_renameat2` are all absent on the target toolchain, so the
rename goes through `syscall(2)` with constants we supply. Code calling it directly
compiles on a modern host and fails to link on SLES 12 SP5.

**Historical — the figures as they stood at the close of C3.** The denominator has since
been corrected from 226 to 214, so these are not comparable to the current numbers above
without that adjustment.

```
In v1.0.0 scope:  100 of 226 requirements verified (44.2%)
Tests:            8,067 assertions / 187 cases      (all tiers green)
Line coverage:    88.0% overall (mover 76.5%, fsops 81.3%, store 79.6%)
```

The figure moved only two points, against the roadmap's ~55% estimate and C3-PLAN's
revised ~48–50%. Both were wrong for the same reason, now written down: a milestone's
contribution depends on how many requirements it is the **first** to verify, not on how
much work it is. C3 adds only `L2-XFR-001` and `L2-XFR-004` as newly traced; everything
else it touches was already traced by C1 and C2, and the L1s it satisfies are composite
and counted transitively. Estimate future milestones by listing the specific untraced IDs
they will close.

**The move engine exists and the commit point is real.** `MoveEngine`
(`cpp/include/filemover/mover.hpp`) runs six phases with exactly one atomic commit —
the rename out of the source directory. Before it nothing has happened; after it every
step is idempotent, including the state machine. **No path deletes a source whose
destination is not in place, structurally rather than by care:** the source is never
deleted, it is renamed, and one syscall both removes the old name and creates the new.

The kill-after-every-phase suite found two real idempotency bugs — the engine re-issued
transitions the store correctly refused, on both sides of the commit point. That is the
suite doing exactly what it exists for.

**C0 (the foundation) is delivered and merged.** Five components are built, tested,
fuzzed where they touch untrusted input, and green on every gate including the GCC 4.8.5
fidelity tier: the strict-subset **JSON parser** and REST codec, the **configuration
loader**, the **job model and state machine**, the **rename template engine**, and the
**HTTP request-head parser**. The full CI apparatus is in place — fifteen gates. C0 was
merged into `main` and published, `v2-cpp` was retired, and work now happens on one
branch per milestone (see *Merge cadence*).

**Nothing that moves a file exists yet.** There is no durable store, no filesystem layer,
no move engine, no job manager, no socket server, no daemon entry point. The service
cannot start, because there is no `main`.

```
In v1.0.0 scope:  97 of 226 requirements verified  (42.9%)
Tests:            7,638 assertions / 161 cases     (all tiers green)
Line coverage:    90.5% overall (fsops 85.3%, store 79.6%)
```

The figure landed at 42.9% against `docs/C2-PLAN.md`'s revised estimate of ~43%, not the
roadmap's original ~45% — because four of the sixteen `L2-SEC-*` requirements listed
under C2 actually belong to C4, C8 and C9. The plan said so before the work started,
which is the only reason the number reads as correct rather than as a shortfall.

**SQLite is vendored** at **3.53.4**, pinned per file in `cpp/VENDORED.md`, verified on
real GCC 4.8.5 rather than assumed.

**The durable store exists.** `JobStore` (`cpp/include/filemover/store.hpp`,
`cpp/src/store.cpp`) is the repository interface ADR-0010 called for: WAL and
`synchronous=FULL` both *read back* after being set rather than assumed, idempotent
migration keyed on `PRAGMA user_version`, an absent store treated as first boot
(`L2-JOB-011`), a corrupt or newer-than-known store refused outright with the damage
named and the bytes left untouched (`L2-JOB-012`), write-ahead intent recording
(`L2-JOB-013`), and a durable monotonic sequence committed before it is handed out
(`L2-JOB-015`).

`L2-JOB-009` stopped being an inspection: `make sql-confined` fails the build if
`sqlite3.h` or SQL appears outside the repository. Like every gate here it was verified
by deliberately introducing the violation and confirming it fails.

The figure came out at 37.2% against an estimate of ~30%, which is worth explaining
rather than celebrating: C1's requirements are traced directly at L2, and the milestone
carried more of them than the per-family estimate assumed.

**`L2-JOB-014` is finished on the store side.** `record_transition` classifies a
durable-write failure by commit phase — abort before, halt after — and is tested against
a real SQLite refusal through `inject_write_fault`, not a mocked return value. C3
inherits the decision and carries it out.

**The CI apparatus was audited at the close of C1**, after it broke three times in as
many milestones. All eight gates were negative-tested — the violation each exists to
catch was deliberately introduced and the failure confirmed — and three findings came
out of it worth remembering: the pre-commit hook had never run in this clone
(`core.hooksPath` unset *and* the file not executable); it would have rejected the SQLite
vendoring outright, because its 1 MB limit had no exemption for hash-pinned vendored
files; and SonarCloud was analysing a `g++-13` build while every gate verifies `g++-14`.

**What is left for C2 onward:** migration fixtures and conformance corpora, both in
`docs/TEST-STRATEGY.md`, and a true kernel-level `EFBIG` injection now that C2 starts
writing files rather than rows.

Read `docs/CYBERSECURITY.md` before starting C2, and this file's *Locked decisions*
before starting anything.

---

## v1.0.0 milestone plan (C1–C9)

Nine milestones remain. The ordering is a dependency chain, not a preference: C3 cannot
be written safely before C2 exists, and C2's guarantees are meaningless without C1's
commit record. Deviating from the order means building the data-safety layer last, which
is how the security requirements get retrofitted instead of designed in — the exact
mistake `docs/CYBERSECURITY.md` §10 documents.

Milestone numbering is `C` for the C++ implementation, distinct from the Python `M1–M8`
retained further down for history.

**Merge to `main` at each milestone boundary** — see *Merge cadence* below.

### C1 — Durable store (SQLite)

Authoritative job state in SQLite (WAL, `synchronous=FULL`) behind a repository
interface, per ADR-0010.

- **Advances:** `L2-STO-001..005`, `L2-JOB-001..015` (14 in v1.0.0 scope)
- **First task — done.** The SQLite amalgamation is vendored and pinned at 3.53.4 with
  per-file SHA-256s, and `make verify-vendored` now checks four files rather than two.
  Two things learned doing it, both recorded in `cpp/VENDORED.md`: the `pending` row's
  `sqlite3.{c,h}` shorthand could never have been checked, because the verifier parses
  one path and one hash per row and silently skips a row it cannot parse; and the CI
  container had no C compiler at all, since `g++-14` alone provides no `cc`.
- **Carries the three hardest ideas in the project**, all inherited from the M8 triage
  and none of them optional:
  - `L2-JOB-013` **write-ahead ordering** — the intent is durable *before* the job
    exists. A crash between acting and recording loses the file.
  - `L2-JOB-014` **phase-dependent write-failure handling** — a durable-write failure
    before the commit point aborts; after it, the process halts. Treating both as a
    retry counter lets the record drift from the filesystem.
  - `L2-JOB-015` **durable, monotonic job sequence** across restarts. Without it,
    identifiers repeat after every restart and `{seq}` collides.
- **Done when:** a fresh store initializes on first boot (`L2-JOB-011`); a corrupt store
  is a hard error, never a silent reset (`L2-JOB-012`); `error` is present if and only if
  state is `FAILED`, enforced as a `CHECK` constraint (`L2-JOB-010`); and a kill-at-every-
  statement test leaves the store readable and the sequence non-repeating.

  **Status: met.** All four done-when clauses are satisfied and tested, and all three of
  the hard ideas are built.

  `L2-JOB-014` is complete on the store side. `record_transition` takes the `CommitPhase`
  and returns `AbortJob` before the commit point, `HaltProcess` after — the same failure,
  the opposite verdict — and always sets an error, so there is no path that continues
  silently. It is verified against a *real* SQLite write refusal rather than a mocked
  return value, via `inject_write_fault`, because what has to work is detecting SQLite
  failing rather than us pretending it did.

  What remains for C3 is only *carrying out* the verdict: aborting a job and halting a
  move are the engine's actions, and the engine is the component that knows which side of
  the commit point it is on. The classification is settled here so C3 inherits a decision
  rather than making one.

  One consequence is worth knowing before C3 relies on it: on the `HaltProcess` path the
  attention flag is **best-effort**. If the durable write failed because the store is
  unwritable, recording the flag is another write to that same store and fails too. That
  is why the requirement also demands logging at high severity — the log is the
  guarantee; the flag is the convenience that survives when the store is inconsistent
  rather than unreachable. There is a test pinning exactly this.

### C2 — fd-relative filesystem layer

The layer every later milestone touches the disk through. No path-based
check-then-act anywhere.

**A detailed plan exists: `docs/C2-PLAN.md`.** Read it before starting. Its
pre-flight measurements change the design rather than the implementation — most
importantly, the target toolchain has **no `renameat2` wrapper and no
`RENAME_NOREPLACE` constant** (both need glibc ≥ 2.28; SLES 12 SP5 ships 2.22),
so it must be called through `syscall(2)` with constants we supply. Code that
calls `renameat2` directly compiles on a modern host and fails to link on the
target. The plan also splits out the four requirements the roadmap assigns to
C2 that actually belong to C4, C8 and C9.

- **Advances:** `L2-SEC-001..016` (16), `L2-NFS-001..008` (8)
- **Scope boundary, from `L1-SEC-007`:** same filesystem only, regular files only. Both
  remove attack surface rather than save effort — `linkat` does not work on directories,
  and NFS has no `RENAME_NOREPLACE`, so an atomic no-clobber directory move does not
  exist on the target filesystem at all.
- **Primary/fallback, and note which is which:** `renameat2(RENAME_NOREPLACE)` is the
  primary; on NFS it is unavailable, so `linkat` + `unlinkat` is not a degraded path
  there but *the* path. Test both deliberately.
- **Done when:** every filesystem call is `openat`/`fstatat`/`renameat2`/`linkat`/
  `unlinkat` relative to a held descriptor with `O_NOFOLLOW`; a symlink-swap fault
  injection suite cannot find a window; and the NFS behaviors in `docs/CYBERSECURITY.md`
  §4 each have a probe.

### C3 — Move engine (single commit point)

The bytes actually move. One atomic commit point: everything before it disposable,
everything after it idempotent.

- **Advances:** `L1-SEC-001`, `L1-SEC-002`, `L1-SYS-015`, `L2-XFR-001..003`, the
  in-scope `L2-COPY-*`
- **Explicitly not here:** claim semantics, integrity verification, conservative
  deletion, recovery-by-resumption. Those are `L1-SYS-002..006`, **deferred to v1.1**.
  Do not implement them early to feel complete — v1.0.0 is deliberately narrower.
- **Also not here:** any external command. ADR-0011 removed `ExecTransfer`; a free-text
  command in configuration makes the config file executable and voids the commit-point
  guarantee.
- **Done when:** `SIGKILL` between every pair of phases leaves a state the next start can
  reconcile, and no failure path can delete a source whose destination is not durably in
  place.

### C4 — Job manager and worker pool

The first threads in the project. ThreadSanitizer has been gating since before any
thread existed (`L2-ARC-008`), deliberately.

- **Advances:** `L2-MGR-001..003`, `L2-LIF-*` (3 in scope), `L2-RTY-*` (5 in scope)
- **Adopt the practices already triaged in:** latch-based concurrency tests and an
  injected clock, so scheduling is deterministic in tests rather than hopeful.
- **Done when:** TSan is green under a suite that deliberately interleaves submit,
  cancel, and shutdown; and a worker crash cannot wedge the queue.

### C5 — REST control plane

The routes and socket server deferred from the M9/M10 triage. The request-head parser
they sit on is already delivered.

- **Advances:** `L2-CTL-001..016` (the pre-existing 16)
- **Two rules kept from the inherited design, worth re-reading before starting:** bytes
  beyond the declared `Content-Length` are a `400` — no pipelining, no smuggled second
  request; and the integration test fires the hostile battery *first* (garbage, oversized
  head → 431, gigabyte declaration → 413, chunked → 400, trailing bytes → 400) and then
  proves the same server instance still completes a real job.
- **Open design point, flagged at triage and still open:** the inherited server was
  serial-accept, which contradicts `L2-SEC-010` (one stalled connection must not block
  others) and needs `L2-SEC-009` per-syscall timeouts. Decide the concurrency model
  before writing it, not after.
- **Done when:** the hostile battery passes, timeouts are per-syscall rather than
  per-request, and a stalled client cannot starve another.

### C6 — Daemon entry point

`main`, signals, and the startup sequence. The service becomes runnable here.

- **Advances:** `L2-CTL-017..020`, `L2-EVT-001..005`
- **Requirements already written for this, from the final triage:** handler assigns only
  to a `volatile sig_atomic_t` (`L2-CTL-017`); `SIGPIPE` ignored process-wide
  (`L2-CTL-018`); `--check` config validation for systemd `ExecStartPre` (`L2-CTL-019`);
  ordered startup with reverse-order teardown (`L2-CTL-020`).
- **Do not copy the inherited 200 ms `nanosleep` wait loop.** Block on `sigsuspend` or a
  self-pipe; a daemon should not wake five times a second forever to poll a flag.
- **Done when:** `systemctl start/stop` is clean, `--check` fails the unit on a bad
  config before anything is created, and shutdown drains rather than aborts.

### C7 — Operator dashboard

- **Advances:** `L2-DASH-001..003`
- **`L2-DASH-003` is the load-bearing one:** every dynamic value enters the DOM through
  `textContent`/`createTextNode`, never `innerHTML`. Paths are attacker-influenced by
  definition — whoever can create a file chooses its name — and the operator's browser
  holds the one session with authority over this service.
- **Done when:** single self-contained page, no external resources, and a test feeds a
  filename containing markup and proves it renders as text.

### C8 — Packaging, hardening, deployment

- **Advances:** `L2-SEC-014`, `L2-ENV-001..003`
- **The hardened unit is already specified** and is stronger than the inherited one:
  `ProtectSystem=strict`, `ReadWritePaths=` limited to managed trees, `NoNewPrivileges`,
  `PrivateTmp`, `ProtectHome`, a trimmed `CapabilityBoundingSet=`, a dedicated service
  account, and `UMask=0077`.
- **Done when:** the service installs and runs unprivileged on RHEL 9 (SELinux) and
  SLES 12 SP5 (AppArmor), and the environment diagnostic gates the deployment.

### C9 — Qualification and documentation

The milestone that makes v1.0.0 *shippable* rather than merely built.

- **NFS qualification on real hardware** — the checklist in `docs/DEPLOYMENT.md` is
  implementation-neutral and hard-won; keep it through the rewrite.
- **The documentation rewrites owed** (table below) come due here.
- **Done when:** the scope-adjusted trace figure is at 100% for in-scope requirements,
  every retired-banner document has been rewritten or consciously re-deferred, and the
  release checklist passes on both target platforms.

### Milestone-to-coverage expectations

A rough shape of the in-scope trace figure as each lands, so a number that comes out
badly wrong is a signal rather than a surprise:

| After | In-scope verified (approx.) |
|---|---|
| C0 (today) | 21% |
| C1 | ~30% |
| C2 | ~45% |
| C3 | ~55% |
| C4 | ~63% |
| C5 | ~75% |
| C6 | ~82% |
| C7 | ~85% |
| C8 | ~92% |
| C9 | 100% in-scope |

These are estimates from requirement counts per family, not commitments. The figure that
matters is the one `build-trace-matrix.py` prints.

## Merge cadence — milestones on `main`

Each milestone is developed on **its own branch off `main`** and merged back at the
milestone boundary. **These merges are progress markers, not releases: no version bump,
no tag, no changelog release heading.**

Branch naming is `c<N>-<short-name>`: `c1-durable-store`, `c2-fs-layer`, and so on.

```bash
# from a clean, fully green milestone branch
git checkout main
git merge --no-ff c1-durable-store -m "Merge: C1 — durable store"
git push origin main

# the finished milestone leaves no branch behind
git branch -d c1-durable-store
git push origin --delete c1-durable-store

# the next milestone starts from main, not from the previous branch
git checkout -b c2-fs-layer
git push -u origin c2-fs-layer
```

`--no-ff` is required so each milestone is one identifiable commit in `main`'s history.

**Why not one long-lived branch.** Every C++ commit through C0 sat on a single `v2-cpp`
branch. By the time C0 closed it had been merged into `main` but not deleted, so the two
refs described identical content while the existence of a separate branch implied they
diverged — and `origin/v2-cpp` was seven commits stale on top of that. A branch per
milestone makes the unit of work, the unit of review, and the unit of merge the same
thing, and a finished milestone leaves nothing behind to go stale. `v2-cpp` was retired
at the C0 boundary; every commit it carried is reachable from `main`.

**Bar for merging — the same as for committing, no lower:**

1. `make check-ci` green (read the tail of the log, not a pipeline's exit code)
2. the GCC 4.8.5 container tier green
3. `python3 scripts/build-trace-matrix.py --check` clean
4. `docs/TRACE-MATRIX.md` regenerated and committed

**The Python implementation is safe.** It is preserved in full by the `v0.4.2` tag —
verified, 38 source files — so merging the C++ branch into `main` removes Python from
`main`'s *tip* but destroys nothing. `v0.4.2` remains the version to deploy until v1.0.0
ships. The tag is on `origin` as well as locally, at `9930a60`, which was `origin/main`'s
tip before the C0 merge was published; confirm that with `git ls-remote --tags origin`
before any operation that rewrites what `main` points at.

**Publishing is part of closing a milestone, not a separate errand.** `main` is pushed
at the boundary and the milestone branch is deleted on `origin` once merged. Leaving the
merge unpublished is what let `origin/main` fall 34 commits behind during C0.

One sharp edge worth knowing before it costs an hour: `git branch -d` refuses to delete a
branch that is ahead of *its own upstream*, even when the branch is fully merged into
`main` — the message says "not fully merged", which reads as data loss and is not.
Delete the remote branch first, then the local one. To satisfy yourself before deleting,
`git merge-base --is-ancestor <branch> origin/main` answers the question that actually
matters.

## Documentation rewrites owed

The Python implementation was removed from this branch ahead of v1.0.0. Several documents
that describe it were **kept deliberately** rather than deleted, so the behavior and
reasoning are not lost to a tag — each opens with a banner. Every one of them owes a
rewrite against the C++ implementation, and this list is the only thing standing between
"kept on purpose" and "quietly stale."

Rewrite each when the C++ it describes exists — not before, and not piecemeal.

| Document | Rewrite when | Notes |
|---|---|---|
| `docs/ARCHITECTURE.md` | The manager and transfer engine exist | Process/thread model changes completely: no GIL, real worker threads, TSan already gating |
| `docs/CLI-REFERENCE.md` | A C++ client exists, if one ever does | The thin CLI over `AF_UNIX` is gone; REST may make a bespoke client unnecessary |
| `docs/CONFIG-REFERENCE.md` | The C++ schema settles | Pair with `config/file-mover.ini`; `[journal]` is `[storage]` now (ADR-0010) |
| `docs/LOGGING.md` | The daemon has a logging path | The `-O`/`__debug__` gating convention is Python-specific and has no C++ analogue |
| `docs/DEPLOYMENT.md` | The daemon can be deployed | Keep the NFS qualification checklist — it is implementation-neutral and hard-won |
| `docs/USER-GUIDE.md` | v1.0.0 is shippable | |
| `docs/FEATURE-INTERACTIONS.md` | The v1.1 features return | Kernel copy, bandwidth limiting, resume are all v1.1 |
| `docs/12-FACTOR.md` | Now — it is only partly stale | Factor VII **inverted**: the `AF_UNIX` deviation became REST conformance |
| `docs/MAINTAINER-GUIDE.md` | Per workflow, as each lands | Layout and cheat sheet are already current; the per-workflow sections are not |

## Owed: reinstate schema migrations before the first post-v1.0.0 schema change

**Status: deliberately removed. MUST return before any schema change that
follows the v1.0.0 release.** Tracked here rather than in a code comment alone
because this is a decision with an expiry date, and the thing that expires is
the reason it was safe.

**What was changed.** `JobStore` carries no migration path. `kSchemaVersion` is
1 and stays at 1; the schema is defined solely by `kSchemaSql`. A database whose
`user_version` does not match is **refused in either direction** with a message
telling the operator to delete the file. `kMigrateV1ToV2`, `kMigrateV2ToV3`, the
migration table and its loop, and `tests/fixtures/store-v1.db` were all deleted.

**Why it was safe.** Before v1.0.0 ships there are no databases in the field.
Every store is a developer or CI database and all of them are disposable, so a
schema change can recreate rather than migrate. Maintaining a migration chain
for databases that do not exist is cost without benefit — and it is cost with a
sharp edge: the migration dispatch was found applying exactly one step and then
stamping `user_version` with the target version, so the moment a second
migration existed a v1 store would have been migrated to v2, labelled v3, and
left silently missing a column. That defect could only exist because migrations
existed.

**What must happen, and when.** The moment v1.0.0 is released this stops being
true, because a released build creates databases somebody else owns. Before the
*first* schema change after that release:

1. Restore an ordered migration table and a loop that applies every step in
   turn — not a single step chosen by condition, which is what broke before.
2. Freeze a fixture database written by the released build, and test the full
   chain against it rather than only the most recent step.
3. Change the version-mismatch message: "delete the database" is correct advice
   only while the data is disposable, and becomes dangerous advice the moment
   it is not.

**The trap to avoid.** The refusal message and the missing migration path are
the same decision viewed from two sides. Restoring migrations without rewriting
that message leaves a build that can migrate but still tells operators to delete
their data.

## Owed: restore branch coverage reporting

**Status: temporarily disabled. Restore when the tree is stable — no later than
C9.** This is tracked here rather than left as a Makefile comment because a
measure taken "for now" and recorded nowhere is a measure that becomes
permanent.

**What was changed.** `make coverage` runs `gcov` without `-b`, so the reports
SonarCloud consumes carry line coverage only. Before this, the SonarCloud
Quality Gate on `main` failed `new_coverage` at 71.3% against a threshold of
80%, and every other condition passed.

**Why.** SonarCloud blends line and condition coverage into one figure, and
gcov's condition data for C++ counts every exception-unwind edge the compiler
emits. Measured across the tree: **1,296 lines to cover with 114 uncovered
(91.2%), against 2,273 conditions with 909 uncovered (60.0%)** — and of 685
never-taken branches sampled across three files, **502 (73%) sit on source
lines containing no conditional at all**: `std::ostringstream os;`,
`os << "store: " << what;`, `return fail(...)`. They are reachable only by
forcing an allocation failure.

The clearest case is `http_parser.cpp`, which has **100% line coverage** and
still reported 82.3%, because of 83 untaken branches of which 61 are on lines
with no branch in them. The gate was failing on an artifact rather than a gap.

**What was deliberately NOT done.** The branch data is still produced and still
inspected — `make coverage-branches` plus `scripts/branch-coverage-audit.py`
separate the roughly 200 genuinely untaken branches from the ~670 unreachable
ones. Dropping branch measurement entirely would have hidden real gaps, which
is the outcome to avoid. `store.cpp` alone carries 120 worth acting on.

**What has to be true to restore it.**

1. The ~200 genuine untaken branches are closed or individually justified —
   most need the fault injection `docs/TEST-STRATEGY.md` describes, since they
   are error paths in code that talks to SQLite and the filesystem.
2. A way to stop counting compiler-emitted edges. Options not yet evaluated:
   compiling the coverage tier with `-fno-exceptions` (the project throws
   nothing, but Catch2 requires exceptions, so the library and the test binary
   would need different flags), or a coverage tool that distinguishes the two —
   `llvm-cov` with a Clang coverage build is the obvious candidate and the
   toolchain already carries clang for fuzzing.
3. Only then re-enable `-b` and raise the gate, with the *measured* number
   rather than an assumed one.

Restoring this is a prerequisite for C9 claiming the tree is qualified: a
coverage figure that omits branch data is a weaker claim than one that includes
it, and the release should not make the weaker claim silently.

## Locked decisions ("do not drop")

These were settled during design and at project kickoff. Keep them
across all future work:

- **Dependency-free runtime.** Production code uses only the C++11 standard library,
  POSIX, and the vendored, hash-pinned dependencies in `cpp/VENDORED.md` (L1-SYS-009).
  This requirement previously meant "Python 3.10 standard library only" — the ID was
  reused, not reminted, when the implementation changed.
- **Conservative deletion.** A source file is deleted only after the destination is
  written, fsynced, published, and verified per the configured integrity policy
  (L1-SYS-003). A failure always *retains* the claimed source.
- **Hybrid naming.** Operator-facing name is generic (`file-mover`, `/etc/file-mover`);
  on-disk staging markers are SWIT-prefixed (`.swit-moving`, `.swit-partial-`) so
  in-flight artifacts are unmistakably ours on shared NFS.
- **~~Unix-socket control plane.~~ Superseded at v1.0.0 by REST** (ADR-0002). The
  `AF_UNIX` socket with length-prefixed JSON is gone. What survives the change and is
  still locked: **submission is idempotent by `request_id`.** What was *lost* and must be
  replaced deliberately: the socket gave filesystem-permission authentication for free,
  and a TCP listener does not — hence the authentication item below.
- **SQLite is the durable queue.** Authoritative job/file state lives in SQLite (WAL,
  `synchronous=FULL`); recovery decisions are made from observable filesystem state plus
  durable records, never from assumptions.
- **~~Poetry, root `src/` layout~~ — superseded at v1.0.0.** The build is GNU make
  (ADR-0005) over `cpp/`. The **full quality battery is locked and grew**: two compilers
  including the GCC 4.8.5 fidelity tier, ASan/UBSan/LSan, ThreadSanitizer, Valgrind,
  cppcheck, clang-tidy, vendored-file integrity, locale-free parser verification,
  coverage, coverage-guided fuzzing with committed corpora, CodeQL, SonarCloud, and
  trace-matrix `--check`.

## Milestones M1–M8 — the Python implementation (historical)

> **This section is history, not a plan.** M1–M8 describe the **Python** implementation
> delivered through v0.4.2, which shipped and is tagged. The forward plan is
> **C1–C9 above**. Nothing in this section is outstanding work.
>
> It is kept because the milestone shapes were sound and the C++ plan reuses several of
> them, and because "M6 transfer engine" appears in ADRs and commit messages that would
> otherwise dangle. Do not schedule against it.

**Status:** M1–M8 were delivered — the Python product was feature-complete for its first
release (systemd service, submit/claim, durable state, integrity, retry, crash recovery,
and the no-panic fuzz harness). Per-milestone detail lives in `CHANGELOG.md`.

### M1 — Foundation & Requirements Baseline ✅

Strip the inherited template scaffolding; establish the Poetry/`src` skeleton, the
reference configuration, and the CLI parser surface; author the L1/L2/L3 requirement
docs and the architecture/CLI/config/maintainer references; adapt CI and the
trace-matrix generator to Python-only. Ships declarative code (constants, exception
hierarchy, enums) and a runnable `file-mover --help`; no transfer behavior yet.

### M2 — Configuration Subsystem

`OptionSpec`-driven section schemas; `ConfigurationLoader` (parse → reject-unknown →
convert → validate ranges/cross-field) returning a frozen `ApplicationConfig`;
`ConfigurationValidationError` that collects all issues; `file-mover config validate`
and a partial `doctor`.
Requirements: L2-CFG-001..011, L2-ARC-001..006.

### M3 — Control Plane (first executable milestone)

Length-prefixed JSON protocol framing; `ControlSocketServer` + client + stale-socket
recovery; `CommandDispatcher` (static command→handler map); singleton process lock;
`health` command; `service run` skeleton (no transfers). **Done-when:** systemd starts
the service, the CLI reaches it over the socket, `health` succeeds, the service stops
cleanly, and a stale socket is recovered safely.
Requirements: L2-EVT-001..005, L3-EVT-001..005, L2-CTL-002, L2-CLI-005/006/010/011.

### M4 — Durable Job State

`SQLiteJobRepository` (schema, WAL/`synchronous=FULL`/`busy_timeout`, per-thread
connections, migrations); `JobRecord`/`FileRecord` dataclasses and the state-machine
transition map; `JobQueryService`; `status`, `list`, `stats`.
Requirements: L1-SYS-007, L2-RTY-003, L2-JOB-002.

### M5 — Submission & Claiming

`SourceValidator` (stability polling, symlink rejection, path policy, dev+inode
identity); `FileClaimManager` (same-device atomic rename into `.swit-moving/<job>/`);
`ManifestWriter` (atomic temp+replace); `JobSubmissionService`; idempotent `submit`.
Requirements: L1-SYS-004, L2-FS-001..005, L2-POSIX-001..006, L2-CLI-008/009,
L2-DST-005, L3-INT-003/004, L2-POSIX-008.

### M6 — Transfer Engine

`BufferedFileCopyEngine` (`.swit-partial-` temp write, bounded buffer, flush+`os.fsync`);
`IntegrityVerifier` (metadata / source-hash / source-and-destination-hash via `hashlib`,
`hmac.compare_digest`); `TransferCoordinator` + bounded worker pool; atomic publish +
directory fsync; source cleanup; `ErrorClassifier` + durable classified retry with
backoff.
Requirements: L1-SYS-001/003/006, L2-DPR-001..007, L2-COPY-001..010,
L2-POSIX-007..012, L2-DST-001..004, L2-DEL-001..004, L2-RTY-001..006,
L3-INT-001..007, L2-DPR-004/005, L3-CPP-053.

### M7 — Recovery & Service Integration

`RecoveryManager` (reconcile DB vs filesystem across all non-terminal states); the full
`BackgroundMoverService` main loop (transfer scheduler + control server + signal-driven
graceful shutdown); retry that survives restart.
Requirements: L1-SYS-005, L2-CLN-001..005, L2-RTY-004, L2-COPY-010.

### M8 — Packaging & Qualification

Production systemd unit (`Type=simple`) + `mover` service account + deployment guide;
fault-injection tests at every destructive boundary; NFS-qualification checklist; a
Python no-panic/fuzz harness (revives the `fuzz` CI workflow); complete trace-matrix
coverage.
Requirements: L1-SYS-002, L2-STO-001..005, plus test-completeness across all categories.

## Deferred (post-1.0, explicitly out of the first release)

- S3 / object-storage adapter — a separate optional package (`file-mover-s3`); the core
  stays dependency-free (L2-STO-003/005).
- `json-lines` streaming output and an offline `database inspect` command.
- Multi-host active/active movers.
- Network / remote API — a networked control surface beyond the local `AF_UNIX` socket
  (e.g. submitting and monitoring jobs across hosts).
- Web dashboard — a browser UI for job status and operational visibility.
- Metrics server — an exported metrics endpoint (e.g. Prometheus-style) for throughput,
  queue depth, and retry counters.
- Advanced scheduling and transfer prioritization — job priorities and scheduling policy
  beyond the current single-active-job, FIFO model.
- Per-job submission policy overrides — optional `submit` flags (`--integrity-mode`,
  `--hash-algorithm`, `--stability-check`/`--stability-polls`/`--stability-poll-interval`)
  that tune policy for a single job, each **constrained by system policy** so a submitter can
  never weaken a required setting (e.g. cannot disable hashing when the service mandates it).
  The resolved values are stored in the job record so recovery reuses them.
- Persisted per-phase job timings — record `perf_counter` durations for submission, source
  hashing, copy, verification, and recovery on each completed job and surface them via
  `status`/`stats`, giving operators visibility into where time goes on a ~100 GB transfer.
- File-size submission policies — optional `[validation]`/`[stability]` limits that reject a
  job **before claiming** when a file is empty (`allow_empty_files = false`) or exceeds a
  per-file / per-job size ceiling (`maximum_file_size_bytes`, `maximum_job_size_bytes`,
  `0` = no limit). Guards against a failed recorder (zero-byte file) or an over-size set.
- Regex / filename-filter submission — optional `filename_filter_regex` for directory
  submissions: compiled and validated at startup, anchored against relative paths, recorded
  in the job, and applied **before** claiming. Deferred in the original design (an explicit
  file list or job-specific directory is the safer primary path); add only if orchestration
  needs it.
- Durable job event / audit log — persist every job/file state transition as a typed event
  to a durable events table (and expose a human-readable per-job timeline), giving operators
  an auditable history beyond the current job/file state snapshot. The first design
  downgraded this to "optional observers, never authoritative" (the jobs/files tables are the
  source of truth), so it remains an unbuilt enhancement.
- Proactive free-space margin pre-flight check — before starting a transfer, verify the
  destination filesystem has at least the job's total size plus a configurable margin
  (`statvfs`), and reject or hold the job otherwise, instead of only handling `ENOSPC`
  reactively (source retained) after copying part of a ~100 GB set. Proposed in the
  original design (`minimum_free_space_margin_bytes`) but not built.
- `version` existing-destination collision policy — a third `ExistingDestinationPolicy`
  alongside `fail` and `verify-and-reuse`: on a *differing* destination collision, publish
  the new recording under a versioned name (keeping the existing file) instead of routing
  the job to `MANUAL_INTERVENTION`. Considered in the original design but not built.
  (`overwrite` remains deliberately excluded — recorded simulation data must never be
  silently replaced.)
- Streaming hash-while-copy integrity mode — hash the source **during** the copy loop
  instead of in a separate pre-copy read, so a ~100 GB dataset is read once, not twice
  (roughly halving source I/O for `source-hash` / `source-and-destination-hash` jobs). It
  was deferred in the first design because it cannot persist the *completed* source hash
  before the transfer begins; under `source-and-destination-hash` that is moot since the
  destination is re-hashed and compared regardless. Would add a fourth `[integrity] mode`
  value alongside the current `metadata` / `source-hash` / `source-and-destination-hash`.
- Manifest per-file hashes for standalone downstream verification — record each file's
  source (and destination) hash in the JSON manifest, not only in the SQLite `FileRecord`,
  so a downstream consumer can verify a published recording without the mover's database.
  Requires rewriting the manifest after the `HASHING_SOURCE` step (the manifest is written
  at submission, before the hashes exist). Job `created_at` and integrity policy already
  live in both the record and the manifest (L2-JOB-007); this extends that parity to hashes.
- Filesystem spool-queue control transport — an alternative to the `AF_UNIX` control
  socket in which `submit` writes a JSON job manifest into a spool directory
  (`queue/` → `processing/` → `completed/` / `failed/`) that the service polls, instead of a
  socket request/response. It was weighed during design as the simpler first-version option
  and deferred in favour of the socket (faster acknowledgement, clearer request/response).
  Its future value is **portability**: it needs no `AF_UNIX`, so it is the most likely path
  to **Windows support** (where `doctor` currently reports `ENVIRONMENT_UNSUPPORTED`). Would
  reuse the existing SQLite durable state and JSON manifests unchanged.
- **Logging enhancements (post-12-factor-logging):**
  - **systemd journal priority prefixes** — emit the sd-daemon `<N>` level prefix on the
    service's stdout stream so journald records the correct priority per record.
  - **JSON log-format mode** (`[logging] format = text | json`) — one JSON object per line,
    leveraging the structured `extra={job_id, file_id}` fields, for log shippers.

## Known gaps (decision needed)

> **Read this section as of v0.4.0.** It describes the traceability position of the
> Python implementation, whose tests left this branch with it. The C++ position is
> different and much earlier — see the scope-adjusted figure in `docs/TRACE-MATRIX.md`.

A **traceability audit** (v0.4.0) reconciled the trace matrix with the code: every
implemented requirement then carried a `@pytest.mark.requirement` test marker (or a
declared Inspection method), so a `Draft` status in the matrix meant *genuinely unbuilt*,
not merely untested. The claim/filesystem and transfer/deletion data-safety requirements
(`L2-FS-*`, `L2-POSIX-*`, `L2-CLN-001/005`, `L2-COPY-*`, `L2-DST-*`, `L2-DEL-*`) are now
tested. The requirements still `Draft` are unimplemented features specified during design —
each needs an **implement-or-withdraw** decision:

- **Claim-directory cleanup — `L2-CLN-003` / `L2-CLN-004`.** There is no staging-directory
  cleanup step: after a job's claimed sources are deleted, the emptied `.swit-moving/<job>/`
  directory is left in place, and unexpected leftover files are neither surfaced nor routed
  to manual intervention. Implement a deepest-first cleanup that removes the emptied claim
  directory and routes a non-empty one (unexpected files) to `MANUAL_INTERVENTION`, or
  withdraw the requirements.
- **Manual retry — `L2-RTY-006`.** The `retry` CLI subcommand exists in the parser but has
  **no server-side handler** (registered control commands are health/status/list/stats/
  submit/throttle/pause/resume/cancel), so sending `retry` returns `UNKNOWN_COMMAND`. Wire a
  `retry` handler that transitions an eligible retained job back to `QUEUED`, or withdraw it.
- **Event publisher — `L2-EVT-001..005` / `L3-EVT-001..005`.** The in-memory observer /
  event-publisher (snapshot subscribers before dispatch, don't hold the lock during
  callbacks, isolate subscriber failures, reject duplicate registration, unsubscribe reports
  removal) has no implementation and no tests. Its observational-not-transactional *principle*
  is already honoured by the coordinator (it updates SQLite directly); decide whether to build
  the publisher (together with the durable event/audit log above) or withdraw the requirements.

The storage-capability abstraction (`TransferSource`/`TransferDestination` Protocols behind
`L2-STO-001/003`) is likewise unbuilt — the workflow uses POSIX directly — but is tracked as
part of the deferred **S3 adapter** rather than a standalone gap.

## Delivered post-1.0

- **Dynamic bandwidth limiting** (v0.2.0) — a userspace token-bucket throughput ceiling
  (`[transfer] max_bytes_per_second`), adjustable live with `file-mover throttle`
  (L2-BWL-001..004). See `docs/ARCHITECTURE.md` § *Bandwidth limiting*.
- **Job lifecycle control** (v0.3.0) — `cancel` / `pause` / `resume` commands with
  cooperative cancellation of in-flight copies; cancel always retains the source
  (L2-LIF-001..005). See `docs/ARCHITECTURE.md` § *Lifecycle control*.
- **Partial-file byte-offset resume** (v0.3.0) — resume an interrupted copy from its
  fsynced partial (`[transfer] resume_partial_files`) instead of restarting from zero,
  with a hash-verified restart fallback (L2-RSM-001..003). See
  `docs/ARCHITECTURE.md` § *Partial-file resume*.

---

# v1.0.0 — C++ / REST implementation

Tracked on the current milestone branch off `main` — see *Merge cadence* below.
**The forward plan is C1–C9 at the top of this file**;
this section records what is already delivered and the architecture it sits on. The
M1–M8 list above belongs to the Python implementation. The inherited external design
used its own M1–M12 numbering, deliberately not carried into this repository.

## Delivered — the C0 foundation

| Component | Requirements | Notes |
|---|---|---|
| Core job state machine | `L3-CPP-001..015`, `L3-CPP-041` | Pure logic, clock-free, exhaustive transition table |
| Strict JSON parser | `L3-CPP-016..024` | Project-owned (ADR-0006), fuzzed, hostile-input tested, 99% line coverage |
| REST API codec | `L3-CPP-025..032` | Strict-reject; parser confined behind it |
| Configuration loader | `L3-CPP-033..040` | Strict schema, all-errors reporting, `[storage]` section |
| Rename template engine | `L3-CPP-042..045` | Pure, clock-free; validates its own result against `.`, `..`, `/`, NUL |
| HTTP request-head parser | `L3-CPP-046..052` | Hand-rolled (ADR-0012), fuzzed, locale-free, **100%** line coverage |
| CI pipeline | — | Fifteen gates, toolchains pinned by explicit version |

Every one of these is pure or near-pure logic. That is not an accident of ordering — it
is why they could be finished to this standard before any of them could move a byte. C1
onward is where the project acquires state, threads, and a filesystem, and the cost per
requirement rises accordingly.

## Security and file-management architecture

`docs/CYBERSECURITY.md` is the reference. It states a threat model in which
endpoint security, MAC, audit agents, and other NFS clients all touch the same
filesystem, and two assumptions are rejected: that a check stays true, and that
privileged interference is impossible.

**Two scoping constraints for v1.0.0**, taken to remove attack surface:

* **Same filesystem only** (`L1-SEC-007`) — no staging directory, no recursive
  copy, no bottom-up fsync ordering. Every move is one atomic operation.
* **Files only** (`L1-SEC-007`) — no recursive walk, and it avoids depending on
  an atomic no-clobber directory move, which **does not exist over NFS**
  (`linkat` does not work on directories and NFS has no `RENAME_NOREPLACE`).

### Outstanding work, in dependency order

| # | Item | Requirements | Blocked on |
|---|---|---|---|
| 1 | **SQLite durable store** — phase model `intent → committed → source-deleted → complete`, source identity at intent | ADR-0010, `L1-SEC-003`, `L2-JOB-001..012` | Vendor the amalgamation |
| 2 | **fd-relative filesystem layer** — `openat`/`renameat2`/`fstatat`/`unlinkat`, identity re-verification after open | `L2-SEC-001..004` | 1 |
| 3 | **`renameat2` capability detection** + `linkat`/`unlinkat` fallback as a primary tested path | `L2-SEC-007`, `L2-NFS-001..003` | 2 |
| 4 | **Preconditions and path validation** — trusted UID, sticky-bit check, canonicalization | `L2-SEC-005`, `L2-SEC-006` | 2 |
| 5 | **Rename operation** on the fd-relative layer, consuming the delivered template engine | `L1-SYS-013`, `L2-REN-001..003` | 2, 3 |
| 6 | **External-interference tolerance** — per-syscall timeouts, forward progress, failed-external state | `L1-SEC-004`, `L2-SEC-009..011`, `L2-NFS-004..005` | 1, 2 |
| 7 | **Transfer strategies** — local rename, `fork`/`execvp` exec strategy; two-hop delivery | `L1-SYS-015`, `L2-XFR-001..004`, `L2-NFS-007` | 5 |
| 8 | **Worker pool and REST server** | `L2-MGR-001..003`, `L2-CTL-001..016` | 1, 7 |
| 9 | **Crash and fault injection suite** | `L1-SEC-002` | 1–8 |
| 10 | **MAC policy + enforcing-mode CI** — SELinux module (RHEL), AppArmor profile (SLES) | `L1-SEC-005`, `L2-SEC-013` | 8 |
| 11 | **Hardened systemd unit** | `L2-SEC-014` | 8 |
| 12 | **ePO exclusion documentation + startup coverage check** | `L2-SEC-016` | 8 |
| 13 | **NFS qualification on a real export** | `L2-NFS-006`, `L2-NFS-008` | 8 |

### Testing obligations that cannot be deferred

The guarantees live in crash-window behavior, which ordinary tests never
reach. Recovery logic that only runs during disasters is the worst possible
place for untested code.

- [ ] `SIGKILL` between each phase transition, verifying recovery on restart
- [ ] Entry swapped mid-operation (identity mismatch)
- [ ] File removed mid-operation (quarantine simulation)
- [ ] `EEXIST` at commit
- [ ] Both paths missing at recovery → failed-external, no retry
- [ ] Injected `open()` latency → timeout, sibling moves unaffected
- [ ] Full suite under SELinux enforcing / AppArmor enforcing, zero denials
- [ ] `linkat`/`unlinkat` fallback exercised as the primary path, not an edge case

## M7 disposition (transfer adapters)

The inherited M7 delivered three transfer strategies. One is deferred, one is
removed, and the third is superseded by work already scheduled.

| Delivered | Outcome |
|---|---|
| `LocalRenameTransfer` | **Superseded** by roadmap items 2–3. Path-based `link`/`unlink`/`lstat` is the check-then-act pattern `L2-SEC-001` prohibits, and `link`+`unlink` is the NFS *fallback* rather than the primary (`L2-SEC-007`). Same finding as M6's rename operation, same cause. |
| `CopyFsyncRenameTransfer` | **Deferred → v1.1** with cross-filesystem support (`L1-SEC-007`). Its `.part` → `fsync` → atomic-placement pattern independently confirms the two-hop reasoning in `L2-NFS-007`. |
| `ExecTransfer` | **Removed** — ADR-0011. |
| `[transfer]` config growth | **Deferred** with the strategies it configures. |
| Progress callback, validating factory | Retained as interface concepts for the rewrite. |

Nothing from M7 was adopted as code. The subprocess discipline it demonstrated
is retained as `L2-SEC-008`, and its temp-file placement pattern informs
`L2-NFS-007`; both were already specified before the drop arrived.

### On external commands, should the question return

ADR-0011 removes the strategy, not the topic. A genuine future need for a
destination the daemon cannot reach as a filesystem path — another host over
SSH, an object store — is a design conversation with its own threat analysis,
not a configuration key. Two constraints any such design has to satisfy:

* Configuration must remain data. Whatever expresses "send it there" cannot be
  a free-text command, or whoever writes the config gets code execution as the
  service account.
* The commit point must stay ours, or the guarantee has to be explicitly and
  visibly weaker for that destination — not silently weaker for everyone.

## M8 disposition (job manager)

The inherited M8 delivered a threaded JobManager. Its code depends on
`journal.hpp`, `rename.hpp`, and `transfer.hpp` -- all superseded or rejected --
so none of it ports. Its *disciplines* are the most valuable thing any drop has
produced.

| Delivered | Outcome |
|---|---|
| Write-ahead ordering -- intent durable **before** the job exists | **Adopted as `L2-JOB-013`.** Exactly the commit-point ordering whose absence in M6 meant a crash between rename and record loses the file. |
| Phase-blind non-fatal write failures (`L3-CPP-075`) | **Rejected**, replaced by `L2-JOB-014`. A write failure is two conditions wanting opposite handling; treating both as a counter lets the durable record drift from the filesystem. |
| Job sequence feeding `{seq}` | **Adopted as `L2-JOB-015`**, with the gap closed: the sequence must be durable and monotonic across restarts, which the inherited design left unspecified. |
| ThreadSanitizer gate | **Adopted as `L2-ARC-008`**, wired into CI and `make check-ci` before the first thread exists. |
| Latch-based deterministic concurrency tests | **Adopted as practice** -- see CONTRIBUTING. Proving all N workers are simultaneously inside the call beats sleeping and hoping. |
| Injected clock (`std::function<int64_t()>`) | **Adopted as practice.** Consistent with the clock-free core, and it makes ordering exactly checkable rather than probabilistically. |
| Queue / worker / drain semantics | Already specified as `L2-MGR-001..003`; the implementation confirms the shape. |
| `JobManager` code, journal wiring, pipeline | **Not ported.** |

## M11/M12 disposition (dashboard and daemon entry point) — CLOSED

The final drop, and the end of the inherited design series. No code adopted;
four requirements and one compliance fix. Full triage in
`docs/MIGRATION-PROVENANCE.md`.

| Delivered | Outcome |
|---|---|
| `LICENSES/` for vendored dependencies | **Adopted** — and it found a real gap. `catch.hpp` references an "accompanying file `LICENSE_1_0.txt`" that did not exist here. Now vendored, hash-pinned, gated by `make verify-vendored`. |
| `textContent`-only DOM insertion | **Adopted** as `L2-DASH-003`. |
| Signal handler sets only `volatile sig_atomic_t`; `SIGPIPE` ignored | **Adopted** as `L2-CTL-017`, `L2-CTL-018`. |
| `--check` config validation, run as systemd `ExecStartPre` | **Adopted** as `L2-CTL-019`. |
| Ordered startup, reverse-order teardown | **Adopted** as `L2-CTL-020`. |
| `src/main.cpp` | **Not ported** — composes the journal (rejected, ADR-0010), the manager and HTTP server (deferred), and a transfer strategy (`ExecTransfer` removed, ADR-0011). Its 200 ms `nanosleep` wait loop is explicitly **not** the pattern to copy; block on `sigsuspend` or a self-pipe. |
| `deploy/filemover.service` | **Superseded** by `L2-SEC-014`, which is stronger (`ProtectSystem=strict`, `ReadWritePaths=`, `CapabilityBoundingSet=`, `UMask=0077`). |
| `dashboard.cpp` | **Deferred** with the dashboard; `L2-DASH-001..003` hold the obligations. |

**The inherited-design series is now closed.** `transcripts/` is deleted. Eight
snapshots produced one adopted component, two adopted helpers, and ~20
requirements; everything else was superseded, deferred, or rejected. If another
design conversation arrives, recreate `transcripts/` as scratch and follow the
same rubric.

## M9/M10 disposition (HTTP layer and recovery) — CLOSED

The first drop containing code worth adopting beyond a pure helper. ADR-0012
committed the project to a hand-rolled HTTP/1.1 subset, so unlike the previous
four milestones this one builds something we actually need.

**Status: the parser is landed.** `cpp/src/http_parser.cpp`, `L3-CPP-046..052`,
with the three fixes below applied, a second libFuzzer target
(`cpp/fuzz/fuzz_http.cpp`, 37 seeds), and the first component built to
`docs/HAND-ROLLED-COMPONENTS.md`. The routes and server remain deferred with
the job manager; the recovery design remains rejected. What stays open from
this milestone is tracked in **M7** below, not here.

| Delivered | Outcome |
|---|---|
| `parse_request_head`, `content_length_for`, `serialize_response` | **Adopted** — `L3-CPP-046..052`, with the fixes below. Pure functions, strict posture, and the untrusted-input surface ADR-0008 requires fuzzing. |
| `http_routes.cpp` | **Defer.** Depends on the job manager, which does not exist. |
| `http_server.cpp` | **Defer.** Socket loop needs config and manager; also needs review against `L2-SEC-009` (per-syscall timeouts) and `L2-SEC-010` (one stalled connection must not block others — the server is serial-accept). |
| `manager.cpp` recovery | **Reject as written.** Journal-based (ADR-0010 chose SQLite), and its non-fatal write-failure handling contradicts `L2-JOB-014`. |
| Test suite (493 lines) | **Adapted** — the parser's share landed as `cpp/tests/test_http_parser.cpp`, keeping the prefix sweep. The hostile battery is an integration test against a socket, so it is deferred with the server. |

### Fixes applied before adopting the parser

1. **Split the header.** `http.hpp` is monolithic: the pure parser, the route
   handlers, and the socket server share one header that includes
   `config.hpp` and `manager.hpp`. The parser needs neither. Split into
   `http_parser.hpp` (pure, std-only), with routes and server following when
   the manager exists. Same layering fault as M7 putting the journal codec in
   `api_codec.hpp`.

2. **Remove locale dependence.** `valid_header_name` uses `std::isalnum` and
   `lower()` uses `std::tolower`, both **locale-sensitive**. A parser on
   untrusted input must not change behavior because something in the process
   called `setlocale`. Replace with explicit range checks — the same reasoning
   that made the JSON parser use explicit tables.

3. **Renumber** `L3-CPP-079..092` into this repository's sequence — landed as
   `L3-CPP-046..052`.

A fourth change was made that the review had not anticipated: `content_length_for`
used `strtoull`, which accepts leading whitespace and a `+`/`-` sign and reports
overflow through `errno`. Replaced with explicit digit accumulation and an
overflow guard, so the strict-digit rule is enforced by the code rather than by
checking the string first and trusting the conversion afterwards.

### What the parser gets right, and is worth preserving

* **Duplicate headers rejected outright** — added mid-build after noticing a
  map's last-wins overwrite is a request-smuggling vector. Correct, and the
  same class of reasoning that made duplicate JSON keys an error (ADR-0009).
* **Any `Transfer-Encoding` is a 400.** No chunked parsing exists to desync.
* **Bytes beyond the declared `Content-Length` are a 400** — no pipelining, no
  smuggled second request.
* **`NeedMore` for every proper prefix of a valid head**, swept exhaustively in
  the tests. This is the property that makes a streaming parser safe.
* `out` is left unmodified except on success, matching the codec contract.

## Open questions (decision needed)

| Item | Question | Raised |
|---|---|---|
| **`{seq}` template field** | **Answered.** The sequence is the job sequence, and `L2-JOB-015` now requires it be durable and monotonic across restarts -- the inherited design left durability unspecified, which would have made identifiers repeat after every restart. | M6 review, closed M8 |
| **Collision suffix walk** | The inherited design walks `.1`–`.1000`, each probe a `link()` attempt. On NFS that is up to 1000 round-trips per collision, and with a `{name}`-only template collision is the normal case rather than the exception. The cap is also arbitrary. Re-evaluate once the fd-relative layer exists — it may be better addressed by making collisions rare by construction than by walking. | M6 review |
| **cpp-httplib on GCC 4.8.5** | **Answered — rejected.** No tag is viable: it routes with `std::regex`, unimplemented in libstdc++ before GCC 4.9. Measured in the container — a literal route registers, a parameterised one throws `regex_error`, and the latest tag will not compile at all. HTTP is hand-rolled (ADR-0012), which also closes the last TBD in ADR-0004. | ADR-0004, closed M9/M10 |
| **Authentication** | v1.0.0 ships none; the bind address is the only access control (`L1-API-006`). Needs a decision before any non-loopback deployment. | L1 merge |
| **Trace matrix and Catch2** | **Answered — implemented.** The generator now reads requirement ids out of Catch2 `TEST_CASE` tag strings as well as pytest markers, so a tag is the whole tracing mechanism. This had to land *before* the Python removal: without it, deleting `tests/` would have taken the matrix to zero tested. | Requirements merge, closed at the Python removal |
| **Stale locked decisions** | **Answered — done.** The locked-decisions section above now marks the Unix-socket control plane and the Poetry/`src` layout as superseded at v1.0.0, and records what the socket's removal *cost* rather than only that it changed. | L1 merge, closed at the Python removal |
| **Deferred-family verification** | The 69 L2/L3 requirements under the five Deferred L1s are excluded from the scope-adjusted coverage figure, which is right for release reporting — but it means nothing gates them, and their Python tests are gone. Before v1.1 begins, decide whether they are re-verified against the C++ or re-derived from scratch. | Python removal |

## Deferred to v1.1

Retained verbatim in the requirements, marked Deferred, never weakened.

| Capability | Requirements |
|---|---|
| Claiming — relocate source so the next run cannot overwrite | `L1-SYS-004`, and `L1-SYS-002` which depends on it |
| Conservative deletion — no delete until published and verified | `L1-SYS-003` |
| Configurable integrity verification | `L1-SYS-006` |
| Recovery by resumption rather than marking failed | `L1-SYS-005` |
| Cross-filesystem moves — staging, recursive fd-relative copy, commit rename | `L1-SEC-007` constrains v1.0.0; the design is retained in `docs/CYBERSECURITY.md` marked **[v1.1]** |
| Directory moves | As above; needs an answer for NFS, which has no atomic no-clobber directory move |
| Bandwidth limiting, partial-file resume, pause/cancel | Python-implementation features not yet ported |
