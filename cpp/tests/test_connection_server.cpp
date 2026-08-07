// Accept loop and handler pool tests (C5, ADR-0013).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-CTL-001, L2-SEC-009, L2-SEC-010
//
// Latch-based, like the C4 manager suite. The property under test is what
// happens while a handler is genuinely stuck, and a sleep makes that likely
// rather than certain.

#include "catch2/catch.hpp"

#include "filemover/server.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include <condition_variable>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

using filemover::ConnectionServer;
using filemover::ListenSocket;

namespace {

// Connects to loopback and returns the descriptor, or -1.
int connect_to(std::uint16_t port) {
    const int fd = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        return -1;
    }
    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(fd, reinterpret_cast<struct sockaddr*>(&addr),
                  sizeof(addr)) != 0) {
        ::close(fd);
        return -1;
    }
    return fd;
}

// Reads until the peer closes, so the whole response is seen rather than
// whatever happened to arrive in the first segment.
std::string read_all(int fd) {
    std::string out;
    char buf[512];
    for (;;) {
        const ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n <= 0) {
            break;
        }
        out.append(buf, static_cast<std::size_t>(n));
    }
    return out;
}

// Holds every handler that enters it until released, and counts arrivals. This
// is what makes "all handlers are busy" a fact rather than a hope.
struct HandlerLatch {
    std::mutex mutex;
    std::condition_variable cv;
    unsigned inside;
    unsigned total_seen;
    bool released;

    HandlerLatch() : inside(0), total_seen(0), released(false) {}

    static void serve(int fd, void* user) {
        HandlerLatch* l = static_cast<HandlerLatch*>(user);
        {
            std::unique_lock<std::mutex> lock(l->mutex);
            ++l->inside;
            ++l->total_seen;
            l->cv.notify_all();
            while (!l->released) {
                l->cv.wait(lock);
            }
            --l->inside;
        }
        const char ok[] = "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok";
        (void)::send(fd, ok, sizeof(ok) - 1, MSG_NOSIGNAL);
    }

    void wait_for_inside(unsigned n) {
        std::unique_lock<std::mutex> lock(mutex);
        while (inside < n) {
            cv.wait(lock);
        }
    }

    void release() {
        std::unique_lock<std::mutex> lock(mutex);
        released = true;
        cv.notify_all();
    }
};

// Replies immediately; used where holding is not the point.
void echo_ok(int fd, void* /*user*/) {
    const char ok[] = "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok";
    (void)::send(fd, ok, sizeof(ok) - 1, MSG_NOSIGNAL);
}

}  // namespace

// --- bounded I/O (L2-SEC-009) ---------------------------------------------

namespace {

// Records how each connection's first read ended, so a test can assert that a
// silent client was timed out rather than merely disconnected.
struct ReadOutcomes {
    std::mutex mutex;
    std::condition_variable cv;
    unsigned timed_out;
    unsigned closed;
    unsigned read_ok;

    ReadOutcomes() : timed_out(0), closed(0), read_ok(0) {}

    static void serve(int fd, void* user) {
        ReadOutcomes* o = static_cast<ReadOutcomes*>(user);
        char buf[256];
        std::size_t got = 0;
        const filemover::IoResult r =
            filemover::read_some(fd, buf, sizeof(buf), got);

        std::unique_lock<std::mutex> lock(o->mutex);
        if (r == filemover::IoResult::TimedOut) {
            ++o->timed_out;
        } else if (r == filemover::IoResult::PeerClosed) {
            ++o->closed;
        } else if (r == filemover::IoResult::Ok) {
            ++o->read_ok;
        }
        o->cv.notify_all();
    }

    void wait_until(unsigned total) {
        std::unique_lock<std::mutex> lock(mutex);
        while (timed_out + closed + read_ok < total) {
            cv.wait(lock);
        }
    }
};

}  // namespace

TEST_CASE("a client that connects and never writes is timed out, and others "
          "are served throughout",
          "[connserver][L2-SEC-009][L2-SEC-010]") {
    // The two requirements together, and the reason serial-accept could not
    // satisfy either. The timeout is deliberately short so the test is quick;
    // it is a real duration rather than a latch because a timeout is inherently
    // temporal -- there is nothing to latch on. The margins are wide enough
    // that a busy machine does not change the outcome.
    ReadOutcomes outcomes;
    filemover::ServerOptions options;
    options.handlers = 2;
    options.recv_timeout_ms = 150;
    options.send_timeout_ms = 150;

    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, options, ReadOutcomes::serve,
                         &outcomes, error) == true);

    // Connects and says nothing. Under serial-accept this is a total outage.
    const int silent = connect_to(server.port());
    REQUIRE(silent >= 0);

    // A well-behaved client, served while the silent one is still hanging.
    const int talker = connect_to(server.port());
    REQUIRE(talker >= 0);
    const char req[] = "GET / HTTP/1.1\r\n\r\n";
    REQUIRE(::send(talker, req, sizeof(req) - 1, MSG_NOSIGNAL) > 0);

    outcomes.wait_until(2);
    {
        std::unique_lock<std::mutex> lock(outcomes.mutex);
        // The silent connection ended by DEADLINE, not by the client leaving.
        // Asserting only "both handlers finished" would pass even if the
        // timeout did nothing and the client had simply been closed.
        CHECK(outcomes.timed_out == 1u);
        CHECK(outcomes.read_ok == 1u);
    }

    ::close(silent);
    ::close(talker);
    server.shutdown();
    CHECK(server.rejected_count() == 0u);
}

namespace {

// Reads THREE times, so the deadline is exercised across several syscalls
// rather than one. Records how many succeeded.
struct ReadRepeatedly {
    std::mutex mutex;
    std::condition_variable cv;
    unsigned succeeded;
    bool timed_out;
    bool done;

    ReadRepeatedly() : succeeded(0), timed_out(false), done(false) {}

    static void serve(int fd, void* user) {
        ReadRepeatedly* r = static_cast<ReadRepeatedly*>(user);
        unsigned ok = 0;
        bool late = false;
        for (int i = 0; i < 3; ++i) {
            char buf[64];
            std::size_t got = 0;
            const filemover::IoResult res =
                filemover::read_some(fd, buf, sizeof(buf), got);
            if (res == filemover::IoResult::Ok) {
                ++ok;
            } else {
                late = (res == filemover::IoResult::TimedOut);
                break;
            }
        }
        std::unique_lock<std::mutex> lock(r->mutex);
        r->succeeded = ok;
        r->timed_out = late;
        r->done = true;
        r->cv.notify_all();
    }

    void wait_done() {
        std::unique_lock<std::mutex> lock(mutex);
        while (!done) {
            cv.wait(lock);
        }
    }
};

}  // namespace

TEST_CASE("the deadline is per syscall, not a budget for the whole exchange",
          "[connserver][L2-SEC-009]") {
    // A client that keeps sending must never be cut off for being slow
    // overall. This is the distinction between SO_RCVTIMEO and a wall-clock
    // budget, and it is what L2-SEC-009's wording -- every potentially
    // blocking system call -- actually requires.
    //
    // The handler reads three times. Each read waits ~200 ms against a 400 ms
    // deadline, so every one succeeds; the exchange takes ~600 ms in total,
    // which a per-request budget of 400 ms would have killed. An earlier
    // version of this test read ONCE and therefore proved only that a single
    // slow read succeeds -- it would have passed against a per-request budget
    // too, which is precisely the design it claims to distinguish.
    ReadRepeatedly reader;
    filemover::ServerOptions options;
    options.handlers = 1;
    options.recv_timeout_ms = 400;
    options.send_timeout_ms = 400;

    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, options, ReadRepeatedly::serve,
                         &reader, error) == true);

    const int client = connect_to(server.port());
    REQUIRE(client >= 0);

    struct timespec pause;
    pause.tv_sec = 0;
    pause.tv_nsec = 200 * 1000 * 1000;  // 200 ms, half the deadline
    for (int i = 0; i < 3; ++i) {
        ::nanosleep(&pause, 0);
        REQUIRE(::send(client, "G", 1, MSG_NOSIGNAL) == 1);
    }

    reader.wait_done();
    {
        std::unique_lock<std::mutex> lock(reader.mutex);
        CHECK(reader.succeeded == 3u);
        CHECK(reader.timed_out == false);
    }

    ::close(client);
    server.shutdown();
}

TEST_CASE("a peer that closes is distinguished from one that stalls",
          "[connserver][L2-SEC-009]") {
    ReadOutcomes outcomes;
    filemover::ServerOptions options;
    options.handlers = 1;
    options.recv_timeout_ms = 2000;  // long, so a timeout would be wrong here
    options.send_timeout_ms = 2000;

    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, options, ReadOutcomes::serve,
                         &outcomes, error) == true);

    const int client = connect_to(server.port());
    REQUIRE(client >= 0);
    ::close(client);  // orderly shutdown, not a stall

    outcomes.wait_until(1);
    {
        std::unique_lock<std::mutex> lock(outcomes.mutex);
        // Collapsing these two into "the read failed" is what makes a stalled
        // connection indistinguishable from a client that hung up, and
        // L2-SEC-009 wants the suspicion recorded.
        CHECK(outcomes.closed == 1u);
        CHECK(outcomes.timed_out == 0u);
    }
    server.shutdown();
}

TEST_CASE("a non-positive timeout is refused rather than meaning 'forever'",
          "[connserver][L2-SEC-009]") {
    ConnectionServer server;
    std::string error;
    filemover::ServerOptions options;
    options.handlers = 1;

    options.recv_timeout_ms = 0;
    CHECK(server.start("127.0.0.1", 0, options, echo_ok, 0, error) == false);
    CHECK(error.empty() == false);

    options.recv_timeout_ms = 1000;
    options.send_timeout_ms = -1;
    CHECK(server.start("127.0.0.1", 0, options, echo_ok, 0, error) == false);
    CHECK(server.is_running() == false);
}

TEST_CASE("write_all reports a vanished peer rather than raising SIGPIPE",
          "[connserver][L2-SEC-009]") {
    ListenSocket listener;
    std::string error;
    REQUIRE(listener.open("127.0.0.1", 0, filemover::kDefaultBacklog, error) ==
            true);

    const int client = connect_to(listener.port());
    REQUIRE(client >= 0);
    const int served = ::accept(listener.fd(), 0, 0);
    REQUIRE(served >= 0);

    ::close(client);  // the peer is gone before anything is written

    // Without MSG_NOSIGNAL this delivers SIGPIPE and kills the whole service
    // because one client left early. The loop is generous so the failure is
    // reported rather than absorbed by a single small buffered write.
    std::string payload(64 * 1024, 'x');
    filemover::IoResult result = filemover::IoResult::Ok;
    for (int i = 0; i < 8 && result == filemover::IoResult::Ok; ++i) {
        result = filemover::write_all(served, payload.data(), payload.size());
    }
    CHECK(result != filemover::IoResult::Ok);

    ::close(served);
}

TEST_CASE("the server refuses to start without handlers or a callback",
          "[connserver][L2-CTL-001]") {
    ConnectionServer server;
    std::string error;
    CHECK(server.start("127.0.0.1", 0, 0, echo_ok, 0, error) == false);
    CHECK(server.start("127.0.0.1", 0, 2, 0, 0, error) == false);
    CHECK(server.is_running() == false);
}

TEST_CASE("a connection is accepted and served", "[connserver][L2-CTL-001]") {
    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, 2, echo_ok, 0, error) == true);
    REQUIRE(server.port() != 0);

    const int client = connect_to(server.port());
    REQUIRE(client >= 0);
    const std::string response = read_all(client);
    ::close(client);

    CHECK(response.find("200 OK") != std::string::npos);
    server.shutdown();
    CHECK(server.served_count() == 1u);
    CHECK(server.rejected_count() == 0u);
}

TEST_CASE("a stalled handler does not stop other connections being served",
          "[connserver][L2-SEC-010]") {
    // The direct refutation of serial-accept, and the argument ADR-0013 makes
    // against the single-threaded event loop: one connection stuck inside a
    // handler must not be a control-plane outage.
    HandlerLatch latch;
    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, 2, HandlerLatch::serve, &latch,
                         error) == true);

    const int stuck = connect_to(server.port());
    REQUIRE(stuck >= 0);
    latch.wait_for_inside(1);  // one handler is genuinely blocked

    // The second handler is free, so this connection must reach it while the
    // first is still stuck.
    const int other = connect_to(server.port());
    REQUIRE(other >= 0);
    latch.wait_for_inside(2);

    CHECK(server.rejected_count() == 0u);

    latch.release();
    CHECK(read_all(other).find("200 OK") != std::string::npos);
    CHECK(read_all(stuck).find("200 OK") != std::string::npos);
    ::close(other);
    ::close(stuck);

    server.shutdown();
    CHECK(server.served_count() == 2u);
}

TEST_CASE("saturation answers 503 rather than queueing without limit",
          "[connserver][L2-SEC-010]") {
    // ADR-0013's bound. Without it the thread count is chosen by whoever is
    // connecting; the failure mode of the unbounded design is process death,
    // and of this one a documented status code.
    HandlerLatch latch;
    ConnectionServer server;
    std::string error;
    const unsigned kHandlers = 2;
    REQUIRE(server.start("127.0.0.1", 0, kHandlers, HandlerLatch::serve, &latch,
                         error) == true);

    std::vector<int> busy;
    for (unsigned i = 0; i < kHandlers; ++i) {
        const int fd = connect_to(server.port());
        REQUIRE(fd >= 0);
        busy.push_back(fd);
    }
    latch.wait_for_inside(kHandlers);  // every handler is occupied

    // One more than the pool can serve.
    const int extra = connect_to(server.port());
    REQUIRE(extra >= 0);
    const std::string refused = read_all(extra);
    ::close(extra);

    // Refused promptly with an answer, not left hanging. The read returning at
    // all is half the assertion: a queueing server would block here.
    CHECK(refused.find("503") != std::string::npos);
    CHECK(refused.find("Connection: close") != std::string::npos);
    CHECK(server.rejected_count() == 1u);

    latch.release();
    for (std::size_t i = 0; i < busy.size(); ++i) {
        ::close(busy[i]);
    }
    server.shutdown();
    CHECK(server.served_count() == kHandlers);
}

TEST_CASE("shutdown lets an in-flight handler finish and joins every thread",
          "[connserver][L2-CTL-001]") {
    HandlerLatch latch;
    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, 2, HandlerLatch::serve, &latch,
                         error) == true);

    const int client = connect_to(server.port());
    REQUIRE(client >= 0);
    latch.wait_for_inside(1);

    // Released first, then shut down: shutdown must not be what unblocks the
    // handler, or the test would prove only that shutdown interrupts work.
    latch.release();
    server.shutdown();

    CHECK(server.is_running() == false);
    CHECK(read_all(client).find("200 OK") != std::string::npos);
    ::close(client);
}

TEST_CASE("shutdown is idempotent and safe without a start",
          "[connserver][L2-CTL-001]") {
    ConnectionServer server;
    server.shutdown();
    server.shutdown();
    CHECK(server.is_running() == false);

    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, 1, echo_ok, 0, error) == true);
    server.shutdown();
    server.shutdown();
    CHECK(server.is_running() == false);
}

TEST_CASE("the port is released for rebinding after shutdown",
          "[connserver][L2-CTL-001]") {
    std::string error;
    std::uint16_t port = 0;
    {
        ConnectionServer first;
        REQUIRE(first.start("127.0.0.1", 0, 1, echo_ok, 0, error) == true);
        port = first.port();
        first.shutdown();
    }
    // A listening descriptor left open by shutdown would make this fail, and
    // the failure would look like a flaky test rather than a leak.
    ConnectionServer second;
    CHECK(second.start("127.0.0.1", port, 1, echo_ok, 0, error) == true);
    second.shutdown();
}

TEST_CASE("starting an already-running server is refused",
          "[connserver][L2-CTL-001]") {
    ConnectionServer server;
    std::string error;
    REQUIRE(server.start("127.0.0.1", 0, 1, echo_ok, 0, error) == true);
    CHECK(server.start("127.0.0.1", 0, 1, echo_ok, 0, error) == false);
    CHECK(server.is_running() == true);
    server.shutdown();
}
