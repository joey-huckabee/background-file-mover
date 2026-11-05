# Increment 111: schema-12 foundation and legacy readers

2026-11-04. The user authorizes the next bounded implementation after the
[migration design](api/SCHEMA-12-MIGRATION-DESIGN.md): target schema and legacy
readers, with migration apply disabled. This is the first implementation slice,
not the completed upgrader, a backup command, P01 freeze or release approval.

## Implemented boundary

Fresh explicit source initialization now creates schema 12. It uses the proposed
jobs_v12-create/rename/index recipe so its canonical DDL matches a rebuilt target.
Jobs carry explicit identity_kind, nullable legacy submission_id, 16-byte UUID
and 32-byte request-digest fields. Partial unique indexes separate legacy
(generator,submission) from globally unique UUID bytes. CHECKs enforce branch
exclusivity, field types, lengths and non-NULL digest version. No new dependency
or producer wire adapter is added.

The current prototype writer explicitly inserts legacy kind 0. Both advisory
replay and transactional acceptance filter on that kind; row reconstruction
checks kind before decoding legacy text. Existing paths, file indices, status,
retention, receipts and manifest-v1 code remain unchanged. UUID-looking legacy
IDs stay legacy. This build cannot admit or recover UUID jobs: a whole-database
capability check rejects any UUID row with UnsupportedIdentity before writable
Store settings or payload bootstrap, including offline history clear. There is
no UUID-to-submission_id conversion and no skipping unsupported jobs.

Normal daemon, initialize, transfer and offline-clear entry points preserve
increment 110's guard/lifetime ordering. State with schema 11 now refuses with
MigrationRequired before conversion/bootstrap; unknown/older/foreign state still
refuses. Missing state is allowed only through explicit fresh initialization.
The original schema-11 jobs DDL is retained for predecessor fixtures. There is
no runtime converter, backup/apply entry point or automatic legacy upgrade.
Do not install this foundation build over a schema-11 service as a usable upgrade;
keep the compatible original binary/state until the guarded upgrader is ready.
No operational database or payload files were changed by this work.

An additional local sequence check rejects missing/duplicate/noninteger or
regressed jobs high-water marks rather than allocating reused IDs. An empty
never-allocated database may lack a jobs sequence row; a cleared database retains
its high-water mark. It cannot detect an independently restored stale snapshot;
the existing no-stale-restore and fencing limitations remain.

## Meaningful validation

Six new Store tests exercise:

- A test-only schema-11 rebuild: canonical target DDL, unchanged original job
  columns and every dependent/shared row, legacy mixed expected-size assertions,
  exact path/index preservation, missing state, replay and next ID above the old
  cleared high-water mark.
- Empty never-allocated and cleared-highest-ID sequences survive that test recipe.
- An actual schema-11 layout refuses without mutation through all Store modes.
- Same textual UUID across legacy/new namespaces is allowed by SQL; duplicate
  UUID across generators, invalid BLOB/type/length, NULL/version and mixed branch
  fields fail constraints. This does not enable UUID HTTP admission.
- Storage-valid UUID-bearing target state refuses in all Store modes without mutation.
- Corrupt sequence state refuses without automatic repair.

The rebuild recipe exists only in cfg(test), on disposable fixtures. It is not a
qualified migrator, downgrade, fault-safe conversion or backup path. Existing
operator/audit/retention/clear and actual payload/manifest tests remain required.
The restart integration test now explicitly requires UUID-looking legacy IDs to
complete with v1/submission_id, never recording_id. Version-refusal CLI cases now
include 11 and use 13 as the unsupported future version.

Validation status: **PENDING**. Independent review and both pinned cargo-libc/SLES
gates must validate the final changed source before closeout. Production NFS,
source deletion, physical power-loss durability, target migration/backup and
historical executable cutover remain unqualified. Historical bootstrap acquisition
assumptions affected by increment 110 still need review/adaptation and separate
fresh qualification; no NFS experiment is started here.
