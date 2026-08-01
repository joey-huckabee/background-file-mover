# Vendored Libraries (ADR-0004)

Rules: files under `third_party/` are never edited. Unavoidable changes are
committed as `.patch` files applied at build time. Every entry records
upstream URL, pinned tag, SHA-256, and license.

All vendored licenses must satisfy the license policy in ADR-0007.

| Library | Pinned tag | File | SHA-256 | License | Status |
|---|---|---|---|---|---|
| Catch2 (v2 line) | v2.13.10 | `third_party/catch2/catch.hpp` | `3725c0f0a75f376a5005dde31ead0feb8f7da7507644c201b814443de8355170` | BSL-1.0 | vendored |
| cpp-httplib | TBD (older tag, pin after GCC 4.8.5 spike) | `third_party/httplib/httplib.h` | TBD | MIT | pending |

Upstream sources:
- Catch2: https://github.com/catchorg/Catch2 (release asset `catch.hpp`)
- cpp-httplib: https://github.com/yhirose/cpp-httplib

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

Note: the JSON libraries above were rejected on technical grounds *before*
ADR-0007 was written. Of them, only the licenses of RapidJSON and json11
would satisfy the current policy; both remain rejected for the reasons stated.
