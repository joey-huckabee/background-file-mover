// Vendored SQLite integration checks (ADR-0004, ADR-0010).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: nothing, deliberately.
//
// Vendoring a dependency does not verify a requirement. The storage
// requirements (L2-STO-*, L2-JOB-*) are satisfied by the repository interface
// built in C1, not by proving that third-party code links, so these cases
// carry no requirement tag and must not acquire one. Tagging them would raise
// the trace-matrix figure without anything being implemented.
//
// What they do cover is the narrow set of things a vendoring commit can get
// wrong and no other gate would notice:
//
//   1. sqlite3.c and sqlite3.h drifting to different releases. VENDORED.md
//      hash-pins them as two independent rows, so each can be individually
//      intact while the pair is mismatched -- a checksum cannot see that.
//   2. The compile-time hardening in the Makefile silently not taking effect.
//      SQLITE_DEFS reaches the C translation unit only, so these are proved at
//      run time through observable behaviour rather than with #ifdef, which
//      would just be testing this file's own preprocessor state.

#include "catch2/catch.hpp"

#include "sqlite/sqlite3.h"

#include <unistd.h>

#include <string>

namespace {

// sqlite3_exec callback: keeps the first column of the first row.
int capture_first_column(void* out, int columns, char** values, char** names) {
    (void)names;
    if (columns > 0 && values != 0 && values[0] != 0) {
        *static_cast<std::string*>(out) = values[0];
    }
    return 0;
}

// Runs a statement, returning the first value it produced.
std::string query_scalar(sqlite3* db, const char* sql) {
    std::string value;
    char* error = 0;
    const int rc = sqlite3_exec(db, sql, capture_first_column, &value, &error);
    if (error != 0) {
        sqlite3_free(error);
    }
    REQUIRE(rc == SQLITE_OK);
    return value;
}

// Runs a statement expected to fail, returning SQLite's message.
std::string error_from(sqlite3* db, const char* sql) {
    char* error = 0;
    const int rc = sqlite3_exec(db, sql, 0, 0, &error);
    CHECK(rc != SQLITE_OK);
    std::string message;
    if (error != 0) {
        message = error;
        sqlite3_free(error);
    }
    return message;
}

// A private on-disk database. WAL is a file-level mode -- an :memory:
// database answers "memory" to journal_mode=WAL and reports success, so a
// memory-backed check would pass while proving nothing.
class TempDatabase {
 public:
    TempDatabase() : db_(0) {
        char path[] = "/tmp/fm-sqlite-vendor-XXXXXX";
        const int fd = mkstemp(path);
        REQUIRE(fd >= 0);
        close(fd);
        path_ = path;
        REQUIRE(sqlite3_open(path_.c_str(), &db_) == SQLITE_OK);
    }

    ~TempDatabase() {
        sqlite3_close(db_);
        // A clean close removes these itself; unlinked unconditionally so a
        // failed assertion mid-test cannot leave them behind.
        unlink((path_ + "-wal").c_str());
        unlink((path_ + "-shm").c_str());
        unlink(path_.c_str());
    }

    sqlite3* get() const { return db_; }

 private:
    TempDatabase(const TempDatabase&);
    TempDatabase& operator=(const TempDatabase&);

    std::string path_;
    sqlite3* db_;
};

}  // namespace

TEST_CASE("the vendored header and amalgamation are the same release",
          "[sqlite][vendor]") {
    // SQLITE_VERSION comes from sqlite3.h at compile time;
    // sqlite3_libversion() comes from sqlite3.c at run time.
    CHECK(std::string(sqlite3_libversion()) == std::string(SQLITE_VERSION));
    CHECK(sqlite3_libversion_number() == SQLITE_VERSION_NUMBER);

    // Pinned in cpp/VENDORED.md. Update both together, deliberately.
    CHECK(std::string(SQLITE_VERSION) == std::string("3.53.4"));
}

TEST_CASE("the build is threadsafe", "[sqlite][vendor]") {
    // SQLITE_THREADSAFE=1. C4 introduces the first worker threads; a build
    // that came out as 0 would stay invisible until they exist.
    CHECK(sqlite3_threadsafe() != 0);
}

TEST_CASE("WAL and synchronous=FULL are available on a file database",
          "[sqlite][vendor]") {
    // The two settings ADR-0010 mandates for the durable store.
    TempDatabase db;
    CHECK(query_scalar(db.get(), "PRAGMA journal_mode=WAL;") ==
          std::string("wal"));
    query_scalar(db.get(), "PRAGMA synchronous=FULL;");
    CHECK(query_scalar(db.get(), "PRAGMA synchronous;") == std::string("2"));
}

TEST_CASE("loadable extensions are compiled out", "[sqlite][vendor]") {
    // SQLITE_OMIT_LOAD_EXTENSION. A database file must never be able to make
    // this process dlopen anything. With the option set the SQL function is
    // not registered at all, so the parser rejects the name outright.
    TempDatabase db;
    const std::string message =
        error_from(db.get(), "SELECT load_extension('/nonexistent.so');");
    CHECK(message.find("no such function") != std::string::npos);
}

TEST_CASE("double-quoted strings are rejected as identifiers",
          "[sqlite][vendor]") {
    // SQLITE_DQS=0. By default SQLite falls back to treating an unresolvable
    // double-quoted identifier as a string literal, which turns a mistyped
    // column name into a silently constant value rather than an error.
    TempDatabase db;
    REQUIRE(sqlite3_exec(db.get(), "CREATE TABLE t(id INTEGER);", 0, 0, 0) ==
            SQLITE_OK);
    const std::string message =
        error_from(db.get(), "SELECT \"not_a_column\" FROM t;");
    CHECK(message.find("no such column") != std::string::npos);
}
