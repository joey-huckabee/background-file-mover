# Mandatory Rust SLES build and test gate

Every Rust build/test validation must target GNU/glibc 2.22 using cargo-zigbuild
and execute the resulting tests in pinned SLES 12 SP5 userspace. A host-only
compile/test pass is insufficient, including for the dependency-free core.

Run `python scripts/check-rust-sles.py` from the repository root (Python 3.10+,
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

Future non-test service binaries are audited here and must gain explicit SLES
behavior/smoke invocations when introduced. Rustdoc tests or custom test harnesses
also need explicit target execution support when introduced; do not validate
them solely on a modern host. Host analysis tools are not deployed artifacts.

## Coverage boundary

The workspace's 38 tests pass in both profiles inside the pinned runtime:
ten core tests, nineteen SQLite storage tests and nine filesystem claim tests.
All ten emitted test executables require at most GLIBC_2.18 and use the standard
loader. The external dependency graph reuses E2's fifteen cumulative Linux
packages and E1's bundled SQLite 3.53.2 configuration. Qualified feature sets are
checked explicitly, including rustix's std/fs/process raw-syscall backend.
See [the claim increment](RUST-INCREMENT-03.md) for the local effect/recovery boundary.

This qualifies the current target test artifacts and exercised logic against
SLES userspace. It does not prove old-kernel/CPU behavior, NFS durability, systemd
deployment or a not-yet-implemented production service. Keep equivalent-container
qualification, no real SLES host requirement, and controlled NFS tests as slices
introduce those effects. [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json) records
the current passing run, pinned inputs, dependencies, per-profile test counts and
artifact hashes/audits. Windows and native WSL entry points passed for the core;
the current expanded workspace passed via the Windows entry point. The
GitHub workflow is configured; its remote outcome is separate from local evidence.
