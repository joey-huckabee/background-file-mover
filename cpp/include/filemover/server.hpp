#ifndef FILEMOVER_SERVER_HPP
#define FILEMOVER_SERVER_HPP

// C5: the REST control plane's socket layer.
//
// Traces: L2-CTL-001, L2-SEC-009, L2-SEC-010
//
// The concurrency model is ADR-0013: an accept loop feeding a bounded pool of
// handler threads. This header owns the listening descriptor only; the pool and
// the routing sit above it. Splitting them is what keeps L2-CTL-014 reachable —
// route handlers stay pure functions of request and manager view, testable
// without a socket, because the socket is somewhere else.

#include <cstdint>
#include <string>

namespace filemover {

// A bound, listening TCP socket.
//
// RAII over one descriptor: the constructor allocates nothing and the
// destructor closes whatever is open. There is no copy, because two objects
// owning one descriptor is how a double close happens.
class ListenSocket {
  public:
    ListenSocket();
    ~ListenSocket();

    // Binds and listens.
    //
    // `bind_address` is a NUMERIC address — "127.0.0.1" or "::1". Name
    // resolution is deliberately disabled (AI_NUMERICHOST): a service that
    // resolves its own bind address at startup can be moved to a different
    // interface by whoever controls DNS, and the failure is silent because the
    // bind still succeeds. L2-CTL-001 defaults this to loopback, which at
    // v1.0.0 is the entire access control — there is no authentication and
    // ADR-0003 forbids in-process TLS.
    //
    // Port 0 asks the kernel for an ephemeral port; `port()` then reports which
    // one. That is how the tests bind without a fixed port and without racing
    // each other, and it is why port() exists at all.
    //
    // The descriptor is created with SOCK_CLOEXEC, so it does not survive into
    // a child process. The service forks nothing today, but a listening socket
    // leaked into a child is a port that stays held after the service exits.
    bool open(const std::string& bind_address,
              std::uint16_t port,
              int backlog,
              std::string& error);

    void close();
    bool is_open() const;

    // -1 when closed. Borrowed, never owned by the caller.
    int fd() const;

    // The port actually bound, which differs from the requested one when 0 was
    // asked for. Zero when closed.
    std::uint16_t port() const;

  private:
    ListenSocket(const ListenSocket&);
    ListenSocket& operator=(const ListenSocket&);

    int fd_;
    std::uint16_t port_;
};

// The default listen backlog. Not a tuning knob at v1.0.0: it bounds the
// kernel's accept queue, and ADR-0013 already bounds concurrency in userspace
// with the handler pool. A deep backlog here would only let more clients wait
// longer before meeting the same limit.
extern const int kDefaultBacklog;

// Serves one accepted connection. Called on a handler thread, with the
// descriptor owned by the server: the handler must not close it.
//
// A plain function pointer rather than std::function, matching the phase hook
// and the clock. Nothing here needs to capture, and a C++11 header that avoids
// <functional> stays cheap to include.
typedef void (*ConnectionHandler)(int fd, void* user_data);

// The accept loop and its bounded pool of handler threads (ADR-0013).
//
// One thread accepts; `handlers` threads serve. When every handler is busy the
// server answers 503 and closes rather than queueing without limit — the bound
// is the point, because without it the thread count is chosen by whoever is
// connecting.
//
// This class knows nothing about routes or JSON. It owns descriptors and
// threads, so that route handlers can stay pure functions of request and
// manager view and be tested without a socket (L2-CTL-014).
class ConnectionServer {
  public:
    ConnectionServer();
    ~ConnectionServer();

    // Binds, then starts the accept thread and the pool. `handlers` must be at
    // least 1. On failure nothing is left running and `error` says why.
    bool start(const std::string& bind_address,
               std::uint16_t port,
               unsigned handlers,
               ConnectionHandler handler,
               void* user_data,
               std::string& error);

    // Stops accepting, lets in-flight handlers finish the connection they are
    // serving, and joins every thread. Idempotent, and safe without a start.
    //
    // The accept thread is woken through a self-pipe rather than by waiting out
    // a poll timeout, so shutdown is prompt rather than "within the tick".
    void shutdown();

    bool is_running() const;

    // The port actually bound; 0 when not running. Port 0 at start() asks the
    // kernel to choose, which is what lets tests run without a fixed port.
    std::uint16_t port() const;

    // Connections handed to a handler, and connections refused with 503
    // because every handler was busy. Counters exist for the tests: saturation
    // behaviour is a requirement (ADR-0013), so it has to be observable.
    std::size_t served_count() const;
    std::size_t rejected_count() const;

  private:
    ConnectionServer(const ConnectionServer&);
    ConnectionServer& operator=(const ConnectionServer&);

    struct Impl;
    Impl* impl_;
};

}  // namespace filemover

#endif  // FILEMOVER_SERVER_HPP
