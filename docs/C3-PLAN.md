# C3 — move engine: implementation plan

The milestone where bytes actually move. One atomic commit point: everything
before it disposable, everything after it idempotent (`L1-SEC-001`,
`L1-SEC-002`).

Written before any code, like `docs/C2-PLAN.md`, because two things turned up
in the requirements that change the shape of the work.

---

## 1. What v1.0.0 actually does — and does not

**There is no copying in C3.** This is the single most important thing to have
straight before writing anything.

`L1-SYS-015` was rewritten to remove the cross-filesystem copy clause: it
contradicted `L1-SEC-007`, which restricts v1.0.0 to one filesystem. `L2-XFR-002`
(write to a temporary name, fsync, rename) is annotated *Deferred → v1.1* with
the reasoning that "a same-filesystem move is an atomic rename with no partial
state to expose". `L2-XFR-003` — the external-command strategy — was removed
outright by ADR-0011.

So the engine performs **a same-filesystem move and nothing else**. No read/write
loop, no buffer size, no partial-file resume. The roadmap's warning applies
directly: do not implement the deferred parts to feel complete.

## 2. Two spec inconsistencies found while reading

Recorded rather than worked around, and **not fixed here** — both change the
headline coverage figure, which makes them decisions rather than cleanups.

### 2.1 The in-scope `L2-COPY-*` requirements describe a capability v1.0.0 lacks

`L2-COPY-001` (bounded-memory read/write loop), `002` (copy buffer size), `003`
(per-file concurrency), and `011` (kernel-assisted copy) all hang off
`L1-SYS-001`, which is **Active** — so the trace matrix counts them in v1.0.0
scope. Every one of them describes copying, which v1.0.0 does not do.

They cannot be satisfied without building the copy engine that `L1-SEC-007`
forbids at this release. This is the same class of contradiction the project
already caught once, when `L1-SYS-015` was found Active alongside `L1-SEC-007`
and had to be rewritten.

The likely correction is that these four are parented to the wrong L1 — they
belong under `L1-SYS-003`, which is already Deferred, rather than under "transfer
independently of orchestration". That is a requirements change and needs a
decision, so C3 leaves them untraced and this note explains why the figure will
land short of the roadmap's estimate.

### 2.2 `v1.0.0 Status` annotations on L2 requirements are decorative

`L2-XFR-002` carries `**v1.0.0 Status**: Deferred → v1.1` in `docs/L2-REQ.md`.
`scripts/build-trace-matrix.py` scopes only by **L1** status
(`deferred_l1s`), so that annotation is never read and the requirement is
counted in scope regardless.

Someone wrote a deferral that has no effect. Either the generator should honour
L2-level annotations, or the annotation should be removed so it stops implying
a scoping it does not perform. Also a decision — teaching the matrix to honour
them would shrink the denominator and *raise* the reported percentage, which is
exactly the kind of change that should be made deliberately and never as a side
effect of a milestone.

## 3. Scope

| Requirement | Substance | Where |
|---|---|---|
| `L1-SEC-001` | Exactly one atomic commit point, a single rename | **C3** |
| `L1-SEC-002` | Before disposable, after idempotent | **C3** |
| `L1-SYS-015` | Same-filesystem atomic rename | **C3** |
| `L1-SYS-021/022` | State sequence, and rejection of anything else | **C3** (core + store already enforce; C3 drives it) |
| `L1-SYS-023` | Per-job error description on failure | **C3** |
| `L2-XFR-001` | Common transfer interface, optional progress callback | **C3** |
| `L2-XFR-004` | Human-readable errors including errno text | **C3** |
| `L2-JOB-014` | Phase policy — abort before commit, halt after | **C3** carries out C1's verdict |
| `L2-SEC-011` | Neither source nor destination present → failed-external | **C3** carries out C2's classification |
| `L2-XFR-002`, `L2-COPY-*` | Copying | **v1.1** — see §1 and §2.1 |
| `L1-SYS-016` | Mark interrupted jobs FAILED at startup | **C6** — needs a startup sequence |

## 4. Where the commit point is, exactly

This needs stating because the delivery pattern uses **two** renames and
`L1-SEC-001` allows exactly **one** commit point.

```
  phase 1  validate, classify, verify identity, check trust     no side effects
  phase 2  durable QUEUED -> RENAMING
  phase 3  rename  source -> destdir/.swit-partial-<job>        <== COMMIT POINT
  phase 4  durable RENAMING -> TRANSFERRING
  phase 5  fsync, rename .swit-partial-<job> -> final name      idempotent
  phase 6  durable TRANSFERRING -> DONE
```

The commit point is **phase 3**, not phase 5. Phase 3 is where the source stops
existing under its original name — the irreversible act. Phase 5 is a rename
within one directory that can be re-driven any number of times to the same
result, which is what `L1-SEC-002` means by idempotent.

Phase 5 exists because of `L2-NFS-007`: a rename is atomic on the server but
other clients may briefly observe neither name or both, so a consumer watching
the destination must never see a partial object under its final name. Note this
is *not* `L2-XFR-002` — that one is about partial **writes**, which cannot
happen here, and is deferred. Same pattern, different hazard.

**No failure path deletes a source whose destination is not durably in place**,
structurally: the source is never deleted at all. It is *renamed*, atomically,
and the same syscall that removes the old name creates the new one. There is no
copy-then-delete window to get wrong. That is the whole reason `L1-SYS-015`
specifies rename.

## 5. What happens when each phase fails

| Fails at | Verdict | Why |
|---|---|---|
| 1 | Rejected | Nothing happened; source untouched |
| 2 | AbortedBeforeCommit | `L2-JOB-014` before-commit: no durable record, so take no action |
| 3 | AbortedBeforeCommit | The rename failed; source still at its original name |
| 4 | **HaltedAfterCommit** | The move is real but unrecorded. Do not proceed, flag for an operator, log at high severity |
| 5 | HaltedAfterCommit | Source is gone and the object is not yet visible; recovery re-drives phase 5 |
| 6 | HaltedAfterCommit | Delivered but unrecorded — the record and reality disagree |

Recovery reads `classify_move_state(source, temp)` from C2:

* `NotStarted` — phase 3 never ran. Re-drive from phase 2.
* `Interrupted` — a `linkat` landed without its `unlinkat` (the NFS path). Both
  names on one inode; finish the `unlinkat` and continue.
* `Completed` — phase 3 done, phase 5 may not be. Re-drive phase 5, which is
  idempotent.
* `Collision` — a different file occupies the destination. Fail with a
  description; never clobber.
* `BothMissing` — `L2-SEC-011`. Mark failed-external, log at high severity, do
  **not** retry automatically.

## 6. Testing

The done-when is a crash suite: **SIGKILL between every pair of phases**, then
assert the next start can reconcile. C1's fork-and-`SIGKILL` pattern applies
directly, with a phase seam so the kill lands at a chosen boundary rather than
by timing.

Add to the existing seams:

* A `set_phase_hook` on the engine, invoked between phases with the phase index,
  default null, not behind an `#ifdef` — the code under test must be the code
  that ships.
* Reuse `JobStore::inject_write_fault` for phases 2, 4 and 6, which is how the
  `L2-JOB-014` verdicts get exercised against a real SQLite refusal rather than
  a mocked one.
* Both move strategies, forced explicitly, as C2 established.

## 7. Sequence

1. `MoveEngine` interface with the progress callback (`L2-XFR-001`) and the
   outcome enum. Interface first, because `L2-XFR-001` exists specifically so
   v1.1's copy strategy is an addition rather than a change to every caller.
2. Phases 1–3 with the commit point, both strategies.
3. Phases 4–6, and the `L2-JOB-014` verdict handling.
4. Recovery from each `MoveState`.
5. The kill-between-every-phase suite.
6. Trace matrix, docs, battery, merge.

## 8. Coverage expectation

The roadmap estimates ~55% after C3. **Expect roughly 48–50%.** The gap is
§2.1: five `L2-COPY-*` requirements sit in the denominator describing a
capability this release does not have, and C3 will not tag tests to
requirements it does not implement. A figure at 55% would mean exactly the
dishonesty this project has been careful to avoid.

### What actually happened: 44.2%

Below even the revised estimate, and worth recording rather than quietly
restating. The reasoning above was right about the roadmap's 55% being
unreachable and wrong about the size of the correction.

C3 adds only two previously-untraced L2 requirements — `L2-XFR-001` and
`L2-XFR-004`. Everything else it touches (`L2-JOB-013/014`, `L2-SEC-004/006/011`)
was already traced by C1 and C2; the engine exercises those requirements harder
but does not move the count. The L1s it satisfies — `L1-SEC-001`, `L1-SEC-002`,
`L1-SYS-015` — are composite and counted transitively through children that
were already covered.

The lesson for C4 onward: a milestone's contribution to the trace figure
depends on how many requirements it is the *first* to verify, not on how much
work it is. Estimating from milestone size will keep being wrong. Estimate by
listing the specific untraced IDs the work will close.
