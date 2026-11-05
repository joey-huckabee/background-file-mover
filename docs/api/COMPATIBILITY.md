# Approved compatibility direction

Approved 2026-11-03, group 52. The user accepted the five compatibility
recommendations below. This approval settles policy; it does not freeze the
entire candidate API, authorize the remaining runtime implementation or claim
an upgrade/recovery qualification result.

| Decision | Approved behavior | Engineering work still required |
|---|---|---|
| Existing stored jobs | Preserve original job/file IDs, paths, custody, enrollment, receipts and worker lifetime evidence. Upgrade only supported state formats; refuse unsupported state safely before effects. Never invent recording UUIDs for legacy jobs. | Declare and qualify exact predecessor/schema combinations; implement and test transactional preservation or refusal. |
| Completion manifests | New recordings use v2 with recording UUID, measured sizes, file SHA-256 and request-identity digest. Existing v1 bytes stay unchanged; support recovery of still-tracked legacy jobs. | Finalize exact v2 serialization/bounds and recovery integration. Existing candidate framing/fixtures are engineering proposals, not separately approved algorithms. |
| Size representation | New producer expected-size values and manifest-v2 measured sizes are canonical decimal strings representing u64. Preserve existing operator/status numeric fields and v1 numeric sizes. | Implement lossless parsing and publication; validate consumers and actual-size evidence. |
| Filenames | Require valid UTF-8 for the new contract; retain exact spelling and case. Reject unsupported names explicitly. Never silently rename, case-fold or normalize Unicode. | Check Unicode scalars and byte limits before filesystem effects; preserve existing custody rather than applying new admission rules destructively to legacy records. |
| Upgrade/rollback | Publish an explicit list of supported release/state combinations. An incompatible binary refuses before effects. Never restore a stale database over active transfers. | Populate and qualify the list using exact binaries/state fixtures. No predecessor, rollback or migration is declared supported merely by this approval. |

## Approved initial migration scope

On 2026-11-04 the user approved planning step 1: one explicit offline path from
validated schema 11 to the next schema, preserving legacy recovery and refusing
unsupported state. See [schema-11 upgrade specification](SCHEMA-11-UPGRADE.md)
for the exact planned matrix, invariants, fixture checklist and draft procedure.
This narrows the initial support target; no upgrade is yet implemented or
qualified, and runtime migration code remains separately gated.

## Wire size boundary

For new producer `expected_sizes_bytes` values and v2 file `size_bytes`, accept
`"0"` through `"18446744073709551615"`, inclusive. Reject JSON numbers, signs,
leading zeros, fractions, exponent notation, whitespace and overflow. For
example, `"9007199254740993"` remains exact in a browser. Parse the string to
an integer before computing the existing candidate request-identity frame;
hash the bounded integer value, not its JSON spelling. The seven existing
framing vectors therefore retain their original bytes and digests.

`ByteCount` remains the numeric u64 schema for current operator/status fields,
source-space policy and legacy v1 manifests. `DecimalByteCount` is the new
producer/v2 type. Retention totals remain existing decimal-string u128 values;
they must not be narrowed to u64. Numeric job selections and review epochs are
unchanged. This decision does not change the default-disabled expected-size
comparison policy or immutable complete-map assertions.

## Legacy and current-state limits

The implementation currently uses schema 11 and manifest v1. The candidate
schemas now describe v1 separately from v2; a shape check does not prove valid
ownership, receipts, commitment, or recovery. A legacy non-UUID submission stays
a legacy record; it must not silently become a new global recording UUID.
Original file/claim indices and original serialized manifest bytes govern
recovery. A still-tracked legacy job's continuation must preserve its original
manifest protocol; do not switch it to v2 because it finishes after an upgrade.

The initial planned matrix is now recorded in the linked upgrade specification.
An executable-qualified support list remains a deliverable, with these required
dispositions rather than invented support claims:

| State/binary situation | Required disposition |
|---|---|
| A declared supported predecessor with retained jobs | Qualified transactional upgrade preserving original custody/identities and immutable manifests, or documented safe refusal if preservation cannot be established. |
| An unknown, unsupported, foreign or corrupt state format | Refuse before filesystem effects; preserve original state and provide operator guidance. Do not initialize replacement state over it. |
| Rollback binary incompatible with the current state format | Refuse before effects. A successful restore of an old database is not a valid rollback while current custody exists. |
| Interrupted upgrade | Recover using original authoritative state and a qualified procedure; no automatic re-enrollment, path relocation, UUID invention or stale snapshot replacement. |

Existing enrollment/binding and instance/lifetime checks remain mandatory. The
unused prototype producer format may be replaced directly without an old-wire
adapter; this does not permit abandoning persisted jobs. Runtime migration,
coexistence and rollback results are pending, not established by schema tests.

Group 50 remains authoritative after clear: files and manifests are left in
place, but all service linkage is forgotten. Legacy recovery support must never
scan, reconstruct or adopt cleared files. Reusing a forgotten UUID creates new
work subject to ordinary no-clobber destination checks, without overwrite,
automatic suffixing or adoption.
