---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: the Python implementation's SQLiteJobRepository (WAL, synchronous=FULL)
supersedes: the append-only journal design inherited from the external design conversation
---

# Use SQLite for durable job state, not an append-only journal

## Context and Problem Statement

The service must survive an unclean shutdown and know, on restart, what was in
flight. Two designs were on the table:

* The **inherited design** specified an append-only journal — one JSON record per
  line, `O_APPEND`, replayed at startup.
* The **Python implementation** uses SQLite (WAL, `synchronous=FULL`) as the
  authoritative durable queue, listed as a "do not drop" decision in
  `docs/ROADMAP.md`.

Neither was adopted by default. The question was reopened because the C++ target
and the narrowed v1.0.0 scope genuinely change the calculus: with no claiming, no
per-file records, and recovery that only marks interrupted jobs FAILED
(`L1-SYS-016`) rather than resuming them, a journal is *sufficient* for v1.0.0 in
a way it would not have been for v0.4.2.

## Decision Drivers

* Correct crash semantics above all else
* `L1-OBS-002` requires aggregate statistics, polled by the dashboard every ~2s
* `L1-SYS-017` allows multiple worker threads, so writes are concurrent
* v1.1 restores claiming, integrity verification, and recovery-by-resumption,
  which need per-file records and partial-transfer offsets
* ADR-0007 license policy
* ADR-0006 established a preference for auditable, project-owned code

## Considered Options

### Append-only journal

* **Good**: the simplest possible durable write — one `write()`, one `fsync()`.
  A torn final record is trivially detectable and discardable because everything
  before it is intact.
* **Good**: ~200 lines, no dependency, no license question, and small enough to
  audit line by line — consistent with the reasoning in ADR-0006.
* **Bad**: reads are O(n) replay. `GET /api/status` needs exactly the aggregate a
  log is worst at. The usual remedy is an in-memory index rebuilt at startup,
  which introduces a second source of truth that can disagree with the first.
* **Bad**: unbounded growth requires a compaction subsystem — rewrite, atomically
  swap, lose nothing on a crash mid-compaction. This is the part that is
  routinely underestimated.
* **Bad**: concurrent writers need locking we implement ourselves. `O_APPEND`
  atomicity is narrower than it appears and does not hold on NFS.
* **Bad**: v1.1's per-file records and offsets are a poor fit, making a migration
  likely.

### SQLite (amalgamation)

* **Good**: **public domain** — the cleanest possible position under ADR-0007,
  with no allowlist question at all.
* **Good**: WAL plus `synchronous=FULL` gives well-understood crash semantics,
  tested against these exact scenarios far more thoroughly than we could.
* **Good**: aggregate queries are trivial and indexed; concurrency, durability,
  and compaction are solved rather than built.
* **Good**: single C89 amalgamation file, compiles on GCC 4.8, fits ADR-0004's
  vendoring discipline unchanged.
* **Good**: absorbs v1.1's per-file records without a redesign, and the Python
  implementation already proved the schema shape against these requirements.
* **Bad**: ~250,000 lines that we cannot audit. This directly contradicts a
  stated driver of ADR-0006.
* **Bad**: roughly 1 MB of binary size, and another dependency to pin and qualify.
* **Bad**: SQLite over NFS is unsafe — its locking relies on POSIX advisory locks
  that NFS implements unreliably.

## Decision Outcome

Chosen option: **SQLite**, vendored as the amalgamation under ADR-0004.

The deciding argument is not performance. It is that a durability-layer migration
at v1.1 would mean rewriting the component whose correctness matters most, under
schedule pressure, after it already appears to work — which is precisely when
durability bugs are introduced. Paying that cost now, against a schema the Python
implementation has already validated, is cheaper than paying it later.

The public-domain status also resolves cleanly against ADR-0007, which is the
constraint that forced the JSON parser in-house.

### Consequences

* Good: `L1-OBS-002` aggregates are a `GROUP BY` rather than a replay plus an
  in-memory index.
* Good: v1.1 claiming and integrity work extends a schema instead of replacing a
  storage layer.
* Bad: the "everything on the untrusted path is project-owned and auditable"
  property from ADR-0006 does **not** extend to durability. This is a real
  inconsistency and is accepted knowingly: SQLite is not on the untrusted-input
  path — it sees only values the codec has already validated.
* Bad: if v1.1 never happens, we bought capability we did not need.

### Constraints

1. **Service state must live on local disk, never the NFS mount.** SQLite's
   locking is unsafe over NFS. Recordings live on NFS; state does not. This must
   be verified in the deployment runbook rather than assumed, and configuration
   validation should reject a state path that resolves onto a network filesystem.
2. WAL mode with `synchronous=FULL`, matching the Python implementation.
3. The amalgamation is vendored verbatim per ADR-0004 and never edited.
4. SQL is confined behind a repository interface, so no other translation unit
   includes `sqlite3.h` — the same containment discipline ADR-0006 applies to the
   codec.
