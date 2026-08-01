# background-file-mover — C++ implementation

The v1.0.0 C++11 implementation: a REST-triggered durable transfer daemon for
SLES 12 SP5 and RHEL 9. Replaces the Python implementation's `AF_UNIX` control
socket with an HTTP/1.1 REST interface (ADR-0002).

Scope for v1.0.0 is deliberately narrower than the Python implementation —
see the **v1.0.0 scope** section of `../docs/L1-REQ.md` for exactly which
guarantees are deferred to v1.1 and why.

## Build & test

    make check                # build and run the suite for this toolchain
    make toolchain            # print the resolved BUILD_DIR
    make clean                # remove only this toolchain's artifacts
    make clean-all            # remove every toolchain's artifacts

Flags: `-std=c++11 -Wall -Wextra -Werror`. Vendored headers are included via
`-isystem third_party` so they do not trip `-Werror`. There are **no**
per-object warning exemptions; `L2-ARC-007` forbids adding one without an ADR.

Build output goes to `build/<machine>-<version>-<tier>`, keyed on the compiler
that produced it, so the modern, gcc:4.8, and sanitizer tiers cannot overwrite
one another. Override with `make BUILD_DIR=/somewhere/else` when needed.

Build on the Linux-native filesystem, not `/mnt/c` — see the "Why not /mnt/c"
section of `../CLAUDE.md`.

## Layout

    include/filemover/   public headers
    src/                 implementation
    tests/               Catch2 v2 test suite (natural-order assertions)
    third_party/         vendored pinned single headers (see VENDORED.md)
    LICENSES/            license texts for vendored dependencies

Requirements and decisions live at the repository root, shared with the
Python implementation during the migration:

    ../docs/L1-REQ.md    system requirements, with v1.0.0 status per requirement
    ../docs/L2-REQ.md    architectural derivations
    ../docs/L3-REQ.md    implementation obligations (L3-CPP-*)
    ../docs/adr/         MADR-format architecture decision records

## Memory safety & security gates (all CI-enforced)

    make check                # functional suite, -Werror
    make check SANITIZE=1     # AddressSanitizer + UBSan + LeakSanitizer
    make check-valgrind       # memcheck, fails on any leak or invalid access
    cppcheck (CI)             # static analysis over project sources

Coverage-guided fuzzing (libFuzzer) gates the JSON parser per ADR-0008.

**Design rules.** RAII only, no naked `new`/`delete`. Never `system(3)` — the
exec transfer strategy uses `fork`/`execvp` with argv arrays, so no shell
injection surface exists. Caller-supplied timestamps in core code, so the
state machine stays deterministic and clock-free. JSON decoding is
strict-reject (unknown members, embedded NULs, trailing bytes, duplicate
keys) per ADR-0009. Request bodies are size-capped at the HTTP layer
(`L1-API-004`).

## CI tiers

| Tier | What it proves |
|---|---|
| modern g++ | fast feedback, plus the sanitizers/fuzzing GCC 4.8 cannot host |
| `gcc:4.8` container | C++11 conformance on the SLES 12 system compiler — **runs the full suite, not just a compile** |
| real SLES 12 SP5 | deployability: systemd, NFS qualification, e2e. Not in CI — see `../docs/DEPLOYMENT.md` |

The `gcc:4.8` container job clones the repository with plain `run` steps
because node-based actions cannot execute against its old glibc. For a
private repository, switch the clone URL to the tokenized form shown in the
workflow comment.

`gcc:4.8` is a *proxy* for the target, not the target: Debian glibc 2.19 vs
SUSE 2.22, no systemd, no NFS.

## REST API (target shape)

    POST /api/jobs        submit {source, dest}
    GET  /api/jobs        list jobs
    GET  /api/jobs/{id}   single job
    GET  /api/status      aggregate stats (dashboard polls this)
    GET  /                dashboard

All responses use `Connection: close` (ADR-0002). The daemon serves plaintext
HTTP and binds to loopback by default; TLS is terminated by a reverse proxy
where required (ADR-0003).

> **v1.0.0 ships no authentication or authorization.** The bind address is the
> only access control. Any non-loopback deployment requires an authenticating
> proxy in front. See the security note in `../docs/L1-REQ.md`.
