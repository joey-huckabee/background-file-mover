#ifndef FILEMOVER_API_CODEC_HPP
#define FILEMOVER_API_CODEC_HPP

// REST API codec boundary.
//
// The JSON parser (filemover/json.hpp) is an implementation detail of
// api_codec.cpp — no other translation unit includes it (L3-CPP-032).
// Everything crossing this boundary is a plain project type, so the parser
// can be replaced without touching a caller. That containment is what made
// swapping picojson out for a project-owned parser a single-file change
// (ADR-0006).
//
// Traces: L2-JSON-001..005, L2-CTL-005, L2-CTL-013

#include <cstdint>
#include <string>
#include <vector>

#include "filemover/job.hpp"

namespace filemover {

struct SubmitRequest {
    std::string source;
    std::string dest;
};

// Parse and validate a POST /api/jobs body.
//
// L3-CPP-025: SHALL accept only a JSON object whose members are exactly
//             "source" and "dest", both non-empty strings.
// L3-CPP-026: SHALL reject unknown members, missing members, wrong types,
//             and non-object top-level values.
// L3-CPP-027: On rejection SHALL return false and populate a non-empty,
//             human-readable error; out SHALL be left unmodified.
// L3-CPP-028: SHALL never terminate the process on malformed input,
//             regardless of size, nesting depth, or byte content.
// L3-CPP-031: SHALL reject a path member longer than PATH_MAX (4096). A
//             longer path cannot be opened, so accepting it only defers the
//             failure to a worse place.
bool decode_submit_request(const std::string& body,
                           SubmitRequest& out,
                           std::string& error);

// Serialize one job / a job collection / an error envelope.
//
// L3-CPP-029: encode_job SHALL emit members id, source, dest, state,
//             created_at_ms, updated_at_ms, finished_at_ms, bytes_total,
//             bytes_moved, error — with state as the to_string token.
// L3-CPP-030: All string members SHALL be JSON-escaped such that the output
//             parses back to the original values.
std::string encode_job(const Job& job);
std::string encode_job_list(const std::vector<Job>& jobs);
std::string encode_error(const std::string& message);

}  // namespace filemover

#endif  // FILEMOVER_API_CODEC_HPP
