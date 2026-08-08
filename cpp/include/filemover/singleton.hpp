#ifndef FILEMOVER_SINGLETON_HPP
#define FILEMOVER_SINGLETON_HPP

// C6: the singleton lock.
//
// Traces: L2-CTL-008
//
// Two daemons on one state database is not a degraded mode, it is corruption.
// Both would run crash recovery over the same rows, both would claim the same
// QUEUED jobs, and both would move the same file -- with the second discovering
// the source gone and recording a failure for work that actually succeeded.
// SQLite's own locking serialises the *writes*; it has nothing to say about two
// processes that each believe they own the queue.
//
// WHY A LOCK AND NOT A PIDFILE. A pidfile has to answer "is pid 4212 still
// alive, and is it still us?" -- and it cannot, because pids are reused. The
// usual repairs (check /proc, compare start time, unlink if stale) are all
// racy, and every one of them can be defeated by a reboot. An advisory lock
// asks nothing: the kernel releases it when the holding process dies, however
// it dies, including SIGKILL and power loss. There is no stale state to reason
// about, so there is no recovery path to get wrong.
//
// WHY flock AND NOT fcntl(F_SETLK). POSIX record locks are owned by the
// (process, file) pair, so a second lock taken by the SAME process silently
// succeeds -- it just replaces the first. That is precisely the case this class
// exists to catch, and it would be invisible. flock is owned by the open file
// description, so a second open in the same process is a different owner and is
// correctly refused. flock's known weakness is NFS, and it does not apply here:
// L2-JOB-008 requires the state database on local storage and check_config
// enforces it with statfs before this is ever reached.

#include <string>

namespace filemover {

// Held for the lifetime of the process. Releasing is a side effect of the
// descriptor closing, which is why the destructor is the whole recovery story.
class SingletonLock {
  public:
    SingletonLock();
    ~SingletonLock();

    // Fails with a human-readable error when another instance holds the lock.
    // The message names the lock file, because the operator's next question is
    // always "which one, and where".
    bool acquire(const std::string& database_path, std::string& error);

    // Idempotent, and safe without an acquire.
    void release();

    bool is_held() const;

  private:
    SingletonLock(const SingletonLock&);
    SingletonLock& operator=(const SingletonLock&);

    int fd_;
};

// The lock file sits beside the state database and is named after it, so the
// lock is keyed to the RESOURCE rather than to the configuration file. Two
// daemons started from two different configs that name the same database are
// the case that matters, and a lock named after the config would let both run.
//
// Exposed for test rather than kept private: the derivation is where the
// interesting mistakes are (a trailing slash, no slash at all, a path that is
// only a slash) and each deserves an assertion.
bool lock_path_for_database(const std::string& database_path,
                            std::string& directory,
                            std::string& name,
                            std::string& error);

}  // namespace filemover

#endif  // FILEMOVER_SINGLETON_HPP
