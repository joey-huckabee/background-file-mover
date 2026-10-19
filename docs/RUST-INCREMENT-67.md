# Rust increment 67: synchronization RPC capability and correlation

## Scope declared before execution

Keep production NFS and source deletion disabled. No production Rust behavior,
dependencies, retries or deadlines change. Observe actual worker fsync/fdatasync
syscalls using an external, bounded fixture tracer, correlated with bounded raw
RPC traffic through the retained relay. The tracer uses the modern fixture
kernel; it is not a service dependency or old-kernel qualification.

First qualify the observer with a small OS-only GNU/glibc-2.22 C probe, built
inside the pinned builder and ELF-audited, running in pinned SLES userspace.
Observe clean-file, dirty-file and directory synchronization in the existing
hard/noac mount profile. Separately try a buffered mount control: intercept a
successful WRITE or COMMIT reply only if generated, prove server-visible bytes
and a pending native fsync, then release or discard with explicit connection
interruption and require completion. Retain actual protocol stability/verifier
fields; do not fabricate a COMMIT, change reply contents or treat RAM visibility
as physical-media durability. An unavailable boundary remains unqualified.

After independent capability evidence, correlate debug/release actual claim and
recording delivery workers (four finite traces) through existing qualification
pauses. Trace actual file and directory sync return codes, descriptor identities
and RPC intervals. Preserve same-job/attempt-one delivery, producer path reuse
only after 202, source retention and original local state. If real service sync
calls produce no interceptable RPC, report that limitation rather than substituting
an artificial worker failure or inferring synchronization durability. Keep the
retained transfer/local-state/startup checks and both mandatory SLES gates.

## Results

Independent `reply-capability-20261018T235849Z-99eef171` passes with no cleanup errors: two retained REMOVE controls, three noac native sync observations, a buffered dirty-file discovery and two successful buffered WRITE withholding/recovery controls. [Raw capability](RUST-NFS-SYNC-CAPABILITY-EVIDENCE.json) captures actual fsync 74, file descriptor, matched successful WRITE, server-visible original data/inode while the caller waits, and two NFSD threads on both servers. Held WRITE requests ask for FILE_SYNC (2), and successful replies report committed=2 for all 4096 original bytes. This is protocol/tmpfs visibility, not power durability. No COMMIT was observed or withheld.

The noac OS probes issue no RPC during their fsync intervals. The buffered discovery issues WRITE (38) inside fsync. Release completes normally. Discard explicitly interrupts the connection; the captured client retry gets NFS4ERR_RETRY_UNCACHED_REP (10068), then a new SEQUENCE/stateid resend succeeds with the same filehandle, offset, stability, size and payload hash. The original inode/content remain unchanged. Three negative controls reject altered filehandle, offset or data hash. This is native client recovery in a separate buffered OS control, not a qualified mover sync-loss path.

Actual-service run `nfs-20261019T000329Z-385f192f` passes all four healthy worker traces:

| Profile | Worker scope | NFS sync calls | RPC calls inside those syncs |
|---|---|---:|---:|
| debug | claim_apply / source | 8 | 0 |
| debug | copy_chunk / destination | 20 | 0 |
| release | claim_apply / source | 8 | 0 |
| release | copy_chunk / destination | 20 | 0 |


All 56 observed NFS fsync calls (x86_64 syscall 74) return zero, with no outgoing RPC inside their syscall intervals. No fdatasync call (75) was observed. Descriptor inode/mount identity comes from local proc data, not a target stat that could cause NFS I/O. Relay records are bounded at 8,192 frames/64 MiB raw RPC bytes per observation window and use the same kernel monotonic clock. The [clock audit](RUST-NFS-SYNC-CLOCK-EVIDENCE.json) independently verifies actual namespace equality across the client, relays and all four external observers. Unsupported compounds remain raw/unknown and cannot establish absence within a nonempty interval. Ptrace changes scheduling; timings are not performance evidence.

Delivery traces record their existing supervised session retirement separately. For either normal exit or SIGKILL retirement, the runner requires an already-Committed job/attempt-one receipt before any recovery/replay call. Claim workers and OS probes still require exit zero. Trace validity alone never substitutes for that durable receipt. The coordinator already uses [Supervised::drop](../rust/crates/file-mover/src/payload.rs) to kill/reap a completed [delivery Session](../rust/crates/file-mover/src/delivery_worker.rs); no production retirement or shutdown logic changed.

The current noac/synchronous-write fixture therefore provides no observed WRITE/COMMIT at these real service sync boundaries to withhold. No worker synchronization reply-loss/death cases were substituted from the buffered control, and no COMMIT/directory/media durability support is claimed. Future shipping profiles and synchronization boundaries stay open under FR-03/05. These four cases are normal execution observations, not coordinator-death qualification.

Every case commits job 1 on attempt one, preserves original claimed inode/content, source retention, database identity and enrollment receipts, and reuses producer paths only after confirmed 202. The recorder still only retries its identical JSON until 202; consumers still require the validated completion manifest. Production NFS and source deletion remain disabled.

Six normal-transfer baselines, twelve NFS-state-parent refusals, 184 state-file checks with fourteen preserved fixtures, inherited-lock and isolated-startup checks pass. Fresh production `20261018T225503Z-f7dd92d6` passes 204 tests/profile; qualification `20261018T225515Z-26264095-nfs-qualification` passes 205/profile. Both use cargo-zigbuild GNU/glibc 2.22 and exact debug/release artifacts in pinned SLES 12 SP5 userspace, 20 ELF audits and six negative controls per configuration, 42 locked external packages and 61 Rust inputs. Seven fixture decoder tests include WRITE/COMMIT field/truncation/stability rejection.

There are no Rust source or dependency changes. The external tracer and separately ELF-audited C OS probe are disposable fixture infrastructure; no additional service executable is shipped. [Exact drivers, Rust input archives and OS probe](RUST-NFS-SYNC-DRIVER-EVIDENCE.json) retain byte-level provenance. See [the step-by-step lab](NFS-SYNC-LAB.md), [worker evidence](RUST-NFS-SYNC-EVIDENCE.json) and [testing limits](TESTING-LIMITATIONS.md). Large reports use a lossless zlib-base64-json envelope; decode report_zlib_base64 and check report_sha256 before inspecting it. A parts envelope lists ordered part files/hashes: concatenate their data_base64_segment strings first; nested trace payloads have their own hashes.

## Retained initial failures

[Initial setup](RUST-NFS-SYNC-INITIAL-EVIDENCE.json) remains FAILED: the UID-1000 compiler had no Zig cache location, so no sync probe ran. Explicit private cache paths fix only fixture setup.

[Initial WRITE replay validation](RUST-NFS-SYNC-WRITE-REPLAY-INITIAL-EVIDENCE.json) also remains FAILED: fsync and native recovery completed, but an overstrict namespace-style byte-identical replay assertion rejected the uncached WRITE resend. The corrected validator requires the captured exact retry/error followed by semantic data-range identity and successful full stable write, plus unchanged server inode/content. Both failed capability reports retain all original driver bytes/hashes and clean normal cleanup; neither is promoted.

The [initial worker run](RUST-NFS-SYNC-WORKER-INITIAL-EVIDENCE.json) also remains FAILED: debug claim passed, then the tracer rejected the delivery session retirement because it assumed exit zero. Twenty observed delivery sync calls had returned zero before supervised SIGKILL. The run never reached the retained state-layout matrix; cleanup was clean. Its thirteen exact drivers remain embedded. The corrected typed retirement check additionally requires an already-Committed job before any recovery call; a kill by itself is not success.

The [initial capture-bound rerun](RUST-NFS-SYNC-TRACE-BOUND-INITIAL-EVIDENCE.json) remains FAILED: the delivery window exceeded 1,024 frames (mostly GETATTR metadata) after 1,258,816 captured bytes; it correctly refused to establish complete coverage. No state-layout regression pass was reached. Cleanup was clean, and thirteen exact drivers remain retained. The fixture limit is now explicitly 8,192 frames/64 MiB; overflow still invalidates a trace and is never silently dropped.

The [initial whole-window capture run](RUST-NFS-SYNC-CAPTURE-OVERHEAD-INITIAL-EVIDENCE.json) also remains FAILED: the delivery worker exceeded the fixture exit wait while the observer rewrote its growing JSON window per packet. Capture had 1,990 frames/1,457,688 bytes with no overflow or relay error, and cleanup was clean. Fourteen exact drivers and the conservatively incomplete clock report remain retained. Capture now stays bounded in memory and is flushed at acknowledged controls, successful reply holds, connection events and errors; a missing stop acknowledgement cannot qualify a trace. This removes observer-generated full-window I/O per packet without relaxing any worker, service or shutdown deadline. The initial tracer's target-stat approach was removed before any sync probe ran to avoid observer-generated NFS I/O.

These controlled tmpfs servers share the modern VM kernel `6.18.33.2-microsoft-standard-WSL2`. Physical NAS, old kernels, persistent media/power, server reboot/reclaim, separate producer-client visibility, larger/load/concurrency cases and unobserved mount/security profiles are not qualified. The [initial auxiliary clock check](RUST-NFS-SYNC-CLOCK-INITIAL-EVIDENCE.json) failed on a list/inspect race during teardown of the already-failed trace-bound run; it did not establish a clock mismatch. The maintained read-only clock checker now tolerates disappearing containers, preserves partial observations and requires all four live observers before passing. The modern-kernel tracer is not a deployment requirement. No VM reboot, OS package installation or new bootstrap was needed.

Independent final inventory confirms no containers on either rootful or default
rootless Podman. Only the pre-existing `file-mover-rustup-1-99` and
`file-mover-cargo-registry` rootful cache volumes and default `podman` network
remain; the VM cgroup is `0::/`. Final fixture cleanup used ordinary unmounts
and needed no manual intervention. Earlier failed fixtures also cleaned up
normally, with their FAILED reports preserved.
