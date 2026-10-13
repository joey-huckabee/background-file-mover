# Rustix compatibility experiment results

**E2 passed on 2026-10-12 America/Chicago.** Twelve runtime phases completed in
SLES 12 SP5 userspace with glibc 2.22: a standard-library control, four rustix
cases, four cumulative rustix/SQLite cases, and three kernel NFSv4.1 cases.
The complete record is in [E2-RUSTIX-EVIDENCE.json](E2-RUSTIX-EVIDENCE.json).
The reproducible probe is under [experiments/e2-rustix](../experiments/e2-rustix).

## Qualified configuration

| Component | Value |
|---|---|
| Rust and Cargo | 1.99.0 |
| cargo-zigbuild | 0.23.4 |
| Zig | 0.16.0 |
| Requested target | x86_64-unknown-linux-gnu.2.22 |
| CPU setting | x86-64 baseline |
| rustix | 1.1.5, defaults disabled, std/fs/process enabled |
| rustix backend | linux_raw, confirmed in build output |
| linux-raw-sys | 0.12.1 |
| SQLite combination | rusqlite 0.40.1, libsqlite3-sys 0.38.2, SQLite 3.53.2 |
| Runtime | Digest-pinned SLES 12 SP5, glibc 2.22-114.34.1 |
| Execution identity | UID/GID 1000 |

The `alloc` feature is enabled by rustix's `std` feature. Features that specialize
for Linux 5.x, `linux_latest`, `io_uring`, and the libc backend were not enabled.
The [upstream manifest](https://raw.githubusercontent.com/bytecodealliance/rustix/v1.1.5/Cargo.toml)
defines these choices; the retained feature tree records the actual resolution.

The isolated x86_64 target feature tree uses rustix, bitflags, and linux-raw-sys.
The full workspace lockfile includes fifteen external crates, including build
and conditional-platform entries. Their declared license choices include MIT
or Apache-compatible terms. The experiment records that graph separately from
the final executable's host-library requirements.

## ELF and runtime libraries

| Artifact | Maximum imported glibc version | Shared libraries |
|---|---|---|
| std control | GLIBC_2.18 | libc, libdl, libpthread |
| rustix probe | GLIBC_2.18 | libc, libdl, libpthread |
| rustix and SQLite | GLIBC_2.18 | libc, libdl, libm, libpthread |
| Seccomp test launcher | GLIBC_2.2.5 | libc |

Rustix adds no shared-library requirement to the control. All artifacts use
`/lib64/ld-linux-x86-64.so.2`, have no RPATH/RUNPATH or private/newer glibc import,
and avoid importing the glibc `renameat2` wrapper. The copied artifacts match
the inspected SHA-256s; `ldd -r` and execution with `LD_BIND_NOW=1` resolve their
imports in the SLES runtime. No compiler, newer libc, or build-host libraries
were installed or mounted into it.

## Filesystem and failure checks

The local rustix probe and its SQLite combination each passed:

- fd-relative open/stat, trusted UID and regular-file checks, close-on-exec,
  and descriptor closing through Rust ownership.
- Rejection of final-file symlinks and symlink directory components.
- Detection of a deterministically replaced regular file through device/inode/type
  identity, including a held old inode that prevents reuse from masking the swap.
- Advisory-lock contention and successful acquisition after release.
- No-replace rename success and existing-destination retention.
- Forced link/unlink fallback, destination collision, and the interrupted state
  where both names refer to the same inode before source unlink.
- Actual kernel-level `ENOSYS` and `EOPNOTSUPP` responses to `renameat2`, injected
  by a seccomp test launcher; the source remains intact before fallback.
- File/directory fsync, missing-entry classification, and fd-relative unlink.

Each cumulative case also reran E1's SQLite settings, transaction, foreign-key,
contention, concurrency, and reopen checks. Authoritative state stayed on local
container storage throughout the recording-filesystem tests.

## Controlled NFS fixture

The NFS checks used a real kernel NFS mount, verified by `fstatfs` magic `0x6969`
and the recorded `/proc/mounts` entry. A separate Debian server container exported
a disposable native volume over NFSv4.1 in an internal container network. No
ports were published. The SLES client mounted that export and ran the same
rustix executable as UID 1000.

The direct fallback, injected ENOSYS, and injected EOPNOTSUPP cases passed on NFS,
including ownership/identity, symlink rejection, lock contention, collision
retention, same-inode recovery classification, file/directory fsync, and unlink.

The fixture used nfs-kernel-server/nfs-common `1:2.6.2-4+deb12u1` and rpcbind
`1.2.6-6+b1`. Its server image ID and complete package inventory are retained.
Identity mapping and a ten-second startup grace period were required; the fixture
waits eleven seconds before reporting readiness. Mount retries were bounded with
test-only `soft,timeo=10,retrans=1` settings. These settings are not a production
mount recommendation or a durability qualification.

Only fixture setup needs rootful containers and mount privileges. The package
tests execute as UID 1000; the ordinary runtime has no network or capabilities.
The fixture's containers, export volume, and network were removed after testing.

## Scope and adoption

Rustix 1.1.5 with the tested features is a qualified candidate for the filesystem
layer. Keep the Linux raw backend and the explicit no-clobber fallback policy;
no package choice removes the need to handle filesystem-dependent rename support.
Repeat import and runtime checks after changing features, versions, native
settings, or the consumed application APIs.

Both runtime containers share WSL2 kernel
`6.18.33.2-microsoft-standard-WSL2`. This experiment did not execute Linux 4.12
or older CPU hardware. The controlled NFSv4.1 peer/mount does not establish
production NFS behavior, outage isolation, power-loss durability, or every
server's atomicity guarantees; those remain R7/R13 obligations. The user's separate
build project also remains unqualified. E3, Serde/JSON, is next.
