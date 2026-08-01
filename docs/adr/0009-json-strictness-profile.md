---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: ADR-0006 (project-owned JSON parser), ADR-0008 (fuzzing strategy)
---

# JSON strictness profile

## Context and Problem Statement

ADR-0006 commits to a project-owned strict-subset parser. "Strict subset"
has to mean something precise, or the parser's behavior is defined by its
implementation rather than by a decision — and parser-differential bugs are
exactly the class that hides security holes. RFC 8259 additionally leaves
several behaviors *explicitly undefined* (notably duplicate keys), so
conformance alone does not settle them.

## Decision Drivers

* Every accepted construct is attack surface; the API needs very little
* Undefined-behavior points in RFC 8259 must be decided here, not discovered
* Resource exhaustion (stack, heap) is the realistic DoS against a parser
* The profile must be testable as a rejection suite against JSONTestSuite

## Decision Outcome

### Accepted grammar

* Top-level value **must** be an object. Bare arrays, strings, numbers,
  `true`/`false`/`null` at top level are rejected.
* Member values may be: string, integer, boolean, or object/array within
  the depth limit. **Floating-point values are rejected outright** — the
  API has no float-typed field, and float parsing is a disproportionate
  share of the complexity and the CVE history.
* Integers are int64. Values outside int64 range are rejected rather than
  clamped or promoted.

### Rejection rules (all are errors, never warnings or coercions)

**Structural**
* Non-whitespace bytes after the top-level value (whole-input consumption)
* **Duplicate keys** — RFC 8259 leaves this undefined; we reject. This is
  the classic parser-differential auth-bypass vector.
* Unknown members, missing required members, wrong value types
* Trailing commas, comments, unquoted keys, single-quoted strings
* A leading byte-order mark
* Empty or whitespace-only input

**Strings**
* Embedded NUL — the unicode escape for code point zero — which is a
  truncation bug anywhere a value reaches a C API
* Unescaped control characters U+0000..U+001F
* Lone surrogates (`\uD800` without a valid low pair)
* Invalid, overlong, or truncated UTF-8 sequences
* Malformed `\u` escapes and unrecognized escape characters

**Numbers**
* Leading zeros (`01`), leading `+`, bare `.5` or `5.`
* `NaN`, `Infinity`, `-Infinity`, hex, and any other non-standard extension
* Exponent notation (follows from rejecting floats)

### Resource limits

| Limit | Value | Rationale |
|---|---|---|
| Max nesting depth | 4 | Stack-exhaustion DoS is the realistic attack; the API needs depth 1 today, so 4 is headroom |
| Max input size | Config-driven, shared with the HTTP 413 cap (L1-013) | Single source of truth for body size |
| Max string length | Bounded | Prevents single-token memory amplification |
| Max member count | Bounded | Prevents many-small-tokens allocation amplification |

Depth is checked **before** descending, never after.

### Implementation constraints

* Recursive descent with an enforced depth counter, or an iterative parser
  with an explicit stack. Unbounded recursion is prohibited.
* `std::string` throughout, length-carrying. **Never** `c_str()` a parsed
  value into a C API — this is what makes embedded-NUL rejection a
  defense-in-depth measure rather than the only control.
* No naked `new`/`delete`; RAII only.
* No exception may escape the codec boundary. The contract is
  `bool` + human-readable error (L3-CPP-019), unchanged from ADR-0006.

### Consequences

* Good: the parser is defined by this document, so JSONTestSuite becomes a
  mechanical conformance exercise — mostly a rejection suite.
* Good: rejecting floats and depth>4 removes the two largest sources of
  parser complexity and historical CVEs.
* Bad: a future endpoint needing floats or deeper nesting requires amending
  this ADR, not just editing the parser. That friction is intentional.
* Neutral: strictness is invisible to well-formed clients. Every rule above
  rejects input the API would have rejected at the validation layer anyway —
  this moves the rejection earlier, to the cheapest possible point.
