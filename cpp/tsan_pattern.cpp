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

struct Shared {
    std::mutex mutex;
    std::condition_variable work_ready;
    std::condition_variable idle_changed;
    std::deque<std::string> runnable;
    std::map<std::string, std::string> requests;
    std::set<std::string> active;
    bool stopping;
    Shared() : stopping(false) {}
};

// Stands in for engine.execute(): burns time touching only thread-local state.
unsigned long slow_work(const std::string& id) {
    unsigned long acc = 0;
    for (int i = 0; i < 20000; ++i) {
        acc += static_cast<unsigned long>(id.size()) + i;
    }
    return acc;
}

void worker(Shared* s) {
    std::unique_lock<std::mutex> lock(s->mutex);
    for (;;) {
        while (s->runnable.empty() && !s->stopping) {
            s->work_ready.wait(lock);
        }
        if (s->runnable.empty() && s->stopping) {
            return;
        }
        const std::string id = s->runnable.front();
        s->runnable.pop_front();
        const std::string payload = s->requests[id];
        s->active.insert(id);

        lock.unlock();
        volatile unsigned long sink = slow_work(payload);
        (void)sink;
        lock.lock();

        s->active.erase(id);
        s->idle_changed.notify_all();
    }
}

int main(int argc, char** argv) {
    const int workers = (argc > 1) ? atoi(argv[1]) : 4;
    Shared s;

    std::vector<std::thread> pool;
    for (int i = 0; i < workers; ++i) {
        pool.push_back(std::thread(worker, &s));
    }

    for (int i = 0; i < 12; ++i) {
        std::ostringstream name;
        name << "f" << i;
        std::unique_lock<std::mutex> lock(s.mutex);
        s.requests[name.str()] = name.str() + "-payload";
        s.runnable.push_back(name.str());
        s.work_ready.notify_one();
    }

    {   // wait_idle equivalent
        std::unique_lock<std::mutex> lock(s.mutex);
        while (!s.runnable.empty() || !s.active.empty()) {
            s.idle_changed.wait(lock);
        }
    }
    {
        std::unique_lock<std::mutex> lock(s.mutex);
        s.stopping = true;
        s.work_ready.notify_all();
    }
    for (size_t i = 0; i < pool.size(); ++i) {
        pool[i].join();
    }
    printf("pattern done\n");
    return 0;
}
