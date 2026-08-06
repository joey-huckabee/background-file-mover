// Scratch: standalone TSan repro for the C4 manager races. Not part of the
// build; see docs/C4-TSAN-OPEN.md step 1.
#include "filemover/manager.hpp"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#include <sstream>
#include <string>

using namespace filemover;

int main(int argc, char** argv) {
    char tmpl[] = "/tmp/fm-repro-XXXXXX";
    const char* root = mkdtemp(tmpl);
    if (root == 0) return 1;
    const std::string base(root);
    const std::string src = base + "/src";
    const std::string dst = base + "/dst";
    ::mkdir(src.c_str(), 0700);
    ::mkdir(dst.c_str(), 0700);

    Config cfg;
    cfg.jobs_workers = (argc > 1) ? atoi(argv[1]) : 4;
    cfg.storage_database_path = base + "/state.db";

    // argv[2] present => "no overlap" mode. Each job is paused the instant it
    // is submitted and resumed only once every submit has finished, so the main
    // thread's SQLite writes never overlap a worker's. If the reports vanish in
    // this mode and not otherwise, cross-connection contention is the cause and
    // nothing else changed to explain it.
    const bool no_overlap = (argc > 2);

    // argv[3] present => "no SQL in the unlocked region" mode. A relative
    // source_dir is rejected by validate_external_path at the top of
    // MoveEngine::execute, BEFORE the first store_.load -- so the worker's
    // unlocked window contains no SQLite at all. The manager still touches the
    // store afterwards, but under its own mutex.
    //
    // This isolates the one thing the clean tsan_pattern.cpp lacks: SQLite
    // running in the gap between lock.unlock() and lock.lock().
    const bool no_sql_unlocked = (argc > 3);

    JobManager manager(cfg.storage_database_path, cfg);
    std::string error;
    if (!manager.start(error)) {
        fprintf(stderr, "start failed: %s\n", error.c_str());
        return 1;
    }

    const int njobs = (getenv("NJOBS") != 0) ? atoi(getenv("NJOBS")) : 12;
    for (int i = 0; i < njobs; ++i) {
        std::ostringstream name;
        name << "f" << i;
        const int fd =
            ::open((src + "/" + name.str()).c_str(), O_WRONLY | O_CREAT, 0600);
        if (fd >= 0) {
            ssize_t n = ::write(fd, "payload", 7);
            (void)n;
            ::close(fd);
        }
        MoveRequest r;
        r.source_dir = no_sql_unlocked ? std::string("relative/src") : src;
        r.source_name = name.str();
        r.dest_dir = dst;
        r.dest_name = name.str() + ".done";
        manager.submit(name.str(), r, error);
        if (no_overlap) {
            manager.pause(name.str(), error);
        }
    }

    if (no_overlap) {
        for (int i = 0; i < njobs; ++i) {
            std::ostringstream name;
            name << "f" << i;
            manager.resume(name.str(), error);
        }
    }

    manager.wait_idle(30000);
    manager.shutdown();
    printf("repro done\n");
    return 0;
}
