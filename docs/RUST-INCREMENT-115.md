# Guarded explicit schema migration

2026-11-07. The user authorizes implementation of the guarded schema-11 to
schema-12 migration recommended after the source cleanup. Base:
`a85f39ebfac9928a10d670d6004bbf6ace8b5e8c`.

## Change

Add --migrate-state CONFIG --backup-dir NEW_ABSOLUTE_DIRECTORY [--confirm].
Preview validates supported state and lexical/local backup placement without
creating output. Confirmed schema 11 requires a freshly verified durable backup
under the same instance/lifetime exclusion, then rebuilds jobs in one transaction.
Known legacy-only 12 is a validated no-op. Unsupported state refuses. Normal
startup never migrates. No payload roots, service workers, HTTP startup or
source enrollment are acquired by this maintenance command.

The private FK-disabled connection uses static packaged DDL, copies all thirteen
original columns with identity_kind=0 and NULL UUID/digest fields, drops the old
parent without renaming it, renames the replacement and creates canonical partial
indexes. It restores the exact sequence, validates DDL/integrity/FKs/readers and
streams exact typed original/dependent/shared rows against the backup before
committing user_version=12. All errors unwind connections before guard release;
postcommit errors require inspection, never automatic restore.

Existing backup receipt version 1 remains a record of the backup step, which
itself does not apply migration. No migration-history table or permanent ownership
linkage is added. Clear semantics, legacy v1 bytes, prototype admission, namespace
and sequence rules remain unchanged. UUID admission and manifest v2 stay disabled.

## Verification

Pending: independent review and fresh production/qualification cargo-libc/SLES
gates for this source. No build/test result is claimed yet.

Added coverage includes full dependent-table/audit/manifest-phase preservation,
exact replay after reopening, empty and cleared sequence history, each precommit
rollback checkpoint, postcommit-error inspection, changed source/backup refusal,
actual CLI preview/apply/no-op without payload roots, backup fault refusal,
production inert fault controls, live/orphan exclusion and qualification process
kills at every rebuild boundary. These tests operate only on disposable fixtures.

Actual predecessor executable refusal, full deployment/NFS qualification and
hardware power-loss durability remain separate evidence requirements. No
operational database has been converted; no deployment or release is authorized.

## Team workflow

Coordinator owns implementation/integration and the single local SLES build queue.
Existing cloud reviewer receives a bounded read-only diff after commit. Review
findings and exact gate results will be recorded before integration. Costs are
unknown; no percentage improvement is claimed.

Operator instructions: [offline migration](OFFLINE-STATE-MIGRATION.md).
