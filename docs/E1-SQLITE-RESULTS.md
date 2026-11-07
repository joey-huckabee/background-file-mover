# SQLite compatibility experiment results

**E1 passed on 2026-10-12 America/Chicago.** Rust SQLite operations ran
unprivileged in digest-pinned SLES 12 SP5 userspace with glibc 2.22. The complete
version, dependency, hash, import, and runtime-output record is retained in
[E1-SQLITE-EVIDENCE.json](E1-SQLITE-EVIDENCE.json). The temporary experiment's
sources, binaries, vendor archives, and raw logs have been removed as requested.

## Qualified build and runtime

| Component | Recorded value |
|---|---|
| Rust and Cargo | 1.99.0 |
| cargo-zigbuild | 0.23.4 |
| Zig | 0.16.0 |
| Target | x86_64-unknown-linux-gnu.2.22 |
| CPU settings | x86-64, forwarded to the C wrapper as x86_64 |
| rusqlite | 0.40.1, defaults disabled, bundled enabled |
| libsqlite3-sys | 0.38.2 |
| Bundled SQLite | 3.53.2 |
| Runtime glibc | 2.22-114.34.1 |
| Loader | /lib64/ld-linux-x86-64.so.2 |
| Runtime user | UID/GID 1000 |
| Runtime restrictions | No network, capabilities, or new privileges |

Builder image:
`ghcr.io/rust-cross/cargo-zigbuild@sha256:9b4f6b3eb9e8f9fefb3960fe288ddba576627d66d9eff851ce7f62d2455564a5`.

Runtime image:
`registry.suse.com/suse/sles12sp5@sha256:4c7d476a692d4da927397d7fe4e6e9aaa93a2dea6927a69a45cb9a1fcd56ba35`.

The reference builder compiled on native container storage. The runtime received
only the resulting executables, with matching hashes, and used its existing
loader/libraries. No compiler, SQLite package, source mount, or newer libc was
introduced into the runtime. The eleven resolved external crates declare MIT
or Apache-compatible licenses; their versions and source checksums are retained
with the lockfile in the evidence record.

## Imports and checks

Both the standard-library control and SQLite executable require at most
`GLIBC_2.18`. The control imports libc, libdl, and libpthread; SQLite adds only
libm. Neither imports a shared SQLite, libgcc, libstdc++, OpenSSL, or an alternate
loader. There is no RPATH/RUNPATH or `GLIBC_PRIVATE` import. `ldd -r` and
`LD_BIND_NOW=1` verified import resolution before and during execution.

The experiment verified:

- `THREADSAFE=1`, `OMIT_LOAD_EXTENSION`, `DQS=0`, `DEFAULT_MEMSTATUS=0`, and
  `ENABLE_API_ARMOR`, including absence of native/SQL extension-loading entry
  points and rejection of double-quoted string fallback.
- WAL, FULL synchronization, and foreign keys, with settings read back.
- Committed and rolled-back transactions, foreign-key rejection, SQLite busy
  timeout, and successful writing after the contending lock was released.
- Four threads with separate connections committing forty rows, integrity
  checking, WAL checkpoint, and a separate process reopening all forty-two rows.
- ELF audit rejection of newer/private glibc requirements, a different loader,
  shared SQLite, and build-host library search paths.

Control SHA-256:
`57654540723c4912d3067ee6866c965f14f55ea21cd1d812c0dd8cf76a76363a`.

SQLite executable SHA-256:
`c6d57abd0c62c79f50817ceb0c81b7cb21e1769110c38c94dd76577158d04238`.

## Findings and scope

rusqlite 0.40.1 failed to compile with the builder image's Rust 1.93 because it
uses `cfg_select!`; Rust 1.99 passed. The experiment pinned the newer toolchain.
The Zig 0.16 link emitted a warning about a deprecated linker optimization
setting; the artifacts passed inspection and execution.

The bundled SQLite version was 3.53.2, whereas the C++ baseline uses 3.53.4.
Changing that version or the enabled features requires another check before
repository adoption in R2/R6. The crate license review does not certify all
components of the Rust/Zig toolchain or container distribution.

The SLES image ran on Podman's WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`. Linux 4.12 and older CPU hardware were not
executed. The image contains libgcc/libstdc++ 13.3, but neither executable imports
those shared libraries. NFS, systemd/MAC enforcement, crash recovery, and
power-loss durability were outside E1. This result applies to the recorded
configuration and exercised APIs.
