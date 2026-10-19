# Mandatory Rust SLES build and test gate

Every Rust build/test validation must target GNU/glibc 2.22 using cargo-zigbuild
and execute the resulting tests in pinned SLES 12 SP5 userspace. A host-only
compile/test pass is insufficient, including for the dependency-free core.

Run `python scripts/check-rust-sles.py` from the repository root (Python 3.11+,
Podman). On Linux use python3 if needed; the WSL shell helper invokes the same
gate. GitHub's Rust workflow runs it on each relevant push/pull request.

## Pinned inputs

[rust-platform.json](../scripts/rust-platform.json) is the gate's configuration:

- Rust 1.99.0, cargo-zigbuild 0.23.4, Zig 0.16.0.
- Target `x86_64-unknown-linux-gnu.2.22`, `-C target-cpu=x86-64`, no musl.
- Builder `ghcr.io/rust-cross/cargo-zigbuild@sha256:9b4f6b3eb9e8f9fefb3960fe288ddba576627d66d9eff851ce7f62d2455564a5`.
- Runtime `registry.suse.com/suse/sles12sp5@sha256:4c7d476a692d4da927397d7fe4e6e9aaa93a2dea6927a69a45cb9a1fcd56ba35`.

The image contains Rust 1.93.0 initially; the harness explicitly installs/checks
1.99.0 using a named toolchain cache. Never silently use the image's older Rust.
Provision missing images/toolchain and locked crate sources first; application Cargo builds stay offline
and locked. Adding dependencies requires their controlled source provisioning
and qualification; this gate does not unpause E6 or approve arbitrary packages.

## Required checks

1. Verify pinned images/tool versions; stage a source snapshot on the builder's
   native container filesystem. Validate formatting and Clippy with warnings denied.
2. Zigbuild all workspace targets in debug and release, with JSON artifact
   discovery. Require actual emitted test binaries, not a successful library-only build.
3. Audit every executable for x86_64, the standard loader, allowed shared libraries,
   no RPATH/RUNPATH, no GLIBC_PRIVATE and no GLIBC requirement above 2.22.
   Reject a linked newer-libc renameat2 wrapper; low-level qualified syscalls are
   a separate filesystem design matter.
4. Exercise six audit negative controls: newer/private glibc, wrong loader,
   unexpected library, runtime search path and wrong architecture.
5. Verify the pinned runtime reports glibc 2.22, copy/hash-check exact artifacts,
   run `ldd -r` with eager binding and execute all discovered Rust test harnesses
   as UID/GID 1000, capabilities dropped and network disabled.
6. Fail if relocation/testing fails or no real tests run. Retain local ignored
   reports/logs/binaries; remove created containers and retain toolchain/registry caches.

The non-test service binary is audited and smoke-tested before test execution.
The gate supplies its exact relocated path to subprocess HTTP tests, which start
the service, submit/replay recordings and exercise shutdown inside SLES userspace.
Future executables must gain explicit behavior checks. Rustdoc tests or custom test harnesses
also need explicit target execution support when introduced; do not validate
them solely on a modern host. Host analysis tools are not deployed artifacts.

## Coverage boundary

Current production/qualification test counts, exact artifact hashes and the
latest passing runs are recorded in [increment 56](RUST-INCREMENT-56.md) and the
linked machine-readable reports. Every emitted executable is audited, including
the service and each target test harness. Keep debug and release evidence for
both build modes; a selected local test does not qualify a whole NFS profile.
The external graph retains E5's thirty-three
Linux packages and adds nine pinned SHA-256 packages, recorded in
[rust-integrity-dependencies.json](../scripts/rust-integrity-dependencies.json).
The gate checks their checksums and sha2's std/force-soft feature set, alongside
the qualified SQLite/rustix/Tokio/Serde/httparse configurations. Rustix's explicit
net feature and associated raw socket-binding features are qualified for private
bootstrap descriptor passing; this adds no packages or netlink/XDP behavior. See
[the automatic delivery increment](RUST-INCREMENT-06.md) and
[the operator status increment](RUST-INCREMENT-07.md) and
[the audited delivery-resume increment](RUST-INCREMENT-08.md) and
[the missing-file deadline-reset increment](RUST-INCREMENT-09.md) and
[retention accounting](RUST-INCREMENT-10.md) and
[supervised payload workers](RUST-INCREMENT-11.md) and
[claim/publication workers](RUST-INCREMENT-12.md) and
[recording filesystem sessions](RUST-INCREMENT-13.md) and
[source bootstrap isolation](RUST-INCREMENT-15.md) for tested effects and limits.
The retained [NFS qualification build](NFS-QUALIFICATION.md) uses the same gate
with `--qualification`; reports and artifact filenames distinguish modes.
Passing this compatibility gate does not imply that the separate NFS baseline
or outage qualification passed.

This qualifies the current target test artifacts and exercised logic against
SLES userspace. It does not prove old-kernel/CPU behavior, NFS durability, systemd
deployment or a not-yet-implemented production service. Keep equivalent-container
qualification, no real SLES host requirement, and controlled NFS tests as slices
introduce those effects. [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json) records
the current passing run, pinned inputs, dependencies, per-profile test counts and
artifact hashes/audits. Windows and native WSL entry points passed for the core;
the expanded workspace passed via the native WSL entry point, and increment 46
reruns both complete gates from Windows against the Linux container engine. The
GitHub workflow is configured; its remote outcome is separate from local evidence.

The [real-worker shutdown matrix](RUST-INCREMENT-45.md) is fixture-only. Its driver
requires byte-identical Rust inputs and rechecks exact artifacts from the passing
production/qualification gates before SLES execution. It does not rebuild Rust,
change dependencies or replace mandatory gates with a host-only test. New Rust
inputs always require fresh gate runs.

[Increment 57](RUST-INCREMENT-57.md) retains a separate controlled systemd
lifecycle driver. Its modern manager runs outside an unchanged pinned SLES root;
the exact mover/children/controllers run inside that root. Mandatory fresh
production and qualification gates remain separate, and manager compatibility
is not inferred from ELF/userspace compatibility.

[Increment 58](RUST-INCREMENT-58.md) records independent fresh ABI/userspace
checks alongside a blocked private-container 228 preflight. Passing these Rust
gates cannot turn unexecuted old-manager lifecycle cases into support.

See [testing limitations](TESTING-LIMITATIONS.md) for the ABI versus kernel/CPU,
storage, manager and deployment boundaries, and the [lifecycle lab procedure](SYSTEMD-LIFECYCLE-LAB.md)
for reproducible setup, exact-artifact checks, test steps and cleanup.

[Increment 60](RUST-INCREMENT-60.md) uses new production/qualification gates
and their exact byte-checked artifacts for four selected combined NFS/systemd
records. Service binaries remain byte-identical to increment 59. Manager/NFS
evidence stays separate from ABI/userspace checks and production enablement.

[Increment 61](RUST-INCREMENT-61.md) runs fresh production/qualification gates
and uses their exact audited artifacts for the two selected restart records.
Rust sources and four service binaries remain identical to increment 60;
manager/NFS lifecycle evidence remains separate from ABI/userspace compatibility.

[Increment 62](RUST-INCREMENT-62.md) uses fresh production/qualification gates
and exact byte-checked artifacts for destination-only startup outage/early recovery.
The Rust inventory and four service binaries are unchanged from increment 61;
selected NFS behavior, readiness and ownership evidence is separate from ABI
compatibility or production support.

[Increment 63](RUST-INCREMENT-63.md) adds twelve selected file/manifest
publication interruption records: four observed blocked client unlinkat syscalls
and eight crashes after namespace effects before sync. Original-state recovery
preserves inode/content and attempt one. Follow [the lab](NFS-PUBLICATION-SYNC-LAB.md)
for infrastructure, exact gates, interruptions and cleanup. Client syscall entry
does not prove RPC delivery/settlement, and pre-sync process crashes do not prove
power-loss durability. In-flight link/sync RPCs and full SH-11/12 remain open;
production NFS and source deletion stay disabled.

[Increment 64](RUST-INCREMENT-64.md) first proves server REMOVE completion
with its successful reply withheld and an actual pending client, then qualifies
four file/manifest worker cases. Loss includes explicit connection closure and
observed NFSv4.1 replay; the initial healthy-stream discard timeout stays failed.
The [lab](NFS-LOST-REPLY-LAB.md) records independent capability, exact SLES artifacts,
recovery and normal-unmount cleanup. No Rust inputs/dependencies changed. Remaining
claim/LINK/sync RPC, server-recovery/durability and full SH gates stay open;
production NFS and source deletion remain disabled.

[Increment 65](RUST-INCREMENT-65.md) qualifies four selected debug/release file/manifest LINK success-reply-loss cases after independent and repeated server-completion/withheld-success/pending-client controls. Recovery preserves original inode/content and attempt one. The loss model explicitly includes connection interruption; it does not qualify source-claim LINK, COMMIT/fsync reply loss, persistent-media/power/server recovery or old kernels. Production NFS and source deletion remain disabled.

[Increment 66](RUST-INCREMENT-66.md) qualifies four selected debug/release source-claim LINK/REMOVE success-reply-loss cases after independent and repeated source-server completion/withheld-success/pending-client controls. Initial/same-ID submissions remain retryable 503 with paths unreleased until original-state custody recovery confirms 202; only then does the producer reuse paths. Original claim inode/content, job ID, database/enrollment and attempt one survive delivery. Loss explicitly includes connection interruption; COMMIT/fsync, remaining claim/mount/security boundaries, server/media/power durability and old kernels remain unqualified. Production NFS and source deletion remain disabled.

[Increment 67](RUST-INCREMENT-67.md) correlates four actual debug/release claim/delivery synchronization traces with raw NFS traffic. Selected noac sync intervals have no observed outgoing RPC; separate buffered OS controls prove stable WRITE reply withholding/recovery, not COMMIT or mover sync-loss support. See [the reproducible sync lab](NFS-SYNC-LAB.md). No Rust/service/dependency policy changes; production NFS and source deletion remain disabled, and FR-03/05 remain open.

The increment 68 [mount-profile lab](NFS-MOUNT-PROFILE-LAB.md) executes no Rust.
Its pinned-client proc inventory decisions complement, and do not replace, both
production and qualification gates. New buffered service behavior is not qualified
by old noac worker runs or matching mount snapshots.

Increment 69's [profile authorization extension](NFS-MOUNT-PROFILE-LAB.md#supervised-rust-authorization-extension)
requires both complete passing final-source gates before using exact audited
executables. It rejects stale Rust archives/inventories and verifies copied binary
hashes. Newly added parser/configuration/descriptor tests also run only through
these gates. Preserve initial failed fixture evidence separately from final passes.
