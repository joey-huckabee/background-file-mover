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
#include <unistd.h>

#include <condition_variable>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

using filemover::ConnectionServer;

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
