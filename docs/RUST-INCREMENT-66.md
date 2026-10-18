# Rust increment 66: source-claim LINK and REMOVE reply loss

## Scope fixed before worker execution

Keep production NFS and source deletion disabled. Extend the retained relay
fixture to the source endpoint. All source mounts, including the base fixture
export, must use the proxy from the first mount; no direct source connection
may exist first and bypass interception. Destination stays independently usable.
Local SQLite/state and the existing ownership protocol remain unchanged.

Before any claim loss case, independently execute four non-Rust controls:
LINK and REMOVE, each with release and discard-plus-connection-interruption.
Require matched RPC/COMPOUND/operation success withheld, actual client D state,
and independent server-local namespace/inode/content evidence at the same time.
LINK creates the second owned alias; REMOVE leaves only the private alias.
Release must complete; discard must produce observed successful native replay
on a new connection with unchanged SEQUENCE/filehandle/name request identity.
Repeat these controls inside the worker fixture before fault cases.

Add two qualification-only pause selections immediately before claim linkat
and unlinkat in the existing relocation hooks. Four cases: debug/release times
claim LINK/REMOVE. Require native syscall 265/263, the correct source/private
parent descriptors and successful server completion while replies are held.
Both servers must remain healthy. Initial submission and identical-ID retry
must not acknowledge unconfirmed custody: expect retryable 503 with
source_paths_released false, an Accepted job and no destination allocation.
Keep the producer's original paths untouched until confirmed 202.
Claim REMOVE removes the original binding after the private alias exists;
the claimed payload remains retained through delivery and commitment. Postcommit
source cleanup stays disabled.

Kill only the coordinator; distinguish prompt exit from surviving workers and
require exclusion through actual old-thread exit. Discard held successes and
interrupt their connections before original-state recovery. Require the same
job/claim inode, local database/enrollment and attempt one, then 202 for the
same submission ID. Only then reuse the producer path and prove normal delivery
and manifest commitment preserve the original claimed contents.

## Limits

Selected NFSv4.1 cases use one nested file of 2 MiB plus 17 bytes, two controlled
tmpfs-backed server containers and a modern shared VM kernel. This does not
qualify physical NAS or persistent-media/power durability, server reboot/reclaim,
old kernels, separate producer-client cache visibility, COMMIT/fsync reply loss,
arbitrary healthy-stream silent loss,
concurrent load or every claim/mount/export/security boundary. There is one
controlled NFS client; producer writes and mover reads share it. A free local
guard is not general remote-settlement evidence. Explicit connection interruption
is a fixture intervention, not a production recovery command or universal
SIGKILL/shutdown bound. Existing retry/review and shutdown deadlines stay intact.
The existing submission deadline is ten seconds; the fixture allows fifteen
seconds including Podman overhead for a pending same-ID retry to return 503,
while health/job/status observations keep their existing five-second bounds.

## Results

Independent source capability `reply-capability-20261018T221446Z-6be218f4` passes all four LINK/REMOVE release/discard controls without Rust execution or cleanup errors; see [raw proof](RUST-NFS-SOURCE-REPLY-CAPABILITY-EVIDENCE.json). Offline raw RPC decoding confirms connection/XID, operation status, payload hashes and new-connection replay identity.

Worker run `nfs-20261018T221850Z-7e29f816` passes six normal transfer baselines, repeats all four source capability controls and the OS-only backend stop/restart recovery proof, and passes the four selected real-claim cases with no cleanup errors. See [raw worker evidence](RUST-NFS-SOURCE-CLAIM-REPLY-EVIDENCE.json) and [the step-by-step procedure](NFS-LOST-REPLY-LAB.md#9-source-claim-link-and-remove-with-success-replies-withheld).

| Profile | Claim boundary | Death outcome | Recovery |
|---|---|---|---|
| debug | claim_link_rpc | surviving_worker_excludes_replacement | same job/inode, attempt 1, PASS |
| debug | claim_unlink_rpc | surviving_worker_excludes_replacement | same job/inode, attempt 1, PASS |
| release | claim_link_rpc | surviving_worker_excludes_replacement | same job/inode, attempt 1, PASS |
| release | claim_unlink_rpc | surviving_worker_excludes_replacement | same job/inode, attempt 1, PASS |

Every case captures a successful source LINK/REMOVE reply while the actual claim worker remains in native linkat/unlinkat D state, and independently observes the completed server namespace transition on the original inode/content. Both servers stay healthy. All source mounts use the proxy from their first mount; no direct source mount is created. Destination uses the other server directly and local state remains local.

Initial submissions and identical-ID retries return retryable 503 with source_paths_released false, while job status stays Accepted and destination job storage is absent. Health/job calls take at most 1.875/1.875 seconds; pending same-ID retries take at most 11.750, including Podman overhead. The existing ten-second submission deadline is unchanged; these measurements are small-fixture observations, not production latency/throughput guarantees.

Read the actual death outcomes above. Surviving workers must report OwnerUnavailable and refuse an alternate-port contender until every old thread exits. Discarded replies are followed by explicit connection interruption, never forwarded as the intercepted original frame. Original-state recovery preserves the claim inode/content, database/enrollment and job ID. The same submission gets 202 only after custody is confirmed; then the producer reuses its original path. Delivery/manifest commit attempt one, retain the claimed source with cleanup false and preserve the producer's new contents. No second job/claim/attempt is allocated.

Twelve NFS-state-parent refusals, 184 state-file checks with fourteen preserved fixtures, inherited-lock and isolated-startup checks pass. Fresh production gate `20261018T210500Z-62e140fa` passes 204 tests/profile; qualification gate `20261018T210513Z-351487b3-nfs-qualification` passes 205/profile. Both use cargo-zigbuild x86_64 GNU/glibc 2.22, exact debug/release artifacts in pinned SLES 12 SP5 userspace, 20 ELF audits and six negative controls per configuration, formatting/Clippy, 42 locked external packages and the exact current 61-file Rust source inventory.

The relay additionally proves transport recovery across a source NFSD thread stop/restart with an actual pending OS hash probe; no mover is active in this supplemental control. It shuts down both socket directions on teardown, retries backend connects on the same accepted frontend for at most 600 seconds with one-second pauses, records transport events and keeps sixteen active/four hundred lifetime connections bounded on reserved ports 601â€“1000. This is not physical NAS or live-mover server-reboot qualification.

The only Rust change is two qualification-only pause mappings in relocation. Claim worker recognition and source routing changes are confined to fixture drivers. No production namespace/retry/review/shutdown policy, dependency or producer contract changes. The fresh SLES gates use the default rootless connection; the NFS fixture uses the explicit rootful connection on the shared modern VM kernel. No OS package installation, module loading or VM bootstrap is needed. Source archives, all 40 ELF hashes, fifteen worker-driver hashes, all source proof frames and exact recovery evidence are independently audited. The [exact final fixture drivers and Rust source archives](RUST-NFS-SOURCE-CLAIM-REPLY-DRIVER-EVIDENCE.json) retain executed bytes, including original line endings; Git normalizes repository text to LF. Production NFS and source deletion remain disabled; FR-03/05 remain open for the remaining operation/sync, server/durability and lifecycle obligations.

## Retained fixture failure and recovery

The [initial full run](RUST-NFS-SOURCE-CLAIM-REPLY-INITIAL-EVIDENCE.json) remains FAILED: all four source-claim cases passed, then the state-layout NFSD interruption exposed the old relay's incomplete socket teardown and unclosed backend-connect failures. The sentinel hash timed out and two normal unmounts timed out. The original healthy source controls passed only their original scope; see [initial capability evidence](RUST-NFS-SOURCE-REPLY-CAPABILITY-INITIAL-EVIDENCE.json).

[Separate cleanup and seventeen exact source snapshots](RUST-NFS-SOURCE-CLAIM-REPLY-INITIAL-RECOVERY.json) retain both failed recovery observations and the final successful recovery. Restarting the relay changed its IP; restoring its original private address/MAC and allowing pending operations to drain permitted fresh ordinary unmounts. No forced/lazy unmount or probe kill was used. The failed run was not promoted.

The [first supplemental backend-restart run](RUST-NFS-SOURCE-RELAY-RESTART-INITIAL-EVIDENCE.json) also remains FAILED: immediate frontend closes during backend refusal exhausted the 400-connection lifetime limit. Its seven original drivers are embedded with hashes. [Separate ordinary-unmount cleanup](RUST-NFS-SOURCE-RELAY-RESTART-INITIAL-RECOVERY.json) preserves the recovery actions. The final relay retries connection establishment on the same accepted frontend, with one-second pauses and a 600-second fixture-only ceiling; no RPC bytes are sent until connection succeeds, so the relay does not synthesize or replay requests. Both socket directions are shut down on established-connection teardown. The fixture-only fix and independently passing backend-restart proof precede the new complete worker run; production code and deadlines are unchanged.

Independent final inventory finds no containers on either rootful or default
rootless Podman. The rootful engine retains only the pre-existing
`file-mover-rustup-1-99` and `file-mover-cargo-registry` cache volumes and default
`podman` network. The VM remains `0::/`. The final full worker run used normal
unmounts and needed no manual cleanup; the earlier failed fixtures have the
separate recovery records above.
