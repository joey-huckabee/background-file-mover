#ifndef FILEMOVER_EVENT_LOG_HPP
#define FILEMOVER_EVENT_LOG_HPP

// C6: the log sink -- the one subscriber the service always installs.
//
// Traces: L2-CLI-006, L2-EVT-002
//
// L2-CLI-006 gives the service a stream contract that is the OPPOSITE of the
// CLI's, and that is the part implemented wrongly when it is not written down:
//
//   CLI      stdout carries the command RESULT; diagnostics go to stderr.
//   service  stdout and stderr both carry the log stream, split by severity --
//            DEBUG/INFO to stdout, WARNING/ERROR to stderr.
//
// A CLI's output is its result, so a stray log line on stdout corrupts a JSON
// consumer. A daemon has no result, so its logs ARE its output. Splitting by
// severity keeps `journalctl -p warning` and `2>/dev/null` behaving the way an
// operator expects.
//
// No log file is ever opened, named, rotated or deleted (twelve-factor XI).
// The environment routes the streams; under the shipped systemd unit that is
// journald.

#include <string>

#include "filemover/events.hpp"

namespace filemover {

// What the sink needs, and all it needs. Passed as the subscriber's user_data,
// so it must outlive the subscription -- the Service owns one for its lifetime.
struct EventLogOptions {
    EventSeverity minimum;
    bool enabled;

    EventLogOptions() : minimum(EventSeverity::Info), enabled(true) {}
};

// One line per event, ISO-8601 UTC first so `sort` on a merged log is
// chronological.
//
//   2026-08-08T06:30:00.123Z INFO  job.completed job=job-12 file=rec.mp4 ...
//
// A PURE function returning a string, deliberately: it is the part with all the
// formatting decisions in it, and this way the tests assert on its output
// directly instead of capturing a file descriptor and hoping. The I/O is the
// trivial part and lives in log_event.
//
// Fields are omitted when absent rather than printed empty, so a service event
// does not carry a misleading `job=`.
std::string format_event(const Event& event);

// The subscriber. `user_data` must point at an EventLogOptions.
//
// Writes to stdout or stderr per L2-CLI-006 and flushes: the daemon's stdout is
// a pipe under systemd, so it is block-buffered, and an unflushed line is a
// line an operator does not see until the buffer fills -- which during an
// incident is exactly when it matters. (main.cpp also sets line buffering; both
// are cheap and this one keeps the sink correct wherever it is used.)
void log_event(const Event& event, void* user_data);

// Parses a configured level: DEBUG, INFO, WARNING, ERROR, or OFF.
//
// Case-insensitive over ASCII only, done by hand rather than through <cctype>:
// L3-CPP-052's reasoning applies wherever a configuration value is classified,
// not only in the parsers the gate scans. Under tr_TR.UTF-8, std::tolower('I')
// is not 'i', so "INFO" would stop matching.
//
// OFF sets `enabled` false and leaves `minimum` untouched -- it is not a level
// above ERROR, it is the absence of logging, and modelling it as a level means
// somebody eventually compares against it.
bool parse_severity(const std::string& text,
                    EventSeverity& minimum,
                    bool& enabled);

}  // namespace filemover

#endif  // FILEMOVER_EVENT_LOG_HPP
