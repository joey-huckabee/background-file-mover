# Rust increment 36: default-off source-space admission

Implementation on `feature/rust-transfer-coordinator`, 2026-10-16. Implements
the first local slice of [the policy](SOURCE-SPACE-ADMISSION-DESIGN.md).
Final-source validation results are recorded below.
Production NFS and source deletion remain disabled. Schema 11, binding version 3,
persisted receipt version 1 and delivery session version 2 remain unchanged.
No Cargo dependency/feature/lockfile changes.

## Behavior

`source_space_admission` is optional and defaults off. Enabled policy accepts
configurable available-byte/percentage margins and bounded sample age/probe
timeout. Both threshold components must pass. Invalid types/ranges/duplicates,
unknown fields, null and enabled zero/zero thresholds are rejected. Disabling
this guard does not disable existing job/byte reservation limits or custody.

A new submission triggers one background sampler when needed. At most two HTTP
requests can await it asynchronously and recheck acceptance once within the
existing total ten-second handoff budget. A healthy cold/expired observation can
therefore admit within the same request, without requiring rapid recorder retries.
Missing/error/late results or full waiter slots return retryable 503
`source_space_unavailable`. Recorder retry retains the same ID/body. Low space returns 503 `source_space_low`, without a job ID or source
release. No claim/job/reservation is created by either refusal. Fresh sufficient
space permits normal acceptance and all-file handoff; 202 retains its meaning.
No destination probe or incoming-payload subtraction is added.

Existing keys bypass measurement entirely, including partial claims. Changed
content still conflicts. Final acceptance repeats replay checking inside the
SQLite immediate transaction before applying an observation permit, so an
already accepted duplicate wins over low/expired/unknown results. Permit freshness
is checked there, after waiting for SQLite. Normal claim/transfer limits and
missing/custody/review behavior remain in place. No new durable schema is needed.

A dedicated bounded sampler thread supervises at most one source child, using
existing inherited lock descriptors and paired source authorization. Descriptor
filesystem statistics run between custody checks in the child, not API/status/
SQLite code. Root identity is checked around the read. Integer arithmetic uses
unprivileged availability and rounded-up percentage of total capacity without
counting already-present files again. Invalid counters become unavailable.

Dispatch age is monotonic and includes IPC/queue time. A deadline requests child
termination, but exit/reaping must be confirmed before its slot is reused. A late
or mismatched private reply never supplies a permit. This is not a new guarantee
that blocked NFS operations can be cancelled. Cache/observations are process-local;
restart or configuration changes require fresh measurements for new keys.
Unavailable results are cached until sample expiry to avoid per-request child
replacement. Expired busy probes remain unavailable without another child.

Global retention adds cached `details.source_space_admission` (effective policy,
state, available/required decimal byte strings, age and bounded reason). Reading
status never triggers a probe. Per-job status/epochs and ledger headroom remain
unchanged; `filesystem_inspected:false` still describes reservation accounting,
while the separate observation identifies `SourceRoot` / `supervised_child`.

## Tests and evidence scope

New tests cover pure arithmetic/rounding/u64 extremes, strict default-off policy,
coalesced/stale/timeout cache decisions, private reply scope/version/sequence and
mixed outcomes, replay-first atomic refusal with no inserted rows, permit expiry
while waiting for SQLite, native local capacity measurements, low-space refusal,
partial/claimed replay, conflicting bodies, restart/threshold changes/off,
nested/empty automatic delivery and retained source accounting.

Qualification-only `FILE_MOVER_QUALIFICATION_SOURCE_SPACE_FAULT=unavailable`
returns a source probe I/O error; production ignores it. The retained
`source_space_statistics` pause uses existing local rendezvous controls before
the native statistics call. Tests observe the actual child, bounded request
responses, no repeated rendezvous before expiry, retained state and responsive
existing replay/health. Production ignores the pause selector too. A paused
process is not a hard NFS call; this is synthetic failure/supervision evidence.

SA cases are mapped in the policy; no physical source-fill, quota/inode, in-flight
NFS statistics, independent fencing, power-loss or old-kernel qualification is
claimed. Existing source bytes remain retained after delivery; a good sample
cannot reserve capacity against external writers or make cleanup safe.

## Validation

Final production gate `20261017T000923Z-833766e7` PASSED with exit 0: **177 tests
per debug/release profile**. Final qualification gate
`20261017T000924Z-2ecefab1-nfs-qualification` PASSED with exit 0: **178 per profile**.
Both passed GNU/glibc-2.22 zigbuild, formatting/Clippy, all 20 executable audits
per mode, six negative ELF controls and exact execution in pinned SLES 12 SP5
userspace. Highest required GLIBC remains 2.18; the dependency graph remains 42
external packages. Both completed container cleanup without error. See the saved
[production report](RUST-SLES-EVIDENCE.json) and
[qualification report](RUST-SLES-QUALIFICATION-EVIDENCE.json). All artifact hashes
match those reports; no host-only tests were substituted.

All 58 current Rust source files match both final archives. Dependency manifests/
lockfile are unchanged. Documentation checks retain all 81 scenario IDs, six DOC
keys and the 18 SA obligations; local Markdown links, JSON examples, whitespace
and trace-matrix checks pass. Source stat/config types and cached observation
fields are described separately in the operator guide.

No new NFS fixture was run: qualification-feature local target tests are not
in-flight hard-NFS statistics evidence. Containers share a modern kernel/CPU;
physical source-fill, quotas/inodes, power loss, old kernels and independent
fencing remain unqualified.

## Development finding: cold-cache retry liveness

The first implementation returned unavailable immediately on a cold probe and
required a later request to find the cached result fresh. Review found that a
recorder retry interval at least as long as sample age could miss every result.
The intermediate production gate `20261016T234448Z-719497b9` passed 174 tests per
profile, but that suite lacked this liveness case; it is superseded for the final
source. Its qualification companion `20261016T234542Z-ebf963f5-nfs-qualification`
also passed its intermediate 175-test-per-profile suite, but is not final
implementation evidence.

Added bounded asynchronous HTTP waiting and one acceptance recheck, with at most
two waiters sharing a probe and the same total ten-second handoff budget. There
is no waiting in claim/SQLite owners and no unbounded replacement. Added direct
cold/expired-request acceptance tests, actual concurrent store races and async
notification completion/slot tests. The paused-child API test now keeps the new
HTTP request pending while checking existing replay and health. Partial-claim
recovery is explicitly checked while Low as well as with no sample. Final gates
must use the corrected source snapshot; no new dependencies/features are needed.

Review also restored the existing replay/storage error mapping in the advisory
lookup: only actual replay conflicts become submission conflicts; blocked/corrupt
state and other storage/protocol failures retain their prior response classes.
Intermediate corrected-liveness runs `20261017T000119Z-33ae7fa9` and
`20261017T000117Z-63f45582-nfs-qualification` precede that final mapping adjustment.
Only the final-source runs above are release evidence for this increment. All
intermediate runs finished and cleaned up; none is reported as final-source
qualification. There were no failed Rust compilation/test gates; the initial
sandboxed engine connection failed before compilation and was rerun through the
authorized Podman connection.
