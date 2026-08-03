---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: sqlite-attest (vendored/air-gapped dependency policy)
---

# Vendor pinned single-header libraries; never edit them in place

## Context and Problem Statement

The target host is air-gapped with no package manager access. The design
needs JSON, an HTTP server, and a test framework without hand-rolling the
two highest-defect-risk components (HTTP parsing, JSON parsing).

## Decision Drivers

* Air-gapped reproducible builds
* GCC 4.8.5 / C++11 compatibility of every vendored file
* Auditable provenance (URL, tag, hash, license)

## Considered Options

* Hand-roll HTTP parser and JSON parser
* System packages (unavailable/ancient on SLES 12)
* Vendored, pinned single-header libraries

## Decision Outcome

Chosen option: **vendored single-header libraries** under `third_party/`,
each recorded in `VENDORED.md` with upstream URL, pinned tag, SHA-256, and
license. Vendored files are never edited; unavoidable changes live as
`.patch` files applied at build time. Pinned set:

* Catch2 **v2.13.10** `catch.hpp` (v2 line: C++11/GCC 4.8 compatible;
  v3 requires C++14) — SHA-256 recorded in VENDORED.md. Vendored now.
* ~~nlohmann/json 3.x~~ — **superseded**. Excluded by upstream's refusal to
  support GCC 4.8; its replacement picojson was then excluded by ADR-0007.
  JSON is now project-owned — see ADR-0006.
* ~~cpp-httplib~~ — **superseded**. The GCC 4.8.5 spike ran and the answer is
  that no tag is viable: cpp-httplib routes with `std::regex`, and libstdc++
  did not implement `<regex>` until GCC 4.9. HTTP is now project-owned — see
  ADR-0012, which records the measurements.
* SQLite (amalgamation) — pinned at integration, for durable state (ADR-0010).

All vendoring is additionally subject to the license policy in ADR-0007.

### Consequences

* Good: provenance is auditable for accreditation.
* Good: the vendoring *discipline* — pin, hash, record provenance, never edit
  in place — applies to whatever is vendored and is unaffected by what was.
* Bad: upgrades are manual; characterization tests must pin the behaviors
  relied upon so a bumped tag fails loudly rather than silently.
* Bad: **this ADR's original premise is fully spent.** It was written to avoid
  hand-rolling "the two highest-defect-risk components (HTTP parsing, JSON
  parsing)". Both are now hand-rolled. JSON went first — no suitable library
  supports GCC 4.8, and the one that did is license-excluded (ADR-0006,
  ADR-0007). HTTP followed for the same structural reason (ADR-0012).

  This was recorded earlier as "half-spent" while the HTTP half was still
  open. It is no longer open. The ADR is retained because the discipline it
  defines still governs Catch2 and SQLite, but its stated motivation no longer
  describes what the project does.

### What the two failures had in common

Both candidates were C++11-conformant. Both were defeated by GCC 4.8's
*standard library* rather than by their own code — nlohmann by compiler
defects 55817/57824, cpp-httplib by an unimplemented `<regex>`.

Any future vendoring decision on this target should therefore ask **"does it
depend on a part of libstdc++ that GCC 4.8 actually implemented?"** rather
than "does it support C++11?", and answer it against the `gcc:4.8` container
rather than against the standard.
