# Pure producer and manifest-v2 codecs

2026-11-07. User authorization: "ok, go ahead with step 2" after the scoped
contract closeout. Base main d3505c2f73a19799cce452d2883c8f198adb590a.
The bounded implementation follows api/PRODUCER-MANIFEST-CONTRACT.md; step 3
runtime activation, full P01, deployment and operational conversion remain gated.

## Implementation

mover-core gains a dependency-free RecordingId, exact decimal-u64 parser and
ProducerRequest semantic model. UUID case canonicalizes without version/variant
restrictions or platform byte swapping. New producer generator/source/path/map
rules preserve exact Unicode and first-submission file order. Request equality
compares immutable assertions independent of file order; original file order
remains separately available for durable allocation. Legacy Submission is unchanged.
The core constructor validates shape, not a bounded HTTP body, source authority,
measured values or custody.

mover-fs recording_codec uses existing serde/serde_json/sha2 for bounded strict
JSON, nested duplicate-key rejection, complete optional size maps, header UUID
equivalence and exact identity-v1 framing/hash. It performs no Store, filesystem,
HTTP or worker operations. No configuration/policy snapshots or dependencies.

ManifestV2 construction requires the ORIGINAL durable request/file mapping and
caller-supplied measurements; it sorts IDs numerically without reallocating them
and emits the exact fixed-field compact UTF-8 v2 bytes. Measurements are inputs,
not proof of physical verification. Decode validates bounded fields/membership/
ordering and retains original bytes, including legal whitespace/key order.
bytes()/sha256() refer to those original bytes; there is no decode/re-encode API
that could hide mutation. validate_request supports consumer request binding;
validate_context additionally checks instance/job and original durable path/index
mapping. Physical bytes/objects, custody and commitment remain caller obligations.

## Tests and fixture provenance

Reuse the seven existing identity vectors and the existing producer/v2 subset of
the 108 contract fixtures, including their semantic expectations and 766-byte
manifest golden. Exact copies/subsets are embedded under Rust so the existing
Rust-only gate archive remains self-contained. The existing Python checker now
verifies these copies against docs, preventing silent drift; no new vector
collection or contract/acceptance IDs are introduced.

New meaningful tests cover UUID/decimal boundaries, equality versus saved order,
legacy validator separation, known-answer frames/hashes, JSON duplicates/scalars/
null maps/unknown fields, map completeness and policy-independent assertions,
exact measured integers, manifest bytes/hash retention, instance/job/request and
mapping mismatches, malformed fields/order, raw byte bounds and a 256-file Unicode/
quote/u64-max manifest. The HTTP regression must keep the new wire rejected with
no job/custody effect and retain existing legacy admission/v1 publication.
Existing whole-state kind-1 refusal tests remain intact.

## Actual validation status

Reference checker passed in existing WSL Python/jsonschema: 70 definitions,
108 structural cases, eleven semantic examples, fifteen route/reference checks,
seven unchanged frames/hashes, existing manifest golden/bound and copied Rust
fixture checks. Rust formatting passed after correcting a test variable that used
the Rust-2024 reserved word gen. No Rust build/test pass is claimed yet.
Independent review and both production/qualification cargo-libc/SLES debug/release
gates remain pending. Record actual reports/hashes and limits before merge.

No current producer handler, Store writer/schema, worker/assignment, manifest-v1
writer, size configuration or startup capability rule is changed. Only a new
inactive library API and regression tests are added. All eight release gates
remain open; production NFS/source deletion stay disabled. No operational DB,
source or destination is touched by this implementation work.

## Team workflow

Coordinator owns implementation/integration and one sequential WSL gate queue;
existing cloud reviewer performs a bounded independent read-only review. Record
findings/rework and actual results here before integration. Token/cloud cost is
unavailable; no fixed percentage improvement is claimed.
