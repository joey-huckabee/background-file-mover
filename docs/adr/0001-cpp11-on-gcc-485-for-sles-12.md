---
status: accepted
date: 2026-08-01
decision-makers: Joey
supersedes: L1-SYS-009 as written for the Python implementation
---

# Implement background-file-mover in C++11 targeting GCC 4.8.5 on SLES 12

## Context and Problem Statement

The Python implementation (v0.4.2) requires Python 3.10+. SLES 12's default
is Python 3.4, 3.6 at best via a package, and **no 3.10 package exists in
the SLES 12 repositories**. This is why `docs/USER-GUIDE.md` classifies
SLES 12 as "⚠️ Not recommended" and `docs/DEPLOYMENT.md` carries a
source-build runbook as the only workable path.

SLES 12 SP5 is a required deployment target. A C++11 implementation
compiles against the platform's own system compiler (GCC 4.8.5) and ships
as a single binary with no interpreter to source-build, version-match, or
qualify — which converts SLES 12 from a constrained, discouraged target
into a first-class one.

> **Correction of record.** An earlier draft of this ADR cited a precedent
> of "background-file-mover (C++11 daemon on SLES 12 / GCC 4.8.5, 44
> L3-CPP requirements, 165 Catch2 tests)". No such implementation exists or
> ever existed; background-file-mover through v0.4.2 is Python. The
> toolchain cost described below is **not** already paid — it is new work,
> and the estimate should be read accordingly. The decision stands on the
> platform argument above, which does not depend on the phantom precedent.

## Decision Drivers

* SLES 12 SP5 must be a supported target, not a documented exception
* Zero runtime dependencies on the target host — no interpreter, no venv
* Deterministic, exhaustively testable core logic
* The REST control plane (ADR-0002) needs no language feature beyond C++11

## Considered Options

* **Remain on Python** — blocked: no 3.10 on SLES 12
* **Python 3.4 stdlib-only rewrite** — would forfeit the 3.10 features the
  current implementation is built on, and 3.4 is long out of support
* **C++11 on the system GCC 4.8.5** — compiles with what the platform ships
* **C++14/17 via the SLES 12 SP5 SDK module (gcc7/gcc9)** — reachable using
  `-static-libstdc++ -static-libgcc` while still targeting glibc 2.22

## Decision Outcome

Chosen option: **C++11 on GCC 4.8.5.**

C++17 is genuinely available via the SDK module and was not rejected as
impossible. It was rejected because it buys little here: the durability
guarantees require raw `open`/`fsync`/`renameat`/`linkat`, so
`std::filesystem` — C++17's headline feature for a file mover — is largely
unusable. What remains (`make_unique`, `optional`, structured bindings) is
ergonomic, not enabling. Against that, requiring the SDK module adds a
build-host prerequisite and an approval step on a locked-down target.

The cost of C++11 is accepted as ergonomic only.

### Consequences

* Good: single binary + config file + systemd unit; no interpreter risk.
* Good: SLES 12 SP5 becomes a first-class target rather than an exception.
* Bad: no C++14+ conveniences; all project code and every vendored header
  must be verified against 4.8.5 (enforced by the `gcc:4.8` CI job).
* Bad: GCC 4.8 cannot host libFuzzer, LSan, or full UBSan, so
  instrumentation runs only on the modern tier (ADR-0008). The mitigation
  is that the 4.8 job runs the **full test suite**, not just a compile.
* Risk: cpp-httplib is still unpinned pending a GCC 4.8.5 compile spike
  (ADR-0004). If no tag compiles, the options are hand-rolling the HTTP/1.1
  subset or revisiting this ADR in favour of the SDK-module toolchain.

## Verification

`gcc:4.8` is a *proxy* for the target, not the target: Debian glibc 2.19 vs
SUSE 2.22, no systemd, no NFS. It verifies C++11 conformance only.
Deployability is verified on real SLES 12 SP5 hardware via the runbook and
NFS qualification checklist in `docs/DEPLOYMENT.md`.
