# Increment 110: compatibility refusal before payload bootstrap

Authorized 2026-11-04 after approval of [migration planning step 1](api/SCHEMA-11-UPGRADE.md).
This implements only early compatibility checks. Schema remains 11; there is no
schema-12 migration, UUID producer, manifest v2, repair or deployment change.

## Behavior

Daemon startup, `--initialize-source`, `--transfer-one` and offline history clear
now acquire the existing
InstanceGuard, validate database/recovery-file locality and identity, register
their process-group lifetime, and inspect compatible local state before starting
source bootstrap. Guard/lifetime ownership continues through normal SQLite
closure. The daemon keeps its independent local control server available during
inspection; a refusal drops that server and removes its socket. Existing `--status` and `--stop` remain independent of SQLite and payload
storage so an operator can observe/stop an already-running owner.

Existing database inspection uses a no-CREATE read-only connection, requires
application ID 0x42464d52, current schema 11 and original WAL mode, checks existing
job reconstruction/foreign keys, compares supported DDL (whitespace differences
allowed) and runs SQLite integrity_check. Unexpected triggers/views/indexes,
changed constraints, missing required tables, corrupt state and foreign/newer
formats refuse. This is deliberately conservative support for the declared DDL,
not a general SQLite equivalence checker. Normal Store open also refuses schemas
1-10 instead of automatically migrating them. Historical migration tests are
replaced by refusal/preservation checks using the retained historical fixtures.

Only explicit `--initialize-source` permits absent or zero-byte state to proceed
to the existing guarded bootstrap/setup flow. A zero-byte file with recovery
sidecars refuses. Inspection never initializes a database; source/enrollment
safety checks still govern actual setup. Normal startup/transfer refuses missing
state rather than creating replacement state. Preserve original state on refusal.

Read-only refers to job data. Existing guard/lifetime files are written and
SQLite may use local shared-memory coordination. No source/destination probes,
payload moves/deletes, adoption or enrollment repair are part of compatibility
inspection. This local check does not prove NFS RPC settlement.

## Checks and evidence

New Store cases cover missing/empty initialization boundaries, all historical
versions, unknown/newer versions, foreign application ID, corrupt input and
modified schema. Historical populated fixtures assert byte-preserving refusal;
the schema-10 fixture retains all populated table comparisons. A CLI case checks
all four effect entry points against versions 1-10, 12/99, foreign and corrupt
state with source unavailable, unchanged database bytes, no enrollment receipt
and no control socket. Existing guard/orphan, original-WAL restart, enrollment,
transfer and offline-clear tests remain required regression coverage.

Validation status: **PENDING**. Both cargo-libc/SLES production and qualification
gates must validate the final changed Rust inputs. No host-only Cargo tests,
production NFS, target-schema migration or incompatible historical executable
qualification is claimed. Exact gate results will be recorded before closeout.


The initial final-source production run `20261105T032748Z-b6e652e8` failed its
new corrupt-database CLI diagnostic assertion in debug (87 API tests passed,
one failed). The CLI refused correctly, but Rust's main-result Debug formatting
used `Sqlite(...)` while daemon startup used Display `SQLite: ...`. The regression
now checks the shared underlying `file is not a database` diagnostic; refusal,
unchanged database bytes, no enrollment and socket cleanup assertions remain.
This failed report is retained; fresh gates must validate the corrected test.
Earlier runs `20261105T031907Z-6c15fd3a` and `20261105T032541Z-a6cfac7b` were
intentionally interrupted after source changes and are not acceptance results.
