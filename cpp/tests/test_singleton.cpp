// Singleton lock tests (C6, L2-CTL-008).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// The cross-process cases fork, and report through a PIPE rather than the exit
// status. Under Valgrind the child inherits the tool, and its leak check
// reports the heap inherited at fork as still-reachable errors -- with
// --error-exitcode that makes the status non-zero whatever the child did. This
// is the third place in this suite to need that; test_service.cpp explains it
// at length and records the two earlier times it was got wrong.

#include "catch2/catch.hpp"

#include "filemover/singleton.hpp"

#include <stdlib.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cstring>
#include <string>

using filemover::lock_path_for_database;
using filemover::SingletonLock;

namespace {

// A temporary directory that cleans up after itself, including the .lock file
// the code under test deliberately leaves behind.
class TempDir {
  public:
    TempDir() {
        char tmpl[] = "/tmp/fm-singleton-XXXXXX";
        const char* made = ::mkdtemp(tmpl);
        path_ = (made != 0) ? made : "";
    }

    ~TempDir() {
        if (path_.empty()) {
            return;
        }
        const std::string db = database_path();
        ::unlink((db + ".lock").c_str());
        ::unlink(db.c_str());
        ::rmdir(path_.c_str());
    }

    bool ok() const { return !path_.empty(); }
    std::string database_path() const { return path_ + "/state.db"; }

  private:
    TempDir(const TempDir&);
    TempDir& operator=(const TempDir&);
    std::string path_;
};

// Runs `body` in a child process and returns the single byte it wrote.
// '1' means the child's acquire succeeded, '0' means it was refused.
char child_result(const std::string& db, bool release_before_exit) {
    int pipe_fds[2];
    REQUIRE(::pipe(pipe_fds) == 0);

    const pid_t pid = ::fork();
    REQUIRE(pid >= 0);

    if (pid == 0) {
        ::close(pipe_fds[0]);
        SingletonLock lock;
        std::string error;
        const char answer = lock.acquire(db, error) ? '1' : '0';
        (void)!::write(pipe_fds[1], &answer, 1);
        ::close(pipe_fds[1]);
        if (release_before_exit) {
            lock.release();
        }
        // _exit, not exit: no atexit handlers, no flushing of a stdio buffer
        // this child shares with the parent through fork.
        ::_exit(0);
    }

    ::close(pipe_fds[1]);
    char answer = '?';
    const ssize_t n = ::read(pipe_fds[0], &answer, 1);
    ::close(pipe_fds[0]);
    int status = 0;
    (void)::waitpid(pid, &status, 0);
    return (n == 1) ? answer : '?';
}

}  // namespace

// --- path derivation ------------------------------------------------------

TEST_CASE("the lock file is named after the database, beside it",
          "[singleton][L2-CTL-008]") {
    std::string dir;
    std::string name;
    std::string error;

    REQUIRE(lock_path_for_database("/var/lib/file-mover/state.db", dir, name,
                                   error) == true);
    CHECK(dir == std::string("/var/lib/file-mover"));
    CHECK(name == std::string("state.db.lock"));

    // A database at the filesystem root: the directory is "/", not "". An
    // empty string would reach open_root and fail with ENOENT, reporting a
    // missing directory instead of the real shape of the path.
    REQUIRE(lock_path_for_database("/state.db", dir, name, error) == true);
    CHECK(dir == std::string("/"));
    CHECK(name == std::string("state.db.lock"));

    // No slash at all: relative to the working directory.
    REQUIRE(lock_path_for_database("state.db", dir, name, error) == true);
    CHECK(dir == std::string("."));
    CHECK(name == std::string("state.db.lock"));
}

TEST_CASE("a path that names no file is refused", "[singleton][L2-CTL-008]") {
    std::string dir;
    std::string name;
    std::string error;

    CHECK(lock_path_for_database("", dir, name, error) == false);
    CHECK(error.empty() == false);

    // Trailing slash: there is no file name to derive a lock name from, and
    // silently locking "<dir>/.lock" would key the lock to the wrong thing.
    CHECK(lock_path_for_database("/var/lib/file-mover/", dir, name, error) ==
          false);
    CHECK(error.empty() == false);
}

// --- exclusion ------------------------------------------------------------

TEST_CASE("a second instance is refused while the first holds the lock",
          "[singleton][L2-CTL-008][L3-CTL-004]") {
    TempDir tmp;
    REQUIRE(tmp.ok() == true);

    SingletonLock first;
    std::string error;
    REQUIRE(first.acquire(tmp.database_path(), error) == true);
    CHECK(first.is_held() == true);

    // A second lock object in THIS process, which is the case fcntl(F_SETLK)
    // would silently allow -- POSIX record locks are owned per (process, file),
    // so the second would replace the first rather than be refused. flock is
    // owned by the open file description, so this is correctly a conflict.
    SingletonLock second;
    std::string second_error;
    CHECK(second.acquire(tmp.database_path(), second_error) == false);
    CHECK(second.is_held() == false);
    // The operator has to be able to tell this apart from a permissions
    // problem, so the message says what happened, not just that it failed.
    CHECK(second_error.find("already running") != std::string::npos);
    // ...and where to look.
    CHECK(second_error.find("state.db.lock") != std::string::npos);
}

TEST_CASE("a second PROCESS is refused too", "[singleton][L2-CTL-008]") {
    TempDir tmp;
    REQUIRE(tmp.ok() == true);

    SingletonLock held;
    std::string error;
    REQUIRE(held.acquire(tmp.database_path(), error) == true);

    CHECK(child_result(tmp.database_path(), true) == '0');
}

TEST_CASE("the lock is available again after a clean release",
          "[singleton][L2-CTL-008]") {
    TempDir tmp;
    REQUIRE(tmp.ok() == true);

    SingletonLock first;
    std::string error;
    REQUIRE(first.acquire(tmp.database_path(), error) == true);
    first.release();
    CHECK(first.is_held() == false);

    SingletonLock second;
    CHECK(second.acquire(tmp.database_path(), error) == true);
}

TEST_CASE("a lock file left behind is not a held lock",
          "[singleton][L2-CTL-008][L3-CTL-004]") {
    // The file is deliberately never unlinked, so every start after the first
    // finds one already there. If its mere existence blocked acquisition the
    // service would start exactly once per machine, ever -- which is the
    // failure mode of the pidfile design this replaces.
    TempDir tmp;
    REQUIRE(tmp.ok() == true);

    {
        SingletonLock warm;
        std::string error;
        REQUIRE(warm.acquire(tmp.database_path(), error) == true);
    }

    struct stat st;
    const std::string lock_file = tmp.database_path() + ".lock";
    REQUIRE(::stat(lock_file.c_str(), &st) == 0);  // still there

    SingletonLock again;
    std::string error;
    CHECK(again.acquire(tmp.database_path(), error) == true);
}

TEST_CASE("the kernel releases the lock when the holder dies",
          "[singleton][L2-CTL-008]") {
    // THE property that makes this a lock and not a pidfile. The child exits
    // via _exit WITHOUT releasing -- no destructor, no cleanup, nothing
    // written to disk to say it is gone. A pidfile scheme would need to decide
    // whether the recorded pid is still alive, and could not do it correctly
    // because pids are reused. Here the kernel has already answered.
    TempDir tmp;
    REQUIRE(tmp.ok() == true);

    REQUIRE(child_result(tmp.database_path(), false) == '1');  // child got it

    SingletonLock after;
    std::string error;
    CHECK(after.acquire(tmp.database_path(), error) == true);
}

TEST_CASE("a different database is a different lock",
          "[singleton][L2-CTL-008]") {
    // The lock is keyed to the resource. Two services on one host with
    // separate state directories are a supported configuration, and a lock
    // that excluded them would be excluding the wrong thing.
    TempDir a;
    TempDir b;
    REQUIRE(a.ok() == true);
    REQUIRE(b.ok() == true);

    SingletonLock first;
    SingletonLock second;
    std::string error;
    REQUIRE(first.acquire(a.database_path(), error) == true);
    CHECK(second.acquire(b.database_path(), error) == true);
}

TEST_CASE("acquiring twice through one object is refused",
          "[singleton][L2-CTL-008]") {
    TempDir tmp;
    REQUIRE(tmp.ok() == true);

    SingletonLock lock;
    std::string error;
    REQUIRE(lock.acquire(tmp.database_path(), error) == true);
    // Not silently re-acquired: that would leak the first descriptor and leave
    // the object holding a lock it no longer knows the name of.
    CHECK(lock.acquire(tmp.database_path(), error) == false);
    CHECK(lock.is_held() == true);
}

TEST_CASE("release is safe without an acquire", "[singleton][L2-CTL-008]") {
    SingletonLock lock;
    lock.release();
    lock.release();
    CHECK(lock.is_held() == false);
}

TEST_CASE("a missing directory is reported, not crashed on",
          "[singleton][L2-CTL-008]") {
    SingletonLock lock;
    std::string error;
    CHECK(lock.acquire("/nonexistent-dir-xyz/state.db", error) == false);
    CHECK(error.empty() == false);
    // Distinguishable from the contended case, which an operator would
    // otherwise chase by looking for a process that does not exist.
    CHECK(error.find("already running") == std::string::npos);
}
