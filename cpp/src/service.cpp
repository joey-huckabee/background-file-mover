// C6: the daemon -- signals, startup order, and teardown.
// Traces: L2-CTL-017..020, L2-CTL-008

#include "filemover/service.hpp"

#include <errno.h>
#include <signal.h>
#include <string.h>

#include <csignal>
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

struct Service::Impl {
    JobManager* manager;
    ConnectionServer server;
    HttpServiceOptions http;
    bool running;

    Impl() : manager(0), running(false) {}
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

void serve(int fd, void* /*user*/) {
    if (g_dispatch.manager != 0 && g_dispatch.options != 0) {
        serve_connection(fd, *g_dispatch.options, *g_dispatch.manager);
    }
}

}  // namespace

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

    // 1. The manager, which opens the store before spawning workers. Nothing
    //    accepts connections yet, so a failure here costs only this call.
    impl_->manager = new JobManager(config.storage_database_path, config);
    if (!impl_->manager->start(error)) {
        delete impl_->manager;
        impl_->manager = 0;
        return false;
    }

    impl_->http.max_body_bytes = config.http_max_body_bytes;
    g_dispatch.manager = impl_->manager;
    g_dispatch.options = &impl_->http;

    // 2. The socket, LAST. A request answered during startup by a half-built
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
        return false;
    }

    impl_->running = true;
    error.clear();
    return true;
}

void Service::stop() {
    if (!impl_->running) {
        return;
    }
    impl_->running = false;

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
}

}  // namespace filemover
