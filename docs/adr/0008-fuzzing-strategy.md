---
status: accepted
date: 2026-08-01
decision-makers: Joey
precedent: ADR-0006 (project-owned JSON parser), the existing Python no-panic
  fuzz harness (`tests/test_fuzz.py`, `.github/workflows/fuzz.yml`, L1-ROB-001)
---

# Coverage-guided fuzzing for the untrusted-input path

## Context and Problem Statement

ADR-0006 moves JSON parsing in-house, so the project now owns the code that
first touches untrusted network bytes with no upstream scrutiny behind it.
Example-based tests confirm the cases we thought of; they say nothing about
the cases we did not. The Python implementation already carries a no-panic
fuzz harness for L1-ROB-001, establishing the precedent — but it is a seeded
random-input loop, not coverage-guided, and it does not carry over to C++.

## Decision Drivers

* A JSON parser is close to an ideal fuzz target: `bytes -> struct`, no I/O,
  no threads, no clock, fully deterministic
* Memory-safety bugs in C++ are not caught by assertion-based tests
* Findings must not regress once fixed
* GCC 4.8.5 cannot host libFuzzer, ASan-with-leak-detection, or UBSan

## Considered Options

* **libFuzzer** — in-process, coverage-guided, trivial target function,
  composes directly with ASan/UBSan. Requires clang.
* **AFL++** — works with GCC, out-of-process, heavier harness and CI setup.
* **Honggfuzz** — comparable to AFL++, less common in CI.
* **Extend the existing seeded random-input loop** — no new tooling, but not
  coverage-guided, so it explores the input space far less efficiently.

## Decision Outcome

Chosen option: **libFuzzer with ASan+UBSan, on the modern-toolchain CI tier.**

The fuzz target is a ~10-line `LLVMFuzzerTestOneInput` that feeds the buffer
to `decode_submit_request` and discards the result. Because the source is
strictly C++11-conformant and compiled from a single body (ADR-0001), the
logic fuzzed on clang is the logic that ships on GCC 4.8.5, even though the
instrumentation cannot run there.

**Corpus discipline:**

* A **seed corpus** is committed, built from the JSONTestSuite files
  (MIT-licensed test *data*, not linked code — satisfies ADR-0007) plus
  valid request bodies.
* A **regression corpus** is committed. Every crash the fuzzer finds is
  minimized and added, which converts a one-time finding into a permanent
  test case. This is the part that carries the long-term value.

**CI gating**, mirroring the Python harness's fast-gate/deep-burn-in split:

| Tier | Trigger | Duration |
|---|---|---|
| Regression corpus replay | every PR | seconds — the corpus is run as ordinary unit tests |
| Fuzz gate | every PR | 60s, `-max_total_time=60` |
| Burn-in | nightly, alongside the existing 06:00 UTC Python job | long-running, `workflow_dispatch` override |

A crash at any tier fails the build.

### Consequences

* Good: the highest-risk component gets the detection method best suited to
  it, and findings become permanent regression tests.
* Good: reuses the existing burn-in schedule and mental model rather than
  introducing a second unfamiliar pattern.
* Bad: adds clang to the CI toolchain requirements alongside GCC.
* Bad: instrumentation never runs against the GCC 4.8.5 compilation, so a
  4.8-specific miscompile would not be caught by fuzzing. Mitigated by
  running the full functional suite on the 4.8 tier — that job must not be
  reduced to a compile check.
* Scope at the time of writing was the JSON parser, with the HTTP layer
  expected to become a second target "once cpp-httplib is pinned". That
  framing is obsolete: cpp-httplib was rejected and the HTTP parser is
  project-owned (ADR-0012), so it is not a candidate for fuzzing — it is a
  **requirement**. Every argument in this ADR for fuzzing the JSON parser
  applies to it with more force, since it sits one layer closer to the socket
  and parses a grammar with a documented history of smuggling and desync
  attacks.

  The config loader remains a lower-priority third target: its input is a file
  the service account controls, not bytes from the network.
