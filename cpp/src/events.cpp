// C6: the operational event stream (L2-EVT-001..005, L3-EVT-001..005).

#include "filemover/events.hpp"

#include <errno.h>
#include <time.h>

#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <string>
#include <vector>

namespace filemover {

const char* to_string(EventSeverity severity) {
    switch (severity) {
        case EventSeverity::Debug:
            return "DEBUG";
        case EventSeverity::Info:
            return "INFO";
        case EventSeverity::Warning:
            return "WARNING";
        case EventSeverity::Error:
            return "ERROR";
    }
    return "UNKNOWN";
}

bool severity_at_least(EventSeverity severity, EventSeverity minimum) {
    return static_cast<int>(severity) >= static_cast<int>(minimum);
}

const char* to_string(EventType type) {
    switch (type) {
        case EventType::ServiceStarted:
            return "service.started";
        case EventType::ServiceStopping:
            return "service.stopping";
        case EventType::JobSubmitted:
            return "job.submitted";
        case EventType::JobStarted:
            return "job.started";
        case EventType::JobCompleted:
            return "job.completed";
        case EventType::JobFailed:
            return "job.failed";
        case EventType::JobHaltedAfterCommit:
            return "job.halted_after_commit";
        case EventType::JobFailedExternal:
            return "job.failed_external";
        case EventType::JobRetryScheduled:
            return "job.retry_scheduled";
        case EventType::JobRetrySubmitted:
            return "job.retry_submitted";
        case EventType::JobPaused:
            return "job.paused";
        case EventType::JobResumed:
            return "job.resumed";
        case EventType::JobCancelled:
            return "job.cancelled";
        case EventType::SubscriberFailed:
            return "subscriber.failed";
    }
    return "unknown";
}

bool is_transfer_event(EventType type) {
    switch (type) {
        case EventType::ServiceStarted:
        case EventType::ServiceStopping:
        case EventType::SubscriberFailed:
            return false;
        case EventType::JobSubmitted:
        case EventType::JobStarted:
        case EventType::JobCompleted:
        case EventType::JobFailed:
        case EventType::JobHaltedAfterCommit:
        case EventType::JobFailedExternal:
        case EventType::JobRetryScheduled:
        case EventType::JobRetrySubmitted:
        case EventType::JobPaused:
        case EventType::JobResumed:
        case EventType::JobCancelled:
            return true;
    }
    return false;
}

Event::Event()
    : type_(EventType::ServiceStarted),
      severity_(EventSeverity::Info),
      timestamp_ms_(0) {}

Event::Event(EventType type,
             EventSeverity severity,
             std::int64_t timestamp_ms,
             const std::string& job_id,
             const std::string& file_id,
             const std::string& detail)
    : type_(type),
      severity_(severity),
      timestamp_ms_(timestamp_ms),
      job_id_(job_id),
      file_id_(file_id),
      detail_(detail) {}

std::int64_t now_epoch_ms() {
    struct timespec ts;
    // CLOCK_REALTIME: this value is read by a human next to other logs, so it
    // must be a wall-clock date even though that means it can step.
    if (::clock_gettime(CLOCK_REALTIME, &ts) != 0) {
        return 0;
    }
    return static_cast<std::int64_t>(ts.tv_sec) * 1000 +
           static_cast<std::int64_t>(ts.tv_nsec) / 1000000;
}

namespace {

struct Subscriber {
    EventCallback callback;
    void* user_data;

    Subscriber() : callback(0), user_data(0) {}
    Subscriber(EventCallback cb, void* user) : callback(cb), user_data(user) {}
};

// Non-zero while THIS thread is inside publish(). Read by unsubscribe to tell
// "another thread is publishing, wait for it" from "I am being called by a
// subscriber, and waiting would be waiting for myself".
thread_local int g_publish_depth = 0;

}  // namespace

struct EventPublisher::Impl {
    mutable std::mutex mutex;
    std::vector<Subscriber> subscribers;

    // How many publish() calls are between taking their snapshot and finishing
    // their last callback. unsubscribe waits for this to reach zero so a caller
    // may free its user_data the moment unsubscribe returns.
    std::size_t in_flight;
    std::condition_variable drained;

    Impl() : in_flight(0) {}
};

EventPublisher::EventPublisher() : impl_(new Impl()) {}

EventPublisher::~EventPublisher() { delete impl_; }

bool EventPublisher::subscribe(EventCallback callback,
                               void* user_data,
                               std::string& error) {
    if (callback == 0) {
        error = "events: subscriber callback is null";
        return false;
    }

    const std::lock_guard<std::mutex> guard(impl_->mutex);
    for (std::size_t i = 0; i < impl_->subscribers.size(); ++i) {
        if (impl_->subscribers[i].callback == callback &&
            impl_->subscribers[i].user_data == user_data) {
            error = "events: subscriber is already registered";  // L3-EVT-004
            return false;
        }
    }

    impl_->subscribers.push_back(Subscriber(callback, user_data));
    error.clear();
    return true;
}

bool EventPublisher::unsubscribe(EventCallback callback, void* user_data) {
    std::unique_lock<std::mutex> lock(impl_->mutex);

    bool removed = false;
    for (std::size_t i = 0; i < impl_->subscribers.size(); ++i) {
        if (impl_->subscribers[i].callback == callback &&
            impl_->subscribers[i].user_data == user_data) {
            impl_->subscribers.erase(impl_->subscribers.begin() +
                                     static_cast<std::ptrdiff_t>(i));
            removed = true;
            break;
        }
    }

    // Removed from the list, but a publish that started earlier may still hold
    // it in its snapshot. Wait that out, so the caller can destroy whatever
    // user_data points at. Skipped when this thread is itself publishing --
    // that in-flight count includes us, and waiting would never return.
    if (g_publish_depth == 0) {
        while (impl_->in_flight > 0) {
            impl_->drained.wait(lock);
        }
    }

    return removed;  // L3-EVT-005
}

void EventPublisher::publish(const Event& event) {
    // L3-EVT-001: the snapshot. Taken under the lock, used outside it.
    std::vector<Subscriber> snapshot;
    {
        const std::lock_guard<std::mutex> guard(impl_->mutex);
        snapshot = impl_->subscribers;
        ++impl_->in_flight;
    }

    // L3-EVT-002: the lock is NOT held from here down.
    ++g_publish_depth;
    for (std::size_t i = 0; i < snapshot.size(); ++i) {
        try {
            snapshot[i].callback(event, snapshot[i].user_data);
        } catch (const std::exception& ex) {
            // L3-EVT-003 / L2-EVT-002. Reported on stderr, NOT published: a
            // subscriber that throws on every event would, if this republished,
            // be handed the failure event and throw again, and the recursion
            // would only end with the stack.
            (void)std::fprintf(stderr,
                               "[%s] subscriber threw on %s: %s\n",
                               to_string(EventSeverity::Error),
                               to_string(event.type()), ex.what());
        } catch (...) {
            (void)std::fprintf(stderr, "[%s] subscriber threw on %s\n",
                               to_string(EventSeverity::Error),
                               to_string(event.type()));
        }
    }
    --g_publish_depth;

    {
        const std::lock_guard<std::mutex> guard(impl_->mutex);
        --impl_->in_flight;
        if (impl_->in_flight == 0) {
            impl_->drained.notify_all();
        }
    }
}

std::size_t EventPublisher::subscriber_count() const {
    const std::lock_guard<std::mutex> guard(impl_->mutex);
    return impl_->subscribers.size();
}

}  // namespace filemover
