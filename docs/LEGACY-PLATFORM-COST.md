# Cost of the Legacy Platform Target

**Prepared for:** engineering management
**Subject:** components this project must build in-house because the deployment
target is SUSE Linux Enterprise Server 12 SP5
**Status:** current as of the v1.0.0 C++ implementation in progress

---

## Summary

Background File Mover must run on **SLES 12 SP5**, whose system compiler is
**GCC 4.8.5** (released 2015) with **glibc 2.22** and a 4.12 kernel.

That constraint has forced the project to write, test, and maintain
**components that would otherwise be off-the-shelf**. Three widely-used
open-source libraries were evaluated and rejected. In every case the library
itself was standards-conformant; **the toolchain was the problem.**

| | Lines | Status |
|---|---:|---|
| JSON parser + tests + fuzz harness + seed generator | **1,148** | Delivered, fully tested |
| HTTP request-head parser + tests + fuzz harness + seeds + locale gate | **1,059** | Delivered, fully tested |
| **Delivered, attributable to the platform** | **2,207** | |
| Projected: HTTP routing and socket server | **~600** | Designed, not yet built |
| **Projected total** | **~2,800** | |

These are lines of security-sensitive, network-facing parsing code that a
modern toolchain would have let us consume as a dependency instead.

**The HTTP figure is now measured, not projected.** The request-head parser
shipped and the earlier estimate held: 1,059 lines against ~1,170 projected for
the parsing half. What remains projected is the routing and socket-server
layer, deferred until the job manager exists.

The delivered code is not merely written but carried to the standard the rest
of the project is held to: **100% line coverage on the HTTP parser** and 99% on
the JSON parser, both continuously fuzzed with committed regression corpora,
both verified on GCC 4.8.5 itself rather than only on a modern compiler, and
both governed by a written standard for hand-rolled components
(`docs/HAND-ROLLED-COMPONENTS.md`). That is the honest cost to report — not
"we wrote a parser," but **"we permanently own a network-facing parser and its
entire verification apparatus."** The maintenance liability, not the line
count, is the number that matters at renewal time.

---

## What was rejected, and why

### 1. JSON parsing — two libraries rejected

**nlohmann/json** — the de-facto standard C++ JSON library. Upstream
**explicitly refuses** GCC 4.8 support, citing compiler defects (GCC bugs
55817 and 57824). Its version gate errors out below GCC 4.9, and community
patches to restore 4.8 compatibility were closed as won't-fix.

**picojson** — the fallback, technically viable on 4.8. Rejected for a
non-technical reason: it is BSD-2-Clause, excluded by internal license policy.

**Result:** a project-owned JSON parser — 525 lines of implementation plus 340
lines of tests and an 88-line fuzzing harness.

### 2. HTTP server — one library rejected

**cpp-httplib** — the standard single-header C++ HTTP server. It routes
requests using `std::regex`, and **libstdc++ did not implement `<regex>` until
GCC 4.9**. On 4.8 the code compiles cleanly and then throws at runtime.

This was verified directly rather than inferred:

```
GCC 4.8.5 :  std::regex("/api/jobs/([^/]+)")  ->  regex_error thrown
GCC 11    :  same pattern                     ->  matched correctly
```

Every published version behaves this way, and **older versions depend on
`std::regex` more heavily**, not less — so pinning an older release does not
help. The most recent release additionally fails to compile on 4.8.5 with 73
errors.

**Result:** a project-owned HTTP/1.1 subset server — approximately 1,170 lines
including tests.

---

## The pattern

All three rejections share a cause worth stating plainly for planning
purposes:

> The libraries were correct. GCC 4.8 claims C++11 conformance it does not
> deliver — `<regex>` is unimplemented, `std::get_time` is absent, and several
> compiler defects affect otherwise-valid code.

The practical consequence is that **"does this library support C++11?" is not
a sufficient question** on this platform. Each candidate must be built and
executed against the actual toolchain before it can be relied on, and a
library can pass compilation while failing at runtime.

---

## What this costs

**Direct engineering cost.** 2,207 lines delivered, ~2,800 projected, that
would otherwise have been three `#include` statements. That is development,
review, and test effort already spent or committed.

**Ongoing maintenance.** Upstream libraries receive security fixes from a
community. Ours do not. Every defect in this code is ours to find and fix, for
the life of the product.

**Risk concentration.** Both hand-written components sit directly on untrusted
input — the JSON parser handles request bodies, the HTTP parser handles raw
network bytes. These are historically the two highest-defect-risk components
in any network service, which is precisely why the project originally intended
to use established libraries for them.

**Mitigations in place.** Because that risk was understood, the code carries
controls a vendored dependency would not have needed:

* Coverage-guided fuzzing with retained regression corpora — two targets, 75
  committed seeds, 3.4 million executions per 90-second run, zero crashes to
  date
* A deliberately minimal accepted grammar — everything unnecessary is rejected
  rather than parsed
* Fourteen independent CI gates, including two compilers, AddressSanitizer +
  UndefinedBehavior + LeakSanitizer, ThreadSanitizer, Valgrind, two static
  analyzers, and a source gate proving the parsers never call locale-sensitive
  classification functions
* **100% line coverage on the HTTP parser, 99% on the JSON parser**
* A written standard these components are built to
  (`docs/HAND-ROLLED-COMPONENTS.md`), so the next one does not depend on
  remembering what made these two acceptable

---

## What would change if the platform changed

The constraint is the **stock SLES 12 toolchain**, not SLES 12 itself. Two
options exist, neither currently recommended without a business driver:

**Option A — SLES 12 SDK module (GCC 9).** SUSE ships a newer compiler as an
add-on module. This would make all three rejected libraries viable. The cost
is a deployment prerequisite: the SDK module must be installed and approved on
every target host, which on a locked-down accredited system is a non-trivial
approval rather than a package install. It also would not retroactively remove
code already written.

**Option B — a newer platform (SLES 15, RHEL 9).** Removes the constraint
entirely. Both are already supported deployment targets for this product; SLES
12 is the one that forces the compromise.

**Recommendation:** no change for v1.0.0. The work is largely done and the
resulting code is well-tested. But the cost should be **counted against SLES
12 in any future platform decision** — this is roughly two thousand lines of
security-sensitive code that exists only because of a 2015-era compiler, and
the next component we need may not be as tractable.

---

## Appendix — measurement basis

Line counts are actual `wc -l` figures from the repository, not estimates. The
HTTP figures are from the completed design pending integration. All
compatibility findings were reproduced in the `gcc:4.8` container that also
serves as the project's fidelity CI tier, so they are repeatable rather than
anecdotal.

Full technical detail is recorded in the project's architecture decision
records: **ADR-0001** (toolchain choice), **ADR-0004** (vendoring policy and
its two failures), **ADR-0006** (JSON parser), and **ADR-0012** (HTTP server,
including the reproduction steps).
