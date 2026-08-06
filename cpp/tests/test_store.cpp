// Durable job store tests (C1, ADR-0010).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-JOB-001..006, L2-JOB-010..015
//
// Every test works through the public repository interface. That is not
// incidental: L2-JOB-009 confines SQL and sqlite3.h to src/store.cpp, so a
// test that reached for a connection to check a row would be the first
// violation of the rule it is meant to protect. Where a property can only be
// observed from outside -- WAL files on disk, a store surviving a kill -- it is
// observed from outside rather than by peeking.

#include "catch2/catch.hpp"

#include "filemover/store.hpp"

#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <string>
#include <vector>

using filemover::CommitPhase;
using filemover::Job;
using filemover::JobState;
using filemover::JobStore;
using filemover::StoreOpenResult;
using filemover::WriteFailureAction;
using filemover::WriteFault;

namespace {

// A private directory per test. Tests run in one process and one working
// directory, so a shared filename would make them order-dependent -- and the
// crash tests below fork, which multiplies the ways that goes wrong.
class TempDir {
  public:
    TempDir() {
        char tmpl[] = "/tmp/fm-store-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        path_ = made;
    }

    ~TempDir() {
        // WAL leaves two sidecars beside the database; a clean close removes
        // them, but a killed process does not, and that is precisely the case
        // these tests create.
        ::unlink((db() + "-wal").c_str());
        ::unlink((db() + "-shm").c_str());
        ::unlink(db().c_str());
        ::rmdir(path_.c_str());
    }

    std::string db() const { return path_ + "/state.db"; }
    const std::string& path() const { return path_; }

  private:
    TempDir(const TempDir&);
    TempDir& operator=(const TempDir&);
    std::string path_;
};

bool exists(const std::string& path) {
    struct stat st;
    return ::stat(path.c_str(), &st) == 0;
}

Job make_job(const std::string& id, std::int64_t now_ms = 1000) {
    return Job(id, "/src/" + id, "/dst/" + id, now_ms);
}

// Opens and REQUIREs success, so each test reads as the property it is about
// rather than as four lines of setup.
void open_ok(JobStore& store, const std::string& path,
             StoreOpenResult expected) {
    StoreOpenResult result = StoreOpenResult::OpenedExisting;
    std::string error;
    INFO("open error: " << error);
    REQUIRE(store.open(path, result, error) == true);
    REQUIRE(error.empty() == true);
    CHECK(result == expected);
}

}  // namespace

// --- first boot and reopening -------------------------------------------

TEST_CASE("an absent store is first boot, not an error", "[store][L2-JOB-011]") {
    TempDir dir;
    REQUIRE(exists(dir.db()) == false);

    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    // "Starting successfully with zero recorded jobs" is the requirement, so
    // the emptiness is asserted rather than assumed from the absence of an
    // error.
    std::map<JobState, std::uint64_t> counts;
    std::string error;
    REQUIRE(store.counts_by_state(counts, error) == true);
    CHECK(counts[JobState::Queued] == 0u);
    CHECK(counts[JobState::Done] == 0u);
}

TEST_CASE("reopening an existing store reports it as existing",
          "[store][L2-JOB-011]") {
    TempDir dir;
    {
        JobStore first;
        open_ok(first, dir.db(), StoreOpenResult::CreatedFresh);
    }
    JobStore second;
    open_ok(second, dir.db(), StoreOpenResult::OpenedExisting);
}

TEST_CASE("schema creation is idempotent across opens", "[store][L2-JOB-004]") {
    TempDir dir;
    std::string error;

    for (int i = 0; i < 3; ++i) {
        JobStore store;
        StoreOpenResult result = StoreOpenResult::OpenedExisting;
        REQUIRE(store.open(dir.db(), result, error) == true);

        int version = 0;
        REQUIRE(store.schema_version(version, error) == true);
        CHECK(version == 1);
    }
}

TEST_CASE("WAL journaling is actually in effect", "[store][L2-JOB-002]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("wal-1"), error) == true);

    // Observed from the filesystem rather than by asking SQLite, because
    // "PRAGMA journal_mode says wal" is what open() already checks. The
    // sidecar existing is independent evidence.
    CHECK(exists(dir.db() + "-wal") == true);
}

// --- corruption ----------------------------------------------------------

TEST_CASE("a corrupt store is a hard error and is never recreated",
          "[store][L2-JOB-012]") {
    TempDir dir;

    // Not a database: a plausible-looking file that is not SQLite at all.
    {
        FILE* f = std::fopen(dir.db().c_str(), "wb");
        REQUIRE(f != 0);
        const char junk[] = "this is definitely not a SQLite database";
        std::fwrite(junk, 1, sizeof(junk) - 1, f);
        std::fclose(f);
    }
    struct stat before;
    REQUIRE(::stat(dir.db().c_str(), &before) == 0);

    JobStore store;
    StoreOpenResult result = StoreOpenResult::CreatedFresh;
    std::string error;
    REQUIRE(store.open(dir.db(), result, error) == false);

    // "A diagnosable error identifying the damage" -- an empty or generic
    // message would satisfy the return code and fail the requirement.
    CHECK(error.empty() == false);
    CHECK(error.find(dir.db()) != std::string::npos);

    // "Corruption shall never be silently skipped or partially recovered":
    // the damaged bytes must still be there, untouched, for an operator to
    // examine.
    struct stat after;
    REQUIRE(::stat(dir.db().c_str(), &after) == 0);
    CHECK(after.st_size == before.st_size);
    CHECK(store.is_open() == false);
}

namespace {

// Overwrites `length` bytes at `offset` with `fill`. Used to damage a store
// from outside, which is the only honest way to test the refusal paths: an
// injected error inside the process still unwinds cleanly, and what these
// requirements are about is a file that is already wrong when we meet it.
//
// Plain file I/O rather than SQL, so these tests stay on the right side of
// L2-JOB-009 like every other test here.
void poke(const std::string& path,
          long offset,
          const unsigned char* bytes,
          size_t length) {
    FILE* f = std::fopen(path.c_str(), "r+b");
    REQUIRE(f != 0);
    REQUIRE(std::fseek(f, offset, SEEK_SET) == 0);
    REQUIRE(std::fwrite(bytes, 1, length, f) == length);
    REQUIRE(std::fclose(f) == 0);
}

}  // namespace

TEST_CASE("a store whose schema does not match this build is refused",
          "[store][L2-JOB-004][L2-JOB-012]") {
    // Both directions, because this build carries no migration path: an older
    // database is exactly as unreadable as a newer one and both must be
    // refused rather than opened and misread. Before migrations were dropped
    // only the newer case was rejected and the older case was migrated, so a
    // single-direction test would now pass while missing half the contract.
    //
    // 0 is excluded deliberately -- that means "no schema yet" and is the one
    // value that must succeed.
    const int foreign_versions[] = {2, 7, 99};

    for (std::size_t i = 0; i < 3; ++i) {
        const int foreign = foreign_versions[i];
        INFO("schema version " << foreign);

        TempDir dir;
        {
            JobStore store;
            open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);
        }

        // user_version lives at byte 60 of the SQLite file header as a 4-byte
        // big-endian integer. Writing it directly produces a database this
        // build did not write without needing another build to exist.
        const unsigned char header[4] = {
            0x00, 0x00, static_cast<unsigned char>((foreign >> 8) & 0xFF),
            static_cast<unsigned char>(foreign & 0xFF)};
        poke(dir.db(), 60, header, sizeof(header));

        JobStore store;
        StoreOpenResult result = StoreOpenResult::CreatedFresh;
        std::string error;
        REQUIRE(store.open(dir.db(), result, error) == false);
        // The message has to tell an operator what to do about it, and the
        // remedy pre-v1.0.0 is to delete the file rather than wait for a
        // migration that is never coming.
        CHECK(error.find("delete the database") != std::string::npos);
        CHECK(store.is_open() == false);
    }
}

TEST_CASE("a store with a damaged page is refused and left intact",
          "[store][L2-JOB-012]") {
    TempDir dir;
    {
        JobStore store;
        std::string error;
        open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);
        // Enough rows to occupy pages beyond the header page, so there is
        // something structural to damage.
        for (int i = 0; i < 200; ++i) {
            std::ostringstream id;
            id << "job-" << i;
            REQUIRE(store.record_intent(make_job(id.str()), error) == true);
        }
    }

    struct stat before;
    REQUIRE(::stat(dir.db().c_str(), &before) == 0);
    REQUIRE(before.st_size > 4096);

    // Overwrite the start of the second page: its b-tree header, not the file
    // header, so the file still looks like a database and the damage has to be
    // found rather than noticed at the door.
    unsigned char junk[64];
    std::memset(junk, 0xA5, sizeof(junk));
    poke(dir.db(), 4096, junk, sizeof(junk));

    JobStore store;
    StoreOpenResult result = StoreOpenResult::CreatedFresh;
    std::string error;
    CHECK(store.open(dir.db(), result, error) == false);
    CHECK(error.empty() == false);
    CHECK(store.is_open() == false);

    // Never silently skipped or partially recovered: the damaged bytes are
    // still there for an operator to look at.
    struct stat after;
    REQUIRE(::stat(dir.db().c_str(), &after) == 0);
    CHECK(after.st_size == before.st_size);
}

// --- write-ahead ordering ------------------------------------------------

TEST_CASE("a recorded intent is durable before the call returns",
          "[store][L2-JOB-013]") {
    TempDir dir;
    std::string error;

    {
        JobStore writer;
        open_ok(writer, dir.db(), StoreOpenResult::CreatedFresh);
        REQUIRE(writer.record_intent(make_job("durable-1"), error) == true);
        // Deliberately no close() and no further work: the point is that the
        // record is already durable at the moment record_intent returned.
    }

    JobStore reader;
    open_ok(reader, dir.db(), StoreOpenResult::OpenedExisting);
    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(reader.load("durable-1", loaded, found, error) == true);
    REQUIRE(found == true);
    CHECK(loaded.source_path == std::string("/src/durable-1"));
    CHECK(loaded.state == JobState::Queued);
}

TEST_CASE("a duplicate id is refused rather than overwriting",
          "[store][L2-JOB-013]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("dup", 1000), error) == true);

    Job second("dup", "/other/source", "/other/dest", 2000);
    CHECK(store.record_intent(second, error) == false);
    CHECK(error.empty() == false);

    // The original must survive: overwriting it would erase the record of a
    // move that may already be in flight.
    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("dup", loaded, found, error) == true);
    REQUIRE(found == true);
    CHECK(loaded.source_path == std::string("/src/dup"));
}

TEST_CASE("loading an unknown job is not an error", "[store][L2-JOB-001]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = true;
    std::string error;
    CHECK(store.load("nope", loaded, found, error) == true);
    CHECK(found == false);
    CHECK(error.empty() == true);
}

// --- transitions and the FAILED invariant --------------------------------

TEST_CASE("legal transitions are persisted", "[store][L2-JOB-005]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("t1"), error) == true);
    REQUIRE(store.update_state("t1", JobState::Renaming, 2000, "", error) ==
            true);

    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("t1", loaded, found, error) == true);
    REQUIRE(found == true);
    CHECK(loaded.state == JobState::Renaming);
    CHECK(loaded.updated_at_ms == 2000);
}

TEST_CASE("an illegal transition is rejected and writes nothing",
          "[store][L2-JOB-005]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("t2"), error) == true);

    // Queued -> Done is not a legal edge.
    CHECK(store.update_state("t2", JobState::Done, 2000, "", error) == false);
    CHECK(error.empty() == false);

    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("t2", loaded, found, error) == true);
    CHECK(loaded.state == JobState::Queued);
    CHECK(loaded.updated_at_ms == 1000);
}

TEST_CASE("FAILED requires an error and other states forbid one",
          "[store][L2-JOB-010]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("inv"), error) == true);

    // FAILED with no description is refused.
    CHECK(store.update_state("inv", JobState::Failed, 2000, "", error) ==
          false);

    // A non-FAILED state carrying a description is refused.
    CHECK(store.update_state("inv", JobState::Renaming, 2000, "why", error) ==
          false);

    // The legal pairing is accepted and round-trips.
    REQUIRE(store.update_state("inv", JobState::Failed, 3000, "disk full",
                               error) == true);
    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("inv", loaded, found, error) == true);
    REQUIRE(found == true);
    CHECK(loaded.state == JobState::Failed);
    CHECK(loaded.error == std::string("disk full"));
    CHECK(loaded.finished_at_ms == 3000);
}

TEST_CASE("updating an unknown job is an error", "[store][L2-JOB-005]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    CHECK(store.update_state("ghost", JobState::Renaming, 2000, "", error) ==
          false);
    CHECK(error.empty() == false);
}

// --- queries -------------------------------------------------------------

TEST_CASE("jobs can be listed by state and counted", "[store][L2-JOB-006]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("a", 1000), error) == true);
    REQUIRE(store.record_intent(make_job("b", 1001), error) == true);
    REQUIRE(store.record_intent(make_job("c", 1002), error) == true);
    REQUIRE(store.update_state("b", JobState::Renaming, 2000, "", error) ==
            true);

    std::vector<Job> queued;
    REQUIRE(store.list_by_state(JobState::Queued, queued, error) == true);
    REQUIRE(queued.size() == 2u);
    CHECK(queued[0].id == std::string("a"));
    CHECK(queued[1].id == std::string("c"));

    std::vector<Job> renaming;
    REQUIRE(store.list_by_state(JobState::Renaming, renaming, error) == true);
    REQUIRE(renaming.size() == 1u);
    CHECK(renaming[0].id == std::string("b"));

    std::map<JobState, std::uint64_t> counts;
    REQUIRE(store.counts_by_state(counts, error) == true);
    CHECK(counts[JobState::Queued] == 2u);
    CHECK(counts[JobState::Renaming] == 1u);
    // States with no jobs are present as zero rather than absent, so a caller
    // rendering statistics need not special-case them.
    CHECK(counts.count(JobState::Done) == 1u);
    CHECK(counts[JobState::Done] == 0u);
}

// --- operator attention (L2-JOB-014, the durable half) -------------------

TEST_CASE("a job can be flagged for operator attention",
          "[store][L2-JOB-014]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("att"), error) == true);
    CHECK(store.mark_needs_attention("att", "write failed after commit",
                                     error) == true);

    // A flag with no reason is an alert nobody can act on.
    CHECK(store.mark_needs_attention("att", "", error) == false);
    // And flagging a job that does not exist is a mistake worth reporting.
    CHECK(store.mark_needs_attention("ghost", "reason", error) == false);
}

// --- the durable sequence ------------------------------------------------

TEST_CASE("the sequence is monotonic within a process",
          "[store][L2-JOB-015]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    std::uint64_t previous = 0;
    for (int i = 0; i < 5; ++i) {
        std::uint64_t value = 0;
        REQUIRE(store.next_sequence(value, error) == true);
        CHECK(value > previous);
        previous = value;
    }
}

TEST_CASE("the sequence does not restart across a reopen",
          "[store][L2-JOB-015]") {
    TempDir dir;
    std::string error;
    std::uint64_t before = 0;

    {
        JobStore store;
        open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);
        REQUIRE(store.next_sequence(before, error) == true);
        REQUIRE(store.next_sequence(before, error) == true);
    }

    JobStore reopened;
    open_ok(reopened, dir.db(), StoreOpenResult::OpenedExisting);
    std::uint64_t after = 0;
    REQUIRE(reopened.next_sequence(after, error) == true);

    // The failure this guards against is a counter held in memory: it would
    // hand out 1 again here, colliding identifiers and quietly pushing {seq}
    // templates into collision handling.
    CHECK(after > before);
}

// --- concurrency ---------------------------------------------------------

TEST_CASE("two connections may address the same store",
          "[store][L2-JOB-003]") {
    TempDir dir;
    std::string error;

    JobStore first;
    open_ok(first, dir.db(), StoreOpenResult::CreatedFresh);
    JobStore second;
    open_ok(second, dir.db(), StoreOpenResult::OpenedExisting);

    REQUIRE(first.record_intent(make_job("shared"), error) == true);

    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(second.load("shared", loaded, found, error) == true);
    CHECK(found == true);

    // And the sequence stays monotonic across both handles, which is the
    // property BEGIN IMMEDIATE exists to preserve.
    std::uint64_t a = 0;
    std::uint64_t b = 0;
    REQUIRE(first.next_sequence(a, error) == true);
    REQUIRE(second.next_sequence(b, error) == true);
    CHECK(b > a);
}

// --- L2-JOB-014: phase-dependent write-failure handling ------------------
//
// The requirement is about what happens when a durable write FAILS, so these
// tests make it fail for real: PRAGMA query_only makes SQLite refuse writes
// from its own write path. Nothing here substitutes a return value, because
// what has to work is detecting SQLite failing rather than us pretending it
// did.

TEST_CASE("a write that succeeds requires no action", "[store][L2-JOB-014]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("ok"), error) == true);
    CHECK(store.record_transition("ok", JobState::Renaming, 2000, "",
                                  CommitPhase::BeforeCommitPoint,
                                  error) == WriteFailureAction::None);
}

TEST_CASE("a write failure before the commit point aborts the job",
          "[store][L2-JOB-014]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("pre"), error) == true);
    REQUIRE(store.inject_write_fault(WriteFault::Refused, error) == true);

    error.clear();
    CHECK(store.record_transition("pre", JobState::Renaming, 2000, "",
                                  CommitPhase::BeforeCommitPoint,
                                  error) == WriteFailureAction::AbortJob);

    // "In neither case shall the software continue silently."
    CHECK(error.empty() == false);

    // Nothing happened, so nothing should have been recorded either.
    REQUIRE(store.inject_write_fault(WriteFault::None, error) == true);
    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("pre", loaded, found, error) == true);
    REQUIRE(found == true);
    CHECK(loaded.state == JobState::Queued);
}

TEST_CASE("a write failure after the commit point halts instead of aborting",
          "[store][L2-JOB-014]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("post"), error) == true);
    REQUIRE(store.update_state("post", JobState::Renaming, 2000, "", error) ==
            true);
    REQUIRE(store.inject_write_fault(WriteFault::Refused, error) == true);

    error.clear();
    const WriteFailureAction action =
        store.record_transition("post", JobState::Transferring, 3000, "",
                                CommitPhase::AfterCommitPoint, error);

    // The same failure, the opposite verdict. Treating both phases as one
    // retryable condition is the mistake this requirement exists to prevent.
    CHECK(action == WriteFailureAction::HaltProcess);
    CHECK(action != WriteFailureAction::AbortJob);
    CHECK(error.empty() == false);
    CHECK(error.find("source must NOT be deleted") != std::string::npos);
}

TEST_CASE("the attention flag is best-effort when the store is unwritable",
          "[store][L2-JOB-014]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("flag"), error) == true);
    REQUIRE(store.inject_write_fault(WriteFault::Refused, error) == true);

    // This is the uncomfortable case worth pinning down rather than
    // discovering in production: the HaltProcess path wants to flag the job,
    // but flagging is another write to the store that just refused one. It
    // fails, and it must fail loudly.
    //
    // That is exactly why L2-JOB-014 also requires logging at high severity.
    // The log is the guarantee; the flag is the convenience that survives when
    // the store is inconsistent rather than unreachable.
    error.clear();
    CHECK(store.mark_needs_attention("flag", "halted after commit", error) ==
          false);
    CHECK(error.empty() == false);

    // Once writable again the flag lands, so the failure above was the
    // injected condition rather than a broken code path.
    REQUIRE(store.inject_write_fault(WriteFault::None, error) == true);
    CHECK(store.mark_needs_attention("flag", "halted after commit", error) ==
          true);
}

TEST_CASE("a genuinely full store fails cleanly, not silently",
          "[store][L2-JOB-014]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.inject_write_fault(WriteFault::Full, error) == true);

    // SQLITE_FULL rather than a refusal, so this covers the out-of-space error
    // class as well as the read-only one. It takes a payload large enough to
    // need a new page; the loop is bounded so a future SQLite that packs rows
    // differently fails this test loudly instead of hanging.
    const std::string bulky(4096, 'x');
    bool saw_failure = false;
    for (int i = 0; i < 64 && !saw_failure; ++i) {
        std::ostringstream id;
        id << "full-" << i;
        Job job(id.str(), bulky, bulky, 1000);
        error.clear();
        if (!store.record_intent(job, error)) {
            saw_failure = true;
            CHECK(error.empty() == false);
        }
    }
    CHECK(saw_failure == true);

    // And the store is intact afterwards: a full disk is not corruption.
    REQUIRE(store.inject_write_fault(WriteFault::None, error) == true);
    std::map<JobState, std::uint64_t> counts;
    CHECK(store.counts_by_state(counts, error) == true);
}

TEST_CASE("a failed sequence bump rolls back and issues nothing",
          "[store][L2-JOB-014][L2-JOB-015]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    std::uint64_t before = 0;
    REQUIRE(store.next_sequence(before, error) == true);

    // The sequence bump is a transaction: BEGIN IMMEDIATE, UPDATE, read,
    // COMMIT. Until now nothing exercised what happens when the UPDATE fails
    // partway through, which is the path that decides whether a number can be
    // issued twice -- the one guarantee L2-JOB-015 makes.
    REQUIRE(store.inject_write_fault(WriteFault::Refused, error) == true);
    error.clear();
    std::uint64_t during = 12345;
    CHECK(store.next_sequence(during, error) == false);
    CHECK(error.empty() == false);
    // The out-parameter must be left alone on failure; a caller that ignored
    // the return value would otherwise use a number that was never committed.
    CHECK(during == 12345u);

    // After the rollback the store is still usable and the sequence resumes
    // without repeating. A transaction left open would deadlock the next bump
    // instead, which is what makes this worth asserting rather than assuming.
    REQUIRE(store.inject_write_fault(WriteFault::None, error) == true);
    std::uint64_t after = 0;
    REQUIRE(store.next_sequence(after, error) == true);
    CHECK(after > before);
}

TEST_CASE("arming a fault on a closed store is an error",
          "[store][L2-JOB-014]") {
    JobStore store;
    std::string error;
    CHECK(store.inject_write_fault(WriteFault::Refused, error) == false);
    CHECK(error.empty() == false);
}

// --- misuse of a closed store --------------------------------------------
//
// Every entry point guards on being open. Worth testing rather than assuming:
// the failure mode without the guard is a null dereference inside SQLite --
// a crash in a library, blamed on the library, from a caller mistake.

TEST_CASE("every operation on a closed store fails cleanly",
          "[store][L2-JOB-001]") {
    JobStore store;
    std::string error;
    REQUIRE(store.is_open() == false);

    CHECK(store.record_intent(make_job("x"), error) == false);
    CHECK(error.empty() == false);

    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    CHECK(store.load("x", loaded, found, error) == false);
    CHECK(store.update_state("x", JobState::Renaming, 1, "", error) == false);
    CHECK(store.mark_needs_attention("x", "reason", error) == false);

    std::vector<Job> jobs;
    CHECK(store.list_by_state(JobState::Queued, jobs, error) == false);

    std::map<JobState, std::uint64_t> counts;
    CHECK(store.counts_by_state(counts, error) == false);

    std::uint64_t sequence = 0;
    CHECK(store.next_sequence(sequence, error) == false);

    int version = 0;
    CHECK(store.schema_version(version, error) == false);
}

TEST_CASE("close is idempotent and safe on a store never opened",
          "[store][L2-JOB-001]") {
    JobStore store;
    store.close();
    store.close();
    CHECK(store.is_open() == false);
}

TEST_CASE("closing a store releases it for reopening", "[store][L2-JOB-003]") {
    TempDir dir;
    std::string error;

    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);
    REQUIRE(store.record_intent(make_job("closed-1"), error) == true);
    store.close();
    CHECK(store.is_open() == false);

    // Reopening the same object must work: close() has to leave it usable, not
    // merely non-crashing.
    open_ok(store, dir.db(), StoreOpenResult::OpenedExisting);
    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("closed-1", loaded, found, error) == true);
    CHECK(found == true);
}

TEST_CASE("an unopenable path is an error, not a crash",
          "[store][L2-JOB-012]") {
    JobStore store;
    StoreOpenResult result = StoreOpenResult::CreatedFresh;
    std::string error;

    // A directory that does not exist: SQLite cannot create the file.
    CHECK(store.open("/nonexistent-directory-for-tests/state.db", result,
                     error) == false);
    CHECK(error.empty() == false);
    CHECK(store.is_open() == false);
}

TEST_CASE("opening a second store closes the first connection",
          "[store][L2-JOB-003]") {
    TempDir first;
    TempDir second;
    std::string error;

    JobStore store;
    open_ok(store, first.db(), StoreOpenResult::CreatedFresh);
    REQUIRE(store.record_intent(make_job("in-first"), error) == true);

    // open() on an already-open object must not leak the previous handle; the
    // Valgrind tier would fail on the leak, but the behavioural half -- that
    // the object now addresses the new file -- is what this asserts.
    open_ok(store, second.db(), StoreOpenResult::CreatedFresh);
    Job loaded(std::string(), std::string(), std::string(), 0);
    bool found = true;
    REQUIRE(store.load("in-first", loaded, found, error) == true);
    CHECK(found == false);
}

TEST_CASE("a job awaiting retry records why without being FAILED",
          "[store][L2-RTY-003][L2-JOB-010]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("retry-me"), error) == true);
    REQUIRE(store.record_attempt("retry-me", 9000, "ESTALE from the export",
                                 error) == true);

    // The job is still QUEUED, so the L2-JOB-010 CHECK forbids `error` being
    // populated. last_error exists precisely so the diagnosis is not lost to
    // that invariant.
    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    REQUIRE(store.load("retry-me", job, found, error) == true);
    CHECK(job.state == JobState::Queued);
    CHECK(job.error.empty() == true);

    JobStore::RetryState retry;
    REQUIRE(store.load_retry_state("retry-me", retry, found, error) == true);
    CHECK(retry.last_error == std::string("ESTALE from the export"));
}

TEST_CASE("only due jobs are dispatched", "[store][L2-RTY-003]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    REQUIRE(store.record_intent(make_job("never-failed", 1000), error) == true);
    REQUIRE(store.record_intent(make_job("waiting", 1001), error) == true);
    REQUIRE(store.record_attempt("waiting", 5000, "not yet", error) == true);

    std::vector<std::string> due;
    REQUIRE(store.due_jobs(4999, due, error) == true);
    // A job that never failed has next_retry_ms == 0 and is always due, which
    // is what makes a first attempt indistinguishable from a retry to the
    // dispatcher.
    REQUIRE(due.size() == 1u);
    CHECK(due[0] == std::string("never-failed"));

    REQUIRE(store.due_jobs(5000, due, error) == true);
    CHECK(due.size() == 2u);

    // A job that is no longer QUEUED is never dispatched again.
    REQUIRE(store.update_state("never-failed", JobState::Renaming, 6000, "",
                               error) == true);
    REQUIRE(store.due_jobs(9999, due, error) == true);
    REQUIRE(due.size() == 1u);
    CHECK(due[0] == std::string("waiting"));
}

TEST_CASE("recording an attempt against an unknown job is an error",
          "[store][L2-RTY-003]") {
    TempDir dir;
    JobStore store;
    open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);

    std::string error;
    CHECK(store.record_attempt("ghost", 1, "why", error) == false);
    CHECK(error.empty() == false);

    JobStore::RetryState retry;
    bool found = true;
    CHECK(store.load_retry_state("ghost", retry, found, error) == true);
    CHECK(found == false);
}

TEST_CASE("retry state on a closed store fails cleanly",
          "[store][L2-RTY-003]") {
    JobStore store;
    std::string error;
    JobStore::RetryState retry;
    bool found = false;
    std::vector<std::string> due;

    CHECK(store.record_attempt("x", 1, "why", error) == false);
    CHECK(store.load_retry_state("x", retry, found, error) == false);
    CHECK(store.due_jobs(0, due, error) == false);
}

TEST_CASE("the sequence does not restart when a store is reopened",
          "[store][L2-JOB-015]") {
    // This used to run against a frozen v1 database, which made it a migration
    // test that happened to check the sequence. The property it actually cares
    // about is that the counter is durable across a reopen, and building the
    // starting state here tests that directly -- and keeps testing it now that
    // the fixture is gone with the migration path.
    TempDir dir;
    std::string error;

    {
        JobStore store;
        open_ok(store, dir.db(), StoreOpenResult::CreatedFresh);
        std::uint64_t issued = 0;
        for (int i = 0; i < 7; ++i) {
            REQUIRE(store.next_sequence(issued, error) == true);
        }
        CHECK(issued == 7u);
    }

    JobStore store;
    StoreOpenResult result = StoreOpenResult::CreatedFresh;
    REQUIRE(store.open(dir.db(), result, error) == true);
    REQUIRE(result == StoreOpenResult::OpenedExisting);

    std::uint64_t next = 0;
    REQUIRE(store.next_sequence(next, error) == true);

    // A build that reset the counter on open would hand out 1 here and collide
    // with every identifier the store had already issued.
    CHECK(next == 8u);
}

// --- kill at every statement ---------------------------------------------
//
// The roadmap's done-when for C1: SIGKILL the writer at successive points and
// prove the store is still readable and the sequence never repeats.
//
// SIGKILL rather than a clean exit, and in a forked child rather than a mocked
// failure, because the property under test is what the *file* looks like when
// a process dies mid-write. Nothing in-process can simulate that: an injected
// error still unwinds, closes handles and lets SQLite tidy up, which is the
// one thing a crash does not do.

namespace {

// Runs `steps` sequence bumps in a child process, reports the last value it
// obtained through a pipe, then kills itself outright. Returns the highest
// value the child managed to report, or 0 if it died before reporting any.
std::uint64_t child_bumps_then_dies(const std::string& db_path, int steps) {
    int fds[2];
    REQUIRE(::pipe(fds) == 0);

    const pid_t pid = ::fork();
    REQUIRE(pid >= 0);

    if (pid == 0) {
        // Child. No Catch2 assertions here: its failure reporting is not
        // fork-aware, and this process is about to be killed regardless.
        ::close(fds[0]);
        JobStore store;
        StoreOpenResult result = StoreOpenResult::OpenedExisting;
        std::string error;
        if (store.open(db_path, result, error)) {
            for (int i = 0; i < steps; ++i) {
                std::uint64_t value = 0;
                if (!store.next_sequence(value, error)) {
                    break;
                }
                const ssize_t written =
                    ::write(fds[1], &value, sizeof(value));
                (void)written;
            }
        }
        ::close(fds[1]);
        // Not exit(): that would run destructors, close the connection and
        // let SQLite clean up -- exactly what a crash does not do.
        ::raise(SIGKILL);
        ::_exit(127);  // unreachable; keeps the compiler happy
    }

    ::close(fds[1]);
    std::uint64_t highest = 0;
    std::uint64_t value = 0;
    while (::read(fds[0], &value, sizeof(value)) ==
           static_cast<ssize_t>(sizeof(value))) {
        if (value > highest) {
            highest = value;
        }
    }
    ::close(fds[0]);

    int status = 0;
    REQUIRE(::waitpid(pid, &status, 0) == pid);
    // The child must actually have been killed, not exited normally --
    // otherwise this test is quietly checking nothing.
    CHECK(WIFSIGNALED(status) == true);
    return highest;
}

}  // namespace

TEST_CASE("a store survives being killed mid-write, and the sequence never "
          "repeats",
          "[store][L2-JOB-012][L2-JOB-015]") {
    TempDir dir;
    std::string error;

    {
        JobStore seed;
        open_ok(seed, dir.db(), StoreOpenResult::CreatedFresh);
    }

    std::uint64_t highest_ever_issued = 0;

    // Increasing step counts put the kill at a different point in the write
    // sequence each round.
    for (int steps = 1; steps <= 6; ++steps) {
        const std::uint64_t child_highest =
            child_bumps_then_dies(dir.db(), steps);
        if (child_highest > highest_ever_issued) {
            highest_ever_issued = child_highest;
        }

        // Readable again after the kill, and reported as an existing store
        // rather than silently recreated.
        JobStore after;
        StoreOpenResult result = StoreOpenResult::CreatedFresh;
        REQUIRE(after.open(dir.db(), result, error) == true);
        CHECK(result == StoreOpenResult::OpenedExisting);

        std::uint64_t next = 0;
        REQUIRE(after.next_sequence(next, error) == true);

        // The invariant: never hand out a number already issued. Gaps are
        // fine -- a committed bump whose reader died is simply lost -- but a
        // repeat would collide job identifiers across a restart.
        CHECK(next > highest_ever_issued);
        highest_ever_issued = next;
    }
}
