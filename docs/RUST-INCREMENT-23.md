# Increment 23: Explicit source binding and durable enrollment

This increment implements the first source-binding step from
[ROOT-OWNERSHIP-DESIGN.md](ROOT-OWNERSHIP-DESIGN.md). Service startup and the
single-file CLI now require `source_binding`; there is no inferred/automatic
filesystem class. Production NFS and source deletion remain disabled. Recorder
submission JSON and 202-after-all-claims behavior are unchanged.

## Provisioning and configuration

Provision the source root and its service-owned 0700 `.file-mover` directory
first. As the service UID, provision `.file-mover/source-binding.json` with the
following JSON and permissions 0600 (0400 is also accepted). Put the same object
under `source_binding` in startup configuration:

```json
{
  "version": 1,
  "coordinator_id": "mover-a",
  "root_id": "recordings-a",
  "endpoint_id": "local-recordings-a",
  "marker_id": "provisioned-recordings-a",
  "filesystem": "local",
  "role": "source"
}
```

For the isolated NFS qualification build use `"filesystem":"nfs"`; that value
cannot enable NFS in production. IDs are operator-provisioned nonsecret labels,
1–128 ASCII letters/digits/underscore/hyphen/dot, excluding `.` and `..` alone.
Use distinct identities for distinct approved scopes. A coordinator ID is not a
recorder token, secret, proof of a unique process or a distributed fence.
Unknown fields, unsupported version/role/filesystem and invalid IDs are refused.

The service never creates, rewrites or repairs a marker. It requires a bounded
owned regular file, one link, no symlink, exact private permissions, same source
device and matching configured content. It checks the open marker before/after
reading and its current directory binding. This is a root marker, not a new
ownership marker for an existing unreceipted job/attempt directory.

## Startup and state behavior

The supervised bootstrap child checks the expected filesystem class and marker,
then acquires custody and rechecks authorization. Before SQLite, a missing mount
cannot be accepted as a local root even if a matching marker has been copied
there. Marker/type/custody/content failures also precede database opening.
The parent receives bounded authorization metadata and the actual locked open
description through the existing private socket; it does no source I/O while
receiving that receipt and still waits for confirmed successful child exit.

SQLite schema 8 persists one source enrollment: configured canonical binding,
source path, state instance ID and observed filesystem type/fsid, root and private
namespace device/inode/UID, and marker identity/size/mtime/link evidence. Mutable
directory size/mtime/link counts are excluded, so ordinary claims do not change
the pin. Job acceptance uses the configured logical root ID.

- A fresh or empty migrated database can enroll only after explicit configuration
  and a valid preprovisioned marker authorize it.
- Matching enrollment is idempotent, including restart/replay with existing jobs.
- A different policy/path/coordinator, changed root/namespace or replaced/modified
  marker refuses startup before workers/readiness. The database can be opened to
  compare enrollment; these failures do not claim to precede all SQLite access.
- A populated database without enrollment returns `SourceEnrollmentRequired`.
  Migration retains jobs/claims but does not infer which current root owns them.
  No enrollment override, automatic rebind or repair command is introduced.
- Schemas 1–7 migrate structurally to 8; older binaries cannot open schema 8 and
  silently ignore its enrollment. Keep legacy state and sources intact for a
  future explicit enrollment/reconciliation workflow. Do not delete a database
  or marker to bypass a refusal.

Device numbers/fsids are strict observed pins, not permanent authenticated global
IDs. An otherwise legitimate reboot/remount or filesystem restoration may change
them and refuse startup. Fenced re-enrollment is future work. A cloned filesystem
or privileged/same-UID actor reproducing all evidence is outside this slice's
authorization proof; server/export identity, failover and replacement remain
unqualified before production NFS. Logical endpoint IDs alone authenticate no server.

## Runtime and CLI checks

The parent carries its enrolled source authorization in claim-worker assignments
and every recording-session command. Children compare the current marker/root
observations before and after effects. A recording session refuses a changed or
downgraded authorization. In the REST service, potentially blocking source metadata
stays inside supervised children; SQLite transitions remain in the parent. The single-file CLI performs
bound bootstrap/enrollment and holds that custody through its synchronous transfer.
Trusted lower-level filesystem/test APIs retain unbound local guards; they are not
an alternate public startup configuration or remote submission path.

Runtime refusal retains sources and does not return 202 for an incomplete claim.
Binding changes during an already authorized effect still require reconciliation;
these checks do not cancel in-flight NFS calls or fence a privileged mount changer.
Normal streamed source hashing plus independent staging verification remains 3N
logical payload I/O. Marker checks add bounded metadata/marker reads, not a source
payload prehash. No dependencies, deployed executable, recorder fields or deletion
capability are added.

## Validation

Initial gates `20261015T071538Z-aa269a7b` and
`20261015T071549Z-ae3bf25e-nfs-qualification` stopped on Clippy's collapsible-if
check; they are not test passes. The condition was corrected, and targeted
root-replacement/session tests were added before restarting both full gates.
Runs `20261015T071816Z-3877e178` and
`20261015T071828Z-28a25232-nfs-qualification` then stopped on an unused mutable
test binding under `-D warnings`. That warning was corrected before the next
full gate launches; no failed gate is promoted as compatibility evidence.
Runs `20261015T072020Z-b6754bcb` and
`20261015T072032Z-0d370d31-nfs-qualification` passed 41/42 debug API tests:
the new test incorrectly reused a session after a blocked reply had correctly
terminated its worker. It now uses independent sessions and confirmed exits for
the downgrade and changed-marker cases. The single-file CLI also gained checks
around each payload phase; removing its obsolete private helper fixed the
dead-code warning reported by `20261015T072431Z-437f6016` and
`20261015T072444Z-fc49c311-nfs-qualification`. These runs remain failed evidence.

Production gate `20261015T072538Z-919959d7` PASSED 125 tests per profile;
qualification gate `20261015T072550Z-cc93e911-nfs-qualification` PASSED 126.
Both completed formatting/Clippy, debug/release zigbuild, ELF/interpreter/library
audits, six negative audit controls per mode and exact target execution in pinned
SLES userspace, with no cleanup errors. Maximum required GLIBC remains 2.18 and
the external Linux graph remains 42 packages. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).
The documented Windows `CONTAINER_CONNECTION=podman-machine-default-root`
selection still builds on native Linux container storage and runs exact artifacts
in pinned SLES userspace; no permanent engine/Ubuntu configuration is changed.

The seven new executable/API tests cover required/strict configuration, eight
marker/filesystem refusal cases before SQLite, marker and root replacement
without rebinding, runtime claim refusal with an untouched producer file,
populated unenrolled state refusal, and delivery-session marker-change/downgrade
refusal with retained source and empty staging. Separate worker sessions are
used after terminal errors. Restoring the original root/marker permits a matching
restart; exact 202 replay preserves a reused producer path. Three new store tests
cover durable/idempotent enrollment and refusal of changed context, schema-7
empty-state enrollment and populated-state refusal with jobs retained.

The retained NFS runner provisions explicit fixture bindings. Its missing-mount
case deliberately copies the matching NFS marker to the local stand-in and
requires both builds to refuse before readiness, preserving an existing SQLite
file unchanged. The separate-client diagnostic still uses the same declared
coordinator identity on both clients; cross-client exclusion/fencing remains a
separate unimplemented protection. Preserve prior diagnostic findings as history,
and promote only the measured missing-mount refusal in SC-054.

Full fixture `nfs-20261015T073324Z-30fcffe1` PASSED with no cleanup errors:
six normal NFS baselines, four ownership/missing-mount diagnostics and all 22
debug/release runtime cases, including selected three-minute claim and verification
outages with live recovery. Retained inherited-lock, blocked-startup and signal/exit
probes also passed. See [source-binding fixture evidence](RUST-NFS-SOURCE-BINDING-EVIDENCE.json).
Both profiles refused the copied-marker local stand-in in qualification and
production. Same-client exclusion and regular-file remote-lock controls passed;
the independent client with the same declared coordinator identity still reached
readiness, so `protection_complete` and `production_authorized` remain false.
These are SLES 12 SP5 userspace containers on WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`, not evidence for the SLES kernel, physical
clients, export replacement, partitions or power loss.

Destination bindings, enrollment of legacy jobs, positively fenced rebind/takeover,
authenticated export identity, partitions, reboot/reclaim and power loss remain
future work. Recorder registration, offline repair and package experiments remain
deferred. Maintain SC-054–057 and DOC-01–06 with actual evidence.
