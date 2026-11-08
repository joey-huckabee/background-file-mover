# REST contract candidate artifacts

2026-11-01, P01 review work following the
[consolidated proposal](../REST-CONTRACT-PROPOSAL.md). **Not frozen. Not runtime
implementation.** Updated 2026-11-03: groups 1-52 are approved; group 50 changes post-clear ownership, and group 49 selects
the reviewed-state retry header. These files make the schema proposal executable without claiming the unfinished API is ready to ship.

The user subsequently authorized bounded group-50 code: see
[increment 107](../RUST-INCREMENT-107.md) and the
[operator command](../RUST-OPERATOR-GUIDE.md#offline-clear-of-completed-history).
That offline committed-job implementation does not turn this candidate OpenAPI
into an implemented authenticated API or qualify cancelled-job clearing.

Separately authorized [increment 110](../RUST-INCREMENT-110.md) adds guarded
schema-11 compatibility refusal before payload bootstrap/offline clear and
removes historical automatic upgrades. This does not implement the target-schema
migration or any pending producer/admin/session wire behavior.

[Increment 111](../RUST-INCREMENT-111.md) implements the first schema-12
foundation slice for fresh setup and legacy readers/writers. Schema 11 now
returns MigrationRequired; migration apply and UUID/v2 activation remain disabled.
See its exact gate status before treating the foundation as a usable upgrade.

[Increment 112](../RUST-INCREMENT-112.md) adds guarded `--check-state` and
explicit verified `--backup-state` for supported schema 11 or legacy-only 12.
Follow [the offline procedure](../OFFLINE-STATE-BACKUP.md); this does not
implement conversion/apply, qualify physical custody or freeze the REST contract.

## Current scoped closeout (increment 116)

The [producer/manifest engineering contract](PRODUCER-MANIFEST-CONTRACT.md)
finalizes step 1 for the new producer and manifest v2: lexical/size bounds,
immutable identity, replay ordering, exact writer bytes and the next codec/
activation increments. The shared file names retain .candidate because the
other routes and full P01 remain unfrozen. Runtime UUID/v2 is still disabled.
This scoped technical closeout does not relabel all other candidate choices
or claim consumer, ingress or service acceptance.

[Increment 115](../RUST-INCREMENT-115.md) and
[PR 3](https://github.com/joey-huckabee/background-file-mover/pull/3) implemented,
reviewed, qualified and merged the explicit schema-11 to legacy-only schema-12
migration. Both local and PR production/qualification gates passed (240/244 tests
per debug/release profile), and actual predecessor/target pairs passed both
profiles. Normal startup still refuses 11; use the explicit
[offline procedure](../OFFLINE-STATE-MIGRATION.md). Prior increment-111/112
apply-disabled statements above are historical checkpoints, not current status.
This does not authorize operational conversion or qualify arbitrary rollback.

## Artifacts

P01 resumed on 2026-11-03. The [access-boundary candidate](ACCESS-BOUNDARY.candidate.md)
specifies fifteen-route audience separation, proposed Origin/CSRF transport,
inactivity renewal and global-revocation admission ordering. This is engineering
contract work only. Group-51 defaults are approved; the fifteen-route schema
candidate is now supplied. Group 52 approves the five compatibility policies;
the bounded legacy migration is qualified by increment 115; broader mixed-identity/rollback
support and full freeze/implementation remain open.

| File | Purpose and limit |
|---|---|
| [openapi.candidate.json](openapi.candidate.json) | OpenAPI 3.1.1 candidate for all fifteen proposed operations, with request/response schemas and per-response error registry. Not implemented or frozen. Do not generate production clients. |
| [contract.candidate.schema.json](contract.candidate.schema.json) | 70 JSON Schema 2020-12 definitions, including current status/operator/retention shapes and proposed list/confirmation/admin views. Semantic and compatibility limits remain explicit. |
| [contract.candidate.fixtures.json](contract.candidate.fixtures.json) | 108 positive/negative structural cases; 11 also declare separately checked semantic expectations. These are not mover HTTP acceptance runs. |
| [SCHEMA-12-MIGRATION-DESIGN.md](SCHEMA-12-MIGRATION-DESIGN.md) | Historical design; increment 115 implements/qualifies its bounded explicit legacy migration. Broader activation and physical durability remain separate. |
| [SCHEMA-11-UPGRADE.md](SCHEMA-11-UPGRADE.md) | Initial support scope/checklist; current implementation/evidence and operator procedure are increment 115. No arbitrary downgrade or stale restore. |
| [COMPATIBILITY.md](COMPATIBILITY.md) | Approved group-52 legacy/state, manifest, decimal-size, UTF-8 and upgrade/rollback direction, with exact qualification still pending. |
| [ROUTE-SCHEMAS.candidate.md](ROUTE-SCHEMAS.candidate.md) | Read/action wire, bounded confirmation preview, local transport representation, error precedence and unresolved compatibility limits. |
| [check_contract_candidate.py](check_contract_candidate.py) | Read-only metaschema, fixture, reference, route inventory and selected access/error checks; requires existing jsonschema. Not a full OpenAPI validator. |
| [REQUEST-IDENTITY.candidate.md](REQUEST-IDENTITY.candidate.md) | Exact immutable-request framing v1 fixed for the increment-116 producer/manifest slice; no runtime claim. |
| [request-identity-v1.candidate.vectors.json](request-identity-v1.candidate.vectors.json) | Seven input/frame/hash known answers, including unordered replay and distinct Unicode spellings. |
| [RETRY-HEADER.candidate.md](RETRY-HEADER.candidate.md) | Exact proposed header encoding, instance/selection binding, byte bounds and validation precedence; not a contract freeze. |
| [retry-context.candidate.vectors.json](retry-context.candidate.vectors.json) | Four wire known answers, 52 decoding cases and explicit NOT_RUN runtime obligations. |
| [check_retry_context_candidate.py](check_retry_context_candidate.py) | Reproducible standard-library codec checker, no service/SQL/filesystem effects. |
| [ADMIN-REPLAY.candidate.md](ADMIN-REPLAY.candidate.md) | Concrete reviewed-state context recommendation, crash/duplicate/replay obligations and latest-sweep deletion proposal. |
| [api-case-map.candidate.tsv](api-case-map.candidate.tsv) | All 143 existing API acceptance IDs, situations and reviewed outcomes indexed to proposal packages. No case is marked executed by the schema checks. |

The first 128 case-map outcomes are copied from the review tables at ad9fee9;
API-E129 adds group 49 and API-E130-132 add group 50 on 2026-11-02.
API-E133-138 add the explicitly approved group-51 defaults on 2026-11-03.
API-E139-143 add the approved group-52 compatibility direction on that date.
Rows marked SUPERSEDED_POST_CLEAR retain historical outcomes for traceability;
they do not require keeping cleared-file linkage. The case map does
not upgrade a proposed detail into approval; later explicit approval sections
and the original row's scope still govern. Rows with transport/no-HTTP outcomes
stay transport/no-HTTP obligations rather than invented OpenAPI responses.

## What the schemas assert

Required fields, types, unknown-field rejection, UUID spelling, path syntax,
integer bounds, file-list uniqueness and conditional null timing are executable
structural constraints. x-* fields are annotations, not validator assertions.
JSON Schema maxLength counts characters, not UTF-8 bytes. Byte limits, scalar
validity, complete exact map keys, prefix conflicts, numeric job-ID ceiling for
string IDs and persisted custody/replay rules need separate semantic checks.
The semantic fixtures deliberately include structurally valid requests that
must be refused by those additional checks. A JSON Schema pass is not admission.
Duplicate JSON keys must be rejected before object validation; a parsed object
has already lost that evidence. Whole raw request/header bounds belong to the
HTTP parser, not these object schemas.

The producer slice now fixes generator ASCII/source/path limits, optional-map
spelling, producer receipt fields and UUID/manifest spelling. Remaining candidate
choices include login lengths, integer admin selections, cookie name and session
edge responses. Group 52 now approves canonical
decimal-string u64 sizes in the new producer and manifest v2; existing operator
numeric fields, v1 numeric sizes and u128 retention strings remain unchanged.
See [compatibility direction](COMPATIBILITY.md). Producer/manifest bounds and framing are fixed by the scoped contract; runtime,
consumer and broader contract qualification remain separate. No new runtime dependency is
introduced here.

Group 50 removes the proposed post-clear retained-owner inventory route.
Tracked-job views and deletion results exist only before clear; no service file
linkage/accounting or cleanup survives successful clear. Physical disk bytes and
unchanged payload/manifest contents may remain; do not rebuild tracking from them.

The OpenAPI candidate now covers all fifteen proposed operations. Current local
operator envelopes are preserved separately from producer errors; cancellation,
deletion and list/confirmation fields are proposed extensions. Its per-response
`x-error-codes` entries form the candidate route registry. Transport/proxy errors
can lack mover JSON. The external producer scheme and local-only transport
annotations are proposed boundaries, not qualified ingress configuration.
See [route schema limits](ROUTE-SCHEMAS.candidate.md) before using these artifacts.

Start the next review with the [short admin-action closeout table](ADMIN-REPLAY.candidate.md#short-closeout-table).
It separates existing approvals from recommended remaining defaults. Keep user
review on visible behavior; exact fields and transaction mechanics are engineering
work. No further encoding-only fixture expansion is planned before implementation.

## Freeze blockers and recommendations

| Blocker | Recommended next decision/design | Still required before freeze |
|---|---|---|
| F01 Release surface | Use the consolidated 15-route inventory, retaining specialized trusted-local controls and bounded dashboard reads | Review the completed candidate read/action schemas and route access; no unrelated historical routes added |
| F02 Retry intent/replay | Group 49 approves immutable existing review epoch/audit context in a header | Group 51 settles zero-accepted 202 and failed duplicate retry; exact errors, same-transaction receipts and bounded storage/retention implementation remain |
| F03 Clear/delete outcomes | Group 50: clear forgets every source/destination link and result; files leave mover management | Qualify safe-stop/atomic forgetting, restart with unmanaged leftovers and no re-adoption. Group 51 approves one-active/latest-result deletion behavior before clear; candidate wire now supplied; durable storage/transaction design and qualification remain pending. |
| F04 UUID persistence | Group 52 approves preserved legacy custody, supported upgrades or safe refusal, and an explicit upgrade/rollback support list | Increment 115 closes the bounded schema-11 to legacy-only-12 path with actual pairs; UUID ownership/admission, partial-legacy continuation at new-wire activation and the future mixed-identity matrix remain to implement/qualify. No invented UUID or stale restore |
| F05 Consumer manifest | Group 52 approves v2 for new recordings with request digest, decimal-string measured sizes and exact UTF-8; preserve legacy v1 bytes/recovery | Step 1 fixes exact schema/serialization in PRODUCER-MANIFEST-CONTRACT.md. Codecs, immutable-byte persistence/publication/recovery and actual consumer evidence remain; this is not an implementation pass |
| F06 Authentication/ingress | [Access-boundary candidate](ACCESS-BOUNDARY.candidate.md): cookie AND CSRF for mutations, exact Origin, deliberate-read activity and revocation/admission ordering | Validate candidate against full route/error schemas; credential/session bounds, runtime race proof and selected proxy profile remain open |

These blockers are not new approvals or all release gates. They are the remaining
P01 items, with P02/P03 deployment evidence explicitly separate. Group 49 now
settles F02 header transport while preserving the compact body and existing job
identifiers. Its [exact wire candidate](RETRY-HEADER.candidate.md) now has
checked encoding/bounds, with existing instance identity as an explicit proposed
precondition. Complete the remaining outcome/transaction/retention design and
other contract details before bulk retry implementation.

## Verification performed

- Existing WSL Python 3.12.3/jsonschema 4.10.3 checked the Draft 2020-12 schema
  against its metaschema, then the original 57 fixture expectations, including rejected
  shapes, overflow, disabled-comparison immutable maps and duplicate selections.
- Eleven separate semantic fixture expectations checked UTF-8 byte lengths,
  map completeness, prefix conflicts, source trailing slash and job-ID range,
  plus basic manifest membership uniqueness. These are bounded example checks,
  not a complete service validator or proof of custody.
- All seven identity frames were reconstructed separately using integer byte
  conversion. Python hashlib and OpenSSL agreed with every saved SHA-256.
  File permutations/uppercase UUIDs matched, while map/Unicode changes differed.
- Windows Python 3.12.10 ran the reference codec checker: four known answers,
  52 decoding cases, including exact large integers, malformed/duplicate fields,
  null/duplicate epochs, wrong instance and encoding/aggregate limits. Widest
  canonical payload/value are 4018/5361 bytes. Node independently matched all
  four selection frames, SHA-256 values and JSON/base64url headers using BigInt
  and the saved decimal-string IDs. These checks do not exercise real HTTP,
  authentication, SQLite scheduling, later-review replay or physical effects.
- JSON parsing, local references, stable API/SC IDs, trace-row coverage and diff
  whitespace were checked. OpenAPI reference consistency was checked; a full
  OpenAPI validator/client generator and live HTTP tests were not run.

The reproducible codec command is `python docs/api/check_retry_context_candidate.py`.
The original seven request-identity vectors and eleven semantic examples retain
their earlier checks; these are separate from the new retry wire checks.

Validation used the existing installed tools and artifact bytes; no install,
Rust build/test, service start, SQLite migration or NFS/delete qualification was
performed. Required SLES modes remain mandatory for future Rust changes. All
eight release gates remain open; production NFS and source deletion remain off.

Schema syntax follows the primary [JSON Schema 2020-12 validation specification](https://json-schema.org/draft/2020-12/json-schema-validation)
and [OpenAPI 3.1.1 specification](https://spec.openapis.org/oas/v3.1.1.html).
These references explain document syntax; they do not approve product behavior.

### P01 access-boundary work, 2026-11-03

The local coordinator drafted the boundary and OpenAPI metadata; the existing
cloud reviewer independently audited the baseline and the new diff. Review
caught one browser-compatibility defect before implementation: mandatory Origin
on same-origin GET activity. The candidate now requires session-bound CSRF for
marked reads, checks supplied Origin/Fetch-Metadata and configured target
authority, and keeps strict Origin for POST actions. No new agent or heavy
build was needed. Token/cloud cost was not measured.

JSON/reference/security-AND checks and all 57 existing structural schema fixtures
pass; this is not a complete OpenAPI-validator, browser, authenticated HTTP or
transaction-race test. Group 51 now approves the specific retry/deletion defaults; cancellation
transport application and broader candidate compatibility/security choices remain
separate. The inventory is now 138 API and 189 SC IDs; earlier IDs are preserved.

### Schema completion checks (2026-11-03)

`python3 docs/api/check_contract_candidate.py` passed in Ubuntu WSL2 with the
existing jsonschema package: 66 definitions, 93 structural fixtures, fifteen
operations and reference/access/error checks. The 36 added cases cover current
legacy/UUID status branches, null measurements, u128 retention strings, audit
and local operator shapes, confirmation completeness and asynchronous counts.
These are structural examples, not service acceptance or full OpenAPI conformance.
No Rust source, runtime, operational state or production setting changed.

### Compatibility approval update (2026-11-03)

Group 52 changes the new producer/v2 size type to `DecimalByteCount` and adds
separate legacy-v1 schemas. The fixture set now has 108 cases and 69 definitions.
The fifteen existing routes remain unchanged. Existing request-identity vectors
use string sizes on input but retain all seven original frames/digests: framing
encodes parsed u64 values, not JSON spelling. The maintained checker covers this
representation boundary without adding another encoding-only fixture set.
The approved policies do not close P01 or declare a supported migration/rollback
matrix; see [compatibility limits](COMPATIBILITY.md).

Validation for this update passed in Ubuntu WSL2: 69 definitions, 108 structural
fixtures, fifteen route operations/reference/access checks, and all seven
existing request-identity frames/hashes with decimal-string input sizes.
Catalog checks found 143 unique API rows, 194 unique SC rows and 143 case-map
entries. No Rust build, migration, service HTTP or consumer qualification ran.

### Producer/manifest engineering closeout (increment 116)

Step 1 fixes the producer slice without freezing the other fourteen operations.
The existing 108 structural cases and eleven semantic examples are checked;
all seven original identity frames/hashes remain unchanged. The existing manifest
fixture supplies one exact 766-byte writer golden and its SHA-256. A conservative
106673-byte maximum proves the 65536-byte request/256-file bound fits the existing
131072-byte manifest limit with the selected compact UTF-8 serialization.
No new vector collection, Rust implementation, HTTP service or consumer acceptance
run is claimed. See [increment 116](../RUST-INCREMENT-116.md) for actual review/checks.
