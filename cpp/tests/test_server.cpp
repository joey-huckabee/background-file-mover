// Socket layer tests (C5).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-CTL-001, L2-SEC-009
//
// Every test binds to port 0 and asks the socket which port it got. Fixed
// ports make a suite that fails when something else on the machine happens to
// be listening, and fails differently when two of these run at once.

#include "catch2/catch.hpp"

#include "filemover/server.hpp"

#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstring>

#include <string>

using filemover::kDefaultBacklog;
using filemover::ListenSocket;

TEST_CASE("a socket binds to loopback and reports the port it got",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    REQUIRE(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);
    CHECK(error.empty() == true);
    CHECK(sock.is_open() == true);
    CHECK(sock.fd() >= 0);
    // Port 0 means "any", so the requested value is not the answer. A caller
    // that assumed it would connect to the wrong place.
    CHECK(sock.port() != 0);
}

TEST_CASE("the descriptor is close-on-exec", "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    REQUIRE(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);

    const int flags = ::fcntl(sock.fd(), F_GETFD);
    REQUIRE(flags >= 0);
    // A listening socket leaked into a child holds the port after this process
    // exits, and the next start fails to bind for reasons nothing explains.
    CHECK((flags & FD_CLOEXEC) == FD_CLOEXEC);
}

TEST_CASE("SO_REUSEADDR is set so a restart does not wait out TIME_WAIT",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    REQUIRE(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);

    int value = 0;
    socklen_t len = sizeof(value);
    REQUIRE(::getsockopt(sock.fd(), SOL_SOCKET, SO_REUSEADDR, &value, &len) ==
            0);
    CHECK(value != 0);
}

TEST_CASE("IPv6 loopback binds too", "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    // Skipped rather than failed where the environment has no IPv6: a
    // container without it is a fact about the runner, not a defect. Reported
    // so the skip is visible rather than silent.
    if (!sock.open("::1", 0, kDefaultBacklog, error)) {
        WARN("IPv6 loopback unavailable here; bind was not exercised: "
             << error);
        return;
    }
    CHECK(sock.port() != 0);
}

TEST_CASE("the bind address is parsed, never resolved",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    // AI_NUMERICHOST is what makes this fail. Without it the name resolves and
    // the service binds wherever DNS says -- succeeding, so nothing looks
    // wrong, while whoever controls the name controls the interface.
    CHECK(sock.open("localhost", 0, kDefaultBacklog, error) == false);
    CHECK(sock.is_open() == false);
    CHECK(error.empty() == false);

    std::string other;
    CHECK(sock.open("example.com", 0, kDefaultBacklog, other) == false);
}

TEST_CASE("a malformed or unusable bind address is refused with detail",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;

    CHECK(sock.open("", 0, kDefaultBacklog, error) == false);
    CHECK(error.empty() == false);

    CHECK(sock.open("999.1.1.1", 0, kDefaultBacklog, error) == false);
    CHECK(error.find("999.1.1.1") != std::string::npos);

    // An address that parses but belongs to no interface here.
    CHECK(sock.open("192.0.2.1", 0, kDefaultBacklog, error) == false);
    CHECK(error.find("192.0.2.1") != std::string::npos);

    CHECK(sock.is_open() == false);
}

TEST_CASE("a non-positive backlog is refused", "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    CHECK(sock.open("127.0.0.1", 0, 0, error) == false);
    CHECK(sock.open("127.0.0.1", 0, -1, error) == false);
    CHECK(sock.is_open() == false);
}

TEST_CASE("opening an already-open socket is refused rather than leaking",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    REQUIRE(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);
    const int first = sock.fd();

    // Without this check the second open would overwrite fd_ and the first
    // descriptor would be unreachable and never closed.
    CHECK(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == false);
    CHECK(sock.fd() == first);
    CHECK(sock.is_open() == true);
}

TEST_CASE("close is idempotent and leaves the object reusable",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    REQUIRE(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);

    sock.close();
    CHECK(sock.is_open() == false);
    CHECK(sock.fd() == -1);
    CHECK(sock.port() == 0);

    sock.close();  // second close must not double-close the descriptor
    CHECK(sock.is_open() == false);

    CHECK(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);
}

TEST_CASE("a second bind to the same port is refused",
          "[server][L2-CTL-001]") {
    ListenSocket first;
    std::string error;
    REQUIRE(first.open("127.0.0.1", 0, kDefaultBacklog, error) == true);
    const std::uint16_t taken = first.port();

    // SO_REUSEADDR permits rebinding a socket in TIME_WAIT; it does not permit
    // two live listeners on one port. This is the check that proves the option
    // was not set so permissively that a second instance could steal the port
    // from a running one -- which L2-CTL-008's singleton lock assumes cannot
    // happen at the socket layer.
    ListenSocket second;
    std::string second_error;
    CHECK(second.open("127.0.0.1", taken, kDefaultBacklog, second_error) ==
          false);
    CHECK(second_error.empty() == false);
}

TEST_CASE("an accepted connection reaches the listening socket",
          "[server][L2-CTL-001]") {
    ListenSocket sock;
    std::string error;
    REQUIRE(sock.open("127.0.0.1", 0, kDefaultBacklog, error) == true);

    const int client = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    REQUIRE(client >= 0);

    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(sock.port());
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    // listen() has already been called, so connect completes into the accept
    // queue without anyone having called accept yet. That is the property the
    // backlog provides and the reason this does not deadlock.
    REQUIRE(::connect(client, reinterpret_cast<struct sockaddr*>(&addr),
                      sizeof(addr)) == 0);

    const int served = ::accept(sock.fd(), 0, 0);
    CHECK(served >= 0);

    if (served >= 0) {
        ::close(served);
    }
    ::close(client);
}
