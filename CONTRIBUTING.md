# Contributing to Background File Mover

This document is the complete development setup. If a step here is wrong or
incomplete, fix it in the same change that discovers the problem — a setup
document that has drifted is worse than none, because it is trusted.

Two implementations currently coexist:

| Branch | Implementation | Status |
|---|---|---|
| `main` | Python 3.10, standard-library-only | Ships through v0.4.2 |
| `v2-cpp` | C++11 with a REST control plane | v1.0.0 in progress |

`CLAUDE.md` carries the migration context and the three failure modes that
are easy to get wrong. Read it before touching requirements.

---

## 1. Development environment

Development happens **inside WSL2 on the Linux-native filesystem**, not on a
Windows drive. The deployment targets are SLES 12 SP5 and RHEL 9, so a Linux
development environment removes a whole class of divergence.

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
    podman

git clone https://github.com/joey-huckabee/background-file-mover.git ~/GIT/background-file-mover
cd ~/GIT/background-file-mover
git checkout v2-cpp
```

What each piece is for:

| Package | Purpose |
|---|---|
| `build-essential` | GCC and the C++ standard library — the primary toolchain |
| `valgrind` | memcheck tier; catches invalid access and leaks the sanitizers structure differently |
| `cppcheck` | static analysis over project sources |
| `clang` | sanitizer and **libFuzzer** tiers (ADR-0008); GCC 4.8 can host neither |
| `clangd` | C++ language server for editor completion, diagnostics, go-to-definition |
| `bear` | records a `compile_commands.json` from a Make build so `clangd` understands the project |
| `podman` | runs the GCC 4.8.5 fidelity tier in a container |

Ubuntu's Podman has no unqualified-search registries configured, so images
must be named in full — `docker.io/library/gcc:4.8`, not `gcc:4.8`. A bare
name fails with `short-name ... did not resolve to an alias`.

### Python tooling (only if working on `main`)

```bash
pipx install poetry
poetry install
```

The trace-matrix generator (`scripts/build-trace-matrix.py`) is
standard-library-only and runs without Poetry.

---

## 3. Editor and language server

`clangd` needs a compilation database. Generate it with `bear`, and regenerate
whenever files are added to the Makefile:

```bash
cd ~/GIT/background-file-mover/cpp
make clean-all
bear -- make all
# writes cpp/compile_commands.json
```

`compile_commands.json` is generated output and is **not** committed.

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
podman run --rm -v ~/GIT/background-file-mover:/src \
    docker.io/library/gcc:4.8 sh -c "cd /src/cpp && make check"
```

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
| GCC 4.8.5 | container | **C++11 conformance on the SLES 12 system compiler** |
| SLES 12 SP5 | hardware | **deployability** — systemd, NFS qualification, e2e |

The GCC 4.8 job runs the **full test suite**, not a compile check. That is
what closes the gap between the instrumented build and the shipped build,
since the sanitizers never run against the GCC 4.8 compilation.

`gcc:4.8` is a *proxy*, not the target: Debian glibc 2.19 versus SUSE 2.22,
no systemd, no NFS. Deployability is verified on real hardware per
`docs/DEPLOYMENT.md`.

---

## 5. Fuzzing

Per ADR-0008, the untrusted-input path is fuzzed with libFuzzer under
ASan+UBSan. libFuzzer requires clang; the code under test is identical
because the source is strictly C++11-conformant and compiled from one body.

Every crash the fuzzer finds is minimized and **committed to the regression
corpus**, which converts a one-time finding into a permanent test case. That
retention is the part that carries the long-term value — fuzzers find bugs
once, corpora prevent them forever.

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

**Known gap:** the generator only scans `tests/` for pytest markers, so the
C++ tree reports 0 tested even though the Catch2 tags exist. A Catch2 tag
scanner is outstanding work; until it lands the matrix understates `cpp/`.

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
rather than technical, say so — ADR-0007 excludes BSD licences by internal
policy and states explicitly that it is not a compatibility finding, so a
future maintainer who checks compatibility, finds no conflict, and concludes
the entry is a mistake does not reverse it.

When a premise turns out to be wrong, correct it in place and keep a note of
what was wrong. ADR-0001 carries a correction-of-record block for exactly
this reason.

---

## 8. Vendored dependencies

Governed by ADR-0004 (pinning and provenance) and ADR-0007 (licence policy).

* Files under `cpp/third_party/` are **never edited**. Unavoidable changes
  live as `.patch` files applied at build time.
* Every entry in `cpp/VENDORED.md` records upstream URL, pinned tag, SHA-256,
  and licence.
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

## 10. `transcripts/`

Staging area for design material produced outside the repository, following
the `docs/CAPTURE.md` precedent: land it, mine it into requirements and ADRs
commit by commit, then delete it. Raw transcript content never becomes
reference documentation.

**An empty `transcripts/` is the ready signal for the next milestone drop.**
See `transcripts/README.md` for the triage rubric — inherited material is
triaged, not adopted, and has already been caught carrying a fabricated
premise.

---

## 11. Before you push

```bash
cd cpp
make clean-all
make check                                    # functional
make check SANITIZE=1                         # sanitizers
make check-valgrind                           # memcheck
cppcheck --enable=warning,portability --error-exitcode=1 \
         --inline-suppr --std=c++11 -Iinclude src/ tests/
podman run --rm -v ~/GIT/background-file-mover:/src \
    docker.io/library/gcc:4.8 sh -c "cd /src/cpp && make check"

cd ..
python scripts/build-trace-matrix.py --check   # traceability gate
```

CI runs the same set. Running it locally first is cheaper than a red branch.
