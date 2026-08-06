#ifndef FILEMOVER_STORE_HPP
#define FILEMOVER_STORE_HPP

// C1: the durable job store — SQLite in WAL mode with synchronous=FULL,
// behind a repository interface (ADR-0010).
//
// Traces: L2-JOB-001..006, L2-JOB-009..015, L2-STO-001
//
// L2-JOB-009 is the reason this header looks the way it does. It does not
// include `sqlite3.h`, and it must never do so: the vendored header and every
// SQL string in the project are confined to src/store.cpp. That is enforced
// mechanically by scripts/assert-sql-confined.sh rather than by review, for
// the same reason the vendored hashes are a gate — a containment rule nothing
// checks is a containment rule that erodes. The database handle is hidden
// behind a pimpl so no caller can acquire one by accident.
//
// Threading (L2-JOB-003): a JobStore owns exactly one connection and is NOT
// safe to share between threads. Each thread that needs the store constructs
// its own; several may address the same file concurrently, which is what WAL
// mode is for. This is a deliberate shape rather than an omission — a shared
// handle behind a mutex would serialise readers against writers and throw away
// the one property WAL provides.

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "filemover/job.hpp"

namespace filemover {

// Why an absent store is not an error, and a damaged one is (L2-JOB-011,
// L2-JOB-012). Open() reports which case it met so a caller can log the
// difference; the distinction is the whole point, so it is in the return type
// rather than in a message a caller has to parse.
enum class StoreOpenResult {
    OpenedExisting,   // a healthy store was already there
    CreatedFresh      // nothing was there; first boot, zero jobs
};

// Which side of the move's single atomic commit point a durable write sits on.
// L2-JOB-014 handles the two cases in opposite directions, so the caller must
// say which it is in; there is no safe default, and guessing here would pick
// the wrong one silently.
enum class CommitPhase {
    BeforeCommitPoint,   // nothing has happened yet; the source is untouched
    AfterCommitPoint     // the move is real, whether or not it was recorded
};

// What the caller must do when a durable write fails (L2-JOB-014).
//
// Returned rather than decided internally because the store cannot carry it
// out: aborting a job and halting a process are the move engine's actions.
// What the store owes is the classification and the guarantee that a failure
// is never reported as success.
enum class WriteFailureAction {
    None,          // the write succeeded; carry on
    AbortJob,      // before the commit point: discard the entry, touch nothing
    HaltProcess    // after the commit point: do NOT delete the source, flag the
                   // job for an operator, log at high severity
};

// Durability fault injection, for the tests that verify the above.
//
// Deliberately NOT behind an #ifdef. Conditional compilation would mean the
// failure handling exercised by the tests is not the failure handling that
// ships, and L2-JOB-014 is precisely the requirement where that difference
// would matter most. Default off, and the only way to arm it is an explicit
// call that no production path makes.
//
// Both modes provoke a real refusal from SQLite's own write path rather than a
// return value we substitute. That distinction is the point: what has to work
// is detecting SQLite failing, not us pretending it did.
enum class WriteFault {
    None,      // disarmed
    Refused,   // PRAGMA query_only -- SQLITE_READONLY. Deterministic: every
               // write fails, regardless of whether it would grow the file.
    Full       // PRAGMA max_page_count pinned to the current size -- a real
               // SQLITE_FULL, but only once a write actually needs a new page.
};

class JobStore {
  public:
    JobStore();
    ~JobStore();

    // Open (creating if absent) the store at `path`.
    //
    // L2-JOB-002: enables foreign keys, WAL journaling and synchronous=FULL,
    //             and verifies each took effect rather than assuming it.
    // L2-JOB-004: applies schema migrations idempotently, so opening an
    //             already-current store is a no-op.
    // L2-JOB-011: an absent store is first boot, not a failure.
    // L2-JOB-012: a present-but-corrupt store is a hard error naming the
    //             damage. It is never silently recreated or partially
    //             recovered — continuing past it would discard the record of
    //             jobs whose source files may still exist.
    //
    // On failure returns false with `error` set, and the object stays closed.
    bool open(const std::string& path,
              StoreOpenResult& result,
              std::string& error);

    // Idempotent; safe on an object that was never opened.
    void close();

    bool is_open() const;

    // L2-JOB-013: record the intent to move a file BEFORE any filesystem
    // action is taken. On return true the record is durable — committed with
    // synchronous=FULL — so a crash immediately afterwards still finds it.
    //
    // A false return means nothing was recorded, and the caller must take no
    // filesystem action at all. That asymmetry is the requirement: a recorded
    // intent for a move that never began is harmless and recovery discards it,
    // whereas a move that began with nothing recorded loses the file.
    //
    // Rejects a duplicate id rather than overwriting, so a resubmission cannot
    // silently erase the record of an in-flight move.
    bool record_intent(const Job& job, std::string& error);

    // As above, recording that this job replaces a FAILED one (L2-RTY-006).
    //
    // Manual retry submits a NEW job rather than reviving the failed one:
    // FAILED is terminal under L1-SYS-021, and walking back out of it would
    // erase the record that the job ever failed. `retry_of` is what keeps the
    // two connected, so the chain of attempts stays reconstructible from the
    // durable record alone.
    bool record_intent(const Job& job,
                       const std::string& retry_of,
                       std::string& error);

    // Apply a state transition and persist it.
    //
    // L2-JOB-005: the transition is validated by the core state machine
    //             (Job::transition) before anything is written, so the durable
    //             layer cannot record a state the core would have refused.
    // L2-JOB-010: the schema additionally enforces that `error` is non-empty
    //             if and only if the state is FAILED. That constraint is
    //             deliberate duplication: the core check governs this process,
    //             the CHECK governs the file, and a row that could not have
    //             been produced by a legal transition cannot be stored even by
    //             a future caller that bypasses this method.
    bool update_state(const std::string& id,
                      JobState to,
                      std::int64_t now_ms,
                      const std::string& error_message,
                      std::string& error);

    // L2-JOB-014. Records a transition, and classifies any durable-write
    // failure by the phase it happened in.
    //
    // Returns None on success. On failure it returns AbortJob before the
    // commit point and HaltProcess after it, and always sets `error` — the
    // requirement's last clause is that the software never continues silently,
    // so there is no path here that fails quietly or returns a retry count.
    //
    // Treating both phases as one retryable condition is the specific mistake
    // this exists to prevent: before the commit point, continuing means acting
    // with no durable record, and a crash then leaves an orphaned file nobody
    // can account for; after it, the move is real but unrecorded, and going on
    // to delete the source leaves reality and the record disagreeing — the
    // exact ambiguity L1-SEC-002 exists to rule out.
    WriteFailureAction record_transition(const std::string& id,
                                         JobState to,
                                         std::int64_t now_ms,
                                         const std::string& error_message,
                                         CommitPhase phase,
                                         std::string& error);

    // Flags a job for an operator. Used on the HaltProcess path.
    //
    // Best-effort by nature, and the caller must treat it that way. If the
    // durable write failed because the store is unwritable, then recording the
    // flag is another write to that same unwritable store and will fail too.
    // That is why L2-JOB-014 also requires logging at high severity: the log is
    // the guarantee, and this flag is the convenience that survives when the
    // store is merely inconsistent rather than unreachable.
    bool mark_needs_attention(const std::string& id,
                              const std::string& reason,
                              std::string& error);

    // Arms or disarms durability fault injection. See WriteFault.
    bool inject_write_fault(WriteFault fault, std::string& error);

    // `found` distinguishes "no such job" from "the query failed", which a
    // bool return alone would conflate.
    bool load(const std::string& id,
              Job& out,
              bool& found,
              std::string& error);

    // L2-JOB-006: query by state, and aggregate counts for the dashboard.
    bool list_by_state(JobState state,
                       std::vector<Job>& out,
                       std::string& error);

    // Every state is present in the result, including those with no jobs, so
    // a caller rendering statistics does not have to special-case absence.
    bool counts_by_state(std::map<JobState, std::uint64_t>& out,
                         std::string& error);

    // L2-JOB-015: a durable, monotonic sequence. Job identifiers and the
    // `{seq}` rename-template field both derive from it, and a counter held in
    // memory repeats after every restart — identifiers collide and `{seq}`
    // silently falls into collision handling instead of producing distinct
    // names.
    //
    // The value is committed before it is returned, so a crash can lose a
    // number but can never hand the same one out twice. Gaps are acceptable;
    // repeats are not.
    bool next_sequence(std::uint64_t& out, std::string& error);

    // The schema version recorded in the store, for diagnostics and for the
    // migration path a future schema change will need.
    bool schema_version(int& out, std::string& error);

    // L2-RTY-003: attempt count, next-retry time and last failure, durable so
    // a restart does not forget that a job has already failed four times.
    //
    // `last_error` is deliberately not `error`: the L2-JOB-010 CHECK binds
    // `error` to be non-empty if and only if the state is FAILED, and a job
    // awaiting a retry is not FAILED. Without a second column there is nowhere
    // to record why it is waiting.
    struct RetryState {
        int attempts;
        std::int64_t next_retry_ms;
        std::string last_error;
        // The FAILED job this one replaces, or empty for a directly submitted
        // job (L2-RTY-006).
        std::string retry_of;

        RetryState() : attempts(0), next_retry_ms(0) {}
    };

    // Records one failed attempt: increments the count, schedules the next
    // eligible time, and stores the reason. Does not change job state — the
    // caller decides whether this is a retry or a terminal failure, because
    // that decision belongs to the retry policy rather than the store.
    bool record_attempt(const std::string& id,
                        std::int64_t next_retry_ms,
                        const std::string& reason,
                        std::string& error);

    bool load_retry_state(const std::string& id,
                          RetryState& out,
                          bool& found,
                          std::string& error);

    // Queued jobs whose next-retry time has arrived. A job that has never
    // failed has next_retry_ms == 0 and is therefore always due, which is what
    // makes a first attempt indistinguishable from a retry to the dispatcher.
    bool due_jobs(std::int64_t now_ms,
                  std::vector<std::string>& out,
                  std::string& error);

  private:
    struct Impl;
    Impl* impl_;

    // A connection is not copyable, and copying one by accident would close
    // the same handle twice. C++11 on GCC 4.8, so this is the private-and-
    // undefined idiom rather than `= delete`-with-a-nicer-error.
    JobStore(const JobStore&);
    JobStore& operator=(const JobStore&);
};

}  // namespace filemover

#endif  // FILEMOVER_STORE_HPP
