Do you think we can go to C++ 11 and HTTP/1.2?

C++11 yes — but HTTP/1.2 doesn't exist. The versions went HTTP/1.0 → HTTP/1.1 (1997, last revised in RFCs 9110–9112) → HTTP/2 (2015, binary framing, multiplexing) → HTTP/3 (2022, QUIC over UDP). There was never a 1.2.

You might be thinking of TLS 1.2, which does exist and is a common requirement in DoD contexts (STIGs mandate TLS 1.2+ for anything encrypted in transit). If the actual question is "can we do HTTPS with TLS 1.2 on SLES 12," the answer is yes-with-caveats: SLES 12's OpenSSL (1.0.1/1.0.2 era) supports TLS 1.2, and you'd link against the system OpenSSL rather than hand-rolling anything. But that meaningfully complicates the hand-rolled server option — at that point vendoring cpp-httplib with CPPHTTPLIB_OPENSSL_SUPPORT, or terminating TLS in front with a reverse proxy (nginx/stunnel from SLES repos), becomes much more attractive than writing your own TLS integration.

For the protocol itself, HTTP/1.1 is exactly what you want. HTTP/2 would be actively wrong here: it requires binary framing, HPACK header compression, and stream multiplexing — enormous implementation surface for zero benefit on a four-endpoint internal API polled every 2 seconds by one dashboard. No hand-rolled server should attempt it, and even vendored C++ HTTP/2 libraries (nghttp2) are a compiled-dependency headache on GCC 4.8.5.

So the stack is: C++11 + HTTP/1.1, with a subset implementation if we hand-roll — GET and POST, Content-Length bodies only (no chunked transfer on requests), Connection: close semantics to dodge keep-alive state machines, and a hard cap on request size. That subset is fully conformant for your clients (curl, browser fetch, whatever triggers the moves) and keeps the parser small enough to exhaustively unit-test.

Was TLS the underlying concern, or did you just want confirmation on the HTTP version? If TLS is required, that decision reshapes option 1 vs option 2 from the last message and belongs in an ADR early.

I think we can build this without TLS and put it behind a proxy if necessary.  I think this is a very complex application and I want to make sure what we develop does not have any bugs if possible. I need small incremental functional steps built and tested.

Good call on TLS — Connection: close, plaintext, proxy-terminated if ever needed. That's an ADR worth writing down day one.

For correctness, the strategy that matters most: build it bottom-up in dependency order, where every milestone is a fully-tested library layer before anything touches a socket or the filesystem. The bugs that hurt in this kind of daemon live in three places — the HTTP parser, the state machine, and filesystem edge cases — so each gets isolated behind an interface and hammered independently. Here's the milestone plan I'd propose:

M1 — Core types & job state machine. Job, JobState enum, legal-transition table (QUEUED→RENAMING→TRANSFERRING→DONE|FAILED), timestamps, error capture. Pure logic, no I/O, no threads. Catch2 tests enumerate every transition — legal ones succeed, illegal ones are rejected. This is your L1 backbone.

M2 — JSON writer, then parser. Writer first (trivial, needed by everything). Parser second: only what the API accepts — objects, strings, numbers, escapes. Tests include malformed input, truncation, huge tokens, invalid escapes. If you vendor nlohmann instead, M2 collapses to a wrapper + acceptance tests pinning the behaviors you rely on.

M3 — Config loader. INI parse + validation with precise error messages (file:line). Tests: missing keys, bad values, empty file, duplicate sections.

M4 — Journal. Append (O_APPEND, single write() per record) + replay. Tests: round-trip, replay with a torn final line (simulated crash), empty file, fsync policy.

M5 — HTTP request parser. Bytes-in, struct-out, zero socket code — the function takes a buffer, so it's exhaustively testable: split reads, oversized headers, bad methods, missing Content-Length, smuggling-shaped inputs. This is the security-critical unit; it earns the largest test count.

M6 — Rename engine. Template expansion + collision policy. Tests against a temp dir fixture: target exists, source missing, no permission, cross-device attempt rejected.

M7 — Transfer adapters. Interface + LocalRename, then CopyFsyncRename (partial-file invariant: destination name never appears incomplete), then ExecTransfer. Failure injection: full disk (test via small tmpfs where possible), missing dest dir, child exit codes.

M8 — JobManager. Queue + workers wired to M1's state machine, using a mock transfer adapter with controllable delays/failures. Tests: ordering, concurrent submission, failure propagation, clean shutdown with in-flight jobs.

M9 — HTTP server + routes. Socket loop glued to M5's parser, endpoints returning M2's JSON. Integration tests via a tiny test client (or curl in a script): happy paths, 404, 405, oversized body → 413.

M10 — Journal-backed recovery + /api/status aggregation. Replay on startup marks interrupted jobs FAILED-with-reason.

M11 — Dashboard. Embedded page, polling. Test is mostly manual + one route test asserting the HTML serves.

M12 — Daemonization & signals. Reuse the background-file-mover skeleton; SIGTERM drains the queue.

Each milestone: write its L3 requirements first, then tests, then implementation, conventional commit per milestone, no milestone starts until the previous one's tests are green. M1–M8 all run without root, network, or timing dependencies, so the suite stays fast and deterministic — the two integration-flavored milestones (M9, M12) sit at the very end where they belong.

Rough sizing based on the C++ port's history: M1–M4 are each a day-ish; M5 and M7 are the two-to-three-day ones; expect the total suite to land somewhere in the 150–250 test range.

Want me to draft the L1 requirement set next, or the ADRs (no-TLS, HTTP/1.1-subset, vendored-vs-hand-rolled JSON) first?

I can vendored libraries so let’s do that as well

Vendoring changes the plan in your favor — it deletes the two riskiest hand-rolled components. Here's the updated picture:

Vendored set (both MIT, single-header, air-gap friendly):

nlohmann/json — pin a 3.x release; the project has long kept GCC 4.8 in its supported-compiler list, but verify your exact pinned tag compiles on 4.8.5 in the spike. M2 collapses from "write a parser" to a thin wrapper plus acceptance tests pinning the behaviors you depend on (parse errors throw vs. parse(..., nullptr, false) returning discarded, number handling, UTF-8 strictness).
cpp-httplib — this one needs a real compatibility spike. Recent releases use language/library features that won't fly on GCC 4.8.5, so you'll be pinning an older tag. Budget the first hour of the project to bisecting tags until one compiles clean with -std=c++11 -Wall -Werror on the actual SLES 12 box. Whatever tag wins goes in the ADR with its SHA-256.

Milestone plan updates:

M2 shrinks to a day: wrapper + acceptance tests.
M5 (HTTP parser) is deleted. cpp-httplib owns parsing. In its place: a small acceptance suite that runs the vendored server on a loopback port and throws hostile inputs at it via raw sockets — oversized headers, bad methods, garbage bytes — asserting it 4xx's or closes rather than crashing. You're no longer testing your parser; you're characterizing the vendored one so an upgrade that changes behavior fails loudly.
M9 shrinks substantially: route handlers become plain functions taking httplib::Request → filling httplib::Response, and you can unit-test the handler logic by constructing those structs directly, no socket needed. Set Connection: close, a max body size, and bind explicitly to the configured interface.
Everything else (M1, M3, M4, M6–M8, M10–M12) is unchanged — the core, journal, rename, transfer, and job-manager work was never the vendored layer's problem.

Vendoring discipline (worth an ADR): a third_party/ directory containing each header verbatim, a VENDORED.md recording upstream URL, pinned tag, SHA-256, license, and the local rationale, and a rule that vendored files are never edited — if a patch is unavoidable it lives as a .patch file applied at build time so upgrades stay tractable. Both licenses are MIT, so a LICENSES/ folder with the two texts satisfies attribution.

Net effect on sizing: the two-to-three-day milestones drop to M7 only, total timeline shortens by roughly three or four days, and the test suite shifts composition — fewer parser unit tests, more characterization tests. Probably lands 130–200 tests instead of 150–250.

The one thing I'd still hand-roll is the INI config loader (M3). It's 100 lines, there's no equivalently-pinnable single-header INI library worth the vendoring paperwork, and you likely have one to lift from background-file-mover anyway.

Ready to draft the L1s, or do you want the three ADRs first (no-TLS/proxy-terminated, vendored cpp-httplib + nlohmann with pins, HTTP/1.1 Connection: close subset)?

I want a project structure and I need to know how to standup a GitHub CI pipeline to build and test this. I also need the ADRs and L1,L2 and L3 requirements and the first build

Everything's built, tested, and packaged. M1 is green: 199 assertions across 10 test cases, compiled -std=c++11 -Wall -Wextra -Werror clean.

What's in the zip:

Project structure — include/filemover/ + src/ (M1 core), tests/ (Catch2, natural-order assertions, requirement IDs in test tags), third_party/catch2/ (v2.13.10 vendored, SHA-256 recorded — v2 line because v3 requires C++14), docs/adr/, docs/requirements/, VENDORED.md, LICENSES/, plain Makefile per ADR-0005.

CI (.github/workflows/ci.yml) — two jobs: a modern-g++ job for fast feedback, and a fidelity job running inside the official gcc:4.8 Docker container (GCC 4.8.5, the closest public proxy for your SLES 12 compiler). One gotcha handled for you: node-based actions like checkout@v4 can't execute in that container (glibc too old), so the fidelity job clones with plain run steps — there's a commented tokenized clone URL to swap in if the repo is private. Standing this up is just: create the GitHub repo, push, done — the workflow triggers on push/PR with no further setup.

ADRs — five, MADR format with precedent: 0001 C++11/GCC 4.8.5, 0002 REST over HTTP/1.1 subset (no gRPC), 0003 no in-process TLS, 0004 vendored pinned single-headers (Catch2 pinned now; nlohmann and cpp-httplib marked TBD pending their compile spikes in M2/M9), 0005 GNU Make.

Requirements — 25 L1 system requirements with verification methods, L2s for all nine components traced to L1s, and 15 L3-CPPs for M1 traced to L2-CORE and verified by name in the test suite.

M1 code — Job + JobState + transition table, pure logic: caller-supplied timestamps, no I/O/thread/clock headers (that's L3-CPP-012). Transitions are atomic — illegal requests, empty-error Failed attempts, and error-on-success attempts all leave the job untouched. The suite exhaustively enumerates all 25 state pairs plus lifecycle, failure-from-every-state, and terminal-immutability cases.

Suggested first commit: feat(core): M1 job state machine with exhaustive transition tests. Next up is M2 — the nlohmann pin spike plus wrapper and characterization tests. Want me to build that next?

Rest File Mover m1 zip is no longer available to download and share.

Let’s continue and how do I make sure I don’t have any memory leaks, use after free or cybersecurity issues?

Both — let's answer the safety question by building it into the pipeline, then continue with M2. First, one fact to verify before pinning the JSON library:

Validated code integrity and plotted CI integration strategy
Validated code integrity and plotted CI integration strategy

M2 is done and the safety pipeline is live: 299 assertions in 22 test cases, passing clean under the functional build, ASan+UBSan+LSan, Valgrind (16,510 allocs / 16,510 frees, zero errors), and cppcheck.

To your question — memory leaks, use-after-free, and security get four independent layers, all now CI-enforced so a regression can't merge:

Sanitizers (make check SANITIZE=1): ASan catches use-after-free, heap/stack overflows; UBSan catches undefined behavior; LSan catches leaks. GCC 4.8 has only partial ASan and no LSan, so these run in the modern-g++ CI job — the code under test is identical since everything is C++11-clean.
Valgrind memcheck (make check-valgrind): overlapping but differently-structured detection, --error-exitcode=1 fails on any finding including still-reachable blocks.
cppcheck static analysis over project sources (vendored headers excluded — they're pinned artifacts, not project code).
Design rules that prevent the bug classes at the source: RAII only, no naked new/delete (nothing in M1/M2 heap-allocates directly at all), caller-supplied timestamps keep the core deterministic, no system(3) ever — M7's exec strategy uses fork/execvp with argv arrays so no shell injection surface exists, and strict-reject JSON decoding (unknown members, embedded NULs, wrong types all bounce).

The pipeline paid for itself immediately. The nlohmann plan died on contact with evidence — its maintainer explicitly refuses GCC 4.8 support due to compiler bugs 55817/57824, workaround PRs closed wontfix — so ADR-0006 pins picojson v1.3.0 instead (single header, ~1,100 lines, BSD-2-Clause, small enough to audit line-by-line, confined to api_codec.cpp per L3-CPP-021). Then the characterization suite caught a real vulnerability before any HTTP code exists: picojson silently ignores trailing bytes after the first JSON value, so {"source":"/a","dest":"/b"}<garbage> parsed clean. The codec now enforces whole-body consumption (L3-CPP-024), the quirk is pinned in a test so a future tag bump fails loudly, and the finding is documented in the ADR.

Also in the zip: L3-CPP-016 through 025 for M2, four new CI jobs (sanitizers, valgrind, cppcheck, plus the existing modern and gcc-4.8 pair), picojson's license text, and updated VENDORED.md with its SHA-256.

Two commits' worth: feat(codec): M2 JSON codec with strict validation over vendored picojson and ci: add sanitizer, valgrind, and cppcheck gates. M3 (config loader) next?

I have included the rest-file-mover-m2 folder for the artifacts of Milestone 2
