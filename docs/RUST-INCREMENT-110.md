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

Earlier NFS bootstrap evidence measured source access before SQLite opened. That
ordering intentionally changes here: supported existing state is now inspected
first. Historical frozen-state/no-SQLite assertions are not fresh evidence for
this binary. Fresh-daemon bootstrap acquisitions must also account for the new
missing-state refusal and explicit initialization path. Existing NFS fixture
capabilities/reports are retained; their affected acquisition assumptions need
review/adaptation and fresh qualification before claiming those scopes again.
No additional NFS experiment is started by this increment.

## Checks and evidence

New Store cases cover missing/empty initialization boundaries, all historical
versions, unknown/newer versions, foreign application ID, corrupt input and
modified schema. Historical populated fixtures assert byte-preserving refusal;
the schema-10 fixture retains all populated table comparisons. A CLI case checks
all four effect entry points against versions 1-10, 12/99, foreign and corrupt
state with source unavailable, unchanged database bytes, no enrollment receipt
and no control socket. Existing guard/orphan, original-WAL restart, enrollment,
transfer and offline-clear tests passed as regression coverage.

Validation status: **PASSED for this bounded increment**. Validated source:
`2a31f233982669a8821bee42bf9691b27c1f39e7`. The [evidence inventory](COMPATIBILITY-PREFLIGHT-EVIDENCE.json)
records source hashes, report/archive hashes, actual results and retained failures.

| Mode | Run | Debug passed | Release passed |
|---|---|---:|---:|
| Production, strict offline | `20261105T033804Z-7c6fa900` | 221 | 221 |
| Qualification, strict offline | `20261105T040737Z-9c980f8e-nfs-qualification` | 223 | 223 |

Both modes passed formatting, Clippy, cargo-libc GNU/glibc-2.22 inspection,
independent ELF audits with six negative controls, eager relocation and actual
pinned SLES 12 SP5 tests. Each profile retains five existing ignored opt-in cases;
no ignored attribute was added or changed here. Both builder/runtime networks
were disabled, and cleanup completed without error.

Independent local verification matched all 63 files in both archived source
snapshots to the committed Git blobs and rehashed all 40 retained executables.
All 11 persisted-schema SQL inputs are unchanged from predecessor reference
`7c66223`. Raw packs remain under
`/home/joey/GIT/background-file-mover-testing/rust/validation/`, outside Git.
No host-only Cargo tests, production NFS, target-schema migration or incompatible
historical executable qualification is claimed. All release gates remain open.

Production run `20261105T032748Z-b6e652e8` at `235e0a8` failed its new
corrupt-database CLI diagnostic assertion in debug (87 API tests passed,
one failed). The CLI refused correctly, but Rust's main-result Debug formatting
used `Sqlite(...)` while daemon startup used Display `SQLite: ...`. The regression
now checks the shared underlying `file is not a database` diagnostic; refusal,
unchanged database bytes, no enrollment and socket cleanup assertions remain.
This failed report is retained; both passing runs above validate the corrected test.
Earlier runs `20261105T031907Z-6c15fd3a` and `20261105T032541Z-a6cfac7b` were
intentionally interrupted after source changes and are not acceptance results.

## Independent review and workflow

The local coordinator implemented/integrated the change; existing cloud child
`thr_xnjapdndei` reviewed it read-only in bounded passes. Review caught one DDL
filter defect: LIKE's underscore wildcard hid a legal sqliteX-prefixed trigger.
Literal-prefix GLOB filtering and the concrete trigger regression fixed it;
subsequent control/sidecar/source-test and offline-clear deltas had no actionable
findings. The final change after those passes is the diagnostic assertion
correction described above. The reviewer ran no builds/tests and supplied no
runtime qualification. There was no specialist fan-out.

Two superseded runs were interrupted and one new diagnostic assertion required
correction before fresh validation. Exact reports are retained rather than
relabelled as passing. Elapsed delivery time and token/cloud cost were not
separately measured; no percentage quality improvement is claimed.
