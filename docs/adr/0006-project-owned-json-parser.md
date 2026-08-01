---
status: accepted
date: 2026-08-01
decision-makers: Joey
supersedes: the picojson selection (previous ADR-0006); the nlohmann/json selection within ADR-0004
precedent: ADR-0004 (vendored pinned single-header policy — unchanged), ADR-0007 (license policy)
---

# Implement a project-owned JSON parser; vendor none

## Context and Problem Statement

The REST control plane needs to decode request bodies and encode responses.
Three vendoring candidates were evaluated and all are now unavailable:

* **nlohmann/json** — upstream refuses GCC 4.8 support (GCC C++11 defects
  55817 and 57824); the version gate errors out below GCC 4.9 and
  4.8-compatibility patches were closed wontfix (issues #211/#544, PR #212).
* **picojson v1.3.0** — technically suitable and previously pinned, but
  BSD-2-Clause is excluded by ADR-0007.
* **RapidJSON / json11** — licenses satisfy ADR-0007, but RapidJSON is
  multi-header with a large audit surface and json11 has weaker int64
  handling. Neither is compelling enough to justify the vendoring paperwork
  for a five-endpoint API.

## Decision Drivers

* Must compile on GCC 4.8.5 in C++11 mode with `-Wall -Wextra -Werror`
* License must satisfy ADR-0007
* The API surface is tiny: flat objects, string and integer members only
* The parser is the most security-exposed component in the daemon — it is
  the first code to touch untrusted network bytes

## Considered Options

* Vendor RapidJSON (MIT) — acceptable license, large audit surface
* Vendor json11 (MIT) — acceptable license, int64 concerns
* Implement a strict-subset parser owned by the project

## Decision Outcome

Chosen option: **a project-owned strict-subset JSON parser**, implemented
behind the existing `api_codec.hpp` boundary.

This is affordable specifically because the required grammar is small. The
parser implements the subset defined in ADR-0009 and rejects everything
else, including constructs that are valid RFC 8259 but unnecessary here
(floats, deep nesting, non-ASCII escapes beyond what the API needs).
A parser that accepts less has less to get wrong.

The `api_codec.hpp` interface is unchanged: it never exposed a vendored
type, so this is a single-translation-unit substitution. The L3-CPP-016
through L3-CPP-024 obligations were written against the codec contract
rather than against picojson and carry over verbatim.

### Consequences

* Good: no third-party code on the untrusted-input path; the entire parse
  surface is project-owned, auditable, and covered by our own tests.
* Good: removes the two `-Wno-maybe-uninitialized` per-object exemptions
  picojson required under modern GCC. `-Werror` is now unqualified.
* Good: L3-CPP-024 (whole-body consumption) becomes a *native property* of
  the parser rather than a compensating control around a vendored quirk.
* Bad: we own the vulnerability surface with no upstream scrutiny. This is
  mitigated by ADR-0008 (fuzzing) and the JSONTestSuite corpus, which are
  mandatory rather than optional for this component.
* Bad: roughly 300–500 lines of new code and its test suite, versus zero
  for a vendored header. Accepted as the cost of the license constraint.
* Neutral: the encode path was already project-owned and is unaffected.

## Verification

The parser is not considered complete until it passes, in CI:
the JSONTestSuite corpus at the strictness profile of ADR-0009, the
hostile-input suite, ASan/UBSan/LSan, Valgrind memcheck, and the fuzz
gate of ADR-0008.
