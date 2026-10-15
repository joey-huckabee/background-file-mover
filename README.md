# Background File Mover

**Rust redesign work:** E1–E5 compatibility experiments and the next-session
direction are on `feature/rust-transfer-coordinator`. Read
[the handoff](docs/RUST-DIRECTION.md) and [CONVERSATION.md](CONVERSATION.md).
Experiments are stopped. The first dependency-free [Rust core slice](rust/README.md)
has executable protocol tests and [SQLite acceptance](docs/RUST-INCREMENT-02.md).
It now has [protected local claims](docs/RUST-INCREMENT-03.md) and a
[local submission endpoint](docs/RUST-INCREMENT-04.md), plus a
[verified single-file transfer command](docs/RUST-INCREMENT-05.md) and
[automatic local delivery/manifests](docs/RUST-INCREMENT-06.md) and
[operator job status](docs/RUST-INCREMENT-07.md), plus
[audited delivery resume](docs/RUST-INCREMENT-08.md) and
[audited missing-file deadline reset](docs/RUST-INCREMENT-09.md).
Read-only [retention accounting](docs/RUST-INCREMENT-10.md) is also implemented.
Background copy/verification now uses [supervised child workers](docs/RUST-INCREMENT-11.md).
[Claim and publication operations](docs/RUST-INCREMENT-12.md) now use children too.
[Recording sessions](docs/RUST-INCREMENT-13.md) isolate runtime destination opening,
allocation, manifest writing and custody checks.
[Hard-mount boundary checks](docs/RUST-INCREMENT-14.md) exposed source bootstrap
blocking during outages. [Startup isolation](docs/RUST-INCREMENT-15.md) now keeps
signal handling responsive while custody is pending.
The [retained NFS qualification build](docs/NFS-QUALIFICATION.md) exercises the
same worker code in an isolated fixture; production NFS remains disabled.
[Owned no-clobber fallback and diagnostics](docs/RUST-INCREMENT-17.md) resolve
the fixture's rename refusals and retain explicit interrupted-link recovery.
[Runtime qualification](docs/RUST-INCREMENT-18.md) now exercises selected Rust
worker outages, partial-copy recovery and custody after coordinator death.
The maintained [Rust scenario catalog](docs/RUST-SCENARIOS.md) explains producer,
consumer and operator situations addressed so far and tracks the remaining user
guides. Update it as each increment adds or changes behavior.
[Source-read and verification-read qualification](docs/RUST-INCREMENT-19.md)
also passes in both profiles with observed blocked readers and validated recovery.
[Claim/file link interruption](docs/RUST-INCREMENT-20.md) now preserves and
reconciles the exact two-name NFS intermediates in both profiles; see catalog
scenarios SC-049/050 for producer and consumer behavior.
[Longer outage qualification](docs/RUST-INCREMENT-21.md) adds three-minute blocked
claim/verification checks, same-ID retry/backpressure observations and live recovery.
See SC-051/052 and the increment evidence for the qualified scope.
Offline inspection and repair are deferred; prioritize remaining worker isolation
and controlled NFS qualification. Preserve [the repair design](docs/RETENTION-REPAIR-DESIGN.md).
Every build/test uses the zigbuild/SLES gate.
Registration/authentication is deferred while tested increments develop. The C++
implementation described below remains the reference, not the intended Rust architecture.

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
