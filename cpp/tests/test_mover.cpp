// Move engine tests (C3).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L1-SEC-001, L1-SEC-002, L1-SYS-015, L2-XFR-001, L2-XFR-004,
//         L2-JOB-014, L2-SEC-011
//
// The engine has one atomic commit point, so the tests are organised around
// it: what must be true before, what must be true after, and what recovery
// makes of each state a crash can leave behind.
//
// Both move strategies are driven explicitly. linkat+unlinkat is what
// production runs on the NFS mount (L2-NFS-002), and a test that used whatever
// the local filesystem supports would stop covering it silently.

#include "catch2/catch.hpp"

#include "filemover/mover.hpp"

#include <fcntl.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <string>

using filemover::CommitPhase;
using filemover::DirHandle;
using filemover::EntryKind;
using filemover::FileIdentity;
using filemover::Job;
using filemover::JobState;
using filemover::JobStore;
using filemover::MoveEngine;
using filemover::MoveOutcome;
using filemover::MovePhase;
using filemover::MoveRequest;
using filemover::MoveStrategy;
using filemover::StoreOpenResult;
using filemover::WriteFault;

namespace {

// A source directory, a destination directory and a store, all under one
// temporary root so a test cleans up completely.
class Fixture {
  public:
    Fixture() {
        char tmpl[] = "/tmp/fm-mover-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        root_ = made;
        REQUIRE(::mkdir(src().c_str(), 0700) == 0);
        REQUIRE(::mkdir(dst().c_str(), 0700) == 0);

        StoreOpenResult result = StoreOpenResult::OpenedExisting;
        std::string error;
        REQUIRE(store_.open(db(), result, error) == true);
    }

    ~Fixture() {
        store_.close();
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
    JobStore& store() { return store_; }

    void write_source(const std::string& name, const std::string& body) const {
        const int fd =
            ::open((src() + "/" + name).c_str(), O_WRONLY | O_CREAT | O_TRUNC,
                   0600);
        REQUIRE(fd >= 0);
        if (!body.empty()) {
            REQUIRE(::write(fd, body.data(), body.size()) ==
                    static_cast<ssize_t>(body.size()));
        }
        REQUIRE(::close(fd) == 0);
    }

    // Records the intent the engine requires to already exist (L2-JOB-013).
    void record_intent(const std::string& id) {
        std::string error;
        Job job(id, src() + "/in.dat", dst() + "/out.dat", 1000);
        REQUIRE(store_.record_intent(job, error) == true);
    }

    MoveRequest request() const {
        MoveRequest r;
        r.source_dir = src();
        r.source_name = "in.dat";
        r.dest_dir = dst();
        r.dest_name = "out.dat";
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

    JobState state_of(const std::string& id) {
        Job job(std::string(), std::string(), std::string(), 0);
        bool found = false;
        std::string error;
        REQUIRE(store_.load(id, job, found, error) == true);
        REQUIRE(found == true);
        return job.state;
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
    JobStore store_;
};

const MoveStrategy kStrategies[2] = {MoveStrategy::RenameNoReplace,
                                     MoveStrategy::LinkThenUnlink};

}  // namespace

// --- the happy path, under both strategies -------------------------------

TEST_CASE("a move delivers the file and records DONE",
          "[mover][L1-SYS-015][L1-SEC-001]") {
    for (int i = 0; i < 2; ++i) {
        Fixture fx;
        INFO("strategy: " << filemover::to_string(kStrategies[i]));
        fx.write_source("in.dat", "payload");
        fx.record_intent("job-1");

        MoveEngine engine(fx.store());
        std::string error;
        const MoveOutcome outcome =
            engine.execute("job-1", fx.request(), kStrategies[i], error);

        INFO("error: " << error);
        CHECK(outcome == MoveOutcome::Completed);
        CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Missing);
        CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Regular);
        // The staging name must not survive a completed move.
        CHECK(fx.kind_in(fx.dst(), MoveEngine::staging_name("job-1")) ==
              EntryKind::Missing);
        CHECK(fx.state_of("job-1") == JobState::Done);
    }
}

TEST_CASE("the progress callback reports start and finish",
          "[mover][L2-XFR-001]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-p");

    struct Counter {
        static void tick(std::uint64_t done, std::uint64_t total, void* user) {
            (void)done;
            (void)total;
            *static_cast<int*>(user) += 1;
        }
    };
    int calls = 0;

    MoveEngine engine(fx.store());
    engine.set_progress(Counter::tick, &calls);
    std::string error;
    REQUIRE(engine.execute("job-p", fx.request(),
                           MoveStrategy::RenameNoReplace,
                           error) == MoveOutcome::Completed);

    // A rename moves every byte at once, so this fires exactly twice. The
    // interface exists so v1.1's copy strategy is an addition rather than a
    // change to every caller -- and so a caller that renders progress is
    // written against an instantaneous move from the start.
    CHECK(calls == 2);
}

// --- refusals, before anything happens ------------------------------------

TEST_CASE("a move with no durable intent is refused",
          "[mover][L2-JOB-013]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    // Deliberately no record_intent.

    MoveEngine engine(fx.store());
    std::string error;
    CHECK(engine.execute("ghost", fx.request(), MoveStrategy::RenameNoReplace,
                         error) == MoveOutcome::Rejected);
    CHECK(error.find("L2-JOB-013") != std::string::npos);
    // The source is untouched, which is the point of refusing.
    CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Regular);
}

TEST_CASE("a non-regular source is refused", "[mover][L2-SEC-004]") {
    Fixture fx;
    REQUIRE(::mkfifo((fx.src() + "/in.dat").c_str(), 0600) == 0);
    fx.record_intent("job-fifo");

    MoveEngine engine(fx.store());
    std::string error;
    CHECK(engine.execute("job-fifo", fx.request(),
                         MoveStrategy::RenameNoReplace,
                         error) == MoveOutcome::Rejected);
    CHECK(error.find("FIFO") != std::string::npos);
    CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Missing);
}

TEST_CASE("a missing source is refused", "[mover][L2-XFR-004]") {
    Fixture fx;
    fx.record_intent("job-none");

    MoveEngine engine(fx.store());
    std::string error;
    CHECK(engine.execute("job-none", fx.request(),
                         MoveStrategy::RenameNoReplace,
                         error) == MoveOutcome::Rejected);
    CHECK(error.empty() == false);
}

TEST_CASE("a relative directory is refused before any syscall",
          "[mover][L2-SEC-006]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-rel");

    MoveRequest bad = fx.request();
    bad.source_dir = "relative/path";

    MoveEngine engine(fx.store());
    std::string error;
    CHECK(engine.execute("job-rel", bad, MoveStrategy::RenameNoReplace,
                         error) == MoveOutcome::Rejected);
    CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Regular);
}

TEST_CASE("an occupied destination is not clobbered",
          "[mover][L1-SEC-001]") {
    for (int i = 0; i < 2; ++i) {
        Fixture fx;
        INFO("strategy: " << filemover::to_string(kStrategies[i]));
        fx.write_source("in.dat", "ours");
        fx.record_intent("job-c");

        // Something already occupies the staging name.
        const int fd = ::open(
            (fx.dst() + "/" + MoveEngine::staging_name("job-c")).c_str(),
            O_WRONLY | O_CREAT, 0600);
        REQUIRE(fd >= 0);
        REQUIRE(::close(fd) == 0);

        MoveEngine engine(fx.store());
        std::string error;
        CHECK(engine.execute("job-c", fx.request(), kStrategies[i], error) ==
              MoveOutcome::AbortedBeforeCommit);
        // The commit never happened, so the source is still there.
        CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Regular);
        // RENAMING, not FAILED. The engine records the attempt it began and
        // stops; it does not declare the job over. FAILED is terminal, so
        // writing it here made a retryable failure permanent -- see the note
        // on the phase 3 failure path in mover.cpp.
        CHECK(fx.state_of("job-c") == JobState::Renaming);
    }
}

// --- L2-JOB-014: the same failure, opposite verdicts ----------------------

TEST_CASE("a durable write failure before the commit point aborts",
          "[mover][L2-JOB-014]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-pre");

    std::string error;
    REQUIRE(fx.store().inject_write_fault(WriteFault::Refused, error) == true);

    MoveEngine engine(fx.store());
    CHECK(engine.execute("job-pre", fx.request(),
                         MoveStrategy::RenameNoReplace,
                         error) == MoveOutcome::AbortedBeforeCommit);

    REQUIRE(fx.store().inject_write_fault(WriteFault::None, error) == true);
    // Nothing happened: no durable record of RENAMING, and the source is
    // exactly where it was. Acting without a record is what leaves an orphan.
    CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Regular);
    CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Missing);
    CHECK(fx.state_of("job-pre") == JobState::Queued);
}

namespace {

// Arms a store write failure the moment a chosen phase completes, so the next
// durable write fails on the far side of the commit point.
struct FaultAfterPhase {
    JobStore* store;
    MovePhase after;
    int fired;

    FaultAfterPhase() : store(0), after(MovePhase::Commit), fired(0) {}
};

void arm_after_phase(MovePhase completed, void* user) {
    FaultAfterPhase* f = static_cast<FaultAfterPhase*>(user);
    if (completed == f->after && f->fired == 0) {
        std::string error;
        f->store->inject_write_fault(WriteFault::Refused, error);
        f->fired = 1;
    }
}

}  // namespace

TEST_CASE("a durable write failure after the commit point halts",
          "[mover][L2-JOB-014][L1-SEC-002]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-post");

    FaultAfterPhase fault;
    fault.store = &fx.store();
    fault.after = MovePhase::Commit;

    MoveEngine engine(fx.store());
    engine.set_phase_hook(arm_after_phase, &fault);

    std::string error;
    const MoveOutcome outcome = engine.execute(
        "job-post", fx.request(), MoveStrategy::RenameNoReplace, error);

    // The same class of failure as the test above, and the opposite verdict.
    // Treating both as one retryable condition is the mistake L2-JOB-014
    // exists to prevent.
    CHECK(outcome == MoveOutcome::HaltedAfterCommit);
    CHECK(outcome != MoveOutcome::AbortedBeforeCommit);

    REQUIRE(fx.store().inject_write_fault(WriteFault::None, error) == true);

    // The move is real: the source is gone and the object is staged. Nothing
    // deleted it and nothing pretended the job finished.
    CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Missing);
    CHECK(fx.kind_in(fx.dst(), MoveEngine::staging_name("job-post")) ==
          EntryKind::Regular);
    CHECK(fx.state_of("job-post") != JobState::Done);
}

// --- recovery from every state a crash can leave -------------------------

TEST_CASE("recovery re-drives a move that never committed",
          "[mover][L1-SEC-002]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-r1");

    MoveEngine engine(fx.store());
    std::string error;
    // Nothing has run, so the state on disk is NotStarted.
    const MoveOutcome outcome =
        engine.recover("job-r1", fx.request(), MoveStrategy::RenameNoReplace,
                       error);
    INFO("error: " << error);
    CHECK(outcome == MoveOutcome::Completed);
    CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Regular);
}

TEST_CASE("recovery finishes a move interrupted after the commit",
          "[mover][L1-SEC-002]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-r2");

    // Simulate a crash immediately after the commit: the object is staged and
    // the source is gone, but nothing was published.
    FaultAfterPhase fault;
    fault.store = &fx.store();
    fault.after = MovePhase::Commit;
    MoveEngine engine(fx.store());
    engine.set_phase_hook(arm_after_phase, &fault);
    std::string error;
    REQUIRE(engine.execute("job-r2", fx.request(),
                           MoveStrategy::RenameNoReplace,
                           error) == MoveOutcome::HaltedAfterCommit);
    REQUIRE(fx.store().inject_write_fault(WriteFault::None, error) == true);

    // A fresh engine, as a restart would have.
    MoveEngine restarted(fx.store());
    const MoveOutcome outcome = restarted.recover(
        "job-r2", fx.request(), MoveStrategy::RenameNoReplace, error);
    INFO("error: " << error);
    CHECK(outcome == MoveOutcome::Completed);
    CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Regular);
    CHECK(fx.state_of("job-r2") == JobState::Done);
}

TEST_CASE("recovery is idempotent once the move is already published",
          "[mover][L1-SEC-002]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-r3");

    MoveEngine engine(fx.store());
    std::string error;
    REQUIRE(engine.execute("job-r3", fx.request(),
                           MoveStrategy::RenameNoReplace,
                           error) == MoveOutcome::Completed);

    // Everything after the commit point is idempotent, so running recovery
    // over a finished job must reach the same state rather than fail.
    const MoveOutcome again = engine.recover(
        "job-r3", fx.request(), MoveStrategy::RenameNoReplace, error);
    INFO("error: " << error);
    CHECK(again == MoveOutcome::Completed);
    CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Regular);
}

TEST_CASE("recovery reports failed-external when both names are gone",
          "[mover][L2-SEC-011]") {
    Fixture fx;
    fx.write_source("in.dat", "payload");
    fx.record_intent("job-q");

    // Quarantine by endpoint security: the source is removed after intent was
    // recorded, and nothing was ever staged.
    REQUIRE(::unlink((fx.src() + "/in.dat").c_str()) == 0);

    MoveEngine engine(fx.store());
    std::string error;
    const MoveOutcome outcome =
        engine.recover("job-q", fx.request(), MoveStrategy::RenameNoReplace,
                       error);

    CHECK(outcome == MoveOutcome::FailedExternal);
    CHECK(error.find("L2-SEC-011") != std::string::npos);
    // Explicitly not retried: retrying cannot conjure a file something else
    // removed on purpose.
    CHECK(error.find("Not retrying") != std::string::npos);
    CHECK(fx.state_of("job-q") == JobState::Failed);
}

TEST_CASE("recovery refuses to clobber a foreign file at the staging name",
          "[mover][L1-SEC-001]") {
    Fixture fx;
    fx.write_source("in.dat", "ours");
    fx.record_intent("job-x");

    const int fd = ::open(
        (fx.dst() + "/" + MoveEngine::staging_name("job-x")).c_str(),
        O_WRONLY | O_CREAT, 0600);
    REQUIRE(fd >= 0);
    REQUIRE(::close(fd) == 0);

    MoveEngine engine(fx.store());
    std::string error;
    CHECK(engine.recover("job-x", fx.request(),
                         MoveStrategy::RenameNoReplace,
                         error) == MoveOutcome::HaltedAfterCommit);
    CHECK(error.find("clobber") != std::string::npos);
    CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Regular);
}

// --- tokens ---------------------------------------------------------------

TEST_CASE("outcome and phase tokens are stable", "[mover][L2-XFR-004]") {
    CHECK(std::string(filemover::to_string(MoveOutcome::Completed)) ==
          "COMPLETED");
    CHECK(std::string(filemover::to_string(MoveOutcome::AbortedBeforeCommit)) ==
          "ABORTED_BEFORE_COMMIT");
    CHECK(std::string(filemover::to_string(MoveOutcome::HaltedAfterCommit)) ==
          "HALTED_AFTER_COMMIT");
    CHECK(std::string(filemover::to_string(MoveOutcome::FailedExternal)) ==
          "FAILED_EXTERNAL");
    CHECK(std::string(filemover::to_string(MoveOutcome::Rejected)) ==
          "REJECTED");

    CHECK(std::string(filemover::to_string(MovePhase::Validate)) == "VALIDATE");
    CHECK(std::string(filemover::to_string(MovePhase::Commit)) == "COMMIT");
    CHECK(std::string(filemover::to_string(MovePhase::Publish)) == "PUBLISH");
    CHECK(std::string(filemover::to_string(MovePhase::RecordRenaming)) ==
          "RECORD_RENAMING");
    CHECK(std::string(filemover::to_string(MovePhase::RecordMoved)) ==
          "RECORD_MOVED");
    CHECK(std::string(filemover::to_string(MovePhase::RecordDone)) ==
          "RECORD_DONE");
}

TEST_CASE("the staging name is SWIT-prefixed and job-specific",
          "[mover][L1-SEC-001]") {
    // A locked decision: on-disk staging markers are SWIT-prefixed so an
    // in-flight artifact on a shared NFS mount is unmistakably ours.
    CHECK(MoveEngine::staging_name("abc") == std::string(".swit-partial-abc"));
    CHECK(MoveEngine::staging_name("abc") != MoveEngine::staging_name("abd"));
}

// --- kill between every pair of phases ------------------------------------
//
// The milestone's done-when. A child runs the move and SIGKILLs itself the
// instant a chosen phase completes; the parent then recovers and asserts the
// result is correct. SIGKILL rather than a clean exit because the property is
// what the *filesystem and the store* look like when a process dies, and an
// in-process error still unwinds and tidies up.

namespace {

struct KillAfter {
    MovePhase phase;
};

void kill_after_phase(MovePhase completed, void* user) {
    const KillAfter* k = static_cast<const KillAfter*>(user);
    if (completed == k->phase) {
        ::raise(SIGKILL);
    }
}

}  // namespace

TEST_CASE("killing after any phase leaves a state recovery can reconcile",
          "[mover][L1-SEC-002][L2-JOB-014]") {
    const MovePhase phases[5] = {MovePhase::Validate, MovePhase::RecordRenaming,
                                 MovePhase::Commit, MovePhase::RecordMoved,
                                 MovePhase::Publish};

    for (int i = 0; i < 5; ++i) {
        Fixture fx;
        INFO("killed after phase: " << filemover::to_string(phases[i]));
        fx.write_source("in.dat", "payload");
        fx.record_intent("job-k");
        // Released before forking so the child owns its own connection; two
        // processes sharing one SQLite handle is undefined.
        fx.store().close();

        const pid_t pid = ::fork();
        REQUIRE(pid >= 0);
        if (pid == 0) {
            JobStore store;
            StoreOpenResult result = StoreOpenResult::OpenedExisting;
            std::string error;
            if (store.open(fx.db(), result, error)) {
                MoveEngine engine(store);
                KillAfter k;
                k.phase = phases[i];
                engine.set_phase_hook(kill_after_phase, &k);
                engine.execute("job-k", fx.request(),
                               MoveStrategy::RenameNoReplace, error);
            }
            ::_exit(0);  // reached only if the hook never fired
        }

        int status = 0;
        REQUIRE(::waitpid(pid, &status, 0) == pid);
        CHECK(WIFSIGNALED(status) == true);

        // A fresh process, as a restart would be.
        StoreOpenResult result = StoreOpenResult::CreatedFresh;
        std::string error;
        REQUIRE(fx.store().open(fx.db(), result, error) == true);
        // The store must still be readable after the kill -- never silently
        // recreated, which would discard the record of a move that happened.
        CHECK(result == StoreOpenResult::OpenedExisting);

        MoveEngine restarted(fx.store());
        const MoveOutcome outcome = restarted.recover(
            "job-k", fx.request(), MoveStrategy::RenameNoReplace, error);
        INFO("recover error: " << error);
        CHECK(outcome == MoveOutcome::Completed);

        // Whatever instant the kill landed on, the end state is the same one:
        // delivered under its final name, source gone, no staging debris.
        CHECK(fx.kind_in(fx.dst(), "out.dat") == EntryKind::Regular);
        CHECK(fx.kind_in(fx.src(), "in.dat") == EntryKind::Missing);
        CHECK(fx.kind_in(fx.dst(), MoveEngine::staging_name("job-k")) ==
              EntryKind::Missing);
        CHECK(fx.state_of("job-k") == JobState::Done);
    }
}
