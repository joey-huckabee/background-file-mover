# E5: Tokio runtime and signals

Tokio replaces direct signal-hook at the user's request. It is a broader
dependency: the qualified candidate is Tokio 1.53.2 with defaults disabled and
only `rt,signal,sync,time,net,io-util`. No macros, multi-thread scheduler, fs,
process, parking_lot, full or io-uring feature is requested. Unix signals still
bring in signal-hook-registry transitively; the runner records the actual graph.

Run `python experiments/e5-tokio/run.py` with Podman on PATH. It builds the std
control, isolated Tokio probe and cumulative E1–E5 probe using Rust 1.99.0,
pinned cargo-zigbuild/Zig and GNU/glibc 2.22 with baseline x86-64 flags. It tests
the exact inspected binaries in pinned SLES 12 SP5 userspace, UID/GID 1000,
eager binding, no capabilities and container-loopback networking only.

The current-thread executor enables IO/timers and caps the blocking pool at
two threads. Tests cover async TCP, timeout/channel/timer progress during
blocking work, semaphore admission, actual completion of a started blocking
task after abort, and explicit worker draining before runtime shutdown.
The cumulative probe repeats the E1/E2/E3/E4 batteries, then passes a Tokio TCP
POST through httparse and strict typed JSON to a blocking SQLite transaction,
with commit preceding the 201 response.

The host harness delivers actual SIGTERM/SIGINT to isolated and cumulative
subprocesses after an explicit READY marker. Cases cover idle wakeup, ongoing
fsync/SQLite work, bursts of stop signals and three drop/recreate cycles in one
process. Signal masks are checked on the main and blocking-worker threads;
SIGPIPE remains ignored by Rust startup and broken-pipe writes return errors.
Signals are coalescing notifications: the fixture checks a sticky stop and
completed work, never one event per kill invocation. Tokio leaves its registered
handlers process-global when streams drop; the fixture checks that behavior.

SQLite uses local WAL/FULL storage. Shutdown stops new work and joins already
started blocking jobs. Tokio abort/shutdown_timeout does not cancel a running
filesystem/SQLite operation; production must preserve bounded admission and
the separate NFS isolation decisions in R1. This experiment does not settle the
final runtime sizing, full TCP server design, NFS hangs or forced-stop policy.

The runner checks ELF loader, glibc/library imports, six negative audit controls,
crate features/licenses, host macros and copied binary hashes. Logs, binaries
and source/vendor archives remain in ignored `results/<run-id>/`; created
containers are removed. Old-kernel/CPU execution and the user's own builder
remain unqualified. The [NFS fixture note](../../docs/NFS-TEST-FIXTURE.md) stays
available; no NFS server is needed for this experiment.

`--reuse-build <run-id>` verifies unchanged archived Rust/C++/corpus inputs and
pinned image configuration before repeating runtime checks. Changed compiler,
crate/features or build inputs require rebuilding and requalification.

After a passing run, execute `python experiments/e5-tokio/random_fallback.py
<run-id>` to test the weak getrandom dependency. A separately built, test-only
seccomp launcher verifies its filter, then runs the inspected Tokio binary with
GRND_INSECURE returning EINVAL and with all getrandom calls returning ENOSYS.
It also inspects the pinned SLES libc's actual exported symbols. Supplementary
logs/source/helper hashes are retained under `results/<run-id>/entropy/`.
The helper is not part of the service. These targeted fallbacks supplement
userspace validation; they do not emulate the complete SLES kernel.
