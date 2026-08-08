// C6: the singleton lock (L2-CTL-008).
//
// The rationale for flock-over-pidfile and flock-over-fcntl is in the header;
// it is design, not implementation detail, and belongs where a caller reads it.

#include "filemover/singleton.hpp"

#include "filemover/fsops.hpp"

#include <errno.h>
#include <string.h>
#include <sys/file.h>
#include <unistd.h>

#include <cstdio>
#include <cstring>
#include <string>

namespace filemover {

bool lock_path_for_database(const std::string& database_path,
                            std::string& directory,
                            std::string& name,
                            std::string& error) {
    if (database_path.empty()) {
        error = "singleton: database path is empty";
        return false;
    }

    const std::string::size_type slash = database_path.find_last_of('/');
    if (slash == std::string::npos) {
        // A bare file name is relative to the working directory. Accepted
        // rather than rejected because tests use it; production paths come
        // from the config, which L3-CPP-039 requires to be absolute.
        directory = ".";
        name = database_path;
    } else {
        // "/db" -> directory "/", not "". An empty directory string would be
        // passed to open_root, which would fail with ENOENT and report the
        // wrong problem.
        directory = (slash == 0) ? "/" : database_path.substr(0, slash);
        name = database_path.substr(slash + 1);
    }

    if (name.empty()) {
        error = "singleton: database path '" + database_path +
                "' names a directory, not a file";
        return false;
    }

    name += ".lock";
    return true;
}

SingletonLock::SingletonLock() : fd_(-1) {}

SingletonLock::~SingletonLock() { release(); }

bool SingletonLock::is_held() const { return fd_ >= 0; }

bool SingletonLock::acquire(const std::string& database_path,
                            std::string& error) {
    if (fd_ >= 0) {
        error = "singleton: lock is already held by this instance";
        return false;
    }

    std::string directory;
    std::string name;
    if (!lock_path_for_database(database_path, directory, name, error)) {
        return false;
    }
    const std::string display = directory + "/" + name;

    // Through the fd-relative layer (L2-SEC-001), which is also what keeps
    // <fcntl.h> out of this translation unit -- see scripts/assert-fd-relative.sh.
    DirHandle dir;
    if (!dir.open_root(directory, error)) {
        error = "singleton: " + error;
        return false;
    }

    int fd = -1;
    if (!open_lock_file(dir, name, fd, error)) {
        error = "singleton: " + error;
        return false;
    }

    if (::flock(fd, LOCK_EX | LOCK_NB) != 0) {
        const int err = errno;
        (void)::close(fd);
        if (err == EWOULDBLOCK || err == EAGAIN) {
            // The message an operator reads at 3am. It says what is wrong and
            // where to look, and deliberately does NOT name a pid: the pid in
            // the file is diagnostic and may be stale, and printing it as if it
            // were authoritative invites killing an unrelated process.
            error = "another instance is already running (lock held on " +
                    display + ")";
        } else {
            error = "singleton: cannot lock '" + display +
                    "': " + std::strerror(err);
        }
        return false;
    }

    fd_ = fd;

    // Diagnostics only, and best-effort. The lock is the truth; this is so
    // `cat` on the lock file answers "which process" during an incident. A
    // failure here is not a failure to acquire -- the lock is already held, and
    // refusing to start because a comment could not be written would be absurd.
    if (::ftruncate(fd_, 0) == 0) {
        char buffer[32];
        const int n = std::snprintf(buffer, sizeof(buffer), "%ld\n",
                                    static_cast<long>(::getpid()));
        if (n > 0 && static_cast<std::size_t>(n) < sizeof(buffer)) {
            (void)!::write(fd_, buffer, static_cast<std::size_t>(n));
        }
    }

    error.clear();
    return true;
}

void SingletonLock::release() {
    if (fd_ < 0) {
        return;
    }
    // Closing releases the flock. The file is deliberately NOT unlinked:
    // between another process's open and its flock there is a window where
    // unlinking here would delete the object it is about to lock, leaving two
    // processes holding exclusive locks on two different inodes with the same
    // name. A leftover lock file is not a stale lock -- it holds nothing, and
    // the next start locks it again.
    (void)::close(fd_);
    fd_ = -1;
}

}  // namespace filemover
