# Producer/manifest contract closeout

2026-11-07. The user authorizes step 1 of the next recommendation: finalize the
producer/manifest-v2 contract and reconcile migration status. Base main:
25202943138db5e7a852c762d6070758c10001bc. This is documentation, schemas and
reference checks only. Rust codecs, UUID admission, v2 runtime, full P01 freeze,
consumer qualification, operational conversion and deployment are not authorized.

## Result

PRODUCER-MANIFEST-CONTRACT.md fixes the existing candidate producer fields,
lexical/size/JSON bounds, optional UUID header equivalence, global identity and
replay/current-size-policy ordering, error registry, canonical response UUIDs,
positive usable retry delays and exact v2 serialization/membership. It specifies
first-acceptance file indices and immutable saved bytes, with numeric sizes kept
for legacy v1/operators. Metadata/shipping/consumer and other-route obligations
remain explicit; legacy partial custody is an activation gate, not silently
solved by wire replacement. Steps 2 (pure codecs) and 3 (complete activation)
have concrete scope/tests and require separate authorization.

The seven existing identity frames/hashes stay unchanged. The existing manifest
fixture now records its 766-byte compact UTF-8 golden and SHA-256. No new vector
suite, transfer simulation or acceptance IDs are added. The checker runs the
existing eleven semantic examples, strict JSON/scalar rejection and a conservative
106673-byte maximum-manifest proof under the existing request/file bounds.

Reconcile stale migration claims in the bundle index, compatibility and proposal
with increment 115/PR 3. Retain historical checkpoints as history. This does not
expand the declared schema support or qualify arbitrary rollback.

## Validation

Local existing WSL Python/jsonschema checks passed: 70 definitions, 108 structural
fixtures, eleven semantic examples, fifteen route/reference/access checks, seven
unchanged identity frames/hashes, existing manifest golden and bound proof.
These are contract reference checks, not full OpenAPI conformance, Rust, HTTP,
SQL scheduling, consumer or physical durability tests. Independent review and
final diff/catalog/reference verification are pending before integration.

No Rust source, build input, dependency, worker, state or runtime setting changes.
No Rust build/test is needed for this documentation/reference slice; qualified
Rust tree remains ce45cf6bddb72e0cd9cec5665773907ba80947ea. Both SLES modes remain
mandatory for the separately authorized future Rust increments. All eight release
gates remain open; production NFS/source deletion stay disabled.

## Team workflow

Coordinator owns contract/checker integration; existing cloud reviewer performs
a bounded independent read-only review before merge. Record concrete findings,
check results and scope corrections here. Token/cloud cost is unavailable; no
fixed improvement percentage is claimed.
