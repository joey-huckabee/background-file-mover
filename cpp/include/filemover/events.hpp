#ifndef FILEMOVER_EVENTS_HPP
#define FILEMOVER_EVENTS_HPP

// C6: the operational event stream.
//
// Traces: L2-EVT-001..005, L3-EVT-001..005
//
// What this is FOR, and what it is deliberately not for.
//
// The event stream is how the service tells an operator what it is doing. It is
// an OBSERVATION channel: everything published here has already happened and
// has already been recorded durably. L2-EVT-003 states the consequence -- no
// subscriber performs an authoritative job-state transition -- and it is worth
// being blunt about why. If a state change were applied by a subscriber, then a
// subscriber that threw, or was slow, or had been unsubscribed a microsecond
// earlier, would silently change what the service DID rather than only what it
// reported. Publication is therefore always the last step of an operation, and
// never a step the operation depends on.
//
// The subscriber contract is a plain function pointer plus a void*, matching
// the clock and the phase hook. No <functional>: this crosses an API boundary,
// and a C++11 header should not drag std::function through it for a callback
// that is always a free function in practice.

#include <cstddef>
#include <cstdint>
#include <string>

namespace filemover {

// Maps onto the syslog-style levels L2-CLI-006 splits across the standard
// streams: Debug and Info to stdout, Warning and above to stderr.
enum class EventSeverity { Debug, Info, Warning, Error };

const char* to_string(EventSeverity severity);

// True when `severity` is at or above `minimum` -- the filter the log sink
// applies. A total order over the enum, kept as a function so the comparison
// is not spelled out (and got backwards) at each call site.
bool severity_at_least(EventSeverity severity, EventSeverity minimum);

// The closed set of things worth telling an operator about. An enum rather than
// a string: L2-EVT-001 requires typed records, and a typed event cannot be
// emitted with a misspelled name that no subscriber will ever match on.
enum class EventType {
    // Service lifecycle. No job identifier applies to these.
    ServiceStarted,
    ServiceStopping,

    // Job lifecycle. Every one of these carries a job identifier
    // (L2-EVT-005); is_transfer_event() is the predicate that says so.
    JobSubmitted,
    JobStarted,
    JobCompleted,
    JobFailed,

    // Distinct from JobFailed on purpose. L2-JOB-014's HaltedAfterCommit means
    // the move really happened but the record does not say so, and L2-SEC-011's
    // FailedExternal means something outside this service removed the file. An
    // operator's next action differs for each, and collapsing them into
    // "failed" would delete the only signal that says which.
    JobHaltedAfterCommit,
    JobFailedExternal,

    JobRetryScheduled,
    JobRetrySubmitted,
    JobPaused,
    JobResumed,
    JobCancelled,

    // A subscriber threw. Published by nothing -- see EventPublisher::publish,
    // which reports these directly rather than recursively.
    SubscriberFailed
};

const char* to_string(EventType type);

// L2-EVT-005: transfer events carry a job identifier. Service-lifecycle events
// do not, because there is no job to name.
bool is_transfer_event(EventType type);

// L2-EVT-001: a typed, immutable record.
//
// Immutable by having no mutators rather than by const members: const members
// would delete copy-assignment, and L3-EVT-001's snapshot copies these into a
// vector. Nothing can change an Event after construction, which is the property
// the requirement is after -- a subscriber cannot alter what a later subscriber
// sees.
class Event {
  public:
    Event();
    Event(EventType type,
          EventSeverity severity,
          std::int64_t timestamp_ms,
          const std::string& job_id,
          const std::string& file_id,
          const std::string& detail);

    EventType type() const { return type_; }
    EventSeverity severity() const { return severity_; }

    // Wall-clock milliseconds since the Unix epoch. Wall clock, not the
    // manager's monotonic clock: this one is read by a human against other
    // logs, and a monotonic value is meaningless outside this process.
    std::int64_t timestamp_ms() const { return timestamp_ms_; }

    const std::string& job_id() const { return job_id_; }
    const std::string& file_id() const { return file_id_; }
    const std::string& detail() const { return detail_; }

    bool has_job_id() const { return !job_id_.empty(); }
    bool has_file_id() const { return !file_id_.empty(); }

  private:
    EventType type_;
    EventSeverity severity_;
    std::int64_t timestamp_ms_;
    std::string job_id_;
    std::string file_id_;
    std::string detail_;
};

// Wall-clock milliseconds since the Unix epoch, for event construction.
// Separate from the manager's ClockFn, which is monotonic and injectable --
// these are different clocks answering different questions, and conflating them
// is how a log line ends up stamped with 41 years before the Unix epoch.
std::int64_t now_epoch_ms();

// A subscriber. Invoked with the publishing thread, so it must be quick and
// must not take a lock the publisher's caller already holds.
typedef void (*EventCallback)(const Event& event, void* user_data);

// L2-EVT-004: safe under concurrent emission.
class EventPublisher {
  public:
    EventPublisher();
    ~EventPublisher();

    // L3-EVT-004: a duplicate registration is refused rather than silently
    // accepted. Identity is the (callback, user_data) PAIR -- one callback
    // registered twice with different user data is two subscribers, which is
    // how several sinks share one function.
    //
    // Refused rather than deduplicated because a double subscribe is a bug in
    // the caller, and the caller that then unsubscribes once would otherwise be
    // left with a subscription it believes it removed.
    bool subscribe(EventCallback callback, void* user_data, std::string& error);

    // L3-EVT-005: reports whether anything was removed, so a caller can tell
    // "cleaned up" from "was never registered".
    //
    // BLOCKS until any in-flight publish that may hold this subscriber in its
    // snapshot has finished, so a caller may destroy the object `user_data`
    // points at as soon as this returns. Without that guarantee the snapshot
    // L3-EVT-001 requires would be a use-after-free waiting to happen: the
    // subscriber list no longer names you, but a publishing thread is still
    // holding the copy it took a moment ago.
    //
    // Called FROM a subscriber callback it does not wait -- the in-flight
    // publication it would be waiting for is the one calling it, and waiting
    // would deadlock a thread on itself.
    bool unsubscribe(EventCallback callback, void* user_data);

    // L3-EVT-001 and L3-EVT-002: snapshot the subscriber list under the lock,
    // release the lock, then invoke. Holding the lock across callbacks would
    // put arbitrary subscriber code inside the publisher's critical section --
    // a slow subscriber would serialise every emitting thread, and one that
    // published from its own callback would deadlock outright.
    //
    // L2-EVT-002 and L3-EVT-003: each callback is invoked inside its own
    // try/catch, so a subscriber that throws cannot stop delivery to the
    // subscribers after it. The failure is reported on stderr rather than
    // published, because publishing it would re-enter this function from a
    // broken subscriber and could not terminate.
    void publish(const Event& event);

    std::size_t subscriber_count() const;

  private:
    EventPublisher(const EventPublisher&);
    EventPublisher& operator=(const EventPublisher&);

    struct Impl;
    Impl* impl_;
};

}  // namespace filemover

#endif  // FILEMOVER_EVENTS_HPP
