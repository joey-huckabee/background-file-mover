# Increment 25: Cooperative regular-file lock custody

This increment replaces directory locking with a preprovisioned regular-file
lock, including source bootstrap, inherited claim/payload workers and recording
destination sessions. It implements cooperative exclusion; it does not implement
lost-lock detection, partition/reclaim fencing or permission to take over another
coordinator's state. Production NFS and source deletion remain disabled.

## Provisioning and cutover

Both source and destination binding configuration/markers now require
`"version":2`; their other fields and role rules are unchanged. Before starting
the service, provision `.file-mover/coordinator.lock` at each approved root as
the service UID: an empty regular file, exact mode 0600, one link, on the root's
filesystem. Provision exclusively; never truncate, rewrite, replace or recreate
an active lock to make a root available. Namespace permissions remain 0700.
Neither bootstrap nor delivery creates or repairs lock files or binding markers.

Version 1 is refused. New markers/configuration fail validation in the older
binary. Stop and positively exclude all old coordinators/workers before changing
provisioning: an in-flight operation is not cancelled by changing a marker.
Mixed-version operation is unsupported. Old source enrollment and destination
observations also differ from the new strict pins and refuse automatic reuse,
including otherwise empty enrolled state. Preserve state and source/staging data
for a future explicit fenced enrollment workflow; there is no rebind override
or delete-and-restart migration procedure. SQLite remains schema 9.

See [the example configuration](../rust/config/local.example.json) and
[binding setup](RUST-INCREMENT-24.md) for fields; use version 2 for both roles.
The coordinator ID remains a nonsecret provisioned identity, not recorder
authentication, proof of a unique process or a distributed queue identity.

## Descriptor and observation protocol

The lock is opened read/write without create/truncate, with no-follow,
close-on-exec and nonblocking flags. Validate regular-file type, exact permission,
owner, zero length, one link, device and current named identity. Acquire exclusive
nonblocking flock on that description and recheck custody. Source/destination
observations now include this immutable lock identity. Binding observation uses
descriptor-relative no-follow metadata and does not open an independent lock
description on every check.

The bootstrap receipt is private protocol version 2, with bounded root/namespace/
lock identities and exactly one SCM_RIGHTS descriptor. It transfers the actual
locked open description; the parent does no source metadata I/O and still waits
for successful bootstrap child exit before using custody. Legacy/inconsistent,
missing, extra or truncated receipts fail closed.

Workers inherit duplicates of the same locked description through their existing
stdin/stdout channels. They refuse directory or read-only descriptors, compare
held and named lock identities, and check exclusive custody before effects.
Guard validation also checks the saved lock observation and root/namespace pins.
The existing source/destination marker checks remain in place. Closing a parent
copy must not release custody while a child copy survives; qualification below
must measure that behavior on the selected NFS mount, not assume it from the
local filesystem or a shell lock control.

These are advisory locks among cooperating instances on the qualified fixture.
Revalidating a descriptor or successfully acquiring flock does not fence delayed
effects, privileged file replacement or lost/reclaimed network locks. There is
no heartbeat, lease-file timeout, automatic failover or reassignment based only on
coordinator death. Do not deploy production NFS before the remaining ownership,
export and storage failure qualification.

## Validation

Validation is in progress. Initial gates `20261015T112215Z-44725f6f` and
`20261015T112215Z-a17c701d-nfs-qualification` passed 53/55 debug API tests.
Two older marker-correction fixtures attempted exclusive lock provisioning twice.
Setup now provisions the lock once and leaves marker corrections independent.
Those runs are failed evidence.

Production gate `20261015T112605Z-e8a6835a` PASSED 142 tests per profile;
qualification gate `20261015T112605Z-f8739448-nfs-qualification` PASSED 143.
Both completed formatting/Clippy, debug/release zigbuild, ELF/interpreter/library
audits, six negative audit controls per mode and exact target execution in pinned
SLES 12 SP5 userspace. See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).
Maximum required GLIBC remains 2.18; the external Linux
dependency graph remains 42 packages.

Full fixture `nfs-20261015T113434Z-21fea880` PASSED: six directional NFS
baselines, eight ownership cases and all 22 debug/release runtime cases, including
selected three-minute claim/verification outages with live recovery. Retained OS
lock, blocked-startup and signal/exit probes passed. The report has no cleanup
errors; final engine inventory found no containers or temporary networks, leaving
the existing toolchain/registry caches. See [custody evidence](RUST-NFS-CUSTODY-EVIDENCE.json).

Both profiles excluded same-client and independent-client startup before SQLite/
readiness. A separate client could start after clean release of the empty test
scope; that control submitted no jobs and grants no independent-state takeover.
All four real claim/delivery worker cases excluded the peer with `WouldBlock`
after coordinator death and while the stopped assigned worker survived. Peer
file-lock controls also observed source custody (and destination custody for
delivery) through worker lifetime, then observed release after confirmed exit.
Recovery with the original database/configuration completed commitment with
matching manifest/hashes and retained source. Copied-marker missing-mount refusal
remains passing in both profiles/build modes.

`cooperative_exclusion_passed` is true; `protection_complete` and
`production_authorized` deliberately remain false. The two container clients
have distinct NFS identities and network/mount namespaces but share WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`. Clients run pinned SLES 12 SP5 userspace on
the controlled hard NFSv4.1 export with `local_lock=none`. This is not the SLES
kernel, separate physical hosts, partition/reclaim, server reboot or power-loss
qualification. Both gated source archives match their own recorded hashes, and
their complete file inventories/content match each other and the checkout.
Artifact/driver hashes and actual contention reasons were checked. Preserve the
older directory-lock admission gap evidence as historical results.

The added tests cover six missing/unsafe source-lock cases before SQLite,
binding-version refusal, source-lock replacement on restart and during a live
claim, forged directory/read-only inherited descriptors, destination-lock
replacement before payload and malformed/legacy bootstrap lock receipts.
Existing contention, inherited child lifetime, replay, CLI, delivery, source
retention, integrity and migration tests must remain passing.

The NFS fixture additionally tests peer startup exclusion, clean release of an
empty scope, and real claim/delivery worker custody after coordinator death in
both profiles. The same original database performs recovery after confirmed
worker exit. Peer file-lock probes test release; they do not grant takeover of
the original database's jobs. Keep independent-client identity/remote-lock controls,
missing-mount refusals and the full runtime matrix as separate scoped facts.

Maintain SC-053, SC-061–063 and DOC-01–06. No package or executable is added.
The normal payload integrity path remains 3N; lock/marker checks add metadata,
not a separate source hash pass. Retain qualification-only controls and the NFS
fixture permanently. Registration, offline repair and package experiments stay
deferred; fencing, authenticated exports and explicit enrollment remain future.
