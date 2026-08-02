// M1 test suite: job state machine.
// Assertions use natural order: actual == expected.

#include "catch2/catch.hpp"
#include "filemover/job.hpp"

#include <vector>

using filemover::Job;
using filemover::JobState;

namespace {

const std::vector<JobState> kAllStates = {
    JobState::Queued,
    JobState::Renaming,
    JobState::Transferring,
    JobState::Done,
    JobState::Failed
};

// Single source of truth for the legal-transition table used by the
// exhaustive tests below. Mirrors L3-CPP-003.
bool expected_legal(JobState from, JobState to) {
    if (from == JobState::Queued)
        return to == JobState::Renaming || to == JobState::Failed;
    if (from == JobState::Renaming)
        return to == JobState::Transferring || to == JobState::Failed;
    if (from == JobState::Transferring)
        return to == JobState::Done || to == JobState::Failed;
    return false; // Done, Failed: terminal
}

// Force a job into an arbitrary state via legal transitions only.
Job make_job_in_state(JobState target, std::int64_t now_ms) {
    Job job("job-001", "/data/in/a.ch10", "/data/out/a.ch10", now_ms);
    switch (target) {
        case JobState::Queued:
            break;
        case JobState::Renaming:
            job.transition(JobState::Renaming, now_ms + 1);
            break;
        case JobState::Transferring:
            job.transition(JobState::Renaming, now_ms + 1);
            job.transition(JobState::Transferring, now_ms + 2);
            break;
        case JobState::Done:
            job.transition(JobState::Renaming, now_ms + 1);
            job.transition(JobState::Transferring, now_ms + 2);
            job.transition(JobState::Done, now_ms + 3);
            break;
        case JobState::Failed:
            job.transition(JobState::Failed, now_ms + 1, "forced failure");
            break;
    }
    return job;
}

} // namespace

TEST_CASE("state tokens are stable, unique, uppercase", "[core][L3-CPP-001][L3-CPP-002]") {
    CHECK(std::string(to_string(JobState::Queued)) == "QUEUED");
    CHECK(std::string(to_string(JobState::Renaming)) == "RENAMING");
    CHECK(std::string(to_string(JobState::Transferring)) == "TRANSFERRING");
    CHECK(std::string(to_string(JobState::Done)) == "DONE");
    CHECK(std::string(to_string(JobState::Failed)) == "FAILED");
}

TEST_CASE("terminal predicate covers exactly Done and Failed", "[core][L3-CPP-004]") {
    CHECK(filemover::is_terminal(JobState::Queued) == false);
    CHECK(filemover::is_terminal(JobState::Renaming) == false);
    CHECK(filemover::is_terminal(JobState::Transferring) == false);
    CHECK(filemover::is_terminal(JobState::Done) == true);
    CHECK(filemover::is_terminal(JobState::Failed) == true);
}

TEST_CASE("construction establishes Queued with coherent timestamps",
          "[core][L3-CPP-005]") {
    Job job("job-42", "/src/file.bin", "/dst/file.bin", 1000);

    CHECK(job.id == "job-42");
    CHECK(job.source_path == "/src/file.bin");
    CHECK(job.dest_path == "/dst/file.bin");
    CHECK(job.state == JobState::Queued);
    CHECK(job.created_at_ms == 1000);
    CHECK(job.updated_at_ms == 1000);
    CHECK(job.finished_at_ms == 0);
    CHECK(job.bytes_total == 0u);
    CHECK(job.bytes_moved == 0u);
    CHECK(job.error.empty() == true);
    CHECK(job.is_terminal() == false);
}

TEST_CASE("is_legal_transition matches the specified table exhaustively",
          "[core][L3-CPP-003][L3-CPP-015]") {
    for (JobState from : kAllStates) {
        for (JobState to : kAllStates) {
            INFO("from=" << to_string(from) << " to=" << to_string(to));
            CHECK(filemover::is_legal_transition(from, to) ==
                  expected_legal(from, to));
        }
    }
}

TEST_CASE("transition rejects every illegal pair and leaves the job unmodified",
          "[core][L3-CPP-006]") {
    for (JobState from : kAllStates) {
        for (JobState to : kAllStates) {
            if (expected_legal(from, to)) {
                continue;
            }
            Job job = make_job_in_state(from, 1000);
            const Job before = job;

            const std::string err =
                (to == JobState::Failed) ? "some error" : "";
            INFO("from=" << to_string(from) << " to=" << to_string(to));
            CHECK(job.transition(to, 9999, err) == false);
            CHECK(job.state == before.state);
            CHECK(job.updated_at_ms == before.updated_at_ms);
            CHECK(job.finished_at_ms == before.finished_at_ms);
            CHECK(job.error == before.error);
        }
    }
}

TEST_CASE("happy path lifecycle updates state and timestamps",
          "[core][L3-CPP-009][L3-CPP-010]") {
    Job job("job-1", "/a", "/b", 100);

    CHECK(job.transition(JobState::Renaming, 110) == true);
    CHECK(job.state == JobState::Renaming);
    CHECK(job.updated_at_ms == 110);
    CHECK(job.finished_at_ms == 0);

    CHECK(job.transition(JobState::Transferring, 120) == true);
    CHECK(job.state == JobState::Transferring);
    CHECK(job.updated_at_ms == 120);
    CHECK(job.finished_at_ms == 0);

    CHECK(job.transition(JobState::Done, 130) == true);
    CHECK(job.state == JobState::Done);
    CHECK(job.updated_at_ms == 130);
    CHECK(job.finished_at_ms == 130);
    CHECK(job.is_terminal() == true);
    CHECK(job.error.empty() == true);
}

TEST_CASE("failure is reachable from every non-terminal state and records the error",
          "[core][L3-CPP-011]") {
    const std::vector<JobState> non_terminal = {
        JobState::Queued, JobState::Renaming, JobState::Transferring};

    for (JobState from : non_terminal) {
        Job job = make_job_in_state(from, 1000);
        INFO("from=" << to_string(from));
        CHECK(job.transition(JobState::Failed, 2000, "disk full") == true);
        CHECK(job.state == JobState::Failed);
        CHECK(job.error == "disk full");
        CHECK(job.updated_at_ms == 2000);
        CHECK(job.finished_at_ms == 2000);
        CHECK(job.is_terminal() == true);
    }
}

TEST_CASE("transition to Failed requires a non-empty error message",
          "[core][L3-CPP-007]") {
    Job job("job-1", "/a", "/b", 100);

    CHECK(job.transition(JobState::Failed, 200) == false);
    CHECK(job.transition(JobState::Failed, 200, "") == false);
    CHECK(job.state == JobState::Queued);
    CHECK(job.updated_at_ms == 100);
    CHECK(job.error.empty() == true);
}

TEST_CASE("transition to non-Failed states rejects an error message",
          "[core][L3-CPP-008]") {
    Job job("job-1", "/a", "/b", 100);

    CHECK(job.transition(JobState::Renaming, 200, "unexpected") == false);
    CHECK(job.state == JobState::Queued);
    CHECK(job.updated_at_ms == 100);

    CHECK(job.transition(JobState::Renaming, 200) == true);
    CHECK(job.transition(JobState::Transferring, 300, "unexpected") == false);
    CHECK(job.state == JobState::Renaming);
    CHECK(job.updated_at_ms == 200);
}

TEST_CASE("terminal states accept no further transitions",
          "[core][L3-CPP-003][L3-CPP-006]") {
    for (JobState terminal : {JobState::Done, JobState::Failed}) {
        Job job = make_job_in_state(terminal, 1000);
        const std::int64_t finished = job.finished_at_ms;

        for (JobState to : kAllStates) {
            const std::string err =
                (to == JobState::Failed) ? "late error" : "";
            INFO("terminal=" << to_string(terminal)
                             << " to=" << to_string(to));
            CHECK(job.transition(to, 5000, err) == false);
        }
        CHECK(job.state == terminal);
        CHECK(job.finished_at_ms == finished);
    }
}
