#include "filemover/api_codec.hpp"

#define PICOJSON_USE_INT64
#include <picojson/picojson.h>

namespace filemover {

namespace {

bool contains_nul(const std::string& s) {
    return s.find('\0') != std::string::npos;
}

// Validate one required non-empty string member. Returns false with a
// message on any violation.
bool require_string(const picojson::object& obj,
                    const char* key,
                    std::string& value,
                    std::string& error) {
    picojson::object::const_iterator it = obj.find(key);
    if (it == obj.end()) {
        error = std::string("missing required member \"") + key + "\"";
        return false;
    }
    if (!it->second.is<std::string>()) {
        error = std::string("member \"") + key + "\" must be a string";
        return false;
    }
    const std::string& s = it->second.get<std::string>();
    if (s.empty()) {
        error = std::string("member \"") + key + "\" must be non-empty";
        return false;
    }
    if (contains_nul(s)) {                          // L3-CPP-018
        error = std::string("member \"") + key +
                "\" contains an embedded NUL character";
        return false;
    }
    value = s;
    return true;
}

} // namespace

bool decode_submit_request(const std::string& body,
                           SubmitRequest& out,
                           std::string& error) {
    picojson::value root;
    std::string parse_err;
    std::string::const_iterator rest =
        picojson::parse(root, body.begin(), body.end(), &parse_err);
    if (!parse_err.empty()) {                       // L3-CPP-019/020
        error = "malformed JSON: " + parse_err;
        return false;
    }
    // L3-CPP-024: picojson stops at the end of the first JSON value and
    // ignores trailing bytes (pinned by characterization test); the codec
    // enforces whole-body consumption itself.
    for (; rest != body.end(); ++rest) {
        const char c = *rest;
        if (c != ' ' && c != '\t' && c != '\n' && c != '\r') {
            error = "trailing content after JSON value";
            return false;
        }
    }
    if (!root.is<picojson::object>()) {             // L3-CPP-017
        error = "request body must be a JSON object";
        return false;
    }
    const picojson::object& obj = root.get<picojson::object>();

    for (picojson::object::const_iterator it = obj.begin();
         it != obj.end(); ++it) {                   // L3-CPP-017: unknowns
        if (it->first != "source" && it->first != "dest") {
            error = "unknown member \"" + it->first + "\"";
            return false;
        }
    }

    SubmitRequest parsed;                           // L3-CPP-019: out
    if (!require_string(obj, "source", parsed.source, error)) {
        return false;                               //   untouched on error
    }
    if (!require_string(obj, "dest", parsed.dest, error)) {
        return false;
    }
    out = parsed;
    return true;
}

namespace {

picojson::value job_to_value(const Job& job) {
    picojson::object o;
    o["id"] = picojson::value(job.id);
    o["source"] = picojson::value(job.source_path);
    o["dest"] = picojson::value(job.dest_path);
    o["state"] = picojson::value(std::string(to_string(job.state)));
    o["created_at_ms"] = picojson::value(job.created_at_ms);
    o["updated_at_ms"] = picojson::value(job.updated_at_ms);
    o["finished_at_ms"] = picojson::value(job.finished_at_ms);
    o["bytes_total"] =
        picojson::value(static_cast<std::int64_t>(job.bytes_total));
    o["bytes_moved"] =
        picojson::value(static_cast<std::int64_t>(job.bytes_moved));
    o["error"] = picojson::value(job.error);
    return picojson::value(o);
}

} // namespace

std::string encode_job(const Job& job) {
    return job_to_value(job).serialize();
}

std::string encode_job_list(const std::vector<Job>& jobs) {
    picojson::array arr;
    arr.reserve(jobs.size());
    for (std::vector<Job>::const_iterator it = jobs.begin();
         it != jobs.end(); ++it) {
        arr.push_back(job_to_value(*it));
    }
    picojson::object o;
    o["jobs"] = picojson::value(arr);
    return picojson::value(o).serialize();
}

std::string encode_error(const std::string& message) {
    picojson::object o;
    o["error"] = picojson::value(message);
    return picojson::value(o).serialize();
}

} // namespace filemover
