// REST API codec. The only translation unit that includes the JSON parser
// (L3-CPP-032).
//
// Traces: L2-JSON-001..005, L2-CTL-005, L2-CTL-013

#include "filemover/api_codec.hpp"

#include "filemover/json.hpp"

#include <cstdio>
#include <limits>

namespace filemover {
namespace {

// PATH_MAX on Linux is 4096 including the terminating NUL, so a longer path
// cannot be opened. Rejecting it here keeps the failure at the boundary,
// where the error message can still say something useful, instead of
// deferring it to an ENAMETOOLONG deep in the transfer stage.
const std::size_t kMaxPathBytes = 4096;

// Limits tuned for this API rather than the parser's general defaults. The
// submit body is a flat object of two strings; nothing else needs to be
// representable, so nothing else is allowed.
json::Limits submit_limits() {
    json::Limits limits;
    limits.max_depth = 2;              // the top-level object, and nothing under it
    limits.max_input_bytes = static_cast<std::size_t>(16) * 1024;
    limits.max_string_bytes = kMaxPathBytes;
    limits.max_members = 8;            // 2 expected; the rest is slack for a clear error
    limits.max_elements = 8;
    return limits;
}

// Extracts a required non-empty string member.
bool require_string(const json::Value& object,
                    const char* name,
                    std::string& out,
                    std::string& error) {
    const json::Value* member = object.find(name);
    if (member == 0) {
        error = std::string("missing required member \"") + name + "\"";
        return false;
    }
    if (!member->is_string()) {
        error = std::string("member \"") + name + "\" must be a string";
        return false;
    }
    if (member->as_string().empty()) {
        error = std::string("member \"") + name + "\" must not be empty";
        return false;
    }
    // Redundant with the parser's max_string_bytes, deliberately. The bound
    // that matters is a property of the API, not of whatever limits happen
    // to be configured, and it should not silently relax if those change.
    if (member->as_string().size() > kMaxPathBytes) {
        error = std::string("member \"") + name + "\" exceeds the maximum path length";
        return false;
    }
    out = member->as_string();
    return true;
}

void append_string_member(std::string& out,
                          const char* name,
                          const std::string& value,
                          bool trailing_comma) {
    out += '"';
    out += name;
    out += "\":\"";
    out += json::escape(value);
    out += '"';
    if (trailing_comma) out += ',';
}

void append_int(std::string& out, std::int64_t value) {
    char buf[32];
    (void)std::snprintf(buf, sizeof(buf), "%lld",
                        static_cast<long long>(value));
    out += buf;
}

void append_int_member(std::string& out,
                       const char* name,
                       std::int64_t value,
                       bool trailing_comma) {
    out += '"';
    out += name;
    out += "\":";
    append_int(out, value);
    if (trailing_comma) out += ',';
}

// Job byte counters are uint64; JSON integers are int64 (ADR-0009). Values
// above int64 max are not representable and would wrap to negative, so they
// are clamped. The threshold is ~9.2 exabytes in a single job, which is not
// a real transfer — but a wrapped negative byte count in an operator
// dashboard is a bug report, and clamping is not.
std::int64_t to_int64_clamped(std::uint64_t value) {
    const std::uint64_t max =
        static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (value > max) return std::numeric_limits<std::int64_t>::max();
    return static_cast<std::int64_t>(value);
}

}  // namespace

bool decode_submit_request(const std::string& body,
                           SubmitRequest& out,
                           std::string& error) {
    json::Value root;
    if (!json::parse(body, root, error, submit_limits())) {
        return false;  // parse() guarantees a non-empty error (L3-CPP-019)
    }
    // parse() already guarantees an object top level, but the codec does not
    // rely on that: this boundary states its own contract.
    if (!root.is_object()) {
        error = "request body must be a JSON object";
        return false;
    }

    // Unknown members are rejected rather than ignored. A client sending
    // {"source", "dest", "overwrite": true} has a belief about the request
    // that the server does not share; silently dropping it is how that turns
    // into data loss rather than a 400.
    const std::vector<json::Member>& members = root.as_object();
    for (std::size_t i = 0; i < members.size(); ++i) {
        const std::string& key = members[i].key;
        if (key != "source" && key != "dest") {
            error = "unknown member \"" + json::escape(key) + "\"";
            return false;
        }
    }

    // Both are extracted into locals first, so `out` is untouched unless the
    // whole request validates (L3-CPP-027).
    std::string source;
    std::string dest;
    if (!require_string(root, "source", source, error)) return false;
    if (!require_string(root, "dest", dest, error)) return false;

    out.source = source;
    out.dest = dest;
    error.clear();
    return true;
}

std::string encode_job(const Job& job) {
    std::string out;
    out.reserve(256);
    out += '{';
    append_string_member(out, "id", job.id, true);
    append_string_member(out, "source", job.source_path, true);
    append_string_member(out, "dest", job.dest_path, true);
    append_string_member(out, "state", to_string(job.state), true);
    append_int_member(out, "created_at_ms", job.created_at_ms, true);
    append_int_member(out, "updated_at_ms", job.updated_at_ms, true);
    append_int_member(out, "finished_at_ms", job.finished_at_ms, true);
    append_int_member(out, "bytes_total", to_int64_clamped(job.bytes_total), true);
    append_int_member(out, "bytes_moved", to_int64_clamped(job.bytes_moved), true);
    append_string_member(out, "error", job.error, false);
    out += '}';
    return out;
}

std::string encode_job_list(const std::vector<Job>& jobs) {
    // Wrapped in an object rather than returned as a bare array: a top-level
    // array cannot gain a sibling field later without breaking every client,
    // and paging metadata is the obvious thing to want next.
    std::string out = "{\"jobs\":[";
    for (std::size_t i = 0; i < jobs.size(); ++i) {
        if (i != 0) out += ',';
        out += encode_job(jobs[i]);
    }
    out += "]}";
    return out;
}

std::string encode_status(const JobManager::StatusSnapshot& snapshot,
                          std::size_t limit) {
    std::string out;
    out.reserve(1024);
    out += '{';
    out += "\"running\":";
    out += snapshot.running ? "true" : "false";
    out += ',';
    append_int_member(out, "runnable",
                      to_int64_clamped(
                          static_cast<std::uint64_t>(snapshot.runnable)),
                      true);
    append_int_member(out, "active",
                      to_int64_clamped(
                          static_cast<std::uint64_t>(snapshot.active)),
                      true);

    // Keyed by the SAME uppercase token to_string(JobState) produces, which is
    // what the page indexes its counters by. Two spellings of a state -- one
    // for the API and one for the display -- is how a counter reads zero
    // forever and nobody notices.
    out += "\"counts\":{";
    bool first = true;
    for (std::map<JobState, std::uint64_t>::const_iterator it =
             snapshot.counts.begin();
         it != snapshot.counts.end(); ++it) {
        if (!first) out += ',';
        first = false;
        out += '"';
        out += json::escape(to_string(it->first));
        out += "\":";
        append_int(out, to_int64_clamped(it->second));
    }
    out += "},";

    // The cap is reported rather than left implicit. A dashboard showing 50
    // rows of 4,000 jobs without saying so lies about the size of the backlog.
    append_int_member(out, "limit",
                      to_int64_clamped(static_cast<std::uint64_t>(limit)),
                      true);
    out += "\"truncated\":";
    out += (limit > 0 && snapshot.jobs.size() >= limit) ? "true" : "false";

    out += ",\"jobs\":[";
    for (std::size_t i = 0; i < snapshot.jobs.size(); ++i) {
        if (i != 0) out += ',';
        out += encode_job(snapshot.jobs[i]);
    }
    out += "]}";
    return out;
}

std::string encode_error(const std::string& message) {
    std::string out = "{\"error\":\"";
    out += json::escape(message);
    out += "\"}";
    return out;
}

}  // namespace filemover
