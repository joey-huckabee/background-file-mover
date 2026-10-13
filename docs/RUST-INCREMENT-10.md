# Rust retention accounting inspection

`GET /api/v2/retention` and `GET /api/v2/jobs/{job_id}/retention` now expose
read-only conservative database accounting. This is the first retention-tooling
slice; it does not inspect or repair filesystem orphans, reclaim staging, delete
sources or release reservations. The next effects must follow
[RETENTION-REPAIR-DESIGN.md](RETENTION-REPAIR-DESIGN.md).

The JSON response has `details` containing scope, retained/committed job counts,
claim-intent and confirmed-claim counts, unmeasured files, source/destination
reserved bytes, destination attempts grouped by durable phase, and the current
process's configured limits. All byte values are exact decimal strings; totals
use checked u128 arithmetic, including values larger than u64. Counts are JSON
integers. Missing per-job IDs return 404; canonical ID/method/body rules match
the existing read API. Existing submission responses are unchanged.

Source bytes include every recorded claim intent's observed size, even before
its claim receipt. Files without an intent are counted as unmeasured; producer
size assertions do not become measured reservations. Destination bytes charge
the full observed source size once for every recorded attempt, including old
interrupted attempts and published files. Committed jobs and retained sources
continue to count. The report shares the exact byte-summing function used by
admission checks; it does not implement a second accounting rule.

Only the global report exposes `global_headroom`: new job slots, independently
available source/destination reservation bytes and an `over_limit` flag.
Headroom saturates at zero when startup limits are below existing reservations.
Replays remain possible at capacity. The per-job report sets global headroom
to null; one job's totals cannot establish global admission capacity.
Configured limits describe this process's startup policy, not durable quota
metadata. Library read-only opens without configuring limits report null limits.

Every response explicitly states `filesystem_inspected:false`,
`unreceipted_allocations_accounted:false`, and
`automatic_reclamation_enabled:false`. Reservations are not physical disk usage,
free space or proof of current custody. Directory/database/manifest overhead and
allocations without receipts are not measured. An `Intent` attempt can contain
partially copied bytes; do not infer emptiness or cleanup authority from its phase.
The report's `source_paths_released:false` grants no recorder handoff or cleanup.

A single SQLite read transaction returns a fixed-sized report through the
existing eight-slot operator worker. Rows are streamed rather than collected
into job/object lists. Rust result/row-buffer memory and output are bounded, but scan time grows with the
ledger and currently has no SQL cancellation deadline. The two-second API wait
does not cancel an admitted query; a large scan can delay other SQLite commands.
Production query scheduling/cancellation and paginated object inventory remain
future work. There is no source/destination filesystem inspection on the report
path; SQLite still reads local state.

Tests exercise empty and unknown scopes, pending observations, exact totals
beyond u64, unchanged admission behavior, old attempts charged alongside
published files, retained committed sources, read-only restart, current headroom,
route validation and an unreceipted test allocation remaining untouched and
explicitly outside database accounting. This provides partial Rust evidence for
`L1-SYS-030` (bounded outage admission) and aggregate/individual inspection in
`L1-API-002`. It does not complete aggregate operational status, physical-space
qualification, orphan discovery or repair. Historical C++ scopes/trace coverage
are unchanged; formal Rust trace discovery remains roadmap work.

No dependency, schema, feature or toolchain change is introduced. Platform
results are recorded in [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).
Keep container-only glibc 2.22 qualification, registration deferred and source
deletion disabled. Next: offline custody/orphan inspection and durable allocation
intent/fencing prerequisites before implementing repair effects.

The native WSL gate passed all 88 tests in each profile on the pinned SLES
userspace. All 20 emitted executables passed ELF/loader/library audits and require
at most GLIBC_2.18. The six audit rejection controls passed, the 42-package Linux
graph/features stayed unchanged, and container cleanup completed without errors.
This is userspace qualification, not proof of old-kernel/CPU or NFS behavior.
