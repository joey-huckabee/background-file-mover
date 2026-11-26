# Rust logging and operational observations

The [reviewed logging design](LOGGING-DESIGN.md) is implemented for qualification.
See the [operator guide's Logging section](RUST-OPERATOR-GUIDE.md#logging) for
settings, custody, rotation and failure behavior. Logging is default OFF with
exact legacy stdout/stderr and no logger resources. Enablement requires a file;
enabled events use journal severity prefixes and a private rotating file.

No new dependencies or shell commands are used by runtime logging. Records are
bounded and lossy, with fixed public event codes, numeric context and validated
operation/errno diagnostics; secrets and
arbitrary request/error/config values are never rendered into enabled logs.
Full/slow sinks stay off claim/copy/delivery loops. This does not reserve free
space or isolate physical storage: the user permits a shared disk.

Coordinator local WSL test and OFF/info performance results are recorded in
[increment 172](RUST-INCREMENT-172.md). The user accepted the delivery benchmark
as #115's performance proof on 2026-11-25. Sustained load is recorded as “no
slowdown observed; too noisy to bound at 2%”, not a separate quantitative gate. The coordinator reports fmt/Clippy clean
before these review fixes. Fresh Rust checks, both SLES modes and remaining
validation are pending. Local results are not a claimed target pass. See also [current operator statuses](RUST-OPERATOR-GUIDE.md),
[lifecycle handling](RUST-RESTART-RUNBOOK.md) and [release closure](RUST-RELEASE-CLOSURE.md).
All release gates remain open; production NFS and operational deployment remain
disabled/unapproved. Logging never supplies transfer/deletion/recovery authority.

## Local performance comparison

In the Rust workspace, with the gate-provided matching executable and SQLite
flags, run the existing `timer_retries_do_not_starve_under_sustained_sender_load`
API test with `FILE_MOVER_TEST_LOGGING_LEVEL=off`, `info` and `debug`, and with
`FILE_MOVER_TEST_SUSTAINED_SENDERS=0` and `6`. The logging selector is a test
helper that writes the fixture config, not a runtime environment override.

Run `logging_fixed_work_delivery_benchmark -- --ignored --nocapture` at the same
three levels. It transfers the same eight 1 MiB jobs and reports fixed-work
elapsed time/bytes per second. Alternate at least five OFF/info pairs under the
same host/cache/storage conditions; compare late-file handoff elapsed time and
fixed-work completion time. Info elapsed/OFF elapsed must be at most 1.02 in the
delivery benchmark, with uncertainty reported. The user's 2026-11-25 acceptance
uses that benchmark; sustained timing remains supporting regression evidence.
Preserve failed and inconclusive runs;
do not infer transfer throughput from raw producer request rate. Debug and
saturated-sink tests provide stress evidence, not replacements for info acceptance.
No performance result has been measured in the cloud worker environment.
