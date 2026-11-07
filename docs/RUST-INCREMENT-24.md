# Increment 24: Pinned destination authorization

This increment adds required destination policy to startup configuration and pins
it with each accepted job, without accessing destination storage during acceptance
or source claiming. Recorder JSON and the 202-after-all-claims contract stay the
same. Production NFS and source deletion remain disabled.

## Provisioning and policy

Provision the destination root and service-owned 0700 `.file-mover` namespace.
As the service UID, provision `.file-mover/destination-binding.json`, mode 0600
(0400 also accepted), and configure the identical object as `destination_binding`:

```json
{
  "version": 1,
  "coordinator_id": "mover-a",
  "root_id": "recordings-destination-a",
  "endpoint_id": "local-destination-a",
  "marker_id": "provisioned-destination-a",
  "filesystem": "local",
  "role": "destination"
}
```

Use the same coordinator ID as `source_binding`. IDs follow increment 23's bounds
and character rules. `filesystem` is explicitly `local` or `nfs`; the latter is
usable only in the isolated qualification build. Missing configuration, unknown
fields, invalid IDs/version/role and coordinator mismatch are refused.

The marker uses the same bounded, private, regular-file custody checks as the
source marker. Startup never provisions or repairs either marker. Labels and
numeric filesystem observations are trusted-provisioning evidence, not secrets,
authenticated export identity or cross-client fencing.

## Acceptance, delivery and restart

Schema 9 stores each job's configured destination policy transactionally with
acceptance. Replay preserves the original policy/path even if current startup
routing changes. No destination filesystem access is needed for acceptance,
source claiming or 202, within existing retained-job/byte admission limits.

A supervised recording child checks the declared filesystem, protected marker
and held destination custody. The parent durably pins its bounded observation
before sending any staging allocation or subsequent effect. Future sessions
must match that observation. The child keeps that authorization in its held
guard and revalidates before/after effects. The single-file CLI uses the job's
stored policy and the same durable observation before its transfer effects.

The first observation is made on first authorized delivery access, not during
acceptance. Before that observation, identity relies on the provisioned marker
and declared policy. Cloning a complete approved root is not authenticated export
identity. Strict pins can refuse legitimate remounts/reboots; explicit fenced
re-enrollment remains future work.

Structural migration from schemas 1–8 preserves jobs/claims/reservations. Service
startup refuses jobs without a saved destination policy rather than adopting the
current route. There is no backfill/rebind override; retain state/source data for
a future explicit enrollment workflow. Older binaries refuse schema 9. Trusted
low-level filesystem/test APIs retain explicitly unbound local contexts; public
service and CLI startup require the configured bindings.

## Validation

Production gate `20261015T084447Z-e5519464` PASSED 135 tests per profile;
qualification gate `20261015T084448Z-845f7344-nfs-qualification` PASSED 136.
Both completed formatting/Clippy, debug/release zigbuild, ELF/interpreter/library
audits, six negative audit controls per mode and exact artifact execution in
pinned SLES 12 SP5 userspace. Maximum required GLIBC remains 2.18 and the external
Linux dependency graph remains 42 packages. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

The 49 API tests include seven new destination cases: required strict policy,
six unsafe/missing marker custody cases, source handoff followed by foreign-marker
review/correction/audited resume, expected NFS on a local stand-in, root replacement
with the original marker inode, runtime marker change before payload, and populated
state without destination policy. Existing routing/replay, CLI and recovery tests
also pass. Three new store tests cover durable policy/observation pinning under
route changes, schema-8 legacy-job refusal after structural migration and immediate
binding review persisted after an outage.

Full fixture `nfs-20261015T085325Z-edda377b` PASSED: six normal directional
NFS baselines, four ownership/missing-mount diagnostics and all 22 debug/release
runtime cases, including selected three-minute claim and verification outages
with live recovery. Retained inherited-lock, blocked-startup and signal/exit
probes also passed. The report has no cleanup errors; a final engine inventory
found no containers or temporary networks, retaining only the existing toolchain
and registry caches. See [destination-binding fixture evidence](RUST-NFS-DESTINATION-BINDING-EVIDENCE.json).

Same-client exclusion and regular-file remote-lock controls passed, and both
profiles/build modes still refused the copied-marker source mount stand-in.
An independent NFS client with the same coordinator identity still reached
readiness: `protection_complete` and `production_authorized` remain false.
These are SLES 12 SP5 userspace containers on WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`, not qualification of the SLES kernel,
physical clients, replacement exports, partitions or power loss. Destination
tamper/replacement refusal tests are local; the NFS run qualifies regression
of the existing baseline/interruption matrix, not an NFS export-tampering case.
Both gates' archive hashes match their reports; complete archived source
inventories/content match each other and the checkout despite distinct compressed
archive hashes. Fixture artifact hashes and ownership-driver hashes were checked.

Initial gates `20261015T083828Z-419dbae8` and
`20261015T083829Z-944cb667-nfs-qualification` stopped on two misplaced fields
in a transfer initializer. Corrected gates `20261015T084111Z-4768c7ba` and
`20261015T084111Z-517c2867-nfs-qualification` passed 44/49 debug API tests:
one older test omitted the newly required configuration field, and SQLite's
constrained diagnostic vocabulary refused the new review code, causing the
service to stop rather than persist review. Schema 9 now preserves/rebuilds the
retry table with the additional code, and a dedicated store regression test
checks durable immediate review after an outage. These runs are failed evidence.

An absent destination root/namespace is retried after five seconds without
consuming the ordinary failure budget. An observable wrong filesystem, invalid
marker or changed observation immediately persists three-failure review with
`destination_binding_requires_review`. Correcting provisioning does not clear that
review; the existing audited resume workflow is required. Other uncertain effects
retain their existing bounded retry/review semantics. Generic delivery failure
now updates its code when following a prior destination-unavailable record.

No packages, extra executable, payload prehash or deletion capability are added.
Normal integrity remains source hashing during copy plus destination staging
reread: 3N logical payload I/O. Cross-client exclusion/fencing, authenticated export
identity, fenced legacy enrollment/rebind, partitions/reclaim and power-loss
qualification remain future work.
