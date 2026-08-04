# Vendored Libraries (ADR-0004)

Rules: files under `third_party/` are never edited. Unavoidable changes are
committed as `.patch` files applied at build time. Every entry records
upstream URL, pinned tag, SHA-256, and license.

All vendored licenses must satisfy the license policy in ADR-0007.

| Library | Pinned tag | File | SHA-256 | License | Status |
|---|---|---|---|---|---|
| Catch2 (v2 line) | v2.13.10 | `third_party/catch2/catch.hpp` | `3725c0f0a75f376a5005dde31ead0feb8f7da7507644c201b814443de8355170` | BSL-1.0 | vendored |
| Catch2 license text | v1.0 (BSL) | `third_party/catch2/LICENSE_1_0.txt` | `c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566` | BSL-1.0 | vendored |
| SQLite (amalgamation) | 3.53.4 (2026-07-24) | `third_party/sqlite/sqlite3.c` | `b1dd5d74ec7f29055a6684fa06fb3c2f6821c87dd38f9a458dfd2e8a1db28189` | Public domain | vendored |
| SQLite (amalgamation) | 3.53.4 (2026-07-24) | `third_party/sqlite/sqlite3.h` | `919e7f2e8ed1d8f56ac17b412b8971c76aa5d1a879752cc6058f75e7d5910e1d` | Public domain | vendored |

Upstream sources:
- Catch2: https://github.com/catchorg/Catch2 (release asset `catch.hpp`)
- Boost Software License 1.0: https://www.boost.org/LICENSE_1_0.txt
- SQLite: https://sqlite.org/download.html — `2026/sqlite-amalgamation-3530400.zip`,
  2946650 bytes, upstream SHA3-256
  `628a44cfe82c66aed1ccbbe85a562d2e33ebe64b3288981ed76285612227934e`

Only `sqlite3.c` and `sqlite3.h` are vendored. The zip also ships `shell.c` (the
`sqlite3` CLI) and `sqlite3ext.h` (the loadable-extension interface); neither is used,
and extensions are compiled out entirely — see the build flags below.

## Why the license text is a vendored file and not a note

`catch.hpp`'s own header says "Distributed under the Boost Software License,
Version 1.0. (See accompanying file `LICENSE_1_0.txt` ...)" — and for a while
no such accompanying file existed here. Recording *the name* of a license in
this table is inventory; BSL-1.0 requires that the copyright notice and the
full license text travel with every copy of the source, so a table entry does
not discharge the obligation. The text is therefore vendored like any other
third-party file, hash-pinned in the row above, and checked by
`make verify-vendored` — a missing license file now fails a gate rather than
being noticed during a release review, or not at all.

Note the carve-out that makes this obligation narrower than it first looks:
BSL-1.0 exempts copies "solely in the form of machine-executable object code."
Catch2 is test-only and is never linked into a shipped binary, so the
distributed artifact does not carry it. The obligation attaches to *this
repository*, which does distribute the source.

SQLite is the one vendored dependency that is not a single header and is too large to
audit line by line (~250 kLOC). ADR-0010 records why that is accepted: it is public
domain, it sees only codec-validated values rather than untrusted input, and it is
confined behind a repository interface (L2-JOB-009).

It is also the first dependency to occupy **two rows**. `scripts/verify-vendored.sh`
parses one path and one hash per row, so the `sqlite3.{c,h}` shorthand the pending row
used would have matched nothing and been silently skipped — the script only fails on a
row it *can* parse and finds wrong. Two rows, two hashes, two files checked.

### On SQLite 3.53.4 and GCC 4.8.5

Measured in the `gcc:4.8` container rather than inferred, following the precedent
ADR-0012 set for cpp-httplib: a portability claim about the deployment toolchain is
tested, not assumed.

The latest release was viable, so no version step-back was needed. `sqlite3.c` compiles
under GCC 4.8.5 at `-O2 -Wall`, links, and runs. The probe exercised what C1 actually
depends on rather than merely calling `sqlite3_libversion()`: `journal_mode=WAL`,
`synchronous=FULL`, and a `CHECK` constraint of the shape `L2-JOB-010` requires — which
both accepted a legal row and rejected `FAILED` with a null error.

The container reports **glibc 2.13**, older than the SLES 12 SP5 target's 2.22, so it is
a conservative floor: passing there implies passing on the target.

**`sqlite3.c` must not be compiled under this project's `-Werror`.** At `-O2 -Wall` GCC
4.8.5 emits three `-Wstrict-aliasing` warnings from `sqlite3Int64ToText` and
`sqlite3FpDecode`, where SQLite writes digit pairs through a `u16*` cast. The code is
deliberate and upstream is aware of it; the project's own translation units keep
`-Werror`, and the vendored unit is compiled by its own rule with
`-fno-strict-aliasing` instead. Suppressing the warning would be the wrong fix —
`-fno-strict-aliasing` changes what the optimizer is permitted to assume, which is the
actual requirement.

One diagnostic worth writing down because it wastes an afternoon otherwise: `ldd
--version` **segfaults** in the `gcc:4.8` image. It is a defect in that image's ancient
`ldd` shell script, has nothing to do with SQLite, and appears in build logs immediately
next to the compile step. Use `getconf GNU_LIBC_VERSION` to read the glibc version there.

## Removed

| Library | License | Removed | Reason |
|---|---|---|---|
| picojson v1.3.0 | BSD-2-Clause | 2026-08-01 | Excluded by ADR-0007; replaced by a project-owned parser (ADR-0006) |

## Rejected

| Library | License | Reason |
|---|---|---|
| nlohmann/json | MIT | Upstream refuses GCC 4.8 support (GCC bugs 55817/57824); version gate errors below GCC 4.9 |
| RapidJSON | MIT | Old-compiler friendly, but multi-header with a large audit surface |
| json11 | MIT | Small, but less battle-tested int64 handling |
| cpp-httplib | MIT | Routes with `std::regex`, which libstdc++ did not implement until GCC 4.9. **No tag is viable** — see ADR-0012 |

Note: the JSON libraries above were rejected on technical grounds *before*
ADR-0007 was written. Of them, only the licenses of RapidJSON and json11
would satisfy the current policy; both remain rejected for the reasons stated.

### On cpp-httplib specifically

Measured in the `gcc:4.8` container rather than inferred. Every tag from
v0.5.12 (2019, C++11-era) through 0.51.0 routes with `std::regex`; older tags
depend on it *more* (37 references versus 13). On GCC 4.8.5 a literal route
such as `/api/jobs` registers successfully, but a parameterised one —
`/api/jobs/([^/]+)`, which the API requires — throws `regex_error` at
runtime. The latest tag additionally fails to compile there, with 73 errors
including a missing `std::get_time`.

The failure is in the standard library, not the library, so **pinning an
older tag cannot fix it**. ADR-0012 records the full measurements.
