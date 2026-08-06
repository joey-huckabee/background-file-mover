// Scratch: does the JobManager LOCK PATTERN alone race under TSan, with no
// SQLite and no filesystem work anywhere near it?
//
// Mirrors run_worker(): one unique_lock held across the loop, released around
// the slow part and retaken, over the same container types the manager guards.
// If this is clean, the pattern is fine and the reports come from inside
// engine.execute(). If it reports, the manager's own locking is the problem.
#include <deque>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>

#include "sqlite/sqlite3.h"

// Set from argv[2]: each worker opens its own connection to one shared file,
// exactly as L2-JOB-003 requires of the manager. Nothing else about the
// program changes, so if the reports appear only when this is on, SQLite's
// presence is what TSan cannot model -- not the locking.
static const char* g_db_path = 0;

// argv[3]: run the SQLite write while the shared mutex is HELD, rather than in
// the unlocked window.
static bool g_sql_under_lock = false;

struct Shared {
    std::mutex mutex;
    std::condition_variable work_ready;
    std::condition_variable idle_changed;
    std::deque<std::string> runnable;
    std::map<std::string, std::string> requests;
    std::set<std::string> active;
    bool running;
    bool stopping;
    std::vector<std::thread> workers;
    Shared() : running(false), stopping(false) {}

    // A member function reached through std::thread(&Shared::run, this),
    // matching how the manager starts its workers.
    void run();
};

// Stands in for engine.execute(): burns time touching only thread-local state.
unsigned long slow_work(const std::string& id) {
    unsigned long acc = 0;
    for (int i = 0; i < 20000; ++i) {
        acc += static_cast<unsigned long>(id.size()) + i;
    }
    return acc;
}

void Shared::run() {
    Shared* s = this;

    // Per-thread connection, opened before the loop and closed after it, the
    // same lifetime JobStore has inside run_worker().
    sqlite3* db = 0;
    if (g_db_path != 0) {
        if (sqlite3_open(g_db_path, &db) != SQLITE_OK) {
            fprintf(stderr, "open failed\n");
            return;
        }
        sqlite3_busy_timeout(db, 5000);
        char* msg = 0;
        sqlite3_exec(db, "PRAGMA journal_mode=WAL;", 0, 0, &msg);
        if (msg) sqlite3_free(msg);
    }

    std::unique_lock<std::mutex> lock(s->mutex);
    for (;;) {
        while (s->runnable.empty() && !s->stopping) {
            s->work_ready.wait(lock);
        }
        if (s->runnable.empty() && s->stopping) {
            break;
        }
        const std::string id = s->runnable.front();
        s->runnable.pop_front();
        const std::string payload = s->requests[id];
        s->active.insert(id);

        lock.unlock();
        volatile unsigned long sink = slow_work(payload);
        (void)sink;
        if (db != 0 && !g_sql_under_lock) {
            // One trivial write per job, in the unlocked window.
            char* msg = 0;
            sqlite3_exec(db, "INSERT INTO t (k) VALUES (NULL);", 0, 0, &msg);
            if (msg) sqlite3_free(msg);
        }
        lock.lock();

        // The manager's failure path (fail_permanently / handle_failure) calls
        // the store WHILE HOLDING the manager mutex. That is the one shape the
        // clean runs above never exercised: SQLite taking its own mutexes while
        // M9 is already in this thread's held set.
        if (db != 0 && g_sql_under_lock) {
            char* msg = 0;
            sqlite3_exec(db, "INSERT INTO t (k) VALUES (NULL);", 0, 0, &msg);
            if (msg) sqlite3_free(msg);
        }

        s->active.erase(id);
        s->idle_changed.notify_all();
        if (s->runnable.empty() && s->stopping) {
            break;
        }
    }
    lock.unlock();
    if (db != 0) {
        sqlite3_close(db);
    }
}

int main(int argc, char** argv) {
    const int workers = (argc > 1) ? atoi(argv[1]) : 4;
    if (argc > 2) {
        g_db_path = argv[2];
    }
    if (argc > 3) {
        g_sql_under_lock = true;
    }

    // Open a connection on the main thread BEFORE any worker exists, so
    // SQLite's one-time lazy initialization happens single-threaded. The
    // manager gets this for free because start() opens its own store before
    // spawning workers; without it, four concurrent sqlite3_open calls race
    // inside sqlite3_initialize and drown out whatever else is happening.
    sqlite3* main_db = 0;
    if (g_db_path != 0) {
        if (sqlite3_open(g_db_path, &main_db) != SQLITE_OK) {
            fprintf(stderr, "main open failed\n");
            return 1;
        }
        char* msg = 0;
        sqlite3_exec(main_db,
                     "PRAGMA journal_mode=WAL;"
                     "CREATE TABLE IF NOT EXISTS t (k INTEGER PRIMARY KEY);",
                     0, 0, &msg);
        if (msg) sqlite3_free(msg);
    }

    // Heap-allocated, like JobManager::Impl, so the shared state is not on
    // main's stack.
    Shared* s = new Shared();

    // start(): flags under the lock, threads spawned with the lock RELEASED,
    // then the lock retaken to record them -- the manager's exact shape.
    {
        std::unique_lock<std::mutex> lock(s->mutex);
        s->stopping = false;
        s->running = true;
    }
    std::vector<std::thread> spawned;
    for (int i = 0; i < workers; ++i) {
        spawned.push_back(std::thread(&Shared::run, s));
    }
    {
        std::unique_lock<std::mutex> lock(s->mutex);
        for (size_t i = 0; i < spawned.size(); ++i) {
            s->workers.push_back(std::move(spawned[i]));
        }
    }

    for (int i = 0; i < 12; ++i) {
        std::ostringstream name;
        name << "f" << i;
        std::unique_lock<std::mutex> lock(s->mutex);
        s->requests[name.str()] = name.str() + "-payload";
        s->runnable.push_back(name.str());
        s->work_ready.notify_one();
    }

    {   // wait_idle equivalent
        std::unique_lock<std::mutex> lock(s->mutex);
        while (!s->runnable.empty() || !s->active.empty()) {
            s->idle_changed.wait(lock);
        }
    }

    // shutdown(): flip the flags and swap the worker vector out under the
    // lock, then join outside it.
    std::vector<std::thread> to_join;
    {
        std::unique_lock<std::mutex> lock(s->mutex);
        s->stopping = true;
        s->running = false;
        s->work_ready.notify_all();
        to_join.swap(s->workers);
    }
    for (size_t i = 0; i < to_join.size(); ++i) {
        if (to_join[i].joinable()) {
            to_join[i].join();
        }
    }
    delete s;
    if (main_db != 0) {
        sqlite3_close(main_db);
    }
    printf("pattern done\n");
    return 0;
}
