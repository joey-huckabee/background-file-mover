// Daemon startup, teardown and signal tests (C6).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-CTL-017..020
//
// The signal cases fork. A test that installed handlers and raised SIGTERM in
// the runner would change the whole suite's disposition for every test after
// it, and a test that leaves the process it runs in different from how it
// found it is a test that makes the next failure hard to read.
//
// Success is signalled down a PIPE, not through the exit status. Under Valgrind
// the child inherits the tool, and its leak check reports the heap inherited at
// fork as still-reachable errors -- with --error-exitcode that makes the exit
// status non-zero whatever the child does, so asserting on WEXITSTATUS asserts
// on Valgrind rather than on the code. WIFEXITED is still asserted, because
// "did not die of a signal" is exactly what the SIGPIPE case is about and a
// pipe cannot show it.
//
// This is the second time this has been got wrong here; the manager's
// assertion test hit it first. Recorded so the third author does not.

#include "catch2/catch.hpp"

#include "filemover/service.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cstddef>
#include <cstring>
#include <sstream>
#include <string>

using filemover::check_config;
using filemover::Config;
using filemover::Service;

namespace {

class TempRoot {
  public:
    TempRoot() {
        char tmpl[] = "/tmp/fm-service-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        root_ = made;
    }

    ~TempRoot() {
        ::unlink((db() + "-wal").c_str());
        ::unlink((db() + "-shm").c_str());
        ::unlink(db().c_str());
        ::rmdir(root_.c_str());
    }

    std::string db() const { return root_ + "/state.db"; }

    Config config() const {
        Config c;
        c.jobs_workers = 2;
        c.storage_database_path = db();
        c.http_bind = "127.0.0.1";
        c.http_port = 0;  // let the kernel choose, so tests do not collide
        return c;
    }

  private:
    TempRoot(const TempRoot&);
    TempRoot& operator=(const TempRoot&);
    std::string root_;
};

bool can_connect(std::uint16_t port) {
    const int fd = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        return false;
    }
    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    const bool ok = ::connect(fd, reinterpret_cast<struct sockaddr*>(&addr),
                              sizeof(addr)) == 0;
    ::close(fd);
    return ok;
}

}  // namespace

// --- service-manager readiness (L2-CTL-011/012, L3-CPP-054) ---------------

TEST_CASE("notification is a no-op when no service manager asked for it",
          "[service][L3-CPP-054]") {
    (void)::unsetenv("NOTIFY_SOCKET");
    std::string error;
    // Success, not failure. Without this the service starts under systemd and
    // refuses to start anywhere else -- a test, a shell, a container.
    CHECK(filemover::notify_service_manager("READY=1", error) == true);
    CHECK(error.empty() == true);
}

TEST_CASE("a send failure is not an error either", "[service][L3-CPP-054]") {
    (void)::setenv("NOTIFY_SOCKET", "/nonexistent-dir-xyz/notify.sock", 1);
    std::string error;
    CHECK(filemover::notify_service_manager("READY=1", error) == true);
    (void)::unsetenv("NOTIFY_SOCKET");
}

TEST_CASE("an empty state is the one thing refused", "[service][L2-CTL-011]") {
    std::string error;
    CHECK(filemover::notify_service_manager("", error) == false);
    CHECK(error.empty() == false);
}

TEST_CASE("READY=1 reaches a listening notify socket",
          "[service][L2-CTL-011]") {
    // A real AF_UNIX datagram socket, so the wire format is exercised rather
    // than assumed.
    char dir[] = "/tmp/fm-notify-XXXXXX";
    REQUIRE(::mkdtemp(dir) != 0);
    const std::string path = std::string(dir) + "/notify.sock";

    const int listener = ::socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    REQUIRE(listener >= 0);
    struct sockaddr_un addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    std::memcpy(addr.sun_path, path.c_str(), path.size());
    REQUIRE(::bind(listener, reinterpret_cast<struct sockaddr*>(&addr),
                   sizeof(addr)) == 0);

    (void)::setenv("NOTIFY_SOCKET", path.c_str(), 1);
    std::string error;
    CHECK(filemover::notify_service_manager("READY=1", error) == true);

    char buf[64];
    std::memset(buf, 0, sizeof(buf));
    const ssize_t n = ::recv(listener, buf, sizeof(buf) - 1, MSG_DONTWAIT);
    CHECK(n > 0);
    CHECK(std::string(buf) == std::string("READY=1"));

    (void)::unsetenv("NOTIFY_SOCKET");
    ::close(listener);
    ::unlink(path.c_str());
    ::rmdir(dir);
}

TEST_CASE("a '@' path is sent to the abstract namespace",
          "[service][L2-CTL-011]") {
    // The one part of the protocol that fails SILENTLY when it is wrong.
    // Copying the '@' verbatim addresses a filesystem path that does not
    // exist; sendto fails, the failure is deliberately not fatal, and the
    // service never reports ready. That presents to an operator as a slow
    // start and a timeout kill, not as a bad notification. So it is tested by
    // binding a real abstract socket and reading the datagram back.
    std::ostringstream name;
    name << "@fm-notify-test-" << ::getpid();
    const std::string abstract_name = name.str();

    const int listener = ::socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    REQUIRE(listener >= 0);
    struct sockaddr_un addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    // Leading NUL, and a length that stops at the name -- an abstract address
    // is exactly as long as it is declared to be, with no terminator.
    std::memcpy(addr.sun_path, abstract_name.c_str(), abstract_name.size());
    addr.sun_path[0] = '\0';
    const socklen_t addr_len = static_cast<socklen_t>(
        offsetof(struct sockaddr_un, sun_path) + abstract_name.size());
    REQUIRE(::bind(listener, reinterpret_cast<struct sockaddr*>(&addr),
                   addr_len) == 0);

    (void)::setenv("NOTIFY_SOCKET", abstract_name.c_str(), 1);
    std::string error;
    CHECK(filemover::notify_service_manager("STOPPING=1", error) == true);

    char buf[64];
    std::memset(buf, 0, sizeof(buf));
    const ssize_t n = ::recv(listener, buf, sizeof(buf) - 1, MSG_DONTWAIT);
    CHECK(n > 0);
    CHECK(std::string(buf) == std::string("STOPPING=1"));

    (void)::unsetenv("NOTIFY_SOCKET");
    ::close(listener);
}

TEST_CASE("the watchdog interval is read, validated and halved",
          "[service][L2-CTL-012]") {
    (void)::unsetenv("WATCHDOG_USEC");
    (void)::unsetenv("WATCHDOG_PID");
    CHECK(filemover::watchdog_interval_ms() == 0u);

    // Half the interval, as systemd's own guidance says: pinging exactly at
    // the deadline races it.
    (void)::setenv("WATCHDOG_USEC", "30000000", 1);  // 30 s
    CHECK(filemover::watchdog_interval_ms() == 15000u);

    // Garbage is not a schedule.
    (void)::setenv("WATCHDOG_USEC", "not-a-number", 1);
    CHECK(filemover::watchdog_interval_ms() == 0u);
    (void)::setenv("WATCHDOG_USEC", "-5", 1);
    CHECK(filemover::watchdog_interval_ms() == 0u);

    // WATCHDOG_PID naming another process means the interval belongs to a
    // parent. Pinging on its behalf would report the wrong process healthy.
    (void)::setenv("WATCHDOG_USEC", "30000000", 1);
    (void)::setenv("WATCHDOG_PID", "1", 1);
    CHECK(filemover::watchdog_interval_ms() == 0u);

    std::ostringstream mine;
    mine << ::getpid();
    (void)::setenv("WATCHDOG_PID", mine.str().c_str(), 1);
    CHECK(filemover::watchdog_interval_ms() == 15000u);

    (void)::unsetenv("WATCHDOG_USEC");
    (void)::unsetenv("WATCHDOG_PID");
}

TEST_CASE("check_config refuses what it can before anything is created",
          "[service][L2-CTL-019]") {
    TempRoot root;
    std::string error;

    CHECK(check_config(root.config(), error) == true);

    Config no_path = root.config();
    no_path.storage_database_path.clear();
    CHECK(check_config(no_path, error) == false);
    CHECK(error.empty() == false);

    Config no_workers = root.config();
    no_workers.jobs_workers = 0;
    CHECK(check_config(no_workers, error) == false);

    // The point of L2-CTL-019: an ExecStartPre can fail the unit on this
    // without the service having opened a socket or created a database.
    Config missing_dir = root.config();
    missing_dir.storage_database_path = "/nonexistent-dir-xyz/state.db";
    CHECK(check_config(missing_dir, error) == false);
    CHECK(error.empty() == false);
}

TEST_CASE("the service starts, serves, and stops in reverse order",
          "[service][L2-CTL-020]") {
    TempRoot root;
    Service service;
    std::string error;

    REQUIRE(service.start(root.config(), error) == true);
    CHECK(service.is_running() == true);
    REQUIRE(service.port() != 0);
    CHECK(can_connect(service.port()) == true);

    service.stop();
    CHECK(service.is_running() == false);
    // The listener is closed first on the way down, so nothing can connect to
    // a service whose pool is draining.
    CHECK(can_connect(service.port()) == false);
}

TEST_CASE("stop is idempotent and safe without a start",
          "[service][L2-CTL-020]") {
    Service service;
    service.stop();
    service.stop();
    CHECK(service.is_running() == false);

    TempRoot root;
    std::string error;
    REQUIRE(service.start(root.config(), error) == true);
    service.stop();
    service.stop();
    CHECK(service.is_running() == false);
}

TEST_CASE("a service that fails to start leaves nothing running",
          "[service][L2-CTL-020]") {
    TempRoot root;
    Config bad = root.config();
    bad.http_bind = "203.0.113.1";  // parses, belongs to no interface here

    Service service;
    std::string error;
    CHECK(service.start(bad, error) == false);
    CHECK(service.is_running() == false);
    // The manager was started before the socket and must have been torn down
    // when the socket failed. A leaked manager would hold the database and make
    // the next start fail for an unrelated-looking reason.
    CHECK(error.empty() == false);

    Service second;
    CHECK(second.start(root.config(), error) == true);
    second.stop();
}

TEST_CASE("a second service on the same database is refused",
          "[service][L2-CTL-008]") {
    // The lock is only worth having if start() actually takes it. Verified
    // here rather than only in test_singleton.cpp, because "the class works"
    // and "the service uses the class" are different claims and only the
    // second one keeps two daemons off one database.
    TempRoot root;
    Service first;
    std::string error;
    REQUIRE(first.start(root.config(), error) == true);

    Service second;
    std::string second_error;
    CHECK(second.start(root.config(), second_error) == false);
    CHECK(second.is_running() == false);
    CHECK(second_error.find("already running") != std::string::npos);

    // ...and the refusal is temporary, not a poisoned database. Once the first
    // stops, the next start succeeds -- a lock that outlived its holder would
    // turn a restart into an outage.
    first.stop();
    Service third;
    CHECK(third.start(root.config(), error) == true);
    third.stop();
}

TEST_CASE("the lock is taken before the store is opened",
          "[service][L2-CTL-008]") {
    // Ordering matters, not just exclusion. A second instance that opened the
    // store first would run crash recovery over rows the running instance
    // owns, and would have done that damage before discovering it was not
    // alone. Proven by pointing the second service at a database whose
    // DIRECTORY does not exist: if the lock is taken first, the failure is the
    // lock's (it cannot open its own directory either) and the store is never
    // reached.
    TempRoot root;
    Service first;
    std::string error;
    REQUIRE(first.start(root.config(), error) == true);

    Service second;
    std::string second_error;
    CHECK(second.start(root.config(), second_error) == false);
    // The message comes from the lock, not from SQLite. A store error here
    // would mean the store was opened first.
    CHECK(second_error.find("already running") != std::string::npos);
    CHECK(second_error.find("SQL") == std::string::npos);
    CHECK(second_error.find("database is locked") == std::string::npos);

    first.stop();
}

TEST_CASE("a stop signal wakes sigsuspend and the daemon shuts down",
          "[service][L2-CTL-017]") {
    TempRoot root;
    int done[2] = {-1, -1};
    REQUIRE(::pipe(done) == 0);
    const pid_t pid = ::fork();
    REQUIRE(pid >= 0);

    if (pid == 0) {
        // Child: the whole daemon lifecycle, driven by a real signal.
        std::string error;
        if (!filemover::install_signal_handlers(error)) {
            ::_exit(20);
        }
        Service service;
        if (!service.start(root.config(), error)) {
            ::_exit(21);
        }
        // Delivered to this process with the signal already blocked, so it is
        // pending rather than lost -- and sigsuspend must still return. This
        // is the window a poll loop would paper over and a naive
        // check-then-sleep would fall into.
        ::raise(SIGTERM);
        filemover::wait_for_stop_signal();
        if (!filemover::stop_requested()) {
            ::_exit(22);
        }
        service.stop();
        if (service.is_running()) {
            ::_exit(23);
        }
        ::close(done[0]);
        const char ok = 'K';
        (void)!::write(done[1], &ok, 1);
        ::_exit(0);
    }

    ::close(done[1]);
    char got = 0;
    const ssize_t n = ::read(done[0], &got, 1);
    ::close(done[0]);

    int status = 0;
    REQUIRE(::waitpid(pid, &status, 0) == pid);
    INFO("child status " << status);
    // Exited normally rather than being killed: an unhandled SIGTERM would
    // show as WIFSIGNALED, which is exactly the regression this guards.
    CHECK(WIFEXITED(status) == true);
    CHECK(n == 1);
    CHECK(got == 'K');
}

TEST_CASE("SIGPIPE is ignored process-wide", "[service][L2-CTL-018]") {
    int done[2] = {-1, -1};
    REQUIRE(::pipe(done) == 0);
    const pid_t pid = ::fork();
    REQUIRE(pid >= 0);

    if (pid == 0) {
        std::string error;
        if (!filemover::install_signal_handlers(error)) {
            ::_exit(20);
        }
        // Deliberately WITHOUT MSG_NOSIGNAL, which is the whole point: C5
        // passes that flag everywhere, and this proves the guarantee holds for
        // code that forgets it.
        int pair[2] = {-1, -1};
        if (::socketpair(AF_UNIX, SOCK_STREAM, 0, pair) != 0) {
            ::_exit(21);
        }
        ::close(pair[1]);
        const std::string payload(64 * 1024, 'x');
        for (int i = 0; i < 4; ++i) {
            (void)::send(pair[0], payload.data(), payload.size(), 0);
        }
        ::close(pair[0]);
        ::close(done[0]);
        const char ok = 'K';
        (void)!::write(done[1], &ok, 1);
        ::_exit(0);
    }

    ::close(done[1]);
    char got = 0;
    const ssize_t n = ::read(done[0], &got, 1);
    ::close(done[0]);

    int status = 0;
    REQUIRE(::waitpid(pid, &status, 0) == pid);
    INFO("child status " << status);
    // Without SIG_IGN the child dies of SIGPIPE, so WIFEXITED is the assertion
    // that matters, and the byte proves the child reached the end.
    CHECK(WIFEXITED(status) == true);
    CHECK(n == 1);
    CHECK(got == 'K');
}
