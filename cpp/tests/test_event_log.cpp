// Log sink tests (C6, L2-CLI-006).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// format_event is a pure function, so the formatting decisions are asserted
// directly instead of by capturing a file descriptor. The stream SPLIT is the
// one part that cannot be tested that way -- which stream a line goes to is not
// visible in the line -- so that case redirects the real stdout and stderr.

#include "catch2/catch.hpp"

#include "filemover/event_log.hpp"

#include <stdio.h>
#include <unistd.h>

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

using filemover::Event;
using filemover::EventLogOptions;
using filemover::EventSeverity;
using filemover::EventType;
using filemover::format_event;

namespace {

// 2025-08-08T06:33:20.123Z
const std::int64_t kStamp = 1754634800123LL;

std::string read_file(const std::string& path) {
    std::ifstream in(path.c_str());
    std::ostringstream os;
    os << in.rdbuf();
    return os.str();
}

}  // namespace

TEST_CASE("a formatted event leads with an ISO-8601 UTC timestamp",
          "[event_log][L2-CLI-006]") {
    const Event event(EventType::JobCompleted, EventSeverity::Info, kStamp,
                      "job-7", "rec.mp4", "moved");
    const std::string line = format_event(event);

    // Leading, and fixed-width, so `sort` on a merged log is chronological.
    CHECK(line.substr(0, 24) == std::string("2025-08-08T06:33:20.123Z"));
    CHECK(line.find(" INFO ") != std::string::npos);
    CHECK(line.find("job.completed") != std::string::npos);
    CHECK(line.find("job=job-7") != std::string::npos);
    CHECK(line.find("file=rec.mp4") != std::string::npos);
    CHECK(line.find("moved") != std::string::npos);
}

TEST_CASE("absent fields are omitted rather than printed empty",
          "[event_log][L2-CLI-006]") {
    // A service event has no job, and `job=` with nothing after it reads as a
    // job whose id is the empty string.
    const Event event(EventType::ServiceStarted, EventSeverity::Info, kStamp,
                      std::string(), std::string(), "port=8080");
    const std::string line = format_event(event);

    CHECK(line.find("job=") == std::string::npos);
    CHECK(line.find("file=") == std::string::npos);
    CHECK(line.find("port=8080") != std::string::npos);
}

TEST_CASE("the millisecond field is zero-padded", "[event_log][L2-CLI-006]") {
    // 5 ms must render as .005, not .5 -- otherwise the timestamps are not
    // fixed width and sorting them lexically silently stops working.
    const Event event(EventType::JobStarted, EventSeverity::Info, 1000LL * 5 + 5,
                      "job-1", std::string(), std::string());
    const std::string line = format_event(event);
    CHECK(line.substr(0, 24) == std::string("1970-01-01T00:00:05.005Z"));
}

TEST_CASE("a pre-epoch timestamp does not produce a negative field",
          "[event_log][L2-CLI-006]") {
    // A board with a dead RTC comes up before 1970. Truncating division would
    // give a negative millisecond remainder and a second that is one too high.
    const Event event(EventType::JobStarted, EventSeverity::Info, -1LL,
                      "job-1", std::string(), std::string());
    const std::string line = format_event(event);
    CHECK(line.substr(0, 24) == std::string("1969-12-31T23:59:59.999Z"));
}

TEST_CASE("control characters in a value cannot forge a log line",
          "[event_log][L2-CLI-006]") {
    // Paths are attacker-influenced by definition: whoever can create a file
    // chooses its name. A newline in a job or file identifier would end the
    // line and start one the attacker composed -- including a fake ERROR.
    const Event event(EventType::JobFailed, EventSeverity::Error, kStamp,
                      "job-1\nFORGED ERROR line", "a\tb", "x\ry");
    const std::string line = format_event(event);

    CHECK(line.find('\n') == std::string::npos);
    CHECK(line.find('\r') == std::string::npos);
    CHECK(line.find('\t') == std::string::npos);
    CHECK(line.find("\\x0a") != std::string::npos);
    CHECK(line.find("\\x09") != std::string::npos);
    CHECK(line.find("\\x0d") != std::string::npos);
}

// --- level filtering ------------------------------------------------------

TEST_CASE("the configured level is parsed, case-insensitively",
          "[event_log][L2-CLI-006]") {
    EventSeverity level = EventSeverity::Error;
    bool enabled = false;

    REQUIRE(filemover::parse_severity("debug", level, enabled) == true);
    CHECK(level == EventSeverity::Debug);
    CHECK(enabled == true);

    REQUIRE(filemover::parse_severity("Info", level, enabled) == true);
    CHECK(level == EventSeverity::Info);

    REQUIRE(filemover::parse_severity("WARNING", level, enabled) == true);
    CHECK(level == EventSeverity::Warning);

    REQUIRE(filemover::parse_severity("ERROR", level, enabled) == true);
    CHECK(level == EventSeverity::Error);
}

TEST_CASE("OFF disables logging rather than naming a level",
          "[event_log][L2-CLI-006]") {
    EventSeverity level = EventSeverity::Warning;
    bool enabled = true;
    REQUIRE(filemover::parse_severity("off", level, enabled) == true);
    CHECK(enabled == false);
    // Left alone: OFF is the absence of logging, not a level above ERROR, and
    // modelling it as a level invites a comparison against it.
    CHECK(level == EventSeverity::Warning);
}

TEST_CASE("an unrecognised level is refused", "[event_log][L2-CLI-006]") {
    EventSeverity level = EventSeverity::Info;
    bool enabled = true;
    CHECK(filemover::parse_severity("verbose", level, enabled) == false);
    CHECK(filemover::parse_severity("", level, enabled) == false);
}

// --- the stream split (L2-CLI-006) ----------------------------------------

TEST_CASE("INFO goes to stdout and WARNING and above go to stderr",
          "[event_log][L2-CLI-006]") {
    // The requirement's whole point, and not visible in the formatted line --
    // so the real streams are redirected to files and read back.
    //
    // freopen on the actual stdout/stderr rather than a wrapper, because the
    // sink writes to those and a test against an injected stream would be
    // testing a seam that production does not use.
    char out_template[] = "/tmp/fm-log-out-XXXXXX";
    char err_template[] = "/tmp/fm-log-err-XXXXXX";
    const int out_fd = ::mkstemp(out_template);
    const int err_fd = ::mkstemp(err_template);
    REQUIRE(out_fd >= 0);
    REQUIRE(err_fd >= 0);
    ::close(out_fd);
    ::close(err_fd);

    const int saved_out = ::dup(STDOUT_FILENO);
    const int saved_err = ::dup(STDERR_FILENO);
    REQUIRE(saved_out >= 0);
    REQUIRE(saved_err >= 0);

    EventLogOptions options;
    options.minimum = EventSeverity::Debug;

    {
        REQUIRE(std::freopen(out_template, "w", stdout) != 0);
        REQUIRE(std::freopen(err_template, "w", stderr) != 0);

        filemover::log_event(Event(EventType::JobCompleted, EventSeverity::Info,
                                   kStamp, "job-out", std::string(),
                                   std::string()),
                             &options);
        filemover::log_event(Event(EventType::JobFailed, EventSeverity::Error,
                                   kStamp, "job-err", std::string(),
                                   std::string()),
                             &options);
        filemover::log_event(Event(EventType::JobRetryScheduled,
                                   EventSeverity::Warning, kStamp, "job-warn",
                                   std::string(), std::string()),
                             &options);
        (void)std::fflush(stdout);
        (void)std::fflush(stderr);
    }

    // Restore before asserting, or a failure message would go to the temp file.
    (void)::dup2(saved_out, STDOUT_FILENO);
    (void)::dup2(saved_err, STDERR_FILENO);
    ::close(saved_out);
    ::close(saved_err);

    const std::string out = read_file(out_template);
    const std::string err = read_file(err_template);
    ::unlink(out_template);
    ::unlink(err_template);

    CHECK(out.find("job-out") != std::string::npos);
    CHECK(out.find("job-err") == std::string::npos);
    CHECK(out.find("job-warn") == std::string::npos);

    CHECK(err.find("job-err") != std::string::npos);
    CHECK(err.find("job-warn") != std::string::npos);
    CHECK(err.find("job-out") == std::string::npos);
}

TEST_CASE("events below the configured level are dropped",
          "[event_log][L2-CLI-006]") {
    // Asserted through the sink rather than the formatter, because the filter
    // lives in the sink and a formatter test would pass either way.
    char out_template[] = "/tmp/fm-log-lvl-XXXXXX";
    const int out_fd = ::mkstemp(out_template);
    REQUIRE(out_fd >= 0);
    ::close(out_fd);

    const int saved_out = ::dup(STDOUT_FILENO);
    REQUIRE(saved_out >= 0);

    EventLogOptions options;
    options.minimum = EventSeverity::Warning;

    REQUIRE(std::freopen(out_template, "w", stdout) != 0);
    filemover::log_event(Event(EventType::JobStarted, EventSeverity::Info,
                               kStamp, "job-quiet", std::string(),
                               std::string()),
                         &options);
    filemover::log_event(Event(EventType::JobStarted, EventSeverity::Debug,
                               kStamp, "job-quieter", std::string(),
                               std::string()),
                         &options);
    (void)std::fflush(stdout);

    (void)::dup2(saved_out, STDOUT_FILENO);
    ::close(saved_out);

    const std::string out = read_file(out_template);
    ::unlink(out_template);

    CHECK(out.find("job-quiet") == std::string::npos);
    CHECK(out.empty() == true);
}

TEST_CASE("a disabled sink writes nothing at all", "[event_log][L2-CLI-006]") {
    char out_template[] = "/tmp/fm-log-off-XXXXXX";
    const int out_fd = ::mkstemp(out_template);
    REQUIRE(out_fd >= 0);
    ::close(out_fd);

    const int saved_out = ::dup(STDOUT_FILENO);
    const int saved_err = ::dup(STDERR_FILENO);
    REQUIRE(saved_out >= 0);
    REQUIRE(saved_err >= 0);

    EventLogOptions options;
    options.enabled = false;
    options.minimum = EventSeverity::Debug;

    REQUIRE(std::freopen(out_template, "w", stdout) != 0);
    REQUIRE(std::freopen(out_template, "a", stderr) != 0);
    filemover::log_event(Event(EventType::JobFailed, EventSeverity::Error,
                               kStamp, "job-silent", std::string(),
                               std::string()),
                         &options);
    (void)std::fflush(stdout);
    (void)std::fflush(stderr);

    (void)::dup2(saved_out, STDOUT_FILENO);
    (void)::dup2(saved_err, STDERR_FILENO);
    ::close(saved_out);
    ::close(saved_err);

    const std::string out = read_file(out_template);
    ::unlink(out_template);
    CHECK(out.empty() == true);
}

TEST_CASE("a null options pointer is survivable", "[event_log][L2-CLI-006]") {
    // The subscriber signature takes a void*, so nothing in the type system
    // stops a caller passing null. Dropping the event beats dereferencing it.
    filemover::log_event(Event(EventType::JobFailed, EventSeverity::Error,
                               kStamp, "job", std::string(), std::string()),
                         0);
    SUCCEED("no crash");
}
