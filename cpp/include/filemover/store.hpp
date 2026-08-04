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

    // L2-JOB-014, the after-the-commit-point half. When a durable write fails
    // after the move has committed, the source must NOT be deleted and the job
    // must be flagged for an operator. This records that flag.
    //
    // The phase policy itself — abort before the commit point, halt after —
    // belongs to the move engine (C3), which is the only component that knows
    // which side of the commit point it is on. What C1 owes it is a durable
    // place to record the verdict, and the guarantee that a failed write is
    // always reported rather than counted and swallowed.
    bool mark_needs_attention(const std::string& id,
                              const std::string& reason,
                              std::string& error);

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
