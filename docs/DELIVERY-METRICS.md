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
| Working sessions | **5** |
| **Measured active engineering time** | **8.7 hours** *(lower bound — see §5)* |
| Elapsed calendar time | 30.7 hours |
| Commits | 29 |
| Total lines authored | **9,981** *(excludes vendored and generated files)* |
| Test assertions passing | **6,782** across 96 test cases |
| Line coverage, C++ components delivered | **97.4%** |

Active time is derived from commit timestamps clustered into sessions, not
from elapsed calendar time. Days with no work contribute nothing.

**Measurement point:** commit `fd466aa`, the close of the migration intake.
Figures exclude the vendored Catch2 header (~17,000 lines, third-party) and
the generated trace matrix (168 lines), because neither was authored here.

---

## 2. Output by category

| Category | Lines |
|---|---:|
| Production C++ (`src/`, `include/`) | 2,055 |
| C++ test suites | 1,807 |
| Fuzzing harnesses, corpus generators, verification scripts | 560 |
| Build system and CI workflows | 770 |
| **Subtotal — code and build** | **5,192** |
| Requirements (L1 / L2 / L3) | 1,524 |
| Architecture decision records (12) | 950 |
| Architecture, security, and process documentation | 1,558 |
| Contributor and repository documentation | 757 |
| **Subtotal — specification and documentation** | **4,789** |
| **Total** | **9,981** |

Not counted above: 75 committed fuzzing corpus seeds (byte-exact protocol
test vectors rather than lines of code), the vendored dependency, and the
generated trace matrix.

Note the ratio: **48% of output is specification, not code.** That is
deliberate for a system carrying full requirements traceability, and it is the
part of the work that conventionally consumes the most senior engineering
time. The proportion fell from 59% as implementation caught up with the
specification — the security architecture was deliberately specified ahead of
the code it governs (§6).

---

## 3. Engineering artifacts delivered

| Artifact | Count |
|---|---:|
| Requirements written and traced (L1 → L2 → L3) | **293** |
| Architecture decision records | 12 |
| Independent CI quality gates | 14 |
| Toolchains verified against | 3 |
| Coverage-guided fuzz targets | 2 |
| Fuzz executions (90-second run, zero crashes) | 3.4 million |

The fourteen gates: functional build; GCC 4.8.5 deployment-target fidelity
running the **full** suite, not a compile; AddressSanitizer + UndefinedBehavior
+ LeakSanitizer; ThreadSanitizer; Valgrind memcheck; vendored-file integrity by
SHA-256; locale-free parser verification; cppcheck; clang-tidy; fuzz corpus
replay; a 60-second live fuzz session per pull request; coverage; CodeQL; and
SonarCloud. A nightly fuzzing burn-in runs on top of these.

Three of the fourteen — vendored integrity, locale-free parsers, and the
compile-database assertion inside clang-tidy — exist because a gate was found
passing without doing its job. They are gates that check other gates, and §4
explains why that turned out to be necessary.

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
| **Line-ending normalization would have silently corrupted the protocol test corpus** | Repository policy rewrites CRLF to LF. The HTTP fuzzing seeds exist precisely to exercise CRLF framing, and the parser treats a bare-LF head as incomplete rather than invalid — so the corpus would have kept passing while testing something else entirely |
| **A security test that would have passed against the bug it tested for** | The locale-independence test used input containing no uppercase `I`, the exact character the hazard turns on. It asserted the property without exercising it |
| **The same test silently disabled itself in CI** | It depends on a locale that is not generated on the runners; the standard library reports that by returning null, which the test ignored and reported a pass |
| **A static-analysis gate was failing, unread** | clang-tidy had been red on the branch tip for at least one commit. The gate worked; nobody had read its output |
| **Vendored dependency shipped without its license text** | The Catch2 header directs the reader to an accompanying license file that did not exist in the repository. BSL-1.0 requires the text travel with the source |

Seven of the eleven are **failures of the quality apparatus itself** — gates
that reported success without doing their job, or tests that asserted a
property without exercising it. These are the hardest class of defect to find,
because nothing appears wrong: the build is green, the report says pass, and
the only symptom is an absence.

The pattern is worth naming for the engineering organization, because it
generalizes past this project: **a test that cannot fail is indistinguishable
from a test that passes.** Four of the findings above are instances of it. The
countermeasure adopted here is to prefer checks that fail closed, and to ask of
every test what happens when the mechanism it depends on is missing — recorded
as a standing rule in `docs/HAND-ROLLED-COMPONENTS.md` §5.1.

---

## 5. Methodology and its limits

**How active time was measured.** Commit timestamps were clustered into
sessions with a 90-minute idle threshold; each session's span is
first-commit to last-commit. The five sessions were 5.70 h, unmeasurable,
1.35 h, unmeasurable, and 1.60 h.

**This figure is a lower bound, and understates real effort.** Specifically:

* Work before a session's first commit is invisible — analysis, reading, and
  design that precedes the first commit is not counted.
* **Two of the five sessions produced a single commit each**, so their spans
  are zero by this method despite representing real work.
* Long verification runs are counted as active time whether or not they were
  attended, which pushes the other way. On this project those runs are
  substantial: the full local CI tier takes roughly fifteen minutes and was
  executed repeatedly.
* Realistic active effort is therefore **higher than 8.7 hours** — plausibly
  11–15 — and the figure should be quoted as a floor, not a measurement.

**What is not attributable to this effort.** Milestone design material was
produced in separate AI sessions outside this repository and delivered as
snapshots. Work here consisted of evaluating that material against the
project's architecture, integrating what fit, and rejecting what did not.
The final tally, now that the series is closed and recorded in
`docs/MIGRATION-PROVENANCE.md`: **eight snapshots of a complete twelve-milestone
service yielded one adopted component, two adopted helper functions, and
roughly twenty requirements.** Six of the eight were substantially or entirely
rejected on architectural grounds.

That is the honest shape of the work, and it cuts both ways. The report should
not claim origination of designs that arrived from elsewhere. But neither
should the low adoption rate be read as waste: deciding *not* to integrate a
working implementation — and writing down why, so it is not adopted by the next
reader on reflex — is the senior-engineering component of a migration, and it
is most of what these hours bought.

**Conventional-effort comparison.** The calculation below is an estimate, not
a measurement. Rates are stated so the arithmetic can be checked and the rates
substituted.

| Work product | Volume | Rate assumed | Engineer-days |
|---|---:|---|---:|
| Code, tests, build, CI | 5,192 lines | 50–150 SLOC/day | 35–104 |
| Requirements written and traced | 293 requirements | 15–25/day | 12–20 |
| Architecture decision records | 12 records | 1–2 days each | 12–24 |
| Architecture and process documentation | 2,315 lines | 300–500 lines/day | 5–8 |
| **Total** | | | **64–156** |

At a 5-day week that is **13 to 31 engineer-weeks** — roughly **three to seven
months for one engineer**, or seven to sixteen weeks for a team of two.

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

**Against a measured floor of 8.7 hours of active time** (§5), and a realistic
11–15 hours, the comparison is between roughly **one to two working days and
roughly three to seven months of one engineer**.

That ratio is large enough to warrant scepticism, so the honest qualifications:

* The 8.7 hours is a floor and the conventional figure is an estimate. The two
  are not measured the same way, and the comparison is indicative rather than
  like-for-like.
* A substantial part of the specification output adapts design material
  produced in separate AI sessions. A human team would not have had that input
  either — but neither did this work originate all of it.
* Volume is not the same as value. §6 argues this point against the figures
  above.
* The comparison assumes producing **the same artifacts to the same standard**:
  293 traced requirements, 12 decision records, fourteen CI gates, two fuzz
  targets with retained corpora. A team asked only for working code would
  finish far sooner and deliver something different.
* **The system is not finished.** These figures measure a v1.0.0 in progress
  with the durable store, job manager, transfer engine, HTTP server, and
  dashboard still to build. The conventional-effort comparison covers the work
  *done*, not a delivered product.

---

## 6. Honest limitations

A report that only lists successes should not be trusted, so:

**Errors were introduced as well as caught.** Of the eleven findings in §4,
**four were defects created during this work** and caught before shipping — the
btrfs misclassification, one of the requirement contradictions, and both
faults in the locale-independence test. A configuration "fix" was also applied
that turned out to be inert, and a repository-wide text substitution once
edited an identifier *inside* a vendored dependency, which passed every gate
except the checksum that was added afterwards. The process caught them; it did
not prevent them, and the gates that caught several of them exist only because
something got through first.

Worth stating plainly for anyone reading this as a case for the tooling: the
error rate here is not zero, and the errors are not trivial ones. What the
process provides is that they surface inside the same session rather than in
production — and that each one leaves behind a gate that closes its whole
class.

**Output volume is not value.** 9,981 lines includes documentation that a
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

**A durable record of what was refused.** Eight snapshots of a complete working
service were evaluated and mostly not adopted. `docs/MIGRATION-PROVENANCE.md`
records each rejection with its reason, which is the artifact that stops the
same material being adopted on its second pass by a reader with no way of
knowing it had already been examined. In a migration this is the deliverable
that ages best: the code that *was* integrated is visible in the tree, but the
code that was correctly left out is invisible unless someone wrote it down.

---

## Appendix — reproducing these figures

All figures are derived from the repository and can be recomputed:

* Session clustering — `git log --format=%at` over the migration commit range,
  grouped with a 90-minute idle threshold.
* Line counts — `wc -l` over the relevant directories.
* Assertions and coverage — the CI test and coverage jobs.
* Defect evidence — the commit messages, each of which records the finding and
  its cause.
