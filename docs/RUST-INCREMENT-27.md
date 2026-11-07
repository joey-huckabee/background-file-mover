# Rust increment 27: explicit source enrollment and matching restart

Development increment on `feature/rust-transfer-coordinator`, 2026-10-15.
Implements the unused-scope first-enrollment slice of
[the contract](FENCED-ENROLLMENT-DESIGN.md). Existing-job rebind, takeover,
database-loss recovery and production NFS/deletion remain disabled.

## Operator behavior

Exclusively provision a genuinely unused protected source scope, its owned private
`.file-mover` namespace, version-3 source binding marker and empty mode-0600
regular `coordinator.lock`. Configure version-3 source and destination bindings;
provision the destination marker/lock before delivery is needed. Source setup
does not require the destination to be available.

Run `file-mover --initialize-source CONFIG.json` once with the audited binary.
It opens no HTTP listener, claims no recording and copies no payload. It creates
a protected mode-0400 `.file-mover/source-enrollment.json` receipt paired with
the original local database. Then use normal `file-mover CONFIG.json` startup.
Normal startup and `--transfer-one` require the active pair; startup cannot invent
missing enrollment. Repeating initialization on an active matching pair validates
it without rewriting the receipt.

Keep that database and receipt together. A fresh database with the same configured
coordinator label cannot adopt the source, including after clean lock release.
Setup refuses unknown/preexisting private namespace entries, existing local
legacy enrollment and populated state. It never repairs a missing/foreign receipt,
changes an old job's destination, restores producer paths or deletes private data.
Unused producer input directories/files outside the protected namespace are
allowed under the existing immutable handoff contract.

## Persistence and effects

Schema 10 adds `source_ownership` with exact receipt bytes and a nullable object
identity: null means prepared; a saved identity means active. Preparation records
source binding/observation, state instance and receipt together in a local durable
transaction. The separately versioned receipt carries version 1, the original
32-hex-character state instance ID, a deterministic one-time operation ID derived
from that instance, source binding and observation. It is not a secret or fence.

Only the supervised enrollment child accesses the source. It inherits the same
regular-file lock description, validates custody and binding, checks the unused
namespace, creates the receipt exclusively, writes it, applies mode 0400 and
synchronizes the file/parent. The parent validates the bounded result, records
activation durably and attaches the receipt identity to subsequent source
authorization. Claim/delivery checks validate exact bytes, held/named identity,
private mode, owner, link count and device before/after effects. No source I/O is
added to the async executor or database owner.

SQLite and source storage do not commit atomically. A prepared operation without
a receipt can be retried explicitly; normal startup remains unready. If the child
created any receipt but its identity was not activated locally, setup preserves
it and refuses adoption even when its bytes match. This deliberately conservative
review outcome avoids inventing object ownership across a creation/result crash.
There is no repair command in this increment. An active record with a missing,
unsafe or replaced receipt also refuses without creating or overwriting it.

Binding policies/observations advance to version 3 so older binaries reject newly
provisioned configuration/markers instead of ignoring the persistent receipt.
The descriptor-custody bootstrap receipt stays version 2; its file-lock wire shape
has not changed. New bootstrap reception refuses an unexpected preattached
enrollment. Existing binding versions 1/2 refuse configuration validation.
Structural migration preserves old jobs; it does not create ownership receipts
or enroll old bindings. Exclude all old coordinators/workers before provisioning
a new protocol. Mixed-version use and existing-state cutover are unsupported.

## Validation

Production gate `20261015T125334Z-23fc2e1b` PASSED 150 tests per debug/release
profile; qualification gate `20261015T125346Z-22db336c-nfs-qualification` PASSED
151 per profile. Each audited 20 executables across both profiles, completed
formatting/Clippy and six negative ELF controls, and ran the exact targets in
pinned SLES userspace. Maximum required GLIBC is 2.18; the external graph remains
42 packages. See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Full NFS run `nfs-20261015T131554Z-4baea72b` PASSED with exit 0 and
`cleanup_errors: []`. It passed six directional delivery baselines, 20 ownership
cases (two startup exclusion, four inherited-worker, twelve enrollment and two
missing-mount cases), and all 22 runtime cases across debug/release. The original
state recovered actual recording work; fresh peer state and explicit peer
initialization were refused after lock release in both empty and populated
scopes. All twelve enrollment cases confirmed the intended startup/retry/review
decision and unchanged producer input. Four three-minute runtime outages retained
one blocked worker with responsive health/status and recovered successfully.
OS inherited-lock, interrupted metadata, isolated bootstrap termination and
production-NFS-refusal controls also passed. See
[full enrollment/NFS evidence](RUST-NFS-ENROLLMENT-EVIDENCE.json).

Verified driver hashes, complete Rust archive inventories/content and exact gate
artifact provenance. Both source archives match their respective recorded hashes;
their compressed hashes need not match each other. Fixture-owned containers,
network and data volume were removed. Only the default Podman network and the two
existing toolchain/registry cache volumes remain. Cached images/modules are kept.
Cooperative exclusion passes; `protection_complete` and `production_authorized`
remain false. This is hard NFSv4.1 with `local_lock=none` on two container clients
sharing kernel `6.18.33.2-microsoft-standard-WSL2`, not independent physical-host,
partition/reclaim, server-reboot or power-loss qualification. Validation used the
Windows checkout and healthy root Podman WSL2 engine; builds ran natively under
container `/work`, not `/mnt/c`.

Initial run `20261015T124442Z-41e73fde` failed compilation on an ambiguous
`Read`/`Write::by_ref` call. Runs `20261015T124650Z-cbeca12c` and
`20261015T124703Z-2ad4394e-nfs-qualification` passed the 61 debug API tests but
failed the new migration fixture's mismatched source path. Those are failed
evidence. Intermediate version-2 runs `20261015T125109Z-a20d31e8` and
`20261015T125120Z-4d553542-nfs-qualification` passed but are superseded by the
final version-3 source archives above; do not use them for this fixture.

First NFS run `nfs-20261015T130311Z-3e81bc4c` FAILED with clean resource cleanup
after the expected prepared-enrollment startup refusal. The fixture incorrectly
required an unchanged main SQLite file after forced process death. Crash recovery
can checkpoint committed WAL data into that file without changing logical state.
The rerun confirms this physical-file change, pending refusal and successful
explicit retry. Only the deliberate enrollment crash cases permit that main-file
change; other existing-state refusal checks retain their byte-preservation
assertions. Source receipt/producer evidence and durable-phase decisions remain
checked. Retry output and traceback capture now preserve actionable failures.

New gated cases cover explicit initialization, matching restart/replay, fresh
state after prior claims, missing/unsafe/foreign/equal-byte replacement receipts,
prepared versus ambiguous creation recovery, live receipt replacement, legacy
namespace refusal and schema-9 job preservation. Store tests cover durable prepared
state, exact activation and foreign identity refusal. Qualification-only pauses
cover before/after local intent, exclusive creation, before file/parent sync,
after sync and after local activation. They compile to no effects in production.

The retained NFS fixture uses explicit initialization for new test scopes. Its
ownership cases must refuse fresh peer state after clean release and after actual
recording recovery. Enrollment cases kill real initialization parents/children at
the six selected boundaries in debug/release, confirming exit and either safe
explicit retry/active restart or preserved ambiguous receipt review. These are
selected process-death tests without an in-flight RPC outage, server reboot or
power loss. All prior baseline/runtime/startup controls remain passing.

No package or deployed executable is added. Source initialization adds bounded
metadata, not payload hashing; normal integrity remains 3N. Containers run pinned
SLES 12 SP5/glibc 2.22 userspace on the WSL2 kernel. Two fixture clients share that
kernel. Keep prior result documents/reports as historical evidence.

Persistent pairing does not detect a cloned database or stale snapshot containing
the same enrollment. It does not authenticate an export or fence a lost lock,
partition/reclaim, retained descriptor or delayed operation. Keep one statically
assigned coordinator per disjoint scope and retain original state. Positively
fenced populated-state rebind/takeover and deferred repair need separate work.
Maintain SC-053/055/056/063–067 and DOC-03–05 with these exact limits.
