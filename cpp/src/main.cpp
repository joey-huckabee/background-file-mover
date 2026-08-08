// C6: the daemon entry point.
//
// Deliberately thin. Everything worth testing lives in service.cpp, because a
// component reachable only through main is a component tested by starting a
// process and hoping.
//
// Output stream contract (L2-CLI-006): this is the SERVICE, so its event stream
// goes to the standard streams split by severity -- informational to stdout,
// warnings and errors to stderr -- and it manages no log files. The CLI has the
// opposite contract for stdout; see docs/LOGGING.md.

#include <cstdio>
#include <cstring>
#include <string>

#include "filemover/config.hpp"
#include "filemover/service.hpp"

namespace {

int usage(const char* argv0) {
    (void)std::fprintf(stderr,
                       "usage: %s --config <path> [--check]\n"
                       "  --check   validate the configuration and exit; "
                       "creates nothing\n",
                       argv0);
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    // Line-buffered stdout, always -- not only when it happens to be a
    // terminal.
    //
    // The C library block-buffers stdout when it is not a tty, which is every
    // real deployment: journald, a container log, a redirect. Without this the
    // service appears completely silent until it exits or fills four kilobytes,
    // so "listening on ..." arrives at shutdown and an operator watching the
    // log during startup sees nothing at all.
    //
    // Found by a smoke test that waited for that line and hung. It is exactly
    // the failure L2-CLI-006 is about: writing the event stream to the standard
    // streams is only useful if the environment can read it as it happens.
    (void)std::setvbuf(stdout, 0, _IOLBF, 0);
    (void)std::setvbuf(stderr, 0, _IONBF, 0);

    std::string config_path;
    bool check_only = false;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--check") {
            check_only = true;
        } else if (arg == "--config" && i + 1 < argc) {
            config_path = argv[++i];
        } else {
            return usage(argv[0]);
        }
    }
    if (config_path.empty()) {
        return usage(argv[0]);
    }

    filemover::Config config;
    std::string error;
    if (!filemover::load_config_file(config_path, config, error)) {
        // Every issue at once, newline-separated (L2-CFG-008): an operator
        // editing a config by hand should learn everything wrong with it in one
        // run rather than one fault per restart.
        (void)std::fprintf(stderr, "%s\n", error.c_str());
        return 1;
    }

    // L2-CTL-019. Exits before anything is created, so systemd ExecStartPre can
    // fail the unit rather than the service discovering the problem after
    // opening a socket and a database.
    if (!filemover::check_config(config, error)) {
        (void)std::fprintf(stderr, "%s\n", error.c_str());
        return 1;
    }
    if (check_only) {
        (void)std::fprintf(stdout, "configuration is valid\n");
        return 0;
    }

    // Before any thread exists, so the mask is inherited by every thread the
    // manager and the server go on to create and only this one receives the
    // stop signals.
    if (!filemover::install_signal_handlers(error)) {
        (void)std::fprintf(stderr, "%s\n", error.c_str());
        return 1;
    }

    filemover::Service service;
    if (!service.start(config, error)) {
        (void)std::fprintf(stderr, "%s\n", error.c_str());
        return 1;
    }
    (void)std::fprintf(stdout, "listening on %s:%u\n", config.http_bind.c_str(),
                       static_cast<unsigned>(service.port()));

    // sigsuspend, not a poll loop. The inherited design woke five times a
    // second forever to test a flag.
    filemover::wait_for_stop_signal();

    (void)std::fprintf(stdout, "stopping\n");
    service.stop();  // reverse order: listener, then pool, then store
    return 0;
}
