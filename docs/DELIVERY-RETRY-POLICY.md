# Delivery retry policy and staged rollout

Initial policy recorded 2026-10-16. [Increment 33](RUST-INCREMENT-33.md) implements
only confirmed payload-copy ENOSPC backoff. This is a narrow scheduling change;
existing claim, verification, publication, custody and repair rules still apply.

## Current rules

| Situation | Scheduling and review | Evidence required |
|---|---|---|
| ENOSPC from writing an owned payload copy | Retry after 30 seconds following persisted failure 1 and 60 seconds following failure 2. Persist failure 3 and require audited operator resume. | Native copy-write operation and numeric ENOSPC, failed Payload/Intent assignment, no success receipt; typed private worker hint. |
| Destination confirmed unavailable before allocation | Existing five-second deferral; no new failure charged. | Existing destination-open result; never infer absence from an arbitrary error. |
| Destination binding/authorization refused | Existing immediate review. | Existing binding validation and typed refusal. |
| Other I/O, identity/digest refusal, unreceipted allocation or ambiguous namespace/manifest effect | Existing bounded reconciliation attempts at five seconds; review after three persisted failures. No new error-based permission to retry an effect. | Original durable intent, custody and content validation remain necessary before any effect or transition. |
| Hard NFS call still blocked / no worker reply | Existing bounded worker/supervision behavior; no capacity hint, replacement timer or new dispatch permission. | A timeout or diagnostic is not an effect result or fence. |

The capacity schedule follows the total existing failure count, not a separate
streak. A generic failure followed by capacity failure is failure 2 and waits 60
seconds; changing classes does not reset the three-failure budget. Existing unavailable-destination deferrals retain the prior
failure count/cause but can use their five-second deferral once the previous
deadline has expired; the retained code is not a universal delay selector. Successful
commitment can retain the previous retry row as historical status evidence;
Committed state and the manifest exclude further delivery scheduling.

`details.delivery_retry.code` adds `destination_capacity_requires_review` for
this class. Before three failures, condition remains Retrying; at three it becomes
ReviewRequired. Status shape and other codes are unchanged. Failure 3 records a
120-second deadline, but **that deadline does not allow another automatic attempt**:
the failure count excludes the job until audited resume. The threshold remains
three persisted failures; it is not a guarantee of only three physical attempts
across crashes before a failure result is committed.

Restore approved capacity and preserve original state/source/partials. If capacity
returns while the job is waiting after failure 1 or 2, the existing scheduler
retries at the saved deadline and can commit without an operator command. It does
not probe capacity continuously or bring the deadline forward on restoration.
If the job is already in review, restoration/restart alone does not clear it;
use the existing audited resume/replay workflow. Resume resets the budget only
once per accepted command; replaying an old resume does not reset a later failure.
Do not delete old attempts, final names or receipts to bypass review.

## Persistence and failure boundary

SQLite atomically updates the capped count, classification code and absolute Unix
seconds deadline in the schema-11 retry row. Intervals start from the
coordinator failure-handling timestamp passed to SQLite; an unusually delayed
state write can commit an already-due deadline. Restart preserves a recorded
pending deadline and reviewed state; it does not recompute a fresh delay. Negative
times are rejected and additions saturate at i64::MAX. Existing wall-clock deadline
semantics remain; clock-jump handling and jitter are future work.

A crash before SQLite records a returned failure can still lose that failure count
and allow the existing intent-recovery path to run again. This increment does not
close that pre-existing dispatch/result-persistence gap. Payload attempt/admission
limits remain in force. A failed SQLite update stops delivery dispatch rather than
continuing without durable scheduling evidence.

The filesystem adapter exposes a structured native failure fact. Private delivery
session protocol version 2 carries one optional failure enum; unknown variants,
wrong sequence/version, success receipts mixed with the hint, missing/invalid
bounded diagnostics and hints outside Payload/Intent are rejected. Diagnostic text
is never parsed to classify a failure. Transfer assignment encoding and persisted
receipts remain version 1 and source/destination binding version 3 is unchanged.
Schema 11 transactionally widens the allowed retry-code vocabulary; it does not
reclassify or reset any existing row. Writable startup migrates schema 10, retaining
original jobs/claims/transfers/manifests, enrollment/ownership, observations, pending
reservations/deadlines and audit records. Read-only inspection refuses an old schema
until upgrade. Older binaries refuse schema 11; no reverse migration or supported
backup-restoration/rebind workflow is introduced. Parent and child must use the same service executable/protocol.

Only payload copy-write ENOSPC qualifies. Source reads, file/directory sync,
allocation, permissions, verification, relocation and manifest failures do not get
this classification even if they report ENOSPC or have similar diagnostic text.
The hint authorizes only a scheduling choice. A partial write can exist; the
normal retry preserves that attempt and starts a new owned copy from retained
source. No bytes are trusted as a resumable prefix, and no source is deleted.

## Future policy decisions

Keep broader behavior unchanged until separately designed and qualified:

- Classify temporary transport/server errors and persistent permissions/configuration
  errors using operation and phase evidence rather than errno alone.
- Decide bounded jitter, configurable intervals and any longer capacity-wait policy.
  More retries need partial-attempt accounting, admission limits and free-space margins.
- Qualify physical block-device/quota exhaustion, in-flight RPC ambiguity, server EIO,
  power loss and independently enforced fencing before expanding production scope.
- Define clock-anomaly handling and durable assignment/result reconciliation.

Production NFS and deletion remain disabled. Qualification uses the required GNU/
glibc-2.22 zigbuild/ELF/SLES gates and retained container NFS fixture. Consult the
increment for actual passing evidence; synthetic errors do not establish server
hardware behavior.
