#ifndef FILEMOVER_MANAGER_HPP
#define FILEMOVER_MANAGER_HPP

// C4: the job manager and worker pool. The first threads in the project.
//
// Traces: L2-MGR-001..003, L2-LIF-002, L2-LIF-004, L2-LIF-005,
//         L2-RTY-001, L2-RTY-002, L2-RTY-003, L2-RTY-005, L2-RTY-006
//
// Two shapes here are requirements rather than preferences.
//
// The constructor takes a store *path*, not a store. L2-JOB-003 requires a
// connection per thread, so each worker opens its own — sharing one handle
// across threads is exactly what that requirement exists to prevent, and an
// API that accepted a JobStore& would make the mistake the natural thing to do.
//
// Time comes from an injected clock. Retry is defined in terms of "not before
// next_retry_ms", and a test for that which sleeps is slow and occasionally
// wrong. It also removes the workaround C3 needed, where the move engine
// derived timestamps from the job record because nothing had a clock.

#include <cstddef>
#include <cstdint>
#include <string>

#include "filemover/config.hpp"
#include "filemover/fsops.hpp"
#include "filemover/mover.hpp"

namespace filemover {

// Milliseconds since an arbitrary epoch. Monotonic is sufficient: every use is
// a comparison or a delta, never a wall-clock date.
typedef std::int64_t (*ClockFn)(void* user_data);

// L2-LIF-005: lifecycle commands reject an unknown job or an invalid state
// transition with a typed error, never panicking or corrupting durable state.
// Typed rather than a bool plus a string so a caller can branch on the reason
// without parsing prose.
enum class CommandResult {
    Ok,
    UnknownJob,
    InvalidState,
    NotRunning,
    StoreError
};

const char* to_string(CommandResult result);

class JobManager {
  public:
    JobManager(const std::string& store_path, const Config& config);
    ~JobManager();

    // Opens the manager's own store connection and starts the workers.
    bool start(std::string& error);

    // L2-MGR-003: stop intake, let in-flight work finish, join every worker.
    // Idempotent, and safe to call without a preceding start().
    void shutdown();

    bool is_running() const;

    // Records the intent durably, then makes the job runnable. Recording
    // first is L2-JOB-013 — the engine refuses a job it cannot find, so the
    // ordering is enforced rather than merely intended.
    CommandResult submit(const std::string& job_id,
                         const MoveRequest& request,
                         std::string& error);

    // L2-LIF-004. A paused job is not dispatched; resume returns it to the
    // runnable queue. Pausing a job already running does not interrupt it —
    // the move is atomic past the commit point and tearing it in half is the
    // thing being prevented.
    CommandResult pause(const std::string& job_id, std::string& error);
    CommandResult resume(const std::string& job_id, std::string& error);

    // Cancellation at v1.0.0 removes a not-yet-started job and marks it
    // FAILED. It does NOT introduce CANCELLED_RETAINED — that state and its
    // source-retention semantics are L2-LIF-001/003, deferred with
    // L1-SYS-003. A job already in flight is refused rather than torn in half,
    // which is the cooperative-stop-at-a-safe-point reading of L2-LIF-002:
    // with a rename engine the safe points are the phase boundaries.
    CommandResult cancel(const std::string& job_id, std::string& error);

    // L2-RTY-006: manual retry of a retained failed job. Returns it to QUEUED
    // and clears the retry schedule so it runs at the next dispatch.
    CommandResult retry(const std::string& job_id, std::string& error);

    // Moves retry-scheduled jobs whose time has come onto the runnable queue.
    // Called by the caller's loop rather than by an internal timer thread, so
    // tests advance an injected clock instead of sleeping. Returns how many
    // became runnable.
    std::size_t pump(std::string& error);

    // Blocks until the queue is empty and no worker is mid-job, or the budget
    // is exhausted. For tests: a deterministic alternative to sleeping and
    // hoping. Returns false on timeout.
    bool wait_idle(int timeout_ms);

    std::size_t runnable_count() const;
    std::size_t active_count() const;

    void set_clock(ClockFn fn, void* user_data);
    void set_strategy(MoveStrategy strategy);

    // Forwarded to every worker's engine, so a test can hold a worker at a
    // chosen phase and make an interleaving happen rather than hope for it.
    void set_phase_hook(MoveEngine::PhaseHook hook, void* user_data);

  private:
    JobManager(const JobManager&);
    JobManager& operator=(const JobManager&);

    struct Impl;
    Impl* impl_;
};

}  // namespace filemover

#endif  // FILEMOVER_MANAGER_HPP
