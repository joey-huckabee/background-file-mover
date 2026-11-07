# HTTP compatibility experiment results

**E4 passed on 2026-10-13 America/Chicago.** Five runtime phases completed:
the std control, normal HTTP/TCP probe, verified SIMD-disabled HTTP/TCP probe,
and cumulative HTTP/JSON/SQLite/rustix probes in rename and link/unlink modes.
The record is [E4-HTTP-EVIDENCE.json](E4-HTTP-EVIDENCE.json); the reproducible
experiment is [experiments/e4-http](../experiments/e4-http).

## Qualified inputs

| Component | Value |
|---|---|
| Rust/Cargo | 1.99.0 |
| Reference builder | cargo-zigbuild 0.23.4, Zig 0.16.0 |
| Target / CPU | x86_64-unknown-linux-gnu.2.22 / baseline x86-64 |
| httparse | 1.10.1; default features disabled; std enabled |
| Normal parser | Runtime SIMD dispatch, no compile-time SSE4.2/AVX2 requirement |
| Scalar comparison | Published crate's SIMD-disable setting; SWAR fallback |
| Cumulative | E1 SQLite, E2 rustix, E3 serde/serde_json configurations |
| Runtime | Pinned SLES 12 SP5, glibc-2.22-114.34.1 |
| Execution | UID/GID 1000, LD_BIND_NOW=1, no capabilities, container loopback only |

httparse adds exactly one external crate to the E3 graph: itself. It has no
production crate dependencies. The workspace lockfile resolves 27 external
packages, including existing build/macro and conditional-platform packages,
with MIT/Apache-compatible license choices. E3's versions and host macro
packages are unchanged. Exact versions/features and compiler commands are
retained in the evidence.

## Binary compatibility and CPU checks

| Executable | Highest GLIBC import | Shared libraries |
|---|---|---|
| std control | GLIBC_2.18 | libc, libdl, libpthread |
| normal HTTP/TCP | GLIBC_2.18 | libc, libdl, libpthread |
| SIMD-disabled HTTP/TCP | GLIBC_2.18 | libc, libdl, libpthread |
| cumulative HTTP/JSON/SQLite/rustix | GLIBC_2.18 | libc, libdl, libpthread, libm |

All binaries use `/lib64/ld-linux-x86-64.so.2`, have no RPATH/RUNPATH,
GLIBC_PRIVATE or newer-than-2.22 imports, and pass `ldd -r` and eager binding
in SLES userspace. Copied binary hashes match inspected artifacts. HTTP adds
no shared libraries; cumulative libm remains SQLite's dependency. The same
six negative ELF audit controls used in E3 reject newer/private glibc, wrong
loader, extra shared library, RUNPATH and wrong architecture.

The normal artifact contains httparse SSE4.2, AVX2 and cached runtime-dispatch
symbols. The runner reports both CPU features available; upstream selection
of the AVX2 path is inferred from its dispatch source and feature detection,
not branch instrumentation. Baseline CPU flags remain explicit for Rust and
native SQLite. No native CPU specialization is used.

The published 1.10.1 crate differs from current upstream master in how it
disables SIMD: its build script needs `CARGO_CFG_HTTPARSE_DISABLE_SIMD=1`.
The scalar build supplies `--cfg httparse_disable_simd="1"` in RUSTFLAGS,
which Cargo exposes to that build script. A boolean cfg supplies no `1` and
does not disable SIMD in this release. The initial comparison exposed that
mistake in the executable symbol table. The final gate requires the build's
disable diagnostic and absence of httparse SSE4.2/AVX2/runtime-dispatch
symbols, then runs the same parser/TCP battery on the SWAR artifact.
The resolved crate's complete source is retained in the vendor archive;
[upstream documentation](https://github.com/seanmonstar/httparse) supplies
context, while the pinned source and binary evidence establish actual behavior.

## Parser and framing policy

httparse supplies parsing, while an experimental adapter preserves the
service's narrower policy: exact CRLF framing, uppercase methods of length
1–16, origin-form targets without whitespace/control bytes, HTTP/1.0 or 1.1,
the restricted header-name character set, trimmed OWS, no interior controls,
64 headers and no case-insensitive duplicate names. Bodies require whole-token
unsigned decimal Content-Length, reject all Transfer-Encoding, and cap at
65536 bytes. Head size caps at 8192 bytes. Incomplete frames need more input;
extra received bytes or a pipelined second request are rejected.

The C++ parser runs only on the build host as an independent oracle. All 37
HTTP corpus files match head verdict, consumed head length, and Content-Length
outcome: 10 valid heads/lengths, 17 malformed heads, 7 length-policy failures,
and 3 incomplete heads. Original corpus files remain unchanged. Tests also
cover every proper prefix of a valid head, exact size/count boundaries, missing
and malformed lengths, uint64 overflow, OWS normalization, LF/obs-fold/control
rejection, body completeness, extra bytes and 10000 deterministic mutations.

A separate C++ oracle case verifies a non-UTF8 target. C++ permits arbitrary
non-control target bytes, while httparse represents its path as UTF-8. The
adapter validates the original target first, then uses an equal-length,
bounded head copy with high target bytes replaced for upstream syntax parsing
only when necessary. It returns the original target bytes and preserves all
framing offsets. This keeps the existing byte contract without adopting a
second HTTP parser or silently tightening URL acceptance.

## Bounded TCP and cumulative behavior

The loopback fixture uses four concurrent workers, reaps completed thread
handles, and returns 503 when connection admission is full. Read buffers and
frame sizes are bounded; each request has a 200ms absolute deadline, recalculated
after each read, and response writes have a timeout. Dribbled bytes do not reset
the deadline. A valid GET completes alongside the slow client, which receives
408. Duplicate headers, TE, excessive body declarations, extra bytes and EOF
before the declared body produce expected rejection responses. Subsequent
requests continue successfully. Response status, Content-Length, body and
Connection: close are parsed and checked. Observed peak workers is exactly four.

Both cumulative rename and link/unlink cases repeat the E1/E2/E3 batteries.
Their TCP POST decodes strict typed JSON and commits a local SQLite transaction
before returning 201. A hostile null payload returns 400 and creates no row;
reopening the database confirms exactly the accepted source/destination pair.
SQLite retains WAL/FULL and foreign-key configuration. This verifies interaction
among the qualified packages rather than merely linking them together.

## Limits and next work

The completed run is `20261013T084531Z-415f4830`, using build
`20261013T084039Z-b1202a48` after verifying its archived sources against the
current experiment, both corpora and C++ references. Evidence retains the
lockfile, selected graph, compiler/macro commands, CPU symbols, ELF imports,
toolchain/runtime inventory, corpus/oracle outcomes, artifact/archive hashes
and runtime logs. Ignored results retain binaries and source/vendor archives.
The preliminary scalar comparisons are superseded by this verified result.

The fixture is an experiment, not the production event loop, complete router,
or final response/error contract. Later migration work still covers complete
socket lifecycle, connection exhaustion, sustained load, response schema,
shutdown and differential fuzzing. Extra-byte tests cover bytes received with
the first frame; late pipelining is closed rather than serviced. A 200ms fixture
deadline is not a production configuration decision.

Execution uses WSL2 kernel 6.18.33.2-microsoft-standard-WSL2 and its CPU. Running
the SWAR comparison exercises the fallback implementation, but does not emulate
a CPU missing advanced instructions or prove old-kernel execution. The user's
own builder remains unqualified. No real SLES host or NFS server is required;
the [NFS fixture note](NFS-TEST-FIXTURE.md) remains available for later tests.
E5 (`signal-hook`) is next.
