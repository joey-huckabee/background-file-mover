# Root authorization and coordinator ownership

This describes the staged implementation design, not enabled production NFS.
Read [increment 22](RUST-INCREMENT-22.md) for measured startup behavior and
[the protocol](TRANSFER-PROTOCOL.md) for the required custody model. Production
NFS and deletion stay disabled. Generator registration remains deferred.

## First-release authority contract

[Increment 41](RUST-INCREMENT-41.md) revises the
[ownership contract](NFS-OWNERSHIP-FENCING-CONTRACT.md) for one mover restarting
on the same host/account, with fixed local state/config and private NFS working
areas. [Increment 42](RUST-INCREMENT-42.md) implements the explicitly inherited
host-local guard with selected local evidence. The proposed default-60 shutdown
controller and remaining SH-01–14 qualification, including owned NFS recovery,
remain pending. Local guard release is not proof of remote settlement.
The earlier external-fencer NF requirements are mapped to carry-forward safety
or deferred cross-host/maintenance profiles; no provider is assumed available.
The broad authenticated-export/fencing mechanisms below remain candidate extended
controls, not facts about the user's NAS. Current binding/receipt checks remain.

## Separate the three decisions

1. **Authorization:** is this the source/destination root the operator approved?
2. **Exclusion:** can another cooperating coordinator acquire the same scope?
3. **Fencing:** can an old coordinator/worker still affect storage after takeover?

A pathname, matching hash, device/inode number, local mount ID, marker, heartbeat
or assignment generation cannot answer all three. A lock on a directory is not
assumed to be a distributed lock. Even a functioning remote advisory file lock
does not make unrelated writes, link/unlink operations or old worker effects
conditional on possession of that lock. Linux documents NFS flock emulation,
write-open requirements and mount-option-dependent local locking; these are
reasons to qualify the actual mechanism, not proof about this fixture's outcome.
See the primary [flock(2) documentation](https://man7.org/linux/man-pages/man2/flock.2.html).

## First implementation: explicit endpoint bindings

Add an operator-provisioned immutable coordinator identity and separate source
and destination binding policies. A policy needs a version, logical root ID,
endpoint/export ID, expected filesystem class, root marker ID, role and permitted
coordinator identity. [Increment 23](RUST-INCREMENT-23.md) implements the required
`source_binding` object, protected marker and strict SQLite enrollment/observations;
[Increment 24](RUST-INCREMENT-24.md) adds required destination policy pinned at
acceptance, first-use observation persistence before allocation and worker/CLI
revalidation. Authenticated export identity remains future work.
Do not infer an expected NFS endpoint from whichever filesystem is reachable.

Provision a protected marker before enrollment. The service must never create
a missing marker to make an existing directory look authorized, rewrite a foreign
marker, or attach a new ownership marker to an unreceipted operation directory.
Stable logical IDs survive allowed restarts; device/inode/mount observations
identify a particular binding during a session and cannot substitute for those IDs.
Markers are identity evidence under trusted provisioning, not secrets or a defense
against a privileged/same-UID actor cloning the entire root. Export replacement
or a copied marker must not silently authorize a new export.

Specify and qualify how the configured endpoint/export and root marker bind to
the actual mounted root before enabling it. Mount-source strings alone are not
authenticated server identity; an address may also legitimately change during
managed server failover. Filesystem identity/filehandle observations and approved
mount configuration are candidate supporting evidence, not portable global IDs.
If the implementation cannot establish the configured binding, refuse effects.
Define explicit fenced re-enrollment for intentional replacements; do not accept
them automatically because file contents or marker text match.

Persist the coordinator and root binding policies in local SQLite and pin the
resolved destination binding with each accepted job. A startup route change cannot
redirect old recordings. Migration of legacy state with jobs needs explicit
enrollment/reconciliation; never guess its authorization from the current path.
Validate a source binding in the existing supervised bootstrap child before
SQLite/readiness. Return bounded metadata and the actual locked descriptions,
then compare with configuration/state outside the async executor.

Keep destination unavailability independent of producer handoff: an approved,
pinned destination may be unavailable while source claims are accepted within
configured retention limits. Validate its binding in the recording worker before
any destination allocation or recovery effect. Missing/unavailable and wrong or
ambiguous bindings need distinct retry/review decisions. A visible unexpected
local directory must not count as an available NFS destination.

Each child must validate the assignment's binding and held root/namespace/lock
descriptions before effects. Compare the current path binding with held custody;
do not reopen a different root and silently transfer authority to it. Keep those
checks inside supervised children because even metadata can block on hard NFS.
Retain the approved-parent/no-untrusted-writer requirement; a preflight check does
not eliminate races with an administrator replacing a mount during an operation.

## Coordinator exclusion and takeover

[Fenced enrollment](FENCED-ENROLLMENT-DESIGN.md) specifies persistent source/state
pairing and interrupted setup. [Increment 27](RUST-INCREMENT-27.md) implements
explicit unused-scope initialization and matching restart with schema 10 and
version-3 bindings. Fresh state cannot adopt an enrolled root after lock release.
Populated-state rebind, clone/stale-backup recovery and independently enforced
fencing remain future work; preserve original state and exclude old binaries.

The initial production policy should use one statically assigned coordinator and
disjoint source scopes. A second independent state database must not gain custody
merely because job IDs restart at one. A marker naming the permitted coordinator
can reject a different identity, but two copies of the same identity still need
real exclusion and a takeover protocol. Do not implement automatic failover yet.

Qualify a preprovisioned regular lock file, opened for writing and held through
the same inherited open description, as a candidate for cooperative cross-client
exclusion. Bind it to the protected namespace and expected operation owner; refuse
missing/replaced/extra-link/foreign lock files. The existing directory descriptor
validation and bootstrap descriptor protocol would need deliberate changes; do
not simply change a filename and assume inherited custody remains valid.
[Increment 25](RUST-INCREMENT-25.md) implements this regular-file custody with
binding version 2, a versioned bootstrap receipt and held/named lock checks in
actual workers. Its debug/release two-client tests pass cooperative startup
exclusion and actual claim/delivery child custody after coordinator death, with
recovery through the original database. The separate regular-file control is an OS
observation, and neither result constitutes a production takeover fence.

Takeover must require positive evidence that every old writer and in-flight effect
is excluded, plus recovery of uncertain operation intents. Process exit on a
different host, lock expiration, loss of a heartbeat, ping failure, a timeout or
a fresh generation number alone is insufficient. Network partition and server
reboot/lock reclaim can outlive client assumptions. Keep a scope blocked until
an independently qualified fence and reconciliation permit another owner.
Linux's [record-locking documentation](https://man7.org/linux/man-pages/man2/fcntl_locking.2.html)
also describes lost network locks; a successful acquisition is not a permanent
ownership grant through every failure mode.
That may require operational host/storage fencing rather than another Rust crate.
Never attempt a timestamp/lease-file workaround with unqualified clock semantics.

## Short implementation and qualification sequence

1. Validate the source-binding/enrollment slice in increment 23, including absent
   NFS, wrong root/marker, changed binding, legacy state and restart refusal.
   Specify a positively fenced enrollment/rebind procedure for legacy jobs and
   legitimate changes to strict observed identity pins. Leave production NFS disabled.
2. Qualify the destination-binding slice in increment 24: unavailable versus
   foreign destinations, first observation before allocation, runtime/restart
   refusal and replay under changed routing, retaining the producer's 202 contract.
3. Implement and qualify the candidate cross-client lock with actual Rust
   coordinator/worker inheritance, contention and coordinator death. Verify
   separate client identities and a remote-lock positive control.
4. Implement/qualify the revised single-host SH guard/shutdown/recovery cases,
   including delayed effects, actual mount/root validation and safe original-state
   restart/refusal. Keep production NFS/cleanup off until the release gates pass.
   Independently fenced takeover/re-enrollment remain separate deferred profiles.

Maintain SC-046 and the diagnostic SC-053/054 entries, plus DOC-04/05 runbooks.
Do not mark an expected refusal as supported until implementation and evidence
show it. Keep root authorization independent of deferred recorder tokens and
offline repair; neither is a prerequisite for testing these filesystem bindings.
