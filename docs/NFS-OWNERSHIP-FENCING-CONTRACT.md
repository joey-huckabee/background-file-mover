# First-release NFS ownership and fencing contract

Design baseline, increment 40, 2026-10-16. **Specified, not implemented or
qualified.** Defines FR-03 within the [first-release checklist](RUST-FIRST-RELEASE.md).
Production NFS and source deletion remain disabled. No fencer, takeover command,
lease service, credential scheme, migration or new runtime configuration is added.
Registration and offline repair remain deferred.

## First-release scope

One statically assigned mover and its original local SQLite state own disjoint
source custody and destination allocation scopes. Support explicit unused-scope
enrollment and matching original-state restart only. No automatic failover,
second active mover, populated re-enrollment, database clone/rollback adoption,
route reassignment or cross-host takeover. A detected uncertainty may require
operator intervention and indefinite refusal; availability does not override custody.

The reference candidate is hard-mounted NFSv4.1 with TCP, remote cooperative
locking (`local_lock=none`) and qualified synchronization/no-clobber behavior.
This matches the retained fixture's protocol, not a production-approved mount
recipe. NFSv3, other minor versions, soft mounts, alternative locking/security
modes and arbitrary server failover profiles require separate scope decisions
and evidence. The host kernel handles NFS; the service does not implement NFS.

The existing fixture's trusted network/UID policy does not establish authenticated
production server/export identity. The production profile must select an
independently authenticated endpoint/transport and approved export mapping.
RPCSEC_GSS with server authentication/integrity, such as a qualified krb5p profile,
is a candidate to evaluate, not a selected dependency or available infrastructure
assumption. No silent fallback to AUTH_SYS, a different server or a local directory.
A marker, mount-source string, IP, inode or copied filehandle observation alone
is insufficient. Keep strict source/destination binding pins; legitimate changes
remain unsupported without the deferred reconciliation/re-enrollment mechanism.

## Separate authority, exclusion and enforcement

| Evidence/control | What it establishes | What it cannot establish alone |
|---|---|---|
| Approved endpoint policy and authenticated storage transport | Intended server/export and permitted storage identity for a scoped session | Continuous worker exclusion, original database identity or settled old RPCs |
| Paired source enrollment receipt and original local state | Recorded source/state authorization and matching restart evidence | Detection of copied/stale databases or authenticated export identity |
| Protected regular lock and inherited description | Cooperative exclusion and measured child custody on the qualified mount | A per-effect storage fence or proof of uninterrupted lock history |
| Assignment/owner generation in durable state | Correlation and rejection of stale worker results by the coordinator | Rejection of a stale write/link/unlink at an NFS server |
| Independently enforced access fence plus settled-operation barrier | Old execution cannot issue or later apply effects within the covered scope | Permission to change routes, adopt foreign objects or restore stale state |

Current bindings, receipts and locks remain necessary. A new NFS lock acquisition,
process signal, elapsed timeout, heartbeat, successful ping, normal API mTLS or
boolean `fenced=true` cannot replace the last row. There is no promise that every
network lock loss is observable before a subsequent syscall with today's code.
The selected storage/host controls must enforce exclusion independently of that
assumption throughout their declared failure model.

## Ownership scope and effect authority

Bind ownership to the original state instance, approved coordinator, execution
incarnation and qualified endpoint/export/root scope. An execution incarnation
is a design identity for one activation, distinct from persistent coordinator IDs;
no format or generation field is implemented here. Enumerate all pinned source
and destination roots used by retained jobs, not only current startup routes.
Include namespace allocation, claims, partial files, links/unlinks, payload writes,
sync, final publication and manifests. Future cleanup is separately gated and off.
Include local SQLite writer exclusion when authorizing another activation.

Producer permissions cover only approved input paths under the agreed closed-writer
handoff; they must not grant access to private claims, lock/receipt namespaces or
destination staging. Consumers do not mutate mover-owned destination evidence.
Mismatched or colliding coordinator scopes refuse provisioning, including shared
UIDs/credentials, nested namespaces and differently named aliases of one export.
The actual server policy must demonstrate exclusion; logical root strings alone
cannot prove disjointness. Trusted provisioning/admin controls must prevent
uncoordinated mount/ACL/credential changes during active custody. Unexpected
interference is preserved/refused for review, not treated as successful ownership.

Every worker must use the approved assignment, held root/lock descriptions and
current scope authorization. Old worker results cannot authorize SQL transitions,
202, publication or cleanup after their assignment loses authority, even if the
reported hash matches. A manager check before dispatch is necessary but cannot
prevent an already issued syscall; the external enforcement/barrier must cover it.
All potentially blocking validation remains in bounded supervised children.

## Proposed authority states and allowed behavior

These states describe required behavior, not current persisted enums/API codes.
Missing or unrecognized authority defaults to blocked, never active. Persist
recovery-relevant incidents/assignments before permitting further effects; exact
schema, provider interface and migration need a later reviewed increment.

| State | Allowed behavior | Required transition evidence |
|---|---|---|
| Unproven | Bounded diagnostics and operator observation only; no readiness/claim effects for that source | Original source/state pair, endpoint authorization, approved active-owner enforcement and cooperative custody all validated |
| Active | Assign only effects for covered roots; use existing intent/receipt/replay and resource limits | Continuous provider guarantees and matching bindings; planned stop or uncertainty closes new assignment authority |
| Unavailable with continuity established | Preserve pending effects, apply existing bounded retry/backpressure and original-state recovery; do not spawn replacements for unconfirmed children | Provider/profile positively preserves sole-owner authority and stable endpoint binding through this outage; timeout alone cannot establish continuity |
| Uncertain | Stop new effects for affected scopes, preserve assignments and request bounded child shutdown; read-only local diagnostics where safe | Independent old-writer exclusion and settled-operation evidence required; restoring connectivity or reacquiring a lock does not return Active |
| Fenced/quiescent | No normal claim/delivery effects; original-state reconciliation only under explicit scope-limited maintenance authority | Old execution remains excluded, state writer is exclusive, every ambiguous intent is reconciled without adoption/repair and all current pins match |
| Restart eligible | Permit only a reviewed matching original-state activation, not re-enrollment or takeover | New activation authority cannot revive old clients/credentials/RPCs; persist/revalidate its scope and return Active only after normal bootstrap checks |

Known/suspected lost lock, changed root/export, changed enforcement generation,
unknown enforcement status, conflicting owner or server recovery outside a proven
continuity guarantee enters Uncertain. Ordinary network unavailability is not by
itself proof of lost ownership; treating it as continuity requires a qualified
provider guarantee, not the service guessing that no other writer exists.
If no continuity proof is available, use Uncertain. An unobservable lost lock is
why the independent enforcement requirement cannot be replaced by an EIO detector.

Scope-specific behavior preserves the producer contract: a destination-only
outage can still allow source claiming/202 when source authority, local state,
pinned route and admission limits are valid. No destination mutation proceeds
without its own authority. A source authority incident blocks new claims and
withholds new unproven 202 acknowledgements. A prior valid 202 still permits path
reuse and must never be retracted; recovery uses private claims, not reused input.
No replay may infer authority from a possibly stale database. Previously committed
manifests remain consumer-visible; an incident does not retract commitment.

## What the independent fencing facility must do

The contract selects an enforcement class: **independent old-writer exclusion
plus an endpoint-confirmed settled-operation barrier**, with fail-closed activation.
The exact facility is unresolved. No cluster product, BMC, Kerberos installation,
server revocation behavior or client-visible barrier API is assumed to exist.
Without a selected, enforceable and qualified implementation, FR-03 stays open.

The facility must cover the old coordinator, every child/client identity and all
access paths/aliases to each affected source and pinned destination, including
open descriptors, cached credentials, queued/retried RPCs, server-accepted work,
writeback and reconnect/reclaim. Revoking a credential or network path for future
requests is insufficient if accepted work can still execute later. Powering off
a host can be one control, but cannot by itself prove server-side queues settled.
Waiting a fixed number of seconds cannot establish that condition either.

Define a barrier B at each endpoint: after B, no effect from the excluded execution
may change that scope. Effects completed before B may be ambiguous and must be
reconciled from original intents/receipts and qualified storage durability evidence.
Do not require earlier operations to have done nothing; require their outcomes
settled and no later old effect. Partial barrier success across endpoints grants
no combined restart authority. Retain all exclusions throughout reconciliation
and new activation; rollback of the fencing operation must never reopen old access.

Re-enabling a host/network/credential must not make old requests valid again.
The chosen facility must distinguish the new execution, or prove the old client,
cache, descriptors and queues are fully gone before granting access to it. An
application generation in SQLite is not an NFS per-operation fencing token.
Cooperative locks remain an additional check, not a substitute for enforcement.

A future independently obtained observation must identify the provider/version
and qualification reference, operation/activation IDs, old execution/client
identities, original state, endpoint/export/root scopes, denial status and barrier
results for every endpoint, evidence freshness, still-enforced exclusions and
reconciliation result. Unavailable/stale/incomplete/foreign/replayed observations
refuse activation. Never accept an operator-supplied JSON file or HTTP parameter
as fence proof merely because its fields look correct. Authentication, transport,
bounded observation parsing and failure semantics of the real facility must be
specified before integrating it; no fencer REST API/config format is frozen here.

## Restart and incident procedure boundary

A clean same-owner restart requires confirmed old coordinator/worker exit,
exclusive original local state and provider evidence that old storage operations
are settled or continuously excluded under the qualified profile. Process reaping
alone does not establish remote settlement. Then validate the exact source/state
pair and all bindings and reconcile original operation records. A legitimate reboot/remount
that changes persisted pins can therefore remain refused in the first release;
matching restart is not a promise of recovery across every reboot. A hard-mounted
unreapable child, unavailable endpoint/barrier or incomplete original record keeps
the affected scope blocked. Bounded concurrency does not imply bounded shutdown.

After an uncertainty incident: stop ingress/assignments in the affected scope,
preserve state/source/staging/final objects, obtain independent exclusion and
all required endpoint barriers, and perform scoped original-state reconciliation.
If any object requires missing allocation ownership, changed pins, populated
rebind, cloned/stale state or offline repair, stop at review; those tools remain
deferred. An independent fence is necessary, not permission to bypass evidence.
No force/resume/reset command may clear ownership uncertainty. Existing delivery
resume and missing reset remain their original narrow operations.

## Finite qualification matrix (all pending)

NF IDs refine FR-03, L1-SEC-009 and catalog scenarios; they are not replacement
requirement IDs or passing test claims. Tests use the retained container fixture and exact
SLES-gated artifacts. A fake provider may test coordinator refusal/transitions,
but cannot qualify real fencing. Shared-kernel clients cannot prove independent
host/cache behavior; report that gap instead of requiring a physical SLES host.

| Case | Required evidence before declaring the profile supported |
|---|---|
| NF-01 | Default production NFS/deletion gates stay off. Unsupported protocol/security/enforcement profile, missing provider or proof refuses before effect readiness. |
| NF-02 | Explicit unused enrollment and clean matching restart preserve original state, receipts, pins and retained jobs. No auto-enrollment or changed-observation activation. |
| NF-03 | Two independently isolated clients contend using actual Rust inherited lock descriptions; server-visible lock control distinguishes local-only locking. Only the assigned original state may own a scope. Record independent versus shared-kernel evidence. |
| NF-04 | Wrong server/export, copied marker, nested/aliased scopes, local fallback mount or same-label foreign state refuses before effects; prove authenticated endpoint mapping and disjointness policy. |
| NF-05 | Kill coordinator while claim/copy/verification/publication workers survive. No replacement/activation before child exit and qualified remote settlement; original intents and data preserved. |
| NF-06 | Partition/reconnect and lost-lock/reclaim, including a loss without prompt EIO notification: independent enforcement excludes conflicting effects; no reliance on detecting every lost lock or reacquiring a lock. |
| NF-07 | Freeze/delay old writes, namespace allocation, link/unlink, sync and manifest RPCs at client and server boundaries; settle old outcomes before barriers, then prove zero old mutation after every barrier/new activation. A userspace pre-call pause alone is insufficient. |
| NF-08 | Fence only one of source/multiple pinned destinations; stale, forged, replayed, wrong-scope or unavailable observations refuse combined restart and preserve all objects. Include original routes no longer in startup configuration. |
| NF-09 | Crash/restart fencing control during deny/barrier/activation; no rollback reopens old clients. Reconnect old credentials/host/cache/session after activation and demonstrate continued denial. |
| NF-10 | Server restart/grace/reclaim/export failover invalidates or positively preserves authority under the declared profile. Verify endpoint identity, barriers and durability separately; no automatic rebind. |
| NF-11 | Outage beyond three minutes, bounded queue flood and unreapable children: no unbounded replacement, no false 202/commitment and responsive local diagnostics within measured limits. Unsupported indefinite shutdown stays explicit. |
| NF-12 | Destination-only outage with proven source authority still permits configured bounded 202 handoff. Source uncertainty withholds new unproven 202; preserve previous valid 202, reused paths and committed manifests. |
| NF-13 | Original-state post-fence reconciliation handles settled applied/not-applied/partial effects without clobber; unknown allocation, foreign aliases, changed pins or missing receipts stop for review rather than repair. |
| NF-14 | Clone/stale backup, copied credentials, old binary and second state cannot be activated by the supported provisioning/enforcement workflow. Do not claim persistent IDs detect every clone; no backup restoration/takeover support. |
| NF-15 | Native storage-full/quota/EIO/sync/server-reset and durability-boundary cases cover the supported server/storage profile. Container/process kills alone do not prove hardware power-loss durability; record any unresolved release gap. |
| NF-16 | Source deletion remains off even with a valid fence; no source/input/final cleanup added. Later FR-04 must independently prove pinned/current policy and receipt-gated cleanup. |
| NF-17 | Every changed Rust build/test passes production/qualification zigbuild GNU/glibc 2.22, ELF and exact pinned SLES-userspace gates. Qualify actual provider dependencies separately, including fail-closed parsing and asynchronous isolation. |
| NF-18 | DOC-04/05 explain the exact supported mount/security/provider profile, incident refusal, confirmed shutdown, original-state restart and unsupported rebind/takeover. Execute the declared end-to-end cases with preserved evidence and cleanup. |

## Evidence baseline, references and next work

Increments 22–28 establish selected binding, pairing, exclusion, worker survival
and startup behavior; 29–33 add bounded native capacity/failure evidence;
38 qualifies selected source-admission recovery. Consult those reports for actual
scope. None closes NF-01–18 in aggregate or implements this authority lifecycle.
Existing automatic fixture recovery is measured behavior, not a newly qualified
production continuity guarantee.

Linux documents advisory/NFS flock behavior in
[flock(2)](https://man7.org/linux/man-pages/man2/flock.2.html), network lock loss
and absent asynchronous notification in
[fcntl_locking(2)](https://man7.org/linux/man-pages/man2/fcntl_locking.2.html), and
mount/security options in [nfs(5)](https://man7.org/linux/man-pages/man5/nfs.5.html).
These support limitations and available primitives; the activation/barrier policy
above is a project design, not a capability certified by those references.

Next collect the actual endpoint authentication, server/export topology, client
identity isolation and host/storage fence plus settled-operation control available
for the intended deployment. Select one profile and attach implementation-level
NF pass/refusal cases before developing its adapter. An unavailable facility is
a release blocker, not justification for a lease-file workaround. Independent
local producer-ingress implementation and other bounded qualification may proceed
under existing disabled production gates. Registration remains deferred.
