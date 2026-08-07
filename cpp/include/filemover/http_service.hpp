#ifndef FILEMOVER_HTTP_SERVICE_HPP
#define FILEMOVER_HTTP_SERVICE_HPP

// C5: the loop that drives one connection through parse, route and reply.
//
// Traces: L2-CTL-002, L2-CTL-004, L2-CTL-005, L2-SEC-009
//
// Deliberately a separate translation unit from router.cpp. The router is a
// pure function of request and manager (L2-CTL-014) and its tests open no
// sockets; keeping the descriptor handling out of that file is what stops the
// boundary eroding one convenience at a time.

#include <cstddef>
#include <cstdint>

#include "filemover/manager.hpp"

namespace filemover {

struct HttpServiceOptions {
    // Head larger than this is 431 (L2-CTL-005). The cap exists so a client
    // cannot make the service buffer without limit before it has said what it
    // wants — the head is read before anything is known about the request.
    std::size_t max_head_bytes;

    // Declared body larger than this is 413, refused WITHOUT reading it.
    // Reading a body in order to reject it is the denial of service the limit
    // exists to prevent.
    std::uint64_t max_body_bytes;

    HttpServiceOptions() : max_head_bytes(8 * 1024),
                           max_body_bytes(64 * 1024) {}
};

// Serves one connection to completion and returns. Does not close `fd` — the
// ConnectionServer owns it.
//
// Answers every input, including the ones it refuses: L2-CTL-004 requires that
// a malformed message never crashes the service, and the way to keep that true
// is to have no path that does anything other than reply and return.
//
// The connection is closed after one response (L2-CTL-002). No keep-alive, no
// pipelining: bytes beyond the declared Content-Length are a 400 rather than
// the start of a second request.
void serve_connection(int fd,
                      const HttpServiceOptions& options,
                      JobManager& manager);

// Exposed for tests: how many bytes the last serve_connection read from the
// socket. The 413 case has to assert that a declared gigabyte was refused
// WITHOUT being read, and a status code alone cannot show that.
std::size_t last_connection_bytes_read();

}  // namespace filemover

#endif  // FILEMOVER_HTTP_SERVICE_HPP
