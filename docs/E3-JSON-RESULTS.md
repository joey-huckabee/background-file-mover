# JSON compatibility experiment results

**E3 passed on 2026-10-13 America/Chicago.** The std control, isolated JSON
probe, and cumulative JSON/SQLite/rustix probes (rename and link/unlink modes)
completed in pinned SLES 12 SP5 userspace with glibc 2.22. The retained record
is [E3-JSON-EVIDENCE.json](E3-JSON-EVIDENCE.json); the reproducible experiment
is [experiments/e3-json](../experiments/e3-json).

## Qualified configuration

| Component | Value |
|---|---|
| Rust/Cargo | 1.99.0 |
| Reference builder | cargo-zigbuild 0.23.4, Zig 0.16.0 |
| Target / CPU | x86_64-unknown-linux-gnu.2.22 / baseline x86-64 |
| serde | 1.0.229; defaults disabled; std, derive |
| serde_json | 1.0.154; defaults disabled; std |
| JSON target dependencies | serde_core 1.0.229, itoa 1.0.18, memchr 2.8.3, zmij 1.0.23 |
| Macro host dependencies | serde_derive 1.0.229, proc-macro2 1.0.107, quote 1.0.47, syn 3.0.9, unicode-ident 1.0.27 |
| Cumulative packages | E1 rusqlite 0.40.1/bundled SQLite 3.53.2; E2 rustix 1.1.5/linux_raw |
| Runtime | Pinned SLES 12 SP5, glibc-2.22-114.34.1 |
| Program identity | UID/GID 1000, LD_BIND_NOW=1, network disabled, capabilities dropped |

The [serde manifest](https://raw.githubusercontent.com/serde-rs/serde/master/serde/Cargo.toml)
and [serde_json manifest](https://raw.githubusercontent.com/serde-rs/json/master/Cargo.toml)
describe the feature choices; Cargo.lock and the recorded feature graph establish
the exact qualified resolution. No preserve_order, arbitrary_precision,
raw_value, float_roundtrip or unbounded_depth features were enabled.
The full workspace resolves 26 external packages, including host build tools
and conditional-platform entries, with MIT/Apache-compatible license choices.
The five macro packages compile for the builder host; retained rustc commands
confirm the procedural macro compilation has no target override. They impose
no shared-library dependency on the deployed service binaries.

## ELF and loading results

| Executable | Highest GLIBC import | Shared libraries |
|---|---|---|
| std control | GLIBC_2.18 | libc, libdl, libpthread |
| isolated serde JSON | GLIBC_2.18 | libc, libdl, libpthread |
| cumulative JSON/SQLite/rustix | GLIBC_2.18 | libc, libdl, libpthread, libm |

All binaries use `/lib64/ld-linux-x86-64.so.2`, have no RPATH/RUNPATH or
GLIBC_PRIVATE requirements, and pass `ldd -r` and eager runtime binding.
Copied executable SHA-256s match the inspected artifacts. JSON introduces
no new shared libraries; the cumulative libm dependency comes from SQLite.
All imports fit glibc 2.22. Six deliberate invalid ELF reports were rejected:
newer glibc, private glibc, wrong interpreter, extra shared library, RUNPATH,
and wrong architecture. The build log records baseline CPU flags for Rust
and the bundled SQLite C compiler wrapper.

## API policy and corpus results

Serde defaults do not implement the service's full ADR-0009 policy. The
experimental adapter uses a bounded DeserializeSeed/Visitor, checks duplicate
keys before accepting values, and rejects nulls and NULs. A small lexical
integer-policy guard rejects decimal/exponent spellings and signed overflow,
while retaining integer `-0`, which serde_json otherwise represents as f64.
Serde owns JSON syntax, UTF-8 and escaping. Typed requests add
`deny_unknown_fields` and missing/wrong-type checks.

The existing C++ parser was compiled and executed only on the build host as
an independent oracle. All 38 committed corpus files matched its outcomes:
12 accepted and 26 rejected. Filenames are not expected-result assertions:
`r-escaped-nul` actually contains an empty string and is accepted; `utf8-raw`
contains octal shell escapes and is rejected. The BOM and raw-NUL fixtures
also do not contain their apparent intended bytes. The original files remain
unchanged. Explicit tests separately reject actual BOM, raw/escaped NUL,
invalid UTF-8, lone surrogates, raw controls, nested/escaped duplicate keys,
trailing input, null, decimal/exponent forms and signed int64 overflow.

Additional checks passed at and above each existing default limit: depth 4
(root counts as 1, including scalar descendants), input 65536 bytes, decoded
string 4096 bytes (the same policy applies to keys), and 64 object members/array elements. A 10000-level
input rejects before descending beyond the limit. The input cap precedes
decoding; escaped-string scratch allocation is bounded by the input cap,
with the decoded token limit checked by the visitor. Typed serialization and
Unicode/control-character roundtrips passed. Each JSON run exercised 10000
deterministic corpus mutations without panic and serialized/reparsed every
accepted mutation. The entire battery repeated in both cumulative runs,
followed by real rustix operations and SQLite transactions/configuration tests.

## Evidence and remaining limits

The completed audit/runtime run is `20261013T074919Z-b5b50210`, reusing build
`20261013T074614Z-e14203ea` after verifying source archive contents against
current Rust, C++ oracle and corpus inputs. Evidence includes the lockfile,
enabled feature graph, host macro commands, ELF imports, image/toolchain
inventory, corpus hashes/oracle outcomes, artifact hashes and runtime output.
Ignored results retain source/vendor archives and the actual binaries.
The first run stopped on the incorrect filename-based corpus assumption;
its artifacts are not the qualified result.

This qualifies the pinned package/features and exercised APIs. It does not
port the application or replace later parser differential fuzzing, resource
profiling, response schema work and service integration. The container uses
WSL2 kernel 6.18.33.2-microsoft-standard-WSL2; old-kernel and old-CPU execution
remain unproven. The user's own builder still requires qualification.
The reusable [NFS fixture note](NFS-TEST-FIXTURE.md) is retained for filesystem
tests; E3 required no NFS server. E4 (httparse) is next.
