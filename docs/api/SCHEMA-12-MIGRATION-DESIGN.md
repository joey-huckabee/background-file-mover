# Transactional schema-11 to schema-12 migration design

2026-11-04. User authorization: start migration design after increment 110.
**Design only: no runtime schema change, migration command, backup operation or
new producer/manifest implementation is authorized or executed here.** Schema 12
is the proposed next version. Groups 1-52 and the
[schema-11 support scope](SCHEMA-11-UPGRADE.md) govern preservation/refusal.
The exact SQL and implementation below are engineering recommendations for
review; this is not P01 freeze or a supported upgrade claim.

## Recommendation and scope

Rebuild only `jobs` in one SQLite transaction to replace its unconditional legacy
unique constraint with two disjoint identity namespaces. Preserve the ten
per-job dependent tables and all shared tables in place. Keep job IDs and their
high-water mark; preserve every original column value, file index, custody,
receipt, path and immutable v1 manifest. No payload root is opened.

A side table alone does not solve the old NOT NULL/UNIQUE constraint: storing a
UUID in submission_id could collide with a UUID-looking legacy value. Avoid
fabricated legacy strings, reserved prefixes, synthetic public identifiers or
UUIDs assigned to existing jobs. Rebuilding jobs removes that constraint
explicitly while keeping its authoritative job_id.

The first implementation must pair the upgrader with schema-12-aware legacy
readers/writers and v1 recovery before permitting conversion. New UUID admission,
UUID destination allocation, manifest v2 and producer wire replacement remain
separate gated work. Dormant UUID columns are not permission to insert such jobs.
Existing prototype admission remains legacy until its separately authorized
replacement; no old/new wire adapter is introduced by migration.

## Reference state and support

Schema 11 uses application ID 0x42464d52. Reference format source remains
`7c662239f00bd0ad87ec31bf82d553fc2663963d`. Increment 110's qualified Rust source
is `2a31f233982669a8821bee42bf9691b27c1f39e7`; `4968ee8` has the same Rust tree.
Its [evidence](../COMPATIBILITY-PREFLIGHT-EVIDENCE.json) establishes unchanged
schema SQL and early refusal checks, not a schema-12 upgrade qualification.
Use exact retained executable hashes when selecting the predecessor test binary.
The older offline bundle is not automatically the same executable.

Only validated schema 11 converts. A valid schema 12 supported by the tool's
reader is a no-op after validation. Schema 1-10, unknown/newer/foreign/corrupt
state and absent/empty state refuse this command. New-binary normal startup must
report that schema 11 requires explicit migration, without auto-conversion or
payload bootstrap. Fresh explicit initialization creates schema 12 only after
its existing unused-scope authorization. No source re-enrollment is performed.

## Concrete target layout

[Candidate jobs DDL](migrations/schema-12-jobs.candidate.sql) is a review artifact
outside rust/. Its executable content creates only the temporary replacement;
commented cutover statements are not a complete safe migration script.

| Field / index | Proposed meaning |
|---|---|
| Original job_id and all original common columns | Same names, types and values. submission_id becomes nullable only to represent the other identity kind. |
| identity_kind = 0 | Legacy: submission_id is TEXT; UUID and request-digest fields are NULL. Never reinterpret UUID-looking legacy text. |
| identity_kind = 1 | UUID: submission_id is NULL; recording_uuid is a 16-byte BLOB and request digest is a 32-byte SHA-256 BLOB with version 1. |
| jobs_legacy_identity | Partial UNIQUE(generator_id COLLATE BINARY, submission_id COLLATE BINARY) WHERE identity_kind=0. Preserves original byte/case equality. |
| jobs_uuid_identity | Partial UNIQUE(recording_uuid) WHERE identity_kind=1. Global across generators. |

No default identity_kind: every insertion must choose a branch explicitly.
SQL CHECKs enforce branch exclusivity, BLOB lengths and explicit non-NULL version;
NULL must not let a CHECK pass through SQL's three-valued logic. Application
validation still proves UUID parsing, exact immutable assertions and digest
correctness. BLOB UUID bytes are the 16 bytes obtained by parsing the existing
32 hexadecimal digits in order, not platform/GUID mixed-endian bytes. Do not add
a UUID version/variant restriction beyond the agreed lexical contract. Wire
case is canonicalized only for UUID identity; filenames remain exact.

The digest representation/version follows the existing
[request-identity candidate](REQUEST-IDENTITY.candidate.md). Its precise framing
remains a freeze dependency before UUID admission; this design does not approve
that algorithm. No digest is invented for legacy jobs. New UUID replay must
compare saved immutable assertions as well as validate the digest, rather than
use hash equality alone to authorize handoff or changed content.

Do not add another expected-size representation or per-job size policy. Existing
files.expected_size stays TEXT/NULL with every legacy byte preserved. A legacy
mixed expected-size list stays legacy; do not infer a complete new-contract map
or rewrite it. Future UUID jobs require the approved complete-map/all-absent
invariant across files; with a nonempty file set that identifies presence without
a redundant flag. Compare files by exact path for new replay while preserving
original file_index and claim numbering.

Manifest protocol is derived from persisted identity_kind: legacy -> v1,
UUID -> v2. There is no mutable startup setting or redundant manifest-version
column. Legacy jobs completing after upgrade stay v1. Existing manifests table,
serialized bytes, hashes/phases and objects remain unchanged. An existing v1
receipt on a UUID job, or v2 on legacy, is inconsistent state, not permission to
rewrite it. Future readers must recognize both supported protocols before UUID
jobs can be admitted. Unknown kind/digest version or unsupported identity
capability refuses the whole startup before payload access, even on schema 12.

## Owner, backup and validation phases

The proposed host-local interface is `--migrate-state CONFIG.json --backup-dir
ABSOLUTE_NEW_DIRECTORY --confirm`, with a separate guarded `--check-state
CONFIG.json` inspection. **Neither command exists.** A migration without confirm
reports eligibility and required backup location without converting. Normal
startup never calls apply implicitly. Preview/preflight may write normal local
guard/lifetime metadata but not job data. Configuration checking remains lexical;
missing/unavailable payload roots must not block this database-only operation.

1. Acquire InstanceGuard and independent epoch admission, then register this
   process lifetime before any SQLite connection. Retain them until all source,
   backup and validation connections/owner threads have closed. Never replace
   epoch/lock files, adopt workers or infer remote settlement from a free flock.
2. Open existing source without CREATE or URI interpretation, preserving existing
   WAL mode and sidecars; require the known schema-11 DDL and pinned SQLite
   configuration. Reject unknown triggers/views/indexes, including sqliteX names;
   only literal internal sqlite_ names are filtered. Reconstruct every job,
   validate SQLite integrity/FKs, shared instance/enrollment/ownership and sequence
   consistency without storage probes. Supported pending enrollment/review stays
   pending/refused; missing evidence is not synthesized. Finalize shared-state
   validation against the current enrollment receipt types, not new inference.
3. Reserve a new private local backup directory (0700), refuse overlap with the
   live state directory or any source/destination namespace, and create its
   output file exclusively (0600). Reuse existing local-parent/mount/owner safety
   primitives; do not probe payload roots merely to classify the backup path.
   Paths must be configured as protected local storage and lexically disjoint.
4. Proposed copy mechanism: `VACUUM main INTO ?1` with a bound literal absolute
   output path, from a source connection with synchronous=FULL, outside an SQL
   transaction and with all statements finalized. The file must be the newly
   created empty file, never arbitrary existing contents. Verify descriptor/name
   identity before and after; do not enable URI mode. Include committed WAL data
   through SQLite, not raw main-file copying. No new dependency or rusqlite
   optional feature is required for this SQL choice.
5. Close the backup writer, validate the snapshot read-only using a dedicated
   snapshot validator, compare all declared-key logical rows and sequence values
   against the guarded source, then hash it and sync file/directory/parent entries.
   VACUUM may change physical rowids of tables without INTEGER PRIMARY KEY;
   those are not durable mover IDs. Compare composite keys, never physical-row
   order. A snapshot's journal mode may differ; do not force it through the live
   WAL-only Store opener or modify it merely to make that opener accept it.
6. Write/sync a private completion receipt containing snapshot hash, instance ID,
   schema/application IDs and tool identity. An interrupted backup without a
   verified receipt is incomplete. Preserve it for diagnosis; a retry uses a new
   directory. Any backup/validation/sync/space failure stops before conversion.
   Space estimates must cover backup, replacement table and WAL growth but cannot
   promise writes will succeed. No source/destination capacity probe is involved.

Backups are explicit operator recovery artifacts, not a new live ownership
inventory. Keep their paths/job contents out of the operational database and
never discover or restore them automatically. They contain historical state;
operators must protect and retire them separately. Clear still forgets all live
job linkage, and does not promise secure erasure of separately held backups or
old physical database pages. No permanent detailed migration-history table is
introduced.

[SQLite's VACUUM INTO documentation](https://www.sqlite.org/lang_vacuum.html)
describes consistent snapshot output and synchronization under NORMAL/FULL.
Pinned SQLite 3.53.2 behavior, read-only-source execution, file identity and
failure handling still need exact-target proof; these are not results of the
increment-110 gates.

## Transactional conversion

Use a dedicated maintenance connection that is never exposed to service work.
Keep trusted_schema OFF, writable_schema OFF and legacy_alter_table OFF. Source
SQL is static, packaged SQL; never execute arbitrary sqlite_schema contents.
The supported predecessor has no custom trigger/view objects to preserve.

The rebuild ordering follows [SQLite's generalized ALTER TABLE procedure](https://www.sqlite.org/lang_altertable.html#making_other_kinds_of_table_schema_changes).
Disable FK enforcement only on this private connection before BEGIN, build a
replacement, copy rows, drop the old table, rename the replacement, check FKs
before commit and re-enable enforcement afterward. Renaming the original parent
first can retarget child references and is specifically excluded.

Detailed application sequence:

1. Capture all original jobs columns, every other table keyed by its declared
   primary key, DDL definitions, instance data and sqlite_sequence values for
   before/after comparison. Bound memory or stream the comparison for large
   retained histories; counts/hashes alone do not replace exact evidence checks.
   Require positive job IDs and consistent AUTOINCREMENT state. For jobs with
   rows require one integer jobs sequence >= max(job_id), within i64. Zero jobs
   may have no sequence (never allocated) or a retained sequence after clear.
2. On the dedicated connection, set foreign_keys=OFF and verify it while outside
   any transaction; BEGIN IMMEDIATE. Revalidate source schema/data under this
   transaction and exclusive instance ownership before executing transformation.
   The earlier backup remains consistent because no cooperative writer can run
   between backup and conversion. Do not share this FK-disabled handle.
3. Execute the candidate CREATE TABLE jobs_v12; refuse any preexisting staging
   object. Copy the 13 original columns by explicit name, including original
   job_id, with identity_kind=0 and the other three new fields NULL. Do not use
   SELECT *, INSERT OR REPLACE, new ID allocation or reserialized core records.
4. DROP TABLE jobs, then ALTER TABLE jobs_v12 RENAME TO jobs. Do not rename the
   old jobs table. The files/operator/etc. foreign keys keep referencing jobs;
   dependent table data is never deleted, recopied or cascaded.
5. Create the two named partial unique indexes shown by the candidate. The old
   automatic legacy unique index disappears with the original table. Check that
   all non-jobs DDL is unchanged and every FK still targets its original parent,
   with no jobs_v12 references or leftover staging objects.
6. Restore the exact captured jobs high-water mark in sqlite_sequence. Rebuild
   may otherwise reset it to max(remaining jobs), losing IDs of cleared jobs.
   Delete only jobs/jobs_v12 sequence entries and insert the original jobs value
   if one existed. Preserve absence when originally empty/unallocated; preserve
   every other sequence entry. Never lower a sequence or search payloads for IDs.
7. Reconstruct all target jobs with the schema-12 reader using THIS connection,
   so validation sees the uncommitted target. Confirm every legacy identity,
   phase, audit result, original column and dependent row against the source
   capture. Validate shared state, exact sequence, target DDL, integrity_check and
   foreign_key_check, including while enforcement is disabled. Any mismatch
   rolls back; a separate connection cannot validate uncommitted conversion.
8. Set user_version=12 in the same transaction, leaving application_id unchanged;
   verify target version-dependent invariants and COMMIT with synchronous=FULL.
   Never commit the version before validating the transformation. No new work
   is admitted before commit/durability success is established.
9. Restore foreign_keys=ON outside the transaction, verify ON and close the
   maintenance owner before releasing InstanceGuard. On any precommit error,
   roll back, restore enforcement or close the handle, and preserve original
   authority. A postcommit error means inspection/forward recovery, not undo.

Fresh schema-12 creation must yield the same canonical DDL as migration. The
current validator compares SQL after whitespace normalization; ALTER RENAME can
quote the final jobs name. Use the same jobs_v12-create/rename/index recipe for
fresh creation before adding its child tables, or qualify an explicit canonical
schema representation. Do not blindly compare migrated SQL to an independently
spelled CREATE TABLE jobs and weaken validation when it differs.

## Runtime integration required before enabling apply

| Area | Required change / boundary |
|---|---|
| Compatibility and Store open | Explicit operation-specific schema 11/12 validation; normal target startup requires 12. No historical chain or automatic conversion. Fresh and migrated target DDL match. |
| load/status/retention | Read a typed Legacy versus UUID identity; preserve original job/file IDs and current operator numeric formats. Never map UUID into legacy submission_id. All callers must handle their supported kinds or refuse early. |
| accept_guarded and accepted replay/admission reads | Update BOTH current lookup paths to discriminate legacy kind; later UUID lookup is global by blob, then exact generator/assertion comparison. Same UUID across generators conflicts. |
| Legacy writer during prototype transition | Explicitly insert kind=0; retain legacy assertions. Replacing the producer wire later removes old-wire admission without adding an adapter. |
| Claims/transfers/destination allocation | Existing legacy custody, job-ID paths and receipts stay unchanged. Later UUID route generation must branch on durable identity before any new UUID is accepted; never recompute legacy paths from UUID text. |
| Manifest generator and worker protocol | Legacy recovery stays v1 with exact saved bytes. Later v2 generation/parsing must use measured evidence and request identity, versioned worker messages and immutable serialization. |
| History clear | Identity/UUID/digest live in jobs, so existing child-first clear removes them with that row. No new child receipt table, tombstone or retained ownership appears. Preserve sequence. |
| Lifecycle/control | Status/stop remain independent of SQLite; maintenance does not bootstrap source, HTTP or workers. Hold lifetime/guard through every owner close. |

A schema-12 legacy-capable binary may not silently skip UUID rows it cannot
interpret. Add a whole-state capability check before effects until the complete
dual-format reader is qualified. Version number alone is insufficient. All
code paths using load, Submission::submission_id, positional INSERTs or row
column order need an explicit audit; no half-upgrade may be shipped.

## Interruption and rollback outcomes

| Interruption | Required outcome |
|---|---|
| Before verified backup / before BEGIN | Original schema 11 remains authoritative. Partial backup is not usable. |
| After copy, DROP, rename, sequence restore or validation, before commit | SQLite rollback/recovery yields the original schema 11 with all original logical rows and sequence. Do not restore a snapshot automatically. |
| During COMMIT or sync with uncertain result | Keep original state files, guard/epoch and diagnostics; reopen under exclusion to identify a valid 11 or 12. Never infer that an error means no commit. |
| After committed 12, before success response | Repeating migration validates supported 12 and reports no conversion. Start only a capable target binary with original state/config/enrollment. |
| Re-enabling FK or postcommit inspection fails | Report committed-or-uncertain failure and require guarded inspection; no false rollback claim or automatic downgrade. |
| Operator attempts older software / backup restore | Known early-check predecessor should refuse 12 before payload bootstrap, tested against actual output. Older binaries lacking the check require the still-unqualified installation launch boundary. No stale restore over progressed custody. |

No reverse migration is proposed. The backup is diagnostic/recovery evidence,
not a general license to overwrite the live database. State alone cannot prove
that a stale/cloned snapshot represents current custody; retain existing
same-host/account/namespace assumptions and the stronger deferred fencing rules.

## Acceptance mapping and implementation order

These extend the existing MIG-01-13 cases; none has been executed for migration.

| Cases | Concrete proof required |
|---|---|
| MIG-01/02/13 | Before/after exact-key row comparison for all tables, mixed phases, unrelated jobs, enrollment pending/review and old unmanaged leftovers; target startup/recovery preserves files and v1 bytes. |
| MIG-01 | Clear highest ID and then all IDs; preserve high-water mark and allocate strictly larger IDs. Also cover never-allocated empty sequence. |
| MIG-03 | UUID-looking legacy strings remain kind 0. Target constraint tests permit the same textual UUID in distinct namespaces, reject duplicate global UUIDs across generators, wrong BLOB lengths/types, NULL version and mixed branch fields. New HTTP admission remains NOT_RUN. |
| MIG-04 | Legacy manifest phases 0-4 and unfinished jobs continue v1; no serialized-byte rewrite, rehash substitution or manufactured UUID/digest. |
| MIG-05/06/08 | Every refusal/no-op row from the support matrix; extra legal sqliteX trigger, altered CHECK/index, malformed sequence/shared state and unsupported same-schema identity capability. |
| MIG-07/11 | Existing daemon/guard and separately exited coordinator's surviving child exclude before SQLite; unavailable source/destination roots do not prevent a valid offline conversion. |
| MIG-09 | Process kill and injected failures at create/copy/drop/rename/index/sequence/validation/version/commit and postcommit boundaries; repeat actual reopen checks. Rollback must restore child FK targets as well as rows. |
| MIG-10 | Backup of committed WAL content, unknown output path/refusal, no-clobber, interruption/ENOSPC/I/O/sync failures; validate snapshot and original preservation. Test VACUUM INTO on the exact bundled SQLite and safe output descriptors. |
| MIG-12 | Exact old/new executable pairs using actual migrated state, not a header-only fixture; known predecessor early refusal and target original-state recovery. Older bundle launch boundary remains separate. |

Recommended increments after implementation authorization:

1. Target schema/readers plus candidate-DDL/sequence/namespace tests, with apply
   disabled until legacy reconstruction and fresh-vs-migrated DDL agree.
2. Guarded inspection and verified backup, with fault/refusal tests and no
   conversion on any incomplete backup. No new dependency is needed by design.
3. One-transaction conversion, failure checkpoints, guarded CLI and actual
   predecessor/target recovery tests; enable apply only when the whole path works.
4. Final independent review, both pinned cargo-libc/SLES gates and exact artifact
   evidence. Keep all failed reports. Broader NFS/bootstrap acquisition updates,
   actual deployment and remote settlement remain separately qualified work.

Design verification status: source/document audit only. The SQL artifact is not
included in Rust or executed on a database. No Rust builds/tests, SQL execution,
backup, installs, state copies or migration qualification were run for this
planning task. Existing increment-110 passes validate its source only.


Independent cloud review of `4968ee8..887f431` found no actionable findings.
The reviewer checked source, documents and SQLite guidance only; it executed no
SQL, builds or state operations. Local checks passed document-link resolution,
coverage of all MIG-01-13 dispositions and absence of Rust source changes.
These checks establish reviewability, not execution correctness or qualification.
