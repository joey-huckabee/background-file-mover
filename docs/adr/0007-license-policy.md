---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: ADR-0004 (vendored pinned single-header policy)
---

# License policy for vendored and linked dependencies

## Context and Problem Statement

The project is licensed Apache-2.0. ADR-0004 permits vendoring pinned
single-header libraries, but did not state which licenses are acceptable.
Without a written policy, each vendoring decision reopens the question and
a rejection can arrive late — as it did for picojson, after it had been
pinned, integrated, and tested.

## Decision Drivers

* Vendoring decisions should be mechanical, not re-litigated per library
* A rejection must be discoverable *before* integration work begins
* The policy must cover test-only and build-only dependencies, not just
  shipped code

## Decision Outcome

**BSD-2-Clause is excluded.** No dependency under BSD-2-Clause may be
vendored, linked, or otherwise incorporated, in shipped or test-only code.

All other permissive licenses remain acceptable, specifically including:

| License | Status | In use |
|---|---|---|
| MIT | Allowed | cpp-httplib (pending, ADR-0004) |
| Apache-2.0 | Allowed | this project |
| BSL-1.0 | Allowed | Catch2 v2.13.10 |
| Public domain / Unlicense / CC0 | Allowed | — |
| BSD-2-Clause | **Excluded** | — (picojson removed, ADR-0006) |
| BSD-3-Clause | **Excluded** | — |
| Any copyleft (GPL / LGPL / AGPL / MPL) | Excluded | — |

> **Rationale.** The BSD exclusions are an **internal organizational policy**
> constraint, not a legal-compatibility finding. BSD-2-Clause and
> BSD-3-Clause are permissive licenses imposing only notice retention (plus,
> for BSD-3, non-endorsement), and both are compatible with Apache-2.0
> distribution. The exclusion does not derive from any conflict with this
> project's license.
>
> This is recorded explicitly so that a future maintainer who checks the
> compatibility question, finds no conflict, and concludes the entry is an
> error does **not** reverse it. It is not an error. The constraint is
> policy, and policy is the authority here — reversing it requires a policy
> change, not a licensing argument.

### Consequences

* Good: vendoring decisions are now a table lookup.
* Good: applies to test-only dependencies too, so a policy break cannot
  enter through the test tree.
* Bad: cost the picojson integration (ADR-0006) and roughly 300–500 lines
  of replacement parser plus its test suite.
* Bad: narrows the JSON library field to RapidJSON and json11, neither of
  which was compelling — which is what forced the project-owned parser.
* Neutral: Catch2 (BSL-1.0) and cpp-httplib (MIT) are unaffected.

## Notes

BSD-3-Clause is deliberately left undecided rather than assumed. It differs
from BSD-2-Clause only by the non-endorsement clause; if the driver for the
BSD-2 exclusion also covers BSD-3, this table should be updated before the
next vendoring decision rather than during one.
