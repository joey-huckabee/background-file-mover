# Rust increment 35: configurable source-space admission design

Documentation increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Defines [SOURCE-SPACE-ADMISSION-DESIGN.md](SOURCE-SPACE-ADMISSION-DESIGN.md).
No implementation, configuration parser, API, schema, dependency or runtime
behavior changes. The current binary rejects the proposed configuration object.

## Decisions captured

- Optional startup guard defaults off and can explicitly be disabled. When
  enabled, configurable absolute-byte and percentage margins both apply.
  Unknown/stale observations refuse new admission; errors never silently turn
  the guard off. Threshold/time bounds and example fragments are specified.
- Existing job-count and source/destination reservation limits remain mandatory.
  Claiming existing payload does not need another full payload allocation;
  sampled source availability must not double-charge those bytes.
- Gate new submission keys before durable acceptance. Resolve identical replay
  and conflicting content before the new-key gate, including a final serialized
  race check. Preserve accepted partial handoffs, pinned policy and normal
  missing/custody/ledger checks. Only ordinary all-file claims authorize 202.
- Read source statistics through bounded supervised child work with fresh
  scope-bound observations and no filesystem calls in API/status/SQLite owners.
  Unknown/timeouts cannot authorize new acceptance. Confirm exit before replacing
  a blocked child; cache observations do not survive process/policy changes.
- Proposed low/unavailable 503 responses create no job and release no paths.
  Cached global operator visibility is separate from reservation headroom and
  per-job review. Turning the guard off resets no existing review or reservations.

SA-01–18 define acceptance expectations for configuration, arithmetic/rounding,
refusal/restoration, unknown/blocked probes, replay/partial claims, concurrency,
restart, storage races and target compatibility. SC-075–081 are new stable
**future-design** situations, not newly supported runtime scenarios.

L1-SYS-030 is refined additively without changing its scope annotation or reusing
IDs. Protocol/API drafts, operator guide, roadmap and handoff link the design.
DOC-01/03/04/05 retain the implementation-dependent guide/example obligations;
the existing operator guide remains documentation of current behavior with an
explicit unavailable-feature note. The roadmap contains implementation and
qualification tasks rather than a completed policy-definition task.

## Inspection and validation boundary

Inspected current `Config`, `process`, `Store::accept`, claim/transfer capacity
checks and retention accounting. They establish existing strict configuration,
replay-before-job-limit handling, acceptance before claiming and independent
claim/attempt reservation checks. A new physical margin gate therefore needs a
replay-aware acceptance boundary, not a check after inserting a new job.

Checked the filesystem-statistics definitions against the Linux
[statvfs/fstatvfs manual](https://man7.org/linux/man-pages/man3/statvfs.3.html).
This is API research, not qualification of any implementation/backend or symbol
set. Quota/inode enforcement, physical reservation, old kernels, lost-lock fences
and production NFS remain outside this design's evidence.

Documentation checks cover both JSON fragments and their specified bounds,
arithmetic examples, all 18 distinct SA rows, unchanged prior 74 scenario IDs
plus seven new IDs, all six DOC entries, Markdown targets/table structure and
Git whitespace. All documentation checks and `build-trace-matrix.py --check`
passed. No Rust build/test, service walkthrough, native capacity test or
NFS fixture was run for this documentation-only change. Existing implementation
evidence through increment 33 is unchanged; no SA case is labeled passing.

Next implement a complete small local slice with configuration, pure decisions,
bounded measurement, replay-aware acceptance and cached visibility; keep the
option unavailable if prerequisites must land first. Every Rust build/test must
use the GNU/glibc-2.22 zigbuild/ELF/pinned-SLES gate. Qualify relevant blocked and
changed-storage cases with the retained container NFS fixture before claiming
that scope. Production NFS and deletion remain disabled; package experiments,
registration, offline repair and takeover stay deferred.
