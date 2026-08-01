// libFuzzer entry point for the strict-subset JSON parser (ADR-0008).
//
// The parser is close to an ideal fuzz target: bytes in, struct out, no I/O,
// no threads, no clock, fully deterministic. Everything interesting is
// reachable from this one function.
//
// Build and run:  make fuzz && make fuzz-run
//
// This is compiled by clang, not GCC — GCC 4.8 can host neither libFuzzer nor
// LeakSanitizer. The logic under test is identical because the source is
// strictly C++11-conformant and compiled from one body (ADR-0001).

#include "filemover/json.hpp"

#include <cstddef>
#include <cstdint>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data,
                                      std::size_t size) {
    const std::string input(reinterpret_cast<const char*>(data), size);

    filemover::json::Value value;
    std::string error;

    // The contract under test is not "parses correctly" but "always returns".
    // Any crash, hang, leak, or sanitizer trip is the finding.
    const bool ok = filemover::json::parse(input, value, error);

    if (!ok) {
        // L3-CPP-019: rejection must always carry a diagnosable reason. An
        // empty error would be a silent failure, which is its own defect.
        if (error.empty()) {
            __builtin_trap();
        }
    } else {
        // L3-CPP-016: success implies a top-level object, since nothing else
        // is accepted. Touch the result so the optimizer cannot discard the
        // parse entirely.
        if (!value.is_object()) {
            __builtin_trap();
        }
    }

    return 0;
}
