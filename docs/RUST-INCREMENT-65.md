# Rust increment 65: server-completed LINK reply loss

## Scope fixed before worker execution

Keep production NFS and source deletion disabled. Extend the existing transparent
relay with explicit REMOVE (28) or LINK (11) selection; retain REMOVE defaults.
Add qualification-only pauses immediately inside the exclusive-link namespace
call, before native linkat, for file and manifest publication. No production
retry, review, deadline, ownership or publication policy change is intended.

Before any mover LINK loss case, independently prove both release and
discard-plus-connection-interruption controls without executing Rust. Start with
one staging link and no final name. Require a matching RPC/NFS/LINK success held
by the relay, both server-local names bound to the original inode with link count
two and unchanged content, and the actual client still pending in D state.
Release must complete successfully. Discard must close the affected connection
and produce observed session replay on a new connection, never forwarding the
intercepted frame. Repeat this capability gate in the mover fixture.

Four worker cases: debug/release times file/manifest LINK. Both NFS endpoints
remain healthy and independent within the controlled VM; state stays local.
Require native x86_64 linkat (265), correct source/destination parent descriptors,
withheld success and server-local two-alias evidence. API remains responsive,
custody replay is 202 and SQLite must not falsely commit. Kill the coordinator,
retain exclusion through actual old-thread exit, discard the buffered success
with explicit connection interruption, then recover original state. Preserve
payload/manifest inode/hash, attempt one, source custody, database/enrollment and
producer-reused paths; remove only owned staging aliases during recovery.

## Limits

This is selected NFSv4.1 LINK reply loss plus connection interruption. It is not
healthy-stream silent-loss bounded retry, source-claim LINK qualification,
COMMIT/fsync reply loss, server reboot, persistent-media/power durability, physical
NAS isolation, old-kernel qualification or systemd testing. Server completion is
not durable publication or whole-recording commitment. Do not infer settlement
from a free local lock or universal termination deadlines from selected exits.
Each worker fixture contains one explicitly listed nested file of 2 MiB plus
17 bytes. These cases do not qualify large-recording throughput, concurrent jobs,
queue saturation, multiple-file commitment or every export/mount/security profile.

## Results

Independent capability `reply-capability-20261018T200112Z-fb530318` passes release and discard-plus-connection-interruption controls before any Rust LINK worker test, with no cleanup errors. See [independent raw proof](RUST-NFS-LINK-REPLY-CAPABILITY-EVIDENCE.json). Retained REMOVE controls also pass in `reply-capability-20261018T200427Z-a948eee5`; see [regression evidence](RUST-NFS-REMOVE-REPLY-REGRESSION-EVIDENCE.json). The increment-64 initial healthy-stream silent-loss failure remains unchanged.

Worker run `nfs-20261018T203516Z-eb5b56b7` repeats both LINK capability controls and passes all four selected cases with normal-unmount-first cleanup and no errors. See [raw worker evidence](RUST-NFS-LOST-LINK-REPLY-EVIDENCE.json).

| Profile | Boundary | Death outcome | Recovery |
|---|---|---|---|
| debug | file_link_rpc | surviving_worker_excludes_replacement | original inode, attempt 1, PASS |
| debug | manifest_link_rpc | surviving_worker_excludes_replacement | original inode, attempt 1, PASS |
| release | file_link_rpc | surviving_worker_excludes_replacement | original inode, attempt 1, PASS |
| release | manifest_link_rpc | surviving_worker_excludes_replacement | original inode, attempt 1, PASS |

Each captured success corresponds to real server creation of the final hard link while the actual mover remains in native linkat 265/D state. Staging/final share the original inode, size/hash and link count two; neither endpoint is stopped. API health/status/replay remain bounded and the job stays Claimed with unchanged durable phases. Server-local manifest visibility is not SQLite commitment.

Maximum measured health/job/replay calls take 1.797/1.890/1.938 seconds including Podman overhead. These small-fixture observations are not production latency or throughput guarantees.

Actual surviving-worker outcomes above retain exclusion, report OwnerUnavailable and refuse an alternate-port contender. After killing the known old worker, discarding buffered successes and explicitly closing their connections, every old thread must be Z/gone before recovery. Original-state recovery commits attempt one, preserves payload/manifest inode/hash and source/database/enrollment, removes only owned staging, retains claimed source with cleanup false and preserves producer-reused paths.

Six normal transfer baselines, twelve NFS-state-parent refusals, 184 state-file checks with fourteen preserved fixtures, inherited-lock and isolated-startup checks pass. Fresh production gate `20261018T200219Z-f573e23c` passes 204 tests/profile; qualification gate `20261018T200231Z-a5394a11-nfs-qualification` passes 205/profile. Both use cargo-zigbuild GNU/glibc 2.22, pinned SLES 12 SP5 userspace, debug/release exact-artifact tests, 20 ELF audits and six negative controls per configuration, formatting/Clippy, 42 locked external packages and 61 exact Rust inputs.

The fresh SLES gates used the default rootless Podman connection; the NFS capability and worker fixtures use the explicit rootful connection. Both gate/runtime images remain pinned; all containers share the modern VM kernel. No package installation, module loading or VM bootstrap was needed.

The only Rust change is four qualification-only hook lines in relocation. No production namespace/retry/review/deadline/deletion behavior changed. Raw wire payloads, driver hashes, source archives and all 40 ELF hashes are independently checked. No production NFS or source deletion is enabled; FR-03/05 remain open for the remaining operation/sync, durability and lifecycle obligations.

Independent final inventory finds no validation containers on either rootful or
default rootless Podman. The rootful engine retains only the two pre-existing
Rust cache volumes and default `podman` network. The VM remains `0::/`. All
fixture mounts were normally unmounted before owned resources were removed;
no manual cleanup or forced/lazy unmount was needed in either worker attempt.

## Retained fixture failure

The [initial worker run](RUST-NFS-LINK-REPLY-INITIAL-EVIDENCE.json) remains FAILED: debug file LINK passed, then the manifest fixture raised IndexError before arming the relay because it indexed a slash-free `COMMITTED.json` basename with `[1]`. Normal fixture cleanup passed with no errors. The fix uses `[-1]` for both nested payload and plain manifest names; it changes only the Python driver. [The exact original drivers](RUST-NFS-LINK-REPLY-INITIAL-DRIVER.json) are retained with SHA-256 and base64 source, and all fourteen originally executed driver hashes were verified before changing it. This is a fixture failure, not passing manifest qualification or a mover defect. Both SLES artifacts and independent LINK capability drivers are unchanged by the fix.
