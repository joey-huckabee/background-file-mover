# Increment 22: Root and cross-client ownership diagnostics

This increment measures the current ownership boundary before implementing new
authorization or a different locking mechanism. It adds retained `--ownership`
probes to the isolated NFS runner and specifies the next short implementation
sequence in [ROOT-OWNERSHIP-DESIGN.md](ROOT-OWNERSHIP-DESIGN.md).
No service behavior, package, schema, producer contract or normal 3N I/O changes.
Production NFS and source deletion remain disabled.

The runner first validates the exact production/qualification artifacts against
passing mandatory gates and repeats the six normal NFS baselines. It then mounts
the same private export in a second pinned SLES container with separate network
and mount namespaces. Record mount options, server-observed client identities,
root/namespace inode/ownership observations and a shared witness digest. Both
clients use UID 1000; all SQLite databases and destinations remain local.

For debug and release, start the actual qualification coordinator on client A.
A competing service in the same client must refuse before SQLite/readiness.
Observe whether a service with an independent local database in client B can
announce readiness against the same source. No jobs are submitted while these
coordinators overlap; startup exclusion is the measured property, not a data race.
A separate regular-file RDWR/flock control must exclude client B while held by A
and permit it after release. This establishes a working remote-locking control;
it is not an implemented Rust lock-file protocol or stale-writer fence.

After stopping peer services, unmount only client B's fixture mount. Provision
an owned local root/.file-mover at the same configured path and rerun the identical
qualification configuration/state database. Observe startup admission without
an expected-filesystem/export policy, and also check the production executable's
local-directory behavior. Production's NFS refusal remains a separate control.
The local directories contain no producer data and no jobs are submitted.

`ownership.probe_status` describes completion of the diagnostic, while per-case
exclusion/refusal fields describe the protection actually observed.
`production_authorized` stays false. A diagnostic PASSED must never be described
as a passed production fence if startup exclusion or missing-mount refusal is
false. Both known gaps and successful controls belong in the scenario catalog.

The initial run `nfs-20261015T024809Z-669ad4ee` completed both cross-client
profiles: same-client exclusion and regular-file remote controls passed, while
both independent peer services reached readiness. It then failed fixture setup
because UID 1000 could not create a local stand-in below the root-owned unmounted
mount point. Cleanup had no errors. This is an overall FAILED run, not a completed
ownership qualification. Run `nfs-20261015T025358Z-34a0f768` repeated both
cross-client findings but failed at the proposed chown setup: the restricted
client has SYS_ADMIN for mounts but intentionally lacks CHOWN. Its cleanup also
had no errors. The final setup lets the owning administrator chmod only the
empty unmounted `/tmp/nfs` inside the disposable peer container to 1777, then UID
1000 creates its own 0700 stand-in directories. No new capability is granted;
no host mount point or production directory is changed. These two setup failures
are not evidence of missing-mount refusal by the service.

Production gate `20261015T024021Z-c93b14b0` passed 115 tests per profile;
qualification gate `20261015T024033Z-df962b10-nfs-qualification` passed 116.
Both passed formatting/Clippy, debug/release zigbuild, ELF/loader/library audits,
six negative audit controls per mode and exact pinned SLES userspace execution.
Maximum GLIBC remains 2.18 and the locked external Linux graph remains 42 packages.
Both gates finished with no cleanup errors using the documented Windows/Podman
WSL2 engine selection and native Linux container build directories. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Final fixture `nfs-20261015T025958Z-71e9bee8` PASSED its diagnostic checks and
cleanup, with all six normal baselines, four diagnostic cases and the retained
inherited-lock/startup/outage probes completed. See the full
[ownership evidence](RUST-NFS-OWNERSHIP-EVIDENCE.json), including audited binary
hashes, driver source hashes, service logs and the server's distinct client IDs.
The protection aggregate is false and production authorization is false.

| Observation | Debug | Release |
|---|---|---|
| Same-client competing coordinator | Refused before SQLite/readiness | Refused before SQLite/readiness |
| Other NFS client / independent local database | Reached readiness against the same source | Reached readiness against the same source |
| Regular-file remote-lock control | Peer refused while held; acquired after release | Peer refused while held; acquired after release |
| Qualification restart on underlying local stand-in | Same config/database reached readiness | Same config/database reached readiness |
| Production NFS startup control | Refused before SQLite/readiness | Refused before SQLite/readiness |
| Production startup on local stand-in | Reached readiness | Reached readiness |

SC-053/054 are **Gap**, not supported production scenarios. No cross-client job
race or wrong-location transfer is claimed: no submissions were made during
overlap or local-stand-in admission. The local-stand-in result means that the
configuration has no way to express an expected NFS/export identity, not that
the production binary has started accepting NFS. Source/destination data and
previous full interruption/long-outage evidence remain unchanged.

The immediate next implementation is explicit source root binding/state
enrollment, followed by pinned destination binding and qualified cross-client
exclusion/fencing as specified in ROOT-OWNERSHIP-DESIGN.md. This increment
deliberately does not replace the custody lock or add a marker before its
authorization, migration and stale-worker rules are implemented and tested.

The owning runner restored NFS, confirmed process completion and unmounted before
removing its resources. Final inventory showed no containers or fixture networks/
volumes; only the default Podman network and retained Rust toolchain/registry
caches remained. Python syntax/CLI checks, scenario IDs/evidence mappings,
documentation links, whitespace and the historical trace-matrix gate also pass.
No Rust requirement coverage is inferred from scenario keys. DOC-01–06 remain
the user-guide backlog, with DOC-04/05 now including these ownership limitations.

This increment does not rerun the earlier full runtime interruption or long-outage
matrices. Two container clients use distinct network/mount namespaces and
server-observed NFS client identities, but share kernel
`6.18.33.2-microsoft-standard-WSL2` and the runner CPU. This is not independent
physical-host, old-kernel, partition, reboot, lock-reclaim or power-loss evidence.
