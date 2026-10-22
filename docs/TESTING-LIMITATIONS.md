# Testing limits and what the evidence means

This document explains the boundaries of the Rust evidence. A pass establishes
the finite cases and configuration recorded by that test, not universal safety
under every machine, filesystem or failure. Read the raw reports and
[scenario catalog](RUST-SCENARIOS.md) alongside this matrix. All eight
[first-release gates](RUST-FIRST-RELEASE.md) remain open.

## Current operating boundary

The production build remains a trusted loopback/protected-local-filesystem
prototype. Production NFS and source deletion are disabled. The retained NFS
qualification build/fixtures exercise selected NFS behaviors, separately from
the production feature boundary. A recording generator keeps completed files
unchanged until 202 and then has no delivery-monitoring duty. Destination
completion requires the validated manifest, not just a visible payload file.

The confirmed ownership profile is one mover, same-host restart, same user,
configuration and fixed local state, with private working folders. Cross-host
takeover, alternate-state bypass and hostile same-UID/root interference are not
covered by that cooperative profile. They are not made safe by a passing local
lock test. Preserve original state and conservative refusal on uncertain effects.

The equivalent-systemd-228 lifecycle lab requires a rootful privileged Podman VM
with working named-v1 cgroups and cgroup namespaces. The manager/bootstrap has that infrastructure
privilege; tested mover processes run as UID/GID 1000 with no capabilities and
NoNewPrivs. Rootless engines, other container backends and kernels that disable
the required hierarchy are not qualified by this recipe. Do not change VM boot
settings or production/NAS privileges to conceal an unsupported lab backend.
The standalone publication/NFS fixture does not start systemd or bootstrap that
hierarchy; its client observer needs mount and selected syscall-observation
capabilities, while the mover/worker capability checks remain unchanged.

## Evidence matrix

| Test layer | What the existing evidence can establish | What it cannot establish | Remaining work or release implication |
|---|---|---|---|
| GNU/glibc ABI and SLES userspace | Exact gated debug/release binaries/tests load and execute in pinned SLES 12 SP5/glibc 2.22; ELF loader, imported libraries/symbol versions and negative controls pass; locked package/features are checked. | Every program path, old-kernel syscall behavior, every x86_64 CPU, vendor NFS behavior or systemd deployment. Containers share the runner kernel/CPU. | Keep this gate for every Rust build/test. Declare/qualify kernel/CPU/storage/deployment profiles separately; FR-06/07 remain open. |
| Local Rust/API/SQLite/filesystem tests | Specified protocol decisions, idempotency, protected custody, copy/reread verification, publication/recovery and selected invalid-input/failure cases work for the exercised protected local setup. | Exhaustive input/failure/interleaving coverage, physical-media durability, arbitrary filesystem semantics, all migration/upgrade cases or hostile privileged mutation. | Maintain meaningful boundary/fault tests and Rust requirements traceability; complete remaining contracts/recovery/migrations; FR-01/05/07. |
| Controlled NFS fixtures | Selected real hard-mount blocking, source/destination outages, coordinator death, ownership retention and original-state recovery have per-case evidence. Some fixtures use separate exports or independently interrupted endpoints. | All operations/directions/timeout branches; server-accepted delayed RPC settlement; every NFS version/security/mount option; actual NetApp/Isilon behavior, firmware, caches or physical network failures. Endpoints still share the VM kernel/infrastructure. | Finish the declared SH/NFS matrix, actual mount/root scope and conservative delayed-effect reconciliation/refusal for the supported profile before enabling production NFS; FR-03/05. |
| Deterministic pauses and SIGSTOP | A selected userspace boundary or stopped process can be reproduced and its local ownership/lifecycle tested. | An in-flight server RPC or uninterruptible kernel operation merely because execution paused near it. A stopped local worker is not a blocked NFS worker. | Label pause-only evidence separately. Require actual blocked state/syscall evidence where claimed; remaining namespace/synchronization/delayed-effect cases stay open. |
| Source synchronization versus native transport capability | [85](RUST-INCREMENT-85.md)/SC-119 observes 32 successful source fsync calls in four actual claim workers and proves native source-export FILE_SYNC WRITE success withholding/release/drop-reconnect on both buffered layouts. Raw call/reply intervals and independent server inode/bytes are retained. | No eligible service WRITE/COMMIT occurs inside those source-sync intervals; zero mover source-sync reply-loss/death cases are qualified. Native probes, broader-window RPCs and successful fsync do not establish service recovery or namespace power-loss durability. | Use the [source-sync lab](NFS-SOURCE-SYNC-LAB.md). Further service fault selection needs a positive actual RPC; keep server recovery/delayed settlement, other workloads and FR-03/05 open. Production NFS/deletion stay off. |
| Native NFS server-recovery capability | [86](RUST-INCREMENT-86.md)/SC-120 proves four retained-FD/handle/backing-inode native recoveries across NFSD and confirmed same-container termination/start, with BADSESSION/new sessions/changed verifiers, exact wire proof and clean final inventory. | Network namespace and VM boot ID do not change. No Rust mover, lost UNSTABLE data, complete reclaim, delayed-effect settlement, actual NAS/VM reboot, independent storage/cache or physical durability is qualified. Two earlier failed acquisitions remain failed. | Use the [complete lab](NFS-SERVER-RECOVERY-LAB.md). Select actual worker cases under the measured facility before claiming service recovery; FR-03/05 stay open and production NFS/deletion stay off. |
| Actual mover controlled server recovery | [87](RUST-INCREMENT-87.md)/SC-121 passes four debug/release source-read cases, same live worker/attempt 1, retained source/state/staging inode, payload/manifest and clean-restart replay, after four native controls and independent audit. | Two mounts share one client filesystem/backing volume. Container cases stop NFSD before SIGKILL/exit/start; repeated abrupt controls failed. No distinct-client-filesystem/independent-share, other phase/death, NAS/power or old-kernel qualification. | Use the [complete lab](NFS-SERVER-MOVER-LAB.md); preserve four failed acquisitions/rescues and the rejected device assumption. Finish remaining server/failure/mount/workload/deployment matrix; all eight gates and production NFS/deletion stay open/off. |
| Local ownership guard and epoch | Selected cooperative same-host starts/workers remain excluded through observed process/thread exit, including cases where the raw lock closes before a surviving group ends. | NAS-side cancellation/settlement, cross-host fencing, intentional alternate-state launches, stale backup adoption or global cryptographic export identity. | Keep original local state, current scope checks and independent lifetime evidence. Complete remaining SH cases; do not use free lock/timer/process exit as remote-settlement authority; FR-03/05/06. |
| Systemd 252 lab | Increment 57 records selected real-manager local lifecycle, account refusal, bounded restart and recovery behavior with the mover in pinned SLES userspace. | Native SLES systemd 228, its maintenance patches, old cgroup/kernel behavior, actual host authorization/install policy or combined NFS blocking. | Retain the report, but do not substitute it for the older-manager/deployment matrix; FR-05/06. |
| Systemd 228 equivalent lab | Increment 59 passes ten selected local lifecycle records across both profiles/build modes, actual unit verification, eight armed races, independent controller checks, original-state recovery and owned-hierarchy cleanup. Mover/children/controllers retain the SLES root; the approved manager uses controller-free v1 cgroups. | Exact SLES-maintained RPM revision: the manager is a pinned Leap 42.3 equivalent. It also does not test an old SLES kernel, resource-controller policy or combined hard-NFS/systemd. A candidate key list alone does not prove lifecycle. | Keep 58's BLOCKED/NOT_RUN history and 59's failed-attempt evidence. Verify the declared package/deployment profile before claiming native SLES-manager support; FR-05/06. |
| Systemd 228 / actual hard-NFS mid-copy | Increment 60 passes four managed stop/death records in debug/release with distinct controlled NFSv4.1 exports/local state, actual D workers, old-thread/epoch observations and original-state recovery. | Every operation/endpoint/deadline branch, exact RPC settlement, independent NAS failures, persistent disk/power durability, exact vendor/kernel policy, full account/install or production-scale behavior. Prompt exit is distinct from a retained uncancellable worker. | Read actual per-case outcomes and lab section 12. Finish remaining SH/FR-03/05/06 obligations; production NFS and deletion remain disabled. |
| Systemd 228 / restart after incomplete stop | Increment 61 passes debug/release with three explicit starts each, 91.953/92.062-second outages after incomplete stop, 25.547/25.328-second quiet windows, preserved old epoch/D threads, 24 direct competitor refusals and original-state recovery. | Managed starts fail at the occupied listener before the guard; separate alternate-port/effect commands test the guard. No rate-limit saturation or automatic replacement is observed. This does not qualify other listener configurations, phases, endurance, every interleaving or remote settlement. | After storage restoration and confirmed old exit, all snapshots remain NoActiveOwner over 12.344/12.672 seconds; explicit reset/start recovers. Shipping restart/account/persistence and remaining SH/FR-03/05/06 stay open. See lab section 13. |
| Destination-only outage before startup / early delivery | Increment 62 passes eight empty/populated debug/release death/stop records: source startup, health 200/Running and confirmed custody/replay 202 succeed while a real destination delivery worker is D. Four blocked orphans retain ownership and refuse twelve competing commands; original database/source/receipt/binding/partial survive recovery. | Destination-blocked source bootstrap, every later phase, uncancellable/default-60 deadline, arbitrary interleavings, physical NAS or RPC settlement. All four short stops exit promptly; no surviving terminating orphan is observed. Live SQLite/WAL hashes are diagnostic and not atomic backups. | See SC-096 and the dedicated destination-startup lab. Preserve control readiness versus destination health/commitment distinctions, original state and actual old-thread exit. Remaining SH/FR-03/05/06 and production NFS/deletion gates stay open. |
| Buffered same-share workers | [Increment 70](RUST-INCREMENT-70.md) exercises debug/release baselines and durable claim/file LINK crash recovery with disjoint private roots on one NMP-41B mount/export and local state; original-state replay preserves custody, manifest and newer producer bytes. | Pending or withheld RPC replies, outages, NAS/server reboot/failover or explicit grace/reclaim, other-client caches, power/persistent-media durability, all worker phases or production-scale endurance. The two-copy inode check is not an I/O-volume benchmark. | Follow [the same-share lab](NFS-SAME-SHARE-LAB.md); complete remaining buffered fault/sync boundaries. FR-03/05 remain open; production NFS/deletion stay off. |
| Process death versus machine/storage loss | SIGKILL/restart exercises selected application crash boundaries while the kernel/storage stay up. | Power loss, torn media writes, reboot persistence, volatile NAS/controller-cache behavior, disk/controller failure or a server's truthfulness about durable acknowledgements. | Qualify declared durability assumptions and storage/reboot/upgrade behavior in a controlled equivalent environment. Do not promise hardware-failure durability from process-crash tests; FR-03/05/06/08. |
| Capacity/admission tests | Selected bounded fill/restoration, unchanged-policy refusal/retry and existing-job recovery are exercised; sampling is configurable and off by default. | Physical reservation, quotas/inodes, all external-writer races, sparse/deduplicated/compressed accounting, arbitrary concurrent load or all destination-shortage conditions. | Complete remaining FR-02 cases and profile-specific margins; preserve existing-job retries. Retained logical bytes and filesystem available capacity answer different questions. |
| Timing and races | A finite bounded observation can demonstrate the measured deadline/refusal and stable ownership at its sample points. Armed starts exercise selected competing launches. | Fairness, all scheduling interleavings, zero arbitrarily short overlap between samples, universal cancellation bounds or progress under every kernel/server stall. | Report loaded budget, timestamps, actual outcomes and observation limits. A timeout is not cancellation; uncertainty must still prevent conflicting effects; FR-03/05. |
| Workload size and endurance | Finite fixture payloads, queues and capacity cases exercise their recorded sizes and durations. The lifecycle lab uses a nested 2 MiB plus 17 byte input. | Sustained roughly 100 GB recordings, a production backlog, multi-day memory/descriptor/retention behavior, NAS throughput/latency or recovery time at production scale. Small-file correctness is not a performance or endurance qualification. | Declare representative size/concurrency/retention targets and run bounded scale/endurance cases on suitable equivalent infrastructure before promising production capacity or timing; FR-02/05/06/08. |
| Account and remote security | Local identity/mode/capability checks and selected refusals exercise the stated trusted local profile. | Actual administrator system-service authorization, full sandbox correctness, TLS/proxy/caller binding, certificate lifecycle, remote adversarial exposure or registration. User= does not authorize systemctl. | Implement/qualify the remote contract and approved deployment policy before remote use; registration remains deferred; FR-01/06/08. |
| Packaging and release evidence | Pinned inputs, crate checksums, ELF/source/driver/artifact hashes and exact local test execution can be audited. | A finished offline/reproducible shipping bundle, all notices, upgrade/rollback safety, remote CI success or release readiness merely from the local counts. | Finish FR-06/07/08, the declared release-candidate matrix and producer/consumer/operator walkthroughs. No completion percentage follows from increment/test counts. |

## Important distinctions

[Post-unlink qualification](RUST-INCREMENT-73.md) adds eight buffered
same/separate-share debug/release process-crash cases after staging unlink has
returned, before the following staging-directory sync is called. Require staging
absent and the original final one-link inode/content both before crash and after
old-worker exit, then attempt-1 recovery and stable committed replay. The worker
remains at an unreleased local pause and is SIGSTOPped during the controlled joint
NFSD outage. This is not a pending fsync/COMMIT, successful RPC reply withheld or
power-loss test; retained server/cache state does not establish persistent-media
durability. The [lab](NFS-BUFFERED-POST-UNLINK-LAB.md) needs no extra syscall-
observer capabilities. One server/client/shared modern kernel cannot establish
independent NAS/cache failures, old SLES kernel semantics or production-scale
behavior. Guard observations are measured separately; contender probes precede
worker SIGKILL and add no terminating/free-raw-guard branch. Full FR-03/05 and
production NFS/source deletion stay gated.

The initial post-unlink run fails a combined health/status timing assertion:
two requests plus host copy/Podman overhead total 5.344 seconds, with no individual
timings retained. It cannot establish an individual request failure or a passing
eight-case matrix. The corrected fixture measures each request independently
below five seconds and keeps the combined value only as diagnostic cost; service
timeouts, retry/review and shutdown deadlines remain unchanged. Preserve the
[failed initial report](RUST-NFS-BUFFERED-POST-UNLINK-INITIAL-EVIDENCE.json) and
read the final measured cases separately.
The final eight cases pass: maximum measured health/status requests are
1.937/1.922 seconds including host overhead. All sixteen sampled orphan guards
remain contended (no observed early raw-lock closure); all twenty-four competing
commands refuse before worker SIGKILL. These are the observed finite branches,
not new terminating/free-guard or universal timing guarantees.

[Buffered publication/manifest qualification](RUST-INCREMENT-72.md) distinguishes
actual D-state client unlinkat on an owned staging-parent descriptor from a
returned LINK paused before following sync. The latter is a stopped-process
crash with live server/cache retained, not an in-flight fsync/COMMIT failure or
power loss. The sixteen-case matrix covers debug/release on same/separate shares
of one controlled server; it does not establish independent NAS failure/cache
coherence or server reboot/failover/reclaim and delayed mutating settlement.
Read the [lab](NFS-BUFFERED-PUBLICATION-LAB.md) and actual per-case results for
original-inode reconciliation, manifest validity, raw guard observations and
confirmed old-thread exit. Existing foreign-target no-clobber negative tests
remain separate; this matrix adds no concurrent foreign-target conflict race.
Contender probes precede worker SIGKILL; following it, the harness waits for
confirmed exit. Do not infer a new terminating/free-raw-guard contender branch.
Actual results show all 32 orphan guard samples contended, with no observed early
raw-lock closure. All eight pending-unlink cases retain two owned aliases after
old-worker exit; normal recovery removes staging. No successful server REMOVE
or withheld success reply is inferred from the client syscall observation.

Same-ID POST replay revalidates source custody. The initial buffered-publication
run's expectation of 202 during joint source/destination outage failed; it did
not capture its actual response body/code. Keep that run failed rather than
claiming a specific response. The corrected matrix checks replay before outage
and after original-state recovery; during outage it checks health/status/control
without adding a separate custody-validation worker. This changes fixture scope,
not service retry/review/timeouts or recorder obligations. Production NFS and
source deletion remain disabled; full FR-03/05 qualification remains open.

[Lost-reply qualification](RUST-INCREMENT-64.md) proves a selected NFSv4.1
REMOVE completed on the live server while its matching successful reply was
withheld and the actual client stayed D. Two capability controls precede four
file/manifest worker cases. The passing loss model discards the reply and closes
that connection, then observes same-session/sequence replay on a new connection;
it does not promise bounded retries after silently discarding on a healthy TCP
stream. The initial timeout/cleanup refusal is preserved as failed evidence with
separate recovery. This advances selected SH-11 evidence beyond the pre-server
unlink stalls/pre-sync pauses in increment 63, without qualifying LINK/COMMIT/fsync
loss, power/disk/server reboot, physical NAS isolation, old-kernel NFS behavior or
arbitrary delayed settlement. The relay's connection closure is lab intervention,
not an implemented service recovery action or universal signal/deadline guarantee. See [the step-by-step lab](NFS-LOST-REPLY-LAB.md).



[Publication interruption evidence](RUST-INCREMENT-63.md) adds twelve finite
cases: four blocked client unlinkat syscalls and eight process crashes after
link/unlink returned before sync. The selected syscall number, staging-parent
file descriptor and D state identify client execution, not a particular RPC
reaching the server or remote settlement. The eight pauses are before sync,
not in-flight fsync failures; retained live-server tmpfs/cache state is not
power-loss durability. Original-state inode/hash reconciliation passes within
this scope. See [the step-by-step lab](NFS-PUBLICATION-SYNC-LAB.md). Remaining
link/sync RPC, server recovery and storage-durability gates stay open.



[Increment 62](RUST-INCREMENT-62.md) and
[the destination-startup lab](NFS-DESTINATION-STARTUP-LAB.md) distinguish two
different outage boundaries. Source bootstrap can be blocked before store open,
with Starting/unready and frozen existing-state evidence. A destination-only
outage can instead permit source startup, health 200/Running and claimed 202
acceptance/replay while an early supervised delivery session is blocked. Readiness
does not certify destination health or recording commitment. SQLite/WAL bytes
can legitimately change after open/acceptance/scheduling; diagnostic live-file
hashes are not atomic backups. Read actual per-case results before claiming a
specific death/stop branch; keep other phases, exact RPC settlement, physical NAS,
power durability and production/deployment support separate.

The selected restart-after-incomplete-stop matrix in
[increment 61](RUST-INCREMENT-61.md) extends the mid-copy lifecycle scope, with
three spaced explicit start requests per profile, at least 90 seconds of outage
after incomplete stop, a quiet window and restoration/old-thread-exit checks.
Read the actual results for manager refusal versus application guard refusal
and automatic versus explicitly requested recovery. These are finite observations
on the same controlled server/kernel, not an indefinite restart-storm guarantee,
proof of arbitrarily brief non-overlap, shipping restart-policy qualification or
NAS RPC settlement. The default 60-second application wait is unchanged; shortened
fixture waits and rate limits are recorded separately. Other operation phases,
independent endpoints, account/persistence and full FR-03/05/06 remain open.

1. **A byte-identical tested artifact is stronger than a matching version label.**
   Keep source/feature/toolchain and exact ELF hashes. A library's version number
   alone does not prove that it imports no newer glibc symbol or loader.
   The ELF audit checks dynamic imports; it is not a complete direct-syscall or
   machine-instruction compatibility audit. Passing with old userspace on the
   current WSL2 kernel therefore does not prove execution on an old kernel/CPU.
2. **A package-equivalent manager is not the exact vendor package.** The 228
   equivalent tests old-version semantics in a useful controlled setting, while
   SLES maintenance patches and the declared supported package revision remain
   a separate qualification obligation. This can be done in a container; it
   does not require a real SLES installation.
3. **A live PID, active unit or successful stop job is not an application result.**
   Confirm health/readiness and the mover's ownership/shutdown status. Even
   MainPID 0 can coexist with a live original owner. Observe actual old-worker
   exit before replacement; remote effects need their own reconciliation.
   The 228 fixture also exposed a candidate unit whose global ExecStop stopped
   the legitimate owner after a contender failed its guard. The corrected legacy
   fixture uses unit-owned SIGTERM and tests the controller independently.
   Selected passes for a different manager never qualified that failure path.
   In the increment-60 hard-NFS death cases, the old worker remains D and the
   unit is failed/timeout with MainPID 0; no automatic replacement is observed
   during the bounded window. Recovery explicitly starts the original unit
   after restoration/confirmed old exit. Eventual automatic recovery and
   indefinite restart/storm behavior remain unqualified.
   Increment 61 adds repeated starts after incomplete stop: each requested
   contender exits at listener binding while the old coordinator still owns
   that port; no managed guard-refusal or rate-limit trip is observed. The final
   quiet windows show no further activation, and explicit restart succeeds after
   restoration/old exit and a separate 12-second no-owner observation. This is
   finite manual-recovery evidence, not an automatic-recovery guarantee.
4. **NFS process exit is not remote settlement.** A server may have accepted work
   whose result is uncertain locally. Preserve custody, receipts, partials and
   original database/configuration; do not force retry or delete a guard to make
   a status green. Unsupported repair remains a stop/review path.
5. **The approved bootstrap is a broader boundary.** It briefly accesses shared
   VM cgroup state. Private namespaces afterward do not erase that fact. Named
   hierarchy cleanup and retained kernel references must be verified separately
   from container deletion. Do not generalize that authorization to production.
   The lab checks both owned-directory removal and disappearance of the named
   hierarchy, with bounded empty-root mount/unmount retries. Its earlier cleanup
   failure remains evidence; a successful container removal alone was inadequate.
6. **Content verification and durable storage are different.** Hashing while
   copying and rereading staging validates the bytes returned to the client.
   Normal filesystem delivery is 3N logical data I/O; OS/server caches and metadata
   mean this is not a promise of exactly 3N physical disk/network traffic. These
   tests cannot prove that data survives loss of hardware behind a server's
   acknowledged durable write. That requires the declared storage assumptions
   and corresponding durability qualification.

## How a release gate can close

Choose a finite declared supported profile: architecture/CPU policy, kernel,
manager/package revision, local persistent-state storage, source/destination
filesystems, NFS version/mount/security assumptions, and account/access policy.
List required acceptance/failure cases before running them. Link actual passing
artifacts and meaningful failure evidence, document conservative unsupported
outcomes, and provide the corresponding user instructions. A documented limit
does not waive a requirement included in the first release.

No finite suite proves that every failure is impossible. The release must pair
tested guarantees with explicit assumptions and refusal/review behavior when
those assumptions or old effect outcomes are uncertain. Testing remains in
controlled containers/equivalent environments; exact-kernel or storage-failure
questions may need a suitable isolated engine or controlled guest environment.
Do not replace them with claims about an untested real installation.

## Deliberate exclusions versus unfinished requirements

S3, generator registration, offline repair and cross-host takeover remain deferred
unless separately scheduled. Their absence is not a hidden passing test. Source
cleanup is different: conservative configurable cleanup is in first-release
FR-04, remains disabled/unimplemented here, and must not be enabled from these
local lifecycle tests alone. Remote producer access is also a first-release
requirement still pending FR-01; the loopback prototype does not satisfy it.

For the exact remaining deliverables use [the first-release checklist](RUST-FIRST-RELEASE.md),
the future-only [roadmap](ROADMAP.md), the [NFS contract](NFS-OWNERSHIP-FENCING-CONTRACT.md)
and [remote-access contract](REMOTE-API-ACCESS-CONTRACT.md). The
[systemd lab procedure](SYSTEMD-LIFECYCLE-LAB.md) explains infrastructure setup,
each test step, evidence and cleanup. Update this matrix with each newly qualified
profile; do not silently expand a passing result's scope.

[Increment 65](RUST-INCREMENT-65.md) qualifies four selected debug/release file/manifest LINK success-reply-loss cases after independent and repeated server-completion/withheld-success/pending-client controls. Recovery preserves original inode/content and attempt one. The loss model explicitly includes connection interruption; it does not qualify source-claim LINK, COMMIT/fsync reply loss, persistent-media/power/server recovery or old kernels. Production NFS and source deletion remain disabled. The [lab section 8](NFS-LOST-REPLY-LAB.md#8-link-completion-with-a-withheld-success-reply) gives step-by-step prerequisites, controls, syscall observations, ownership/recovery and normal-unmount cleanup. A successful LINK and two server-local names do not prove following fsync/COMMIT completed, recording commitment or universal SIGKILL/shutdown bounds. Modern shared-kernel/tmpfs containers remain different from physical NAS and old SLES kernels. Historical failed healthy-stream silent-loss evidence stays failed.

[Increment 66](RUST-INCREMENT-66.md) qualifies four selected debug/release source-claim LINK/REMOVE success-reply-loss cases after independent and repeated source-server completion/withheld-success/pending-client controls. Initial/same-ID submissions remain retryable 503 with paths unreleased until original-state custody recovery confirms 202; only then does the producer reuse paths. Original claim inode/content, job ID, database/enrollment and attempt one survive delivery. Loss explicitly includes connection interruption; COMMIT/fsync, remaining claim/mount/security boundaries, server/media/power durability and old kernels remain unqualified. Production NFS and source deletion remain disabled. One controlled NFS client hosts both the producer writes and mover reads; separate producer-client cache/visibility is not qualified. The [lab section 9](NFS-LOST-REPLY-LAB.md#9-source-claim-link-and-remove-with-success-replies-withheld) documents source routing from first mount, four non-Rust controls, real worker syscalls, pending acknowledgements, safe same-ID recovery and normal-unmount cleanup. The fixture retains the existing ten-second submission deadline and allows fifteen seconds including Podman overhead; health/job/status checks remain five seconds. A producer path disappearing before 202 does not authorize reuse or prove loss of the privately retained payload. Selected connection interruption and old-thread exit are not universal cancellation or remote-settlement proof.

## Synchronization observation limits (increment 67)

[Increment 67](RUST-INCREMENT-67.md) correlates four actual debug/release claim/delivery synchronization traces with raw NFS traffic. Selected noac sync intervals have no observed outgoing RPC; separate buffered OS controls prove stable WRITE reply withholding/recovery, not COMMIT or mover sync-loss support. See [the reproducible sync lab](NFS-SYNC-LAB.md). No Rust/service/dependency policy changes; production NFS and source deletion remain disabled, and FR-03/05 remain open. A separately privileged external ptrace observer uses modern-kernel APIs and changes scheduling; it is not deployed with the service. Local proc descriptor inspection avoids inducing target NFS I/O. Unknown/nonempty or overflowed/truncated trace windows cannot prove RPC absence. Buffered control mount options are deliberately separate from the service fixture. Server-reported FILE_SYNC and tmpfs bytes do not establish power-loss durability. Both initial fixture failures and exact sources remain preserved with clean cleanup. The simple JSON-until-202 recorder and manifest-based consumer workflow are unchanged.

## Mount-profile model limits (increment 68)

[Increment 68](RUST-INCREMENT-68.md) selects buffered hard/TCP NFSv4.1/sec=sys
as a first-release qualification candidate and retains noac as a separate
fixture diagnostic. The [contract](NFS-MOUNT-PROFILE.md) and
[lab](NFS-MOUNT-PROFILE-LAB.md) validate read-only inventory decisions, not new
Rust startup enforcement or authorization for production NFS/deletion. Earlier
noac worker evidence and buffered OS-only WRITE controls retain their scope.
The initial failed assumption is preserved: unmount/remount reused the mount IDs
and the entire observed pin. Matching snapshots cannot establish mount continuity.
NFSD-zero inventory still matches, so it also cannot prove availability, effect
settlement, real path/descriptor custody, symlink safety or authenticated NAS
identity. Changed effective options refuse prior pins in the model; concurrent
replacement/alias exclusion and protected descriptor/enrollment rechecks remain
required. New service enforcement remains pending, including unchanged-job replay.

Synthetic v3/v4.2/UDP/security-option mutations are negative parser/policy controls,
not actual variant mounts. Same-share/mixed-profile matches are not mover transfer
or recovery tests. Root-squashed child exports demonstrate only ordinary fixture
UID/GID access. Controlled sync exports/tmpfs and local overlay state establish no
NAS policy, physical durability, persistent state, firmware or old-kernel behavior.
No real SLES host, NAS administration or host mount changes are prerequisites for
this lab. The pinned userspace still shares the modern Podman/WSL2 kernel.

## Supervised mount-profile enforcement (increment 69)

[Increment 69](RUST-INCREMENT-69.md) implements explicit per-binding nfs_mount
configuration and supervised source/destination worker checks. The
[contract](NFS-MOUNT-PROFILE.md) and [extended lab](NFS-MOUNT-PROFILE-LAB.md#supervised-rust-authorization-extension)
separate live Rust refusals/replay from the earlier Python model decisions.
A local proc fingerprint is checked against the opened root fdinfo mnt_id and
rechecked after marker/custody observations. Existing private root, marker,
enrollment and inherited-lock checks remain necessary. Namespace/option changes
can intentionally refuse original-state restart. No matching pin proves mount
continuity, remote cancellation/settlement, authenticated server or durability.

The qualification feature alone permits NFS. Production NFS and source deletion
remain disabled; no new dependency/executable, daemon mount management, source
cleanup, registration or takeover is added. Local binding encodings stay unchanged.
Legacy NFS bindings without a declared profile refuse; there is no automatic
marker/pin/receipt rewrite or job-policy migration. Keep original legacy state
and binary for a separately qualified migration; do not delete state to bypass it.

Finite B/B and N/N worker cases use private root-squashed tmpfs exports and a
pinned SLES client on the modern shared kernel. Source nested-mount refusal must
withhold 202; restored original scope permits same-ID retry. Destination refusal
keeps prior valid custody 202 and requires the existing audited resume after
restoration. These cases do not qualify every phase/race, cache visibility across
producer clients, old SLES kernels, actual NAS/security/server failover or power
loss. Additional buffered synchronization/death qualification remains open.

Increment 69's retained broad run remains FAILED at an obsolete production-startup
outage assertion despite its individually passed 6/12/184 transfer/state scopes.
The new early production refusal is expected. A separate qualification-binary
startup-only run passes the corrected blocked-child/status/stop/restoration case;
its other scopes are explicitly NOT_RUN. Initial cleanup EBUSY required a later
normal unmount and exact-resource teardown, preserved separately. Neither failed
run is promoted to passing overall evidence. The live authorization run passes
all four B/B/N/N cases with normal cleanup; two earlier fixture setup attempts and
their exact sources are retained as failed findings.

## Buffered copy and verification read qualification

[Increment 71](RUST-INCREMENT-71.md) and its [lab](NFS-BUFFERED-READS-LAB.md)
separate actual blocked read(2)/descriptor observations from cache advice and
metadata stalls. Same-share and distinct-export cases use one controlled server
with a joint outage, local state and ordinary UID-1000 workers; the isolated root
observer alone has SYS_PTRACE/DAC_READ_SEARCH for /proc inspection. No host ptrace policy or
production privilege is changed. Source hashes must be captured before advice;
reading the target after eviction would invalidate the fixture.

Coordinator death and local exclusion do not establish remote settlement. Wait
for actual old-worker exit after restoration, preserve original state/custody
and validate owned bytes/allocations. Interrupted copies use attempt 2 with old
partials retained; verification retains attempt 1. Independent NAS failures, other-client cache visibility,
exact/withheld RPC replies, NAS/server reboot/failover or explicit grace/reclaim, persistent media/power, old
kernels, all cache/size/duration/load combinations and remaining worker phases
stay unqualified. Production NFS/deletion stay disabled; FR-03/05 remain open.

Increment 71 observes sixteen contended raw-flock orphan samples across its eight
passing cases; zero cases exhibit early raw-guard closure. The buffered evidence
therefore establishes held-guard exclusion. Earlier closed-guard regression
evidence remains separate; do not infer that specific buffered branch or remote
settlement from these samples.

## Buffered source-claim interruption evidence

[Increment 74](RUST-INCREMENT-74.md) and [the claim lab](NFS-BUFFERED-CLAIM-LAB.md)
cover eight buffered same/separate-share debug/release claim interruptions before
202. Actual D-state linkat/unlinkat numbers, directory descriptors and flags
identify pending client operations; this does not prove server completion with
a reply withheld or pending fsync/COMMIT. The recorder keeps files/parents
unchanged until confirmed 202; retryable 503 leaves paths unreleased. Original
state and source inode survive recovery to custody/202, delivery and committed
replay. Namespace removal during claiming is distinct from disabled post-delivery
source cleanup. One modern shared-kernel client/server, joint outage and volatile
tmpfs establish no physical NAS/power persistence, independent cache/failure,
old-kernel, scale/endurance or universal timing guarantee. Contender probes precede
worker SIGKILL; afterwards actual exit is confirmed, adding no terminating/free-
raw-guard contender scope. Full FR-03/05 and production NFS/deletion stay gated.

## Buffered enrolled/populated bootstrap evidence

[Increment 75](RUST-INCREMENT-75.md) and [the bootstrap lab](NFS-BUFFERED-BOOTSTRAP-LAB.md)
cover eight aged-buffered enrolled-empty/populated startup cases on both share
layouts and profiles. Actual D state, pending syscall and NFS/RPC stack or wait
channel evidence distinguish blocked bootstrap from a userspace pause. Starting
and a connected unanswered health request must not become a false-ready reply.
Original database/WAL/configuration, source/enrollment/bindings and partials are
compared while closed before recovery; these are not live backup instructions.
Populated recovery preserves its old partial and finishes attempt 2; enrolled-empty
finishes its first job on attempt 1. Original source inode and producer-reused
bytes survive. The existing bootstrap budget may request termination while a
worker stays blocked; no explicit stop/deadline matrix or runtime timeout change
is added. Probe contenders before SIGKILL, then confirm actual old-thread exit.

These cache-aged source-bootstrap cases do not qualify every warm-cache, fresh-
enrollment or later destination phase, terminating/free-guard contender interval,
server-completed RPC/reply loss, pending sync/COMMIT, reboot/failover, independent
NAS/cache, disk/power durability, old SLES kernel or production-scale workload.
Readiness still describes the control plane, not destination health. The fixture
uses one shared modern kernel/server, joint outage and volatile tmpfs. All full
release gates stay open; production NFS and source deletion remain disabled.

[Increment 76](RUST-INCREMENT-76.md) and the
[buffered synchronization lab](NFS-BUFFERED-SYNC-LAB.md) observe eight healthy
NMP-41B claim/delivery workers and conditional native capability controls. Actual
client/observer/relay clock identity precedes correlation; full mount-ID counts
include exact roots excluded by the helper descendant convenience list. Raw
payloads, unknown compounds and capture limits remain explicit. Timing overlap
is correlation, not unique causal attribution; ptrace changes scheduling. Native
withholding is not service fault/recovery evidence and no unobserved COMMIT is
assumed. One modern shared kernel, one client/server, logical exports and volatile
tmpfs do not qualify actual NAS failover, SLES kernel or disk/power durability.
Production NFS/deletion remain disabled; all eight release gates remain open.

Actual increment-76 results: all 112 service NFS syncs return zero, with no captured
call/reply inside or captured pair spanning entry. Broader windows contain WRITE/
COMMIT and undecoded compounds; this is not universal RPC absence. Native WRITE
is observed on both layouts, but the service-matching intersection is empty, so
zero new withholding/service fault cases run. Initial separate-share native
capture watched an idle destination relay; corrected discovery captures both,
observing actual source-relay traffic. Preserve the rejected-scope initial report
and do not infer a transport from a mount address.

[Increment 77](RUST-INCREMENT-77.md) and the [I/O lab](NFS-BUFFERED-IO-LAB.md)
add bounded external open/read/write/close/stat/chmod/sync observations. Local
proc descriptor snapshots and worker-memory reads avoid target observation I/O;
ptrace still changes scheduling and permits independent kernel writeback. NFS
fsid/fileid and byte/range matching are fixture-local identity correlations,
not authenticated NAS authority or unique causal proof. Correct SAVEFH/RESTOREFH
state is necessary; the initial conflicting-identity failure remains preserved.
Unknown attributes, unmatched operations, pre-checkpoint I/O and unsupported
vectored cases are not promoted to supported fault boundaries. No reply loss,
death, production NFS/deletion, old kernel or physical durability is qualified.

Actual increment-77 evidence matches twenty delivery requests to payload/manifest
fchmod before fsync, with twelve WRITE ranges matching earlier completed writes.
The first 1 MiB predates attachment; claim-window WRITE/COMMIT remains unattributed
to the selected claim worker. All 112 syncs return zero without captured traffic
inside them. This selects a COMMIT candidate, not tested reply-withholding or
fault recovery. Fixture preparation precedes the checkpoint; pending producer/
source synchronization remains unqualified. Server FILE_SYNC/COMMIT success on
volatile tmpfs does not establish physical-media/power durability.

## Buffered payload-fchmod COMMIT reply-loss qualification

[Increment 78](RUST-INCREMENT-78.md) and [the complete procedure](NFS-BUFFERED-COMMIT-LAB.md)
retain six native controls and eight selected mover cases. Actual fchmod syscall
91/0400/target FD remains D-state while a matching server-success COMMIT reply is
held before forwarding; server-local inode/size/hash and successful UNSTABLE
ranges with the same handle/verifier corroborate the controlled boundary. Native
reply drops include explicit connection interruption and exact session replay.
Four service cases delay/release the reply with a live coordinator. Four combine
coordinator death, independently observed orphan local-guard retention, worker
kill and reply drop; actual exit precedes preserved-state restart/attempt 2.
Original source/database/enrollment/partial and newer producer bytes survive.

No live-COMMIT-loss-without-death or UNSTABLE-WRITE-loss case is inferred. Native
ptrace discovery and service pending-proc snapshots have different scopes;
protocol/FD/server correlations are not unique kernel causality or authenticated
global NAS identity. Both exports share one server and volatile tmpfs on modern
WSL2 kernel 6.18.33.2 with pinned SLES/glibc 2.22 userspace. Neither server COMMIT
success nor client fsync/hash proves physical power durability, original SLES
kernel/maintenance-package behavior, independent NAS failover or NetApp/Isilon
interoperability. Larger files/load/endurance, other phases/ranges/outages and
delayed effects remain open. Local exit/guard availability alone is not remote
settlement. Production NFS/deletion remain disabled; all eight release gates remain open.

## Buffered UNSTABLE WRITE reply-loss qualification

[Increment 79](RUST-INCREMENT-79.md) and the
[complete procedure](NFS-BUFFERED-UNSTABLE-LAB.md) retain six native controls and
eight mover cases. All three full-count WRITE requests/replies are decoded
stable=0/committed=0 and held before forwarding. Actual fchmod syscall 91, mode
0400, target FD/D state, matching controlled server inode and full payload hash
corroborate the boundary. Native drop includes explicit connection interruption:
every range receives uncached-reply error, is resent UNSTABLE and gets matching
later successful COMMIT. The highest-slot hint changes for two retries on each
layout; initial over-strict validation remains a separately retained failure,
with no service cases run before its correction and full rerun.

Four mover cases release replies with a live coordinator; four combine coordinator
death, original orphan-guard retention, worker kill and reply drop. Actual exit
precedes original-state restart/attempt 2, preserving the first partial, original
source/database/enrollment, newer producer bytes and validated manifest. This does
not qualify live loss without death, different sizes/cache/load/phases, server
restart/changed verifier or general delayed effects. Stronger-resend regression
models are not claimed as observed native behavior.

Host kernel NFS performs the I/O; relays only inject controlled faults. One
controlled server with two volatile tmpfs exports on modern WSL2 6.18.33.2 is not
independent NAS failure domains or original SLES kernel/maintenance packages.
Pinned SLES/glibc 2.22 ABI tests do not close those gaps. UNSTABLE success is not
durable persistence, and COMMIT on tmpfs is not power-loss proof. Controlled
protocol/FD/server correlations are not unique kernel causality or authenticated
NAS identity; local worker exit/guard availability is not remote settlement.
Production NFS/deletion stay disabled and all eight release gates remain open.

## Live-coordinator payload reply loss

[Increment 80](RUST-INCREMENT-80.md)/SC-114 adds twelve native controls and
eight live-coordinator payload reply-loss cases: COMMIT/UNSTABLE WRITE across
both buffered share layouts and debug/release profiles. The same coordinator
remains responsive, same-ID replay stays 202, and each case commits attempt 1
without replacement, restart, review or manual state changes. The
[step-by-step procedure](NFS-BUFFERED-LIVE-LOSS-LAB.md) accounts separately for
payload retransmissions and later other-handle traffic, retaining all raw bytes.
This supplies selected FR-03/05 evidence; all eight release gates remain open.
Production NFS/source deletion, retry/review policy and deadlines stay unchanged.
Longer losses, other phases, reboot/verifier changes and deployment/NAS/kernel/
physical-durability qualification remain open.

The preliminary COMMIT acquisition is retained separately with its exact sources;
the complete matrix is repeated after adding explicit original-handle versus
other-handle accounting. Only the final two common-source matrices support this
increment's acceptance. No unrelated manifest traffic is discarded from raw
reports. The handle selector never filters same-handle ranges/bytes/stability or
retry identity; missing or mismatched payload evidence still fails validation.

Reply drop deliberately interrupts the connection. The actual pending call is
payload fchmod (syscall 91/mode 0400), not an assumed fsync call. Shared clock,
server-local inode/hash and protocol correlations are controlled evidence, not
unique kernel causality, authenticated NAS identity or physical-media proof.
These SLES/glibc 2.22 userspace tests share the modern WSL2 kernel and volatile
NFSD tmpfs. They do not qualify the original SLES kernel/maintenance patches,
independent NetApp/Isilon failures, server reboot/verifier change, power loss,
all sizes/cache/load, longer delays, replacement scheduling or unobserved source
sync/pre-checkpoint phases. Local exit or guard availability is not remote
settlement. Producer/consumer behavior and all deferred capabilities stay unchanged.

Increment 80's actual post-drop status is already Committed in the first sample
for all eight cases. Health/status also pass at the proven held-reply/D-worker
boundary. These are discrete responsiveness observations, not continuous API
availability measurements across reconnection or exact recovery-time bounds.

## Manifest-specific withholding capability

[Increment 81](RUST-INCREMENT-81.md)/SC-115 establishes actual manifest-side
successful-reply withholding: four healthy worker traces, then four hold/release
controls across both buffered layouts/profiles. The
[step-by-step lab](NFS-MANIFEST-CAPABILITY-LAB.md) separates actual manifest
WRITE stability and pending permission change from earlier payload COMMIT/
UNSTABLE evidence. Complete private bytes do not imply public commitment.
All cases preserve original source/state/enrollment and commit attempt 1 after
release. Selected reply loss, replay and coordinator-death recovery are covered
separately by increment 82; all eight release gates and production NFS/deletion remain
unchanged. Maintain DOC-01–05; DOC-06 stays deferred.

The existing publish checkpoint starts observation after payload verification;
pre-checkpoint/source synchronization remains outside capture. Healthy discovery
uses ptrace and actual common time namespaces; it changes scheduling. Holding
controls use local proc plus server-local inspection, with UID/GID-1000 movers/
workers/relays, no capabilities and NoNewPrivs. Extra privileges belong only to
owned fixture setup/observation. Original manifest bytes/inode are followed from
private staging to public publication; mount-address inference and plain timing
are insufficient proof. Full raw/unknown traffic is retained.

The increment 81 acquisition tests successful reply release. Increment 82
separately qualifies selected live/death drops; server reset, changed verifier
and general worker-replacement/remote-settlement safety remain unqualified. Health/status
checks while held are discrete observations, not continuous availability or a
recovery-time bound. FILE_SYNC protocol success on volatile NFSD tmpfs is not
physical-media/power-loss proof, old SLES kernel/maintenance-package behavior,
independent NAS failure or NetApp/Isilon interoperability. Pinned SLES/glibc 2.22
userspace shares modern WSL2; local exit/guard availability is not NAS settlement.
All remaining ranges/sizes/cache/load, synchronization/deployment and release
obligations stay open. The native C fixture probe is unused in this increment;
no shipping executable, Rust crate, API, retry/review or deadline changes.

## Manifest reply-loss and immutable-intent recovery


[Increment 82](RUST-INCREMENT-82.md)/SC-116 qualifies eight finite manifest WRITE
reply-loss recoveries after eight repeated discovery/release controls, across both
buffered NMP-41B layouts and debug/release profiles. Live-coordinator replay and
post-death application recovery from immutable SQLite intent are checked
separately. The latter confirms coordinator exit, orphan guard retention, actual
old-worker exit before restart, original staging inode/bytes before republication
and phase-1 to phase-4 durable intent preservation. All cases commit with payload
attempt 1 and preserve source/state/enrollment and producer-path reuse.
Read [the complete loss/recovery procedure](NFS-MANIFEST-LOSS-LAB.md) and retained
raw/audit evidence. This supplies selected FR-03/05 evidence; all eight release
gates stay open. Production NFS/source deletion, Rust inputs/dependencies,
retry/review and deadlines stay unchanged. Other workload/phases, server/verifier
recovery, delayed-effect settlement, NAS/kernel/power and deployment qualification
remain open. Maintain DOC-01–05; DOC-06 stays deferred.

The post-restart observation window and original handle/range/bytes prove a
successful write during original-state recovery; timing alone does not uniquely
attribute every kernel request to a new process or prove native session replay.
A cached/session replay or uncached-retry response is checked separately in live
cases. The old worker's local exit and free guard do not establish NAS settlement.
Exact DB/WAL copies are acquired only after confirmed coordinator exit; read-only
queries operate on disposable copies with hash/quick_check checks. This verifies
saved intent consistency in the controlled crash, not every SQLite/storage/power
failure or a new supported offline repair workflow. Restart reuses the recorded
manifest allocation; already published payload attempt 1 is distinct from repeated
manifest writes. The fixture uses one modern shared kernel and volatile exports.
Discrete health/status/replay samples do not prove continuous availability or
exact reconnection latency. No physical media, independent NASes, original SLES
kernel/maintenance packages, endurance or all manifest sizes/cache/load are covered.


[Increment 83](RUST-INCREMENT-83.md)/SC-117 adds buffered actual source-claim LINK
and REMOVE successful-reply hold/release controls, with the
[step-by-step procedure](NFS-CLAIM-CAPABILITY-LAB.md). Server-side namespace
completion does not authorize recorder path reuse before confirmed 202. Keep
selected capability/release evidence separate from increment 84's selected
reply-discard/replay/death evidence. Production NFS/source deletion stay off;
Rust behavior/dependencies and retry/review/deadline policy remain unchanged.
All eight release gates and DOC-01/02/04/05 completion remain open; maintain
DOC-03 and defer DOC-06.

These claim controls sample the pending syscall and directory descriptors and
trace full wire compounds; they do not capture every syscall entry/exit or
uniquely map every unrelated session request to a process. Independent server
aliases and matched status-zero replies establish the selected namespace effect,
not later directory-sync acknowledgement or physical durability. A producer
path absent after server REMOVE is still unavailable for reuse until 202.
No discarded reply, reconnection, native replay, crash recovery or server restart
is inferred from releasing the saved success. Keep pending source synchronization
and delayed-effect reconciliation as separate qualification obligations.


[Increment 84](RUST-INCREMENT-84.md)/SC-118 qualifies sixteen finite buffered
source-claim LINK/REMOVE reply-loss recoveries after eight repeated release
controls across both share layouts and build profiles. Live cases prove successful
cached namespace session replay with full raw request-byte checks and the same
coordinator. Death cases prove orphan exclusion, actual exit and unchanged server
aliases before original-state restart. Every case commits attempt 1 while
preserving source/state/enrollment and newer producer bytes. The
[step-by-step lab](NFS-CLAIM-LOSS-LAB.md) documents infrastructure, proof, cleanup
and limits. Rust/dependencies, retry/review/deadlines and production NFS/deletion
stay unchanged. All eight release gates remain open; maintain DOC-01–05 and
defer DOC-06. Server recovery, delayed effects, pending source synchronization,
other workloads and NAS/kernel/power/deployment qualification remain future work.


[Increment 85](RUST-INCREMENT-85.md)/SC-119 isolates source synchronization:
four actual buffered claim workers pass 32 source fsync calls, with no captured
request/reply inside those intervals or captured pair spanning entry. Separate
source-export native probes prove FILE_SYNC WRITE success withholding, release
and drop/reconnect recovery on both share layouts. The actual-service/native
operation intersection is empty, so zero mover source-sync reply-loss/death
cases are qualified. Read the [step-by-step lab](NFS-SOURCE-SYNC-LAB.md) and raw
scope/limitations; broader-window traffic is not source-sync attribution.
Server recovery/delayed settlement and other workloads remain open. Production
NFS/source deletion, Rust behavior/dependencies, retry/review and deadlines stay
unchanged. Maintain DOC-01–05 and defer DOC-06; all eight release gates stay open.


[Increment 86](RUST-INCREMENT-86.md)/SC-120 establishes native server-recovery
fixture capability after two retained failed acquisitions. Four original-FD
probes pass NFSD stop/start and confirmed same-container SIGKILL/exit/start on
source/destination exports, preserving opaque handles/backing inodes while
observing BADSESSION, new sessions and changed write verifiers. Network namespace
and VM kernel boot ID remain unchanged; this is not VM/NAS reboot or Rust mover
recovery qualification. The [step-by-step lab](NFS-SERVER-RECOVERY-LAB.md)
records pinned private IP, actual exit, live trace checkpoints, WSL clocks,
raw proof, rescue/normal cleanup and limits. Both SLES gates and independent
36-control proof audit pass. Production NFS/source deletion and runtime policy
remain unchanged; maintain DOC-01–05, defer DOC-06 and keep all eight gates open.


[Increment 87](RUST-INCREMENT-87.md)/SC-121 qualifies four actual live-coordinator
source-copy recoveries after four native controls: debug/release with NFSD restart
or NFSD quiescence followed by same-container SIGKILL/confirmed exit/start.
Each retains the original worker/attempt 1, custody/local state, staging inode,
payload/manifest integrity and clean-restart committed replay. Two mounts/export
paths share one client NFS filesystem and backing volume; distinct client
filesystems/independent shares remain unqualified. Repeated abrupt termination
controls failed and are retained with rescue evidence; the final controlled
sequence does not qualify abrupt failure, other phases, NAS or power loss.
Read the [complete lab](NFS-SERVER-MOVER-LAB.md), raw/input evidence and rejected
audit assumption. Both SLES gates, 50 proof controls and final inventory pass.
Rust/dependencies, retry/review/deadlines, production NFS/source deletion and
all eight release gates remain unchanged. Maintain DOC-01–05; defer DOC-06.


[Increment 88](RUST-INCREMENT-88.md)/SC-122 extends the controlled source-copy
recovery matrix to two genuinely distinct client NFS filesystems, backed by two
bounded tmpfs superblocks held by a separate storage container. Four native
controls precede four debug/release actual mover cases. Original-worker attempt-1
completion, staging inode, private source, local state/enrollment and committed
replay are preserved. The [step-by-step lab](NFS-DISTINCT-RECOVERY-LAB.md) documents
volume bounds, keeper/backend/reader/client identity checks, initial OCI setup
failure, normal cleanup and independent audit. This adds selected cross-filesystem
copy evidence; it does not qualify independent NAS, persistent disks, abrupt live
server termination, power loss, other phases or worker replacement. Both SLES
gates remain mandatory; production NFS/source deletion and all eight release
gates stay unchanged. Maintain DOC-01-05 and defer DOC-06.


[Increment 89](RUST-INCREMENT-89.md)/SC-123 extends the retained two-filesystem
fixture to live destination-staging verification across controlled NFS server
restart. Four native prerequisites precede four debug/release mover cases using
NFSD restart or NFSD-quiesced same-container termination/start. The
[complete lab](NFS-VERIFICATION-RECOVERY-LAB.md) distinguishes durable Copied
status and a full staging file from completed verification: require actual
D-state staging read/FD/offset proof, unchanged staging/source/state and no final
payload or manifest during the outage, then original-worker attempt-1 commitment
and original-state replay. I/O tracing checks full reread through EOF and later
publication; it starts after earlier copy synchronization. READ RPC compounds
remain unknown in the retained decoder, so this is not READ session-replay proof.
Keep retained-memory/modern-kernel, independent NAS/power and other-phase limits
explicit. Maintain DOC-01-05 and defer DOC-06; runtime policy, production NFS/source
deletion and all eight release gates remain unchanged.

The release container-restart case in increment 89 continues across an observed
backend network-namespace change while keeper/storage and VM boot identity remain
stable. This selected actual continuation does not close broader namespace,
lease/reclaim, VM/NAS reboot or physical-durability qualification.


[Increment 90](RUST-INCREMENT-90.md)/SC-124 tests controlled server recovery at
payload publication's two-name staging-removal boundary. Four native controls
precede four debug/release live-worker cases on the retained two-filesystem
fixture. The [complete lab](NFS-PUBLICATION-RECOVERY-LAB.md) requires complete
same-inode staging/final aliases with two links, PublishIntent and no manifest,
actual pending unlinkat on the staging directory, unchanged custody/state/ownership,
then original-call removal, one-link original final inode, later manifest and
attempt-1 committed replay. Staging removal is not postcommit source cleanup.
The initial final LINK/file/new-parent sync precede tracing; initial LINK and other
sync/manifest/death boundaries remain separate. Retained memory, controlled NFSD
quiescence and modern-kernel evidence do not establish NAS/power durability or a
full lease/reclaim matrix. Maintain DOC-01-05, defer DOC-06 and keep runtime policy,
production NFS/source deletion and all eight release gates unchanged.


[Increment 91](RUST-INCREMENT-91.md)/SC-125 extends the same finite controlled
server-recovery matrix to manifest staging-name removal. The
[step-by-step lab](NFS-MANIFEST-RECOVERY-LAB.md) requires an already Published
one-link verified payload with no payload staging, manifest_phase 3, and complete
same-inode manifest aliases with two links. Actual D-state unlinkat named
COMMITTED.part, unchanged source/payload/manifest/state/ownership and correlated
successful raw REMOVE precede original-worker attempt-1 commitment. The original
manifest inode/hash survives with one link after the remaining syncs. Clean
original-state replay preserves recorder reuse. A valid COMMITTED.json remains
the consumer signal; this boundary precedes the local Committed receipt and adds
no consumer API-polling or recorder monitoring duty. Initial manifest LINK/file/
new-parent sync precede tracing. Other sync/death/reconciliation boundaries,
retained-memory versus physical durability, controlled quiescence, independent
NAS/power and modern-kernel limits remain explicit. Maintain DOC-01-05 and defer
DOC-06; production NFS/source deletion and all eight release gates stay unchanged.


[Increment 92](RUST-INCREMENT-92.md)/SC-126 extends controlled server-recovery
qualification to the initial payload LINK at file_link_rpc. The
[step-by-step lab](NFS-PAYLOAD-LINK-RECOVERY-LAB.md) starts with verified one-link
staging, PublishIntent and absent final payload/manifest. Require actual D-state
linkat with both directory FD/path/mount/inode observations, successful raw LINK
inside its original pending interval, final-file/new-parent sync before staging
removal and later manifest publication. The original staging inode/hash becomes
the one-link final payload; original-worker attempt-1 commitment and clean
original-state replay preserve recorder reuse and private source/state/enrollment.
The recorder and valid-manifest consumer contracts stay unchanged. Earlier
copy/verification/original-file sync precede tracing; remaining initial manifest
LINK, other sync/death/reconciliation, NAS/power, full session/reclaim and modern-
kernel limits remain explicit. Maintain DOC-01-05 and defer DOC-06; production
NFS/source deletion and all eight release gates stay unchanged.


[Increment 93](RUST-INCREMENT-93.md)/SC-127 extends controlled server-recovery
qualification to initial manifest LINK at manifest_link_rpc. The
[step-by-step lab](NFS-MANIFEST-LINK-RECOVERY-LAB.md) starts with payload
Published, manifest_phase 3, complete one-link manifest staging, absent final
manifest and unchanged one-link verified payload with no payload staging.
Require actual D-state linkat with both directory FD/path/mount/inode observations,
successful raw LINK named COMMITTED.json inside its original pending interval,
manifest-file/new-parent sync before staging removal and remaining successful
syncs before the local receipt. Original manifest inode/hash, payload, source,
state/epoch and attempt-1 committed replay preserve recorder reuse. Producer and
valid-manifest consumer duties stay unchanged. Earlier payload effects/manifest
write/original-file sync precede tracing; remaining sync/death/reconciliation,
retained-memory versus physical NAS/power durability, full session/reclaim and
modern-kernel limits remain explicit. Maintain DOC-01-05 and defer DOC-06;
production NFS/source deletion and all eight release gates stay unchanged.


[Increment 94](RUST-INCREMENT-94.md)/SC-128 establishes exact publication file-
fsync capability before selecting more sync recovery. The
[step-by-step lab](NFS-PUBLICATION-SYNC-DISCOVERY-LAB.md) repeats native controls
and eight actual debug/release payload/manifest healthy/stopped-NFSD observations.
An external exact-path observer holds at entry/exit without changing shipping
Rust or substituting syscalls; artificial ptrace stops are excluded from syscall/
RPC timing and are not D-state. Require complete aliases/source/payload, original
state/epoch/guard, actual outcome before/after restoration, attempt-1 commitment
and clean committed replay. Independently decode raw interval traffic and captured
pairs spanning entry, keeping broader/unknown activity separate. Successful local
completion while NFSD is stopped supplies no blocked-sync recovery qualification;
native dirty-write recovery cannot substitute for actual service evidence.
Producer/consumer duties, runtime policy and deadlines remain unchanged. Maintain
DOC-01-05, defer DOC-06, keep production NFS/private-source deletion disabled and
all eight release gates open. Other sync/directory/workload/cache, death/recovery,
physical NAS/power and old-kernel profiles remain separate.

[Increment 95](RUST-INCREMENT-95.md)/SC-129 adds four selected debug/release
payload-LINK coordinator-death recoveries across NFSD/quiesced-container restart,
after four native prerequisites. Actual pending linkat and old-worker D-state
are distinguished from artificial pauses and successful syscall returns. Logical
ownership refuses all three contenders through actual old-worker exit; physical
flock closure is recorded separately. After restoration, independent read-only
namespace/custody observations precede original-state attempt-1 commitment and
replay preserving producer reuse. No arbitrary uncertain-effect redispatch or
remote-settlement proof follows from local exit. See the
[step-by-step lab](NFS-PAYLOAD-LINK-DEATH-RECOVERY-LAB.md) and exact raw/audit
results. Both SLES gates and normal cleanup pass. Other phases, actual blocked
syncs, NAS/persistent-storage/power and old-kernel behavior remain unqualified;
production NFS/private-source deletion stay off and all eight release gates open.

[Increment 96](RUST-INCREMENT-96.md)/SC-130 adds four selected manifest-LINK
coordinator-death recoveries across NFSD/quiesced-container restart after four
native prerequisites. Require actual D-state linkat, old-group exclusion and all
three contender modes refused until actual worker exit. Independent read-only
backing observations retain original manifest/payload/source custody; exact raw
SQLite/WAL copies prove phase 3 remains pending after old-worker exit, separately
from a visible valid completion manifest. Original-state attempt-1 commitment and
replay preserve producer reuse. Recorder/consumer duties remain unchanged. See
the [step-by-step lab](NFS-MANIFEST-LINK-DEATH-RECOVERY-LAB.md), raw/audit evidence
and both SLES gates. Normal cleanup passes. Local ownership/exit is not global
remote-settlement proof; unselected phases/syncs, NAS/power and old-kernel behavior
remain unqualified. Production NFS/private-source deletion stay off; eight release
gates remain open.

The Windows-host copied-SQLite auditor requires a writable workspace scratch
location. The first default-temp permission denial is retained in the
[initial audit evidence](RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-AUDIT-INITIAL-EVIDENCE.json).
The corrected audit reconstructs the same raw acquisition under resolved,
workspace-contained scratch paths, inherits the workspace ACL and closes SQLite
before owned scratch cleanup; it changes no global permissions or service policy.

[Increment 97](RUST-INCREMENT-97.md)/SC-131 qualifies four selected source-claim
LINK coordinator-death recoveries before HTTP 202 across NFSD/quiesced-container
restart, after four native prerequisites. Require actual D-state linkat, logical
old-worker exclusion/three contender refusals through actual exit, preserved
original/private source custody and copied SQLite/WAL proof of pending done=0
with no transfer/manifest before replacement. The original request must have no
202/path release; only confirmed identical-ID retry 202 permits producer reuse.
Original-state attempt-1 delivery and replay preserve newer producer bytes. See
the [step-by-step lab](NFS-CLAIM-LINK-DEATH-RECOVERY-LAB.md) and exact raw/audit
results. Both SLES gates and normal cleanup pass. Claim source-name removal is
separate from disabled private-source cleanup; local exit is not global remote
settlement. Unselected REMOVE/sync/termination, NAS/power and old-kernel behavior
remain open; eight release gates stay open and production NFS/deletion stay off.

[Increment 98](RUST-INCREMENT-98.md)/SC-132 qualifies four selected source-claim
REMOVE coordinator-death recoveries before HTTP 202 across NFSD/quiesced-container
restart after four native prerequisites. Require same-inode two-name custody at
entry, actual D-state unlinkat, independently decoded preceding LINK/resumed REMOVE,
logical exclusion/three contender refusals through actual exit and copied local
SQLite/WAL claim done=0/no transfer or manifest before replacement. Confirmed
identical-ID retry 202 precedes producer reuse; original-state attempt-1 commitment
and replay preserve newer bytes. See the [step-by-step lab](NFS-CLAIM-REMOVE-DEATH-RECOVERY-LAB.md),
raw/audit evidence and preserved initial pre-mount Podman connection failure.
Both SLES gates and normal cleanup pass. Observer attachment at REMOVE excludes
earlier file/new-parent syncs; this is not actual blocked-sync or NAS/power-loss
qualification. Local exit is not global remote settlement. Other sync/termination,
old-kernel/deployment and broader workloads remain open; all eight release gates
stay open and production NFS/postcommit private-source cleanup stay off.

[Increment 99](RUST-INCREMENT-99.md)/SC-133 adds eight selected source-claim
private-file/private-parent synchronization observations before HTTP 202, across
debug/release and healthy/stopped NFSD after four native prerequisites. External
actual syscall entry/exit controls exclude artificial holds; independently audit
raw interval traffic and captured pairs spanning entry, seven observed syncs per
worker, complete two-name custody/Accepted state and no producer reuse until
confirmed same-ID 202. Original-state attempt-1 delivery/replay preserves newer
bytes. See the [step-by-step lab](NFS-CLAIM-SYNC-DISCOVERY-LAB.md) and measured
raw/audit evidence. Successful local stopped-NFSD completion is discovery, not
blocked-sync, reply-withholding or physical-durability qualification. Original-file
sync before LINK and other workloads/caches/termination remain separate. Both
SLES gates and normal cleanup pass after correcting and retaining an initial
shared case-count assertion failure and rerunning the full matrix. Keep all eight release gates open and
production NFS/postcommit private-source cleanup disabled.

[Increment 100](RUST-INCREMENT-100.md)/SC-134 adds four debug/release x healthy/
stopped-NFSD original-file fsync observations before claim LINK after four native
prerequisites. Exact actual entry/exit excludes artificial holds; require complete
one-link original, private data absent, Accepted state and no premature 202.
Both stopped-NFSD calls return locally: no selected raw RPC or captured pair
spanning entry is observed. All eight syncs per worker return zero; successful
following LINK pairs calibrate capture. Same-ID 202 before reuse, attempt-1
commitment, original-state replay, both SLES gates and normal cleanup pass.
See the [step-by-step lab](NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-LAB.md), retained setup
connection failure and raw/input evidence. This does not qualify blocked-sync,
reply-loss, physical durability or broader cache/workloads. Prioritize joint-outage
replay/revalidation/admission next; require positive RPC evidence before further
sync recovery. All eight release gates stay open; production NFS/private-source
cleanup stay disabled.

[Increment 101](RUST-INCREMENT-101.md)/SC-135 adds four debug/release x source-space
admission off/on joint-outage cases after four native prerequisites. Actual
D-state destination verification and source revalidation preserve acknowledged
custody, original state and producer replacement bytes. The initial replay plus
six-request burst returns bounded retryable non-release 503s with queue refusal;
timed-out HTTP waiters do not cancel queued commands. Enabled policy permits at most one
probe; probes may already have exited. The two blocked data workers stay stable. One-job retention prevents
new durable acceptance, while original attempt-1 delivery and clean restart/replay
recover after restoration. Both SLES gates, exact-artifact/raw/corruption audits
and normal cleanup pass. See [step-by-step infrastructure](NFS-JOINT-OUTAGE-LAB.md).
This finite shared-backend test does not qualify independent outages, pre-202/
partial claims, source substitution, throughput/endurance or physical durability.
Keep all eight release gates open and production NFS/private-source cleanup off.
