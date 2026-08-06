// Job manager and worker pool tests (C4).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-MGR-001..003, L2-LIF-002/004/005, L2-RTY-001/002/003/005/006
//
// These are the project's first concurrency tests, and they are latch-based
// rather than sleep-based on purpose. A latch *makes* an interleaving happen;
// a sleep makes it likely, which is the difference between a test that fails
// when the code is wrong and one that fails when the machine is busy.
//
// The levers are the seams earlier milestones installed: MoveEngine's phase
// hook holds a worker mid-move at a chosen phase, and the injected clock lets
// retry timing be asserted without waiting for it.

#include "catch2/catch.hpp"

#include "filemover/manager.hpp"

#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#include <condition_variable>
#include <mutex>
#include <set>
#include <sstream>
#include <string>

using filemover::CommandResult;
using filemover::Config;
using filemover::DirHandle;
using filemover::EntryKind;
using filemover::FileIdentity;
using filemover::Job;
using filemover::JobManager;
using filemover::JobState;
using filemover::JobStore;
using filemover::MovePhase;
using filemover::MoveRequest;
using filemover::StoreOpenResult;

namespace {

class Fixture {
  public:
    Fixture() {
        char tmpl[] = "/tmp/fm-mgr-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        root_ = made;
        REQUIRE(::mkdir(src().c_str(), 0700) == 0);
        REQUIRE(::mkdir(dst().c_str(), 0700) == 0);
    }

    ~Fixture() {
        remove_all(src());
        remove_all(dst());
        ::unlink((db() + "-wal").c_str());
        ::unlink((db() + "-shm").c_str());
        ::unlink(db().c_str());
        ::rmdir(src().c_str());
        ::rmdir(dst().c_str());
        ::rmdir(root_.c_str());
    }

    std::string src() const { return root_ + "/src"; }
    std::string dst() const { return root_ + "/dst"; }
    std::string db() const { return root_ + "/state.db"; }

    void write_source(const std::string& name) const {
        const int fd = ::open((src() + "/" + name).c_str(),
                              O_WRONLY | O_CREAT | O_TRUNC, 0600);
        REQUIRE(fd >= 0);
        REQUIRE(::write(fd, "payload", 7) == 7);
        REQUIRE(::close(fd) == 0);
    }

    // Occupies the name a committed-but-unpublished object would take, so the
    // commit rename fails with EEXIST under either MoveStrategy. This is the
    // project's uid-independent way to force a pre-commit abort; the C3 suite
    // uses the same lever (tests/test_mover.cpp).
    void occupy_staging_name(const std::string& job_id) const {
        const std::string staging =
            dst() + "/" + filemover::MoveEngine::staging_name(job_id);
        const int fd = ::open(staging.c_str(), O_WRONLY | O_CREAT | O_EXCL,
                              0600);
        REQUIRE(fd >= 0);
        REQUIRE(::close(fd) == 0);
    }

    MoveRequest request(const std::string& name) const {
        MoveRequest r;
        r.source_dir = src();
        r.source_name = name;
        r.dest_dir = dst();
        r.dest_name = name + ".done";
        return r;
    }

    EntryKind kind_in(const std::string& dir, const std::string& name) const {
        DirHandle handle;
        std::string error;
        if (!handle.open_root(dir, error)) {
            return EntryKind::Unknown;
        }
        FileIdentity id;
        if (!filemover::classify(handle, name, id, error)) {
            return EntryKind::Unknown;
        }
        return id.kind;
    }

    JobState state_of(const std::string& id) const {
        JobStore store;
        StoreOpenResult result = StoreOpenResult::OpenedExisting;
        std::string error;
        REQUIRE(store.open(db(), result, error) == true);
        Job job(std::string(), std::string(), std::string(), 0);
        bool found = false;
        REQUIRE(store.load(id, job, found, error) == true);
        REQUIRE(found == true);
        return job.state;
    }

    JobStore::RetryState retry_of(const std::string& id) const {
        JobStore store;
        StoreOpenResult result = StoreOpenResult::OpenedExisting;
        std::string error;
        REQUIRE(store.open(db(), result, error) == true);
        JobStore::RetryState state;
        bool found = false;
        REQUIRE(store.load_retry_state(id, state, found, error) == true);
        return state;
    }

    Config config(unsigned workers) const {
        Config c;
        c.jobs_workers = workers;
        c.storage_database_path = db();
        return c;
    }

  private:
    Fixture(const Fixture&);
    Fixture& operator=(const Fixture&);

    static void remove_all(const std::string& dir) {
        DirHandle handle;
        std::string error;
        if (!handle.open_root(dir, error)) {
            return;
        }
        std::vector<filemover::DirEntry> entries;
        if (!filemover::read_entries(handle, entries, error)) {
            return;
        }
        for (size_t i = 0; i < entries.size(); ++i) {
            ::unlink((dir + "/" + entries[i].name).c_str());
        }
    }

    std::string root_;
};

// A clock the test advances by hand. Retry is defined as "not before
// next_retry_ms", and asserting that with a real clock means sleeping.
struct TestClock {
    std::mutex mutex;
    std::int64_t now;

    TestClock() : now(1000) {}

    static std::int64_t read(void* user) {
        TestClock* c = static_cast<TestClock*>(user);
        std::lock_guard<std::mutex> guard(c->mutex);
        return c->now;
    }

    void advance(std::int64_t ms) {
        std::lock_guard<std::mutex> guard(mutex);
        now += ms;
    }
};

// Holds a worker at a chosen phase until the test releases it. This is what
// makes "pause a job that is genuinely in flight" a fact rather than a race.
struct Latch {
    std::mutex mutex;
    std::condition_variable cv;
    bool arrived;
    bool released;
    MovePhase at;

    Latch() : arrived(false), released(false), at(MovePhase::Validate) {}

    static void hook(MovePhase completed, void* user) {
        Latch* l = static_cast<Latch*>(user);
        if (completed != l->at) {
            return;
        }
        std::unique_lock<std::mutex> lock(l->mutex);
        l->arrived = true;
        l->cv.notify_all();
        while (!l->released) {
            l->cv.wait(lock);
        }
    }

    void wait_arrival() {
        std::unique_lock<std::mutex> lock(mutex);
        while (!arrived) {
            cv.wait(lock);
        }
    }

    void release() {
        std::unique_lock<std::mutex> lock(mutex);
        released = true;
        cv.notify_all();
    }
};

}  // namespace

// --- dispatch -------------------------------------------------------------

TEST_CASE("workers drain the queue and each job runs once",
          "[manager][L2-MGR-001]") {
    Fixture fx;
    JobManager manager(fx.db(), fx.config(4));
    std::string error;
    REQUIRE(manager.start(error) == true);

    const int kJobs = 12;
    for (int i = 0; i < kJobs; ++i) {
        std::ostringstream name;
        name << "f" << i;
        fx.write_source(name.str());
        REQUIRE(manager.submit(name.str(), fx.request(name.str()), error) ==
                CommandResult::Ok);
    }

    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    // Every job delivered exactly once: the destination exists and the source
    // is gone. A job dispatched twice would fail its second run, because the
    // source it needs is no longer there.
    for (int i = 0; i < kJobs; ++i) {
        std::ostringstream name;
        name << "f" << i;
        INFO("job " << name.str());
        CHECK(fx.kind_in(fx.dst(), name.str() + ".done") == EntryKind::Regular);
        CHECK(fx.kind_in(fx.src(), name.str()) == EntryKind::Missing);
        CHECK(fx.state_of(name.str()) == JobState::Done);
    }
}

TEST_CASE("submitting before start is refused", "[manager][L2-LIF-005]") {
    Fixture fx;
    JobManager manager(fx.db(), fx.config(2));
    std::string error;
    CHECK(manager.submit("x", fx.request("x"), error) ==
          CommandResult::NotRunning);
    CHECK(error.empty() == false);
}

// --- shutdown -------------------------------------------------------------

TEST_CASE("shutdown stops intake, finishes in-flight work and joins",
          "[manager][L2-MGR-003]") {
    Fixture fx;
    fx.write_source("held");
    JobManager manager(fx.db(), fx.config(2));

    Latch latch;
    latch.at = MovePhase::Commit;
    manager.set_phase_hook(Latch::hook, &latch);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("held", fx.request("held"), error) ==
            CommandResult::Ok);

    // The worker is genuinely past the commit point and stopped there.
    latch.wait_arrival();
    CHECK(manager.active_count() == 1u);

    latch.release();
    manager.shutdown();

    // The in-flight job was finished rather than abandoned: a move past its
    // commit point left half-recorded is the thing shutdown must not do.
    CHECK(fx.state_of("held") == JobState::Done);
    CHECK(fx.kind_in(fx.dst(), "held.done") == EntryKind::Regular);
    CHECK(manager.is_running() == false);
}

TEST_CASE("shutdown is idempotent and safe without start",
          "[manager][L2-MGR-003]") {
    Fixture fx;
    JobManager manager(fx.db(), fx.config(2));
    manager.shutdown();
    manager.shutdown();
    CHECK(manager.is_running() == false);
}

// --- pause and resume -----------------------------------------------------

TEST_CASE("a paused job is not dispatched until resumed",
          "[manager][L2-LIF-004]") {
    Fixture fx;
    fx.write_source("blocker");
    fx.write_source("later");

    // One worker, so dispatch order is observable rather than racy.
    JobManager manager(fx.db(), fx.config(1));
    Latch latch;
    latch.at = MovePhase::Commit;
    manager.set_phase_hook(Latch::hook, &latch);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("blocker", fx.request("blocker"), error) ==
            CommandResult::Ok);
    latch.wait_arrival();

    // The only worker is held, so "later" is queued and can be paused with
    // certainty rather than in the hope it has not started.
    REQUIRE(manager.submit("later", fx.request("later"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.pause("later", error) == CommandResult::Ok);
    CHECK(manager.runnable_count() == 0u);

    latch.release();
    manager.set_phase_hook(0, 0);
    REQUIRE(manager.wait_idle(30000) == true);

    // Paused work stayed put while the pool went idle.
    CHECK(fx.kind_in(fx.dst(), "later.done") == EntryKind::Missing);
    CHECK(fx.state_of("later") == JobState::Queued);

    REQUIRE(manager.resume("later", error) == CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    CHECK(fx.kind_in(fx.dst(), "later.done") == EntryKind::Regular);
    CHECK(fx.state_of("later") == JobState::Done);
}

TEST_CASE("pausing a job that is mid-move is refused, not forced",
          "[manager][L2-LIF-002]") {
    Fixture fx;
    fx.write_source("running");
    JobManager manager(fx.db(), fx.config(1));

    Latch latch;
    latch.at = MovePhase::Commit;
    manager.set_phase_hook(Latch::hook, &latch);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("running", fx.request("running"), error) ==
            CommandResult::Ok);
    latch.wait_arrival();

    // Past the commit point the move is real. Cooperative stopping means
    // refusing at a safe point, not tearing the move in half.
    CHECK(manager.pause("running", error) == CommandResult::InvalidState);
    CHECK(manager.cancel("running", error) == CommandResult::InvalidState);

    latch.release();
    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();
    CHECK(fx.state_of("running") == JobState::Done);
}

// --- typed errors ---------------------------------------------------------

TEST_CASE("lifecycle commands reject unknown jobs with a typed error",
          "[manager][L2-LIF-005]") {
    Fixture fx;
    JobManager manager(fx.db(), fx.config(2));
    std::string error;
    REQUIRE(manager.start(error) == true);

    CHECK(manager.pause("ghost", error) == CommandResult::UnknownJob);
    CHECK(manager.resume("ghost", error) == CommandResult::UnknownJob);
    CHECK(manager.cancel("ghost", error) == CommandResult::UnknownJob);
    CHECK(manager.retry("ghost", error) == CommandResult::UnknownJob);
    CHECK(error.empty() == false);

    manager.shutdown();
}

TEST_CASE("resuming a job that is not paused is an invalid state",
          "[manager][L2-LIF-005]") {
    Fixture fx;
    fx.write_source("a");
    JobManager manager(fx.db(), fx.config(1));
    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("a", fx.request("a"), error) == CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);

    CHECK(manager.resume("a", error) == CommandResult::InvalidState);
    manager.shutdown();
}

TEST_CASE("command result tokens are stable", "[manager][L2-LIF-005]") {
    CHECK(std::string(filemover::to_string(CommandResult::Ok)) == "OK");
    CHECK(std::string(filemover::to_string(CommandResult::UnknownJob)) ==
          "UNKNOWN_JOB");
    CHECK(std::string(filemover::to_string(CommandResult::InvalidState)) ==
          "INVALID_STATE");
    CHECK(std::string(filemover::to_string(CommandResult::NotRunning)) ==
          "NOT_RUNNING");
    CHECK(std::string(filemover::to_string(CommandResult::StoreError)) ==
          "STORE_ERROR");
}

// --- cancellation ---------------------------------------------------------

TEST_CASE("cancelling a queued job removes it and marks it FAILED",
          "[manager][L2-LIF-005]") {
    Fixture fx;
    fx.write_source("blocker");
    fx.write_source("doomed");

    JobManager manager(fx.db(), fx.config(1));
    Latch latch;
    latch.at = MovePhase::Commit;
    manager.set_phase_hook(Latch::hook, &latch);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("blocker", fx.request("blocker"), error) ==
            CommandResult::Ok);
    latch.wait_arrival();
    REQUIRE(manager.submit("doomed", fx.request("doomed"), error) ==
            CommandResult::Ok);

    REQUIRE(manager.cancel("doomed", error) == CommandResult::Ok);

    latch.release();
    manager.set_phase_hook(0, 0);
    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    // v1.0.0 cancellation marks FAILED. CANCELLED_RETAINED belongs to
    // L2-LIF-001/003, deferred with L1-SYS-003, and inventing it here would
    // put a state in the durable record the core machine does not define.
    CHECK(fx.state_of("doomed") == JobState::Failed);
    // The source is untouched -- nothing ran.
    CHECK(fx.kind_in(fx.src(), "doomed") == EntryKind::Regular);
    CHECK(fx.kind_in(fx.dst(), "doomed.done") == EntryKind::Missing);
}

// --- failure isolation and retry ------------------------------------------

TEST_CASE("a failing job does not wedge the queue", "[manager][L2-MGR-001]") {
    Fixture fx;
    // "bad" has no source file, so its move is refused before the commit.
    fx.write_source("good1");
    fx.write_source("good2");

    Config cfg = fx.config(2);
    cfg.retry_max_attempts = 1;  // fail it immediately rather than rescheduling
    JobManager manager(fx.db(), cfg);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("bad", fx.request("bad"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.submit("good1", fx.request("good1"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.submit("good2", fx.request("good2"), error) ==
            CommandResult::Ok);

    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    // The roadmap's done-when: a worker whose job fails cannot stop the
    // others making progress.
    CHECK(fx.kind_in(fx.dst(), "good1.done") == EntryKind::Regular);
    CHECK(fx.kind_in(fx.dst(), "good2.done") == EntryKind::Regular);
    CHECK(fx.state_of("bad") == JobState::Failed);
}

TEST_CASE("a retryable failure is rescheduled with backoff and persisted",
          "[manager][L2-RTY-003][L2-RTY-005]") {
    Fixture fx;
    TestClock clock;

    Config cfg = fx.config(1);
    cfg.retry_max_attempts = 5;
    cfg.retry_backoff_initial_ms = 100;
    cfg.retry_backoff_max_ms = 400;

    JobManager manager(fx.db(), cfg);
    manager.set_clock(TestClock::read, &clock);

    // A retryable failure, not a denial. The source is present and valid, so
    // the request passes validation and fails at the commit rename --
    // MoveOutcome::AbortedBeforeCommit, source untouched. A missing source
    // would be the wrong lever: that is Rejected, permanent by design, and
    // must NOT retry.
    //
    // The failure is induced by occupying the staging name, so the rename
    // fails with EEXIST. An earlier version made the destination directory
    // read-only instead, which worked locally and silently tested NOTHING in
    // the GCC 4.8.5 container, because that runs as root and root bypasses
    // directory permission checks -- the move simply succeeded and the test
    // asserted against a retry that never happened. Anything gated on file
    // permissions is not a test on this project's fidelity tier.
    fx.write_source("flaky");
    fx.occupy_staging_name("flaky");

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("flaky", fx.request("flaky"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);

    // L2-RTY-003: the attempt count and reason are durable, and the job is
    // still QUEUED -- so the reason lives in last_error, which is exactly why
    // that column exists.
    JobStore::RetryState state = fx.retry_of("flaky");
    CHECK(state.attempts == 1);
    CHECK(state.last_error.empty() == false);
    CHECK(state.next_retry_ms > 1000);
    // RENAMING: phase 2 recorded the attempt before the commit rename failed,
    // and nothing rewinds it. The job is still live -- FAILED would have made
    // it terminal and unretryable.
    CHECK(fx.state_of("flaky") == JobState::Renaming);

    // Not yet due: pump moves nothing.
    CHECK(manager.pump(error) == 0u);
    CHECK(manager.runnable_count() == 0u);

    // Due now. No sleeping was involved in establishing that.
    clock.advance(1000);
    CHECK(manager.pump(error) == 1u);

    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();
    CHECK(fx.retry_of("flaky").attempts == 2);
}

TEST_CASE("retry stops at the configured attempt ceiling",
          "[manager][L2-RTY-005][L2-RTY-002]") {
    Fixture fx;
    TestClock clock;

    Config cfg = fx.config(1);
    cfg.retry_max_attempts = 2;
    cfg.retry_backoff_initial_ms = 10;
    cfg.retry_backoff_max_ms = 10;

    JobManager manager(fx.db(), cfg);
    manager.set_clock(TestClock::read, &clock);

    fx.write_source("hopeless");
    fx.occupy_staging_name("hopeless");

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("hopeless", fx.request("hopeless"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);

    clock.advance(1000);
    REQUIRE(manager.pump(error) == 1u);
    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    // Bounded: the second attempt hits the ceiling and the job is FAILED
    // rather than retried forever. Unbounded retry against a permanent error
    // is how a queue fills with work that can never succeed.
    CHECK(fx.state_of("hopeless") == JobState::Failed);
    const JobStore::RetryState state = fx.retry_of("hopeless");
    CHECK(state.attempts == 2);
    CHECK(state.last_error.find("gave up after") != std::string::npos);
}

TEST_CASE("manual retry of a non-FAILED job is refused",
          "[manager][L2-RTY-006][L2-LIF-005]") {
    Fixture fx;
    fx.write_source("done1");
    JobManager manager(fx.db(), fx.config(1));
    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("done1", fx.request("done1"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);

    // A typed refusal rather than a panic or a silent no-op (L2-LIF-005).
    CHECK(manager.retry("done1", error) == CommandResult::InvalidState);
    CHECK(error.empty() == false);
    manager.shutdown();
}
