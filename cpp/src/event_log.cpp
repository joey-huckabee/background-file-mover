// C6: the log sink (L2-CLI-006).

#include "filemover/event_log.hpp"

#include <time.h>

#include <cstdio>
#include <string>

namespace filemover {
namespace {

char ascii_upper(char c) {
    // Explicit range, not <cctype> -- see the header. This is the same rule
    // L3-CPP-052 states for the parsers, applied where it also matters.
    if (c >= 'a' && c <= 'z') {
        return static_cast<char>(c - 'a' + 'A');
    }
    return c;
}

std::string upper(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (std::size_t i = 0; i < text.size(); ++i) {
        out.push_back(ascii_upper(text[i]));
    }
    return out;
}

// A value an operator sees; anything that could carry a newline would let a
// path forge a second log line. Paths are attacker-influenced by definition --
// whoever can create a file chooses its name -- so control characters are
// escaped rather than trusted. Same reasoning as L2-DASH-003 for the dashboard.
std::string sanitize(const std::string& value) {
    std::string out;
    out.reserve(value.size());
    for (std::size_t i = 0; i < value.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(value[i]);
        if (c < 0x20 || c == 0x7f) {
            char escape[8];
            (void)std::snprintf(escape, sizeof(escape), "\\x%02x",
                                static_cast<unsigned>(c));
            out += escape;
        } else {
            out.push_back(value[i]);
        }
    }
    return out;
}

}  // namespace

std::string format_event(const Event& event) {
    // Split into whole seconds and the millisecond remainder. floor division,
    // not truncation: a negative epoch value (a clock set before 1970, which
    // does happen on a board with a dead RTC) would otherwise produce a
    // millisecond field of the wrong sign and a time an hour out.
    const std::int64_t ms = event.timestamp_ms();
    std::int64_t seconds = ms / 1000;
    std::int64_t remainder = ms % 1000;
    if (remainder < 0) {
        remainder += 1000;
        seconds -= 1;
    }

    const time_t as_time = static_cast<time_t>(seconds);
    struct tm parts;
    std::string stamp;
    if (::gmtime_r(&as_time, &parts) != 0) {
        // Sized for the worst case the compiler can prove rather than the one
        // that occurs: tm_year is an int, so -Wformat-truncation reasons about
        // an 11-digit year. 64 costs nothing on the stack and keeps -Werror.
        char buffer[64];
        // Formatted by hand rather than with strftime, which consults the
        // locale for field widths and separators in some implementations.
        (void)std::snprintf(buffer, sizeof(buffer),
                            "%04d-%02d-%02dT%02d:%02d:%02d.%03ldZ",
                            parts.tm_year + 1900, parts.tm_mon + 1,
                            parts.tm_mday, parts.tm_hour, parts.tm_min,
                            parts.tm_sec, static_cast<long>(remainder));
        stamp = buffer;
    } else {
        // Effectively unreachable for a valid time_t, but a plausible-looking
        // date would be worse than an obviously broken one: the raw value is
        // printed so nothing is silently invented.
        // Sized for the worst case the compiler can prove rather than the one
        // that occurs: tm_year is an int, so -Wformat-truncation reasons about
        // an 11-digit year. 64 costs nothing on the stack and keeps -Werror.
        char buffer[64];
        (void)std::snprintf(buffer, sizeof(buffer), "epoch_ms=%lld",
                            static_cast<long long>(ms));
        stamp = buffer;
    }

    std::string line = stamp;
    line += " ";
    line += to_string(event.severity());
    line += " ";
    line += to_string(event.type());

    if (event.has_job_id()) {
        line += " job=";
        line += sanitize(event.job_id());
    }
    if (event.has_file_id()) {
        line += " file=";
        line += sanitize(event.file_id());
    }
    if (!event.detail().empty()) {
        line += " ";
        line += sanitize(event.detail());
    }
    return line;
}

void log_event(const Event& event, void* user_data) {
    const EventLogOptions* options =
        static_cast<const EventLogOptions*>(user_data);
    if (options == 0 || !options->enabled) {
        return;
    }
    if (!severity_at_least(event.severity(), options->minimum)) {
        return;
    }

    // L2-CLI-006: DEBUG and INFO to stdout, WARNING and above to stderr.
    std::FILE* stream =
        severity_at_least(event.severity(), EventSeverity::Warning) ? stderr
                                                                    : stdout;

    const std::string line = format_event(event);
    (void)std::fprintf(stream, "%s\n", line.c_str());
    (void)std::fflush(stream);
}

bool parse_severity(const std::string& text,
                    EventSeverity& minimum,
                    bool& enabled) {
    const std::string value = upper(text);
    if (value == "OFF") {
        enabled = false;
        return true;
    }

    enabled = true;
    if (value == "DEBUG") {
        minimum = EventSeverity::Debug;
    } else if (value == "INFO") {
        minimum = EventSeverity::Info;
    } else if (value == "WARNING") {
        minimum = EventSeverity::Warning;
    } else if (value == "ERROR") {
        minimum = EventSeverity::Error;
    } else {
        return false;
    }
    return true;
}

}  // namespace filemover
