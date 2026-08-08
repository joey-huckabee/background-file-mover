#ifndef FILEMOVER_SERVICE_HPP
#define FILEMOVER_SERVICE_HPP

// C6: the daemon -- signals, startup order, and teardown.
//
// Traces: L2-CTL-017..020, L2-CTL-008
//
// `main` is deliberately thin and lives elsewhere. Everything a test would want
// to drive is here, because a component reachable only through `main` is a
// component tested by starting a process and hoping.

#include <string>

#include "filemover/config.hpp"
#include "filemover/http_service.hpp"
#include "filemover/manager.hpp"
#include "filemover/server.hpp"

namespace filemover {

// L2-CTL-019: everything that can be checked without creating anything.
//
// Exists so a systemd ExecStartPre can fail the unit before the service has
// opened a socket, created a database, or written a line of log. A daemon that
// validates its configuration *after* starting has already done half its
// damage by the time it complains.
//
// Performs I/O -- it stats the storage path to confirm the filesystem is local
// (L2-JOB-008) -- which is why it is separate from load_config_from_string,
// which L3-CPP-040 requires to stay pure.
bool check_config(const Config& config, std::string& error);

// Startup order, and its reverse on the way down (L2-CTL-020).
//
//   store  ->  manager  ->  socket
//
// That order is load-bearing rather than aesthetic. The manager opens its own
// store connection before spawning workers, because SQLite's one-time lazy
// initialization is not thread-safe against several threads calling
// sqlite3_open as their first SQLite call -- measured, and commented at the
// call site in manager.cpp. The socket comes last so nothing can be accepted
// before there is a manager to serve it: a request answered during startup by
// a half-built service is worse than a connection refused.
//
// Teardown reverses it. The listener stops accepting first, so no new work
// arrives while the pool drains.
class Service {
  public:
    Service();
    ~Service();

    bool start(const Config& config, std::string& error);

    // Stops accepting, drains, and joins. Idempotent and safe without a start.
    void stop();

    bool is_running() const;

    // The port actually bound; 0 when not running. Non-zero even when the
    // configuration asked for 0, which is how a test reaches the service.
    std::uint16_t port() const;

  private:
    Service(const Service&);
    Service& operator=(const Service&);

    struct Impl;
    Impl* impl_;
};

// --- signals (L2-CTL-017, L2-CTL-018) -------------------------------------

// Installs handlers for SIGINT and SIGTERM and ignores SIGPIPE process-wide.
//
// L2-CTL-018: SIGPIPE must be ignored here rather than relied upon at every
// call site. C5 passes MSG_NOSIGNAL on every send, which is correct and is not
// a substitute -- the first write that forgets the flag would kill the service,
// and "every future author remembers" is not a mechanism.
//
// L2-CTL-017: the handler assigns to a volatile sig_atomic_t and does nothing
// else. Not even a write to a self-pipe, which would be async-signal-safe but
// is more than the requirement permits. Waking is sigsuspend's job.
bool install_signal_handlers(std::string& error);

// True once SIGINT or SIGTERM has been seen.
bool stop_requested();

// Blocks until a stop signal arrives, then returns.
//
// sigsuspend, not a poll loop. The inherited design woke every 200 ms forever
// to test a flag; a daemon that does that spends its whole life waking up to
// discover nothing has happened. Requires the signals to be blocked first --
// install_signal_handlers does that -- so a signal arriving between the flag
// check and the suspend is not lost.
void wait_for_stop_signal();

// Test seam: clears the flag so a suite can exercise the wait more than once.
// Not conditional on NDEBUG, for the reason the phase hook is not -- the code
// under test must be the code that ships.
void reset_stop_flag_for_test();

}  // namespace filemover

#endif  // FILEMOVER_SERVICE_HPP
