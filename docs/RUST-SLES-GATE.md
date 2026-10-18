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
