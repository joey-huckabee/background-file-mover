// Rename template expansion.
// Traces: L3-CPP-042..045

#include "filemover/rename_template.hpp"

#include <cstdio>
#include <ctime>

namespace filemover {
namespace {

// A leading dot is not an extension separator: ".bashrc" is all stem, no ext.
// Without that rule, a dotfile template using {stem} would silently produce an
// empty name, which L3-CPP-044 then rejects — a confusing failure for a
// perfectly ordinary filename.
void split_name(const std::string& name,
                std::string& stem,
                std::string& ext) {
    const std::string::size_type dot = name.rfind('.');
    if (dot == std::string::npos || dot == 0) {
        stem = name;
        ext.clear();
        return;
    }
    stem = name.substr(0, dot);
    ext = name.substr(dot + 1);
}

std::string format_ts(std::int64_t at_ms) {
    // at_ms is caller-supplied; no clock is read here (L3-CPP-045).
    const time_t seconds = static_cast<time_t>(at_ms / 1000);
    const int millis = static_cast<int>(at_ms % 1000);

    struct tm utc;
    if (::gmtime_r(&seconds, &utc) == 0) {
        // Only reachable for a time_t gmtime_r cannot represent. Returning a
        // marker rather than formatting uninitialised tm fields; the result
        // is still a valid filename component, so it fails visibly at the
        // destination rather than corrupting one.
        return std::string("INVALID-TIMESTAMP");
    }

    char buffer[64];
    (void)std::snprintf(buffer, sizeof(buffer),
                        "%04d%02d%02dT%02d%02d%02d.%03d",
                        utc.tm_year + 1900, utc.tm_mon + 1, utc.tm_mday,
                        utc.tm_hour, utc.tm_min, utc.tm_sec, millis);
    return std::string(buffer);
}

std::string format_seq(std::uint64_t sequence) {
    char buffer[64];
    (void)std::snprintf(buffer, sizeof(buffer), "%06llu",
                        static_cast<unsigned long long>(sequence));
    return std::string(buffer);
}

}  // namespace

bool expand_rename_template(const std::string& templ,
                            const std::string& source_name,
                            const RenameContext& context,
                            std::string& out,
                            std::string& error) {
    std::string stem;
    std::string ext;
    split_name(source_name, stem, ext);

    std::string result;
    std::string::size_type pos = 0;

    while (pos < templ.size()) {
        const char c = templ[pos];
        if (c != '{') {
            if (c == '}') {
                error = "stray '}' in rename template";  // L3-CPP-043
                return false;
            }
            result += c;
            ++pos;
            continue;
        }

        const std::string::size_type close = templ.find('}', pos);
        if (close == std::string::npos) {
            error = "unclosed '{' in rename template";  // L3-CPP-043
            return false;
        }

        const std::string field = templ.substr(pos + 1, close - pos - 1);
        if (field == "name") {
            result += source_name;
        } else if (field == "stem") {
            result += stem;
        } else if (field == "ext") {
            result += ext;
        } else if (field == "ts") {
            result += format_ts(context.at_ms);
        } else if (field == "seq") {
            result += format_seq(context.sequence);
        } else {
            error = "unknown rename template field \"{";  // L3-CPP-043
            error += field;
            error += "}\"";
            return false;
        }
        pos = close + 1;
    }

    // L3-CPP-044. Validating the RESULT, not just the template, is what makes
    // directory escape impossible: a template composed entirely of legal
    // fields can still expand to "..", or to something containing '/', if the
    // source filename does.
    if (result.empty() || result == "." || result == "..") {
        error = "rename template expands to an invalid name";
        return false;
    }
    if (result.find('/') != std::string::npos ||
        result.find(static_cast<char>(0)) != std::string::npos) {
        error = "expanded rename target must not contain '/' or NUL";
        return false;
    }

    out = result;
    error.clear();
    return true;
}

}  // namespace filemover
