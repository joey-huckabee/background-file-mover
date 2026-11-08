# Producer and manifest-v2 engineering contract

2026-11-07, increment 116. The user authorizes step 1: finalize this bounded
contract and reconcile completed migration work. This is the final engineering
baseline for the next codec increment, using groups 1-52. It does not freeze
all P01 routes, claim consumer compatibility, authorize runtime UUID/v2 activation,
convert operational state or deploy anything. Other candidate/admin/access
choices remain identified in [the bundle index](README.md).

## Implementation checkpoint

Step 2 codecs merged in PR 5. The user authorized runtime step 3 on 2026-11-08;
see [increment 118](../RUST-INCREMENT-118.md) for actual source/gate status and
the supported activation matrix. Historical authorization limits in this
2026-11-07 contract remain descriptions of that checkpoint; the approved
engineering rules below remain unchanged.

## Authority and artifacts

This document fixes the producer/v2 details previously left as engineering
candidates in packages 2/4 of REST-CONTRACT-PROPOSAL.md. Existing approved
API-E01-48/61-74/112-113/139-143 and SC-139-142/164/190-194 retain their IDs and
scope; no new product approval group is invented. The strict ProducerRequest,
ProducerAccepted, ProducerError, RequestIdentity, ManifestFile and ManifestV2
schemas in contract.candidate.schema.json implement structural constraints.
Annotations and the semantic rules below remain mandatory beyond JSON Schema.
The producer operation in openapi.candidate.json carries this scoped baseline;
the other fourteen operations remain candidates. A schema pass is not custody.

REQUEST-IDENTITY.candidate.md now fixes identity encoding v1 for this slice;
its seven existing frame/hash vectors stay byte-for-byte unchanged. The existing
manifest-v2 fixture gains its exact writer-byte length/hash; no new vector suite
or simulated transfer lifecycle is introduced.

## Producer request and lexical rules

POST /api/v2/jobs, application/json. The body has exactly four required fields:
generator_id, recording_id, source_directory and files; expected_sizes_bytes
is the only optional field. Reject old submission_id/source_path forms,
producer-supplied destinations/hashes and arbitrary metadata fields. The unused
prototype wire is replaced directly at activation, without an old-wire adapter.

| Item | Final engineering rule |
|---|---|
| Raw body | At most 65536 bytes, before parsing; strict UTF-8. Reject BOM, duplicate JSON keys at any depth, non-JSON numeric constants and unpaired surrogate escapes. |
| Raw HTTP head | Existing 8192-byte aggregate including request line/terminator, at most 64 headers; existing strict framing and read/handoff budgets stay unchanged. External proxy/TLS profile qualification remains P02/P03. |
| generator_id | 1-128 ASCII bytes, first alphanumeric, remaining alphanumeric, dot, underscore or hyphen; case-sensitive and bound to the authorized configured generator. |
| recording_id | Exactly 36 ASCII characters, hyphenated 8-4-4-4-12 hexadecimal, either hex case. Parse to 16 bytes in textual hex order; emit lowercase. No braces/URN/compact form, extra version/variant restriction or trimming. |
| source_directory | Absolute slash-separated path, 1-4095 UTF-8 bytes, no backslash, controls, empty/dot/dot-dot components or trailing slash except root. Lexical validity does not authorize the root or service-private namespaces. |
| files | 1-256 unique relative paths. Each is 1-4095 UTF-8 bytes; no leading/trailing slash, empty/dot/dot-dot component, backslash, U+0000-001F or U+007F-009F. Reject components .file-mover, .control, .staging and COMMITTED.json at any depth. No path may be another path's directory ancestor. |
| expected_sizes_bytes | When present, an object with exactly the files keys, each a canonical decimal-string u64 from "0" through "18446744073709551615". No null, numbers, sign, whitespace, leading zero, fraction, exponent or overflow. |

Reject invalid Unicode scalars. Preserve all other valid spelling, case and UTF-8
bytes: no Unicode normalization, case folding, trimming, percent decoding or
filesystem alias resolution to establish replay equality. JSON escape spelling
is syntax, not identity: equivalent decoded scalars compare equally. No additional
public component-length bound is introduced; actual filesystem/object admission
can still refuse unsupported names under existing safety/error rules. Reserved
names above are exact case-sensitive components, not arbitrary substrings.

Idempotency-Key is optional, never a second identity. Require at most one header
occurrence; duplicate headers follow 400 invalid_http. After existing HTTP field
OWS parsing, a supplied value must use
the same UUID lexical syntax and parse to the body UUID bytes; malformed or
mismatched values give 400 idempotency_key_conflict. Hex case alone is equivalent.
Validate this binding before a receipt can be replayed. Existing trusted-local
operator command headers continue to match command_id bytes exactly.

## Identity, replay and admission ordering

A new recording UUID is global across generators, represented as schema-12 kind
1. Kind 0 remains the separate legacy namespace: even UUID-looking submission_id
text never becomes a new recording UUID. Retain original immutable assertions,
not only their hash. The identity digest is an integrity binding, not a credential,
new job ID, content hash or proof of human inspection/custody.

Process the following order; no partial success or batch-wide rollback is implied:

1. Enforce existing framing/aggregate/read bounds. Authenticate the caller and
   authorize the producer route/configured generator before any job-existence
   disclosure. Failed authorization may be generic and must not echo private
   state. TLS/proxy failures need not have mover JSON.
2. Decode strict JSON, validate field types/bounds/lexical rules, exact map keys
   in both checking modes and optional header binding. Structural failures
   precede replay; malformed retries cannot obtain receipts. Match the validated
   body generator against the trusted caller/configured binding before lookup.
   Root lexical syntax and authorized configured scope remain distinct checks.
3. Under authoritative instance ownership, perform global UUID lookup and exact
   immutable comparison. A different owner or changed generator/source directory,
   file membership or map presence/value is 409 recording_id_conflict for an
   otherwise authorized caller. Do not disclose the other owner's job/details.
   File permutation and UUID hex case are equivalent; map changes conflict even
   when size comparison is off. A matching digest alone is insufficient.
4. For an exact still-tracked request with durable whole-set handoff proof,
   validate the existing authority/custody evidence and return the original 202
   meaning/job ID. Do not apply a newly enabled missing-map requirement, reopen
   producer-reused original leaves, retransfer completed work or run new-key
   source-space/retention admission. Unsafe/unprovable evidence refuses safely.
5. For an exact unfinished request, first honor cancellation and persisted
   missing/unsafe-custody review blocks. Cancelled pre-handoff work is 409
   recording_cancelled; review blocks are 409 recording_blocked. For otherwise
   eligible unfinished work, apply the current startup
   check_expected_sizes setting (final name, default false). Off ignores expected
   numeric comparisons, not immutable assertions. On requires the original
   complete map: absence is 400 invalid_submission; a measured mismatch is 409
   source_size_mismatch, both retryable:false. For already claimed files use
   private custody/receipts, never reused original names. Map checks cannot reset
   independent blocks. An existing confirmed whole-set handoff keeps its approved
   replay meaning under step 4.
6. For new keys, apply existing source authority, reservations and retention/
   source-space admission before acceptance/effects, including transactional
   rechecks against concurrent requests. Existing keys bypass only new-key gates.
   Persist first acceptance and path-to-file-index mapping atomically. A competing
   equivalent permutation uses the winning mapping, never its own reordered IDs.
7. Claim/measure stable source objects using existing supervised custody rules.
   Confirmed absence is 409 source_file_missing within the persisted missing
   window; a live worker/unknown RPC outcome is 503 handoff_pending, not absence.
   No new timeout or automatic reset is added. Return 202 only after durable
   custody for the whole submitted set; earlier claims remain protected on error.

The current setting applies after restart to unfinished work; never persist a
per-job size-policy snapshot. It cannot change measured facts, integrity checks,
immutable assertions or a prior whole-set release. This adds no live reload.
Legacy original assertions must remain legacy, including sparse per-file values;
never manufacture a complete map or reinterpret a legacy job through this wire.
Activation must qualify legacy continuation or safe refusal using original
custody before removing old-wire admission, especially for partial legacy claims.
The current migration alone is not proof of that future continuation mechanism.

Destination outage alone cannot block source handoff when source authority,
custody and admission are independently established (ER-D07). Existing pinned
destination policy/authority and reservation rules still apply; ambiguous/changed
binding is a safety refusal, not an outage exemption. No new destination health
probe or generic destination HTTP error is introduced by this wire contract.
Delivery failures after 202 remain operator concerns; they never revoke release.

## Responses and errors

202 has exactly job_id (positive i64 decimal string), canonical lowercase
recording_id, accepted:true and source_paths_released:true. It says nothing about
destination completion. Identical authorized confirmed replay retains the original
job ID. The recorder compares parsed UUID identity, so an uppercase request can
accept a lowercase echo; a different UUID or malformed receipt grants no release.
No required Location/polling workflow or operator access is added.

Mover errors have exactly the five required fields: recording_id (canonical or
null when unavailable/unsafe), error, retryable, retry_after_seconds (null or
integer 1-2147483647), source_paths_released:false. No extra diagnostic fields.
False grants no new release and cannot revoke an earlier valid 202. The producer
operation's per-status x-error-codes registry is final for mover-generated replies
in this slice; the ProducerError enum is exactly its union. Preserve the existing
approved distinctions between startup/OS/TLS failures and served HTTP responses.

For deterministic 400 mapping: JSON/UTF-8/BOM/duplicate-key/scalar decoding errors
are invalid_json; wrong/missing/unknown fields, invalid UUID/source syntax,
empty/overlarge file array and bad/partial/extra size maps are invalid_submission;
duplicate or invalid file paths/prefix conflicts are invalid_file_paths. Optional
header mismatch is idempotency_key_conflict. Existing transport errors retain
invalid_http, unsupported_headers, incomplete_request and request_timeout rules.
Malformed request values precede known-ID lookup; confirmed receipt replay precedes
conditional size policy; independent unsafe custody always prevents false release.

Use the approved retry guidance: usable JSON delay, then valid Retry-After for an
otherwise retryable result, then 5/10/20/30-second fallback (stay at 30). A valid
retryable:false stops automatic retries regardless of headers. Controlled 429/503
with known delay send the same integer Retry-After; null timing omits it. For 409
use the JSON delay. The five-minute warning and configurable recorder retry
settings do not alter the mover's missing window or delivery retry policy.
Unexpected 2xx, redirect or invalid 202 is a protocol error: preserve paths and
alert. Lost replies/temporary transport failure keep the same UUID/body. Never
infer no effects from a failed response or fabricate success/counts.

## Manifest v2: exact writer bytes and evidence

New kind-1 recordings use COMMITTED.json version 2. The fields, in emitted order,
are version, instance_id, job_id, generator_id, recording_id, request_identity,
files. request_identity order is version, algorithm, sha256. Each file order is
file_id, path, size_bytes, algorithm, sha256. No optional/extra metadata fields.

Assign file IDs 0..N-1 from the first durably accepted file-list order and preserve
that path/index mapping. Emit the full manifest array in ascending NUMERIC file-ID
order, not lexicographic ID order or replay input order. IDs are canonical decimal
strings 0..255. Paths equal the original exact membership; each appears once.
Sizes are measured verified u64 decimal strings, never expected values or null.
Both algorithms are "sha256"; digests are 64 lowercase hex digits. instance_id
is the existing 32-lowercase-hex durable mover instance; job_id remains the
original positive i64 decimal string, not a new public identifier.

Writer encoding is compact UTF-8 JSON: fixed field order above, no BOM, no
insignificant whitespace, no trailing newline. Escape quote as \" and backslash
as \\; all other permitted scalars, including non-ASCII and U+2028/U+2029, emit
as their UTF-8 bytes. Do not ASCII/HTML-escape Unicode or escape slash. Invalid
scalars/controls were already rejected; no float formatting participates.
SHA-256 of the manifest is over THESE exact serialized bytes. Serialize once,
persist bytes/hash in the manifest intent and publish those same immutable bytes.
Recovery reads the saved bytes; it must not regenerate formatting to hide change.

The existing manifest-v2 fixture is the writer golden: 766 bytes, SHA-256
4c9909f703393be2cb1aae8d4775272a159b25e43df3a0b2af9f08ff40b7bd9b.
Its request_identity is the existing minimal request vector's digest. Only that
digest appears publicly; no source directory/map is embedded in the manifest.
The hash is not a secret and does not authenticate an untrusted filesystem.

The manifest limit stays 131072 serialized bytes. A 65536-byte valid producer
body plus 256 fixed-size entries and bounded header fits this limit; the checker
verifies a conservative bound using maximum IDs/sizes/header. Canonical UTF-8
path string encoding cannot exceed the corresponding valid raw request string
encoding. No valid admitted request should fail solely because metadata expansion
was ignored. Decoder byte limits apply before parsing; reject duplicates/unknown
fields, noncanonical size/ID values, invalid membership/order, paths and digests.
A generic consumer may accept legal JSON field order/whitespace within the byte
bound; that never authorizes service-side mutation or bypass of saved-byte checks.

A consumer must validate every listed file, actual size and full hash against
the complete manifest. When it has the original request it must also compare
exact membership and recompute request identity; a digest alone cannot reconstruct that request or
prove first-acceptance order. A visible payload, a visible precommit manifest or
202 alone does not establish validated destination completion. Preserve existing
no-clobber publication, manifest synchronization and coordinator commitment
ordering; actual consumer/runtime qualification remains required before activation.

The minimal contract covers payload content, exact names, measured sizes and
hashes. It adds no promise to copy source ACLs, ownership, timestamps, xattrs,
sparse layout or hard-link relationships. Recording metadata is excluded; a
listed metadata.json is ordinary payload. Existing service permission/custody
rules remain unchanged; broader shipping filesystem metadata policy is still a
release obligation, not silently approved by a JSON schema.

## Legacy compatibility, clear and implementation increments

Increment 115 implemented and qualified explicit schema-11 to legacy-only schema
12 conversion; main merge 25202943138db5e7a852c762d6070758c10001bc. Exact pairs,
SLES results and limits are in RUST-INCREMENT-115.md/STATE-MIGRATION-EVIDENCE.json
and PR 3, with operating steps in OFFLINE-STATE-MIGRATION.md. This is not an
operational upgrade authorization. Normal startup still refuses schema 11.

Still-tracked kind-0 jobs retain their legacy IDs, original file indices/routes,
receipts and exact v1 bytes. Legacy jobs completing after a supported upgrade
still write v1; do not apply fresh-request lexical restrictions destructively to
stored names. Preserve numeric v1/operator sizes and decimal-string u128 ledger
totals. Unsupported state/identity/old binaries refuse before payload effects;
no reverse conversion, stale restore, automatic adoption or UUID assignment.

Clear forgets all live file/identity/accounting/action linkage. No old manifest,
backup or directory scan may rebuild it. Reusing a forgotten UUID is fresh work
with a larger job ID and fresh custody; ordinary no-clobber collisions can refuse
its UUID-named destination. No overwrite, automatic suffix or adoption shortcut.
External protected backups remain separately held historical artifacts.

The next two implementation increments require separate authorization:

- Step 2: pure UUID/decimal/path validation, immutable identity framing/digest and
  v2 encode/decode helpers using existing crates. Keep mover-core dependency-free
  and hashing/serde in existing capable layers; no new project dependency. Reuse
  the seven identity vectors, existing semantic fixtures and manifest golden.
  Include exact integers/scalars/duplicate rejection, persisted mapping/order,
  maximum bound and malformed-input tests. Leave producer routing, writable
  Store admission, worker assignments and kind-1 whole-state refusal unchanged.
  Both production/qualification cargo-libc/SLES gates and independent review apply.
- Step 3: only after codecs pass, wire global UUID ownership/replay and current
  size policy into acceptance, durable path/index storage, UUID destination
  allocation (canonical UUID component under the existing pinned destination/
  generator-grouping policy), all relevant worker messages, v2 publication/recovery and safe
  history clear. Keep legacy v1 recovery and declare partial-legacy continuation/
  refusal before replacing prototype producer admission. Prove transaction races,
  lost-202/producer path reuse, restarts, incomplete claims, size-policy changes,
  no-clobber, immutable manifest bytes and clear/reused UUID behavior with actual
  HTTP/SQL/filesystem fixtures. Remove whole-state UUID refusal only when every
  effect entry point supports the complete path. Publish the exact activation
  compatibility matrix; no half-upgraded daemon, deployment or NFS enablement.

Full P01 admin/session/ingress closeout, selected proxy, consumer acceptance and
all eight release gates remain separate. This document closes engineering choices
for the producer/manifest codec slice, not those broader qualification obligations.
