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
* cpp-httplib — tag to be pinned after a GCC 4.8.5 compile spike; recent
  releases require newer compilers, so an older tag is expected.

All vendoring is additionally subject to the license policy in ADR-0007.

### Consequences

* Good: provenance is auditable for accreditation.
* Good: reduces hand-rolled surface where a compliant library exists.
* Bad: upgrades are manual; characterization tests must pin the behaviors
  relied upon so a bumped tag fails loudly rather than silently.
* Bad: **this ADR's original premise did not survive.** It was written to
  avoid hand-rolling "the two highest-defect-risk components (HTTP parsing,
  JSON parsing)". JSON parsing is now hand-rolled anyway — first because no
  suitable library supports GCC 4.8, then because the one that did is
  license-excluded. Only the HTTP half of the premise remains, and it is
  contingent on the cpp-httplib spike succeeding. The vendoring *discipline*
  in this ADR stands on its own; the *motivation* is half-spent.
