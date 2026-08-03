---
status: accepted
date: 2026-08-02
decision-makers: Joey
supersedes: the cpp-httplib selection within ADR-0004
precedent: ADR-0002 (HTTP/1.1 subset), ADR-0006 (project-owned JSON parser)
---

# Hand-roll the HTTP/1.1 subset; cpp-httplib is not viable on GCC 4.8.5

## Context and Problem Statement

ADR-0004 provisionally named cpp-httplib as the HTTP server, pending a
GCC 4.8.5 compile spike. It was the last unresolved item in that ADR and the
one open risk against ADR-0001 — if no tag worked, the choices were
hand-rolling the subset or moving to a newer toolchain via the SLES 12 SP5 SDK
module.

The spike has run.

> **Numbering note.** The originating external design recorded this decision
> as its own "ADR-0007". That number is taken here by the license policy, so
> the decision is renumbered into this repository's sequence. Content is
> assessed on its merits, not inherited with its identifier.

## The spike, measured

cpp-httplib routes requests with `std::regex`. libstdc++ did not implement
`<regex>` until GCC 4.9; on 4.8 the headers exist and compile, and then throw
at runtime.

Verified directly in the `gcc:4.8` container against GCC 11 as a control:

```
GCC 4.8.5 :  std::regex("/api/jobs/([^/]+)")  ->  regex_error thrown
GCC 11    :  same pattern                     ->  MATCHED, capture[1] = job-000001
```

Every published tag routes this way. Older tags depend on it *more*:

| Tag | Size | `std::regex` refs | On GCC 4.8.5 |
|---|---|---|---|
| v0.5.12 (C++11 era) | 156 KB | 37 | compiles; **parameterised routes throw** |
| v0.7.18 | 226 KB | 33 | routes via regex |
| v0.11.4 | 281 KB | 34 | routes via regex |
| v0.14.3 | 308 KB | 26 | routes via regex |
| 0.51.0 (latest) | 732 KB | 13 | **73 compile errors** |

Latest fails to build on 4.8.5 for reasons unrelated to regex: `std::get_time`
absent from that libstdc++, defaulted move-constructor exception-specification
mismatches, and user-defined-literal spacing the 4.8 parser rejects.

**One correction to the received account.** It is not true that regex "throws
for essentially every pattern". A *literal* route such as `/api/jobs`
registers and works on 4.8.5. What throws is any pattern containing regex
syntax — which is every parameterised route. The API requires
`GET /api/jobs/{id}`, so the distinction offers no way out, but the precise
statement is that parameterised routing is unavailable rather than that regex
is wholly non-functional.

## Decision Drivers

* The failure is in the standard library, not in the library being pinned, so
  no tag selection can fix it
* A runtime `regex_error` is worse than a compile error: it ships
* The accepted grammar is already tiny (ADR-0002: GET/POST, `Content-Length`
  bodies, `Connection: close`, five endpoints)

## Considered Options

* **Pin an older cpp-httplib tag** — compiles, cannot route
* **Move to the SLES 12 SP5 SDK toolchain (gcc9)** to get a working `<regex>`
* **Hand-roll the HTTP/1.1 subset**

## Decision Outcome

Chosen option: **hand-roll the HTTP/1.1 subset.**

Pinning an older tag was rejected on the evidence above: it buys compilation
and loses routing.

Moving to gcc9 was rejected as disproportionate. It would resolve the regex
defect, but ADR-0001 chose 4.8.5 so the project builds with the stock SLES 12
toolchain and needs no SDK module approval on a locked-down target. Changing
that to obtain a library we can replace with ~600 lines under our own
requirement regime is the wrong trade — particularly when the same reasoning
already produced a JSON parser we are satisfied with (ADR-0006).

The subset is small enough to specify exhaustively, and the strictness posture
of ADR-0009 transfers directly: reject rather than interpret, cap everything,
and treat every rejection as a tested obligation.

### Consequences

* Good: no vendored code on the untrusted-input path at all. Both the JSON
  parser and the HTTP parser are project-owned, auditable, and covered by our
  own fuzzing (ADR-0008).
* Good: the last TBD in ADR-0004 is closed, and the open risk against ADR-0001
  is resolved without reopening the toolchain decision.
* Bad: ~600 lines of network-facing code we own, on the most hostile input
  surface in the system. This is only acceptable because the grammar is
  deliberately tiny and the fuzzing and hostile-input discipline already
  exists.
* Bad: no upstream security fixes to inherit. Ours to find.

## The pattern worth naming

This is the **second** vendoring candidate to die the same structural death.
nlohmann/json was excluded by GCC 4.8 compiler defects; cpp-httplib by GCC
4.8's unimplemented `<regex>`. In both cases the library was C++11-conformant
and the *toolchain* was the problem.

The lesson for any future vendoring decision on this target: "does it support
C++11?" is the wrong question. The right one is **"does it depend on a part of
libstdc++ that GCC 4.8 actually implemented?"** `<regex>`, `<thread>` edge
cases, `std::get_time`, and defaulted-function exception specifications are
all places where 4.8 claims conformance it does not deliver. Check against the
container, not against the standard.
