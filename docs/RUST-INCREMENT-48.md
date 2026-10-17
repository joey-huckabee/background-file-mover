# Rust increment 48: bootstrap and source-read coordinator death

Recorded 2026-10-17 on `feature/rust-transfer-coordinator`.

## Finite scope and pass conditions

Extend the retained disposable hard-NFS fixture with
`--coordinator-death --death-scope bootstrap-source-read`. Keep the default
claim/copy/verification matrix and its increment 47 evidence intact. This selects
eight cases: debug/release × bootstrap/source-read × blocked/following local stop.
These phase cases use an NFS source and local destination to isolate source I/O;
the six normal baselines also cover NFS destination and both-NFS layouts.
Do not add runtime features, dependencies, retry/review changes or deletion.

Bootstrap starts with a freshly provisioned, not-yet-enrolled source and
unavailable NFS, without a pause hook or an existing database. Require exactly
one actual bootstrap worker in D, bounded local Starting status, a connected/sent but pending health request and no SQLite database/sidecars. The
blocked case kills only the coordinator PID. The terminating case uses the existing
two-second configured stop: record prompt confirmed exit separately, or require
ShutdownIncomplete/exit 2 and kill the coordinator while its worker remains D.
The existing 30-second bootstrap assignment deadline is unchanged.

Source-read uses the retained qualification-only pre-read cache advice/rendezvous.
Require durable 202/custody, a preserved producer-reused path, zero-byte destination
staging and an incomplete read loop after releasing the worker into unavailable
NFS. Verify D directly; advice alone is not proof of a blocked read. Apply the
same blocked/following-stop distinction as bootstrap.

For each surviving orphan, bracket three independent raw-flock/logical-status
observations with actual D state, require OwnerUnavailable/exit 2, and refuse all
three competing effect commands before SQLite/source effects. Preserve the local
epoch until old exit. Record raw-lock closure separately; this phase expansion
does not require reproducing increment 47's verification-specific closure in each
new worker mode and does not replace its stricter regression.

Restore NFS and confirm old worker exit before any recovery start. Bootstrap must
still have no database or successful health response, with original input bytes
intact, before explicit first enrollment and the first submission. Enrollment is
performed only after restoration/confirmed exit, using the original config/state;
no state file is deleted or bypassed. Recover using that same config/state, replace
only the inactive epoch with the new coordinator group, and require Committed,
SHA-256/manifest agreement, retained claimed source and preserved reused paths.
Interrupted source-read copies must preserve attempt-1 staging and restart as
attempt 2; bootstrap's first transfer uses attempt 1.

Keep six normal-transfer, twelve NFS-state-parent, 184 state-file refusal and
inherited-lock/startup/interruption regressions. Audit exact sources, artifacts,
script hashes and cleanup. Every Rust build/test uses the mandatory production
and qualification GNU/glibc-2.22 zigbuild/ELF/SLES 12 SP5 userspace gates.

## Results

Fixture `nfs-20261017T200408Z-cafee8b6` passed all eight cases; see
[complete phase evidence](RUST-NFS-STARTUP-READ-DEATH-EVIDENCE.json).

| Worker phase | Debug blocked | Debug following stop | Release blocked | Release following stop |
|---|---|---|---|---|
| Fresh bootstrap | Surviving D orphan retains ownership | Prompt confirmed exit | Surviving D orphan retains ownership | Prompt confirmed exit |
| Accepted source read | Surviving D orphan retains ownership | Prompt confirmed exit | Surviving D orphan retains ownership | Prompt confirmed exit |

Four actual surviving orphans retained ownership across three bracketed samples
each, all returning OwnerUnavailable/exit 2. Twelve competing service/initialize/
transfer commands refused (maximum 0.968 seconds); no ownership loss occurred.
Sampled orphan status took at most 0.937 seconds. All four stop cases exited
promptly (maximum 1.157 seconds including Podman execution overhead) with a
configured two-second wait; none qualifies a surviving terminating-orphan branch
or the default-60 deadline branch. No new case observed raw flock closure; retain
increment 47's separate stricter passing counterexample evidence.

All bootstrap cases had one actual blocked child, a connected/sent unanswered
health request, no SQLite before death or after old exit, and unchanged original
input hash. Local Starting observations took at most 0.938 seconds. After NFS
restoration/confirmed exit, explicit first enrollment and the first recording
completed on attempt 1, using the original state directory/guard. Source-read
cases had a D reader with an incomplete loop and zero-byte staging at outage;
recovery reached Committed on attempt 2 with attempt-1 staging and private source
preserved. Every case verified destination/source SHA-256, completion manifest,
producer-reused path and stable root identities; source cleanup stayed false.
The epoch stayed unchanged until old exit and was normally replaced by the new
coordinator group under the same boot, PID namespace and guard identity.

Retained checks passed six normal NFS transfers, twelve NFS-state-parent refusals
and 184 file-owner/mount/control refusals across fourteen preserved fixtures
(maximum 0.985 seconds). OS inherited-lock/interruption, isolated startup and
stable-root restoration checks passed. The retained global startup status took
0.937 seconds; SIGTERM confirmed bootstrap exit before restoration without SQLite
or readiness. Current script hashes match the saved report. Cleanup errors are
empty, and independent resource inspection found no containers or fixture volumes/
networks, only the two existing toolchain/cache volumes and default network.

Reproduce this exact artifact selection with:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T162146Z-b28d902b --qualification-gate rust/validation/20261017T162159Z-32bce9a2-nfs-qualification --isolated-startup --coordinator-death --death-scope bootstrap-source-read
```

Future runs can supply fresh passing production/qualification gate directories;
source/archive and executable hash checks remain mandatory.

## Compatibility and exact artifacts

Fresh production `20261017T195308Z-0fbd983f` passed 204 tests per profile;
qualification `20261017T195309Z-ea5be268-nfs-qualification` passed 205 per profile.
Each gate passed twenty ELF audits and six negative controls in pinned SLES 12 SP5
userspace, using cargo-zigbuild GNU/glibc 2.22. The package graph remains 42 external
packages, maximum required GLIBC_2.18 and the standard GNU loader. No Rust source,
Cargo dependency/feature, schema, wire format or runtime policy changed.

The complete 61-file source inventories and every artifact hash match current
inputs. See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json). The fixture ran
with the previously passing increment 47 gates `20261017T162146Z-b28d902b` and
`20261017T162159Z-32bce9a2-nfs-qualification` while the fresh gates completed.
Their complete Rust snapshots match current files, and all four service binaries
(production/qualification × debug/release) are byte-for-byte identical to the fresh
passing binaries. Preserve the fixture's actual gate IDs in its raw report; this
is exact-artifact reuse with fresh compatibility validation, not a rebuilt or
unaudited fixture binary. Both fresh gates completed cleanup successfully.

## Remaining scope

Production NFS and source deletion stay disabled. This is one controlled modern
server/client kernel with pinned SLES userspace; it does not qualify old kernels,
NAS power loss/reboot/reclaim, both-NFS crash layouts, delayed RPC settlement or
systemd/account policy.
Enrolled/populated-state bootstrap death, publication/manifest coordinator-death
phases and other SH-01–14 obligations remain
open under FR-03/05. Registration and offline repair remain deferred. Maintain
SC-029/034/041/092/093/095 and DOC-03/04/05 without changing their stable IDs.
