// Event stream tests (C6, L2-EVT-001..005, L3-EVT-001..005).
// Assertions use natural order: actual == expected (L3-CPP-014).

#include "catch2/catch.hpp"

#include "filemover/events.hpp"

#include <time.h>

#include <atomic>
#include <condition_variable>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>

using filemover::Event;
using filemover::EventPublisher;
using filemover::EventSeverity;
using filemover::EventType;

namespace {

// A subscriber that records what it saw.
struct Recorder {
    std::vector<Event> seen;

    static void callback(const Event& event, void* user) {
        static_cast<Recorder*>(user)->seen.push_back(event);
    }
};

struct Thrower {
    int calls;

    Thrower() : calls(0) {}

    static void callback(const Event& /*event*/, void* user) {
        ++static_cast<Thrower*>(user)->calls;
        throw std::runtime_error("subscriber is broken");
    }

    static void callback_non_std(const Event& /*event*/, void* user) {
        ++static_cast<Thrower*>(user)->calls;
        throw 42;  // not derived from std::exception
    }
};

struct Counter {
    std::atomic<int> count;
    Counter() : count(0) {}

    static void callback(const Event& /*event*/, void* user) {
        ++static_cast<Counter*>(user)->count;
    }
};

Event sample(EventType type = EventType::JobCompleted,
             EventSeverity severity = EventSeverity::Info) {
    return Event(type, severity, 1754630000123LL, "job-7", "rec.mp4",
                 "detail here");
}

}  // namespace

// --- the record (L2-EVT-001, L2-EVT-005) ----------------------------------

TEST_CASE("an event carries its type, severity, time and identifiers",
          "[events][L2-EVT-001][L2-EVT-005]") {
    const Event event = sample();
    CHECK(event.type() == EventType::JobCompleted);
    CHECK(event.severity() == EventSeverity::Info);
    CHECK(event.timestamp_ms() == 1754630000123LL);
    CHECK(event.job_id() == std::string("job-7"));
    CHECK(event.file_id() == std::string("rec.mp4"));
    CHECK(event.detail() == std::string("detail here"));
    CHECK(event.has_job_id() == true);
    CHECK(event.has_file_id() == true);
}

TEST_CASE("an event has no mutators", "[events][L2-EVT-001]") {
    // L2-EVT-001 requires immutable records. Enforced by the type: a
    // const Event is fully readable, and there is no setter to call on a
    // non-const one either. A subscriber receives a const reference, so it
    // cannot alter what the next subscriber sees.
    const Event event = sample();
    Event copy = event;  // copyable, which the L3-EVT-001 snapshot needs
    CHECK(copy.job_id() == event.job_id());
    CHECK(std::is_copy_assignable<Event>::value == true);
}

TEST_CASE("transfer events are distinguished from service events",
          "[events][L2-EVT-005]") {
    // L2-EVT-005 applies to transfer events; service-lifecycle events have no
    // job to name. The predicate is what the manager test asserts against.
    CHECK(filemover::is_transfer_event(EventType::JobSubmitted) == true);
    CHECK(filemover::is_transfer_event(EventType::JobCompleted) == true);
    CHECK(filemover::is_transfer_event(EventType::JobFailed) == true);
    CHECK(filemover::is_transfer_event(EventType::JobHaltedAfterCommit) ==
          true);
    CHECK(filemover::is_transfer_event(EventType::JobFailedExternal) == true);
    CHECK(filemover::is_transfer_event(EventType::ServiceStarted) == false);
    CHECK(filemover::is_transfer_event(EventType::ServiceStopping) == false);
}

TEST_CASE("every event type and severity has a distinct name",
          "[events][L2-EVT-001]") {
    // A duplicated or missing name makes two different events indistinguishable
    // in the log, which is the only place most of them are ever seen.
    const EventType types[] = {
        EventType::ServiceStarted,      EventType::ServiceStopping,
        EventType::JobSubmitted,        EventType::JobStarted,
        EventType::JobCompleted,        EventType::JobFailed,
        EventType::JobHaltedAfterCommit, EventType::JobFailedExternal,
        EventType::JobRetryScheduled,   EventType::JobRetrySubmitted,
        EventType::JobPaused,           EventType::JobResumed,
        EventType::JobCancelled,        EventType::SubscriberFailed};
    const std::size_t count = sizeof(types) / sizeof(types[0]);

    std::vector<std::string> names;
    for (std::size_t i = 0; i < count; ++i) {
        const std::string name = filemover::to_string(types[i]);
        CHECK(name != std::string("unknown"));
        for (std::size_t j = 0; j < names.size(); ++j) {
            CHECK(names[j] != name);
        }
        names.push_back(name);
    }
}

TEST_CASE("severity is ordered", "[events][L2-EVT-001]") {
    CHECK(filemover::severity_at_least(EventSeverity::Error,
                                       EventSeverity::Warning) == true);
    CHECK(filemover::severity_at_least(EventSeverity::Info,
                                       EventSeverity::Info) == true);
    CHECK(filemover::severity_at_least(EventSeverity::Debug,
                                       EventSeverity::Info) == false);
}

// --- subscription (L3-EVT-004, L3-EVT-005) --------------------------------

TEST_CASE("a duplicate subscriber registration is refused",
          "[events][L3-EVT-004]") {
    EventPublisher publisher;
    Recorder recorder;
    std::string error;

    REQUIRE(publisher.subscribe(Recorder::callback, &recorder, error) == true);
    CHECK(publisher.subscribe(Recorder::callback, &recorder, error) == false);
    CHECK(error.empty() == false);
    CHECK(publisher.subscriber_count() == 1u);
}

TEST_CASE("the same callback with different user data is two subscribers",
          "[events][L3-EVT-004]") {
    // Identity is the (callback, user_data) PAIR. Several sinks share one
    // function, and refusing the second would make that impossible.
    EventPublisher publisher;
    Recorder first;
    Recorder second;
    std::string error;

    REQUIRE(publisher.subscribe(Recorder::callback, &first, error) == true);
    CHECK(publisher.subscribe(Recorder::callback, &second, error) == true);
    CHECK(publisher.subscriber_count() == 2u);

    publisher.publish(sample());
    CHECK(first.seen.size() == 1u);
    CHECK(second.seen.size() == 1u);
}

TEST_CASE("a null callback is refused", "[events][L3-EVT-004]") {
    EventPublisher publisher;
    std::string error;
    CHECK(publisher.subscribe(0, 0, error) == false);
    CHECK(publisher.subscriber_count() == 0u);
}

TEST_CASE("unsubscribe reports whether anything was removed",
          "[events][L3-EVT-005]") {
    EventPublisher publisher;
    Recorder recorder;
    std::string error;

    REQUIRE(publisher.subscribe(Recorder::callback, &recorder, error) == true);
    CHECK(publisher.unsubscribe(Recorder::callback, &recorder) == true);
    // The second call removes nothing, and says so -- a caller can tell
    // "cleaned up" from "was never registered".
    CHECK(publisher.unsubscribe(Recorder::callback, &recorder) == false);
    CHECK(publisher.subscriber_count() == 0u);
}

TEST_CASE("an unsubscribed subscriber stops receiving", "[events][L3-EVT-005]") {
    EventPublisher publisher;
    Recorder recorder;
    std::string error;

    REQUIRE(publisher.subscribe(Recorder::callback, &recorder, error) == true);
    publisher.publish(sample());
    REQUIRE(recorder.seen.size() == 1u);

    publisher.unsubscribe(Recorder::callback, &recorder);
    publisher.publish(sample());
    CHECK(recorder.seen.size() == 1u);
}

// --- isolation (L2-EVT-002, L3-EVT-003) -----------------------------------

TEST_CASE("a subscriber that throws does not stop the others",
          "[events][L2-EVT-002][L3-EVT-003]") {
    // The subscriber that throws is registered FIRST, so if the exception
    // escaped it would take the later subscribers with it. Ordering matters
    // here: registering it last would let the test pass with no isolation
    // whatsoever.
    EventPublisher publisher;
    Thrower thrower;
    Recorder recorder;
    std::string error;

    REQUIRE(publisher.subscribe(Thrower::callback, &thrower, error) == true);
    REQUIRE(publisher.subscribe(Recorder::callback, &recorder, error) == true);

    publisher.publish(sample());

    CHECK(thrower.calls == 1);
    CHECK(recorder.seen.size() == 1u);
}

TEST_CASE("a subscriber throwing a non-std type is also contained",
          "[events][L2-EVT-002][L3-EVT-003]") {
    // catch(...) as well as catch(const std::exception&). A subscriber in
    // another translation unit can throw anything at all, and an escaping
    // throw would call std::terminate on the publishing thread -- which for a
    // worker thread means the whole daemon.
    EventPublisher publisher;
    Thrower thrower;
    Recorder recorder;
    std::string error;

    REQUIRE(publisher.subscribe(Thrower::callback_non_std, &thrower, error) ==
            true);
    REQUIRE(publisher.subscribe(Recorder::callback, &recorder, error) == true);

    publisher.publish(sample());

    CHECK(thrower.calls == 1);
    CHECK(recorder.seen.size() == 1u);
}

TEST_CASE("a throwing subscriber keeps receiving later events",
          "[events][L2-EVT-002]") {
    // Not auto-unsubscribed on failure. Dropping a subscriber that threw once
    // would silently disable the log sink for the rest of the process, and the
    // symptom -- logs that stop -- looks like the service hanging.
    EventPublisher publisher;
    Thrower thrower;
    std::string error;
    REQUIRE(publisher.subscribe(Thrower::callback, &thrower, error) == true);

    publisher.publish(sample());
    publisher.publish(sample());
    CHECK(thrower.calls == 2);
    CHECK(publisher.subscriber_count() == 1u);
}

// --- L3-EVT-001 / L3-EVT-002 ----------------------------------------------

namespace {

// Subscribes and unsubscribes from inside a callback, which is what the
// snapshot has to tolerate.
struct Reentrant {
    EventPublisher* publisher;
    Recorder* other;
    int calls;

    Reentrant() : publisher(0), other(0), calls(0) {}

    static void unsubscribe_self(const Event& /*event*/, void* user) {
        Reentrant* self = static_cast<Reentrant*>(user);
        ++self->calls;
        // Must not deadlock: the in-flight publish it would otherwise wait for
        // is the one calling it.
        self->publisher->unsubscribe(unsubscribe_self, self);
    }

    static void publish_again(const Event& event, void* user) {
        Reentrant* self = static_cast<Reentrant*>(user);
        ++self->calls;
        if (self->calls < 2) {
            // Re-entering publish would deadlock if the subscriber lock were
            // held across callbacks (L3-EVT-002).
            self->publisher->publish(event);
        }
    }
};

}  // namespace

TEST_CASE("a subscriber may publish from its own callback",
          "[events][L3-EVT-002]") {
    // The direct test of "the lock is not held across callbacks". Verified by
    // holding it: this test HANGS rather than failing, because the nested
    // publish blocks on a mutex its own caller holds. So a hang here means the
    // lock came back -- it is a real signal, not a flaky test.
    EventPublisher publisher;
    Reentrant reentrant;
    reentrant.publisher = &publisher;
    std::string error;
    REQUIRE(publisher.subscribe(Reentrant::publish_again, &reentrant, error) ==
            true);

    publisher.publish(sample());
    CHECK(reentrant.calls == 2);
}

TEST_CASE("a subscriber may unsubscribe itself from its own callback",
          "[events][L3-EVT-002][L3-EVT-005]") {
    EventPublisher publisher;
    Reentrant reentrant;
    reentrant.publisher = &publisher;
    std::string error;
    REQUIRE(publisher.subscribe(Reentrant::unsubscribe_self, &reentrant,
                                error) == true);

    publisher.publish(sample());
    CHECK(reentrant.calls == 1);
    CHECK(publisher.subscriber_count() == 0u);

    publisher.publish(sample());
    CHECK(reentrant.calls == 1);
}

TEST_CASE("a subscriber removed before a publish does not receive it",
          "[events][L3-EVT-001]") {
    EventPublisher publisher;
    Recorder first;
    Recorder second;
    std::string error;
    REQUIRE(publisher.subscribe(Recorder::callback, &first, error) == true);
    REQUIRE(publisher.subscribe(Recorder::callback, &second, error) == true);

    publisher.unsubscribe(Recorder::callback, &second);
    publisher.publish(sample());
    CHECK(first.seen.size() == 1u);
    CHECK(second.seen.size() == 0u);
}

// --- concurrency (L2-EVT-004) ---------------------------------------------

TEST_CASE("concurrent publishers all deliver", "[events][L2-EVT-004]") {
    // Run under TSan in its own tier, which is where a missing lock actually
    // shows. The count assertion is what catches a lost update.
    EventPublisher publisher;
    Counter counter;
    std::string error;
    REQUIRE(publisher.subscribe(Counter::callback, &counter, error) == true);

    const int kThreads = 8;
    const int kPerThread = 200;
    std::vector<std::thread> threads;
    threads.reserve(kThreads);
    for (int i = 0; i < kThreads; ++i) {
        threads.push_back(std::thread([&publisher]() {
            for (int n = 0; n < kPerThread; ++n) {
                publisher.publish(sample());
            }
        }));
    }
    for (std::size_t i = 0; i < threads.size(); ++i) {
        threads[i].join();
    }

    CHECK(counter.count.load() == kThreads * kPerThread);
}

TEST_CASE("concurrent subscribe and unsubscribe leave a consistent list",
          "[events][L2-EVT-004]") {
    EventPublisher publisher;
    Counter stable;
    std::string error;
    REQUIRE(publisher.subscribe(Counter::callback, &stable, error) == true);

    std::atomic<bool> stop(false);
    std::thread publisher_thread([&publisher, &stop]() {
        while (!stop.load()) {
            publisher.publish(sample());
        }
    });

    // Wait for the publisher to actually be running before churning
    // subscriptions against it. Without this the churn loop can finish before
    // the thread is first scheduled, and the test asserts nothing at all --
    // which is how it behaved the first time it ran: zero publishes, green.
    while (stable.count.load() == 0) {
    }

    for (int i = 0; i < 200; ++i) {
        Counter transient;
        std::string subscribe_error;
        if (publisher.subscribe(Counter::callback, &transient,
                                subscribe_error)) {
            publisher.unsubscribe(Counter::callback, &transient);
        }
    }

    stop.store(true);
    publisher_thread.join();
    CHECK(stable.count.load() > 0);
    CHECK(publisher.subscriber_count() == 1u);
}

namespace {

// Blocks inside its callback until released, so a publish can be held with its
// snapshot taken and its remaining callbacks not yet made.
struct Gate {
    std::mutex mutex;
    std::condition_variable cv;
    bool arrived;
    bool released;

    Gate() : arrived(false), released(false) {}

    static void callback(const Event& /*event*/, void* user) {
        Gate* self = static_cast<Gate*>(user);
        std::unique_lock<std::mutex> lock(self->mutex);
        self->arrived = true;
        self->cv.notify_all();
        while (!self->released) {
            self->cv.wait(lock);
        }
    }

    void wait_arrival() {
        std::unique_lock<std::mutex> lock(mutex);
        while (!arrived) {
            cv.wait(lock);
        }
    }

    void release() {
        const std::lock_guard<std::mutex> guard(mutex);
        released = true;
        cv.notify_all();
    }
};

void sleep_ms(int ms) {
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = static_cast<long>(ms % 1000) * 1000000L;
    (void)::nanosleep(&ts, 0);
}

}  // namespace

TEST_CASE("unsubscribe waits for an in-flight publish to finish with it",
          "[events][L2-EVT-004][L3-EVT-001]") {
    // The hazard the snapshot creates, and the reason unsubscribe blocks.
    //
    // A publishing thread copies the subscriber list, then invokes callbacks
    // with no lock held. If unsubscribe returned while that copy was still in
    // use, the caller would be entitled to destroy its user_data -- and the
    // publisher would then call into freed memory.
    //
    // Made deterministic rather than left to chance: a gate subscriber holds
    // the publish open, so the removal and the free happen while the snapshot
    // is provably still live. The churn test above does NOT catch this --
    // verified by removing the wait and watching it stay green.
    EventPublisher publisher;
    Gate gate;
    std::string error;
    REQUIRE(publisher.subscribe(Gate::callback, &gate, error) == true);

    // Heap-allocated so the free is a real free ASan can see, and registered
    // AFTER the gate so its callback is still pending when the gate blocks.
    Counter* victim = new Counter();
    REQUIRE(publisher.subscribe(Counter::callback, victim, error) == true);

    std::thread publishing([&publisher]() { publisher.publish(sample()); });
    gate.wait_arrival();  // snapshot taken, victim's callback not yet made

    std::atomic<bool> freed(false);
    std::thread remover([&publisher, victim, &freed]() {
        publisher.unsubscribe(Counter::callback, victim);
        delete victim;
        freed.store(true);
    });

    // With the wait in place the remover is blocked and `freed` stays false;
    // the bounded poll then expires and the gate is released, after which the
    // remover proceeds safely. Without the wait, `freed` goes true almost at
    // once and releasing the gate sends the publisher into freed memory --
    // which is the point, and what ASan reports.
    for (int waited = 0; waited < 300 && !freed.load(); waited += 5) {
        sleep_ms(5);
    }
    gate.release();

    publishing.join();
    remover.join();

    CHECK(publisher.subscriber_count() == 1u);  // the gate remains
    publisher.unsubscribe(Gate::callback, &gate);
}
