# Background File Mover

A durable background transfer coordinator for large simulation recordings, written in
**C++11** with a **REST** control plane.

Simulation orchestration on six Linux hosts records ~100 GB per run to a local NFS mount.
Moving that data synchronously stalls the hosts and delays the next run. Background File
Mover accepts a submitted recording set, returns a durable acknowledgement immediately,
and then moves the data in the background around a single atomic commit point: everything
before it is disposable, everything after it is idempotent. A source file is never
deleted until its destination is durably in place, so any failure retains the source.

It targets **SLES 12 SP5** — GCC 4.8.5, glibc 2.22 — and RHEL 9. That constraint shapes
the codebase more than any other decision; see `docs/LEGACY-PLATFORM-COST.md`.

## Highlights

- Runs under **systemd**, controlled over a hand-rolled HTTP/1.1 subset (ADR-0012).
- **SQLite** (WAL, `synchronous=FULL`) holds authoritative durable job state (ADR-0010).
- Filesystem work is **fd-relative** (`openat`/`renameat2`/`fstatat`), not path-based,
  so a racing adversary cannot swap a path between check and use.
- Every parser on untrusted input is fuzzed continuously with a committed regression
  corpus, and built to a written standard (`docs/HAND-ROLLED-COMPONENTS.md`).
- Fourteen independent CI gates, including a **GCC 4.8.5 fidelity tier** that runs the
  full test suite rather than just compiling.
- Full **L1/L2/L3 requirement traceability** (`docs/TRACE-MATRIX.md`), generated from
  both pytest markers and Catch2 tags.

## Status

**Under active construction — not yet shippable.** The JSON codec, configuration loader,
job state machine, rename template engine, and HTTP request parser are delivered and
tested. The durable store, job manager, transfer engine, socket server, and dashboard are
not yet built. In v1.0.0 scope, **48 of 226 requirements (21.2%)** carry test evidence.
`docs/TRACE-MATRIX.md` carries the live figure; `docs/ROADMAP.md` opens with where the
work stands and the **C1–C9** plan to v1.0.0.

The **Python implementation** (v0.4.2) was removed from this branch ahead of v1.0.0. It
remains on `main` and at the `v0.4.2` tag, and is still the version to deploy today.
v1.0.0 is deliberately **narrower** than v0.4.2 — claim semantics, integrity
verification, conservative deletion, and recovery-by-resumption are deferred to v1.1 and
retained verbatim in `docs/L1-REQ.md`.

## Quickstart (development)

```
cd cpp
make check                # build and run the suite, -Werror
make check-ci             # every gate, in a container, as CI runs them
```

See `CONTRIBUTING.md` for the full toolchain setup. The canonical checkout lives inside
WSL on a Linux-native filesystem — building under `/mnt/c` is unreliable and slow, and
`CLAUDE.md` records the measurements.

## Documentation

- `cpp/README.md` — build commands, CI tiers, design rules, REST API shape.
- `docs/L1-REQ.md` / `docs/L2-REQ.md` / `docs/L3-REQ.md` — requirements.
- `docs/TRACE-MATRIX.md` — generated forward trace, and the live coverage figure.
- `docs/CYBERSECURITY.md` — threat model and the v1.0.0 scope boundary.
- `docs/adr/` — architecture decision records.
- `docs/MAINTAINER-GUIDE.md` — dev setup and contribution workflows.

Documents describing the retired Python implementation are kept as the source material
for the rewrite and each opens with a banner saying so.

## License

Apache-2.0 — see `LICENSE`.
