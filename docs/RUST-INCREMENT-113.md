# Rust development baseline integration and C++ deprecation

2026-11-07. The user authorizes merging the accumulated Rust coordinator work
into `main`, then using small reviewed increments. C++ is deprecated and retained
as historical reference. This is an integration checkpoint, not release,
deployment, migration apply, UUID/v2 activation or operational-state authorization.

## Integration scope and audit

Base main is `a6efb3d0964f4b5914f918a12876b4d0dc6d4717`. The previous Rust tip is
`6ddb69c10c43fed702d34aeda69bb3a262a730e3`, 232 commits ahead and zero behind.
The baseline adds the Rust coordinator, retained qualification tooling/evidence,
packaging and approved contract/design records. The original C++ runtime,
Makefile, vendored dependencies and configuration are preserved. Its only tree
change in this integration closeout is the deprecation notice in `cpp/README.md`.

The existing trace-matrix generator has one wording correction relative to main:
countable deferred requirements are no longer mislabeled as only L2/L3. It still
discovers historical Python/C++ tests; Rust release traceability remains a known
release-closure gap, not a qualification claim introduced by merging.

All four C++-specific workflows (build CI, fuzzing, CodeQL, SonarCloud) retain
their job/step definitions and action/tool pins, but become manual-only. Daily/
weekly schedules and automatic PR/push triggers are removed for this deprecated
implementation. Rust SLES CI stays enabled with both production/qualification
modes. No installer, deployment, release/tag publication or operational-state
command is triggered by a main merge. No repository protection setting or check
requirement is bypassed or changed by this work.

README, CONTRIBUTING, cpp/README, AGENTS, CLAUDE, the roadmap and agent workflow
now identify Rust as active, C++ as deprecated, and main as the integration base
for short-lived feature/fix branches. Historical C++ guidance/evidence remains
visible as historical material. Each new implementation increment uses a reviewed
PR with applicable checks passing; production release approval stays separate.

## Validation boundary

The compiled Rust tree remains `6b2c0c13e0e08105d88e2c95bb635f89d0950232`.
[Increment 112](RUST-INCREMENT-112.md) and
[its evidence](STATE-BACKUP-EVIDENCE.json) record passing local exact-target SLES
production/qualification gates in debug/release (233/236 tests per profile),
67 Git-matched source inputs and 40 independently rehashed executables. GitHub
Rust CI also passed for `785c7a9` in run `42034971715`, both modes. These results
validate their named source inputs, not a new production release.

For this integration, validate workflow YAML and compare every legacy workflow's
jobs/permissions/pins to its predecessor; allow only name, trigger and explanatory
comment changes. Record the independent integration review and fresh PR checks
before merging. No C++ build rerun is claimed when only its documentation and
workflow scheduling change. No Rust build input is changed by this closeout.

The integration PR records independent review, exact check runs and merge
acceptance. Its GitHub merge record supplies the final merge SHA/time; this
document does not declare release readiness or waive any required check.

All eight release gates remain open. Production NFS/source deletion, migration
apply and new UUID/manifest-v2 runtime remain disabled. No operational state or
payload is modified, no release tag is created, and no old branch is deleted.
