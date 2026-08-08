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
#include <sys/wait.h>
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

TEST_CASE("a duplicate job id is refused rather than published twice",
          "[manager][L2-JOB-013][L2-LIF-005]") {
    Fixture fx;
    fx.write_source("only-once");
    JobManager manager(fx.db(), fx.config(1));
    std::string error;
    REQUIRE(manager.start(error) == true);

    REQUIRE(manager.submit("only-once", fx.request("only-once"), error) ==
            CommandResult::Ok);
    // The claim survives the window in which submit releases the manager mutex
    // to do its durable write. Before that window existed the store's INSERT
    // was the only defence; now the id is reserved in memory as well, because
    // the store cannot refuse a duplicate that has not been written yet.
    CHECK(manager.submit("only-once", fx.request("only-once"), error) ==
          CommandResult::InvalidState);
    CHECK(error.empty() == false);

    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();
    CHECK(fx.kind_in(fx.dst(), "only-once.done") == EntryKind::Regular);
}

TEST_CASE("a job can be submitted while a worker is mid-move",
          "[manager][L2-MGR-001]") {
    Fixture fx;
    fx.write_source("held");
    fx.write_source("second");

    JobManager manager(fx.db(), fx.config(1));
    Latch latch;
    latch.at = MovePhase::Commit;
    manager.set_phase_hook(Latch::hook, &latch);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("held", fx.request("held"), error) ==
            CommandResult::Ok);
    latch.wait_arrival();

    // The submit path takes the manager mutex, releases it for its durable
    // write, and retakes it. This exercises that sequence while a worker is
    // genuinely in flight -- the interleaving the claim set exists to make
    // safe.
    REQUIRE(manager.submit("second", fx.request("second"), error) ==
            CommandResult::Ok);

    latch.release();
    manager.set_phase_hook(0, 0);
    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    CHECK(fx.kind_in(fx.dst(), "held.done") == EntryKind::Regular);
    CHECK(fx.kind_in(fx.dst(), "second.done") == EntryKind::Regular);
}

TEST_CASE("allocated job ids are unique and survive a restart",
          "[manager][L2-JOB-015]") {
    Fixture fx;
    std::string first;
    std::string second;

    {
        JobManager manager(fx.db(), fx.config(1));
        std::string error;
        REQUIRE(manager.start(error) == true);
        fx.write_source("one");
        REQUIRE(manager.submit(fx.request("one"), first, error) ==
                CommandResult::Ok);
        CHECK(first.empty() == false);
        REQUIRE(manager.wait_idle(30000) == true);
        manager.shutdown();
    }

    {
        // A fresh manager over the SAME database. The sequence is durable, so
        // it must not restart -- a repeated id would let this job overwrite
        // the record of the one above, which is exactly what L2-JOB-015 exists
        // to prevent. Testing this within one process would prove only that a
        // counter increments.
        JobManager manager(fx.db(), fx.config(1));
        std::string error;
        REQUIRE(manager.start(error) == true);
        fx.write_source("two");
        REQUIRE(manager.submit(fx.request("two"), second, error) ==
                CommandResult::Ok);
        manager.shutdown();
    }

    CHECK(first != second);
    CHECK(fx.state_of(first) == JobState::Done);
}

TEST_CASE("allocating an id against a stopped manager is refused",
          "[manager][L2-JOB-015]") {
    Fixture fx;
    JobManager manager(fx.db(), fx.config(1));
    std::string job_id;
    std::string error;
    // Refused before a sequence number is spent. Allocating first and then
    // discovering the manager is stopped would leave a gap for nothing.
    CHECK(manager.submit(fx.request("x"), job_id, error) ==
          CommandResult::NotRunning);
    CHECK(job_id.empty() == true);
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

    std::string spawned;
    CHECK(manager.pause("ghost", error) == CommandResult::UnknownJob);
    CHECK(manager.resume("ghost", error) == CommandResult::UnknownJob);
    CHECK(manager.cancel("ghost", error) == CommandResult::UnknownJob);
    CHECK(manager.retry("ghost", spawned, error) == CommandResult::UnknownJob);
    CHECK(spawned.empty() == true);
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
    std::string spawned;
    CHECK(manager.retry("done1", spawned, error) ==
          CommandResult::InvalidState);
    CHECK(spawned.empty() == true);
    CHECK(error.empty() == false);
    manager.shutdown();
}

// --- the store-under-mutex assertion --------------------------------------
//
// The invariant is that no store call happens while the manager mutex is held:
// a durable write blocks on busy_timeout for five seconds, and that mutex is
// what every worker takes to pick up its next job.
//
// It was a comment before it was an assertion, and two violations survived the
// commit that introduced the comment. So the assertion itself is tested, in a
// forked child because it ends in abort() -- the same reason the C1 crash suite
// forks. A test that cannot observe the abort would be asserting nothing, which
// is the failure mode this whole mechanism exists to prevent.

// Success is signalled down a PIPE, not through the exit status. Under
// Valgrind the child inherits the tool, and its leak check makes the exit
// status non-zero whatever the child does -- the inherited still-reachable heap
// is reported as errors and --error-exitcode applies. Asserting on the exit
// code therefore failed the Valgrind tier while passing everywhere else.
//
// A byte on a pipe is the honest signal: the child writes it only after every
// command has returned, and an abort() writes nothing.

TEST_CASE("the manager-mutex assertion aborts when the invariant is violated",
          "[manager][L2-MGR-001]") {
    Fixture fx;
    fx.write_source("victim");
    fx.write_source("decoy");

    int done[2] = {-1, -1};
    REQUIRE(::pipe(done) == 0);

    const pid_t pid = ::fork();
    REQUIRE(pid >= 0);

    if (pid == 0) {
        // Child. Drive every command that touches the store, so each one
        // exercises store_for_command at least once. If a future edit merges a
        // lock and a store call back together, the assertion aborts here and
        // this test sees the signal instead of an exit code of zero.
        //
        // The job must actually EXIST for cancel() to reach the store. An
        // earlier version cancelled a nonexistent id, which returns UnknownJob
        // at the first check without ever touching the store -- so it exercised
        // nothing and passed even with the defect deliberately reintroduced.
        //
        // It must also be QUEUED rather than running, which is why the single
        // worker is pinned on a decoy first. A previous version submitted and
        // then paused, and the worker won that race under AddressSanitizer:
        // pause returned InvalidState and the child exited 22. Latch-based
        // rather than timing-based, like the rest of this file.
        JobManager manager(fx.db(), fx.config(1));
        Latch latch;
        latch.at = MovePhase::Commit;
        manager.set_phase_hook(Latch::hook, &latch);

        std::string error;
        if (!manager.start(error)) {
            ::_exit(20);
        }
        if (manager.submit("decoy", fx.request("decoy"), error) !=
            CommandResult::Ok) {
            ::_exit(21);
        }
        latch.wait_arrival();  // the only worker is now pinned mid-move

        if (manager.submit("victim", fx.request("victim"), error) !=
            CommandResult::Ok) {
            ::_exit(22);
        }
        // Queued with certainty, so cancel reaches the store.
        if (manager.cancel("victim", error) != CommandResult::Ok) {
            ::_exit(23);
        }

        latch.release();
        manager.set_phase_hook(0, 0);
        manager.shutdown();

        // Reached only if every command above returned. An abort() skips this.
        ::close(done[0]);
        const char ok = 'K';
        const ssize_t written = ::write(done[1], &ok, 1);
        ::_exit(written == 1 ? 0 : 24);
    }

    ::close(done[1]);
    char got = 0;
    const ssize_t n = ::read(done[0], &got, 1);
    ::close(done[0]);

    int status = 0;
    REQUIRE(::waitpid(pid, &status, 0) == pid);

    // With the invariant held, every command returns and the child sends its
    // byte. This is the guard against the assertion firing on CORRECT code -- a
    // false abort would be worse than no assertion, because it would be
    // switched off within a day.
    //
    // Verified in both directions by hand: reintroducing the defect in cancel()
    // makes the child abort with the diagnostic and this read return 0 bytes.
    INFO("child status " << status << ", pipe bytes " << n);
    CHECK(n == 1);
    CHECK(got == 'K');
}

// --- manual retry (L2-RTY-006) --------------------------------------------

TEST_CASE("manual retry submits a new job and leaves the failed one alone",
          "[manager][L2-RTY-006]") {
    Fixture fx;
    Config cfg = fx.config(1);
    cfg.retry_max_attempts = 1;  // fail on the first attempt, no auto-retry
    JobManager manager(fx.db(), cfg);

    std::string error;
    REQUIRE(manager.start(error) == true);
    // No source file: Rejected, which is permanent and not auto-retried.
    REQUIRE(manager.submit("doomed", fx.request("doomed"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);
    REQUIRE(fx.state_of("doomed") == JobState::Failed);

    // Now make the move possible and retry by hand.
    fx.write_source("doomed");
    std::string spawned;
    REQUIRE(manager.retry("doomed", spawned, error) == CommandResult::Ok);
    CHECK(spawned == std::string("doomed-retry-1"));

    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    // The new job ran and delivered.
    CHECK(fx.state_of(spawned) == JobState::Done);
    CHECK(fx.kind_in(fx.dst(), "doomed.done") == EntryKind::Regular);

    // The failed job is untouched and still FAILED -- permanently. That record
    // is the whole reason retry does not revive it: an operator investigating
    // later needs to see that this move failed and why.
    CHECK(fx.state_of("doomed") == JobState::Failed);

    // And the two are linked, so the chain is reconstructible from the durable
    // record without consulting anything in memory.
    CHECK(fx.retry_of(spawned).retry_of == std::string("doomed"));
    // A directly submitted job has no predecessor.
    CHECK(fx.retry_of("doomed").retry_of.empty() == true);
}

TEST_CASE("retrying a retry does not nest the identifier",
          "[manager][L2-RTY-006]") {
    Fixture fx;
    Config cfg = fx.config(1);
    cfg.retry_max_attempts = 1;
    JobManager manager(fx.db(), cfg);

    std::string error;
    REQUIRE(manager.start(error) == true);
    REQUIRE(manager.submit("flaky", fx.request("flaky"), error) ==
            CommandResult::Ok);
    REQUIRE(manager.wait_idle(30000) == true);

    std::string first;
    REQUIRE(manager.retry("flaky", first, error) == CommandResult::Ok);
    CHECK(first == std::string("flaky-retry-1"));
    REQUIRE(manager.wait_idle(30000) == true);
    REQUIRE(fx.state_of(first) == JobState::Failed);

    // Retrying the retry yields -retry-2, NOT flaky-retry-1-retry-1. The id is
    // operator-facing and a name recording the shape of the chain rather than
    // its length becomes unreadable after two attempts.
    std::string second;
    REQUIRE(manager.retry(first, second, error) == CommandResult::Ok);
    CHECK(second == std::string("flaky-retry-2"));

    REQUIRE(manager.wait_idle(30000) == true);
    manager.shutdown();

    // Each links to the attempt it actually replaced, so the chain is walkable
    // one step at a time rather than collapsed onto the original.
    CHECK(fx.retry_of(second).retry_of == first);
    CHECK(fx.retry_of(first).retry_of == std::string("flaky"));
}
