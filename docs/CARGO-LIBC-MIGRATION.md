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
   check, in both production and retained qualification modes. Launch target
   test executables in their own visible session/group with `setsid --wait`,
   preserving failure exit statuses and verifying the launch environment first.
   Keep application builds offline/locked; provision sources separately. Run
   both full gates sequentially in native Ubuntu WSL2 and retain failures as
   well as passes.
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
Retain the built image and raw packs to preserve the exact historical inputs.

The provider linker emits dynamically linked `ET_EXEC` (non-PIE) executables,
as observed in both production profiles. This is cargo-libc's current provider
link strategy. The existing ABI gate does not enforce a PIE hardening policy;
shipping hardening remains part of FR-06/P09, not a result of this migration.

cargo-libc's automatic provider and ELF check do not replace pinned SLES runtime
tests. No kernel simulation, old CPU/kernel, real NAS, NFS fault or production
support is claimed. All eight release gates remain open; production NFS and
source deletion stay disabled.

## Results

Both native WSL gates passed with Rust runtime code/manifests/Cargo.lock unchanged:

| Mode | Run | Debug tests passed | Release tests passed |
| --- | --- | ---: | ---: |
| Production | `20261101T181414Z-b2a31c1e` | 211 | 211 |
| Qualification | `20261101T184249Z-346c7961-nfs-qualification` | 213 | 213 |

Each gate audited and inspected 20 executables, exercised six audit negative
controls and completed cleanup without errors. Independent post-run verification
matched both 62-file source snapshots to current Rust inputs, checked both
archive hashes, rehashed all 40 retained binaries and checked every cargo-libc
inspection. [The evidence record](CARGO-LIBC-EVIDENCE.json) retains the reports,
report hashes and actual local builder image identity. Raw packs remain in
`/home/joey/GIT/background-file-mover-testing/rust/validation/`.

These local gates ran the integration at `bdd24d8`; subsequent CI launcher fixes
do not change Rust inputs, toolchain configuration or the builder recipe. Final
CI gates additionally validate the new session launcher on GitHub's OCI engine.

The initial production attempt `20261101T181211Z-de05dc4d` failed before any
application build/test because the harness combined provider diagnostics on
stderr with generated TOML on stdout. The corrected gate keeps these streams
separate, validates the TOML before use and passes two regression tests on both
Windows and native WSL. The failed report/logs remain retained.

GitHub initially exposed a pre-existing container-launch problem: the service's
`rustix::process::getpgrp()` panicked because its group was outside the visible
PID namespace (group ID zero). Run `41339459969` failed immediately in both
modes; `41339844179` retained full diagnostics identifying the panic. The older
ZigBuild run `39820695958` had the same 12/72 production and 9/75 qualification
pass/fail counts. No runtime ownership assertion was removed or weakened.

The corrected launcher uses SLES's `setsid --wait`, records PID == PGID == SID > 0
before testing, and preserves child failure status. A local SLES probe verified
matching positive IDs and propagation of exit status 7; old SLES `ps` requires
separate `-o` options for the preflight columns. CI now retains diagnostic
reports/logs for 14 days and allows 60 minutes per mode for complete runs.

Final [CI run 41340296012](https://github.com/joey-huckabee/background-file-mover/actions/runs/41340296012)
passed both complete modes at commit `b6d90ac`: production 211 and qualification
213 tests in each of debug/release. Its reports confirm private positive test
sessions and no cleanup errors. Downloaded CI reports and their hashes are
retained alongside local results in [the evidence record](CARGO-LIBC-EVIDENCE.json).

Two independent read-only cloud reviews, covering the migration and the session
fix respectively, found no actionable issues. They did not build or run the
application and do not substitute for execution. Historical evidence remains
unchanged; all eight release gates remain open.
