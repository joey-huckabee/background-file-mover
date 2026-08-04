# Test Strategy

What kinds of testing this project uses, what exists today, and — the part that
matters — which kinds get **disproportionately more expensive the longer they
are deferred**. Written during C1, when the code base is still small enough
that adding a tier is cheap.

The trace matrix answers "is this requirement verified?". This document answers
the different question "are we verifying it in a way that would actually catch
the failure?".

## Status at a glance

| Tier | State | Lands |
|---|---|---|
| Unit | **In place** — 7,300+ assertions, 127 cases | C0 |
| Crash / durability | **In place** for the store (kill-at-every-statement) | C1 |
| Source gates | **In place** — vendored hashes, locale-free, SQL confinement | C0–C1 |
| Coverage-guided fuzzing | **In place** — JSON and HTTP, committed corpora (ADR-0008) | C0 |
| Sanitizers / Valgrind | **In place** — ASan, UBSan, LSan, TSan, memcheck | C0 |
| Fidelity (GCC 4.8.5) | **In place** — full suite, not just a compile | C0 |
| Migration / upgrade | **Proposed** — see *Start now* | C1 |
| Fault injection | **Proposed** — see *Start now* | C1–C3 |
| Conformance corpora | **Proposed** — see *Start now* | C1 |
| Concurrency (deterministic) | Planned — latch-based, injected clock | C4 |
| Hostile / negative (REST) | Planned — the hostile battery | C5 |
| End-to-end | Planned — needs a `main()` to exist | C6 |
| Performance baseline | Proposed | C6+ |
| Platform qualification | Planned — real RHEL 9 / SLES 12 SP5 hardware | C9 |

## Start now — these get expensive if deferred

### 1. Migration fixtures

**Why now:** the moment a schema v2 exists, a v1 database is something you have
to *reconstruct from memory* to test against. Today one is free — the current
build produces it.

Check in a small, real v1 store as a binary fixture and assert that opening it
migrates cleanly and preserves its rows. Repeat per schema version, forever.
The cost of starting is one file; the cost of starting late is archaeology.

### 2. Fault injection

**Why now:** `L2-JOB-014` is *about* durable-write failure — abort before the
commit point, halt after — and there is currently no way to make a durable
write fail on demand. A requirement whose whole subject is a failure mode
cannot be verified without producing that failure. This is the single largest
gap in C1's verification, and it is why `src/store.cpp` sits near 75% line
coverage while the rest of the tree is 91–100%: the uncovered quarter is almost
entirely "what happens when this write fails".

Three privilege-free techniques, in increasing order of bluntness:

* `PRAGMA max_page_count` — makes further writes fail with `SQLITE_FULL`
  without filling a real disk. Cheapest and most targeted.
* `setrlimit(RLIMIT_FSIZE)` in a forked child, with `SIGXFSZ` ignored, so
  writes fail with `EFBIG` at a chosen size. Exercises the real errno path.
* A read-only directory, so WAL sidecar creation fails at open.

The forked-child pattern already used by the crash suite applies directly: the
injected limit dies with the child instead of leaking into later tests.

### 3. Conformance corpora

**Why now:** both parsers are hand-rolled and sit on untrusted input
(`docs/HAND-ROLLED-COMPONENTS.md`). Fuzzing proves they do not *crash*;
conformance proves they accept and reject the *right* inputs. Those are
different claims, and only the second one catches a parser that is confidently
wrong.

* **JSON** — a published suite of accept/reject/implementation-defined cases is
  the standard instrument here. The project's strictness profile (ADR-0009) is
  deliberately narrower than the standard, so the expected verdict per case has
  to be recorded rather than assumed — which is itself a useful exercise: it
  turns "strict subset" from a phrase into a table.
* **HTTP** — a table of raw request bytes to expected outcomes, extending the
  cases already in `test_http_parser.cpp`. This grows directly into C5's
  hostile battery rather than being thrown away.

### 4. A coverage floor

**Why now:** coverage is measured but not enforced, so it can only decay
silently. A floor makes a drop a failure rather than a number nobody reads.

Set it below the current figure — enough headroom that a new component landing
partially covered does not block work — and treat it as a **ratchet**: raised
deliberately, never lowered quietly to make a build pass.

## Deferred deliberately, with the reason

* **End-to-end** — genuinely blocked. There is no `main()` until C6, so an E2E
  test would have nothing to start. What *can* be decided early is the harness
  shape: how the service is launched, how a test gets an isolated state
  directory and NFS-like mount, and how it asserts on a moved file. That
  decision belongs with C6, not before.
* **Concurrency** — ThreadSanitizer has gated since before any thread existed
  (`L2-ARC-008`), deliberately. The deterministic interleaving tests belong
  with C4, when there is something to interleave.
* **Performance** — meaningless before bytes move. Worth a baseline as soon as
  C3 lands, because a throughput regression on a ~100 GB transfer is invisible
  in a unit test.

## Principles

* **A gate that cannot fail is not a gate.** Every source gate added here has
  been verified by deliberately introducing the violation it exists to catch
  and confirming it fails. An untested gate is a comment with a build step.
* **Prefer a mechanical check to an inspection.** `L2-JOB-009` was specified as
  Inspection; it is now `make sql-confined`. Inspection is the verification
  method that silently stops happening.
* **Coverage is a floor, not a target.** 100% line coverage of error paths that
  are never *taken* proves nothing; a fault-injected 80% is worth more than a
  contrived 95%.
* **Test the file, not the function, where the requirement is about the file.**
  Durability requirements are about what survives on disk, so the crash suite
  kills real processes rather than mocking a failure — an injected error still
  unwinds and cleans up, which is precisely what a crash does not do.
