# Triage of the ten Open L2 requirements

Drafted 2026-11-22 against `main` at `6bfd27e`, after the complete L2 mapping.
This is step 2 of the [traceability plan](TRACE-MATRIX.md#plan).
The [L2 requirements](L2-REQ.md) and [trace dispositions](TRACE-L2.md) are
unchanged. These are proposed next actions, not approvals or test results.

There are **4 test gaps, 6 feature gaps and 0 already-covered rows**. A test
gap means the relevant implementation exists but its required verification is
missing; it does not mean that the implementation is already proved compliant.
In particular, the two NFS entries need qualification of existing behavior on
the intended export. A failing qualification must reopen the implementation
question, rather than weaken the checks or become a pass by inspection.

Effort is relative: **S** is one focused existing-harness test; **M** is a
bounded set of tests or one integration; **L** needs a new qualification tier,
platform facilities or several coordinated cases. These are sizing estimates,
not calendar commitments. Test names and new paths below are proposals only.

| Open L2 ID | Classification | Effort | Next action |
|---|---|---|---|
| L2-JSON-005 | test gap | M | Independent JSON corpus plus coverage-guided fuzzing and retained regressions. |
| L2-CFG-011 | feature gap | M | Shared option definitions for validation and generated configuration documentation. |
| L2-ARC-008 | test gap | L | A separate, applicable ThreadSanitizer CI tier with stated instrumentation coverage. |
| L2-CTL-011 | feature gap | M | Service-manager readiness and stopping notification integration. |
| L2-CTL-012 | feature gap | L | Manager watchdog emission and a qualified hung-service restart policy. |
| L2-SEC-013 | feature gap | L | Destination-label handling and target-specific AppArmor policy. |
| L2-SEC-014 | feature gap | M | Complete and qualify the shipped hardened service unit. |
| L2-SEC-016 | feature gap | L | Supported endpoint-security exclusion query and coverage reporting. |
| L2-NFS-005 | test gap | L | Real-export silly-rename artifact tolerance across the applicable managed paths. |
| L2-NFS-008 | test gap | L | Target server/export/backing-storage durability qualification. |

## JSON conformance and fuzzing

**Existing evidence.** In
[recording_codec/tests.rs](../rust/crates/mover-fs/src/recording_codec/tests.rs),
`strict_raw_json_and_original_map_rules_before_policy` checks malformed UTF-8,
BOMs, duplicate keys including escaped aliases, deep input and invalid size
maps. `malformed_manifest_fields_and_duplicate_keys_are_refused` mutates
manifest fields, duplicate paths and repeated keys.
`byte_limits_and_maximum_integer_manifest_are_bounded` checks the producer byte
boundary, oversized manifests and a large valid manifest. These bodies exercise
the [existing codec](../rust/crates/mover-fs/src/recording_codec.rs), but they
are neither a third-party corpus nor coverage-guided fuzzing.

**Test to add.** Add
`independent_json_corpus_preserves_strict_producer_contract` in that test file,
with a pinned, license-reviewed third-party corpus and explicit expectations
for the project's stricter duplicate-key, UTF-8 and size rules. Distinguish JSON
syntax acceptance from producer/manifest schema acceptance: a valid arbitrary
JSON value need not be a valid producer request. Add a proposed fuzz target
`rust/fuzz/fuzz_targets/producer_json.rs` for bounded producer and manifest
decoding, no-panic properties and successful encode/decode consistency. Retain
every minimized finding as a regression. Any new fuzz tooling/dependencies need
their own approval; this triage adds none. Completion requires actual corpus
and fuzz evidence, not merely creating a target.

**Proposed disposition after evidence:** Tested only when both required kinds
of verification exist with findings retained; a corpus alone remains partial.

## Shared configuration definition

**Existing evidence.** `Config`, its defaults and `validate` in
[file-mover/src/lib.rs](../rust/crates/file-mover/src/lib.rs) are handwritten.
`read_config` in [main.rs](../rust/crates/file-mover/src/main.rs) reads bounded
JSON, deserializes and validates it; it does not generate documentation.
Configuration instructions are maintained separately. Existing range tests
cannot demonstrate a shared definition source that is absent.

**Work needed / user decision.** Either retain the requirement and implement a
shared option catalog used by validation and a deterministic documentation
generator, with a generated-output drift check, or explicitly approve the
separate-maintenance model and reword the requirement. A catalog must represent
defaults and cross-field rules accurately; generating field names alone would
not meet the wording. No such scope change is decided here.

## ThreadSanitizer coverage

**Existing evidence.**
`owner_thread_serializes_concurrent_replays` in
[mover-store/src/tests.rs](../rust/crates/mover-store/src/tests.rs) launches 16
concurrent callers and checks one accepted job ID and consistent replay IDs.
It exercises existing concurrency, but a normal passing run is not race
detection. The production/qualification matrix in
[rust-ci.yml](../.github/workflows/rust-ci.yml) and
[the SLES driver](../scripts/check-rust-sles.py) run debug/release checks, not a
ThreadSanitizer tier. There is no separate sanitizer pass to cite.

**Test to add.** Add a CI job named `concurrent_claim_delivery_reload_tsan` in
that workflow, running applicable existing Store, API and TLS lifecycle
concurrency tests with ThreadSanitizer. First establish compatible Rust/std and
native SQLite/TLS instrumentation and document exclusions; uninstrumented native
dependencies cannot silently be counted as covered. Keep TSan separate from any
ASan tier and retain diagnostic failures. Toolchain and native-instrumentation
feasibility are part of this L-sized verification task; an unsupported target
requires an explicit revised strategy, not an automatic N/A decision. This tier
supplements both existing SLES modes and does not substitute for their ABI proof.

**Proposed disposition after evidence:** Tested only for the requirement's
concurrent-code scope when the enforced tier and its coverage support it;
limited instrumentation must be described as partial.

## Manager readiness and stopping

**Existing evidence.** `serve_inner` in
[lib.rs](../rust/crates/file-mover/src/lib.rs) prints `Ready on ...` and updates
the lifecycle. [control.rs](../rust/crates/file-mover/src/control.rs) exposes
the lifecycle to local status queries. The
[candidate service unit](../scripts/bundle/file-mover.service.in) uses
`Type=simple`; these paths do not notify a service manager of readiness or
stopping. Polling status is a different mechanism.

**Work needed / user decision.** Define and implement the supported manager
notification interface, align readiness with completed service startup, emit
stopping on the first stop transition and qualify both startup failure and
shutdown under the target manager. Preserve custody and the original shutdown
deadline. Alternatively the user must approve revising the manager-notification
requirement. Packaging and host deployment remain separate authorizations.

## Manager watchdog

**Existing evidence.** The request-driven `/healthz` path in
[lib.rs](../rust/crates/file-mover/src/lib.rs) and SSE keepalives in
[admin.rs](../rust/crates/file-mover/src/admin.rs) are not periodic liveness
signals to a manager. The candidate unit has `Restart=no` and no watchdog
interval. A watchdog test alone would have no emitter/restart integration to
exercise.

**Work needed / user decision.** Specify which loss of progress is a service
hang, implement bounded manager heartbeats and qualify detection and restart
behavior. In particular, an independent heartbeat must not falsely attest a
hung coordinator's progress. Restart/timeout policy must preserve actual-worker
lifetime exclusion and the first shutdown deadline; it cannot authorize killing
or adopting surviving workers or repairing stale sockets. The user must choose
the retained watchdog obligation or approve a scope revision before deployment
policy is implemented.

## Mandatory-access-control integration

**Existing evidence.** Destination staging and publication in
[transfer.rs](../rust/crates/mover-fs/src/transfer.rs) and
[manifest.rs](../rust/crates/mover-fs/src/manifest.rs) do not apply an explicit
final-destination SELinux context before publication. Filesystem inheritance
alone does not demonstrate the final-path label, especially when staging and
final parents have different policy. No qualified path-exact AppArmor profile
is supplied by the candidate unit.

**Work needed / user decision.** Retain and implement the target's default-label
lookup/application before final visibility, with safe failure before publication
and no source-context copying. Supply and qualify AppArmor access rules against
the actual service/worker, custody, state, credential and socket paths. Exercise
enforcing target policies and refusal paths. Platform policy support and any
dependencies require a separate implementation decision; accepting host defaults
or excluding a platform requires explicit user approval, not a Tested label.

## Hardened service unit

**Existing evidence.** The
[candidate unit](../scripts/bundle/file-mover.service.in) includes service
User/Group, empty capabilities, `NoNewPrivileges=yes` and `UMask=0077`. It lacks
the full required `ProtectSystem`, constrained `ReadWritePaths`, `PrivateTmp`
and `ProtectHome` settings and is explicitly not qualified production packaging.

**Work needed / user decision.** Complete the unit for approved provisioned paths
and qualify startup, credentials/reload, normal delivery and shutdown under its
actual restrictions. Account for private temporary-directory visibility and
worker paths instead of adding broad writable exceptions. Either retain this
shipping deliverable or obtain an explicit scope revision. Host administrators
still provision accounts, directories, mounts and units as recorded in
[AGENTS.md](../AGENTS.md); this document installs nothing.

## Endpoint-security policy verification

**Existing evidence.** Platform/startup checks in
[main.rs](../rust/crates/file-mover/src/main.rs) and
[lib.rs](../rust/crates/file-mover/src/lib.rs) do not query endpoint-security
on-access exclusions. Worker I/O errors cannot establish that a requested ePO
policy reached the host.

**Work needed / user decision.** Select supported products/versions and a bounded,
read-only query available to the non-root service account. Report per-managed-tree
covered, uncovered or unknown results with policy freshness/source, avoiding
secret output. Define unavailable/unsupported/stale-query behavior explicitly;
absence of a query is not proof that exclusions are active. Do not modify scanner
policy. The user must retain this platform integration or approve its revised
applicability; a test without a supported query cannot close the gap.

## NFS silly-rename artifacts

**Existing evidence.** Explicit producer file lists avoid recursive discovery.
`remove_empty_area` in [mover-fs/src/lib.rs](../rust/crates/mover-fs/src/lib.rs)
preserves a nonempty private directory on `NOTEMPTY`/`EXIST` rather than removing
unknown contents. This is existing preservation behavior to qualify, not proof
of complete `.nfsXXXX` tolerance. In particular, `discard_retained_source` also
checks object identity and post-unlink link count; its outcome with a real
silly rename must be observed, not assumed or bypassed.

**Test to add.** Add
`held_open_unlink_preserves_silly_name_and_original_custody` to the disposable
real-export cases in [nfs_runtime.py](../scripts/nfs_runtime.py). Use controlled
open/unlink operations that actually produce a silly-rename artifact, recording
which NFS client holds the handle and performs unlink; do not assume a second
client's open alone will produce it. Cover source, private custody and destination
directories as applicable, including restart and authorized fixture-only cleanup.
Check that unrelated artifacts are preserved and not adopted, normal listed work
can proceed, and cleanup does not turn an artifact into a false unexpected-entry
failure. Keep exact ownership, link-count and byte-integrity assertions. If the
case shows the implementation cannot meet the requirement, stop and reclassify
the demonstrated path as a feature gap before proposing a change.

**Proposed disposition after evidence:** at most Partly tested for a bounded
qualification-build/export matrix; name the remaining paths and profiles.
Production NFS is disabled, and a lab pass cannot establish production readiness.

## Server-side NFS durability

**Existing evidence.** The copy and publication effects in
[transfer.rs](../rust/crates/mover-fs/src/transfer.rs) sync staged data and
directories, reread staged bytes for verification, and sync publication before
recording completion. Missing fsync calls are not the gap identified here.
The [sync lab](NFS-SYNC-LAB.md) explicitly distinguishes returned WRITE/COMMIT
protocol facts and server-local tmpfs bytes from persistent-media/power-loss
durability. These limits are evidence against claiming the row already covered.

**Test to add.** Extend the existing real-export recovery driver
[check-nfs-server-recovery.py](../scripts/check-nfs-server-recovery.py) with a
case named `target_export_acknowledged_commit_survives_storage_recovery` and a
retained target-profile report. Qualification needs an authorized disposable
persistent backing store, recorded server/export/mount/cache policy, an
independent client and a recovery oracle for acknowledged bytes/manifests.
Distinguish service/server restart from storage/power-loss recovery: demonstrate
the selected failure model on the intended stack, and record untested models.
Existing protocol/VM-tmpfs experiments cannot stand in for this case. Keep
original custody and uncertain state intact if durability cannot be established.

**Proposed disposition after evidence:** Partly tested for the actual tested
server/export/storage/failure matrix; broader claims need corresponding evidence.
This is a qualification task for existing effects, not permission to run a fault
on operational storage. It needs separate target/lab authorization and cannot
alone enable production NFS, source deletion, deployment or close the FR gates.

## Completeness and limits

The index contains exactly the ten `Open` IDs in `TRACE-L2.md` at the stated
base. No row is proposed as already covered: nearby tests, console status,
partial unit hardening and earlier NFS experiments do not satisfy the missing
obligations. Six feature gaps go to the user; four verification gaps remain
backlog proposals, with platform prerequisites stated above.

Only documentation is added. No test, CI tier, dependency, host policy or runtime
behavior is changed, and no disposition or requirement is rewritten. No Rust,
SLES, sanitizer, fuzzing, security-policy or NFS qualification was run for this
triage. The separate decision sheet does not itself grant any approvals.
