# Standard for Hand-Rolled Components

Rules for any component this project must write in-house because no
acceptable dependency exists on the deployment toolchain.

`docs/LEGACY-PLATFORM-COST.md` explains why there are three such components.
This document says what they must satisfy. It applies to the JSON parser and
the HTTP parser today, and to anything the SLES 12 toolchain forces on us
later.

---

## Why the bar is higher here

A vendored library arrives with other people's bug reports already fixed. Ours
does not. Every defect in this code is ours to find, for the life of the
product — and both components sit directly on untrusted input.

So the standard is not "as good as we would write anyway." It is deliberately
stricter than the code around it, because the safety net a dependency would
have provided has to be replaced with something.

---

## 1. Separation of concerns

### 1.1 A pure core, with no I/O

The parsing or transformation logic is a **pure function of its inputs**: no
file access, no sockets, no clock, no global state. Anything requiring the
outside world lives in a thin adapter around it.

This is not stylistic. It is what makes the entire validation matrix testable
without a fixture, and it is why the JSON parser's several thousand rejection
assertions run in milliseconds and never touch a disk.

Established by `L3-CPP-040` (config), `L3-CPP-045` (rename template),
`L2-CORE-004` (clock-free core).

### 1.2 One header per layer

**A header may not span layers.** If a header forces a consumer to include
things it does not use, it is doing two jobs.

This has been violated twice by inherited material and rejected both times:

* M7 declared the journal event codec in `api_codec.hpp`, making the REST
  codec `#include "journal.hpp"` — a REST response and an on-disk record have
  different audiences and very different compatibility contracts.
* M9 put the pure HTTP parser, the route handlers, and the socket server in
  one `http.hpp` that includes `config.hpp` and `manager.hpp`. The parser
  needs none of them.

The rule: name the header for the layer, not the feature.
`rename_template.hpp` holds a pure function; the filesystem operation that
consumes it lives elsewhere and arrives later.

### 1.3 Confinement behind a boundary

A hand-rolled component is reached through **one interface**, and no other
translation unit includes its header.

Verified by inspection, and it is what made replacing picojson with a
project-owned parser a single-file change. `L3-CPP-032` states it for JSON;
the same obligation applies to each new component.

### 1.4 Dependencies point one way

The core depends on nothing. The adapter depends on the core. The application
depends on the adapter. Nothing depends upward — if the parser needs to know
about the job manager, the layering is wrong.

---

## 2. Test density

A hand-rolled component is not complete when it works. It is complete when the
ways it can be made to misbehave are enumerated and asserted.

### 2.1 Every requirement carries a tagged test

Each `L3-CPP-*` obligation is named in at least one test tag, so the trace
matrix shows coverage rather than assertion. Requirements verified by
inspection say so explicitly; silence is not acceptable.

### 2.2 Rejection suites, not acceptance suites

For a component defined by what it refuses, **most tests assert refusal**. The
JSON suite is ~80% rejection cases. Acceptance tests prove the happy path
works; rejection tests prove the component is what the specification says.

### 2.3 The five obligatory properties

Every parser of untrusted input asserts all five:

1. **Every proper prefix of valid input is rejected** — swept exhaustively,
   not sampled. Truncation is the commonest malformed input in production; a
   client that dies mid-request produces exactly this.
2. **Output is unmodified on failure.** Pre-poison the output with a sentinel
   and assert it survives. A caller reusing a struct must not mistake stale
   data for a parse result.
3. **Failure always carries a diagnosable reason.** An empty error string is
   its own defect and is asserted against centrally.
4. **Arbitrary byte input returns rather than terminates.** Deterministic
   pseudo-random input in the unit suite; coverage-guided fuzzing beyond it.
5. **Every resource is bounded** — depth, length, count, total size — and each
   bound has a test that trips it.

### 2.4 Fuzzing is mandatory, and its corpus is committed

Coverage-guided fuzzing for anything reading untrusted bytes (ADR-0008). Seed
corpus committed. **Every crash found is minimized and committed to a
regression corpus** replayed on every PR — a fuzzer finds a bug once, a corpus
prevents it forever.

### 2.5 Coverage floor

**95% line coverage** on hand-rolled components, reported per-file. Current
figures: `json.cpp` 99.1%, `api_codec.cpp` 95.7%, overall 98.1%.

Coverage is a floor, not a target. 100% coverage of a suite that only tests
acceptance proves very little.

---

## 3. Conformance

### 3.1 The accepted subset is written down before it is built

An ADR states exactly what the component accepts and refuses, including the
points where a standard leaves behavior undefined and we must choose. ADR-0009
does this for JSON — duplicate keys reject, floats reject, depth bounded —
and ADR-0012 for the HTTP subset.

Undefined-behavior points in a specification are where independent
implementations disagree, and disagreement between parsers is the mechanism
behind request smuggling and auth bypass. They get decided deliberately.

### 3.2 Third-party conformance corpora where they exist

Where an external suite exists, run it. JSONTestSuite for JSON. For a strict
subset it functions mainly as a **rejection** suite, which is the point.

### 3.3 Differential comparison where possible

Round-trip through our own encoder and decoder at minimum. Where a reference
implementation is available on a modern toolchain, compare against it — a
divergence is either a bug or a deliberate strictness decision, and either way
it needs to be named.

### 3.4 Strictness is a security control, not pedantry

Prefer rejecting to interpreting. A parser that accepts less has less to get
wrong, and every construct accepted is attack surface. Where the API needs
depth 1, permitting depth 4 is already generous.

---

## 4. Checklist

Before a hand-rolled component is considered done:

- [ ] Pure core with no I/O; adapters separate
- [ ] One header per layer; no consumer forced to include what it does not use
- [ ] Reachable through one interface; confinement verified by inspection
- [ ] Dependencies point one way only
- [ ] Accepted subset stated in an ADR, including undefined-behavior decisions
- [ ] Every `L3-CPP-*` obligation named in a test tag
- [ ] Rejection cases outnumber acceptance cases
- [ ] Prefix sweep: every proper prefix of valid input rejected
- [ ] Output-unmodified-on-failure asserted with a sentinel
- [ ] Non-empty error asserted on every rejection
- [ ] Arbitrary-bytes test returns rather than terminates
- [ ] Every resource bound has a test that trips it
- [ ] Fuzz target exists; seed corpus committed; regression corpus wired to CI
- [ ] ≥95% line coverage, reported per file
- [ ] Third-party conformance corpus run where one exists
- [ ] Clean on all gates: GCC 4.8.5, GCC 14, ASan/UBSan/LSan, TSan, Valgrind,
      cppcheck, clang-tidy

---

## 5. Applying this to the HTTP parser

The HTTP parser was the first component adopted under this standard. It is
`cpp/src/http_parser.cpp` / `include/filemover/http_parser.hpp`, tracing
`L3-CPP-046..052`. Three changes were required before it could land:

1. **Split the header** (§1.2). `http.hpp` became `http_parser.hpp` — pure,
   standard-library only. Routes and server follow when the job manager
   exists.
2. **Remove locale dependence.** `std::isalnum` and `std::tolower` are
   locale-sensitive; a parser on untrusted input must not change behavior
   because something in the process called `setlocale`. Replaced with explicit
   range checks, as the JSON parser uses.
3. **Renumber** the inherited `L3-CPP-079..092` into this repository's
   sequence, as `L3-CPP-046..052`.

A fourth change surfaced during the port that the review had not anticipated:
`content_length_for` used `strtoull`, which accepts leading whitespace and a
sign and reports overflow out-of-band through `errno`. It now accumulates
digits explicitly with an overflow guard, so the strict-digit rule is enforced
by the code rather than by checking the string first and trusting the
conversion afterwards.

It already satisfied the properties in §2.3 — the prefix sweep in particular —
and its strictness decisions (duplicate headers rejected, any
`Transfer-Encoding` refused, bytes past `Content-Length` refused) are the kind
§3.4 asks for. It has a fuzz target and committed corpus per §2.4
(`fuzz/fuzz_http.cpp`, 37 seeds).

### 5.1 What the locale property cost, and the general lesson

The locale rule is the one place where a test alone turned out not to be
enough, and it is worth recording why.

The obvious test sets `tr_TR.UTF-8` and re-parses. Turkish is the right choice:
`std::tolower('I')` there does not yield `'i'`, because the Turkish lowercase
of I is dotless `ı` and does not fit in a byte, so the call returns `'I'`
unchanged and a locale-sensitive parser would key `IF-MATCH` under `iF-mATCH`
and miss every lookup. Two things went wrong with it anyway:

- The first version parsed a fixture with **no capital `I` in any header
  name**, so it would have passed against a locale-sensitive parser. A test
  for a hazard has to actually contain the hazard.
- `setlocale` returns `NULL` when the locale is not generated, and it is not
  generated in any of our CI containers. The test silently degraded to running
  the `C` case twice and reporting a pass.

The fix is both halves: the fixture now carries `IF-MATCH`, the test `WARN`s
when the locale is unavailable instead of reporting a clean pass, and
`scripts/assert-locale-free.sh` greps the parser sources for `<cctype>` and the
`strtoul` family as a gate the environment cannot skip (`make locale-free`,
plus a CI job of the same name).

**Generalize this.** For any property in §2.3, ask what happens when the
mechanism the test depends on is missing. If the answer is "the test passes",
it is not a gate. Prefer checks that fail closed — and where the property is
"this code does not call X", grepping for X is a legitimate and cheap gate,
not a substitute for the test but a complement to it.

That gate earned its keep on its first run: `config.cpp`'s `parse_uint`
documented that it rejected `" 80"`, but checked only for a leading `-` or `+`
while `strtoul` skips whitespace. It was unreachable — the caller trims — but
the stated contract was false, and it now requires a leading digit.
