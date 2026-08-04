# Contributing to Background File Mover

This document is the complete development setup. If a step here is wrong or
incomplete, fix it in the same change that discovers the problem — a setup
document that has drifted is worse than none, because it is trusted.

The implementations live on separate branches — they no longer share a tree:

| Branch | Implementation | Status |
|---|---|---|
| `main` | C++11 with a REST control plane | v1.0.0 in progress; **no Python in the tree** |
| `c<N>-<name>` | The milestone in flight, cut from `main` | Currently `c1-durable-store`; merged and deleted at the boundary |
| tag `v0.4.2` | Python 3.10, standard-library-only | **Deploy this today.** Not a branch — the Python tree was removed from `main` when C0 merged |

The long-lived `v2-cpp` branch is gone: it merged into `main` at the C0 boundary and was
deleted. Work happens on one branch per milestone — see *Merge cadence* in
`docs/ROADMAP.md`.

`CLAUDE.md` carries the migration context and the three failure modes that
are easy to get wrong. Read it before touching requirements.

---

## 1. Development environment

Development happens **inside WSL2 on the Linux-native filesystem**, not on a
Windows drive. The deployment targets are SLES 12 SP5 and RHEL 9, so a Linux
development environment removes a whole class of divergence.

### Toolchain versions are pinned, and must match

There are two toolchains, with different jobs:

| Toolchain | Role |
|---|---|
| **GCC 4.8.5** (`gcc:4.8` container) | **The deployment target.** SLES 12 SP5's system compiler. This is the tier that decides whether the code ships. |
| **g++-14 / clang-20 / clang-tidy-20** (Ubuntu 24.04) | An *instrument*, not a target. It hosts the sanitizers, libFuzzer, and clang-tidy that GCC 4.8 cannot run. |

Tools are pinned by **explicit package version**, not by taking the runner
image's defaults — Ubuntu 24.04 defaults to g++-13 and clang-tidy-18, and the
pipeline deliberately uses the newer g++-14 and clang-tidy-20 that the same
repositories provide. Explicit versions mean an image refresh cannot silently
change what the gates check. Both were verified against this codebase before
adoption: g++-14 builds clean under `-Werror`, and clang-tidy-20 reports zero
findings.

| Variable | Default | Purpose |
|---|---|---|
| `CXX` | `g++` | Compiler. CI passes `g++-14`. |
| `GCOV` | `gcov` | **Must match `CXX`** — mixing versions fails with a version mismatch and emits nothing usable. CI passes `gcov-14`. |
| `FUZZ_CXX` | `clang++` | libFuzzer needs clang. CI passes `clang++-20`. |

**Using newer analysis tools carries no deployment risk.** Only the GCC 4.8.5
tier produces a shipped artifact; the modern toolchain never does. Its version
changes how many bugs you find, not what deploys. So the modern tier tracks
current tools deliberately rather than being frozen for safety.

Every C++ workflow pins `runs-on: ubuntu-24.04`. **Never `ubuntu-latest`.**
That label is a moving pointer, and when GitHub moved it from 22.04 to 24.04
three jobs went red with no code change behind them:

* GCC 13 raises `-Wmaybe-uninitialized` against libstdc++ `<regex>` internals
  under `-O1` plus sanitizers, which GCC 11 does not.
* clang-tidy 17 added `misc-include-cleaner` and 18 added
  `performance-enum-size`, so a config enabling check *families* silently
  gains checks.

Analysis tools are part of the build contract; an unpinned one is an unpinned
dependency. Upgrade on purpose, in a commit that also handles the fallout.

### Reproducing CI locally

The WSL host toolchain is whatever the distro ships — fine for the fast inner
loop, but not what CI runs. To run the *exact* CI tier:

```bash
cd cpp && make check-ci
```

That executes functional, sanitizer, Valgrind, cppcheck, and clang-tidy tiers
inside a **prebuilt toolchain image**, `ghcr.io/joey-huckabee/bfm-ci`, built
from `.github/ci-image/Dockerfile`.

It used to run bare `ubuntu:24.04` and apt-install the toolchain on every
invocation (~40s), justified as the price of not maintaining a second distro.
That was the right trade while this repository maintained no images; it already
maintains the GCC 4.8.5 mirror, so the trade changed. The image is also *the
pin* — the package list lives in the Dockerfile and is deliberately not copied
back into the Makefile, because two copies of a pinned toolchain is how pins
drift apart.

Tags are dates, never `latest`, so a run always names the toolchain it used.
Rebuild and repush when a pinned version changes, then update `CI_IMAGE` in
`cpp/Makefile` in the same commit:

```bash
podman build -t ghcr.io/joey-huckabee/bfm-ci:YYYY-MM-DD \
    -f .github/ci-image/Dockerfile .github/ci-image
podman push ghcr.io/joey-huckabee/bfm-ci:YYYY-MM-DD
```

The package must be **public**, for the same reason the fidelity mirror must
be: it lives in a user namespace rather than the repository's.

The tiers compile with `make -j$(CI_JOBS)`, defaulting to `nproc`. Do not
expect much from raising it — the vendored `sqlite3.c` is a single 9.5 MB
translation unit that takes ~49s by itself against ~1.4s for a typical C++
file, so it is the critical path and a parallel build is close to "compile
sqlite3.c".

That object is therefore cached with **ccache**, and nothing else is. It is the
only source here that never changes (ADR-0004 forbids editing vendored files)
and the most expensive to build, so the five or six rebuilds a `check-ci` run
performs were producing an identical object each time. Measured in the
container: **60s cold, 0s warm**.

The cache lives at `$(CCACHE_HOST_DIR)` — `~/.cache/background-file-mover-ccache`
by default — and is mounted into the container. It is outside the repository on
purpose, so `git clean` cannot wipe it, and it survives between runs, which is
the whole point: the container is discarded on exit, so an in-container cache
would start cold every time.

ccache is **not** applied to the project's own sources. The saving there is a
second or two, and the coverage tier compiles with `--coverage`, where ccache
has to place `.gcno` files exactly where gcov will look for them. That is a
real risk for no measurable gain — and this project's coverage reporting has
already been broken once by a path-resolution subtlety.

If ccache is not installed, `CCACHE` is empty and the rule degrades to a plain
compile, so nothing depends on its presence.

`make versions` prints the host toolchain; CI prints the same in its log, so a
runner-image change is a visible diff rather than a mysterious failure
somewhere else.

One gotcha: **LeakSanitizer needs `ptrace`**, which containers block by
default. `make check-ci` passes `--cap-add=SYS_PTRACE`; without it LSan dies
with a fatal error that reads like a test failure.

This used to come with the note "GitHub's runner is not a container and does
not need this." That stopped being true when the sanitizer job moved into the
toolchain image, so it now declares `options: --cap-add=SYS_PTRACE` on its
`container:` for exactly the same reason.

### Why not `/mnt/c`

Two independent, measured reasons:

1. **Builds there are intermittently broken.** GCC fails with
   `Assembler messages: can't open /tmp/ccXXXX.s for reading` on some runs and
   succeeds on others — observed failing and passing within a single
   invocation. Root cause is not established. Setting `TMPDIR` to the native
   filesystem was tried and is **not** a reliable fix. An unpredictable build
   is worse than a broken one.
2. **Small-file I/O over the 9p bridge is ~500× slower.** 300 files: 0.005s
   native versus 2.544s on `/mnt/c`. Compilation only pays ~30% because it is
   compile-bound, but the fuzz corpus (ADR-0008) is thousands of small files
   read on every run — the pathological case.

From Windows the repository is reachable at
`\\wsl.localhost\Ubuntu\home\<you>\GIT\background-file-mover`. That path is
for dropping files in (transcripts, milestone zips), not for building.

---

## 2. One-time setup

```bash
# Toolchain, test/analysis tooling, and the container runtime for the
# GCC 4.8.5 fidelity tier.
sudo apt update
sudo apt install -y \
    build-essential gdb make \
    valgrind cppcheck \
    clang clangd clang-format clang-tidy \
    bear \
    ccache \
    podman

git clone git@github.com:joey-huckabee/background-file-mover.git ~/GIT/background-file-mover
cd ~/GIT/background-file-mover
git checkout c1-durable-store   # or whichever milestone is in flight
```

### GitHub authentication — use SSH

Pushing from WSL needs SSH. The two obvious alternatives do not work here:

* **Git Credential Manager from the Windows side** fails with
  `UtilAcceptVsock:251: accept4 failed 110` — a WSL/GCM interop break, not
  worth debugging.
* **`gh auth login`** needs `gh`, which is not in the base install.

```bash
ssh-keygen -t ed25519 -C "your@email" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub          # paste into https://github.com/settings/ssh/new
ssh -T git@github.com              # expect: "Hi <user>! You've successfully authenticated"
```

The key above is generated without a passphrase, which is conventional for a
development workstation. Add one at any time with
`ssh-keygen -p -f ~/.ssh/id_ed25519`.

What each piece is for:

| Package | Purpose |
|---|---|
| `build-essential` | GCC and the C++ standard library — the primary toolchain |
| `valgrind` | memcheck tier; catches invalid access and leaks the sanitizers structure differently |
| `cppcheck` | static analysis over project sources |
| `clang` | sanitizer and **libFuzzer** tiers (ADR-0008); GCC 4.8 can host neither |
| `clangd` | C++ language server for editor completion, diagnostics, go-to-definition |
| `bear` | records a `compile_commands.json` from a Make build so `clangd` understands the project |
| `ccache` | caches the vendored `sqlite3.o`. Optional — the build degrades to a plain compile without it — but without it every clean build pays ~49s to recompile a 9.5 MB file that never changes. `make versions` says `MISSING` when it is absent. |
| `podman` | runs the GCC 4.8.5 fidelity tier in a container |

Ubuntu's Podman has no unqualified-search registries configured, so images
must be named in full — `docker.io/library/ubuntu:24.04`, not `ubuntu:24.04`.
A bare name fails with `short-name ... did not resolve to an alias`. The
fidelity image is already fully qualified (`ghcr.io/...`), so it is unaffected.

### Python tooling

Not needed on this branch. The only Python left is the trace-matrix generator
(`scripts/build-trace-matrix.py`), which imports the standard library only and
runs under any `python3`. Poetry and the lint/type toolchain went with the
Python implementation; they are still on `main` if you work there.

---

## 3. Editor and language server

`clangd` needs a compilation database. Generate it with `bear`, and regenerate
whenever files are added to the Makefile:

```bash
cd ~/GIT/background-file-mover/cpp
make clean-all          # REQUIRED — see below
bear -- make all
# writes cpp/compile_commands.json
```

`compile_commands.json` is generated output and is **not** committed.

**`make clean-all` before `bear` is not optional.** bear records only the
compiler invocations it observes. Against an already-built tree it sees none
and writes an *empty* database — and clang-tidy then prints
`Skipping src/foo.cpp. Compile command not found.` and **exits 0**. The gate
passes having analyzed nothing, which is invisible unless someone reads the
log closely. This happened once here and was caught only by chance.

`make tidy` and the CI job both run `scripts/assert-compile-db.sh` afterwards
to prove the database covers the sources, so the failure mode is now loud.

**Run `make tidy`, never `clang-tidy` directly.** Two reasons, both learned
the hard way:

* The target analyses `$(LIB_SRC)`, so it cannot drift from the build. The CI
  job used to name `src/job.cpp src/json.cpp` explicitly and silently stopped
  covering `api_codec.cpp` and `config.cpp` when they landed — green while
  checking less and less.
* clang-tidy emits **relative** paths when run with `-p .` from inside `cpp/`.
  Filtering its output with a pattern anchored on `^/` discards every
  diagnostic, and piping it masks the exit code. That combination once
  reported a file as clean when it had three findings. Trust the exit status
  of `make tidy`, not a grep over its output.

For VS Code, use the **Remote-WSL** extension so the editor runs a server
inside WSL. This gives native-speed editing and lets `clangd` see the real
filesystem; opening the UNC path from a Windows-side VS Code instead works
but is slower and `clangd` will struggle with the paths.

---

## 4. Build and test

All commands run from `cpp/`.

```bash
make check                # functional suite, -Werror
make check SANITIZE=1     # ASan + UBSan + LSan
make check-valgrind       # Valgrind memcheck, fails on any finding
make toolchain            # print the resolved BUILD_DIR for this tier
make clean                # remove only this tier's artifacts
make clean-all            # remove every tier's artifacts

cppcheck --enable=warning,portability --error-exitcode=1 \
         --inline-suppr --std=c++11 -Iinclude src/ tests/
```

The GCC 4.8.5 fidelity tier:

```bash
make check-gcc48
```

This target and the CI job pull the **same** image,
`ghcr.io/joey-huckabee/gcc-4.8:4.8.5` — a byte-identical mirror of
`docker.io/library/gcc:4.8`, republished with a v2s2 manifest.

The upstream tag is no longer usable. It was pushed in 2016 with a Docker
manifest v2 *schema 1*, which modern Docker disables by default, so the CI job
failed at the pull with `exit code 125` before compiling anything — while this
tier kept passing locally, because podman still accepts schema 1. Schema 1 is
being removed outright, so pinning the upstream tag is not a fix that lasts.

The invocation lives in the Makefile rather than in prose precisely because
three hand-written copies of it are how local and CI came to pull different
images in the first place.

#### Recreating the mirror

The mirror is infrastructure this project owns, so the recipe belongs here
rather than in one person's shell history. It must be produced with a tool
that can still *read* schema 1 — podman and skopeo can, current Docker cannot,
which is the whole reason the mirror exists.

```bash
podman pull docker.io/library/gcc:4.8
podman tag  docker.io/library/gcc:4.8 ghcr.io/joey-huckabee/gcc-4.8:4.8.5
podman login ghcr.io -u <user> --password-stdin   # needs a write:packages token
podman push --format v2s2 ghcr.io/joey-huckabee/gcc-4.8:4.8.5
```

Verify the conversion actually happened rather than assuming it — the point of
the exercise is the manifest, not the upload:

```bash
podman manifest inspect ghcr.io/joey-huckabee/gcc-4.8:4.8.5
# schemaVersion must be 2, and mediaType
# application/vnd.docker.distribution.manifest.v2+json.
# If it still says manifest.v1+prettyjws, nothing was fixed.
```

The package must be **public**, or CI cannot pull it: it lives in a user
namespace rather than the repository's, so a workflow's `GITHUB_TOKEN` has no
implicit read access to it. Publishing a byte-identical copy of an
already-public image discloses nothing.

### Build directories are keyed on toolchain

Output goes to `build/<machine>-<version>-<tier>`, so the modern, container,
and sanitizer builds cannot overwrite one another. Before this was keyed,
running the WSL build and then the container build left a glibc-2.34 binary
in place for the container to execute, which fails with a wall of
`GLIBC_2.xx not found` and reads as a code fault rather than a stale
artifact.

Override with `make BUILD_DIR=/somewhere/else` when needed.

### The CI tiers, and what each actually proves

| Tier | Where | Proves |
|---|---|---|
| modern g++ | WSL | functional correctness; hosts the instrumentation GCC 4.8 cannot |
| ASan/UBSan/LSan | WSL | memory safety and undefined behavior |
| Valgrind | WSL | invalid access and leaks, structured differently from ASan |
| cppcheck | WSL | static analysis |
| clang-tidy | WSL | static analysis from a second engine; disagrees with cppcheck often enough to be worth both |
| libFuzzer corpus replay | WSL | past findings stay fixed |
| libFuzzer 60s session | WSL | new findings on every PR |
| gcov coverage | WSL | what the tests do not reach |
| GCC 4.8.5 | container | **C++11 conformance on the SLES 12 system compiler** |
| CodeQL | CI only | security queries; C++ needs `build-mode: manual` |
| SonarCloud | CI only | quality gate, via `compile_commands.json` + gcov |
| SLES 12 SP5 | hardware | **deployability** — systemd, NFS qualification, e2e |

`make format-check` exists but is **not** a gate. The sources use deliberate
column alignment that clang-format rewrites, so enabling it means a one-time
bulk reformat of already-tested code — a decision to take on purpose rather
than acquire by adding a job.

CodeQL and SonarCloud cannot be verified locally; they need GitHub and, for
Sonar, the three repository secrets. Everything else in the table runs on
your machine.

The GCC 4.8 job runs the **full test suite**, not a compile check. That is
what closes the gap between the instrumented build and the shipped build,
since the sanitizers never run against the GCC 4.8 compilation.

`gcc:4.8` is a *proxy*, not the target: Debian 7 "wheezy" with glibc 2.13
versus SUSE 2.22, no systemd, no NFS. Older rather than merely different, so
it is a conservative floor. Deployability is verified on real hardware per
`docs/DEPLOYMENT.md`.

---

## 5. Fuzzing

Per ADR-0008, the untrusted-input path is fuzzed with libFuzzer under
ASan+UBSan. libFuzzer requires clang; the code under test is identical
because the source is strictly C++11-conformant and compiled from one body.

```bash
make fuzz                        # build every fuzz target
make fuzz-corpus                 # replay committed corpora once (the PR gate)
make fuzz-run                    # live session, FUZZ_SECONDS=60 per target
make fuzz-run FUZZ_SECONDS=1800  # what the nightly burn-in runs
sh fuzz/make-seeds.sh            # regenerate the JSON seed corpus
sh fuzz/make-seeds-http.sh       # regenerate the HTTP seed corpus
```

There are **two targets**, listed in the Makefile's `FUZZ_TARGETS`: `json`
(`fuzz/fuzz_json.cpp`) and `http` (`fuzz/fuzz_http.cpp`). Every target gets its
own corpora, keyed by name — the `make` targets loop over all of them, so
adding a third means adding one word to `FUZZ_TARGETS` and two directories.

| Path | Committed | Purpose |
|---|---|---|
| `cpp/fuzz/corpus-<target>/` | yes | Curated seeds, one per interesting branch. Hand-written. |
| `cpp/fuzz/corpus-regression-<target>/` | yes | Minimized crash reproducers. Replayed by every PR. |
| `cpp/build/fuzz/corpus-<target>/` | no | libFuzzer's working corpus. Regenerated, mostly noise. |

**libFuzzer writes into the first corpus directory it is given**, and this is
true even with `-runs=0` — it still copies coverage-increasing inputs between
directories. Both Makefile targets therefore pass a scratch directory first
and the committed ones after, as read-only seeds. Point a fuzzing command
straight at `fuzz/corpus-json/` and it will bury the curated seeds under
hundreds of generated ones within a minute.

When the fuzzer finds a crash, the reproducer lands in
`cpp/build/fuzz/artifacts-<target>/` (and is uploaded as a CI artifact).
Minimize it, give it a name that says what it exercises, and commit it to the
matching `corpus-regression-<target>/`. That retention is where the long-term
value is — fuzzers find bugs once, corpora prevent them forever.

## 5a. Coverage

```bash
make coverage                                    # build, run, report
sh scripts/coverage-summary.sh build/coverage/report
```

Coverage builds into its own `-O0 --coverage` tier so instrumented objects
never mix with the ordinary build. gcov must run from `cpp/`, not from the
report directory — it resolves sources by the relative path recorded at
compile time and silently writes one-line stubs if it cannot read them.
`-r` excludes anything reached by an absolute path, which is how system
headers and Catch2 stay out of the report.

## 5b. Concurrency

```bash
make check THREAD=1      # ThreadSanitizer tier (L2-ARC-008)
```

A separate build from `SANITIZE=1`, because TSan and ASan cannot coexist in
one binary — their shadow-memory layouts conflict. Run it whenever you touch
anything threaded. A data race can sit in a tree for years while every test
passes, surfacing only under a scheduler the test machine never produces.

**Concurrency tests are deterministic, never timed.** Do not `sleep` and hope.
To prove N workers run concurrently, block them on a latch *inside* the
operation under test and assert all N arrive before releasing it — that either
holds or hangs, with no middle ground that passes on an idle machine and fails
on a loaded one.

Order is proved the same way: **inject the clock** (`std::function<int64_t()>`)
rather than reading one. A counter incrementing per call makes timestamps
strictly increasing, so completion order is checkable *exactly* rather than
probabilistically — and it keeps the core clock-free (`L2-CORE-004`).

---

## 6. Requirements and traceability

Requirements decompose L1 → L2 → L3, and `docs/TRACE-MATRIX.md` is generated,
never hand-edited:

```bash
python scripts/build-trace-matrix.py            # regenerate
python scripts/build-trace-matrix.py --check    # CI gate; fails on drift
```

Adding a requirement:

1. Add the L1/L2/L3 entry in the appropriate `docs/L*-REQ.md`.
2. Give it a parent — every L2 names one L1, every L3 names one L2.
3. If it introduces a new category prefix, register it in the `CATEGORIES`
   list in `scripts/build-trace-matrix.py` or it will not render.
4. Tag the verifying test: `@pytest.mark.requirement("...")` in Python,
   or a Catch2 tag `"[L3-CPP-NNN]"` in C++.
5. Regenerate the matrix and commit the result alongside the change.

The generator reads **both** languages: `@pytest.mark.requirement` decorators
under `tests/` via an AST parse, and requirement ids inside Catch2 `TEST_CASE`
tag strings under `cpp/tests/`. A tag is the entire mechanism — there is nothing
else to register — and because Catch2 selects on tags, the matrix entry doubles
as a runnable command: `./filemover_tests "[L3-CPP-019]"`.

**Pick the verification method honestly.** `T` commits you to a test that can
fail. When the evidence is a build gate rather than an assertion — "compiles
clean under `-Werror` on GCC 4.8.5" — the method is `D`. Marking such a
requirement `T` leaves a permanent hole in the matrix against something that is
in fact gated on every commit.

**Deferred requirements are not implemented.** v1.0.0 is deliberately
narrower than v0.4.2 — see the v1.0.0 scope section of `docs/L1-REQ.md`. Do
not treat a Deferred requirement as satisfied, and do not delete one to make
the matrix look clean.

---

## 7. Architecture decisions

Decisions live in `docs/adr/`, MADR format, numbered sequentially. Write one
whenever a choice constrains future work: toolchain, dependency, protocol,
storage, or a policy that will outlive the person who made it.

An ADR must record the **real** driver. If a decision is organizational
rather than technical, say so — ADR-0007 excludes BSD licenses by internal
policy and states explicitly that it is not a compatibility finding, so a
future maintainer who checks compatibility, finds no conflict, and concludes
the entry is a mistake does not reverse it.

When a premise turns out to be wrong, correct it in place and keep a note of
what was wrong. ADR-0001 carries a correction-of-record block for exactly
this reason.

---

## 8. Vendored dependencies

Governed by ADR-0004 (pinning and provenance) and ADR-0007 (license policy).

* Files under `cpp/third_party/` are **never edited**. Unavoidable changes
  live as `.patch` files applied at build time.
* Every entry in `cpp/VENDORED.md` records upstream URL, pinned tag, SHA-256,
  and license.
* **BSD-2-Clause and BSD-3-Clause are excluded by internal policy.** Check
  ADR-0007 before introducing any dependency, including test-only ones.

---

## 9. Commit conventions

Conventional commits with a **capitalized type and capitalized subject**:
`Type(scope): Capitalized subject`. Merge commits use `Merge: <subject>`.

```
Docs(deploy): Add end-to-end RHEL 9 and SLES 12 platform runbooks
Feat(version): Derive __version__ from package metadata (single source)
Build(cpp): Key build directories on toolchain
```

Bodies explain *why*, and record decisions that were reversed or premises
that turned out wrong. Do **not** add `Co-Authored-By` trailers — commit
messages are the human-authored record of intent.

---

## 10. Design material produced outside the repository

The convention, following the `docs/CAPTURE.md` precedent: land raw material in
a scratch `transcripts/` directory, mine it into requirements and ADRs commit by
commit, then delete it. Raw transcript content never becomes reference
documentation — the specs are the reference. An empty (or absent)
`transcripts/` is the ready signal for the next drop.

The inherited C++ design series ran to eight milestone snapshots and is closed;
`transcripts/` is gone. What survived it is `docs/MIGRATION-PROVENANCE.md`,
which records where each drop landed and — the part worth keeping — why most of
it was **not** adopted. Read it before re-introducing anything from that
material. Inherited material is triaged, not adopted, and was caught carrying a
fabricated premise.

---

## 11. Before you push

```bash
cd cpp
make clean-all
make check                                    # functional
make check SANITIZE=1                         # sanitizers
make check THREAD=1                           # ThreadSanitizer
make check-valgrind                           # memcheck
make verify-vendored                          # vendored file hashes
make locale-free                              # L3-CPP-052 source gate
make fuzz-corpus                              # fuzz regression gate
make coverage                                 # coverage report
cppcheck --enable=warning,portability --error-exitcode=1 \
         --inline-suppr --std=c++11 -Iinclude src/ tests/
make clean-all && bear -- make all && make tidy    # see the note below
make check-gcc48                              # GCC 4.8.5 fidelity tier

cd ..
python scripts/build-trace-matrix.py --check   # traceability gate
```

CI runs the same set. Running it locally first is cheaper than a red branch.

One test needs a locale that most machines do not have. The
locale-independence check in `tests/test_http_parser.cpp` parses under
`tr_TR.UTF-8`, where `std::tolower('I')` does not yield `'i'`. If the locale is
not generated, `setlocale` returns `NULL` and the test emits a `warning:`
saying so rather than reporting a clean pass. `make check-ci` and the CI
runner both generate it; to run it for real on the host:

```bash
sudo locale-gen tr_TR.UTF-8
```

`make locale-free` is the gate that does not depend on the environment — it
greps the parser sources for `<cctype>` and the `strtoul` family. See
`docs/HAND-ROLLED-COMPONENTS.md` §5.1 for why both exist.
