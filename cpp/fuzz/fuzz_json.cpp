// libFuzzer entry point for the untrusted-input path (ADR-0008).
//
// Covers both layers from one target, because both consume the same bytes:
// the raw parser, and decode_submit_request on top of it. The codec is the
// entry point a real client reaches, so fuzzing only the parser would leave
// the validation layer — unknown-member rejection, type checks, the path
// bound — untested against hostile input.
//
// This is close to an ideal fuzz target: bytes in, struct out, no I/O, no
// threads, no clock, fully deterministic.
//
// Build and run:  make fuzz && make fuzz-run
//
// This is compiled by clang, not GCC — GCC 4.8 can host neither libFuzzer nor
// LeakSanitizer. The logic under test is identical because the source is
// strictly C++11-conformant and compiled from one body (ADR-0001).

#include "filemover/api_codec.hpp"
#include "filemover/json.hpp"

#include <cstddef>
#include <cstdint>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data,
                                      std::size_t size) {
    const std::string input(reinterpret_cast<const char*>(data), size);

    // --- layer 1: the raw parser -----------------------------------------
    {
        filemover::json::Value value;
        std::string error;

        // The contract under test is not "parses correctly" but "always
        // returns". Any crash, hang, leak, or sanitizer trip is the finding.
        const bool ok = filemover::json::parse(input, value, error);

        if (!ok) {
            // L3-CPP-019: rejection must always carry a diagnosable reason.
            // An empty error would be a silent failure, its own defect.
            if (error.empty()) {
                __builtin_trap();
            }
        } else {
            // L3-CPP-016: success implies a top-level object, since nothing
            // else is accepted. Touch the result so the optimizer cannot
            // discard the parse entirely.
            if (!value.is_object()) {
                __builtin_trap();
            }
        }
    }

    // --- layer 2: the codec, which is what a client actually reaches ------
    {
        // Pre-poisoned so a decoder that writes on the failure path is
        // caught: L3-CPP-027 requires the output be left untouched on any
        // rejection.
        filemover::SubmitRequest request;
        request.source = "\x01sentinel";
        request.dest = "\x02sentinel";
        std::string error;

        const bool ok =
            filemover::decode_submit_request(input, request, error);

        if (!ok) {
            if (error.empty()) {
                __builtin_trap();  // L3-CPP-027: rejection needs a reason
            }
            if (request.source != "\x01sentinel" ||
                request.dest != "\x02sentinel") {
                __builtin_trap();  // L3-CPP-027: output was modified
            }
        } else {
            // L3-CPP-025: acceptance implies both members present and
            // non-empty; L3-CPP-031 bounds their length.
            if (request.source.empty() || request.dest.empty()) {
                __builtin_trap();
            }
            if (request.source.size() > 4096 || request.dest.size() > 4096) {
                __builtin_trap();
            }
        }
    }

    return 0;
}
