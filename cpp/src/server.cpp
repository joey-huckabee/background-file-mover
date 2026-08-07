// C5: the REST control plane's socket layer.
// Traces: L2-CTL-001, L2-SEC-009, L2-SEC-010

#include "filemover/server.hpp"

#include <errno.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <cstring>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#include <sstream>

namespace filemover {

const int kDefaultBacklog = 64;

namespace {

std::string errno_text(const std::string& what, int err) {
    return what + ": " + std::strerror(err);
}

// Reads the port back out of whatever address family the kernel bound.
// Written as a switch rather than assuming IPv4, because open() accepts "::1"
// and a sockaddr_in cast over an IPv6 address reads the wrong sixteen bits and
// reports a plausible, wrong port.
bool port_from(const struct sockaddr_storage& ss, std::uint16_t& out) {
    if (ss.ss_family == AF_INET) {
        const struct sockaddr_in* v4 =
            reinterpret_cast<const struct sockaddr_in*>(&ss);
        out = ntohs(v4->sin_port);
        return true;
    }
    if (ss.ss_family == AF_INET6) {
        const struct sockaddr_in6* v6 =
            reinterpret_cast<const struct sockaddr_in6*>(&ss);
        out = ntohs(v6->sin6_port);
        return true;
    }
    return false;
}

}  // namespace

ListenSocket::ListenSocket() : fd_(-1), port_(0) {}

ListenSocket::~ListenSocket() { close(); }

bool ListenSocket::is_open() const { return fd_ >= 0; }

int ListenSocket::fd() const { return fd_; }

std::uint16_t ListenSocket::port() const { return port_; }

void ListenSocket::close() {
    if (fd_ >= 0) {
        // Return value ignored deliberately: there is nothing a caller can do
        // about a failed close of a listening socket, and retrying risks
        // closing a descriptor another thread has since been given.
        (void)::close(fd_);
        fd_ = -1;
    }
    port_ = 0;
}

bool ListenSocket::open(const std::string& bind_address,
                        std::uint16_t port,
                        int backlog,
                        std::string& error) {
    if (is_open()) {
        error = "server: listen socket is already open";
        return false;
    }
    if (bind_address.empty()) {
        error = "server: bind address is empty";
        return false;
    }
    if (backlog <= 0) {
        error = "server: backlog must be positive";
        return false;
    }

    // inet_pton rather than getaddrinfo, and this is not a style preference.
    //
    // getaddrinfo SEGFAULTS on the GCC 4.8.5 fidelity image. Reproduced with a
    // thirty-line program containing no project code: it crashes inside the
    // call, before returning, even with AI_NUMERICHOST set. The cause is
    // glibc's name-service switch, which getaddrinfo initialises and dlopens
    // regardless of whether resolution is actually requested.
    //
    // That makes it the wrong tool here on three counts. It crashes on the
    // deployment toolchain; it dlopens shared objects at startup, which is
    // exactly what ADR-0010's SQLITE_OMIT_LOAD_EXTENSION exists to prevent
    // elsewhere; and it is a resolver being asked to act as a parser.
    //
    // inet_pton is a parser. It touches no configuration, opens nothing, and
    // cannot resolve a name even by accident -- a stronger guarantee than
    // AI_NUMERICHOST, enforced by the function's nature rather than by a flag.
    struct sockaddr_storage addr;
    std::memset(&addr, 0, sizeof(addr));
    socklen_t addr_len = 0;
    int family = 0;

    struct sockaddr_in* v4 = reinterpret_cast<struct sockaddr_in*>(&addr);
    struct sockaddr_in6* v6 = reinterpret_cast<struct sockaddr_in6*>(&addr);

    if (::inet_pton(AF_INET, bind_address.c_str(), &v4->sin_addr) == 1) {
        family = AF_INET;
        v4->sin_family = AF_INET;
        v4->sin_port = htons(port);
        addr_len = sizeof(struct sockaddr_in);
    } else if (::inet_pton(AF_INET6, bind_address.c_str(), &v6->sin6_addr) ==
               1) {
        family = AF_INET6;
        v6->sin6_family = AF_INET6;
        v6->sin6_port = htons(port);
        addr_len = sizeof(struct sockaddr_in6);
    } else {
        error = "server: bind address '" + bind_address +
                "' is not a numeric IPv4 or IPv6 address. Names are not "
                "resolved: a service that resolves its own bind address can "
                "be moved to another interface by whoever controls the name, "
                "and the bind still succeeds.";
        return false;
    }

    // SOCK_CLOEXEC in the socket() call rather than fcntl afterwards: the
    // two-step version has a window in which a fork in another thread inherits
    // the descriptor.
    const int sock = ::socket(family, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (sock < 0) {
        error = errno_text("server: socket", errno);
        return false;
    }

    // Without this a restart fails for as long as the previous socket sits in
    // TIME_WAIT, which turns every deploy into a wait or a port change.
    const int on = 1;
    if (::setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on)) != 0) {
        error = errno_text("server: setsockopt SO_REUSEADDR", errno);
        (void)::close(sock);
        return false;
    }

    if (::bind(sock, reinterpret_cast<struct sockaddr*>(&addr), addr_len) != 0) {
        std::ostringstream os;
        os << "server: cannot bind " << bind_address << ":" << port << ": "
           << std::strerror(errno);
        error = os.str();
        (void)::close(sock);
        return false;
    }
    if (::listen(sock, backlog) != 0) {
        std::ostringstream os;
        os << "server: cannot listen on " << bind_address << ":" << port << ": "
           << std::strerror(errno);
        error = os.str();
        (void)::close(sock);
        return false;
    }

    // Read the bound port back rather than trusting the requested one. With
    // port 0 the requested value is not the answer, and a caller that assumed
    // it would connect to the wrong place.
    struct sockaddr_storage bound;
    std::memset(&bound, 0, sizeof(bound));
    socklen_t bound_len = sizeof(bound);
    if (::getsockname(sock, reinterpret_cast<struct sockaddr*>(&bound),
                      &bound_len) != 0) {
        error = errno_text("server: getsockname", errno);
        (void)::close(sock);
        return false;
    }
    std::uint16_t actual = 0;
    if (!port_from(bound, actual)) {
        error = "server: bound socket has an unexpected address family";
        (void)::close(sock);
        return false;
    }

    fd_ = sock;
    port_ = actual;
    error.clear();
    return true;
}

}  // namespace filemover
