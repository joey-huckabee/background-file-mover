# Schema-11 upgrade specification

Approved scope: 2026-11-04. The user accepted the recommendation to define one
explicit offline upgrade path from validated schema 11, preserving legacy
recovery and refusing state outside the declared matrix. This document completes
migration planning step 1. It does not authorize runtime migration code, freeze
P01, or declare any upgrade qualified. Groups 1-52 remain the product baseline.

## Target and release evidence

The planned target is the next schema, provisionally schema 12. Its exact SQL,
identity layout and manifest integration belong to the implementation design;
changing a version integer alone does not implement this specification.

Reference predecessor source: `7c662239f00bd0ad87ec31bf82d553fc2663963d`.
It uses application ID `0x42464d52`, schema 11 and manifest v1. This source
reference is not an executable qualification claim. Before publishing support,
record the exact predecessor and target binary hashes, source revisions, pinned
build inputs, fixture provenance and production/qualification gate reports.
An artifact from another revision must be identified separately and assessed for
state-format equivalence; do not silently label it as the reference binary.

Support is defined by validated persisted structure and semantics, not by a
claimed producer version alone. An unknown binary or schema-11 label does not
establish provenance or compatibility. No operational database is a test fixture.

## Planned support matrix

Every row below is a required future behavior; runtime status is **NOT_RUN**.

| Input | Required disposition |
|---|---|
| Supported, valid schema 11 with retained jobs | Explicit offline transactional upgrade, preserving every invariant below. |
| Supported, valid schema 11 with zero jobs | Upgrade while preserving shared instance/enrollment state and the job-ID high-water mark, including state emptied by clear. |
| Valid target schema | Validate and report no migration needed; no repeated transformation. |
| Schema 1-10 | Refuse this path; preserve state and explain that a separately declared, qualified predecessor path is required. Do not automatically chain historical migrations. |
| Unknown or newer schema | Refuse and report observed format and compatible-software requirement. |
| Foreign application ID or foreign SQLite contents | Refuse; never initialize or convert it. |
| Corrupt, unreadable or internally inconsistent state | Refuse without repair, reset, replacement or partial upgrade. |
| Missing or empty database | Migration refuses without CREATE or initialization. Fresh setup remains a separate explicit operation. |
| Active daemon or surviving lifetime-epoch worker | Refuse before SQLite admission for migration. |
| Incompatible old binary against upgraded state | Supported installation/startup procedure must refuse before storage effects; direct old-binary invocation is not a supported rollback path. |

The current ordinary Store opener automatically migrates versions 1-10. The
new release must explicitly replace that behavior for this path with refusal;
this is an intentional support boundary, not a claim that those schemas were
never previously accepted. A future older-version upgrade needs its own matrix
and qualification. Fresh target initialization remains separately gated by the
existing explicit enrollment and unused-scope rules.

## What constitutes valid predecessor state

Under offline ownership, inspect the existing database using a no-CREATE path.
Validate application/schema IDs, required table/column/index/constraint structure,
SQLite integrity and foreign keys, and reconstruct each persisted job using the
existing custody/commitment validation semantics. Include shared metadata,
source enrollment/ownership, destination policies, reservations and sequences.
Do not trust version integers, a published file or a manifest alone as proof of
validity or commitment. Structural tolerance for optional SQLite objects must be
specified in the implementation; it cannot permit unknown executable triggers
or constraints to run unnoticed during conversion.

Validation must distinguish legitimate review/incomplete setup from corruption.
A review-required job is valid when its recorded evidence is consistent. A
supported interrupted enrollment remains in its original refused/review state;
migration cannot complete enrollment or authorize work. If preservation cannot
be established, refuse with a diagnostic rather than inventing missing evidence.

Do not reapply new-producer UTF-8/admission restrictions destructively to legacy
records. Preserve any valid predecessor identity/path representation exactly;
if the implementation cannot do so, identify that combination as unsupported
before mutation and document the limitation before declaring support.

Migration reads local state, not source/destination payloads. Unavailable payload
roots must not prevent database validation/conversion. Normal service recovery
still performs its existing binding/custody checks before effects. This does not
qualify recovery while storage is unavailable or prove remote RPC settlement.

## Preservation invariants

Compare logical records before and after conversion; SQLite page bytes may
change, but the following evidence must not:

- Original job IDs, durable file indices, file IDs, exact paths and ordering.
- Legacy generator/submission identity and same-request replay recognition.
- Complete original expected-size assertions, including absent versus supplied
  maps; actual measured sizes and hashes remain separate evidence.
- Source/destination routing, bindings, enrollment and shared instance identity.
- Claims, reservations, all transfer attempts, phases and object identities.
- Missing-file deadlines, retry counts/deadlines, review epochs and failure codes.
- Operator command IDs, receipts, audit reasons and prior-state context.
- Manifest serialized bytes, hashes, phases and object identities.
- Job-ID sequence/high-water mark, including after clearing the highest job.
- Lifetime evidence files and existing exclusion checks; no clearing or replacing
  those files to obtain admission.

Legacy `(generator_id, submission_id)` remains a distinct identity namespace.
Never infer a recording UUID from legacy text, even when it looks like a UUID.
The new global UUID namespace must coexist without changing legacy replay keys.
Still-tracked legacy jobs continue manifest v1 even when they finish after the
upgrade. Stored manifest bytes remain authoritative and are never reserialized
merely to match a newer implementation. New recordings use v2 only when that
separate producer/manifest implementation is authorized and qualified.

Current expected-size policy remains a startup/runtime setting, not a newly
invented per-job snapshot. Migration preserves assertions and actual custody;
it must not measure, re-claim, recopy, publish, remove or rename payloads.

Group 50 applies without exception: previously cleared jobs remain absent. Do
not scan leftovers, reconstruct ownership/accounting, adopt old manifests or
restore replay receipts. Payloads and manifests remain untouched and unmanaged.

## Supported retained-job conditions

| Condition | Acceptance obligation |
|---|---|
| Accepted / awaiting claims / missing files | Preserve acceptance, stable indices, reservations and missing deadlines. |
| Claimed / partially copied | Preserve original custody, destination allocation and all attempt receipts. |
| Verified / published but uncommitted | Preserve exact recovery boundary; never promote publication to commitment. |
| Retry backoff / review required | Preserve counters, deadlines, review epochs, commands and exact replay behavior. |
| Manifest phases 0-3 | Preserve immutable bytes and publication evidence without inferring commitment. |
| Committed | Preserve validated commitment and exact v1 manifest bytes. |
| Multiple mixed jobs / cleared history | Preserve each tracked job independently; never resurrect cleared records. |

No cancellation state is introduced by migration. Clearing cancelled jobs,
remote administration, deletion and repair are outside this scope.

## Transaction, backup and interruption contract

Acquire InstanceGuard and independent lifetime admission before SQLite access;
register the migration process lifetime before opening its Store owner. Hold
ownership until every SQLite owner/backup connection has closed. Admission must
cover all relevant service and effect entry points, not only the migration CLI.

Require a verified consistent local backup before modifying authoritative state.
It must include committed WAL content through a supported SQLite-consistent
backup procedure; copying only the main database file is insufficient. Associate
it with the exact instance, schema, tool/binary and relevant enrollment/lifetime
context. Do not transplant or reactivate lifetime metadata from a backup. A
backup failure or insufficient space refuses migration. Specify private output,
no-clobber naming and verification in implementation; do not add a dependency
merely to implement backup.

Revalidate under the exclusive migration ownership and transaction before
conversion. Transform and validate reconstructed target state in one transaction;
advance schema version atomically with the transformation. Validation must occur
before commit, unlike relying solely on checks after committing a version bump.
No success is reported until commit and required durability operations succeed.

Before commit, rollback leaves the logical predecessor state authoritative.
After commit, recover with the compatible target binary. An ambiguous I/O result
requires reopening under exclusion and validating the committed schema; do not
assume failure means no commit and do not restore a backup automatically.
Crash, process-kill, ENOSPC and SQLite I/O tests must distinguish transaction
atomicity evidence from actual hardware power-loss durability.

## Draft operator procedure -- not executable instructions yet

No migration CLI exists for this specification. Exact command spelling will be
provided with implementation; do not run guessed commands against service state.

1. Install/stage the declared compatible tool and verify its identity. Preserve
   the predecessor binary and configuration for diagnosis.
2. Stop the service using the documented stop procedure. If workers survive,
   follow the restart guide and restore storage as needed; wait for their exit.
   Never remove lock/lifetime files, kill unrelated processes or force takeover.
3. Run guarded existing-state preflight. Resolve a refusal without modifying
   custody or reinitializing. Preflight may write normal local lifetime metadata;
   it is read-only with respect to job data, not entirely filesystem-read-only.
4. Create and verify the consistent protected backup while ownership is held.
5. Explicitly request migration. The command repeats admission/validation; an
   earlier successful preflight is not continuing permission or a held lock.
6. Verify the target schema and preservation summary. Start the target service
   normally with the original configuration, state and enrollment.
7. Inspect status and recovery. Preserve review conditions and apply ordinary
   audited operator actions only when their existing prerequisites are met.

If failure occurs before commit, retain original state and diagnostics. If the
commit outcome is uncertain, stop and run the guarded inspection procedure. If
target state committed, use forward recovery with the target binary. There is
no supported automatic downmigration and no supported stale-database restore
over progressed custody. Reinstalling an old executable does not roll back state.

The old binary currently may touch source bootstrap before rejecting a newer
database. It cannot be retroactively fixed by the migration tool. The eventual
installation/startup compatibility check must run before such effects; test the
supported launch procedure explicitly, and document direct old invocation as
unsupported. Moving files out of the way is not a compatibility check.

## Fixture and acceptance checklist

All cases are **NOT_RUN** for this upgrade. Use synthetic/disposable local
fixtures; record fixture source revision, creation method and expected records.
Map each preservation invariant above to before/after assertions. Assertions
compare logical identity/evidence, not SQLite file-byte equality.

| ID | Fixture / experiment | Required evidence |
|---|---|---|
| MIG-01 | Valid schema-11 empty and previously-cleared instances | Shared state and increasing ID sequence survive; no resurrection. |
| MIG-02 | Mixed retained lifecycle conditions listed above | Every invariant and original replay result preserved; review stays review. |
| MIG-03 | Legacy non-UUID and UUID-looking submission IDs | Both stay legacy; no invented UUID or namespace collision. |
| MIG-04 | Stored v1 manifests and unfinished legacy jobs | Exact bytes/hashes retained; continuation still produces/uses v1. |
| MIG-05 | Schemas 1-10, newer/unknown, foreign, missing/empty | Clear refusal, no initialization, migration or payload effects. |
| MIG-06 | Corrupt structure, FK/semantic mismatch, unreadable state | Error before conversion; original authoritative evidence preserved. |
| MIG-07 | Live daemon and orphan worker after coordinator exit | Refusal before SQLite migration access; rows unchanged. |
| MIG-08 | Target-schema rerun and malformed target | Valid target is no-op; malformed target refuses. |
| MIG-09 | Kill/fault at conversion and commit boundaries | Valid old or valid new state on reopen; never partial conversion. |
| MIG-10 | Committed WAL, backup failure, disk/I/O failure | Backup includes WAL; failure safe; ambiguous commit resolved by inspection. |
| MIG-11 | Unavailable source/destination roots | Offline migration succeeds without payload I/O; startup checks remain. |
| MIG-12 | Incompatible predecessor launch through supported procedure | Refusal before source/destination bootstrap and database mutation. |
| MIG-13 | Original-state restart after upgrade with unmanaged leftovers | Recover tracked work only, preserve payload identity/bytes, no adoption. |

New UUID admission/concurrency and v2 consumer tests remain obligations of later
implementation increments; MIG-03 alone does not establish those capabilities.
All Rust builds/tests use `scripts/check-rust-sles.py` in both pinned production
and qualification modes, with independent ELF audits and exact-target tests.
Local fixtures do not qualify production NFS, remote settlement, systemd
installation, power-loss durability, deletion or release readiness.

## Implementation handoff and completion

Planning step 1 is complete when this matrix, invariants, refusal rules and
acceptance dispositions are recorded and reviewed. Runtime work needs separate
authorization. The next bounded implementation proposal is early compatibility
preflight before source/destination bootstrap; transactional conversion follows
only after its target SQL/identity design is concrete and reviewable.

Before any supported-release claim, replace NOT_RUN with exact evidence and
publish the exact supported binary/state pairs. No predecessor executable,
new-schema layout or rollback procedure becomes qualified by this document.
