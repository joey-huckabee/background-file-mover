# UUID producer and manifest-v2 runtime integration

2026-11-08. User: "ok, go ahead with step 3" after increment 117/PR 5.
Base main a6f5db7381bfc05e6ba7fcb4a8371015900ca79d. Implementation in progress
on feature/uuid-runtime. This is development integration, not deployment,
operational conversion, remote authentication/ingress or release approval.

## Scope and compatibility

Replace the unused prototype producer wire directly with the approved bounded
POST /api/v2/jobs contract. Persist schema-12 kind-1 global UUIDs, original
assertions and identity-v1 digest. Compare assertions independent of file order;
keep the winning first-acceptance path/index allocation through every replay,
claim and worker restart. Use existing crates and exact dependency pins; sha2
is already qualified/locked and is now also used directly by Store. Pure frame
encoding is shared from dependency-free mover-core; hashing remains outside it.

The startup check_expected_sizes boolean defaults false. Its current value
applies to unfinished new-format work, without a per-job setting. Original
complete maps remain immutable even while comparisons are off. Measured facts
remain independent of expected assertions. Existing whole-set custody keeps its
202 replay meaning when the setting changes. Invalid fields/header/map syntax
still fail before lookup; unsafe/missing review blocks precede conditional policy.

New jobs allocate the canonical UUID directory under the pinned destination
root. Claims retain original numeric job/file IDs. Workers carry and pin the
actual directory component, never derive a fresh file ordering from replay input.
New completions use exact manifest-v2 bytes from the qualified codec, persisted
once as intent and reused across recovery; validate saved bytes/hash/context
rather than replace them. Legacy jobs keep original numeric paths, identities,
receipts, measured facts and exact v1 serialization/recovery.

Activation matrix (actual qualification status below):

| State | Behavior |
|---|---|
| Schema 11 | Normal runtime refuses; explicit verified offline 11-to-12 command remains separate. |
| Schema 12, legacy whole-set handoff | Continue existing delivery/recovery with v1 and original paths. |
| Schema 12, legacy incomplete handoff | Refuse before source/destination bootstrap. Preserve state/custody; finish handoff with qualified predecessor, then upgrade. No old-wire adapter or UUID assignment. |
| Schema 12, validated UUID/mixed state | Implemented typed reconstruction, replay, supervised workers and v2 paths; exact gate status below. |
| Damaged assertions/digest/schema/ownership | Refuse safely, without repair, migration, adoption or stale restore. |
| Predecessor codec-only binary with retained UUID rows | Its existing whole-state UnsupportedIdentity refusal applies. Never downgrade active UUID custody by restoring an old snapshot. |
| Cleared job | Forget all live identity/file/action/accounting linkage. Files stay untouched; reusing UUID creates fresh work/greater job ID, subject to ordinary no-clobber collision refusal. |

No cancellation/admin-session/deletion route is added. Offline clear still
clears only committed jobs under existing lifetime exclusion; safely cancelled
jobs remain future work because cancellation is not implemented. Existing trusted
loopback/configured-generator boundaries remain; remote proxy/auth qualification
is separate. Existing grouping support and deletion-disabled policy are unchanged.

## Actual validation and teamwork

Runtime/test source c99dda1302a6cf631f4b94a66b38201e6297bce0 has Rust tree
a3afcf2e95ac22a12356c1b66863f32fc7178c57 and 73 tracked Rust inputs. Both push
and PR CI passed production and qualification cargo-libc/SLES gates: 264 and 268
tests respectively per debug/release profile, with strict Clippy, GNU/glibc-2.22
ELF audits and pinned SLES target execution. Five existing helper tests remain
ignored per profile. Qualification-only bodies, including the actual paused-worker
kill/recovery case, run in the qualification build; these are local fixtures,
not actual NAS/RPC settlement or shipping systemd qualification.

[UUID-RUNTIME-EVIDENCE.json](UUID-RUNTIME-EVIDENCE.json) records all source hashes,
pins and CI report/executable hashes. CI diagnostics do not include executables
for independent rehashing. The seven original identity vectors, 766-byte golden
and structural/semantic reference checks passed unchanged. The existing fixture
copies still match. All 49 Python tooling tests and three offline bundle unit
tests passed; new current fixtures validate v2 while retaining historical v1
interpretation. No historical result was rewritten as qualification of this code.

Coordinator implemented runtime/Store, reviewed/integrated API tests from the
existing child and Python tooling from one temporary specialist, and owns one
sequential local WSL gate queue. Independent bounded runtime review excluded the
reviewer's own API contribution; coordinator reviewed and extended those tests.
Independent review of runtime, helper/callers and material later deltas has no
unresolved findings. Review caught interrupted zero-byte initialization refusal
and Python boolean/integer evidence aliases; both have regression coverage.
No fixed fan-out improvement is claimed; token/cloud cost is unavailable.

Retained development failures include compiler/lint integration errors, a first
CI API run with four failures (fixed enrollment refusal precedence and fixture
path/epoch handling), and a local native-space test that assumed its default
five-second cached sample would survive delivery. The positive accounting case
now explicitly uses the existing permitted 30-second fixture window, asserts its
policy/sufficient/fresh state and retains every accounting/claim/replay check.
Runtime defaults, request/delivery/shutdown bounds and separate short-expiry tests
are unchanged. Superseded local runs were interrupted by verified owned PID and
cleaned up, without claiming full passes. Exact run IDs remain in the evidence.

Before merge, [PR #6](https://github.com/joey-huckabee/background-file-mover/pull/6)
must record both final local modes, raw WSL paths/report hashes, all 73 input
comparisons and all 40 executable rehashes, cleanup and prototype bundle smoke
status. The final PR also records fresh CI for its exact documentation closeout
head; those documentation changes preserve every Rust input. The coordinator's
local production debug API/Store suites passed; full local finalization is
recorded in the PR before integration, not inferred from CI.

All eight release gates remain open. Consumer acceptance, final predecessor/
target release pairs, real NFS/physical durability, ingress and shipping systemd
qualification remain separate. Production NFS/source deletion stay disabled;
no operational database conversion, deployment or account/session change occurred.
