// C6: the daemon -- signals, startup order, and teardown.
// Traces: L2-CTL-017..020, L2-CTL-008

#include "filemover/service.hpp"

#include "filemover/singleton.hpp"

#include <errno.h>
#include <signal.h>
#include <string.h>

#include <stddef.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <atomic>
#include <csignal>
#include <cstdlib>
#include <ctime>
#include <thread>
#include <cstring>
#include <string>

namespace filemover {
namespace {

// L2-CTL-017. The only thing a handler may touch, and the only thing this one
// does touch. sig_atomic_t because nothing wider is guaranteed to be written
// without tearing; volatile because the main thread reads it in a loop the
// compiler would otherwise be entitled to hoist.
volatile std::sig_atomic_t g_stop_requested = 0;

extern "C" void on_stop_signal(int /*signal*/) { g_stop_requested = 1; }

}  // namespace

bool stop_requested() { return g_stop_requested != 0; }

void reset_stop_flag_for_test() { g_stop_requested = 0; }

bool install_signal_handlers(std::string& error) {
    // SIGPIPE first, process-wide (L2-CTL-018). Every send in C5 already passes
    // MSG_NOSIGNAL; this is what makes the guarantee hold for code that has not
    // been written yet.
    struct sigaction ignore;
    std::memset(&ignore, 0, sizeof(ignore));
    ignore.sa_handler = SIG_IGN;
    if (::sigaction(SIGPIPE, &ignore, 0) != 0) {
        error = std::string("service: cannot ignore SIGPIPE: ") +
                std::strerror(errno);
        return false;
    }

    struct sigaction stop;
    std::memset(&stop, 0, sizeof(stop));
    stop.sa_handler = on_stop_signal;
    // Both stop signals blocked while the handler runs, so the second cannot
    // re-enter it. No SA_RESTART: a blocking read interrupted by a shutdown
    // signal should return EINTR and let the loop notice, not silently resume.
    (void)::sigemptyset(&stop.sa_mask);
    (void)::sigaddset(&stop.sa_mask, SIGINT);
    (void)::sigaddset(&stop.sa_mask, SIGTERM);

    if (::sigaction(SIGINT, &stop, 0) != 0 ||
        ::sigaction(SIGTERM, &stop, 0) != 0) {
        error = std::string("service: cannot install stop handlers: ") +
                std::strerror(errno);
        return false;
    }

    // Blocked from here on. wait_for_stop_signal unblocks them atomically
    // inside sigsuspend, which is what closes the window between testing the
    // flag and going to sleep -- a signal delivered in that window would
    // otherwise be consumed by the handler and then waited for forever.
    sigset_t block;
    (void)::sigemptyset(&block);
    (void)::sigaddset(&block, SIGINT);
    (void)::sigaddset(&block, SIGTERM);
    if (::pthread_sigmask(SIG_BLOCK, &block, 0) != 0) {
        error = "service: cannot block stop signals";
        return false;
    }

    error.clear();
    return true;
}

void wait_for_stop_signal() {
    sigset_t unblocked;
    (void)::sigemptyset(&unblocked);
    while (g_stop_requested == 0) {
        // Atomically installs the empty mask and sleeps. Returns on any
        // delivered signal, at which point the flag is re-tested.
        (void)::sigsuspend(&unblocked);
    }
}

// --- service-manager readiness --------------------------------------------

bool notify_service_manager(const std::string& state, std::string& error) {
    if (state.empty()) {
        error = "service: notification state is empty";
        return false;
    }
    error.clear();

    const char* socket_path = ::getenv("NOTIFY_SOCKET");
    if (socket_path == 0 || socket_path[0] == '\0') {
        // Not running under a service manager. L3-CPP-054: this is success.
        return true;
    }

    const int fd = ::socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        return true;  // never fatal
    }

    struct sockaddr_un addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;

    const std::size_t len = std::strlen(socket_path);
    if (len == 0 || len >= sizeof(addr.sun_path)) {
        (void)::close(fd);
        return true;
    }
    std::memcpy(addr.sun_path, socket_path, len);

    // A leading '@' means the abstract namespace, which on the wire is a
    // leading NUL. Copying the '@' verbatim addresses a filesystem path that
    // does not exist, so the send fails silently and readiness is never
    // reported -- systemd then kills the unit at its start timeout, which
    // presents as "the service is slow" rather than "the notification is wrong".
    socklen_t addr_len =
        static_cast<socklen_t>(offsetof(struct sockaddr_un, sun_path) + len);
    if (addr.sun_path[0] == '@') {
        addr.sun_path[0] = '\0';
    } else {
        addr_len = static_cast<socklen_t>(
            offsetof(struct sockaddr_un, sun_path) + len + 1);
    }

    (void)::sendto(fd, state.data(), state.size(), MSG_NOSIGNAL,
                   reinterpret_cast<struct sockaddr*>(&addr), addr_len);
    (void)::close(fd);
    return true;
}

unsigned watchdog_interval_ms() {
    const char* usec = ::getenv("WATCHDOG_USEC");
    if (usec == 0 || usec[0] == '\0') {
        return 0;
    }
    // WATCHDOG_PID, when present, names the process the interval was meant
    // for. Pinging on behalf of a parent would report the wrong process
    // healthy, which is worse than not pinging at all.
    const char* pid = ::getenv("WATCHDOG_PID");
    if (pid != 0 && pid[0] != '\0') {
        errno = 0;
        char* end = 0;
        const long owner = std::strtol(pid, &end, 10);
        if (errno != 0 || end == pid || *end != '\0' ||
            owner != static_cast<long>(::getpid())) {
            return 0;
        }
    }

    errno = 0;
    char* end = 0;
    const long value = std::strtol(usec, &end, 10);
    if (errno != 0 || end == usec || *end != '\0' || value <= 0) {
        return 0;
    }
    // Ping at half the interval, which is what systemd's own documentation
    // recommends: a ping exactly at the deadline races the deadline.
    const long half_ms = (value / 1000) / 2;
    if (half_ms <= 0) {
        return 1;
    }
    return static_cast<unsigned>(half_ms);
}

bool check_config(const Config& config, std::string& error) {
    if (config.storage_database_path.empty()) {
        error = "storage.database_path is required";
        return false;
    }
    // L2-JOB-008, checked against the DIRECTORY rather than the database file.
    //
    // The file does not exist yet on a first start -- L2-JOB-011 treats an
    // absent store as first boot -- and statfs on a path that does not exist
    // fails. Checking the file directly makes --check reject every fresh
    // install, which is the one case it most needs to accept. The filesystem is
    // a property of the directory anyway; the file will be created inside it.
    const std::string& path = config.storage_database_path;
    const std::string::size_type slash = path.rfind('/');
    const std::string directory =
        (slash == std::string::npos) ? std::string(".")
        : (slash == 0)               ? std::string("/")
                                     : path.substr(0, slash);

    std::string reason;
    if (!storage_path_is_local(directory, reason)) {
        error = reason;
        return false;
    }
    if (config.jobs_workers == 0) {
        error = "jobs.workers must be at least 1";
        return false;
    }
    error.clear();
    return true;
}

// --- startup and teardown (L2-CTL-020) ------------------------------------

struct Service::Impl {  // NOLINT
    // L2-CTL-008, declared FIRST on purpose. Members are destroyed in reverse
    // declaration order, so first-declared is last-destroyed -- which makes the
    // destructor release the lock after the server and the manager are gone,
    // matching the order stop() takes explicitly. stop() is the path that
    // normally runs; this is the backstop for the one that does not.
    SingletonLock lock;

    JobManager* manager;
    ConnectionServer server;
    HttpServiceOptions http;
    bool running;

    // L2-CTL-012. A thread that sleeps and pings, holding no mutex -- the
    // shape docs/C5-PLAN.md prescribes for a periodic tick, and the reason a
    // timed condition wait is not used here (it breaks ThreadSanitizer, and
    // make no-timed-condwait forbids it).
    std::thread watchdog;
    std::atomic<bool> watchdog_stop;

    Impl() : manager(0), running(false), watchdog_stop(false) {}

    // A member, because Impl is a private nested type and nothing outside the
    // class can name it -- the same reason JobManager::Impl owns run_worker.
    void run_watchdog(unsigned interval_ms);
};

namespace {

// The server hands each accepted descriptor here. A single pointer rather than
// per-connection state because ConnectionServer takes a plain function and a
// void*, and the service outlives every connection it serves.
struct Dispatch {
    JobManager* manager;
    const HttpServiceOptions* options;
};

Dispatch g_dispatch = {0, 0};

// L2-CTL-012. Sleeps in short slices rather than one long one, so shutdown
// does not wait out a whole watchdog interval before this thread notices --
// systemd's default is often 30 seconds, and joining on that would make every
// stop look hung.
//
// nanosleep and an atomic flag, holding no mutex. Not a timed condition wait:
// that breaks ThreadSanitizer for whatever mutex it is given, and
// make no-timed-condwait forbids it.
void serve(int fd, void* /*user*/) {
    if (g_dispatch.manager != 0 && g_dispatch.options != 0) {
        serve_connection(fd, *g_dispatch.options, *g_dispatch.manager);
    }
}

}  // namespace

// Defined here rather than in the anonymous namespace above: a member function
// may only be defined in the namespace enclosing its class, and an anonymous
// namespace is a different one.
void Service::Impl::run_watchdog(unsigned interval_ms) {
    const unsigned kSliceMs = 100;
    unsigned waited = 0;
    while (!watchdog_stop) {
        struct timespec slice;
        slice.tv_sec = 0;
        slice.tv_nsec = static_cast<long>(kSliceMs) * 1000L * 1000L;
        (void)::nanosleep(&slice, 0);
        waited += kSliceMs;
        if (waited >= interval_ms) {
            waited = 0;
            std::string ignored;
            (void)notify_service_manager("WATCHDOG=1", ignored);
        }
    }
}

Service::Service() : impl_(new Impl()) {}

Service::~Service() {
    stop();
    delete impl_;
}

bool Service::is_running() const { return impl_->running; }

std::uint16_t Service::port() const { return impl_->server.port(); }

bool Service::start(const Config& config, std::string& error) {
    if (impl_->running) {
        error = "service: already running";
        return false;
    }
    if (!check_config(config, error)) {
        return false;
    }

    // 1. The singleton lock, FIRST -- before the store is opened, not after
    //    (L2-CTL-008). A second instance that reached the store first would run
    //    crash recovery over rows the running instance owns, and would have
    //    done that damage by the time it discovered it was not alone.
    if (!impl_->lock.acquire(config.storage_database_path, error)) {
        return false;
    }

    // 2. The manager, which opens the store before spawning workers. Nothing
    //    accepts connections yet, so a failure here costs only this call.
    impl_->manager = new JobManager(config.storage_database_path, config);
    if (!impl_->manager->start(error)) {
        delete impl_->manager;
        impl_->manager = 0;
        impl_->lock.release();
        return false;
    }

    impl_->http.max_body_bytes = config.http_max_body_bytes;
    g_dispatch.manager = impl_->manager;
    g_dispatch.options = &impl_->http;

    // 3. The socket, LAST. A request answered during startup by a half-built
    //    service is worse than a connection refused.
    ServerOptions server_options;
    server_options.handlers = config.jobs_workers;
    if (!impl_->server.start(config.http_bind, config.http_port,
                             server_options, serve, 0, error)) {
        impl_->manager->shutdown();
        delete impl_->manager;
        impl_->manager = 0;
        g_dispatch.manager = 0;
        g_dispatch.options = 0;
        impl_->lock.release();
        return false;
    }

    impl_->running = true;

    // 4. Readiness, LAST -- after the socket is accepting. Telling systemd
    //    READY=1 before the port is open makes every dependent unit start
    //    against a service that cannot yet answer, which is the whole problem
    //    Type=notify exists to solve.
    std::string ignored;
    (void)notify_service_manager("READY=1", ignored);

    const unsigned interval = watchdog_interval_ms();
    if (interval > 0) {
        impl_->watchdog_stop = false;
        impl_->watchdog =
            std::thread(&Service::Impl::run_watchdog, impl_, interval);
    }

    error.clear();
    return true;
}

void Service::stop() {
    if (!impl_->running) {
        return;
    }
    impl_->running = false;

    // STOPPING=1 first, so systemd knows this is a deliberate shutdown before
    // the port closes. Otherwise a slow drain looks like a service that died.
    std::string ignored;
    (void)notify_service_manager("STOPPING=1", ignored);

    impl_->watchdog_stop = true;
    if (impl_->watchdog.joinable()) {
        impl_->watchdog.join();
    }

    // Reverse order. The listener stops accepting first, so no new work
    // arrives while the pool drains -- stopping the manager first would leave
    // connections being accepted and handed to a manager that is shutting down.
    impl_->server.shutdown();
    g_dispatch.manager = 0;
    g_dispatch.options = 0;

    if (impl_->manager != 0) {
        impl_->manager->shutdown();
        delete impl_->manager;
        impl_->manager = 0;
    }

    // The lock LAST, completing the reverse order (L2-CTL-020). Releasing it
    // earlier would let a second instance open the store while this one is
    // still draining -- which is the exact overlap the lock exists to prevent,
    // arrived at through the shutdown path instead of the startup one.
    impl_->lock.release();
}

}  // namespace filemover
