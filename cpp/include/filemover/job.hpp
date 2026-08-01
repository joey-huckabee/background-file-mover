#ifndef FILEMOVER_JOB_HPP
#define FILEMOVER_JOB_HPP

// M1: Core job types and state machine.
// Pure logic: no I/O, no threads, no clock access. Callers supply timestamps.
// Traces: L2-CORE-001..004, L3-CPP-001..015

#include <cstdint>
#include <string>

namespace filemover {

// L3-CPP-001: The job state enumeration SHALL contain exactly the states
// Queued, Renaming, Transferring, Done, and Failed.
enum class JobState {
    Queued,
    Renaming,
    Transferring,
    Done,
    Failed
};

// L3-CPP-002: to_string SHALL return a stable, unique, uppercase token per state.
const char* to_string(JobState state);

// L3-CPP-004: is_terminal SHALL return true for Done and Failed only.
bool is_terminal(JobState state);

// L3-CPP-003: is_legal_transition SHALL permit exactly:
//   Queued->Renaming, Renaming->Transferring, Transferring->Done,
//   Queued->Failed, Renaming->Failed, Transferring->Failed.
// All other pairs, including self-transitions, SHALL be rejected.
bool is_legal_transition(JobState from, JobState to);

struct Job {
    std::string id;
    std::string source_path;
    std::string dest_path;
    JobState state;
    std::int64_t created_at_ms;
    std::int64_t updated_at_ms;
    std::int64_t finished_at_ms;   // 0 until a terminal state is reached
    std::uint64_t bytes_total;     // 0 until sized by the transfer stage
    std::uint64_t bytes_moved;
    std::string error;             // non-empty iff state == Failed

    // L3-CPP-005: A newly constructed Job SHALL start in Queued with
    // created_at_ms == updated_at_ms == now_ms, finished_at_ms == 0,
    // byte counters zeroed, and an empty error string.
    Job(std::string job_id,
        std::string source,
        std::string dest,
        std::int64_t now_ms);

    // Attempt a state transition at time now_ms.
    // L3-CPP-006: transition SHALL return false and leave the Job unmodified
    //             if is_legal_transition(state, to) is false.
    // L3-CPP-007: A transition to Failed SHALL require a non-empty
    //             error_message; otherwise it SHALL be rejected.
    // L3-CPP-008: A transition to any state other than Failed SHALL require an
    //             empty error_message; otherwise it SHALL be rejected.
    // L3-CPP-009: On success, transition SHALL set state = to and
    //             updated_at_ms = now_ms.
    // L3-CPP-010: On a successful transition to a terminal state, transition
    //             SHALL set finished_at_ms = now_ms.
    // L3-CPP-011: On a successful transition to Failed, transition SHALL store
    //             error_message in error.
    bool transition(JobState to,
                    std::int64_t now_ms,
                    const std::string& error_message = std::string());

    bool is_terminal() const;
};

} // namespace filemover

#endif // FILEMOVER_JOB_HPP
