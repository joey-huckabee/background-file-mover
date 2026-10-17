# Fenced enrollment and recovery contract

Design baseline recorded in [increment 26](RUST-INCREMENT-26.md).
[Increment 27](RUST-INCREMENT-27.md) implements the unused-scope setup and matching
restart slice; consult its validation/scope before treating a case below as
qualified. Populated-state rebind, takeover and independently enforced fencing
remain future work. No production NFS approval is given by this contract.
Read [root ownership](ROOT-OWNERSHIP-DESIGN.md) for the separate exclusion limits.
Generator registration and its one-time setup key are separate, deferred work.

## First-release ownership boundary

The [increment 41 contract](NFS-OWNERSHIP-FENCING-CONTRACT.md) narrows the first
release to a fixed same-host/local-state owner and proposed inherited local guard,
with bounded configurable shutdown and qualified original-state reconciliation.
SH-01–14 remain pending. It supersedes a blanket external-provider prerequisite
for that profile, without claiming that process exit or a local lock settles NFS.
The stronger re-enrollment/takeover obligations below remain deferred and are
not satisfied by the local guard or its 60-second timer. No re-enrollment command,
proof-import API or persisted format is implemented. Fencing alone never permits
changed pins, data adoption or stale-database restoration.

## The gap this must close

The schema-9 `source_enrollment` reviewed in increment 26 binds a source policy and observed identity
to `metadata.instance_id` inside one local SQLite database. The protected source
marker names the permitted coordinator, but does not name that database instance.
An empty database can enroll after acquiring custody, even if a different
database previously used the source. This follows from `Store::enroll_source`;
no new populated-source, independent-state NFS experiment is claimed here.

Increment 25 excludes selected concurrent owners and surviving workers. It does
not bind the root permanently to the original state, establish that abandoned
effects have finished, or authorize a different database after lock release.
Keep the original state with its source scope. An empty database, a restored old
snapshot, or the same coordinator label is not permission to adopt leftovers.

## Keep three operations separate

| Operation | Required authority | Intended outcome |
|---|---|---|
| First enrollment | Explicit provisioning of a genuinely unused scope and a new state instance; exclusive custody and no outstanding writers/effects | Bind the scope to that instance before accepting work |
| Ordinary restart | Same instance, completed enrollment, matching root/policy/observations and qualified custody | Continue recorded jobs using existing recovery rules |
| Re-enrollment | Explicit maintenance with an independently established fence, original state and reconciled effects | Change only the approved binding observations/policy; preserve job identity and evidence |

Initial implementation should support first enrollment and matching restart
only. Re-enrollment of existing/legacy jobs, recovery from a lost database and
transfer to another coordinator remain blocked until their own implementation
and qualification. Do not introduce a general `--force`, delete-state remedy,
automatic marker repair, or remote recorder enrollment endpoint for these cases.

## Persistent source ownership

Use a separately versioned, protected source enrollment receipt under
`.file-mover`, paired with a local SQLite enrollment record. Increment 27 adds
that receipt with schema 10 and version-3 binding markers. The empty
`coordinator.lock` must not be repurposed or rewritten by normal startup.

The pair must identify the enrollment operation, original state instance,
permitted coordinator, approved source binding and observation format/version.
Persist the exact agreed receipt bytes locally so retries cannot regenerate a
different record. Use bounded parsing and strict version/unknown-field rules.
Keep the root receipt distinct from the changing job inventory; do not rewrite it
per recording. IDs are correlation evidence under trusted provisioning, not
secrets, authenticated export identity or storage fencing tokens.

Normal startup must require an exact active pair. A root receipt naming another
state instance refuses startup even when the coordinator label matches and the
lock is available. A missing root receipt with previously enrolled state must
refuse, rather than recreate it. A new database plus an existing receipt must
refuse, rather than import jobs or reset the root. Existing protected namespace
objects must never be classified as disposable merely because SQL has no jobs.

Copying a database copies its instance ID. Therefore this pair cannot distinguish
cloned state or detect rollback to a snapshot that retains the enrollment record.
Clones need exclusion and fencing; restoring backups needs independent recovery
evidence covering work since the snapshot. Matching IDs are insufficient for
either. Neither case belongs to ordinary restart.

The first implementation must refuse any preexisting transfer/claim namespace
for first enrollment. Determining that a scope is genuinely unused requires
exclusive, approved provisioning with no untrusted writers; a directory listing
alone is insufficient. Files still in producer-owned input directories are
allowed only under the existing handoff contract. A shared destination also
needs an ownership/allocation policy that prevents collisions with prior state;
this source receipt alone does not establish destination ownership.

## Enrollment cannot be one cross-system transaction

SQLite and source storage cannot commit atomically. Use an explicit, resumable
operation whose partial states refuse readiness and payload admission. All root
I/O stays in supervised filesystem children; a pending operation does not justify
unbounded worker replacement when NFS blocks.

| Durable state | Required behavior |
|---|---|
| No operation and no root receipt | Ordinary startup refuses enrollment-required. Explicit first enrollment may proceed only after unused-scope checks and exclusive custody. |
| Local prepared operation; no root receipt | Remain unready. Retry only that operation after restoring and validating the same custody and provisioning prerequisites. Do not infer absence from an unavailable mount. |
| Local prepared operation; exact owned receipt exists | Reconcile that operation's object ownership and synchronization before recording it active locally. Equal text alone is insufficient ownership evidence. |
| Local prepared operation; foreign/malformed/unproven receipt | Preserve both sides and block for review. Never overwrite the receipt. |
| Active local record and exact validated root receipt | Permit matching restart only after normal binding/custody checks. |
| Active local record with missing/different receipt, or root receipt without its original local record | Preserve state/data and refuse readiness. No automatic rollback, adoption or repair. |

Write the local prepared intent durably before an exclusive root receipt effect.
The filesystem implementation must persist enough allocation identity to recover
a crash between object creation and the SQL result; if ownership is ambiguous,
block instead of treating matching bytes as proof. Synchronize the owned receipt
and namespace before marking the local operation active. Keep the same operation
ID and exact payload on retry. No claim/copy/publication assignment can be issued
between preparation and activation. Test every intent/effect/sync/result boundary
before shipping this state machine; this document does not settle the low-level
receipt allocation/reconciliation strategy.

## What counts as a fence

Before re-enrollment or takeover, the recovery authority must establish that all
previous coordinators, assigned workers and already issued filesystem operations
can no longer mutate either affected source or destination scope. Cover old
credentials, retained descriptors and already accepted requests as applicable to
the selected storage and host controls. Keep that exclusion in force through
reconciliation and activation. Taking a new advisory lock or observing a process
exit does not by itself satisfy this condition.

A future maintenance record must identify the exact old/new scope and state,
reason, operation ID, independently obtained fence evidence, fence mechanism and
qualification reference, uncertain assignments, reconciliation results and the
authority that permits activation. A user-supplied `fenced: true`, timestamp,
heartbeat expiry, receipt generation or manually entered evidence reference is
an audit assertion, not machine enforcement of that fence. Do not expose a
mutating recovery command until the selected mechanism and how it is enforced
have been qualified. No host/storage fencing mechanism is selected by this
increment; production NFS remains blocked on that decision and qualification.

Known or suspected loss of lock/custody must stop new authorizations for the
affected scope. Preserve uncertain assignments and withhold unproven claim 202
or commitment. Do not redispatch effects just because retry limits elapsed or a
replacement worker starts. Previously valid 202 responses remain the producer's
path-release contract; recovery must use private claims, not newer producer data.
Already committed recordings remain consumer-visible; a later incident cannot
retract their manifests. Existing effects might still finish, which is why an
admission stop and signals are not themselves a fence.

Successful repeated `flock` acquisition is not proof that ownership was continuous
through a partition or server lock recovery. Current validators perform that
call, but no complete lost-lock detector is implemented. Any future diagnostic
must distinguish an observed refusal/error from undetectable historical loss.
There is no safe general promise that every lock loss is observable before the
next payload effect with the current advisory-lock protocol.

## Narrow scope of future re-enrollment

Re-enrollment changes authorization, not the meaning of a recording. Preserve
submission/job IDs, exact accepted source names, pinned destination routes,
claim/transfer intents, sizes/digests, manifest bytes and retention policy.
A destination move is a separate migration; changing startup routing must not
redirect accepted jobs. A source observation change does not prove that private
claims on a replacement export are the original objects.

Before activation, reconcile every uncertain assignment and the custody of each
affected object under the independent fence. An unavailable destination or lost
operation evidence leaves the operation pending; do not erase pins to make it
pass. Without the original usable database, stop at the deferred recovery/repair
boundary. Do not recreate producer paths, overwrite files or delete private
sources/staging as part of enrollment.

## Required acceptance cases

This is the acceptance backlog, not an aggregate passing-results claim. Increment
27 records the implemented subset and its actual evidence. Run Rust cases through both mandatory
SLES gates; run filesystem/NFS cases with the exact audited artifacts in the
retained fixture. Keep production NFS/deletion disabled throughout.

| Case | Required evidence |
|---|---|
| Unused scope with explicit initialization | One active paired receipt/state; no producer path or payload changes; no startup auto-enrollment |
| Matching restart | Same instance/operation and recorded jobs, successful normal recovery |
| Fresh database using the same coordinator label after prior work | Refusal before payload/admission, even after clean lock release |
| Missing/foreign/extra-link/unsafe receipt | No automatic creation, replacement or deletion; preserved original state and data |
| Death at each prepare/create/sync/activate boundary | No readiness during mismatch; owned idempotent continuation or explicit review |
| Replaced root/export or changed strict observation | Refusal; matching text/hash does not auto-rebind |
| Database clone or stale backup | No claim of protection from instance IDs alone; fence/reconciliation required |
| Partition or lock reclaim with old worker surviving | Observe possible old effects and admission behavior; a new lock must not authorize takeover |
| Proposed positive fence | Demonstrate old effects cannot arrive after activation at both endpoints, including delayed requests; denial or unavailable fence blocks activation |
| Legacy populated state | Preserved jobs/claims/staging; no default destination backfill or fabricated enrollment |

Container clients share a kernel. A server-process restart is not automatically
server power-loss qualification, and selected partition timings do not establish
all reclaim behavior. Record exact protocol, mount options, client identities,
kernel, fault boundaries and cleanup results. Broader host/storage qualification
remains required before a production fencing claim.
