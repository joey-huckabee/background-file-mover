#ifndef FILEMOVER_API_CODEC_HPP
#define FILEMOVER_API_CODEC_HPP

// M2: JSON codec boundary. The vendored parser (picojson) is an
// implementation detail of api_codec.cpp — no other translation unit may
// include it (L3-CPP-021). Everything crossing this boundary is a plain
// project type.
// Traces: L2-JSON-001..003

#include <string>
#include <vector>

#include "filemover/job.hpp"

namespace filemover {

struct SubmitRequest {
    std::string source;
    std::string dest;
};

// Parse and validate a POST /api/jobs body.
// L3-CPP-016: SHALL accept only a JSON object whose members are exactly
//             "source" and "dest", both non-empty strings.
// L3-CPP-017: SHALL reject unknown members, missing members, wrong types,
//             and non-object top-level values.
// L3-CPP-018: SHALL reject strings containing an embedded NUL character.
// L3-CPP-019: On rejection SHALL return false and populate a non-empty,
//             human-readable error; out SHALL be left unmodified.
// L3-CPP-020: SHALL never terminate the process on malformed input.
// L3-CPP-024: SHALL reject bodies containing non-whitespace bytes after
//             the JSON value (the vendored parser ignores trailing
//             content; the codec enforces whole-body consumption).
bool decode_submit_request(const std::string& body,
                           SubmitRequest& out,
                           std::string& error);

// Serialize one job / a job collection / an error envelope.
// L3-CPP-022: encode_job SHALL emit members id, source, dest, state,
//             created_at_ms, updated_at_ms, finished_at_ms, bytes_total,
//             bytes_moved, error, with state as the to_string token.
// L3-CPP-023: All string members SHALL be JSON-escaped such that the
//             output parses back to the original values.
std::string encode_job(const Job& job);
std::string encode_job_list(const std::vector<Job>& jobs);
std::string encode_error(const std::string& message);

} // namespace filemover

#endif // FILEMOVER_API_CODEC_HPP
