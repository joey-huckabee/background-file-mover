// C1: the durable job store (ADR-0010).
// Traces: L2-JOB-001..006, L2-JOB-009..015, L2-STO-001
//
// L2-JOB-009: this is the ONLY translation unit permitted to include
// sqlite3.h or to contain SQL. scripts/assert-sql-confined.sh enforces it.

#include "filemover/store.hpp"

#include "sqlite/sqlite3.h"

#include <sys/stat.h>

#include <sstream>
#include <string>

namespace filemover {
namespace {

// PRAGMA user_version is SQLite's own slot for this and lives in the database
// header, so it costs no table and cannot disagree with the schema it
// describes.
//
// There is deliberately NO migration path, and this number does not climb with
// each schema change. Until v1.0.0 ships there are no databases in the field:
// every store is a developer or CI database and all of them are disposable, so
// a schema change recreates rather than migrates.
//
// That is a decision with an expiry date. The moment v1.0.0 is released this
// stops being true, and the migration machinery has to come back before the
// first schema change after it. Recorded in docs/ROADMAP.md.
//
// What remains is the check, which is cheap and still worth having: a database
// whose version does not match this build is REFUSED rather than opened and
// misread. A store written by a different schema is not a store this build
// understands, in either direction.
const int kSchemaVersion = 1;

// A connection that blocks briefly rather than returning SQLITE_BUSY the
// instant another writer holds the lock. WAL keeps readers out of the way, so
// this only covers writer-writer overlap, which is short.
const int kBusyTimeoutMs = 5000;

// Finalizes on every path. Statement leaks are invisible to the tests and
// fatal to the Valgrind tier, which treats still-reachable blocks as errors.
class Stmt {
  public:
    Stmt() : stmt_(0) {}
    ~Stmt() { finalize(); }

    void finalize() {
        if (stmt_ != 0) {
            sqlite3_finalize(stmt_);
            stmt_ = 0;
        }
    }

    sqlite3_stmt** out() { return &stmt_; }
    sqlite3_stmt* get() const { return stmt_; }

  private:
    Stmt(const Stmt&);
    Stmt& operator=(const Stmt&);
    sqlite3_stmt* stmt_;
};

std::string fail(sqlite3* db, const std::string& what) {
    std::ostringstream os;
    os << "store: " << what;
    if (db != 0) {
        os << ": " << sqlite3_errmsg(db);
    }
    return os.str();
}

// Rolls back, preserving the error that caused the rollback. Passing the live
// `error` to exec() here would let a ROLLBACK failure overwrite the real
// diagnosis with a less useful one -- the caller would be told the rollback
// failed and never told why anything was being rolled back.
void rollback_quietly(sqlite3* db);

bool exec(sqlite3* db, const char* sql, const std::string& what,
          std::string& error) {
    char* message = 0;
    const int rc = sqlite3_exec(db, sql, 0, 0, &message);
    if (rc != SQLITE_OK) {
        std::ostringstream os;
        os << "store: " << what << ": "
           << (message != 0 ? message : sqlite3_errmsg(db));
        error = os.str();
        if (message != 0) {
            sqlite3_free(message);
        }
        return false;
    }
    return true;
}

void rollback_quietly(sqlite3* db) {
    std::string discarded;
    exec(db, "ROLLBACK;", "rolling back", discarded);
}

// Runs a statement expected to yield exactly one text value, e.g. a PRAGMA
// read-back. Absence of a row is a failure rather than an empty string: a
// PRAGMA that returns nothing means it was not understood.
bool query_text(sqlite3* db, const char* sql, std::string& out,
                std::string& error) {
    Stmt stmt;
    if (sqlite3_prepare_v2(db, sql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(db, std::string("preparing '") + sql + "'");
        return false;
    }
    if (sqlite3_step(stmt.get()) != SQLITE_ROW) {
        error = fail(db, std::string("no result from '") + sql + "'");
        return false;
    }
    const unsigned char* text = sqlite3_column_text(stmt.get(), 0);
    out = (text != 0 ? reinterpret_cast<const char*>(text) : "");
    return true;
}

bool query_int(sqlite3* db, const char* sql, int& out, std::string& error) {
    Stmt stmt;
    if (sqlite3_prepare_v2(db, sql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(db, std::string("preparing '") + sql + "'");
        return false;
    }
    if (sqlite3_step(stmt.get()) != SQLITE_ROW) {
        error = fail(db, std::string("no result from '") + sql + "'");
        return false;
    }
    out = sqlite3_column_int(stmt.get(), 0);
    return true;
}

std::string column_text(sqlite3_stmt* stmt, int index) {
    const unsigned char* text = sqlite3_column_text(stmt, index);
    return text != 0 ? std::string(reinterpret_cast<const char*>(text))
                     : std::string();
}

// L2-JOB-010 lives here as well as in the core state machine. The core check
// governs this process; this constraint governs the file, so a row that could
// not have come from a legal transition cannot be stored even by a caller that
// bypasses update_state.
//
// `error` is NOT NULL with a '' default rather than nullable, so the invariant
// is a comparison of lengths instead of a three-valued NULL expression that
// silently evaluates to NULL and passes.
const char* const kSchemaSql =
    "CREATE TABLE IF NOT EXISTS job ("
    "  id               TEXT PRIMARY KEY,"
    "  source_path      TEXT NOT NULL,"
    "  dest_path        TEXT NOT NULL,"
    "  state            TEXT NOT NULL,"
    "  created_at_ms    INTEGER NOT NULL,"
    "  updated_at_ms    INTEGER NOT NULL,"
    "  finished_at_ms   INTEGER NOT NULL DEFAULT 0,"
    "  bytes_total      INTEGER NOT NULL DEFAULT 0,"
    "  bytes_moved      INTEGER NOT NULL DEFAULT 0,"
    "  error            TEXT NOT NULL DEFAULT '',"
    "  needs_attention  INTEGER NOT NULL DEFAULT 0,"
    "  attention_reason TEXT NOT NULL DEFAULT '',"
    // Schema v2, for L2-RTY-003. last_error is separate from `error` and not
    // a duplicate of it: the CHECK below binds `error` to be non-empty if and
    // only if the state is FAILED, so a job that failed once and is waiting to
    // retry -- and is therefore NOT FAILED -- has nowhere else to record why.
    // Overloading `error` would mean breaking the invariant or losing the
    // diagnosis.
    "  attempts         INTEGER NOT NULL DEFAULT 0,"
    "  next_retry_ms    INTEGER NOT NULL DEFAULT 0,"
    "  last_error       TEXT NOT NULL DEFAULT '',"
    // Schema v3, for L2-RTY-006. The id of the FAILED job this one replaces,
    // or '' for a job that was submitted directly. Manual retry records a new
    // job rather than reviving the old one, because FAILED is terminal under
    // L1-SYS-021 and reviving it would erase the record that it ever failed.
    "  retry_of         TEXT NOT NULL DEFAULT '',"
    "  CHECK (state IN ('QUEUED','RENAMING','TRANSFERRING','DONE','FAILED')),"
    "  CHECK ((length(error) > 0) = (state = 'FAILED')),"
    "  CHECK (needs_attention IN (0,1))"
    ");"
    "CREATE INDEX IF NOT EXISTS job_state_idx ON job(state);"
    // L2-JOB-015. One row, pinned to id 1 by a CHECK so the counter cannot be
    // forked into several rows that each look authoritative.
    "CREATE TABLE IF NOT EXISTS job_sequence ("
    "  id   INTEGER PRIMARY KEY CHECK (id = 1),"
    "  next INTEGER NOT NULL"
    ");"
    "INSERT OR IGNORE INTO job_sequence (id, next) VALUES (1, 0);";

// v1 -> v2. Separate from kSchemaSql because CREATE TABLE IF NOT EXISTS does
// nothing to a table that already exists: a store written by the v1 build has
// the old column set, and only ALTER adds to it.
//
// Column defaults carry the existing rows across without a data migration --
// zero attempts, no scheduled retry, no recorded failure is exactly right for
// jobs that predate retry.
}  // namespace

struct JobStore::Impl {
    sqlite3* db;
    Impl() : db(0) {}
};

JobStore::JobStore() : impl_(new Impl()) {}

JobStore::~JobStore() {
    close();
    delete impl_;
}

bool JobStore::is_open() const { return impl_->db != 0; }

void JobStore::close() {
    if (impl_->db != 0) {
        sqlite3_close(impl_->db);
        impl_->db = 0;
    }
}

bool JobStore::open(const std::string& path,
                    StoreOpenResult& result,
                    std::string& error) {
    close();

    // Checked before the open, because sqlite3_open_v2 creates the file and
    // afterwards the two cases are indistinguishable. L2-JOB-011 turns on this
    // distinction: absent is first boot, present-and-broken is fatal.
    struct stat st;
    const bool existed = (::stat(path.c_str(), &st) == 0);

    sqlite3* db = 0;
    const int rc = sqlite3_open_v2(
        path.c_str(), &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, 0);
    if (rc != SQLITE_OK) {
        // sqlite3_open_v2 returns a handle even on failure so the message can
        // be read from it; it still has to be closed.
        std::ostringstream os;
        os << "store: cannot open '" << path << "': "
           << (db != 0 ? sqlite3_errmsg(db) : sqlite3_errstr(rc));
        error = os.str();
        if (db != 0) {
            sqlite3_close(db);
        }
        return false;
    }

    sqlite3_busy_timeout(db, kBusyTimeoutMs);

    // L2-JOB-012. Only for a store that was already there: a file we just
    // created cannot be corrupt, and running the check on every first boot
    // would be pure cost.
    //
    // Deliberately integrity_check rather than quick_check. This runs once at
    // startup over a table of jobs, not a warehouse, and the cheaper variant
    // skips exactly the cross-page checks that catch the damage worth
    // refusing to start over.
    if (existed) {
        std::string verdict;
        if (!query_text(db, "PRAGMA integrity_check;", verdict, error)) {
            std::ostringstream os;
            os << "store: '" << path
               << "' is present but unreadable as a database (" << error
               << "). Refusing to start: continuing would discard the record "
                  "of jobs whose source files may still exist.";
            error = os.str();
            sqlite3_close(db);
            return false;
        }
        if (verdict != "ok") {
            std::ostringstream os;
            os << "store: '" << path << "' is corrupt: " << verdict
               << ". Refusing to start: corruption is never silently skipped "
                  "or partially recovered.";
            error = os.str();
            sqlite3_close(db);
            return false;
        }
    }

    // L2-JOB-002, and each setting is read back rather than assumed. A PRAGMA
    // that is misspelled or unsupported is silently accepted by SQLite, so
    // "we set it" and "it is set" are different claims.
    if (!exec(db, "PRAGMA foreign_keys=ON;", "enabling foreign keys", error) ||
        !exec(db, "PRAGMA journal_mode=WAL;", "enabling WAL", error) ||
        !exec(db, "PRAGMA synchronous=FULL;", "setting synchronous=FULL",
              error)) {
        sqlite3_close(db);
        return false;
    }

    std::string journal_mode;
    if (!query_text(db, "PRAGMA journal_mode;", journal_mode, error)) {
        sqlite3_close(db);
        return false;
    }
    if (journal_mode != "wal") {
        std::ostringstream os;
        os << "store: journal_mode is '" << journal_mode
           << "', expected 'wal' (ADR-0010)";
        error = os.str();
        sqlite3_close(db);
        return false;
    }

    int synchronous = 0;
    if (!query_int(db, "PRAGMA synchronous;", synchronous, error)) {
        sqlite3_close(db);
        return false;
    }
    if (synchronous != 2) {  // 2 == FULL
        std::ostringstream os;
        os << "store: synchronous is " << synchronous
           << ", expected 2 (FULL) (ADR-0010)";
        error = os.str();
        sqlite3_close(db);
        return false;
    }

    int foreign_keys = 0;
    if (!query_int(db, "PRAGMA foreign_keys;", foreign_keys, error)) {
        sqlite3_close(db);
        return false;
    }
    if (foreign_keys != 1) {
        error = "store: foreign_keys did not take effect";
        sqlite3_close(db);
        return false;
    }

    // L2-JOB-004: idempotent schema creation. CREATE TABLE IF NOT EXISTS makes
    // re-running harmless, and user_version records what was written.
    int version = 0;
    if (!query_int(db, "PRAGMA user_version;", version, error)) {
        sqlite3_close(db);
        return false;
    }
    // Any version other than 0 (empty) or ours is refused, in EITHER direction.
    // Pre-v1.0.0 there is no migration path by design -- see kSchemaVersion --
    // so an older database is exactly as unreadable as a newer one, and the
    // remedy for both is to delete it. Saying so is more useful than a message
    // about which build is ahead.
    if (version != 0 && version != kSchemaVersion) {
        std::ostringstream os;
        os << "store: database schema version " << version
           << " does not match this build's version " << kSchemaVersion
           << ". This is a pre-v1.0.0 build and carries no migration path: "
           << "delete the database file and restart. Refusing to open it "
           << "rather than misread it.";
        error = os.str();
        sqlite3_close(db);
        return false;
    }
    if (version == 0) {
        if (!exec(db, "BEGIN IMMEDIATE;", "beginning schema creation", error)) {
            rollback_quietly(db);
            sqlite3_close(db);
            return false;
        }
        if (!exec(db, kSchemaSql, "applying schema", error)) {
            rollback_quietly(db);
            sqlite3_close(db);
            return false;
        }
        // PRAGMA user_version does not accept a bound parameter, and the value
        // is a compile-time constant rather than anything a caller supplies.
        std::ostringstream set_version;
        set_version << "PRAGMA user_version=" << kSchemaVersion << ";";
        if (!exec(db, set_version.str().c_str(), "recording schema version",
                  error) ||
            !exec(db, "COMMIT;", "committing schema creation", error)) {
            rollback_quietly(db);
            sqlite3_close(db);
            return false;
        }
    }

    impl_->db = db;
    result = existed ? StoreOpenResult::OpenedExisting
                     : StoreOpenResult::CreatedFresh;
    return true;
}

bool JobStore::schema_version(int& out, std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }
    return query_int(impl_->db, "PRAGMA user_version;", out, error);
}

bool JobStore::record_intent(const Job& job, std::string& error) {
    return record_intent(job, std::string(), error);
}

bool JobStore::record_intent(const Job& job,
                             const std::string& retry_of,
                             std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    // L2-JOB-013. A plain INSERT, not INSERT OR REPLACE: a duplicate id must
    // be refused rather than overwrite the record of a move that may already
    // be in flight.
    static const char* const kSql =
        "INSERT INTO job (id, source_path, dest_path, state, created_at_ms,"
        "                 updated_at_ms, finished_at_ms, bytes_total,"
        "                 bytes_moved, error, retry_of)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?);";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing record_intent");
        return false;
    }

    sqlite3_bind_text(stmt.get(), 1, job.id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 2, job.source_path.c_str(), -1,
                      SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 3, job.dest_path.c_str(), -1,
                      SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 4, to_string(job.state), -1,
                      SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt.get(), 5, job.created_at_ms);
    sqlite3_bind_int64(stmt.get(), 6, job.updated_at_ms);
    sqlite3_bind_int64(stmt.get(), 7, job.finished_at_ms);
    sqlite3_bind_int64(stmt.get(), 8,
                       static_cast<sqlite3_int64>(job.bytes_total));
    sqlite3_bind_int64(stmt.get(), 9,
                       static_cast<sqlite3_int64>(job.bytes_moved));
    sqlite3_bind_text(stmt.get(), 10, job.error.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 11, retry_of.c_str(), -1, SQLITE_TRANSIENT);

    if (sqlite3_step(stmt.get()) != SQLITE_DONE) {
        error = fail(impl_->db, "recording intent for job '" + job.id + "'");
        return false;
    }
    return true;
}

bool JobStore::load(const std::string& id,
                    Job& out,
                    bool& found,
                    std::string& error) {
    found = false;
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    static const char* const kSql =
        "SELECT id, source_path, dest_path, state, created_at_ms,"
        "       updated_at_ms, finished_at_ms, bytes_total, bytes_moved, error"
        "  FROM job WHERE id = ?;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing load");
        return false;
    }
    sqlite3_bind_text(stmt.get(), 1, id.c_str(), -1, SQLITE_TRANSIENT);

    const int rc = sqlite3_step(stmt.get());
    if (rc == SQLITE_DONE) {
        return true;  // no such job; found stays false
    }
    if (rc != SQLITE_ROW) {
        error = fail(impl_->db, "loading job '" + id + "'");
        return false;
    }

    Job job(column_text(stmt.get(), 0), column_text(stmt.get(), 1),
            column_text(stmt.get(), 2), 0);

    const std::string token = column_text(stmt.get(), 3);
    if (!from_string(token, job.state)) {
        // Reachable only if the CHECK constraint and the core enumeration
        // disagree, which would mean the file was written by something else.
        error = "store: job '" + id + "' has unrecognised state '" + token +
                "'";
        return false;
    }

    job.created_at_ms = sqlite3_column_int64(stmt.get(), 4);
    job.updated_at_ms = sqlite3_column_int64(stmt.get(), 5);
    job.finished_at_ms = sqlite3_column_int64(stmt.get(), 6);
    job.bytes_total =
        static_cast<std::uint64_t>(sqlite3_column_int64(stmt.get(), 7));
    job.bytes_moved =
        static_cast<std::uint64_t>(sqlite3_column_int64(stmt.get(), 8));
    job.error = column_text(stmt.get(), 9);

    out = job;
    found = true;
    return true;
}

bool JobStore::update_state(const std::string& id,
                            JobState to,
                            std::int64_t now_ms,
                            const std::string& error_message,
                            std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    // Job has no default constructor by design (L3-CPP-005 fixes what a fresh
    // Job looks like), so this placeholder is overwritten by load().
    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    if (!load(id, job, found, error)) {
        return false;
    }
    if (!found) {
        error = "store: no such job '" + id + "'";
        return false;
    }

    // L2-JOB-005. The core state machine decides, not this layer: one set of
    // transition rules, in the component that already owns them and is already
    // exhaustively tested. Rejecting here means nothing is written at all.
    if (!job.transition(to, now_ms, error_message)) {
        std::ostringstream os;
        os << "store: illegal transition for job '" << id << "': "
           << to_string(job.state) << " -> " << to_string(to);
        if (to == JobState::Failed && error_message.empty()) {
            os << " (a transition to FAILED requires an error message)";
        } else if (to != JobState::Failed && !error_message.empty()) {
            os << " (an error message is only valid for FAILED)";
        }
        error = os.str();
        return false;
    }

    static const char* const kSql =
        "UPDATE job SET state = ?, updated_at_ms = ?, finished_at_ms = ?,"
        "               error = ?"
        " WHERE id = ?;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing update_state");
        return false;
    }
    sqlite3_bind_text(stmt.get(), 1, to_string(job.state), -1,
                      SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt.get(), 2, job.updated_at_ms);
    sqlite3_bind_int64(stmt.get(), 3, job.finished_at_ms);
    sqlite3_bind_text(stmt.get(), 4, job.error.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 5, id.c_str(), -1, SQLITE_TRANSIENT);

    if (sqlite3_step(stmt.get()) != SQLITE_DONE) {
        error = fail(impl_->db, "updating job '" + id + "'");
        return false;
    }
    return true;
}

WriteFailureAction JobStore::record_transition(const std::string& id,
                                               JobState to,
                                               std::int64_t now_ms,
                                               const std::string& error_message,
                                               CommitPhase phase,
                                               std::string& error) {
    if (update_state(id, to, now_ms, error_message, error)) {
        return WriteFailureAction::None;
    }

    // L2-JOB-014. The phase decides, and the two answers are opposites --
    // which is why the caller has to state the phase rather than let this
    // guess. `error` is already set by update_state; it is extended rather
    // than replaced so the operator sees both the cause and the consequence.
    std::ostringstream os;
    os << error;
    if (phase == CommitPhase::BeforeCommitPoint) {
        os << " [before the commit point: aborting the job. Nothing has "
              "happened and the source is untouched.]";
        error = os.str();
        return WriteFailureAction::AbortJob;
    }
    os << " [AFTER the commit point: halting. The move is real but unrecorded."
          " The source must NOT be deleted and this needs an operator.]";
    error = os.str();
    return WriteFailureAction::HaltProcess;
}

bool JobStore::inject_write_fault(WriteFault fault, std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    switch (fault) {
        case WriteFault::None:
            // Both mechanisms are lifted, because a test may have armed either
            // and leaving one set would silently poison whatever ran next.
            if (!exec(impl_->db, "PRAGMA query_only=OFF;",
                      "clearing query_only", error)) {
                return false;
            }
            return exec(impl_->db, "PRAGMA max_page_count=1073741823;",
                        "clearing the page limit", error);

        case WriteFault::Refused:
            return exec(impl_->db, "PRAGMA query_only=ON;",
                        "arming a write refusal", error);

        case WriteFault::Full: {
            // max_page_count clamps upward to the current page count rather
            // than shrinking the file, so pinning it to today's size makes the
            // next write that needs a NEW page fail with SQLITE_FULL. Writes
            // that fit in existing free space still succeed -- which is why
            // the deterministic tests use Refused and this mode is reserved
            // for proving a genuine out-of-space error is handled too.
            int pages = 0;
            if (!query_int(impl_->db, "PRAGMA page_count;", pages, error)) {
                return false;
            }
            std::ostringstream os;
            os << "PRAGMA max_page_count=" << pages << ";";
            return exec(impl_->db, os.str().c_str(), "arming a full store",
                        error);
        }
    }

    error = "store: unknown write fault";
    return false;
}

bool JobStore::mark_needs_attention(const std::string& id,
                                    const std::string& reason,
                                    std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }
    if (reason.empty()) {
        // An attention flag with no reason is an alert an operator cannot act
        // on, which is barely better than no alert at all.
        error = "store: mark_needs_attention requires a reason";
        return false;
    }

    static const char* const kSql =
        "UPDATE job SET needs_attention = 1, attention_reason = ?"
        " WHERE id = ?;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing mark_needs_attention");
        return false;
    }
    sqlite3_bind_text(stmt.get(), 1, reason.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 2, id.c_str(), -1, SQLITE_TRANSIENT);

    if (sqlite3_step(stmt.get()) != SQLITE_DONE) {
        error = fail(impl_->db, "flagging job '" + id + "'");
        return false;
    }
    if (sqlite3_changes(impl_->db) == 0) {
        error = "store: no such job '" + id + "'";
        return false;
    }
    return true;
}

bool JobStore::list_by_state(JobState state,
                             std::vector<Job>& out,
                             std::string& error) {
    out.clear();
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    static const char* const kSql =
        "SELECT id, source_path, dest_path, state, created_at_ms,"
        "       updated_at_ms, finished_at_ms, bytes_total, bytes_moved, error"
        "  FROM job WHERE state = ? ORDER BY created_at_ms, id;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing list_by_state");
        return false;
    }
    sqlite3_bind_text(stmt.get(), 1, to_string(state), -1, SQLITE_TRANSIENT);

    for (;;) {
        const int rc = sqlite3_step(stmt.get());
        if (rc == SQLITE_DONE) {
            break;
        }
        if (rc != SQLITE_ROW) {
            error = fail(impl_->db, "listing jobs");
            out.clear();
            return false;
        }

        Job job(column_text(stmt.get(), 0), column_text(stmt.get(), 1),
                column_text(stmt.get(), 2), 0);
        const std::string token = column_text(stmt.get(), 3);
        if (!from_string(token, job.state)) {
            error = "store: job '" + job.id + "' has unrecognised state '" +
                    token + "'";
            out.clear();
            return false;
        }
        job.created_at_ms = sqlite3_column_int64(stmt.get(), 4);
        job.updated_at_ms = sqlite3_column_int64(stmt.get(), 5);
        job.finished_at_ms = sqlite3_column_int64(stmt.get(), 6);
        job.bytes_total =
            static_cast<std::uint64_t>(sqlite3_column_int64(stmt.get(), 7));
        job.bytes_moved =
            static_cast<std::uint64_t>(sqlite3_column_int64(stmt.get(), 8));
        job.error = column_text(stmt.get(), 9);
        out.push_back(job);
    }
    return true;
}

bool JobStore::counts_by_state(std::map<JobState, std::uint64_t>& out,
                               std::string& error) {
    out.clear();
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    // Every state is seeded to zero first, so a caller rendering statistics
    // never has to distinguish "no jobs in this state" from "this state was
    // missing from the result".
    out[JobState::Queued] = 0;
    out[JobState::Renaming] = 0;
    out[JobState::Transferring] = 0;
    out[JobState::Done] = 0;
    out[JobState::Failed] = 0;

    static const char* const kSql =
        "SELECT state, COUNT(*) FROM job GROUP BY state;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing counts_by_state");
        return false;
    }

    for (;;) {
        const int rc = sqlite3_step(stmt.get());
        if (rc == SQLITE_DONE) {
            break;
        }
        if (rc != SQLITE_ROW) {
            error = fail(impl_->db, "counting jobs");
            out.clear();
            return false;
        }
        const std::string token = column_text(stmt.get(), 0);
        JobState state = JobState::Queued;
        if (!from_string(token, state)) {
            error = "store: unrecognised state '" + token + "' in job table";
            out.clear();
            return false;
        }
        out[state] =
            static_cast<std::uint64_t>(sqlite3_column_int64(stmt.get(), 1));
    }
    return true;
}

bool JobStore::record_attempt(const std::string& id,
                              std::int64_t next_retry_ms,
                              const std::string& reason,
                              std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    static const char* const kSql =
        "UPDATE job SET attempts = attempts + 1, next_retry_ms = ?,"
        "               last_error = ?"
        " WHERE id = ?;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing record_attempt");
        return false;
    }
    sqlite3_bind_int64(stmt.get(), 1, next_retry_ms);
    sqlite3_bind_text(stmt.get(), 2, reason.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt.get(), 3, id.c_str(), -1, SQLITE_TRANSIENT);

    if (sqlite3_step(stmt.get()) != SQLITE_DONE) {
        error = fail(impl_->db, "recording attempt for job '" + id + "'");
        return false;
    }
    if (sqlite3_changes(impl_->db) == 0) {
        error = "store: no such job '" + id + "'";
        return false;
    }
    return true;
}

bool JobStore::load_retry_state(const std::string& id,
                                RetryState& out,
                                bool& found,
                                std::string& error) {
    found = false;
    out = RetryState();
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    static const char* const kSql =
        "SELECT attempts, next_retry_ms, last_error, retry_of"
        " FROM job WHERE id = ?;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing load_retry_state");
        return false;
    }
    sqlite3_bind_text(stmt.get(), 1, id.c_str(), -1, SQLITE_TRANSIENT);

    const int rc = sqlite3_step(stmt.get());
    if (rc == SQLITE_DONE) {
        return true;
    }
    if (rc != SQLITE_ROW) {
        error = fail(impl_->db, "loading retry state for '" + id + "'");
        return false;
    }

    out.attempts = sqlite3_column_int(stmt.get(), 0);
    out.next_retry_ms = sqlite3_column_int64(stmt.get(), 1);
    out.last_error = column_text(stmt.get(), 2);
    out.retry_of = column_text(stmt.get(), 3);
    found = true;
    return true;
}

bool JobStore::due_jobs(std::int64_t now_ms,
                        std::vector<std::string>& out,
                        std::string& error) {
    out.clear();
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    // Ordered by next_retry_ms then created_at_ms, so a job that has been
    // waiting longest goes first and a burst of retries does not starve the
    // jobs that never failed.
    static const char* const kSql =
        "SELECT id FROM job"
        " WHERE state = 'QUEUED' AND next_retry_ms <= ?"
        " ORDER BY next_retry_ms, created_at_ms, id;";

    Stmt stmt;
    if (sqlite3_prepare_v2(impl_->db, kSql, -1, stmt.out(), 0) != SQLITE_OK) {
        error = fail(impl_->db, "preparing due_jobs");
        return false;
    }
    sqlite3_bind_int64(stmt.get(), 1, now_ms);

    for (;;) {
        const int rc = sqlite3_step(stmt.get());
        if (rc == SQLITE_DONE) {
            break;
        }
        if (rc != SQLITE_ROW) {
            error = fail(impl_->db, "listing due jobs");
            out.clear();
            return false;
        }
        out.push_back(column_text(stmt.get(), 0));
    }
    return true;
}

bool JobStore::next_sequence(std::uint64_t& out, std::string& error) {
    if (!is_open()) {
        error = "store: not open";
        return false;
    }

    // L2-JOB-015. BEGIN IMMEDIATE takes the write lock up front, so two
    // connections cannot both read the same value and then both write it back
    // incremented by one -- which is exactly how a sequence starts repeating.
    if (!exec(impl_->db, "BEGIN IMMEDIATE;", "beginning sequence bump",
              error)) {
        return false;
    }
    if (!exec(impl_->db, "UPDATE job_sequence SET next = next + 1 WHERE id = 1;",
              "bumping sequence", error)) {
        rollback_quietly(impl_->db);
        return false;
    }

    int value = 0;
    if (!query_int(impl_->db, "SELECT next FROM job_sequence WHERE id = 1;",
                   value, error)) {
        rollback_quietly(impl_->db);
        return false;
    }

    // Committed BEFORE the value is handed out. A crash here loses the number
    // rather than issuing it twice: gaps are acceptable, repeats are not.
    if (!exec(impl_->db, "COMMIT;", "committing sequence bump", error)) {
        rollback_quietly(impl_->db);
        return false;
    }

    out = static_cast<std::uint64_t>(value);
    return true;
}

}  // namespace filemover
