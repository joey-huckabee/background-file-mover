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
#include <poll.h>
#include <unistd.h>

#include <condition_variable>
#include <deque>
#include <mutex>
#include <sstream>
#include <thread>
#include <vector>

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

// --- the accept loop and handler pool (ADR-0013) --------------------------

namespace {

// The saturation response. Fixed bytes rather than a formatted one, because it
// is written from the accept thread and should not allocate there.
//
// Connection: close because L2-CTL-002 closes after every response anyway, and
// Content-Length because a body without one is a framing error waiting to be
// blamed on the client.
const char kServiceUnavailable[] =
    "HTTP/1.1 503 Service Unavailable\r\n"
    "Content-Type: application/json\r\n"
    "Content-Length: 58\r\n"
    "Connection: close\r\n"
    "\r\n"
    "{\"error\":\"all connection handlers are busy; retry shortly\"}";

// A send deadline on every accepted descriptor.
//
// Belongs here rather than in the handler because the REJECTION path writes
// from the accept thread: a client that connects, is refused, and then never
// reads would otherwise block the accept loop inside send() -- reintroducing
// the single-slow-client outage ADR-0013 exists to prevent, on the one path
// that never reaches a handler.
//
// L2-SEC-009 wants a configurable timeout on every blocking syscall; this is
// the floor, and the configurable form arrives with the read path.
void set_send_deadline(int fd, int seconds) {
    struct timeval tv;
    tv.tv_sec = seconds;
    tv.tv_usec = 0;
    (void)::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

const int kRejectSendTimeoutSeconds = 5;

}  // namespace

struct ConnectionServer::Impl {
    ListenSocket listener;
    ConnectionHandler handler;
    void* user_data;

    // Wakes the accept thread out of poll() on shutdown. A pipe rather than a
    // poll timeout: a timeout makes shutdown take up to one tick and makes the
    // loop spin for the rest of the time, and choosing that tick is choosing
    // between those two costs.
    int wake_read;
    int wake_write;

    mutable std::mutex mutex;
    std::condition_variable work_ready;

    std::deque<int> queued;   // accepted descriptors awaiting a handler
    unsigned idle;            // handlers not currently serving
    bool stopping;
    bool running;

    std::size_t served;
    std::size_t rejected;

    std::thread acceptor;
    std::vector<std::thread> handlers;

    Impl()
        : handler(0),
          user_data(0),
          wake_read(-1),
          wake_write(-1),
          idle(0),
          stopping(false),
          running(false),
          served(0),
          rejected(0) {}

    void run_acceptor();
    void run_handler();
    void close_wake();
};

void ConnectionServer::Impl::close_wake() {
    if (wake_read >= 0) {
        (void)::close(wake_read);
        wake_read = -1;
    }
    if (wake_write >= 0) {
        (void)::close(wake_write);
        wake_write = -1;
    }
}

void ConnectionServer::Impl::run_acceptor() {
    for (;;) {
        struct pollfd fds[2];
        fds[0].fd = listener.fd();
        fds[0].events = POLLIN;
        fds[0].revents = 0;
        fds[1].fd = wake_read;
        fds[1].events = POLLIN;
        fds[1].revents = 0;

        // No timeout: the self-pipe is the only other thing that can wake this,
        // and shutdown() writes it exactly once.
        const int ready = ::poll(fds, 2, -1);
        if (ready < 0) {
            if (errno == EINTR) {
                continue;
            }
            return;  // the listener is unusable; handlers still drain
        }
        if ((fds[1].revents & POLLIN) != 0) {
            return;  // shutdown
        }
        if ((fds[0].revents & POLLIN) == 0) {
            continue;
        }

        // accept4 with SOCK_CLOEXEC rather than accept plus fcntl: the flag is
        // applied atomically, so no fork on another thread can land in the
        // window between the two calls. Same reasoning as SOCK_CLOEXEC on the
        // listening socket -- and it keeps <fcntl.h>, a path-based filesystem
        // header banned by L2-SEC-001, out of this file entirely.
        const int conn = ::accept4(listener.fd(), 0, 0, SOCK_CLOEXEC);
        if (conn < 0) {
            // EMFILE and friends: one refused connection, not a dead server.
            // Returning here would turn a transient descriptor shortage into a
            // permanent outage.
            continue;
        }
        set_send_deadline(conn, kRejectSendTimeoutSeconds);

        bool accepted = false;
        {
            const std::lock_guard<std::mutex> guard(mutex);
            if (!stopping && idle > 0) {
                // The slot is reserved HERE, not when the handler wakes.
                // Decrementing on wake would let several connections past one
                // idle handler in the window before it runs.
                --idle;
                queued.push_back(conn);
                accepted = true;
                ++served;
            } else {
                ++rejected;
            }
        }

        if (accepted) {
            work_ready.notify_one();
            continue;
        }

        // Refused. Written from this thread, which is safe only because the
        // descriptor carries a send deadline.
        (void)::send(conn, kServiceUnavailable, sizeof(kServiceUnavailable) - 1,
                     MSG_NOSIGNAL);
        (void)::close(conn);
    }
}

void ConnectionServer::Impl::run_handler() {
    for (;;) {
        int conn = -1;
        {
            std::unique_lock<std::mutex> lock(mutex);
            work_ready.wait(lock,
                            [this]() { return !queued.empty() || stopping; });
            if (queued.empty()) {
                return;  // stopping, and nothing left to serve
            }
            conn = queued.front();
            queued.pop_front();
        }

        if (handler != 0) {
            handler(conn, user_data);
        }
        (void)::close(conn);

        {
            const std::lock_guard<std::mutex> guard(mutex);
            ++idle;
        }
    }
}

ConnectionServer::ConnectionServer() : impl_(new Impl()) {}

ConnectionServer::~ConnectionServer() {
    shutdown();
    delete impl_;
}

bool ConnectionServer::is_running() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->running;
}

std::uint16_t ConnectionServer::port() const { return impl_->listener.port(); }

std::size_t ConnectionServer::served_count() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->served;
}

std::size_t ConnectionServer::rejected_count() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->rejected;
}

bool ConnectionServer::start(const std::string& bind_address,
                             std::uint16_t port,
                             unsigned handlers,
                             ConnectionHandler handler,
                             void* user_data,
                             std::string& error) {
    {
        const std::lock_guard<std::mutex> guard(impl_->mutex);
        if (impl_->running) {
            error = "server: already running";
            return false;
        }
    }
    if (handlers == 0) {
        error = "server: handler count must be at least 1";
        return false;
    }
    if (handler == 0) {
        error = "server: no connection handler supplied";
        return false;
    }

    if (!impl_->listener.open(bind_address, port, kDefaultBacklog, error)) {
        return false;
    }

    // A socketpair rather than a pipe, for one reason: SOCK_CLOEXEC lives in
    // <sys/socket.h> while O_CLOEXEC lives in <fcntl.h>, and <fcntl.h> is the
    // path-based filesystem header L2-SEC-001 keeps out of files that have no
    // business opening paths. The two are equivalent for waking a poll, and the
    // socketpair sets close-on-exec atomically rather than in a second call.
    int wake[2] = {-1, -1};
    if (::socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, wake) != 0) {
        error = errno_text("server: socketpair", errno);
        impl_->listener.close();
        return false;
    }

    {
        const std::lock_guard<std::mutex> guard(impl_->mutex);
        impl_->wake_read = wake[0];
        impl_->wake_write = wake[1];
        impl_->handler = handler;
        impl_->user_data = user_data;
        impl_->idle = handlers;
        impl_->stopping = false;
        impl_->running = true;
        impl_->served = 0;
        impl_->rejected = 0;
    }

    // Threads spawned with the lock released, for the reason JobManager::start
    // records: every thread's first act is taking that same lock, so holding it
    // across construction serialises startup on the creating thread.
    for (unsigned i = 0; i < handlers; ++i) {
        impl_->handlers.push_back(
            std::thread(&ConnectionServer::Impl::run_handler, impl_));
    }
    impl_->acceptor = std::thread(&ConnectionServer::Impl::run_acceptor, impl_);

    error.clear();
    return true;
}

void ConnectionServer::shutdown() {
    std::thread acceptor;
    std::vector<std::thread> handlers;
    {
        const std::lock_guard<std::mutex> guard(impl_->mutex);
        if (!impl_->running) {
            return;
        }
        impl_->stopping = true;
        impl_->running = false;
        // One byte is enough: poll reports readable and the acceptor returns.
        if (impl_->wake_write >= 0) {
            const char b = 'x';
            (void)!::write(impl_->wake_write, &b, 1);
        }
        impl_->work_ready.notify_all();
        acceptor.swap(impl_->acceptor);
        handlers.swap(impl_->handlers);
    }

    if (acceptor.joinable()) {
        acceptor.join();
    }
    for (std::size_t i = 0; i < handlers.size(); ++i) {
        if (handlers[i].joinable()) {
            handlers[i].join();
        }
    }

    // Only after every thread has joined: closing the listener while the
    // acceptor still holds it in poll() is a use-after-close on a descriptor
    // number the kernel may already have reissued.
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    impl_->listener.close();
    impl_->close_wake();
    // Anything still queued was accepted but never served. Closing is the
    // honest end: the client sees the connection drop rather than hanging.
    while (!impl_->queued.empty()) {
        (void)::close(impl_->queued.front());
        impl_->queued.pop_front();
    }
}

}  // namespace filemover
