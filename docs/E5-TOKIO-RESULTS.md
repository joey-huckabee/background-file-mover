# Tokio compatibility experiment results

**E5 passed on 2026-10-13 America/Chicago.** Tokio replaces the direct
signal-hook candidate. Fifteen main runtime phases and two forced entropy
fallback phases passed in pinned SLES 12 SP5/glibc 2.22 userspace. No platform
blocker was found for the tested configuration. The record is
[E5-TOKIO-EVIDENCE.json](E5-TOKIO-EVIDENCE.json); reproduce with
[experiments/e5-tokio](../experiments/e5-tokio).

## Configuration and dependency cost

| Component | Qualified value |
|---|---|
| Rust/Cargo | 1.99.0 |
| Reference builder | cargo-zigbuild 0.23.4, Zig 0.16.0 |
| Target / CPU | x86_64-unknown-linux-gnu.2.22 / baseline x86-64 |
| Tokio | 1.53.2, defaults disabled |
| Requested features | rt, signal, sync, time, net, io-util |
| Executor | Current-thread, IO/time enabled |
| Blocking work | Two blocking threads, bounded fixture/semaphore admission |
| Runtime | Pinned SLES 12 SP5; glibc-2.22-114.34.1 |
| Identity/security | UID/GID 1000, eager binding, no capabilities, loopback only |

The selected features enable bytes/libc/mio/socket2/signal-hook-registry and
conditional windows-sys wiring. No full, macros, rt-multi-thread, fs, process,
parking_lot, io-uring or unstable setting is enabled. No Tokio procedural macros
or direct signal-hook crate is resolved. **signal-hook-registry remains a
transitive dependency** of Tokio's Unix signals, as documented by the
[upstream manifest](https://raw.githubusercontent.com/tokio-rs/tokio/master/tokio/Cargo.toml)
and confirmed in the actual pinned graph.

Compared with E4, the Linux workspace graph adds six packages: tokio 1.53.2,
bytes 1.12.1, mio 1.2.4, pin-project-lite 0.2.17, signal-hook-registry 1.4.8
and socket2 0.6.5. All prior package versions are unchanged. The filtered
x86_64 workspace graph has 33 external packages; Cargo.lock has 36, including
conditional wasi/windows packages. License choices remain MIT/Apache compatible.
Existing Serde macro tools remain build-host dependencies. This is broader
than a signal-only crate and is justified here by testing signals, timers and
async socket coordination together.

## Binary compatibility

| Executable | Highest versioned GLIBC requirement | Shared libraries |
|---|---|---|
| std control | GLIBC_2.18 | libc, libdl, libpthread |
| isolated Tokio | GLIBC_2.18 | libc, libdl, libpthread |
| cumulative E1–E5 | GLIBC_2.18 | libc, libdl, libpthread, libm |

Tokio adds no shared libraries. All service probes retain the expected
`/lib64/ld-linux-x86-64.so.2`, lack RPATH/RUNPATH and GLIBC_PRIVATE/newer glibc
requirements, pass `ldd -r`, and execute with eager binding. Copied hashes match
the inspected artifacts. Six negative ELF controls reject incompatible reports.
The resolved mio backend uses epoll_create1/epoll_wait; io-uring is not enabled.

The isolated Tokio binary also exposes an **unversioned WEAK getrandom** import
from Rust's standard library. The pinned SLES libc has no getrandom export;
that optional import does not impose glibc 2.25. Rust's pinned std source provides
a raw-syscall path, unsupported-flag fallback, and device fallback. To test
actual behavior, a test-only seccomp launcher verified its own filter and reran
the same Tokio binary with GRND_INSECURE rejected by EINVAL (older-kernel flag
behavior), then with all getrandom syscalls rejected by ENOSYS. Both complete
runtime/TCP/blocking batteries passed. The launcher itself requires only libc
and GLIBC_2.2.5 and is not deployed with the service.

## Runtime, signals and cumulative results

The std control and two self-test phases cover timers, channels, semaphore
admission, current-thread progress during blocking work, two-thread blocking
pool behavior, async TCP accept/read/write and timeouts. A started blocking job
continues after abort; its completion is awaited before shutdown. The cumulative
phase repeats SQLite, rustix rename/link-unlink, JSON and HTTP batteries, then
passes Tokio TCP through httparse and strict typed JSON to a real blocking SQLite
transaction. Commit precedes the 201 response, and reopening verifies the row.

Twelve additional cases use real subprocess signal delivery: each isolated and
cumulative binary receives SIGTERM/SIGINT while idle and while doing blocking
fsync/SQLite work, a burst of ten SIGTERMs during work, and TERM/INT/TERM across
three listener drop/recreate cycles. Senders use the service UID, retaining the
capability restrictions. Main and blocking-thread signal masks permit both stop
signals. Rust startup's ignored SIGPIPE disposition remains intact; broken-pipe
writes return errors. The stop state is sticky and does not depend on counting
one notification for every delivered signal. Started worker operations drain;
reopened SQLite row counts equal completed operations after runtime shutdown.

Dropping Tokio signal streams leaves handlers installed for the process lifetime;
the cycle test checks this disposition explicitly. This follows
[Tokio's signal semantics](https://docs.rs/tokio/latest/tokio/signal/index.html).
Application code handles notifications in async tasks, with no custom unsafe
signal callback or database/filesystem work in a signal handler.

## Adoption boundary

The completed main run is `20261013T091043Z-5dbc1e45`, reusing build
`20261013T090637Z-71e5ab70` after comparing archived source inputs with current
Rust/C++/corpus files. The separate entropy supplement uses the same inspected
Tokio artifact. Evidence retains the lockfile, graph/features, macro commands,
ELF imports/binding, hashes, inventories, signal output and verified fault filters.
Ignored results retain binaries and source/vendor archives. All created containers
were removed.

Tokio is acceptable for this qualified scope. Its executor must not run blocking
SQLite/NFS work, and a thread limit alone does not bound queued work. Started
spawn_blocking jobs cannot be aborted; shutdown_timeout stops waiting rather
than canceling them. Production must stop admission and drain or apply the
separate NFS isolation strategy. The migration plan now states those requirements.
[Tokio blocking-task documentation](https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html).

Tests still share the WSL2 kernel/CPU. The selective entropy filters exercise
specific compatibility paths without proving the whole old kernel; actual
old-kernel/CPU execution, final runtime sizing, sustained-load behavior, NFS hangs,
forced termination and the user's own builder remain later qualification work.
No actual SLES host is required. The [NFS fixture note](NFS-TEST-FIXTURE.md)
remains available. E6 (`thiserror`) is next.
