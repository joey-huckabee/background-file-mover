# Approved compatibility direction

Approved 2026-11-03, group 52. The user accepted the five compatibility
recommendations below. This approval settles policy; it does not freeze the
entire candidate API, authorize the remaining runtime implementation or claim
an upgrade/recovery qualification result.

| Decision | Approved behavior | Engineering work still required |
|---|---|---|
| Existing stored jobs | Preserve original job/file IDs, paths, custody, enrollment, receipts and worker lifetime evidence. Upgrade only supported state formats; refuse unsupported state safely before effects. Never invent recording UUIDs for legacy jobs. | Increment 115 qualifies the bounded 11 to legacy-only 12 path. Increment 118 implements UUID/mixed runtime; final release combinations and deployment remain separately qualified. |
| Completion manifests | New recordings use v2 with recording UUID, measured sizes, file SHA-256 and request-identity digest. Existing v1 bytes stay unchanged; support recovery of still-tracked legacy jobs. | Finalize exact v2 serialization/bounds and recovery integration. Increment 116 fixes encoding/bounds for the producer/v2 engineering slice; increment 117 supplies codecs and 118 runtime recovery; consumer acceptance remains pending. |
| Size representation | New producer expected-size values and manifest-v2 measured sizes are canonical decimal strings representing u64. Preserve existing operator/status numeric fields and v1 numeric sizes. | Lossless parsing/publication are implemented in 117/118; consumer acceptance and exact shipping evidence remain open. |
| Filenames | Require valid UTF-8 for the new contract; retain exact spelling and case. Reject unsupported names explicitly. Never silently rename, case-fold or normalize Unicode. | Check Unicode scalars and byte limits before filesystem effects; preserve existing custody rather than applying new admission rules destructively to legacy records. |
| Upgrade/rollback | Publish an explicit list of supported release/state combinations. An incompatible binary refuses before effects. Never restore a stale database over active transfers. | Increment 115/PR 3 supplies exact legacy migration pairs and predecessor refusal. Increment 118 supports mixed state and incompatible-binary refusal. Arbitrary/working rollback and shipping qualification remain open. |

## Current qualified migration and new-contract baseline

Increment 115, main merge 25202943138db5e7a852c762d6070758c10001bc, implements
explicit guarded schema-11 to legacy-only schema-12 migration with a new verified
backup. [PR 3](https://github.com/joey-huckabee/background-file-mover/pull/3) records
both local/PR SLES modes and debug/release actual predecessor/target recovery.
[Evidence](../STATE-MIGRATION-EVIDENCE.json) and the
[operator procedure](../OFFLINE-STATE-MIGRATION.md) bound that support. The known
predecessor at 2a31f23 refuses actual migrated state; this is not general binary
rollback, reverse conversion, hardware durability or deployment qualification.
No operational state was converted. Normal startup still refuses schema 11.

Increment 116 fixes the producer/v2 engineering serialization and bounds in
[the scoped contract](PRODUCER-MANIFEST-CONTRACT.md). Full P01 and consumer acceptance remain separate. [Increment 118](../RUST-INCREMENT-118.md)
implements UUID/mixed-state runtime, preserves legacy v1 recovery and refuses
partial legacy custody before payload bootstrap. Finish partial handoff with the
compatible predecessor before cutover; no old-wire adapter or invented UUID is
provided. [Current release checks](../RUST-INCREMENT-119.md) record actual retained
binary pairs and their limits.

The sections below preserve earlier approval/design checkpoints. Where they
say migration is unimplemented/unqualified, that historical limit is superseded
ONLY by the explicitly bounded increment-115 path above.

## Approved initial migration scope

On 2026-11-04 the user approved planning step 1: one explicit offline path from
validated schema 11 to the next schema, preserving legacy recovery and refusing
unsupported state. See [schema-11 upgrade specification](SCHEMA-11-UPGRADE.md)
for the exact planned matrix, invariants, fixture checklist and draft procedure.
This narrows the initial support target; no upgrade is yet implemented or
qualified, and runtime migration code remains separately gated.

The user separately authorized early compatibility checks on 2026-11-04.
[Increment 110](../RUST-INCREMENT-110.md) implements guarded current-schema
inspection before payload bootstrap and before offline history clear, and
removes automatic schema-1-10 upgrades. Its validation record governs that
bounded capability. It does not implement conversion to the planned target
schema or qualify an old executable's direct launch/rollback behavior.

The next [transactional migration design](SCHEMA-12-MIGRATION-DESIGN.md) supplies
proposed schema-12 jobs DDL, identity constraints, backup/conversion mechanics
and acceptance mapping. The user authorized this design on 2026-11-04; it does
not authorize migration execution or settle the remaining framing/runtime gates.

Separately authorized [increment 112](../RUST-INCREMENT-112.md) adds guarded
inspection and explicit verified offline backup, with conversion/apply disabled.
See [the operator procedure](../OFFLINE-STATE-BACKUP.md) and actual gate status;
these preparation commands do not qualify the upgrade/rollback matrix.

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

The latest foundation implementation creates schema 12 for fresh explicit setup
and supports legacy manifest v1; see [increment 111](../RUST-INCREMENT-111.md).
Existing schema 11 requires the explicit increment-115 offline upgrader; normal startup refuses it. The candidate
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
adapter; this does not permit abandoning persisted jobs. Increment-115 migration and exact predecessor refusal have actual executable
evidence; mixed legacy/UUID runtime, new-wire continuation and arbitrary rollback
remain unqualified and are not established by schema tests.

Group 50 remains authoritative after clear: files and manifests are left in
place, but all service linkage is forgotten. Legacy recovery support must never
scan, reconstruct or adopt cleared files. Reusing a forgotten UUID creates new
work subject to ordinary no-clobber destination checks, without overwrite,
automatic suffixing or adoption.
