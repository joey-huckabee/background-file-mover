# Delivery Metrics — AI-Assisted Development

**Prepared for:** engineering management
**Subject:** measured output and effort for the C++/REST migration of
Background File Mover, developed using Claude Code
**Period:** 2026-08-01 to 2026-08-05
**Status:** v1.0.0 in progress — milestones C1–C4 delivered, C4 not yet merged

---

## 1. Headline figures

| Metric | Value | Previous issue |
|---|---:|---:|
| Engineering heads | **1** | 1 |
| Working sessions | **13** | 6 |
| **Measured active engineering time** | **15.7 hours** *(lower bound — see §5)* | 8.8 h |
| Elapsed calendar time | 101.2 hours | 39.5 h |
| Commits | 62 | 31 |
| Total lines authored | **25,175** *(excludes vendored and generated files)* | 11,082 |
| Test assertions passing | **8,443** across 207 test cases | 6,800 / 97 |
| Line coverage, C++ components delivered | **87.6%** | 97.4% |
| Independent CI quality gates | **16** | 15 |
| **Requirements verified, in v1.0.0 scope** | **109 of 226 (48.2%)** | 48 / 226 (21.2%) |

Active time is derived from commit timestamps clustered into sessions, not
from elapsed calendar time. Days with no work contribute nothing.

**Measurement point:** commit `34b7384`, the tip of the `c4-job-manager`
branch. Figures exclude the vendored Catch2 header and SQLite amalgamation
(~270,000 lines combined, third-party) and the generated trace matrix, because
none of it was authored here.

**Two rows moved in opposite directions, and both are real.**

*Requirements verified* more than doubled, from 21.2% to 48.2%. Three milestones
landed in this period: the durable SQLite store (C2), the fd-relative filesystem
layer and move engine (C3), and the job manager and worker pool (C4). That is
the figure to quote when asked whether v1.0.0 is close, and it is the first
issue of this report where the answer is "about half way".

*Line coverage fell from 97.4% to 87.6%*, and that is not a regression in
discipline. The earlier figure covered a JSON parser, an HTTP head parser, and a
configuration loader — pure functions over in-memory input, where exhaustive
testing is cheap. It now also covers `store.cpp` (79.7%) and `mover.cpp` (77.6%),
whose uncovered lines are overwhelmingly I/O error paths: a failed `fsync`, a
`renameat2` returning `EXDEV`, a SQLite write refused mid-transaction. Those are
reachable only by injecting faults, and the project injects a deliberate subset
rather than all of them. The honest reading is that **coverage got harder to earn
as the code got closer to the disk**, and 87.6% against a gate of 85% is the
number to defend rather than explain away.

---

## 2. Output by category

| Category | Lines | Previous |
|---|---:|---:|
| Production C++ (`src/`, `include/`) | 5,494 | 2,055 |
| C++ test suites | 5,214 | 1,837 |
| Fuzzing harnesses, corpus generators, verification and traceability scripts | 1,894 | 712 |
| Build system, CI workflows, git hooks | 1,589 | 818 |
| **Subtotal — code and build** | **14,191** | 5,422 |
| Requirements (L1 / L2 / L3) | 3,038 | 1,547 |
| Architecture decision records (12) | 954 | 952 |
| Architecture, security, and process documentation | 5,367 | 1,906 |
| Contributor and repository documentation | 1,368 | 914 |
| **Subtotal — specification and documentation** | **10,727** | 5,319 |
| Repository configuration (editor, git attributes, formatter, linter) | 257 | 341 |
| **Total** | **25,175** | 11,082 |

Not counted above: 77 committed fuzzing corpus seeds (byte-exact protocol
test vectors rather than lines of code), the two vendored dependencies, and the
generated trace matrix.

**Test code now slightly exceeds production code** — 5,214 lines against 5,494.
That ratio is a consequence of what C2 through C4 added: a durable store and a
move engine whose correctness claims are about crash behaviour, so a large part
of the suite consists of kill-at-every-statement harnesses that fork, die at a
chosen point, reopen the database, and assert what survived. Those cost more
lines per assertion than testing a parser does.

**Deletions are not counted as output.** The most recent session removed 12,518
lines — the Python implementation, relocated to `main` and the `v0.4.2` tag —
and that figure appears nowhere in this table. Deciding what to delete and
proving nothing depended on it is real work, but it is not production, and a
report that counted it as such would be inflating.

Note the ratio: **43% of output is specification, not code.** That is
deliberate for a system carrying full requirements traceability, and it is the
part of the work that conventionally consumes the most senior engineering
time. The proportion has fallen steadily — 59%, then 48%, now 43% — as
implementation catches up with a specification that was deliberately written
ahead of the code it governs (§6). The absolute volume of specification is
still growing; code is simply growing faster.

---

## 3. Engineering artifacts delivered

| Artifact | Count | Previous |
|---|---:|---:|
| Requirements written and traced (L1 → L2 → L3) | **332** | 332 |
| Architecture decision records | 12 | 12 |
| Independent CI quality gates | **16** | 15 |
| Toolchains verified against | 3 | 3 |
| Coverage-guided fuzz targets | 2 | 2 |
| Fuzz executions (90-second run, zero crashes) | 3.4 million *(carried forward, not re-measured)* | 3.4 million |

The requirement count is unchanged, which is the point: C2 through C4 built
what was already specified rather than discovering new obligations mid-flight.
Verification against those requirements rose from 21.2% to 48.2%.

The sixteen gates: functional build; GCC 4.8.5 deployment-target fidelity
running the **full** suite, not a compile; AddressSanitizer + UndefinedBehavior
+ LeakSanitizer; ThreadSanitizer; Valgrind memcheck; vendored-file integrity by
SHA-256; locale-free parser verification; SQL confinement; fd-relative
filesystem access; no-shell-invocation; strong-hash-only; no permission-based
test failures; clang-tidy; fuzz corpus replay; coverage against a floor; and the
requirements trace matrix. CodeQL, SonarCloud, and a nightly fuzzing burn-in run
on top of these.

**Six of the sixteen exist because a gate was found passing without doing its
job** — vendored integrity, locale-free parsers, the compile-database assertion
inside clang-tidy, the hook-mode check, the header-dependency tracking that
turned out to be absent entirely, and the newest: a gate that bans tests which
force a failure by removing write permission, because the deployment-fidelity
container runs as root and ignores permission bits. They are gates that check
other gates, and §4 explains why that keeps turning out to be necessary.

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
| **Traceability was blind to the C++ tests** | The matrix generator read only Python test markers, so 49 tagged C++ tests traced to nothing. Removing the Python implementation without fixing this first would have taken reported coverage to zero and hidden the real figure behind an obvious artifact |
| **A requirement was implemented but unverified** | The JSON parser reports the byte offset of every rejection and nothing asserted it. Half the requirement was covered incidentally by a test helper, which is what made the gap invisible |
| **A requirement demanded a test that cannot exist** | "Compiles clean under `-Werror` on GCC 4.8.5" was marked verification-by-Test. It is gated on every commit by the fidelity tier, but no assertion can express it, so it read as a permanent hole against something already enforced |
| **Removing Python would have silently dropped a CI gate** | The requirements trace-matrix check lived in the Python workflow. Deleting that workflow would have removed the only automated defence against requirements drifting from tests |

### Added this period (milestones C2–C4)

| Finding | Consequence had it shipped |
|---|---|
| **The build system had no header dependency tracking at all** | `make` rebuilt an object only when its `.cpp` was newer, so every incremental build since the project began was unsound across a header change. Adding a declaration survived it; changing a struct's *layout* did not. Growing `Config` by twelve bytes left a stale test object at the old size, so the test placed a small `Config` on its stack and the loader assigned the large one over it — surfacing as `*** stack smashing detected ***` in a test untouched for three milestones. An ODR violation manufactured by the build system |
| **A failed move marked the job permanently unretryable** | The move engine wrote `FAILED` when the commit rename failed. `FAILED` is terminal in the state machine, so neither automatic backoff nor operator-initiated retry could ever return that job to work. Every transient failure — a full disk, a momentarily unwritable destination — would have become a permanent loss requiring manual re-submission |
| **A whole class of failure fell through the job manager** | Jobs refused before anything happened were neither retried nor failed. They stayed `QUEUED` forever with no worker owning them, indefinitely occupying the queue and reading as pending work |
| **The vendored SQLite checksum could never have been verified** | The integrity manifest recorded the two files with a brace shorthand the verifier cannot parse. It skipped the row silently, so the gate protecting 250,000 lines of vendored C reported success while checking nothing |
| **The deployment-target CI tier was not running at all** | The `gcc:4.8` image is published with a Docker manifest schema that the CI runner has disabled, so the job exited 125. The local container engine still accepted that schema, which is precisely why it went unnoticed — it worked on the machine where anyone would have checked |
| **Coverage was never reaching the analysis platform** | `gcov` emits source paths relative to `cpp/`; the scanner resolved them from the repository root and silently matched nothing. The dashboard reported no coverage data rather than an error |
| **The sanitizer tier was missing its runtime libraries** | A `--no-install-recommends` in the CI image dropped the clang sanitizer runtimes, breaking only the fuzz tier. The first attempted verification of the fix checked a path that does not exist on that distribution and appeared to confirm it |
| **A security test passed for the wrong reason** | The symlink-swap test unlinked and recreated the target, which returned the same inode — so the identity check it was meant to defeat matched by coincidence. It now renames a prepared file over the original and asserts the inodes differ before proceeding |
| **The pre-commit hook had never run** | Two independent faults: `core.hooksPath` was unset and the file was not executable. Its size limit would also have rejected the vendored SQLite amalgamation the moment it did run |
| **The hook-mode gate was inspecting the wrong thing** | Written after the above to prevent recurrence, it checked the *index* rather than the file git executes. When an editing path cleared the working-tree execute bit a third time, the gate reported all hooks healthy while the hook was dead |
| **Retry tests asserted nothing where it mattered most** | They forced a failure by making a directory read-only. Root bypasses that check, and the deployment-fidelity container runs as root — so on the one tier that models the production platform, the move succeeded and six assertions tested the opposite path from the one they named |
| **A link error reachable only on the deployment target** | `clock_gettime` resides in `librt` on the target's glibc and in `libc` on newer ones. The build succeeded on three modern toolchains and every sanitizer tier, and failed only on GCC 4.8.5 |
| **Two idempotency defects in crash recovery** | The kill-after-every-phase suite found the move engine re-issuing state transitions the store correctly refused. Idempotence had been reasoned about for the filesystem and not for the state machine |

Nineteen of the twenty-eight findings are **failures of the quality apparatus
itself** — gates that reported success without doing their job, tests that
asserted a property without exercising it, or checks that would have
disappeared unnoticed. These are the hardest class of defect to find, because
nothing appears wrong: the build is green, the report says pass, and the only
symptom is an absence.

The proportion holds steady at roughly two thirds, and that is worth stating
plainly: as the apparatus grows, so does the share of what can go wrong that
*is* the apparatus. Nine of the thirteen findings added this period are of that
kind. The remaining four — the unretryable-`FAILED` defect, the job-manager
fall-through, the missing `-lrt`, and the two crash-recovery idempotency bugs —
are ordinary product defects of the sort any project produces.

The pattern is worth naming for the engineering organization, because it
generalizes past this project: **a test that cannot fail is indistinguishable
from a test that passes.** Six of the findings above are instances of it. The
countermeasure adopted here is to prefer checks that fail closed, and to ask of
every test what happens when the mechanism it depends on is missing — recorded
as a standing rule in `docs/HAND-ROLLED-COMPONENTS.md` §5.1.

---

## 5. Methodology and its limits

**Corrections to earlier issues of this report.** Two figures were wrong in the
first issue and were restated in the second: the requirement count read 293,
omitting 39 non-`L3-CPP` requirements (true total 332), and the gate count read
14 rather than 15. Both are carried forward correctly here. No figure from the
second issue has been found wrong, but see the note on coverage in §1 — that row
fell by ten points for reasons that are not a decline in rigour, and quoting it
without the explanation would misrepresent the work in the other direction.

**How active time was measured.** Commit timestamps were clustered into
sessions with a 90-minute idle threshold; each session's span is
first-commit to last-commit. The thirteen sessions were 5.71, 0.00, 1.35, 0.00,
1.70, 0.36, 0.00, 1.64, 1.03, 0.00, 2.77, 1.17, and 0.00 hours.

**This figure is a lower bound, and it has degraded badly as a measure.**
Specifically:

* Work before a session's first commit is invisible — analysis, reading, and
  design that precedes the first commit is not counted.
* **Four of the thirteen sessions produced a single commit each**, so their
  spans are zero by this method despite representing real work. This is now the
  dominant error. One zero-scoring session removed 12,518 lines, rewrote the
  traceability generator, and audited every requirement. Another delivered the
  entire C4 job manager and worker pool.
* The method now systematically under-reports precisely the sessions that
  produce the most, because large coherent pieces of work land as one commit
  while exploratory work lands as many. **A measure that scores a milestone at
  zero and a debugging session at three hours is not measuring output.**
* Long verification runs are counted as active time whether or not they were
  attended, which pushes the other way. On this project those runs are
  substantial: the full local CI tier takes roughly fifteen minutes and was
  executed repeatedly.
* Realistic active effort is therefore **materially higher than 15.7 hours** —
  plausibly 25–35 — and the figure should be quoted as a floor, not a
  measurement.

**Recommendation: stop quoting the active-time figure.** It was a reasonable
proxy at six sessions and is misleading at thirteen. Either instrument the work
directly or drop the row; carrying it forward invites a comparison the data no
longer supports. The requirements-verified row is the honest progress measure
and should carry that weight instead.

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
| Code, tests, build, CI | 14,191 lines | 50–150 SLOC/day | 95–284 |
| Requirements written and traced | 332 requirements | 15–25/day | 12–20 |
| Architecture decision records | 12 records | 1–2 days each | 12–24 |
| Architecture and process documentation | 6,735 lines | 300–500 lines/day | 13–22 |
| **Total** | | | **132–350** |

At a 5-day week that is **26 to 70 engineer-weeks** — roughly **six months to
sixteen months for one engineer**, or three to eight months for a team of two.

The range widened as much as it moved, because the code subtotal nearly tripled
and it carries the widest rate band. Treat the lower bound as the defensible
figure; the upper bound assumes a rate appropriate to high-assurance work
throughout, which is true of the store and move engine and less true of the
build system.

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

**Against a measured floor of 15.7 hours of active time** (§5), and a realistic
25–35 hours, the comparison is between roughly **two to five working days and
roughly six to sixteen months of one engineer**.

That ratio is large enough to warrant scepticism, so the honest qualifications:

* The 15.7 hours is a floor, and by §5's own account a badly degraded one; the
  conventional figure is an estimate. The two are not measured the same way, and
  the comparison is indicative rather than like-for-like. Given that §5 now
  recommends retiring the active-time measure altogether, this whole comparison
  should be read as an order-of-magnitude claim and nothing finer.
* A substantial part of the specification output adapts design material
  produced in separate AI sessions. A human team would not have had that input
  either — but neither did this work originate all of it.
* Volume is not the same as value. §6 argues this point against the figures
  above.
* The comparison assumes producing **the same artifacts to the same standard**:
  332 traced requirements, 12 decision records, sixteen CI gates, two fuzz
  targets with retained corpora. A team asked only for working code would
  finish far sooner and deliver something different.
* **The system is not finished.** These figures measure a v1.0.0 in progress.
  The durable store, move engine, and job manager now exist; the HTTP server,
  socket layer, operator CLI, and dashboard do not. The conventional-effort
  comparison covers the work *done*, not a delivered product.

---

## 6. Honest limitations

A report that only lists successes should not be trusted, so:

**Errors were introduced as well as caught.** Of the twenty-eight findings in
§4, **twelve were defects created during this work** and caught before shipping.
From earlier periods: the btrfs misclassification, one requirement
contradiction, both faults in the locale-independence test, and the
mis-declared verification method on the GCC 4.8.5 compile requirement. Added
this period: the unretryable-`FAILED` defect in the move engine, the
fall-through in the job manager, the unparseable vendored-checksum row, the
symlink test that passed by coincidence, the hook-mode gate that checked the
index instead of the file, the retry tests that asserted nothing as root, and
the missing `-lrt`.

A configuration "fix" was also applied that turned out to be inert; a
repository-wide text substitution once edited an identifier *inside* a vendored
dependency; a `sed` with a non-unique pattern corrupted a function call by
inserting an argument; and a claimed verification of the sanitizer-runtime fix
checked a path that does not exist on that distribution. In one session the
first draft of a maintainer-guide edit *documented* a CI gate being dropped
rather than restoring it, and the correction came from re-reading the draft
rather than from any tool.

Two corrections this period were to **stated conclusions rather than to code**,
and they are the ones worth flagging to anyone weighing this report. While
investigating the outstanding ThreadSanitizer issue, two diagnoses were asserted
with more confidence than the evidence supported — that the reports were an
artifact of the test harness, and that they required more than one worker — and
both were disproved by a standalone reproducer built afterwards. Neither reached
the code. Both are recorded in `docs/C4-TSAN-OPEN.md`, because a confident wrong
diagnosis costs more than an admitted unknown: it stops the next person looking.

Worth stating plainly for anyone reading this as a case for the tooling: the
error rate here is not zero, and the errors are not trivial ones. What the
process provides is that they surface inside the same session rather than in
production — and that each one leaves behind a gate that closes its whole
class. **Five of the sixteen gates were added in direct response to a defect
that had already got through.**

**One known defect is open at the measurement point.** C4's ThreadSanitizer
tier reports 32 warnings on the job-manager suite, and the milestone is
deliberately not merged to `main` because of it. Every other tier is green.
Whether the manager's locking is actually wrong is not yet established — every
flagged access is made under the mutex, and the reports carry an internal
contradiction that points at the tool's accounting rather than the code — but
the honest position is that it is unresolved, not benign. Reporting the
milestone as delivered while that is open would be exactly the kind of
green-dashboard claim the rest of this document argues against.

**Output volume is not value.** 25,175 lines includes documentation that a
smaller project would not need. The requirements traceability and decision
records exist because this system has accreditation obligations; they should
not be counted as productivity in a context that does not require them.

**Just over half the in-scope requirements remain unverified.** 109 of 226 carry
evidence; 117 do not. The HTTP server, the socket layer, the dashboard, and the
operator CLI are specified and unbuilt. The figure is up from 21.2% and that is
real progress, but a reader should take 48.2% to mean *about half*, not *nearly
done*.

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
