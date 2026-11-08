# Release checks after UUID runtime integration

2026-11-08. The user authorizes release checks after PR 6 merged as
`0b5d0c1716a31aacf530927d76d12a37df73f07d`. This increment adds a disposable
compatibility runner and corrects active release documentation. It changes no
Rust runtime, dependency, schema, deployment or production switch.

## Current verdict

**Not release-ready. All eight FR gates remain open.** Passing the implementation
checks below does not supply missing release features or waive storage/lifecycle
qualification. No operational state, NFS mount or installed service is touched.

| Existing obligation | Current result / remaining work |
|---|---|
| RC-01 / FR-01 contract | Producer UUID/v2 slice is implemented and checked. Full supported API/admin/access freeze and consumer acceptance remain open. |
| RC-02/03 / FR-01 remote access | Protected producer ingress, caller binding, selected authenticated proxy and end-to-end remote qualification remain missing. Current runtime is loopback-only. |
| RC-04-17 / FR-02/03/05 recovery | Existing scoped tests remain credited. Allocation-intent ordering, remaining capacity/NFS/delayed-effect and shipping lifecycle cells remain open. No new NFS experiment is run here. |
| RC-18/19 / FR-04 cleanup | Configurable postcommit cleanup remains unimplemented/unqualified. Source deletion remains disabled. |
| RC-20 / FR-05/06 compatibility | Guarded schema-11 migration and UUID/mixed runtime exist. This increment checks actual retained predecessor/current executables on disposable state. Shipping cutover, surviving-worker matrix and a positive supported working rollback remain separate. Incompatible refusal is not working rollback. |
| RC-21/22 / FR-06/07 artifacts | Both required local/CI SLES modes and disconnected prototype bundle checks passed for the unchanged runtime. Shipping account/unit/confinement, proxy/native dependency package and exact shipping candidate remain open. |
| RC-23/24 / FR-07/08 evidence/guides | Requirements/test traceability, complete guides and the full remote/capacity/cleanup/cutover release walkthrough remain open. |

The finite [release matrix](RUST-RELEASE-CLOSURE.md) remains authoritative.
D01-D05 (mount profile, proxy, lifecycle support, unproven storage faults and
supported cutover/rollback) are unresolved at their respective boundaries.

## Executable checks

`scripts/check-release-compatibility.py` requires three retained production gate
packs. It validates their passed reports, source archives against the declared
Git trees, and actual executable hashes before running each debug/release pair
in the pinned SLES userspace, with network disabled and application UID/GID 1000.
It does not rebuild or treat a host Cargo test as SLES evidence.

```sh
python3 scripts/check-release-compatibility.py \
  --schema11-gate rust/validation/20261105T033804Z-7c6fa900 \
  --legacy-gate rust/validation/20261108T051411Z-4aa8c7a9 \
  --gate rust/validation/20261108T162438Z-ca1847a4 \
  --output rust/validation/NEW-UNUSED-RELEASE-CHECK-DIRECTORY
```

The schema-11 predecessor is `2a31f233982669a8821bee42bf9691b27c1f39e7`;
the schema-12 codec-only predecessor is `215cf93965f946f07cab99d2c0d25281ae743d78`.
The target gate has the same Rust tree as merged PR 6:
`a3afcf2e95ac22a12356c1b66863f32fc7178c57`.
Every run uses new disposable roots and a new output directory. Failure evidence
is retained; cleanup removes only the container that the runner itself created.

The bounded cases are:

- Normal schema-11 refusal followed by explicit verified migration. Compare all
  original typed table columns and sequence values in stopped disposable copies.
- Live predecessor/target mutual exclusion without stopping the admitted owner.
- Partial legacy refusal before payload bootstrap; the compatible predecessor
  completes handoff. Temporarily deny new destination allocation in the fixture
  so the target must recover an unfinished whole-set legacy delivery afterward.
- Preserve legacy numeric paths, indices, enrollment and original v1 bytes;
  verify recovered bytes and manifest sizes/hashes against known inputs.
- Current UUID publication and mixed-state predecessor refusal. Restart with
  permuted replay and producer-reused leaves; preserve original receipt, payload
  identities and exact v2 bytes, sizes and hashes.

## Actual evidence

Both debug and release compatibility runs **passed** using checker source
`a44c24991d50ac2a521ad013e0e41881e45e8aba`. Raw output:
`/home/joey/GIT/background-file-mover-testing/rust/validation/release-119-pair-3`.
The run lasted 19:10:16-19:18:36 UTC. Both profiles preserved all original columns
in 15 tables (including sqlite_sequence), recovered job 2 from Claimed/Retrying
to committed v1, allocated fresh UUID job 3, preserved original v1/v2 files and
receipts, and passed both live exclusion directions. Both cleanups succeeded;
no fixture containers remain. [Recorded evidence](RELEASE-CHECK-EVIDENCE.json)
contains the exact report/source/executable hashes, raw paths, snapshots and
limits, plus reverified local build/bundle evidence.

These are actual disposable executable-pair results, not a shipping systemd,
remote-access, physical durability, surviving-worker cross-version matrix or
positive working-downgrade qualification.
The first driver run (`release-119-pair-1`) failed its readiness observation:
the HTTP helper omitted request transport into the container. The daemon had
reached readiness; the driver is corrected and the failed report retained with
clean container removal. The second run (`release-119-pair-2`) correctly failed
when its same-port contender hit AddrInUse; contenders now use a separate port
and require the actual durable-guard refusal. Independent review also found missing known-input
payload assertions; those are added before recording passing evidence.

Reference checks passed: 70 schema definitions, 108 structural cases, 11 semantic
examples, 15 routes/reference checks, seven unchanged request-identity vectors,
the existing golden/bound and Rust fixture copies. Retry-context reference checks
passed four known answers and 52 decoding cases. All 56 Python tooling tests
passed. These are contract/tooling checks, not authenticated HTTP or consumer
acceptance qualification.

PR 6 records both local SLES modes: 264 production and 268 qualification tests
per debug/release profile, five existing ignored helpers per profile, strict
Clippy and ELF audits. All 73 Rust inputs and 40 executable hashes were checked;
cleanup was clean. Both final-head CI modes passed. Because the Rust inputs are unchanged, the exact-input build evidence is reused;
no new Rust build or full-suite rerun is claimed for these documentation/fixture
changes. GitHub path filters do not trigger the Rust workflow for this delta.

The prototype offline bundle passed pinned-SLES network-disabled install,
verification, UUID/v2 transfer, restart/replay and tamper/refusal checks. Windows
copy: `rust/validation/runtime-118-bundle/file-mover-0.1.0-prototype-e711b4381c72-linux-x86_64.tar.gz`.
SHA-256: `579cea97ca054aa9a437cb8550b04cbf8dac9b775e18ee5bd6906313a3ae842e`.
This is a prototype artifact, not a published release or installed service.

## Review and scope

The coordinator owns the runner, disposable checks and integration. The existing
cloud reviewer independently audits blockers and the new driver; its concrete
payload-verification finding is addressed. Bounded follow-up review found no
actionable issues in that fix or the separate-port exclusion delta. Review/test
results remain scoped to
the exact inputs recorded above. Costs are unknown; no fixed fan-out improvement
is claimed. Production NFS/deletion, deployment and operational conversion remain
unauthorized. Missing release features require their own bounded implementation.
