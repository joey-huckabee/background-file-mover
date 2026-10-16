# Rust increment 34: operator status and recovery guide

Documentation increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Delivers DOC-03 in [RUST-OPERATOR-GUIDE.md](RUST-OPERATOR-GUIDE.md). No Rust,
dependency, configuration, schema, retry policy or qualification code changes.
Production NFS, deletion, offline repair and registration remain disabled/deferred.

## Delivered explanations

The guide distinguishes durable acceptance, all-file claim handoff, delivery
condition and consumer commitment. Worked partial status projections explain
30/60-second capacity waits, the three-failure review threshold, persisted
deadlines, shared failure counts and historical retry rows after commitment.

Shell examples inspect health/job/retention and submit audited delivery resume
or exact-file missing reset. Each mutation starts from an actual observed epoch,
requires a reviewed reason and preserves the command file for identical replay.
The guide covers lost responses, stale/conflicting commands, independent epochs,
audit limits and HTTP errors without assigning new duties to the recorder.

Capacity triage explains current reservation accounting, unmeasured/old attempts,
physical-space limits and why neither status nor logs authorize reclamation.
Diagnostic examples separate operation/errno facts from scheduling and effect
authority. Refusal guidance preserves allocations, final names, enrollment,
original state and inherited worker custody; it introduces no manual repair,
backup restoration, takeover or repeated blind resume procedure.

The scenario catalog links the delivered guide and retains DOC-01/02/04/05 work
plus deferred DOC-06. SC-033 now backfills schema-11 migration evidence and
separates structural upgrades from source pairing and destination authorization.
All 74 existing stable situation IDs are retained; no new runtime scenario was
introduced. README entry points, retry policy, handoff and AGENTS link the guide.
The roadmap remains future-only.

## Validation and evidence boundary

Checked the command examples against current `file-mover` request/response
handlers and `mover-store` operator, missing-reset and retention implementations.
Compared recovery explanations with increments 07–10, 24–33, the retry policy
and scenario catalog. Parsed all fenced JSON (including both shell here-doc
requests), checked request keys against the Rust input structs, and checked
shell block syntax with Git Bash `bash -n`. Checked local Markdown targets in
changed documents, the unchanged 74 unique SC IDs, all six DOC keys and Git
whitespace. These are documentation checks, not an executed service walkthrough.

No Rust build/test or NFS fixture was run for this documentation-only increment.
Increment 33's [production](RUST-SLES-EVIDENCE.json) and
[qualification](RUST-SLES-QUALIFICATION-EVIDENCE.json) gates remain evidence for
their exact source/artifacts: 164/165 tests per debug/release profile, zigbuild
GNU/glibc 2.22, ELF audits and pinned SLES userspace execution. Its
[selected NFS report](RUST-NFS-CAPACITY-BACKOFF-EVIDENCE.json) covers six capacity
cases and four selected long outages alongside its retained baseline checks;
it is not a new full NFS regression or a production approval. Existing CI run
[38902474727](https://github.com/joey-huckabee/background-file-mover/actions/runs/38902474727)
for implementation commit `03e6940` completed successfully before this increment.

Next admission work should build on the existing job/byte reservation limits:
define source-space margins and sustained destination-shortage behavior, then
qualify before changing effects. Do not describe those existing limits as absent
or equate them with physical free-space admission. Full producer/consumer,
shutdown/restart and deployment guides remain in the catalog backlog.
