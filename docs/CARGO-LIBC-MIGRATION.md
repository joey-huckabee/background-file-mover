# Cargo-libc migration

Requested 2026-11-01. Scope: replace the Rust ZigBuild gate with rustcommons'
cargo-libc, preserving GNU/glibc 2.22, the x86-64 CPU baseline, dependency and
feature qualification, independent ELF auditing and actual SLES execution.
REST contract decisions, runtime code, Cargo.lock and operational custody remain
outside this toolchain change.

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

cargo-libc's automatic provider and ELF check do not replace pinned SLES runtime
tests. No kernel simulation, old CPU/kernel, real NAS, NFS fault or production
support is claimed. All eight release gates remain open; production NFS and
source deletion stay disabled.

## Results

Implementation and validation in progress. Do not treat this plan as a passing
gate report. Historical evidence remains unchanged.
