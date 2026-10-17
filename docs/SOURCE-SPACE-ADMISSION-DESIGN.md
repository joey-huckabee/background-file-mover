# Configurable source-space admission policy

Policy recorded 2026-10-16. [Increment 36](RUST-INCREMENT-36.md) implements the
first local slice; validation results and remaining qualification are recorded
there. This refines L1-SYS-030 and the [transfer protocol](TRANSFER-PROTOCOL.md),
alongside existing job/byte retention limits. Production NFS/deletion remain off.

## Purpose and scope

When enabled, refuse a **new recording submission** if the authorized source
filesystem does not report the configured available-space margin. This limits
additional handoffs during a prolonged destination outage. Apply the same rule
when the destination is healthy; do not probe destination health to decide
whether source admission matters. It is a guard on admission, not a reservation
of future recorder capacity or a promise that existing work can finish.
It cannot stop the recorder or other clients writing files: rejected recordings
still occupy source space. Pre-recording capacity reservation or producer-side
flow control would be a separate contract, not a new duty after submission 202.

Files already exist on the source before submission. Claim relocation does not
copy another payload onto that filesystem or release the occupied bytes. Compare
actual reported availability with the configured margin; do **not** subtract
submitted sizes or existing source reservations a second time. A 100 GiB file
already present does not require 100 GiB of additional claim space. Metadata,
quotas and external writers can still cause a later claim operation to fail.

The guard must never delete retained data, weaken custody, reroute accepted jobs
or change delivery retries/review. Existing job-count and source/destination byte
reservation checks remain independent and mandatory, including when this guard
is off. Those checks can still stop a partial claim or new destination attempt.

## Configuration and explicit off switch

The optional startup object is `source_space_admission`. Omission is equivalent
to `{"enabled":false}` for compatibility. There is no per-request override and
no hot reload in the first slice; change configuration and restart normally
against the original state. All other configuration fields remain required.

Off, including on a previously enabled installation:

```json
{
  "source_space_admission": {
    "enabled": false
  }
}
```

Example enabled configuration fragment (10 GiB / 5% are illustrative values,
not a production sizing recommendation):

```json
{
  "source_space_admission": {
    "enabled": true,
    "min_available_bytes": 10737418240,
    "min_available_percent": 5,
    "max_sample_age_seconds": 5,
    "probe_timeout_seconds": 2
  }
}
```

| Field | Default / validation | Meaning |
|---|---|---|
| `enabled` | Boolean, false | False skips capacity probes, cache refreshes and capacity rejection for this feature. Normal source authorization/claim I/O and existing limits still apply. |
| `min_available_bytes` | Unsigned integer bytes, 0 through u64::MAX; default 0 | Absolute minimum reported available bytes. Zero disables this component. |
| `min_available_percent` | Integer 0–100; default 0 | Minimum percentage of reported total filesystem bytes. Zero disables this component. |
| `max_sample_age_seconds` | Integer 1–60; default 5 | Maximum coordinator-monotonic age of a sample when authorizing insertion of a new job. |
| `probe_timeout_seconds` | Integer 1–60; default 2, no greater than max sample age | Maximum wait for a probe result, not a kernel cancellation guarantee. |

When enabled, at least one threshold must be positive. Validate types, ranges,
unknown/duplicate fields and timeout/age relation even when disabled; a disabled
object with omitted fields is valid. Explicit `null`, negative/fractional values,
overflow, percent above 100 and enabled zero/zero thresholds are invalid startup
configuration. A syntactically valid threshold larger than the filesystem can
provide simply keeps new admission closed. There is no undocumented implicit
threshold, fallback-to-off on error or automatic threshold adjustment.

Disabling the guard takes effect only after the old process and its capacity
worker have confirmed exit. It does not authorize a second coordinator while a
blocked old worker still holds custody. It clears no existing job review,
deadlines, reservations, missing-file blocks or ownership/refusal evidence.

## Measurement and threshold decision

Probe through a supervised child using a descriptor for the validated enrolled
source root and the existing custody protocol. Do not run a pathname shell
`df`, walk submitted files or query the destination. Bind the result to that
source scope, current policy/process generation and probe sequence. Validate
custody/root observations before accepting a result. Confirm child exit before
making that sample eligible for admission or reusing its slot. A replaced or
unauthorized
root remains a custody refusal, not a reason to trust a new filesystem's space.

Use descriptor-based filesystem statistics, with these intended quantities:

```text
available_bytes = available_blocks * fragment_size
total_bytes = total_blocks * fragment_size
percent_floor = ceil(total_bytes * min_available_percent / 100)
required_available_bytes = max(min_available_bytes, percent_floor)
allow_new_job = available_bytes >= required_available_bytes
```

Use checked u128 intermediate arithmetic, exact integer rounding and no floats.
Compute the percentage via quotient/remainder if needed to avoid an overflowing
intermediate product; any unrepresentable result is Unknown.
Compare against the bytes available to unprivileged users, not privileged
reserved blocks. Zero available bytes is a valid low-space observation; a zero
fragment size, zero total, available blocks greater than total, unrepresentable
or unsupported counters are unknown. Never turn invalid counters into a pass.
The Linux [statvfs/fstatvfs documentation](https://man7.org/linux/man-pages/man3/statvfs.3.html)
defines the relevant counters and descriptor interface, and notes that field
meaning depends on the filesystem. Actual backend/API/features and old-target
symbols still need qualification; this design does not qualify a new dependency.

Both enabled thresholds must be met. Exact equality passes; one byte below the
effective threshold fails. There is no hysteresis or sticky low-space state in
the first slice: a fresh sufficient observation reopens new admission. Percentage
is based on total reported filesystem bytes, not total minus the retained ledger.
For example, total 1000 bytes, available 150, byte floor 100 and percent floor
20% means required 200 and refusal. Total 101, percent 5 means a 6-byte floor.

Successful statistics are observations, not allocation locks. Quotas, inode
exhaustion, thin provisioning, server caches and concurrent/external writers can
make a nominal pass insufficient. Byte checks do not qualify inode/quota/storage
durability protection. Continue normal effect checks and conservative failures.

## Admission, replay and partial handoff

1. Validate caller/request and source scope with existing safeguards. Identify
   the stable generator/submission key before capacity probing or new-job writes.
2. If it already exists, compare the original submission. Identical replay uses
   the original job and pinned policy; changed content remains 409 conflict.
   Neither low/unknown space nor a changed guard setting gates this replay.
   Incomplete claims still obey existing missing, reservation, size and custody
   checks; fully claimed replay still validates handoff before returning 202.
3. For a new key with the guard enabled, obtain a valid fresh source observation.
   A recent matching sample can be shared by concurrent requests. A low sample
   refuses admission; an unknown, expired or timed-out sample cannot authorize it.
4. Serialize the final new-job decision with the existing SQLite owner. Recheck
   the key first: a duplicate accepted in the meantime gets normal replay or
   conflict even if this request's capacity result refused. For a still-new key,
   check freshness and ordinary limits, then persist acceptance/path reservations
   atomically. No filesystem call or probe wait occurs in that transaction.
5. Only after durable acceptance, perform existing claim intent/effects/receipts.
   Return submission 202 only after all-file claim confirmation. Capacity can
   drop after insertion; that recording is now existing work and must remain
   recoverable with its same ID. Do not reapply this new-key gate between files.

A low/unknown rejection creates no job, path reservation, missing deadline,
claim intent or filesystem allocation. It releases no producer paths. An
identical recorder retry may later be accepted after a fresh sufficient sample;
the recorder keeps its original ID/body and paths unchanged until submission 202.
If a response is lost, retry that same ID because acceptance might have committed.

This requires an explicit replay-aware acceptance boundary; it cannot be bolted
on after today's `Store::accept` insertion. The preliminary lookup is advisory:
the final serialized operation must repeat replay/conflict checks before either
refusal or insertion. Check sample age at the serialized insertion decision and
abort/retry if it has expired while queued. A sample never reserves payload
bytes, so concurrent admissions do not each subtract the already present payload.
Existing transactional job limits and claim/transfer byte charges still serialize.

## Bounded probing and restart

At most one capacity child per configured source scope may be alive, with bounded
request admission/coalescing. Do not create a capacity child per HTTP request.
Reserve the existing claim/reconciliation paths so a stuck sampler cannot occupy
their worker slot or block identical replay, delivery, health or operator status.
No filesystem probing runs in the API, status handler or SQLite owner.

Timestamp each dispatch with the coordinator's monotonic clock. Age includes
child execution, IPC and queuing; require a reply before the probe timeout and a
still-fresh result (age no greater than the configured maximum) at the new-job
decision. Discard late, wrong-sequence,
wrong-root or old-generation replies. Never use wall time to extend freshness.
No persisted space reading survives a restart or configuration generation change.
Implementation uses nonblocking sampler demand plus at most two asynchronous HTTP
waiters. A cold new-key request can wait for the shared probe and recheck acceptance
once, within the existing total ten-second POST handoff budget. Claim/database
owners never wait for the probe. Excess waiters, missing/error/late observations
return retryable unavailable. Low/failed results are cached until expiry. This
avoids requiring recorder retries faster than the sample age: a healthy cold or
expired sample can be refreshed and used within the same request. Notify
registration and completion are checked together to avoid a lost wakeup.

On timeout/error, new-key requests receive a retryable unavailable result.
Request termination when appropriate, but retain the worker slot/custody until
confirmed exit. A timeout/SIGKILL is not proof an NFS call stopped. Do not spawn
unbounded replacements, let a late sufficient reply reopen admission or make
normal shutdown/takeover claims stronger than existing supervision permits.
Keep bounded demand-triggered refresh; no background polling is required when
there are no new submissions. Periodic monitoring and jitter can be later work.

After matching-state restart, enabled guard starts without a sample and needs a
fresh one for a new key; accepted work bypasses this guard. Turning it off needs
no space sample. Raising thresholds can refuse new keys but cannot retroactively
revoke acceptance, reset review or release reservations. Source enrollment and
schema migration safeguards remain mandatory.

## API and operator visibility

Implemented in increment 36 for the local slice; consult its gate results:

| New-key result | HTTP / error | Recorder action |
|---|---|---|
| Below either configured margin | 503 `source_space_low`, `retryable:true` | Keep paths unchanged; back off and retry the identical submission. |
| Cannot obtain valid fresh measurement | 503 `source_space_unavailable`, `retryable:true` | Same retry rule; operator checks authorized storage and probe diagnostics. |
| Guard off / valid sufficient observation | Continue normal acceptance/claims | Existing failures still apply; only submission 202 releases paths. |

New-key guard refusals have no job ID and `source_paths_released:false`. Existing
validation, source custody, `submission_conflict`, `source_reserved`,
`retention_capacity`, missing-file and delivery errors keep their meaning. This
guard creates no new per-job ReviewRequired state or operator reset endpoint.

The **global** retention response adds cached
`details.source_space_admission`: effective policy, state (`Disabled`, `Unknown`,
`Sufficient`, `Low`), observed available/required bytes or null, monotonic sample
age or null and a bounded reason for Unknown. Observed/required byte values are
decimal strings; the effective `policy` mirrors the startup configuration types.
Unknown covers no result, expiration, failed or timed-out probe. Reading it never
starts or waits for a probe; lack of a new request can leave it Unknown after
expiry until another new submission requests refresh. Disabled reports null
observations. This extra observation is not merged into `global_headroom` and
does not change `filesystem_inspected:false` for the reservation ledger: label
the separate child observation explicitly with its scope/age. Per-job status,
retry codes/epochs and historical source accounting are unchanged.

Do not publish a successful health request, capacity sample or larger configured
limit as proof of safe physical capacity. Explain current guard settings at
startup and preserve bounded operation/errno diagnostics without private paths.
If low space persists while source deletion is disabled, delivery commitment
alone will not reopen admission. Operators need approved additional capacity or
a separately implemented cleanup policy; the recorder cannot repair retained data.

## Acceptance scenarios required before implementation is called supported

These are acceptance obligations, not blanket qualification claims. The
increment-36 mapping below distinguishes implemented tests from remaining storage/
concurrency evidence. Keep these IDs as qualification expands.

| Case | Scenario | Required observable result / evidence |
|---|---|---|
| SA-01 | SC-075: omitted object, explicit false, or enabled then disabled on restart | Existing behavior retained; no feature capacity child/statistics calls or capacity refusals while off. Existing count/byte limits and unsafe-root refusals still apply. |
| SA-02 | SC-075: malformed types/ranges/duplicates/unknown fields, null, enabled zero/zero | Startup rejects clearly; no listener or job effects. Valid disabled omitted-threshold object accepted. Test u64 boundary and timeout/age relation. |
| SA-03 | SC-076: bytes-only, percent-only, both and rounding | Deterministic arithmetic tests cover equality, one below, max-of-two, total 101 at 5%, zero availability and large counters; no floats, unchecked overflow or double payload charge. |
| SA-04 | SC-076: fresh source below margin, destination healthy or unavailable | New key gets exact low-space 503/no job/release. All tables and producer/private namespace contents remain unchanged. |
| SA-05 | SC-076: capacity returns | Same ID/body becomes eligible on fresh sample, claims all files and gets 202 without operator reset; no sticky review. Nested/empty files and omitted/asserted sizes preserve semantics. |
| SA-06 | SC-077: error, invalid counters, stale sample, unsupported statistics | New keys get unavailable 503, never admission on unknown. Status explains bounded reason/age. Valid zero availability remains Low, not Unknown. |
| SA-07 | SC-077: child stalls or dies; late/forged reply | Controlled blocked child times out request wait, no replacements while alive, bounded memory/queue; health/status, existing-key replay and delivery remain usable. Late/wrong root/sequence/generation results never authorize insertion. |
| SA-08 | SC-078: fully claimed same-key replay while Low/Unknown | Original job/202 after normal handoff validation; reused producer path untouched; no probe required, no duplicate job or new payload reservation. Changed content remains conflict. |
| SA-09 | SC-078: partially claimed replay while Low/Unknown | Prior claims preserved, remaining claim reconciliation can proceed without this guard. Existing byte limits/missing review/custody can still refuse; never falsely release paths. |
| SA-10 | SC-079: concurrent same key and changed-body same key | One durable job at most; final transaction resolves replay/conflict even if another request has a low/expired result. No orphan namespace from guard refusal. |
| SA-11 | SC-079: many distinct keys share sample; SQLite wait expires it | Bounded single probe, normal transactional job/byte limits, expired result cannot insert a new key. Queue saturation remains bounded/retryable; no per-request process burst. |
| SA-12 | SC-080: crash before insert, after accept, during partial claim | No new guard state to recover before acceptance; after acceptance same-key recovery bypasses guard and keeps existing reservations/intent/receipts. No deletion, false 202 or acceptance revocation. |
| SA-13 | SC-080: restart/threshold change/clock jump | No old sample reused; new keys need fresh monotonic evidence when enabled. Existing review/deadlines/audits unchanged; off bypasses only this guard after confirmed old-worker exit. |
| SA-14 | SC-081: full filesystem reports below margin; sampling passes but claim later gets ENOSPC | Refusal before insertion in the first case; normal partial-effect preservation/reconciliation in the second. No promise that a sample reserves metadata, inodes or quota. |
| SA-15 | SC-081: retained committed source, old destination partials, shared source/destination filesystem | Source payload counted once in actual availability; ledger still charges its defined reservations/each attempt. Commitment does not pretend source bytes were freed. External consumption remains visible only through later samples. |
| SA-16 | SC-077/081: mount disappears or authorized root changes | Never sample a fallback mount and authorize it. Existing binding refusal and original-state preservation remain in force. Capacity guard off does not bypass them. |
| SA-17 | SC-075–081: API/status contract | Exact new codes, no-job/release flags, cached-only global status and age expiration, command/retry epochs unchanged, no recorder duty after 202. Label observations separately from ledger accounting. |
| SA-18 | SC-075–081: compatibility and storage qualification | Every implementation build/test through GNU/glibc-2.22 zigbuild, ELF audit and exact pinned SLES userspace execution. Controlled filesystem and qualification-only NFS blocked-statistics/capacity cases; no real SLES host requirement. Record quota/block-device/inode and old-kernel/fencing gaps separately. |

## Increment boundaries

Increment 36 implements the first local configuration/decision/admission/child/
visibility slice together. [Increment 38](RUST-INCREMENT-38.md) adds native
bounded tmpfs source depletion/restoration on the retained NFS fixture. Next
qualify blocked or changed-root behavior and remaining storage limits as
appropriate. Keep each
added scope gated on its own SA evidence; do not enable a partially enforced
option or start another package experiment. Production NFS/deletion stay off.

Per-generator margins, inode thresholds, quota-aware adapters, physical-space
reservations, hysteresis and live configuration are future extensions. No
schema change or new crate is authorized merely by this design; any implementation
need must carry its own migration/dependency and compatibility evidence.

## Acceptance evidence through increment 38

Read each increment's final gate results before treating tests as passing. This
mapping does not label every planned scenario fully qualified.

| Cases | Implemented checks | Remaining qualification |
|---|---|---|
| SA-01/02 | Default-off/explicit-off policy and API restart; strict deserialization/ranges; disabled cache never sends work; old safety/ledger suite retained. | Deployment configuration/runbook coverage as supported environments expand. |
| SA-03/04 | Exact integer boundaries/rounding/max counters; native source sample refused by an above-capacity configured floor; no job/private claim created. Increment 38 adds native bounded server tmpfs fill to 1 MiB below a fixed 4 MiB floor, no job/claim/path release. | Physical-disk/quota and metadata-reserve sizing. |
| SA-05 | Fresh native sufficient sample, configurable threshold restoration across restart, nested/empty automatic delivery and cold/expired-cache acceptance without fast retry. Increment 38 restores native bounded tmpfs capacity and admits the identical refused ID without configuration change/restart. | Physical disk/quota and external-writer/storage races. |
| SA-06/07 | Invalid counters, stale/pending cache, wrong/mixed replies, synthetic unavailable and a paused real child before statistics; deadline termination and responsive replay/health. | Native unsupported-statistics return, hard-NFS blocked/in-flight calls, prolonged unreapable child and export replacement. |
| SA-08/09 | Claimed replay under Low/Unknown; partial replay with no sample and under Low, prior claims/source reuse preserved; transaction replay precedes all refusal permits. Increment 38 adds actual NFS claimed/partial replay and commitment while natively Low, preserving reused producer paths. | Broader partial-effect/space exhaustion combinations. |
| SA-10/11 | Eight concurrent replay/conflict/refusal store requests, SQLite-lock wait expires a permit, bounded async notification/waiter tests and coalesced cache demands; existing serialized job/byte limits. | Flooding concurrent new/replay request queues under real blocked statistics. |
| SA-12/13 | Original-state restart/threshold/off, no saved sample; accepted identity survives an unavailable gate on reopened state. Increment 38 adds unchanged-policy/PID live capacity restoration. | New physical probe/acceptance crash matrix and actual NFS shutdown behavior; wall-clock jumps do not extend monotonic cache age by construction. |
| SA-14–16 | Existing conservative effect/custody suite retained; native same-filesystem source/destination delivery with committed-source ledger retained. Increment 38 adds bounded tmpfs source fill and retained claimed-source/producer-reuse checks with local destination. | Inode/quota/metadata failures, physical-disk source fill, external-write race and changed-export measurements. |
| SA-17 | New low/unavailable no-job responses, strict conflicts/replay, cached-only global view and expiry, per-job fields unchanged. | Broader documentation examples as storage qualification expands. |
| SA-18 | Required production and qualification GNU/glibc-2.22 SLES gates; see increment results. Increment 38 adds native capacity fixture evidence with exact audited artifacts. | Hard-NFS blocked statistics, quota/physical disk, old kernel/CPU and independent fencing. |
