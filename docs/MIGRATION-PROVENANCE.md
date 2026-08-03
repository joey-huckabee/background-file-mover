# Migration provenance — what the inherited C++ design contributed, and what it did not

**Status: closed.** Eight milestone snapshots were delivered from an outside
design conversation and staged in a `transcripts/` directory, integrated one
drop at a time. All eight are triaged and retired; the directory and the
snapshots are deleted. This document is what remains of them — the record
rather than the scaffolding.

## Why this is kept

Most of the inherited material was **not** adopted, and the reasons are the
valuable part. Without them the same code arrives again — in a later proposal,
or through a maintainer's entirely reasonable instinct that a rename engine
ought to just call `rename()` — and gets adopted on its second pass because
nobody remembers it was already examined and refused. A rejection with a
written reason is a durable decision; a rejection with no record is a decision
that expires.

So: read this before re-introducing anything listed below, and before
concluding that a gap in the C++ tree is an oversight. Several of them are
deliberate.

**Standing caveat.** The originating conversation designed a standalone project
from scratch, without knowledge of this repository's requirements, locked
decisions, or constraints. It was found to contain at least one fabricated
premise — its ADR-0001 cited a non-existent prior C++ implementation of this
project, corrected in place. Verify factual claims from this material before
promoting them into a spec.

| Bucket | Action taken |
|---|---|
| ADOPT | New capability with no equivalent here |
| REDUNDANT | Re-derives an existing requirement — dropped, mapped to the existing ID |
| CONFLICT | Contradicts an existing requirement — **repo wins by default** |
| SUPERSEDE | Genuinely better, with a written reason |
| DEFER | Good, but not v1.0.0 — moved to `docs/ROADMAP.md` |

## Where each drop ended up

**Eighth and final drop (`rest-file-mover-complete`, M11 dashboard + M12 daemon
entry point) — no code adopted; four requirements and one compliance fix:**

The complete twelve-milestone tree. Diffing every re-shipped file against ours
found **no upstream changes** — the only deltas were our own comments and
renumbering — so the genuinely new material was M11, M12, `deploy/`, and
`LICENSES/`.

| Inherited material | Outcome |
|---|---|
| **Vendored license texts (`LICENSES/`)** | **Adopted, and it caught a real gap.** `catch.hpp` says "See accompanying file `LICENSE_1_0.txt`" and no such file existed here. `VENDORED.md` recorded the license *name*, which is inventory, not compliance — BSL-1.0 requires the text travel with the source. Now vendored at `third_party/catch2/LICENSE_1_0.txt`, hash-pinned, and gated by `make verify-vendored`. |
| **`textContent`-only DOM insertion** | **Adopted as `L2-DASH-003`.** The best idea in the drop. Paths are attacker-influenced by definition — whoever can create a file chooses its name — and the operator's browser is the one session with authority over the service. Text-node insertion removes the injection path instead of escaping it. |
| **Signal handler sets only a `volatile sig_atomic_t`** | **Adopted as `L2-CTL-017`.** Async-signal-safety, with a concrete failure mode: a SIGTERM landing while a thread holds the allocator or the store lock deadlocks shutdown, systemd `SIGKILL`s on `TimeoutStopSec`, and a clean stop becomes the abrupt termination the commit-point invariants must survive. |
| **`SIGPIPE` ignored process-wide** | **Adopted as `L2-CTL-018`.** The default disposition turns a client disconnecting mid-response into a killed daemon — remotely, unauthenticated. |
| **`--check` config validation as `ExecStartPre`** | **Adopted as `L2-CTL-019`.** A bad config fails the unit instead of half-starting a daemon. Parented to `L1-SYS-008` to match the Python `doctor` gate (`L2-ENV-001..003`), which is the same idea. |
| Ordered startup / reverse-order teardown | **Adopted as `L2-CTL-020`.** |
| `src/main.cpp` | **Not ported.** It wires journal → replay → recover → manager → transfer strategy → HTTP server; the journal is rejected (ADR-0010), the manager and server are deferred, and `ExecTransfer` was removed (ADR-0011). Nothing it composes exists here yet. |
| Its 200 ms `nanosleep` wait loop | **Rejected as a pattern.** A daemon that wakes five times a second forever to check a flag should block instead — `sigsuspend` or a self-pipe. Noted so it is not copied in when `main.cpp` is eventually written. |
| `deploy/filemover.service` | **Superseded by our own `L2-SEC-014`**, which is strictly stronger: `ProtectSystem=strict` rather than `full`, plus `ReadWritePaths=`, a trimmed `CapabilityBoundingSet=`, and `UMask=0077`. |
| `dashboard.cpp` (embedded HTML/CSS/JS) | **Deferred** with the dashboard. Cleanly built and genuinely self-contained, but it binds to an API shape we have not built. `L2-DASH-001..003` hold the obligations. |
| `LICENSES/BSD-2-Clause-picojson.txt` | **Not applicable** — picojson is excluded by ADR-0007 and was removed. |
| Everything else | Re-shipped snapshot, already triaged in earlier drops. |

**One claim in the closing narrative is now false, in our favor.** It states
that "the one thing this environment couldn't verify is the true GCC 4.8.5
build." We verify it on every run: `make check-ci`'s fidelity tier plus a
`gcc:4.8` container job in `cpp-ci.yml`, running the full suite rather than a
compile. Their open risk is closed here.

**Its final ledger does not describe this repository** — "25 L1s, ~30 L2s, 100
L3-CPPs, seven ADRs" counts the inherited tree, not ours (twelve ADRs, a
narrower v1.0.0, `L1-SYS-002/003/004/005/006` deferred to v1.1). Do not quote
those figures upward; use `docs/TRACE-MATRIX.md`, which is generated.

**Seventh drop (`rest-file-mover-m10`, HTTP server + startup recovery) — one
component adopted, the rest deferred or rejected:**

This drop opened with a compatibility verdict we had reached independently:
cpp-httplib routes through `std::regex`, and libstdc++ had no working `<regex>`
before GCC 4.9. We had already measured it across every tag from v0.5.12 to
0.51.0 and recorded the result in ADR-0012, so the drop confirmed the decision
rather than making it.

| Inherited material | Outcome |
|---|---|
| **HTTP request-head parser** | **Adopted** as `cpp/src/http_parser.cpp`, `L3-CPP-046..052` — the first component built under `docs/HAND-ROLLED-COMPONENTS.md`. Three changes were required before it could land; see below. |
| Duplicate-header rejection | **Adopted.** The inherited map was last-wins, which is a request-smuggling vector; the drop's own author caught it mid-build. Duplicate `Content-Length` and duplicate names generally are now rejected outright. |
| `Transfer-Encoding` → 400, over-cap → 413, strict-digit `Content-Length` | **Adopted** as the `content_length_for` policy. |
| Routes (`http_routes.cpp`) | **Deferred.** Pure and well-shaped, but they bind to `JobManager`, which does not exist here yet. The status/response *shapes* are recorded; the code lands with the manager. |
| Server (`http_server.cpp`) | **Deferred** with the routes. Two rules from it are worth keeping and are captured in the roadmap: bytes beyond the declared `Content-Length` are a 400 (no pipelining, no smuggled second request), and the hostile-battery-then-still-works integration test. |
| Startup recovery (`recovery`) | **Rejected** — journal-backed, superseded by ADR-0010. Two *concepts* survive: replay must go through `Job::transition` so an illegal transition fails recovery loudly, and recovered in-flight jobs are **not** auto-requeued (a half-moved file is an operator decision). |
| `picojson`, `journal.*`, `rename.cpp`, `transfer.cpp` | **Not ported** — rejected in earlier drops, re-shipped by the snapshot. |

Three changes were needed before the parser could be adopted, and they are the
reason `docs/HAND-ROLLED-COMPONENTS.md` exists:

1. **Header split.** The inherited `http.hpp` pulled in `config.hpp` and
   `manager.hpp`, so the parser could not be tested — or fuzzed — without
   constructing a service. It is now `http_parser.hpp`: standard library only,
   no project dependencies.
2. **Locale-free classification.** The original used `std::isalnum` and
   `std::tolower`, both locale-sensitive. A parser on untrusted network input
   must not change what it accepts because something else in the process called
   `setlocale`. Replaced with explicit ASCII range checks. Likewise `strtoull`
   for `Content-Length`, replaced with digit accumulation and an overflow guard.
3. **Renumbering** from the inherited `L3-CPP-079..092` to `L3-CPP-046..052`.

**A second inherited-test reproduction.** The drop's own log recorded fixing one
wrong expectation — that bare-LF framing is `Bad`. It is `NeedMore`; the size
cap and read timeout handle it. I wrote the assertion the wrong way round
anyway and the test caught it. That is now twice in three drops that reading
the honesty log did not prevent repeating what the log described. It is a
record of hazards, not an inoculation — same conclusion as the `{ext}` case
below, now with enough repetitions to call it a pattern.

**Sixth drop (`rest-file-mover-m8`, job manager) — no code, but the best ideas
so far:**

`manager.hpp` depends on `journal.hpp`, `rename.hpp`, and `transfer.hpp`, all
superseded or rejected, so none of it ports. What it contained instead was
discipline, and one of those closed a gap flagged two drops earlier.

| Inherited material | Outcome |
|---|---|
| **Write-ahead ordering** — intent durable *before* the job exists | **Adopted as `L2-JOB-013`.** This is exactly the commit-point ordering whose absence in M6 meant a crash between rename and record loses the file. The mechanism was a journal; the discipline is mechanism-neutral. |
| Phase-blind non-fatal write failures (`L3-CPP-075`) | **Rejected**, replaced by `L2-JOB-014`. A durable-write failure is two conditions wanting opposite handling — abort before the commit point, halt after — and treating both as a counter lets the record drift from the filesystem. |
| Job sequence feeding `{seq}` | **Adopted as `L2-JOB-015`**, gap closed: durable and monotonic across restarts, which the inherited design left unspecified. Closes the `{seq}` roadmap question. |
| ThreadSanitizer gate | **Adopted as `L2-ARC-008`**, wired into CI and `make check-ci` before the first thread exists. |
| Latch-based concurrency tests, injected clock | **Adopted as practice** — documented in CONTRIBUTING. |
| `JobManager` code, journal wiring, pipeline | **Not ported.** |

Worth noting what changed about *how* these drops read. The early ones were
mined for code; the recent ones are mined for **reasoning**. M8 produced no
lines that survive, and still contributed the single most valuable idea in the
series — write-ahead ordering — plus a correction to its own handling of write
failures that only became visible when checked against invariants written two
drops later.

**Fifth drop (`rest-file-mover-m7`, transfer adapters) — nothing adopted as code:**

| Inherited material | Outcome |
|---|---|
| `LocalRenameTransfer` | **Superseded** by the fd-relative layer already on the roadmap. Path-based `link`/`unlink`/`lstat` is the check-then-act pattern `L2-SEC-001` prohibits; `link`+`unlink` is the NFS fallback, not the primary. Identical finding to M6's rename operation. |
| `CopyFsyncRenameTransfer` | **Deferred → v1.1** — this is the cross-filesystem path, excluded by `L1-SEC-007`. Its `.part` → `fsync` → atomic-placement pattern independently confirms `L2-NFS-007`. |
| `ExecTransfer` | **Removed** — ADR-0011. A free-text command in configuration makes the config file executable, and delegating the move voids the commit-point guarantees. Its *subprocess discipline* was correct and is retained as `L2-SEC-008`. |
| `[transfer]` config growth | **Deferred** with the strategies. |

This drop prompted removing a requirement rather than adding one. `L1-SYS-015`
had required all three strategies — but only because it was derived from the
inherited `L1-023`. Nothing in the actual problem asked for an external
command. A requirement that exists only because an upstream design had it is
not a requirement; it is an inheritance.

It also exposed a contradiction in our own requirements: `L1-SYS-015` (support
cross-filesystem copy) and `L1-SEC-007` (single filesystem only) were both
Active, introduced when the security invariants were added without reconciling
them against the L1 written two sessions earlier. Fixed by deferring the
cross-filesystem clause.

**Fourth drop (`rest-file-mover-m6`, rename engine) plus two architecture
documents — mostly reframed rather than adopted:**

The drop arrived alongside `file-mover-requirements.md` and a
`CYBERSECURITY.md` transcript, which together specify a substantially more
rigorous filesystem design than the milestone implemented. The requirements
did not conflict with the milestone so much as supersede the frame it was
built in.

| Inherited material | Outcome |
|---|---|
| `expand_rename_template` | **Adopted** as `cpp/src/rename_template.cpp`, `L3-CPP-042..045`. Pure, clock-free, and validates its own result against `.`, `..`, `/`, NUL so a template cannot escape its directory. |
| `rename_in_place` (path-based `lstat`/`link`/`unlink`) | **Not adopted.** Path-based check-then-act is the TOCTOU pattern the security requirements prohibit; `renameat2(RENAME_NOREPLACE)` is the correct primary with `linkat`/`unlinkat` as the NFS fallback; and no commit-point ordering was specified. See §10 of `docs/CYBERSECURITY.md`. |
| `[rename]` config growth | **Deferred** with the rename operation. Adding config for a feature that does not exist would be schema growth ahead of the code. |
| `CollisionPolicy` / suffix walk | **Deferred.** Up to 1000 `link()` probes per collision is up to 1000 NFS round-trips; re-evaluated once the fd-relative layer exists. Roadmap open question. |
| `{seq}` | **Adopted as a template field**, but the durable monotonic counter it implies is unspecified. Roadmap open question. |
| `file-mover-requirements.md` | **Adopted and renumbered** — `L1-SEC-001..007`, `L2-SEC-001..016`, `L2-NFS-001..008`. |
| `CYBERSECURITY.md` transcript | **Rewritten** as `docs/CYBERSECURITY.md` for this project: SQLite rather than a journal (ADR-0010), NFS treated as a primary target rather than deferred, both RHEL/SELinux and SLES/AppArmor, and an explicit "what exists today" table. |
| Journal (still present in the snapshot) | **Rejected** again — superseded by ADR-0010. |

Two scoping decisions came out of the review and are recorded as `L1-SEC-007`:
**same filesystem only** and **files only** for v1.0.0. Both remove attack
surface rather than save effort — the second because `linkat` does not work on
directories and NFS has no `RENAME_NOREPLACE`, so an atomic no-clobber
directory move does not exist on the target filesystem at all.

**A note on inherited test suites.** While porting, I reproduced a bug the
milestone's own development log had recorded: asserting that `{ext}` on
`.bashrc` "expands to empty", when an empty expansion is correctly *rejected*.
Reading the log did not prevent making the same mistake — the test suite
caught it. Worth remembering that the honesty log is a record of hazards, not
an inoculation against them.

**Third drop (`rest-file-mover-m4`, append-only journal) — mostly rejected:**

ADR-0010 had already given durability to SQLite, so the mechanism this
milestone built was superseded before it arrived. Rejecting it is applying an
existing decision, not making a new one.

| Inherited material | Outcome |
|---|---|
| `from_string(token, JobState&)` | **Adopted** as `L3-CPP-041` (renumbered from `L3-CPP-034`). Any durable store must turn a persisted token back into a state, so it belongs in the core rather than in whichever layer wanted it first. |
| `error` present iff state is `FAILED` | **Adopted as a concept** — `L2-JOB-010`, mechanism-neutral. The core's own invariant carried into persistence; belongs as a `CHECK` constraint when the schema is written. |
| Missing store = first boot; corruption = hard error | **Adopted as concepts** — `L2-JOB-011`, `L2-JOB-012`. Torn-tail tolerance was *not* adopted: SQLite's WAL owns that, and the concept does not translate. |
| `Journal` class, JSONL format, replay, `L3-CPP-038..044` | **Rejected** — superseded by ADR-0010. |
| `journal.{hpp,cpp}`, `test_journal.cpp` (529 lines) | **Not ported.** |
| `encode_journal_event` placed in `api_codec.hpp` | **Rejected on design grounds, independent of storage.** It made the REST codec `#include "journal.hpp"`. `api_codec.hpp` is the REST API boundary; persistence serialization is a separate concern with a different audience and a much stricter compatibility contract. This would have been wrong even if the journal had survived. |

**How the M4 change was actually found.** The snapshot's `job.hpp` and
`job.cpp` were the only files never edited on this side, so diffing exactly
those two against the repository isolated the one upstream change
(`from_string`) from ~900 KB of already-integrated material. Worth repeating:
find the files you have not touched, and diff those first.

**Second drop (`rest-file-mover-m3`, config loader):**

| Inherited material | Now lives in |
|---|---|
| `config.hpp` / `config.cpp` | `cpp/include/filemover/config.hpp`, `cpp/src/config.cpp` — schema section renamed `[journal]` → `[storage]` per ADR-0010, first-error changed to all-errors per L2-CFG-008 |
| `test_config.cpp` | `cpp/tests/test_config.cpp`, extended |
| `L3-CPP-m3.md` (`L3-CPP-026..033`) | `docs/L3-REQ.md` as **`L3-CPP-033..040`** — the inherited range collided with the codec |
| Everything else in the zip | Already integrated or superseded; the snapshot re-shipped M1/M2, the old ADRs, and picojson |

A note for future drops: the zip is a **full snapshot, not a delta**, and
arrives with Windows `Zone.Identifier` alternate-data-stream files (30 of them
last time). Both are noise. Diff against the repository before assuming
anything in a drop is new.

**First drop (`rest-file-mover-m2`):**

| Inherited material | Now lives in |
|---|---|
| Design conversation | ADR-0001 … ADR-0006, `cpp/README.md` |
| L1 system requirements | `docs/L1-REQ.md`, renumbered into `L1-SYS-*` / `L1-API-*` / `L1-OBS-*` |
| L2 component requirements | `docs/L2-REQ.md` — CORE, JSON, REN, MGR, XFR, DASH, plus a rewritten CTL |
| L3-CPP obligations | `docs/L3-REQ.md`, `L3-CPP-001..032` |
| Job state machine + tests | `cpp/src/job.cpp`, `cpp/tests/test_job.cpp` |
| Codec interface | `cpp/include/filemover/api_codec.hpp`, near-verbatim |
| Codec implementation | **Rewritten** on the project-owned parser (ADR-0006) |
| Codec tests | Rewritten; the picojson characterization suite died with picojson |
| Journal durability design | **Superseded** by ADR-0010 (SQLite); no retirement step needed |
| Milestone numbering (M1..M12) | Deliberately dropped — this repo tracks requirements, not inherited milestones |

## What the series was worth, in one paragraph

Eight snapshots of a complete, working, twelve-milestone C++ service produced,
in this repository, **one adopted component** (the HTTP request-head parser),
one adopted pure helper (the rename template engine), one adopted core function
(`from_string`), and roughly twenty requirements. Everything else was
superseded, deferred, or rejected — not because it was bad work, but because it
was built against a different set of constraints: a journal where we chose
SQLite, path-based filesystem calls where our security requirements demand
fd-relative ones, a `[transfer]` strategy with an exec escape hatch we removed
on principle. The pattern that held across every drop is that the **reasoning**
ported and the **code** usually did not, and the later drops were mined almost
entirely for reasoning. That is a real result, and it is worth knowing before
commissioning the next one.

The corollary, recorded twice in the notes above and worth stating plainly: the
drops' own honesty logs described bugs that were then reproduced here anyway
while porting the very code the log was about — the `{ext}` empty-expansion
case in M6, the bare-LF framing verdict in M9/M10. Reading a hazard log is not
protection against the hazard. Tests are.
