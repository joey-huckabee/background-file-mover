#include "filemover/job.hpp"

namespace filemover {

const char* to_string(JobState state) {
    switch (state) {
        case JobState::Queued:       return "QUEUED";
        case JobState::Renaming:     return "RENAMING";
        case JobState::Transferring: return "TRANSFERRING";
        case JobState::Done:         return "DONE";
        case JobState::Failed:       return "FAILED";
    }
    return "UNKNOWN"; // unreachable with a valid enum value
}

bool is_terminal(JobState state) {
    return state == JobState::Done || state == JobState::Failed;
}

bool is_legal_transition(JobState from, JobState to) {
    switch (from) {
        case JobState::Queued:
            return to == JobState::Renaming || to == JobState::Failed;
        case JobState::Renaming:
            return to == JobState::Transferring || to == JobState::Failed;
        case JobState::Transferring:
            return to == JobState::Done || to == JobState::Failed;
        case JobState::Done:
        case JobState::Failed:
            return false;
    }
    return false;
}

Job::Job(std::string job_id,
         std::string source,
         std::string dest,
         std::int64_t now_ms)
    : id(std::move(job_id)),
      source_path(std::move(source)),
      dest_path(std::move(dest)),
      state(JobState::Queued),
      created_at_ms(now_ms),
      updated_at_ms(now_ms),
      finished_at_ms(0),
      bytes_total(0),
      bytes_moved(0),
      error() {}

bool Job::transition(JobState to,
                     std::int64_t now_ms,
                     const std::string& error_message) {
    if (!is_legal_transition(state, to)) {
        return false;                                   // L3-CPP-006
    }
    if (to == JobState::Failed && error_message.empty()) {
        return false;                                   // L3-CPP-007
    }
    if (to != JobState::Failed && !error_message.empty()) {
        return false;                                   // L3-CPP-008
    }

    state = to;                                         // L3-CPP-009
    updated_at_ms = now_ms;
    if (filemover::is_terminal(to)) {
        finished_at_ms = now_ms;                        // L3-CPP-010
    }
    if (to == JobState::Failed) {
        error = error_message;                          // L3-CPP-011
    }
    return true;
}

bool Job::is_terminal() const {
    return filemover::is_terminal(state);
}

} // namespace filemover
