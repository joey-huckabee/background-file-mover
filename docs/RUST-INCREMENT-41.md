# Rust increment 41: confirmed single-host ownership and bounded stop contract

Documentation/design increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Revises [the ownership contract](NFS-OWNERSHIP-FENCING-CONTRACT.md), roadmap,
release gates and scenarios. Production NFS and source deletion stay disabled.
No Rust code, dependency, configuration parser, schema, lock, control command,
service unit or test harness is changed. Registration and repair remain deferred.

## Confirmed constraints and changed premise

The user confirmed one mover, always restarting on the same host under their
ordinary account, without host sudo or NAS administration. An administrator will
set up systemd. Manual/service starts use the same configuration and fixed local
state directory; SQLite/WAL/state stay on persistent local disk. Both payload
ends are NFS (NetApp/Dell Isilon), usually separate shares but same-share operation
is also required. Other apps and cleanup leave private working areas alone.
NFS version/options cannot be checked yet and remain unknown.

The prior increment 40 treated independent external exclusion/barrier facilities
as a blanket first-release prerequisite before these details were known. This
revision replaces that assumption with a cooperative same-host ownership profile;
it neither asserts that a NAS fencer exists nor labels local flock as storage
fencing. Stronger cross-host/re-enrollment requirements remain deferred. Delayed
NFS effects and correct original-state recovery remain production blockers until
qualified; narrowing ownership does not settle queued storage requests.

## Revised design and acceptance scope

Propose one safe persistent local guard before SQLite/NFS effects, explicitly
inherited by every relevant worker/effect entry point. Parent death leaves live
workers holding ownership; manual/systemd races have one winner. Fixed approved
startup scope and trusted account cooperation are required; deliberate alternate
state or another-host bypass is not prevented by this guard.

The confirmed default shutdown wait is 60 seconds and configurable. The proposed
future key is shutdown_wait_seconds, integer 1–3600, omitted=60. The first stop
sets a monotonic deadline; repeated requests do not extend it. At expiry a bounded
stop controller returns unsuccessful shutdown incomplete/restart blocked, while
the daemon and live workers may remain with ownership intact. No guarantee that
the foreground daemon or an NFS syscall exits by the deadline is made. A separate
bounded operator control path and coordinated actual-version systemd behavior
must be implemented/qualified; existing SIGTERM handling is not that feature.
The design fragment must not be pasted into current strict configuration.

SH-01–14 are all pending obligations: guard scope/races/inheritance, surviving
workers, option validation, clean/timed-out drain, repeated stop, unprivileged
systemd control, same/separate shares, late RPCs, actual mounts/server recovery,
unsupported state and SLES/lifecycle evidence. Original NF-01–18 are retained in
an explicit scope mapping, not renumbered or relabeled as passing SH tests.
L1-SEC-009 is revised under its existing ID/status; the matrix is regenerated
without inventing evidence or new requirement IDs. All eight release gates stay open.

Four pending catalog situations SC-092–095 cover overlapping starts/survivors,
bounded stop, late effects after worker exit and unsafe startup scope. Earlier
SC-046/066/087–091 are refined without deleting their limits; external-provider
cases are explicitly deferred. There are 95 stable IDs/six DOC items. DOC-04/05
now prioritize the actual local-guard/systemd/NFS profile. The current operator
guide labels the proposed setting/controller unimplemented. Historical result
documents and saved runtime evidence remain unchanged.

## Validation and boundaries

Documentation checks passed: 435 local Markdown targets, consistent table
structure, the proposed JSON fragment/default 60, 14 unique SH cases, all 18 original NF mappings, 95 unique stable SC IDs, six DOC
items/eight release gates, unchanged requirement IDs/Deferred annotations,
generated trace consistency, unchanged Rust/scripts and whitespace. Reviewed
Linux flock/SQLite WAL documentation and official systemd v228 manual source
for mechanism/timeout limits; these do not establish the installed host's
systemd version or qualify its lifecycle. The current contract links the sources.

No Rust build/test or NFS/systemd fixture is run for this documentation-only
increment; increment 38 remains the latest runtime evidence. No new timeout,
guard or support claim is implemented. Next implement/qualify shared local guard
and inheritance through the mandatory SLES gates, then bounded stop control and
remaining NFS/lifecycle cases before any production enablement or source cleanup.
