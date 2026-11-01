# Cargo-libc migration

Requested 2026-11-01. Scope: replace the Rust ZigBuild gate with rustcommons'
cargo-libc, preserving GNU/glibc 2.22, the x86-64 CPU baseline, dependency and
feature qualification, independent ELF auditing and actual SLES execution.
REST contract decisions, runtime code, Cargo.lock and operational custody remain
outside this toolchain change.

The integration follows [cargo-libc's plain Cargo workflow](https://github.com/rustcommons/cargo-libc/blob/main/docs/USER-GUIDE.md#plain-cargo-and-ci)
and installs [the published 0.2.4 package](https://crates.io/crates/cargo-libc/0.2.4).
The local cargo-libc checkout was still at 0.2.0; it was inspected without
changing that repository. The published release was checked against upstream
before selection.

## Plan and acceptance

1. Pin Rust 1.99.0's official Bookworm image by digest and published cargo-libc
   0.2.4 with its locked tool dependencies. Build a cached container from
   `scripts/Containerfile.rust`; keep all five installed helpers together.
   Install Clang 16/GNU binutils there, without changing the workstation's tools.
2. Prepare the source-mode glibc 2.22 provider offline in each fresh builder.
   Export `cargo libc env --format cargo` into a per-run configuration, with
   no ambient RUSTFLAGS overriding it. Host build scripts/procedural macros
   remain native; bundled SQLite C uses cargo-libc's target compiler wrapper.
3. Use that configuration with explicit GNU targets for Clippy and Cargo
   debug/release builds. Preserve JSON discovery of every emitted executable.
   Inspect each executable with cargo-libc and independently with the existing
   readelf audit and six negative controls.
4. Hash-copy every executable into the unchanged digest-pinned SLES 12 SP5
   runtime. Require eager relocation, actual target tests and the service smoke
   check, in both production and retained qualification modes. Keep application
   builds offline/locked; provision sources separately. Run the two full gates
   sequentially in native Ubuntu WSL2 and retain failures as well as passes.
5. Update CI, agent instructions and current user documentation. Preserve old
   reports and inventories as historical Zig evidence. Record actual new run IDs,
   artifacts, source hashes, image identity, package inventory and limitations.

## Important boundaries

The `builder_base` configuration is the new Rust builder's base. The legacy
`builder` image is retained **only for NFS fixture infrastructure**, including
the two standalone C probes that use `zig cc`, Python relays and syscall observers.
It is not used to build, lint or test Rust. Replacing that fixture compiler would
change separately qualified acquisition inputs and needs its own bounded probe/
fixture validation. This migration does not silently requalify historical NFS
or systemd results for new binaries.

The derived cargo-libc builder is cached under a recipe/config hash; its actual
OCI image inspection and installed Debian package list are saved with each gate.
The Rust base and cargo-libc version/lock are pinned. Debian package repositories
are not snapshotted, so rebuilding the builder later may change Clang/binutils
package revisions; tool/package/image evidence identifies the actual build.
Retain the built image for byte-exact reproduction.

The provider linker emits dynamically linked `ET_EXEC` (non-PIE) executables,
as observed in both production profiles. This is cargo-libc's current provider
link strategy. The existing ABI gate does not enforce a PIE hardening policy;
shipping hardening remains part of FR-06/P09, not a result of this migration.

cargo-libc's automatic provider and ELF check do not replace pinned SLES runtime
tests. No kernel simulation, old CPU/kernel, real NAS, NFS fault or production
support is claimed. All eight release gates remain open; production NFS and
source deletion stay disabled.

## Results

Production run `20261101T181414Z-b2a31c1e` passed 211 tests in each of debug
and release, 20 independent ELF audits and six negative controls, with no cleanup
error. Qualification run `20261101T184249Z-346c7961-nfs-qualification` is in
progress; it is not yet a passing result.

The initial production attempt `20261101T181211Z-de05dc4d` failed before any
application build/test because the harness combined provider diagnostics on
stderr with generated TOML on stdout. The corrected gate keeps these streams
separate, validates the TOML before use and passes two regression tests on both
Windows and native WSL. The failed report/logs remain retained.

Independent read-only cloud patch review found no actionable issues. It did not
build or run the application and does not substitute for local execution.
Historical evidence remains unchanged.
