# Delivery Metrics — AI-Assisted Development

**Prepared for:** engineering management
**Subject:** measured output and effort for the C++/REST migration of
Background File Mover, developed using Claude Code
**Period:** 2026-08-01 to 2026-08-02
**Status:** v1.0.0 in progress

---

## 1. Headline figures

| Metric | Value |
|---|---:|
| Engineering heads | **1** |
| Working sessions | **3** |
| **Measured active engineering time** | **7.1 hours** *(lower bound — see §5)* |
| Elapsed calendar time | 21.7 hours |
| Commits | 24 |
| Total lines produced | **9,620** |
| Test assertions passing | **6,393** |
| Line coverage (delivered components) | **98.1%** |

Active time is derived from commit timestamps clustered into sessions, not
from elapsed calendar time. Days with no work contribute nothing.

---

## 2. Output by category

| Category | Lines |
|---|---:|
| Production C++ (`src/`, `include/`) | 1,663 |
| C++ test suites | 1,349 |
| Fuzzing harness, corpus generator, tooling scripts | 271 |
| Build system and CI workflows | 620 |
| **Subtotal — code and build** | **3,903** |
| Requirements (L1 / L2 / L3) | 2,861 |
| Architecture decision records (12) | 950 |
| Architecture, security, process documentation | 1,906 |
| **Subtotal — specification and documentation** | **5,717** |
| **Total** | **9,620** |

Note the ratio: **59% of output is specification, not code.** That is
deliberate for a system with full requirements traceability, and it is the
part of the work that conventionally consumes the most senior engineering
time.

---

## 3. Engineering artifacts delivered

| Artifact | Count |
|---|---:|
| Requirements written and traced (L1 → L2 → L3) | **280** |
| Architecture decision records | 12 |
| Independent CI quality gates | 10 |
| Toolchains verified against | 3 |
| Fuzz executions (per run, zero crashes) | 3.8 million |

The ten CI gates are: functional build, AddressSanitizer + UndefinedBehavior +
LeakSanitizer, ThreadSanitizer, Valgrind, cppcheck, clang-tidy, GCC 4.8.5
deployment-target fidelity, coverage, CodeQL, and SonarCloud — plus
coverage-guided fuzzing with a retained regression corpus.

---

## 4. Defects prevented, with evidence

Each of these is verifiable in the commit history. They are listed because
defect prevention is the metric that matters most for a system whose failure
mode is losing customer data.

| Finding | Consequence had it shipped |
|---|---|
| **btrfs misclassified as a network filesystem** | Service would refuse to start on a valid local volume |
| **CI reported "all gates passed" while analysing nothing** | An empty compilation database made the static analyzer skip every file and exit zero |
| **Static-analysis job silently stopped covering new files** | A hardcoded file list was never updated; the gate stayed green while checking less of the codebase |
| **A "clean" analyzer report that was not clean** | An output filter discarded every real finding; three defects were reported as zero |
| **Two contradictions between our own requirements** | A parent requirement contradicted its own child; both were marked active |
| **Configuration file was executable** | A free-text command field would have granted code execution to anyone able to edit the config |

Four of the six are **failures of the quality gates themselves** — cases where
the tooling reported success without doing its job. These are the hardest
class of defect to find, because nothing appears wrong.

---

## 5. Methodology and its limits

**How active time was measured.** Commit timestamps were clustered into
sessions with a 90-minute idle threshold; each session's span is
first-commit to last-commit. The three sessions were 5.71 h, unmeasurable, and
1.35 h.

**This figure is a lower bound, and understates real effort.** Specifically:

* Work before a session's first commit is invisible — analysis, reading, and
  design that precedes the first commit is not counted.
* One session produced a single commit, so its span is zero by this method
  despite representing real work.
* Realistic active effort is therefore **higher than 7.1 hours** — plausibly
  9–12 — and the figure should be quoted as a floor, not a measurement.

**What is not attributable to this effort.** Milestone design material was
produced in separate AI sessions outside this repository and delivered as
snapshots. Work here consisted of evaluating that material against the
project's architecture, integrating what fit, and rejecting what did not —
**five of seven milestone deliveries were substantially rejected** on
architectural grounds. The analysis is real engineering work, but the report
should not claim origination of designs that arrived from elsewhere.

**Conventional-effort comparison.** The calculation below is an estimate, not
a measurement. Rates are stated so the arithmetic can be checked and the rates
substituted.

| Work product | Volume | Rate assumed | Engineer-days |
|---|---:|---|---:|
| Code, tests, build, CI | 3,903 lines | 50–150 SLOC/day | 26–78 |
| Requirements written and traced | 280 requirements | 15–25/day | 11–19 |
| Architecture decision records | 12 records | 1–2 days each | 12–24 |
| Architecture and process documentation | 1,906 lines | 300–500 lines/day | 4–6 |
| **Total** | | | **53–127** |

At a 5-day week that is **11 to 25 engineer-weeks** — roughly **three to six
months for one engineer**, or six to twelve weeks for a team of two.

Notes on the rates, since they carry the whole result:

* **50–150 SLOC/day** is a conventional range for systems C++ delivered to a
  finished standard — designed, reviewed, tested, and traced — not lines typed.
  High-assurance work is often quoted lower still (10–50). The low end of the
  range is used here rather than the lowest defensible figure.
* **Requirements at 15–25/day** assumes adaptation rather than origination.
  Each requirement needs a parent, a verification method, and consistency
  checking against the other 279. Originating them from scratch would be
  slower.
* **ADRs at 1–2 days each** reflects that each records options considered and
  rejected, which is the part that takes the time. Several here also required
  empirical work — the toolchain compatibility ADR involved building and
  running four library versions against the deployment compiler.

**Against a measured floor of 7.1 hours of active time** (§5), and a realistic
9–12 hours, the comparison is between roughly **one working day and roughly
three to six months of one engineer**.

That ratio is large enough to warrant scepticism, so the honest qualifications:

* The 7.1 hours is a floor and the conventional figure is an estimate. The two
  are not measured the same way.
* A substantial part of the specification output adapts design material
  produced in separate AI sessions. A human team would not have had that input
  either — but neither did this work originate all of it.
* Volume is not the same as value. §6 argues this point against the figures
  above.
* The comparison assumes producing **the same artifacts to the same standard**:
  280 traced requirements, 12 decision records, ten CI gates, fuzzing with a
  retained corpus. A team asked only for working code would finish far sooner
  and deliver something different.

---

## 6. Honest limitations

A report that only lists successes should not be trusted, so:

**Errors were introduced as well as caught.** Of the six findings in §4, two
were defects *created* during this work and caught before shipping — the
btrfs misclassification and one of the requirement contradictions. A
configuration "fix" was also applied that turned out to be inert, and was
discovered only when re-tested. The process caught them; it did not prevent
them.

**Output volume is not value.** 9,620 lines includes documentation that a
smaller project would not need. The requirements traceability and decision
records exist because this system has accreditation obligations; they should
not be counted as productivity in a context that does not require them.

**The security architecture is specified ahead of implementation.** Roughly 30
requirements currently describe controls that are designed but not built.
That was a deliberate sequencing choice — designing the filesystem layer
against a threat model rather than retrofitting it — but it means a portion of
the requirements output is not yet verified by tests.

**Single-operator measurement.** These figures reflect one engineer on one
project. They are not a basis for organization-wide projection without
comparable measurement elsewhere.

---

## 7. Where the leverage actually came from

The measurable throughput is real, but in this project the more consequential
benefits were qualitative:

**Fast empirical answers to questions that would otherwise be argued.** A
library-compatibility question that had been an open risk for the whole
project was settled definitively in minutes by building and running the
candidate against the actual deployment toolchain in a container — including
testing four historical versions — rather than by reading documentation and
estimating.

**Consistency of scrutiny.** Every inherited design was checked against the
same written invariants, which is how two contradictions between our own
requirements surfaced. That kind of cross-checking is exactly what erodes
first under schedule pressure.

**Written rationale as a by-product.** Twelve decision records exist, each
recording what was rejected and why. That documentation is normally the first
thing dropped and the first thing wanted at an audit.

---

## Appendix — reproducing these figures

All figures are derived from the repository and can be recomputed:

* Session clustering — `git log --format=%at` over the migration commit range,
  grouped with a 90-minute idle threshold.
* Line counts — `wc -l` over the relevant directories.
* Assertions and coverage — the CI test and coverage jobs.
* Defect evidence — the commit messages, each of which records the finding and
  its cause.
