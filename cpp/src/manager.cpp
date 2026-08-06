// C4: the job manager and worker pool.
// Traces: L2-MGR-001..003, L2-LIF-002/004/005, L2-RTY-001/002/003/005/006

#include "filemover/manager.hpp"

#include <time.h>

#include <chrono>
#include <condition_variable>
#include <deque>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <thread>
#include <vector>

namespace filemover {
namespace {

// The default clock. Monotonic rather than wall-clock: every use is a
// comparison or a delta, so an operator changing the system time must not make
// a retry wait an hour or fire an hour early.
std::int64_t monotonic_now(void* /*user*/) {
    struct timespec ts;
    if (::clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0;
    }
    return static_cast<std::int64_t>(ts.tv_sec) * 1000 +
           static_cast<std::int64_t>(ts.tv_nsec) / 1000000;
}

// Strips a trailing "-retry-<digits>" so retrying a retry stays flat:
// "job-retry-2" retried again yields "job-retry-3", not
// "job-retry-2-retry-1". Ids are operator-facing, and a name that records the
// shape of the retry chain rather than its length gets unreadable fast.
//
// Only a well-formed suffix is stripped. A job genuinely named "backup-retry-x"
// keeps its name, because the digits are what make the suffix ours.
std::string strip_retry_suffix(const std::string& id) {
    const std::string marker("-retry-");
    const std::string::size_type at = id.rfind(marker);
    if (at == std::string::npos) {
        return id;
    }
    const std::string::size_type first = at + marker.size();
    if (first >= id.size()) {
        return id;
    }
    for (std::string::size_type i = first; i < id.size(); ++i) {
        if (id[i] < '0' || id[i] > '9') {
            return id;
        }
    }
    return id.substr(0, at);
}

// L2-RTY-005: bounded exponential backoff. Doubling from the initial delay,
// clamped to the maximum, so a long-running failure settles at a fixed poll
// rate rather than growing without limit.
std::int64_t backoff_for(unsigned attempts,
                         std::uint32_t initial_ms,
                         std::uint32_t max_ms) {
    std::int64_t delay = initial_ms;
    for (unsigned i = 1; i < attempts && delay < max_ms; ++i) {
        delay *= 2;
    }
    if (delay > static_cast<std::int64_t>(max_ms)) {
        delay = max_ms;
    }
    return delay;
}

}  // namespace

const char* to_string(CommandResult result) {
    switch (result) {
        case CommandResult::Ok:           return "OK";
        case CommandResult::UnknownJob:   return "UNKNOWN_JOB";
        case CommandResult::InvalidState: return "INVALID_STATE";
        case CommandResult::NotRunning:   return "NOT_RUNNING";
        case CommandResult::StoreError:   return "STORE_ERROR";
    }
    return "STORE_ERROR";
}

struct JobManager::Impl {
    std::string store_path;
    Config config;
    MoveStrategy strategy;

    ClockFn clock;
    void* clock_user;
    MoveEngine::PhaseHook hook;
    void* hook_user;

    // One mutex guards everything below it. A single lock rather than several
    // because the states interact -- a job moves between runnable, waiting,
    // paused and active -- and lock ordering between four mutexes is a bug
    // waiting for the first person who takes them in a new order.
    mutable std::mutex mutex;
    std::condition_variable work_ready;   // workers wait here
    // There is deliberately no idle_changed condition variable. wait_idle()
    // polls under the lock instead -- see the note there for why a timed
    // condition wait had to go. A condvar nothing waits on is dead state that
    // reads like a synchronisation point.

    std::deque<std::string> runnable;
    std::map<std::string, MoveRequest> requests;
    std::map<std::string, std::int64_t> waiting;  // job -> earliest run time
    std::set<std::string> paused;
    std::set<std::string> active;

    // Ids claimed by a command that has released the manager mutex to do its
    // durable write and has not published the job yet. Without this a second
    // submit of the same id could slip through the window between the claim
    // and the insert into `requests`.
    std::set<std::string> pending;

    // Guards the manager's OWN store connection, and nothing else.
    //
    // Separate from `mutex` on purpose: a command's durable write can block for
    // busy_timeout -- five seconds -- when a worker holds the database write
    // lock, and holding the manager mutex across that stalls every worker,
    // because `mutex` is what they take to pick up their next job. This mutex
    // makes concurrent commands safe to share one connection (L2-JOB-003)
    // without coupling them to dispatch.
    //
    // LOCK ORDER: `store_mutex` may be held while taking `mutex`. The reverse
    // is never done, so there is no cycle. submit() avoids nesting entirely by
    // releasing one before taking the other; retry() nests, because probing for
    // a free id has to consult both the durable record and the live maps.
    // Workers never take `store_mutex` at all -- each has its own connection.
    mutable std::mutex store_mutex;

    bool running;
    bool stopping;
    std::vector<std::thread> workers;

    // The manager's own connection, for command handling. Workers never touch
    // it; each opens its own (L2-JOB-003).
    JobStore store;

    Impl(const std::string& path, const Config& cfg)
        : store_path(path),
          config(cfg),
          strategy(MoveStrategy::RenameNoReplace),
          clock(monotonic_now),
          clock_user(0),
          hook(0),
          hook_user(0),
          running(false),
          stopping(false) {}

    std::int64_t now() { return clock(clock_user); }

    // Members rather than free functions in an anonymous namespace: Impl is a
    // private nested type, so nothing outside the class can name it.
    void run_worker();
    bool take_runnable(const std::string& job_id);
    void fail_permanently(JobStore& store,
                          const std::string& job_id,
                          const std::string& reason);
    bool handle_failure(JobStore& store,
                        const std::string& job_id,
                        const std::string& failure,
                        std::int64_t now_ms,
                        std::int64_t& due_ms);
};

JobManager::JobManager(const std::string& store_path, const Config& config)
    : impl_(new Impl(store_path, config)) {}

JobManager::~JobManager() {
    shutdown();
    delete impl_;
}

void JobManager::set_clock(ClockFn fn, void* user_data) {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    impl_->clock = (fn != 0) ? fn : monotonic_now;
    impl_->clock_user = user_data;
}

void JobManager::set_strategy(MoveStrategy strategy) {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    impl_->strategy = strategy;
}

void JobManager::set_phase_hook(MoveEngine::PhaseHook hook, void* user_data) {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    impl_->hook = hook;
    impl_->hook_user = user_data;
}

bool JobManager::is_running() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->running;
}

std::size_t JobManager::runnable_count() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->runnable.size();
}

std::size_t JobManager::active_count() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->active.size();
}

bool JobManager::Impl::take_runnable(const std::string& job_id) {
    for (std::deque<std::string>::iterator it = runnable.begin();
         it != runnable.end(); ++it) {
        if (*it == job_id) {
            runnable.erase(it);
            return true;
        }
    }
    return false;
}

// L2-RTY-001/002. The decision composes the classifications C2 and C3 already
// make rather than re-deriving them from the message text.
//
// Only a pre-commit abort is ever retried. Past the commit point the move is
// real and re-running it would act on a source that no longer exists;
// FailedExternal is excluded because L2-SEC-011 says so outright.
//
// Caller must NOT hold the lock. Every store call below can block on
// busy_timeout, and holding the manager mutex across one stalls the whole pool.
// The only shared state this touches is `config`, which is copied at
// construction and never mutated, and the clock, which is snapshotted by the
// caller for the same reason.
//
// Returns true when the job should run again later, with `due_ms` set to when.
// The caller records that under the lock -- `waiting` is dispatch state and
// belongs to the mutex, even though the durable write does not.
bool JobManager::Impl::handle_failure(JobStore& store,
                                      const std::string& job_id,
                                      const std::string& failure,
                                      std::int64_t now_ms,
                                      std::int64_t& due_ms) {
    JobStore::RetryState state;
    bool found = false;
    std::string load_error;
    if (!store.load_retry_state(job_id, state, found, load_error) || !found) {
        return false;
    }

    const unsigned attempts = static_cast<unsigned>(state.attempts) + 1;
    if (attempts < config.retry_max_attempts) {
        const std::int64_t due =
            now_ms + backoff_for(attempts, config.retry_backoff_initial_ms,
                                 config.retry_backoff_max_ms);
        std::string record_error;
        if (store.record_attempt(job_id, due, failure, record_error)) {
            // The durable state is left exactly where the engine stopped --
            // QUEUED if it never got past phase 2, RENAMING if it did. No
            // state change is needed to make the job runnable again, because
            // execute() re-enters a RENAMING job by skipping phase 2 and
            // re-driving the rename.
            //
            // No new "retrying" state either: the machine has no such value,
            // and inventing one would put something in the durable record that
            // L1-SYS-021 does not define. The difference between "queued" and
            // "queued, waiting out a backoff" lives in next_retry_ms, which is
            // exactly what that column is for.
            due_ms = due;
            return true;
        }
        return false;
    }

    // L2-RTY-005: the attempt ceiling. Unbounded retry against a permanent
    // failure fills the queue with work that can never succeed.
    std::ostringstream os;
    os << "gave up after " << attempts << " attempts: " << failure;
    fail_permanently(store, job_id, os.str());
    return false;
}

// Ends a job with no further retry: records the reason durably and settles the
// state at FAILED. Reached both from the attempt ceiling and from an outright
// denial, which want identical handling once the verdict is in.
//
// Caller must NOT hold the lock, for the same reason as handle_failure.
void JobManager::Impl::fail_permanently(JobStore& store,
                                        const std::string& job_id,
                                        const std::string& reason) {
    std::string ignored;
    // Zero, not a due time: this job is not coming back, and leaving a stale
    // next_retry_ms behind would make it look due to anything scanning for
    // work later.
    store.record_attempt(job_id, 0, reason, ignored);

    Job job(std::string(), std::string(), std::string(), 0);
    bool have = false;
    if (!store.load(job_id, job, have, ignored) || !have) {
        return;
    }
    // The engine marks a job FAILED itself on a commit-rename failure, so it
    // may already be there. Re-issuing the transition would be refused by the
    // store, which is correct of it -- C3's crash suite found exactly this
    // class of bug twice.
    if (job.state == JobState::Failed) {
        return;
    }
    store.update_state(job_id, JobState::Failed, job.updated_at_ms + 1, reason,
                       ignored);
}

void JobManager::Impl::run_worker() {
    JobManager::Impl* impl = this;
    // L2-JOB-003: this thread's own connection. Opened here rather than handed
    // in, so there is no way to accidentally share one.
    JobStore store;
    StoreOpenResult opened = StoreOpenResult::OpenedExisting;
    std::string open_error;
    if (!store.open(impl->store_path, opened, open_error)) {
        // A worker that cannot open the store contributes nothing, but it must
        // not take the pool down with it: the others still make progress, and
        // start() has already reported the store is openable.
        return;
    }
    MoveEngine engine(store);

    // One lock object for the whole loop, released around the move and taken
    // again after it, rather than two scoped locks per iteration. Two separate
    // unique_locks occupy the same stack slot on alternate halves of the loop,
    // which is correct C++ but leaves ThreadSanitizer tracking what looks like
    // one lock being acquired twice without an intervening release.
    std::unique_lock<std::mutex> lock(impl->mutex);

    for (;;) {
        std::string job_id;
        MoveRequest request;
        MoveStrategy strategy = MoveStrategy::RenameNoReplace;

        while (impl->runnable.empty() && !impl->stopping) {
            impl->work_ready.wait(lock);
        }
        if (impl->runnable.empty() && impl->stopping) {
            return;
        }
        job_id = impl->runnable.front();
        impl->runnable.pop_front();
        request = impl->requests[job_id];
        strategy = impl->strategy;
        impl->active.insert(job_id);
        engine.set_phase_hook(impl->hook, impl->hook_user);

        // Snapshotted while the lock is held. The clock is installed by
        // set_clock() before start(), so this is stable, but reading it under
        // the lock keeps that a fact rather than an assumption.
        const std::int64_t now_ms = impl->now();

        std::string error;
        MoveOutcome outcome = MoveOutcome::Rejected;
        bool reschedule = false;
        std::int64_t due_ms = 0;
        {
            // The move runs unlocked -- it is the slow part, and holding the
            // manager's lock across it would serialize the whole pool onto one
            // job at a time, which is the opposite of having a pool.
            //
            // The failure recording that follows it runs unlocked for a
            // sharper reason: those store calls can block on busy_timeout for
            // five seconds when another connection holds the write lock, and
            // this mutex is the one every other worker needs to pick up its
            // next job. Recording a failure must not stall the pool.
            lock.unlock();
            outcome = engine.execute(job_id, request, strategy, error);

            if (outcome == MoveOutcome::AbortedBeforeCommit) {
                // The attempt failed with the source untouched. Whatever went
                // wrong may not still be wrong in a minute, so this is the
                // retryable class (L2-RTY-001).
                reschedule = impl->handle_failure(store, job_id, error, now_ms,
                                                  due_ms);
            } else if (outcome == MoveOutcome::Rejected) {
                // L2-RTY-002: a denial is permanent, so it is failed outright
                // rather than rescheduled. Every Rejected site in the engine is
                // a refusal of the request itself -- an unusable path, a
                // missing source, a non-regular file, no durable record -- and
                // none of those become true later. Retrying them would burn the
                // attempt ceiling to arrive at the same answer.
                //
                // Handled explicitly and not by omission: falling through left
                // the job QUEUED with no worker owning it and no retry
                // scheduled, so it sat in the durable record forever looking
                // like pending work.
                impl->fail_permanently(store, job_id, error);
            }

            lock.lock();
        }

        // Back under the lock, and only in-memory dispatch state is touched
        // here -- everything durable was written above, unlocked.
        impl->active.erase(job_id);
        if (reschedule) {
            impl->waiting[job_id] = due_ms;
        }
    }
}

bool JobManager::start(std::string& error) {
    unsigned count = 0;
    {
        const std::unique_lock<std::mutex> lock(impl_->mutex);
        if (impl_->running) {
            return true;
        }

        StoreOpenResult opened = StoreOpenResult::OpenedExisting;
        if (!impl_->store.open(impl_->store_path, opened, error)) {
            return false;
        }

        impl_->stopping = false;
        impl_->running = true;
        count = impl_->config.jobs_workers > 0 ? impl_->config.jobs_workers : 1;
    }

    // Threads are spawned with the lock RELEASED. Holding it across
    // std::thread construction means every worker's first act -- taking that
    // same lock at the top of its loop -- blocks until the whole pool has been
    // created, so startup serializes on the one thread doing the creating.
    //
    // Built into a local vector and swapped in under the lock, rather than
    // push_back'ing into impl_->workers directly, because that vector is
    // shared state: shutdown() swaps it out to join, and a reallocating
    // push_back racing that swap is a use-after-free.
    std::vector<std::thread> spawned;
    spawned.reserve(count);
    for (unsigned i = 0; i < count; ++i) {
        spawned.push_back(std::thread(&JobManager::Impl::run_worker, impl_));
    }

    const std::unique_lock<std::mutex> lock(impl_->mutex);
    for (std::size_t i = 0; i < spawned.size(); ++i) {
        impl_->workers.push_back(std::move(spawned[i]));
    }
    return true;
}

void JobManager::shutdown() {
    std::vector<std::thread> to_join;
    {
        const std::unique_lock<std::mutex> lock(impl_->mutex);
        if (!impl_->running) {
            return;
        }
        // L2-MGR-003: intake stops first, so nothing new is accepted while the
        // pool drains. Workers finish the job in hand -- a move past its commit
        // point must not be abandoned half-recorded.
        impl_->stopping = true;
        impl_->running = false;
        impl_->work_ready.notify_all();
        to_join.swap(impl_->workers);
    }

    for (std::size_t i = 0; i < to_join.size(); ++i) {
        if (to_join[i].joinable()) {
            to_join[i].join();
        }
    }

    const std::lock_guard<std::mutex> guard(impl_->mutex);
    impl_->store.close();
}

CommandResult JobManager::submit(const std::string& job_id,
                                 const MoveRequest& request,
                                 std::string& error) {
    std::int64_t now_ms = 0;
    {
        const std::unique_lock<std::mutex> lock(impl_->mutex);
        if (!impl_->running) {
            error = "manager: not running";
            return CommandResult::NotRunning;
        }
        // Claim the id before releasing the mutex. Two concurrent submits of
        // the same id would otherwise both pass this point and both attempt the
        // durable write; the store would refuse the second, but only after the
        // first had already been published.
        if (impl_->requests.find(job_id) != impl_->requests.end() ||
            !impl_->pending.insert(job_id).second) {
            error = "manager: job '" + job_id + "' already exists";
            return CommandResult::InvalidState;
        }
        now_ms = impl_->now();
    }

    // Durable first (L2-JOB-013), and deliberately OUTSIDE the manager mutex.
    // record_intent can block on busy_timeout for five seconds when a worker
    // holds the database write lock, and this mutex is what every worker takes
    // to pick up its next job -- so holding it here stalls the entire pool on
    // one submit. store_mutex keeps concurrent commands safe on the shared
    // connection without coupling them to dispatch.
    const Job job(job_id, request.source_dir + "/" + request.source_name,
            request.dest_dir + "/" + request.dest_name, now_ms);
    bool recorded = false;
    {
        const std::lock_guard<std::mutex> store_guard(impl_->store_mutex);
        recorded = impl_->store.record_intent(job, error);
    }

    const std::unique_lock<std::mutex> lock(impl_->mutex);
    impl_->pending.erase(job_id);
    if (!recorded) {
        return CommandResult::StoreError;
    }
    // Published only now, so the job becomes runnable strictly after its intent
    // is durable -- which is the whole of L2-JOB-013.
    impl_->requests[job_id] = request;
    impl_->runnable.push_back(job_id);
    impl_->work_ready.notify_one();
    return CommandResult::Ok;
}

CommandResult JobManager::pause(const std::string& job_id,
                                std::string& error) {
    const std::unique_lock<std::mutex> lock(impl_->mutex);
    if (impl_->requests.find(job_id) == impl_->requests.end()) {
        error = "manager: no such job '" + job_id + "'";
        return CommandResult::UnknownJob;
    }
    if (impl_->active.find(job_id) != impl_->active.end()) {
        // L2-LIF-002 read for a rename engine: the safe points are the phase
        // boundaries, and a job past its commit point must finish. Refusing is
        // the cooperative answer; interrupting would tear a move in half.
        error = "manager: job '" + job_id +
                "' is already in flight and cannot be paused mid-move";
        return CommandResult::InvalidState;
    }
    impl_->take_runnable(job_id);
    impl_->waiting.erase(job_id);
    impl_->paused.insert(job_id);
    return CommandResult::Ok;
}

CommandResult JobManager::resume(const std::string& job_id,
                                 std::string& error) {
    const std::unique_lock<std::mutex> lock(impl_->mutex);
    if (impl_->requests.find(job_id) == impl_->requests.end()) {
        error = "manager: no such job '" + job_id + "'";
        return CommandResult::UnknownJob;
    }
    if (impl_->paused.erase(job_id) == 0) {
        error = "manager: job '" + job_id + "' is not paused";
        return CommandResult::InvalidState;
    }
    impl_->runnable.push_back(job_id);
    impl_->work_ready.notify_one();
    return CommandResult::Ok;
}

CommandResult JobManager::cancel(const std::string& job_id,
                                 std::string& error) {
    const std::unique_lock<std::mutex> lock(impl_->mutex);
    if (impl_->requests.find(job_id) == impl_->requests.end()) {
        error = "manager: no such job '" + job_id + "'";
        return CommandResult::UnknownJob;
    }
    if (impl_->active.find(job_id) != impl_->active.end()) {
        error = "manager: job '" + job_id +
                "' is in flight; a move past its commit point is not "
                "interruptible";
        return CommandResult::InvalidState;
    }

    impl_->take_runnable(job_id);
    impl_->waiting.erase(job_id);
    impl_->paused.erase(job_id);

    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    if (!impl_->store.load(job_id, job, found, error) || !found) {
        return CommandResult::UnknownJob;
    }
    if (job.state != JobState::Queued) {
        error = "manager: job '" + job_id + "' is " + to_string(job.state) +
                " and cannot be cancelled";
        return CommandResult::InvalidState;
    }
    // FAILED rather than CANCELLED_RETAINED: that state belongs to
    // L2-LIF-001/003, deferred with L1-SYS-003. Using the states the machine
    // actually defines keeps the durable record legal.
    if (!impl_->store.update_state(job_id, JobState::Failed,
                                   job.updated_at_ms + 1,
                                   "cancelled by operator", error)) {
        return CommandResult::StoreError;
    }
    return CommandResult::Ok;
}

CommandResult JobManager::retry(const std::string& job_id,
                                std::string& new_job_id,
                                std::string& error) {
    new_job_id.clear();

    MoveRequest move;
    std::int64_t now_ms = 0;
    {
        const std::unique_lock<std::mutex> lock(impl_->mutex);
        if (!impl_->running) {
            error = "manager: not running";
            return CommandResult::NotRunning;
        }
        const std::map<std::string, MoveRequest>::const_iterator request =
            impl_->requests.find(job_id);
        if (request == impl_->requests.end()) {
            error = "manager: no such job '" + job_id + "'";
            return CommandResult::UnknownJob;
        }
        move = request->second;
        now_ms = impl_->now();
    }

    // Every store call from here to the publish runs outside the manager mutex,
    // guarded only by store_mutex -- same reasoning as submit(). Probing for a
    // free id is several loads, each of which can block on busy_timeout.
    const std::lock_guard<std::mutex> store_guard(impl_->store_mutex);

    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    if (!impl_->store.load(job_id, job, found, error) || !found) {
        error = "manager: no such job '" + job_id + "'";
        return CommandResult::UnknownJob;
    }
    if (job.state != JobState::Failed) {
        // L2-LIF-005: a refusal is a typed error, not a panic.
        error = "manager: job '" + job_id + "' is " + to_string(job.state) +
                "; only a FAILED job can be retried";
        return CommandResult::InvalidState;
    }

    // A NEW job, not a revival. FAILED is terminal under L1-SYS-021, so there
    // is no legal edge back to QUEUED -- and there should not be one: the
    // record that this move failed, and why, is exactly what an operator needs
    // to still be there after the retry. retry_of links the two.
    const std::string root = strip_retry_suffix(job_id);
    std::string candidate;
    for (int n = 1;; ++n) {
        std::ostringstream os;
        os << root << "-retry-" << n;
        candidate = os.str();

        // Free means free in BOTH the durable record and this manager's live
        // maps. Checking only the store would let a retry collide with a job
        // submitted in this process but not yet recorded.
        bool taken = false;
        Job existing(std::string(), std::string(), std::string(), 0);
        if (!impl_->store.load(candidate, existing, taken, error)) {
            return CommandResult::StoreError;
        }
        if (taken) {
            continue;
        }
        // LOCK ORDER: store_mutex is already held and the manager mutex is
        // taken inside it. That nesting is the only one permitted -- nothing
        // anywhere takes the manager mutex first and then store_mutex, so
        // there is no cycle. submit() avoids nesting entirely by releasing one
        // before taking the other.
        const std::unique_lock<std::mutex> lock(impl_->mutex);
        if (impl_->requests.find(candidate) == impl_->requests.end() &&
            impl_->pending.insert(candidate).second) {
            break;
        }
    }

    const Job fresh(candidate, move.source_dir + "/" + move.source_name,
              move.dest_dir + "/" + move.dest_name, now_ms);
    const bool recorded = impl_->store.record_intent(fresh, job_id, error);

    const std::unique_lock<std::mutex> lock(impl_->mutex);
    impl_->pending.erase(candidate);
    if (!recorded) {
        return CommandResult::StoreError;
    }
    impl_->requests[candidate] = move;
    impl_->runnable.push_back(candidate);
    impl_->work_ready.notify_one();

    new_job_id = candidate;
    return CommandResult::Ok;
}

std::size_t JobManager::pump(std::string& error) {
    const std::unique_lock<std::mutex> lock(impl_->mutex);
    if (!impl_->running) {
        error = "manager: not running";
        return 0;
    }

    const std::int64_t now = impl_->now();
    std::size_t moved = 0;
    std::vector<std::string> due;
    for (std::map<std::string, std::int64_t>::iterator it =
             impl_->waiting.begin();
         it != impl_->waiting.end(); ++it) {
        if (it->second <= now && impl_->paused.find(it->first) ==
                                     impl_->paused.end()) {
            due.push_back(it->first);
        }
    }
    for (std::size_t i = 0; i < due.size(); ++i) {
        impl_->waiting.erase(due[i]);
        impl_->runnable.push_back(due[i]);
        ++moved;
    }
    if (moved > 0) {
        impl_->work_ready.notify_all();
    }
    return moved;
}

bool JobManager::wait_idle(int timeout_ms) {
    // A bounded poll rather than a timed condition wait, and the reason is
    // ThreadSanitizer rather than taste.
    //
    // This was `idle_changed.wait_until(lock, deadline)`, which is correct C++
    // and which TSan cannot model. `wait_until` lowers to
    // pthread_cond_timedwait, and TSan's accounting for the mutex does not
    // survive it: it subsequently believes the mutex is still held after an
    // explicit unlock, reports a phantom "double lock", and from then on treats
    // every access guarded by that mutex as unsynchronised -- producing race
    // reports in which BOTH sides are recorded as holding the same mutex, which
    // is impossible.
    //
    // Demonstrated in isolation rather than inferred. cpp/tsan_pattern.cpp is a
    // standalone program with no project code that runs the same loop three
    // ways from one binary, selected at runtime so nothing else differs:
    //
    //     wait()          0 warnings
    //     wait_until()   11-19 warnings
    //     bounded poll    0 warnings
    //
    // Reproducible across runs at four workers. See docs/C4-TSAN-OPEN.md.
    //
    // Polling is acceptable here specifically because this is a test helper for
    // waiting out quiescence, not a synchronisation mechanism: nothing depends
    // on the 1 ms granularity, and a missed wakeup costs a millisecond rather
    // than correctness. The project's preference for latches over sleeps is
    // about making an interleaving HAPPEN, which is a different problem and is
    // still served by the phase hook.
    //
    // The predicate is read under the lock. runnable and active change together
    // in run_worker -- a job is popped from one and inserted into the other in
    // the same critical section -- so there is no window in which both look
    // empty while a job is in flight.
    const int kPollMs = 1;
    int waited = 0;
    for (;;) {
        {
            const std::unique_lock<std::mutex> lock(impl_->mutex);
            if (impl_->runnable.empty() && impl_->active.empty()) {
                return true;
            }
        }
        if (waited >= timeout_ms) {
            const std::unique_lock<std::mutex> lock(impl_->mutex);
            return impl_->runnable.empty() && impl_->active.empty();
        }
        struct timespec ts;
        ts.tv_sec = 0;
        ts.tv_nsec = kPollMs * 1000000L;
        ::nanosleep(&ts, 0);
        waited += kPollMs;
    }
}

}  // namespace filemover
