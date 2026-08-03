// libFuzzer entry point for the HTTP request parser (ADR-0008).
//
// This is the outermost untrusted-input surface in the system: raw bytes off
// a socket, before anything else has looked at them. HTTP framing has a long
// history of smuggling and desync attacks, and the parser is hand-rolled
// because no vendored option works on the deployment toolchain (ADR-0012) —
// so there is no upstream fuzzing corpus backing it. Ours has to.
//
// Compiled by clang; GCC 4.8 can host neither libFuzzer nor LSan. The logic
// is identical because the source is strictly C++11-conformant (ADR-0001).

#include "filemover/http_parser.hpp"

#include <cstddef>
#include <cstdint>
#include <string>

namespace {

const std::size_t kMaxHead = 8192;
const std::uint64_t kMaxBody = 65536;

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data,
                                      std::size_t size) {
    const std::string input(reinterpret_cast<const char*>(data), size);

    // Pre-poisoned so a parser that writes on a failure path trips
    // immediately: L3-CPP-049 requires `out` be untouched unless Ok.
    filemover::http::Request request;
    request.method = "\x01SENTINEL";
    request.target = "\x02SENTINEL";

    std::size_t head_len = 0xDEADBEEF;
    std::string error;

    const filemover::http::HeadParse verdict =
        filemover::http::parse_request_head(input, kMaxHead, request,
                                            head_len, error);

    switch (verdict) {
        case filemover::http::HeadParse::Ok:
            // A parsed head must be internally consistent.
            if (request.method.empty() || request.target.empty()) {
                __builtin_trap();
            }
            if (request.target[0] != '/') {
                __builtin_trap();
            }
            if (head_len > input.size()) {
                __builtin_trap();  // head cannot extend past the input
            }
            break;

        case filemover::http::HeadParse::NeedMore:
            // Incomplete: nothing may have been written.
            if (request.method != "\x01SENTINEL" ||
                request.target != "\x02SENTINEL") {
                __builtin_trap();
            }
            break;

        case filemover::http::HeadParse::Bad:
        case filemover::http::HeadParse::TooLarge:
            if (error.empty()) {
                __builtin_trap();  // rejection needs a diagnosable reason
            }
            if (request.method != "\x01SENTINEL" ||
                request.target != "\x02SENTINEL") {
                __builtin_trap();  // output modified on failure
            }
            break;
    }

    // Second layer: the Content-Length policy, reachable only with a parsed
    // head. Driven from whatever headers the fuzzer managed to produce.
    if (verdict == filemover::http::HeadParse::Ok) {
        std::uint64_t length = 0;
        int status = 0;
        std::string cl_error;
        if (!filemover::http::content_length_for(request, kMaxBody, length,
                                                 status, cl_error)) {
            if (cl_error.empty()) {
                __builtin_trap();
            }
            if (status != 400 && status != 413) {
                __builtin_trap();  // only these two are specified
            }
        } else if (length > kMaxBody) {
            __builtin_trap();  // accepted a body over the cap
        }
    }

    return 0;
}
