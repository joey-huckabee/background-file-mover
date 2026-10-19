# First-release NFS mount profile contract

Increment 68 defines a **candidate**, not production NFS support. Production NFS
and source deletion remain disabled. The read-only Python qualification model
and container lab validate inventory decisions; service startup does not yet
enforce this contract. Existing Rust descriptor/root/enrollment guards remain in
place. Registration, cross-host takeover and automatic re-enrollment stay deferred.

## Candidate and diagnostic profiles

| Property | NMP-41B: first-release candidate | NMP-41N: retained diagnostic |
|---|---|---|
| Client | Linux x86_64 GNU/glibc 2.22, pinned SLES 12 SP5 userspace in the lab | Same |
| NFS | Explicit effective version 4.1, TCP, port 2049 | Same |
| Retry | Hard; no soft, softerr or softreval | Same |
| Client caching/writes | Attribute caching and normal buffered writes; no noac or client sync | noac with observed client sync |
| Coherence | Normal close-to-open and shared cache; lookupcache=all/default; local_lock=none | Same |
| Security | sec=sys on a trusted, access-controlled network, consistent UID/GID and private working areas | Same lab assumption |
| Connections | One connection; no unqualified multipath/cache extensions | Same |
| Server storage | Must honor stable-write/commit semantics; declared export durability still requires separate evidence | Fixture uses sync exports backed by tmpfs |
| Status | Selected target for further service qualification; no shipping authorization | Preserve earlier noac evidence; not an interchangeable shipping profile |

NMP-41B is a design choice for bounded qualification, **not a claim about the
user's NetApp/Isilon mounts**, whose actual version/options/security are unknown.
NFSv3, v4.0/v4.2, UDP, RDMA and Kerberos profiles require separate qualification;
they are not declared intrinsically unsafe. Do not change an existing host mount
to fit this document. The operator supplies its actual inventory for comparison.
The service never mounts, remounts or changes a NAS export.

Example administrator-provisioned candidate options are
`vers=4.1,proto=tcp,port=2049,hard,sec=sys,ac,async`.
This is a profile illustration, not an installation command or tuning advice.
The lab uses `timeo=10,retrans=1` for controlled observations; production timing
and rsize/wsize values must be recorded and qualified for the declared deployment.
Hard retries remain unbounded by those numbers. Keep the separate configurable
60-second shutdown/controller budget and surviving-worker exclusion.

Client `async` is distinct from server export `async`: the candidate permits
buffered client writes and does not approve a server that lies about stable
storage. Neither the pathname, IP, sec=sys nor a copied marker authenticates a NAS.
The lab proves ordinary UID/GID 1000 access with **root_squash** on its two child
exports; no_root_squash is not a deployment requirement. Permission/ACL validation
for the real account remains necessary.

## Explicit declaration and observations

The lab declaration contains `state_path` and, for source and destination,
`path`, `mountpoint`, expected `source` (server/export string), effective `addr`
and profile ID. These are **model inputs, not new service configuration keys**.
Use exact expected values; do not discover an arbitrary mount and approve it
merely by copying its identity into a new declaration. Initial operator approval
and protected enrollment remain independent prerequisites.

Read bounded `/proc/self/mountinfo` in the same mount namespace as the worker.
The model consumes at most 1 MiB, checks structure/escapes/unique mount IDs and
selects the deepest component-containing mount, refusing an ambiguous stack.
It performs no resolve/stat/open/traversal of payload paths. This avoids making
the inventory check itself depend on an NFS response. It cannot detect symlink
redirection; lexical approval is not descriptor/root approval.

Record mount ID, parent, major:minor, filesystem root, mountpoint, filesystem
type, source, VFS/superblock options and optional propagation fields. Pin the
selected records, roots and profiles for same-namespace rechecks. Include all
effective options, including negotiated sizes, retry parameters, cache settings
and client/server addresses. Option defaults absent from proc are interpreted
only where explicitly defined by the model, not as missing endpoint authority.
Unknown effective NFS superblock options refuse review. Recognized modern
`fatal_neterrors` is recorded in the fixture pin: its presence/behavior is not
SLES-kernel qualification, and hard must not be described as preventing every
possible network error return.

Pins are conservative observations, not permanent NAS identifiers. Unrelated
inventory changes outside the selected roots need not change them; a selected
record or declaration change refuses automatic continuation. **An unmount/remount
can reuse mount IDs and reproduce the entire pin**, as the initial lab run found.
A matching pin therefore cannot prove mount continuity, even within one namespace.
Descriptor/root/enrollment checks and exclusion around effects are still required.
No fixed delay, force flag or fresh database overrides a detected mismatch.

## Acceptance and refusal obligations

| ID | Required behavior | Increment 68 evidence / remaining work |
|---|---|---|
| MP-01 | Explicit per-root profile, version, transport, security and endpoint/export match | Read-only model; live B/B, N/N and mixed observations. Mixed matches are diagnostic, not shipping authorization. |
| MP-02 | Require writable hard mounts; refuse soft/fallback/coherence overrides | Live soft, ro and nocto refusals for each endpoint; other incompatible settings are synthetic inventory controls. |
| MP-03 | Missing NFS mount must not fall back to an ordinary local directory | Live missing-both and missing-destination inventories refuse. Production guard integration pending. |
| MP-04 | Disjoint approved roots on the same share or separate shares | Live same-share disjoint roots and separate tmpfs export devices match; overlap refuses. Full service buffered same/separate-share fault matrix pending. |
| MP-05 | No unexpected nested/stacked/subtree-bind mount in an approved root | Live source/destination nested tmpfs and subtree bind alias refuse. Whole-root bind aliases and concurrent mount replacement require descriptor identity/alias checks. |
| MP-06 | Database, guard/control/worker evidence and sidecars stay on protected persistent local disk | Model rejects NFS state and nested state mounts. Overlay/tmpfs accepted only as lab-local observation; persistence is never certified. Existing Rust checks remain authoritative; deployment/account qualification pending. |
| MP-07 | Recheck original selected pins, never auto-rebind after observed change | Stable pin matches; a changed effective retry option refuses. Same-options remount can reproduce the pin: matching observations do not establish continuity. |
| MP-08 | Inventory match must never imply server availability, root custody or RPC settlement | Server NFSD threads verified zero; local inventory still matches. This is deliberately a match, not readiness. |
| MP-09 | Validate real root descriptors, inode/device, filesystem, UID/mode/ACL, private directories and enrollment receipts before effects | Existing selected Rust guards; this model adds no such implementation or new evidence. Missing/inaccessible roots and symlink/alias races still need supervised service qualification. |
| MP-10 | No coordinator payload traversal; mount/root work is bounded/supervised and revalidated around effects | Intended integration contract; inventory is local-only. Snapshot-to-use races are not closed by this increment. |
| MP-11 | Reconcile uncertain owned NFS effects using original state; do not redispatch on timeout or guard release | Existing retained cases remain scoped to their actual mounts. Buffered service sync/lost-reply and server recovery remain open. |
| MP-12 | Preserve producer 202 custody, 3N copy/verification, no-clobber manifest and retained sources | Unchanged. No Rust transfer is executed by this new lab; prior evidence cannot be promoted to NMP-41B. |

For later startup integration, a profile mismatch must withhold new effects and
unproven 202; preserve original state/claims and report the reason for operator
review. A previously valid 202 remains valid for producer path reuse. A destination
outage alone need not prevent source claiming where original source authority is
established; a local inventory match alone establishes neither endpoint's authority.
Existing-job retries must not bypass profile/custody checks. Do not advertise these
new refusal decisions as current service errors before integration lands.

## Qualification order and limits

1. Integrate the profile declaration/observations into supervised Rust startup and
   effect authorization, with local-only coordinator reads and original pin checks.
   Keep the production NFS gate closed.
2. Qualify actual service bootstrap/claim/copy/verify/publication/manifest on B/B
   and disjoint same-share roots. Preserve earlier N/N evidence separately.
3. Trace actual B/B service sync RPCs. Withhold only observed operations after
   proving server completion and pending callers; absence of COMMIT is not failure
   to call fsync. Include original-state recovery, server restart/grace, delayed
   effects and declared shutdown/account/persistence boundaries before enablement.

Container userspace/ELF compatibility, modern shared-kernel behavior, server RAM
visibility, stable protocol replies and physical-media durability are separate
claims. This work proves no NetApp/Isilon firmware behavior, old SLES kernel,
authenticated NAS identity, storage failover or power-loss safety. See the
[lab procedure](NFS-MOUNT-PROFILE-LAB.md), [results](RUST-INCREMENT-68.md),
[release checklist](RUST-FIRST-RELEASE.md) and [testing limits](TESTING-LIMITATIONS.md).

## Verified references

Linux [nfs(5)](https://man7.org/linux/man-pages/man5/nfs.5.html) documents hard/soft
retries, noac's synchronous-write effect, cache and security options.
[proc_pid_mountinfo(5)](https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html)
defines the namespace-specific mount inventory fields and escaping.
[exports(5)](https://man7.org/linux/man-pages/man5/exports.5.html) distinguishes
server sync semantics and UID squashing. Consulted 2026-10-18; current manuals
are semantics references, not evidence that new options exist on an old kernel.
