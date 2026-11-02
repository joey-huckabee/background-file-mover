# REST contract candidate artifacts

2026-11-01, P01 review work following the
[consolidated proposal](../REST-CONTRACT-PROPOSAL.md). **Not frozen. Not runtime
implementation.** Updated 2026-11-02: groups 1-49 are approved; group 49 selects
the reviewed-state retry header. These files make the schema proposal executable without claiming the unfinished API is ready to ship.

## Artifacts

| File | Purpose and limit |
|---|---|
| [openapi.candidate.json](openapi.candidate.json) | Partial OpenAPI 3.1.1 producer, three session operations and admin retry; route/read/action completion and security details remain blockers. Do not generate production clients. |
| [contract.candidate.schema.json](contract.candidate.schema.json) | 25 proposed JSON Schema 2020-12 definitions for producer, session, selections/counts and manifest v2. Route-specific code/precedence remains separate. |
| [contract.candidate.fixtures.json](contract.candidate.fixtures.json) | 57 positive/negative structural cases; 11 also declare separately checked semantic expectations. These are not mover HTTP acceptance runs. |
| [REQUEST-IDENTITY.candidate.md](REQUEST-IDENTITY.candidate.md) | Exact proposed immutable-request framing and compatibility limits. |
| [request-identity-v1.candidate.vectors.json](request-identity-v1.candidate.vectors.json) | Seven input/frame/hash known answers, including unordered replay and distinct Unicode spellings. |
| [RETRY-HEADER.candidate.md](RETRY-HEADER.candidate.md) | Exact proposed header encoding, instance/selection binding, byte bounds and validation precedence; not a contract freeze. |
| [retry-context.candidate.vectors.json](retry-context.candidate.vectors.json) | Four wire known answers, 52 decoding cases and explicit NOT_RUN runtime obligations. |
| [check_retry_context_candidate.py](check_retry_context_candidate.py) | Reproducible standard-library codec checker, no service/SQL/filesystem effects. |
| [ADMIN-REPLAY.candidate.md](ADMIN-REPLAY.candidate.md) | Concrete reviewed-state context recommendation, crash/duplicate/replay obligations and latest-sweep deletion proposal. |
| [api-case-map.candidate.tsv](api-case-map.candidate.tsv) | All 129 existing API acceptance IDs, situations and reviewed outcomes indexed to proposal packages. No case is marked executed by the schema checks. |

The first 128 case-map outcomes are copied from the review tables at ad9fee9;
API-E129 adds the approved group-49 outcome on 2026-11-02. It does
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

Candidate choices remain choices: generator ASCII profile, source/path limits,
login lengths, integer job selection, optional-map spelling, producer receipt
fields, cookie name and session edge responses. Manifest v2 currently retains
u64 JSON numeric sizes as a compatibility proposal. Clients must parse those
integers losslessly; ordinary binary64 JSON parsing can round values above
2^53-1. Exact decimal-string sizes remain an alternative requiring a deliberate
schema/consumer decision. No new runtime dependency is introduced here.

The partial OpenAPI file now includes the retry header parameter and its
decoded/read-projection schemas. It does not enumerate every error or complete authentication
and CSRF protection. Its default producer error response describes mover-generated
JSON only; it does not promise that proxy errors or TLS failures have that body.
The external producer security scheme is a proposed boundary, not deployment
configuration or proof of protected ingress. Listing/status/retained-data and
specialized operator schemas remain to finish under the route inventory.

Start the next review with the [short admin-action closeout table](ADMIN-REPLAY.candidate.md#short-closeout-table).
It separates existing approvals from recommended remaining defaults. Keep user
review on visible behavior; exact fields and transaction mechanics are engineering
work. No further encoding-only fixture expansion is planned before implementation.

## Freeze blockers and recommendations

| Blocker | Recommended next decision/design | Still required before freeze |
|---|---|---|
| F01 Release surface | Use the consolidated 16-route inventory, retaining specialized trusted-local controls and bounded dashboard reads | Review exact read schemas and route access; do not inherit unrelated historical routes |
| F02 Retry intent/replay | Group 49 approves immutable existing review epoch/audit context in a header | Concrete header encoding/bounds candidate supplied and checked; exact error/duplicate/zero-accepted outcomes, same-transaction receipts and bounded retention remain |
| F03 Clear/delete outcomes | Retain ownership by old job_id; one active deletion sweep and latest-sweep summary | Confirm stale selection, request replay, partial failure and summary lifetime; keep actual files protected |
| F04 UUID persistence | Explicit state-preserving migration or safe refusal; no rekey/relocation of legacy custody | Exact supported old-state schema matrix and upgrade/rollback design; collision response for cleared UUID reuse |
| F05 Consumer manifest | V2 with versioned request digest, actual sizes/hashes and unchanged legacy v1 bytes | Approve numeric/filename compatibility, exact v2 schema and consumer fixtures |
| F06 Authentication/ingress | Global session revocation, HTTPS, same-origin mutation protection, separate producer trust | Exact CSRF, inactivity activity rules, endpoint denial/validation precedence and bounded selected proxy profile |

These blockers are not new approvals or all release gates. They are the remaining
P01 items, with P02/P03 deployment evidence explicitly separate. Group 49 now
settles F02 header transport while preserving the compact body and existing job
identifiers. Its [exact wire candidate](RETRY-HEADER.candidate.md) now has
checked encoding/bounds, with existing instance identity as an explicit proposed
precondition. Complete the remaining outcome/transaction/retention design and
other contract details before bulk retry implementation.

## Verification performed

- Existing WSL Python 3.12.3/jsonschema 4.10.3 checked the Draft 2020-12 schema
  against its metaschema, then all 57 fixture expectations, including rejected
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
