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
| Local ownership guard and epoch | Selected cooperative same-host starts/workers remain excluded through observed process/thread exit, including cases where the raw lock closes before a surviving group ends. | NAS-side cancellation/settlement, cross-host fencing, intentional alternate-state launches, stale backup adoption or global cryptographic export identity. | Keep original local state, current scope checks and independent lifetime evidence. Complete remaining SH cases; do not use free lock/timer/process exit as remote-settlement authority; FR-03/05/06. |
| Systemd 252 lab | Increment 57 records selected real-manager local lifecycle, account refusal, bounded restart and recovery behavior with the mover in pinned SLES userspace. | Native SLES systemd 228, its maintenance patches, old cgroup/kernel behavior, actual host authorization/install policy or combined NFS blocking. | Retain the report, but do not substitute it for the older-manager/deployment matrix; FR-05/06. |
| Systemd 228 equivalent lab | Increment 59 passes ten selected local lifecycle records across both profiles/build modes, actual unit verification, eight armed races, independent controller checks, original-state recovery and owned-hierarchy cleanup. Mover/children/controllers retain the SLES root; the approved manager uses controller-free v1 cgroups. | Exact SLES-maintained RPM revision: the manager is a pinned Leap 42.3 equivalent. It also does not test an old SLES kernel, resource-controller policy or combined hard-NFS/systemd. A candidate key list alone does not prove lifecycle. | Keep 58's BLOCKED/NOT_RUN history and 59's failed-attempt evidence. Verify the declared package/deployment profile before claiming native SLES-manager support; FR-05/06. |
| Systemd 228 / actual hard-NFS mid-copy | Increment 60 passes four managed stop/death records in debug/release with distinct controlled NFSv4.1 exports/local state, actual D workers, old-thread/epoch observations and original-state recovery. | Every operation/endpoint/deadline branch, exact RPC settlement, independent NAS failures, persistent disk/power durability, exact vendor/kernel policy, full account/install or production-scale behavior. Prompt exit is distinct from a retained uncancellable worker. | Read actual per-case outcomes and lab section 12. Finish remaining SH/FR-03/05/06 obligations; production NFS and deletion remain disabled. |
| Systemd 228 / restart after incomplete stop | Increment 61 passes debug/release with three explicit starts each, 91.953/92.062-second outages after incomplete stop, 25.547/25.328-second quiet windows, preserved old epoch/D threads, 24 direct competitor refusals and original-state recovery. | Managed starts fail at the occupied listener before the guard; separate alternate-port/effect commands test the guard. No rate-limit saturation or automatic replacement is observed. This does not qualify other listener configurations, phases, endurance, every interleaving or remote settlement. | After storage restoration and confirmed old exit, all snapshots remain NoActiveOwner over 12.344/12.672 seconds; explicit reset/start recovers. Shipping restart/account/persistence and remaining SH/FR-03/05/06 stay open. See lab section 13. |
| Destination-only outage before startup / early delivery | Increment 62 passes eight empty/populated debug/release death/stop records: source startup, health 200/Running and confirmed custody/replay 202 succeed while a real destination delivery worker is D. Four blocked orphans retain ownership and refuse twelve competing commands; original database/source/receipt/binding/partial survive recovery. | Destination-blocked source bootstrap, every later phase, uncancellable/default-60 deadline, arbitrary interleavings, physical NAS or RPC settlement. All four short stops exit promptly; no surviving terminating orphan is observed. Live SQLite/WAL hashes are diagnostic and not atomic backups. | See SC-096 and the dedicated destination-startup lab. Preserve control readiness versus destination health/commitment distinctions, original state and actual old-thread exit. Remaining SH/FR-03/05/06 and production NFS/deletion gates stay open. |
| Process death versus machine/storage loss | SIGKILL/restart exercises selected application crash boundaries while the kernel/storage stay up. | Power loss, torn media writes, reboot persistence, volatile NAS/controller-cache behavior, disk/controller failure or a server's truthfulness about durable acknowledgements. | Qualify declared durability assumptions and storage/reboot/upgrade behavior in a controlled equivalent environment. Do not promise hardware-failure durability from process-crash tests; FR-03/05/06/08. |
| Capacity/admission tests | Selected bounded fill/restoration, unchanged-policy refusal/retry and existing-job recovery are exercised; sampling is configurable and off by default. | Physical reservation, quotas/inodes, all external-writer races, sparse/deduplicated/compressed accounting, arbitrary concurrent load or all destination-shortage conditions. | Complete remaining FR-02 cases and profile-specific margins; preserve existing-job retries. Retained logical bytes and filesystem available capacity answer different questions. |
| Timing and races | A finite bounded observation can demonstrate the measured deadline/refusal and stable ownership at its sample points. Armed starts exercise selected competing launches. | Fairness, all scheduling interleavings, zero arbitrarily short overlap between samples, universal cancellation bounds or progress under every kernel/server stall. | Report loaded budget, timestamps, actual outcomes and observation limits. A timeout is not cancellation; uncertainty must still prevent conflicting effects; FR-03/05. |
| Workload size and endurance | Finite fixture payloads, queues and capacity cases exercise their recorded sizes and durations. The lifecycle lab uses a nested 2 MiB plus 17 byte input. | Sustained roughly 100 GB recordings, a production backlog, multi-day memory/descriptor/retention behavior, NAS throughput/latency or recovery time at production scale. Small-file correctness is not a performance or endurance qualification. | Declare representative size/concurrency/retention targets and run bounded scale/endurance cases on suitable equivalent infrastructure before promising production capacity or timing; FR-02/05/06/08. |
| Account and remote security | Local identity/mode/capability checks and selected refusals exercise the stated trusted local profile. | Actual administrator system-service authorization, full sandbox correctness, TLS/proxy/caller binding, certificate lifecycle, remote adversarial exposure or registration. User= does not authorize systemctl. | Implement/qualify the remote contract and approved deployment policy before remote use; registration remains deferred; FR-01/06/08. |
| Packaging and release evidence | Pinned inputs, crate checksums, ELF/source/driver/artifact hashes and exact local test execution can be audited. | A finished offline/reproducible shipping bundle, all notices, upgrade/rollback safety, remote CI success or release readiness merely from the local counts. | Finish FR-06/07/08, the declared release-candidate matrix and producer/consumer/operator walkthroughs. No completion percentage follows from increment/test counts. |

## Important distinctions

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
