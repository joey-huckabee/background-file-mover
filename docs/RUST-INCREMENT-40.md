# Rust increment 40: first-release NFS authority and fencing contract

Documentation/design increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Defines [the NFS authority contract](NFS-OWNERSHIP-FENCING-CONTRACT.md) for FR-03.
Production NFS and source deletion remain disabled. No Rust, dependency, runtime
configuration, database/wire format, provider adapter, takeover command or test
harness changes. Registration and offline repair stay deferred.

## Defined behavior and boundary

The first-release design keeps one assigned owner with its original local state,
disjoint protected scopes, unused enrollment and matching restart. It separates
authenticated endpoint identity, persistent pairing, cooperative lock exclusion
and independently enforced fencing. The selected enforcement class combines
old-execution exclusion with endpoint-confirmed settlement of prior operations;
no actual facility is selected, assumed available or qualified.

The proposed authority lifecycle distinguishes proven continuity during an outage
from uncertainty. Uncertainty stops new affected effects and requires independent
exclusion/settlement before original-state reconciliation and activation. All
retained jobs' pinned endpoints and local state writer must be covered. A partial
fence cannot authorize combined restart, and regrant cannot revive old workers,
credentials, descriptors or queued/server-accepted RPCs. Signals, lock acquisition,
generations, fixed waits and operator assertions are insufficient proof.

Source-valid/destination-only outages retain bounded handoff behavior; uncertain
source authority cannot grant new unproven 202. Prior valid 202 and committed
manifests remain valid, with private source claims and producer-reused paths
preserved. Fencing never authorizes changed pins, cloned/stale database adoption,
foreign allocation repair, automatic takeover or source deletion.

NF-01–18 enumerate finite pending acceptance obligations, distinguishing actual
storage enforcement from fake-provider coordinator tests, shared-kernel clients,
userspace pauses and physical durability. The candidate hard-NFSv4.1 reference
profile follows measured fixture scope; authenticated production transport and
the exact host/storage controls remain deployment prerequisites. There is no
new requirement to test on a real SLES host or implement an NFS stack.

SC-046/066/067 link the refined contract. Five pending situations SC-087–091 cover
unknown continuity, partial endpoint fencing, delayed old RPCs, invalid fence
observations and revived old access. The catalog now has 91 stable IDs and six
DOC items. DOC-04/05 retain actual-provider and incident/runbook obligations;
none of these new situations is promoted to runtime support.

L1-SEC-009 is one new Rust-specific authority obligation, marked historical
v1.0.0 Deferred; it is distinct from L1-SEC-008 remote caller binding. Existing
requirement IDs/meanings/statuses are preserved. L2/L3 and Rust evidence remain
pending; the trace matrix gains a deferred, currently underived requirement,
not a new coverage claim. Root/enrollment/protocol/security documents, README,
future-only roadmap, release checklist and handoffs link the contract. All eight
release gates stay open.

## Validation and limits

Review checked current binding/custody code, paired enrollment, qualification
notes and prior ownership evidence. Linux flock, fcntl_locking and nfs manuals
were checked for advisory/NFS locks, lost-lock notification and transport/mount
primitives; links are in the contract. Those references do not certify the
project's proposed enforcement facility or prove old effects are settled.

Documentation validation passes for 410 local links and consistent table
structure, eighteen unique NF cases, all 91 unique scenarios/six DOC items/eight release gates, the single
additive requirement with unchanged prior IDs/statuses, generated trace matrix
and whitespace. No Rust build/test or fixture is run for this documentation-only
increment; increment 38 remains current runtime evidence. The design does not
close FR-03 or enable production NFS/deletion. Next obtain the actual endpoint
and host/storage exclusion/settlement capabilities, select one qualified profile
and implement its exact denial/activation behavior. Independent local ingress
work remains possible under current disabled production gates.
