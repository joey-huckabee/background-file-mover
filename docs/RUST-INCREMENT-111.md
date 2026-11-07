# Increment 111: schema-12 foundation and legacy readers

2026-11-04 through 2026-11-05. The user authorizes the next bounded implementation after the
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

An additional local sequence check rejects missing/duplicate/noninteger values
and sequences below a retained job ID rather than repairing them. An empty
never-allocated database may lack a jobs sequence row; a cleared database retains
its high-water mark. Once jobs are cleared, the former maximum cannot be recovered
independently from a damaged or lowered counter; never scan leftovers to infer it.
This check cannot detect an independently restored stale snapshot. Preserve the
recorded sequence during conversion; existing no-stale-restore/fencing limits remain.

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
operator/audit/retention/clear and local payload/manifest tests passed as regressions.
The restart integration test now explicitly requires UUID-looking legacy IDs to
complete with v1/submission_id, never recording_id. Version-refusal CLI cases now
include 11 and use 13 as the unsupported future version.

Validation status: **PASSED for this bounded foundation**. Validated source:
`617960a7404cb0dec9359aaf7862709cc1a81e31`. The
[evidence inventory](SCHEMA12-FOUNDATION-EVIDENCE.json) records exact inputs,
report/archive hashes, profile results and limitations.

| Mode | Run | Debug passed | Release passed |
|---|---|---:|---:|
| Production, strict offline | `20261105T053518Z-09ab3d21` | 227 | 227 |
| Qualification, strict offline | `20261105T060535Z-5f6f819b-nfs-qualification` | 229 | 229 |

Both gates passed formatting, Clippy, cargo-libc GNU/glibc-2.22 inspection,
independent ELF audits with six negative controls, eager relocation and actual
pinned SLES 12 SP5 tests. Five existing opt-in cases remain ignored per profile;
no ignored attribute was added or changed. Builder/runtime networking was disabled,
and both gates cleaned up without error. No host-only Cargo tests were used.

Independent local verification matched all 65 archived inputs in both runs to
the committed Git blobs and rehashed all 40 retained executables. The frozen
schema-11 jobs DDL matches the predecessor definition exactly after its fixture
comment. Rebuild tests are inside the existing cfg(test) module, not the daemon.
Raw evidence remains in
`/home/joey/GIT/background-file-mover-testing/rust/validation/`, outside Git.

Production NFS, source deletion, physical power-loss durability, migration/backup and
historical executable cutover remain unqualified. Historical bootstrap acquisition
assumptions affected by increment 110 still need review/adaptation and separate
fresh qualification; no NFS experiment is started here.

## Review and workflow

The local coordinator implemented and integrated the foundation. Independent
read-only cloud review of efac4f4..617960a found no actionable findings; the
reviewer ran no SQL, tests or builds. There was no specialist fan-out. Source
was frozen before the two sequential gates, and no source correction or gate
rerun was required. Elapsed delivery time and token/cloud cost were not separately
measured; no percentage quality improvement is claimed.

The next implementation slice is guarded predecessor inspection and a verified
backup. The eventual apply path must still pass transactional crash/failure and
actual predecessor/target recovery qualification before it can be enabled.
All release gates remain open; this increment does not make migration usable.
