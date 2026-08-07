// C5: the loop that drives one connection through parse, route and reply.
// Traces: L2-CTL-002, L2-CTL-004, L2-CTL-005, L2-SEC-009

#include "filemover/http_service.hpp"

#include <string>

#include "filemover/api_codec.hpp"
#include "filemover/http_parser.hpp"
#include "filemover/router.hpp"
#include "filemover/server.hpp"

namespace filemover {
namespace {

// Per-thread, because handlers run concurrently and a shared counter would be
// both a race and a meaningless number.
thread_local std::size_t g_bytes_read = 0;

http::Response refusal(int status, const std::string& message) {
    http::Response r;
    r.status = status;
    r.body = encode_error(message);
    return r;
}

// Writes the response and returns. A failed write is not worth reporting
// anywhere: the client is gone, the connection is about to close, and there is
// no second channel on which to complain.
void reply(int fd, const http::Response& response) {
    const std::string wire = http::serialize_response(response);
    (void)write_all(fd, wire.data(), wire.size());
}

}  // namespace

std::size_t last_connection_bytes_read() { return g_bytes_read; }

void serve_connection(int fd,
                      const HttpServiceOptions& options,
                      JobManager& manager) {
    g_bytes_read = 0;

    std::string buffer;
    http::Request request;
    std::size_t head_len = 0;
    std::string parse_error;

    // --- the head ---------------------------------------------------------
    //
    // Read until the parser says it has a whole head, it is malformed, or it
    // is over the cap. The cap is enforced by the parser on what has arrived
    // so far, so a client that never sends CRLFCRLF is stopped by the limit
    // rather than by running the process out of memory.
    for (;;) {
        const http::HeadParse state = http::parse_request_head(
            buffer, options.max_head_bytes, request, head_len, parse_error);

        if (state == http::HeadParse::Ok) {
            break;
        }
        if (state == http::HeadParse::Bad) {
            reply(fd, refusal(400, parse_error));
            return;
        }
        if (state == http::HeadParse::TooLarge) {
            reply(fd, refusal(431, "request head exceeds the permitted size"));
            return;
        }

        char chunk[2048];
        std::size_t got = 0;
        const IoResult r = read_some(fd, chunk, sizeof(chunk), got);
        if (r != IoResult::Ok) {
            // Timed out, closed, or failed with nothing usable. There is no
            // request to answer, so nothing is sent: replying 400 to a client
            // that has already gone is writing into a closed socket, and
            // replying to a stall rewards it with a response it never read.
            return;
        }
        g_bytes_read += got;
        buffer.append(chunk, got);
    }

    // --- the declared body size -------------------------------------------
    //
    // content_length_for supplies the status: 413 when the declaration exceeds
    // the cap, 400 for chunked (L2-CTL-002 forbids it) or an unparseable
    // length. This happens BEFORE any body byte is read, which is the whole
    // point -- reading a gigabyte in order to reject it is the denial of
    // service the cap exists to prevent.
    std::uint64_t declared = 0;
    int status = 0;
    std::string length_error;
    if (!http::content_length_for(request, options.max_body_bytes, declared,
                                  status, length_error)) {
        reply(fd, refusal(status, length_error));
        return;
    }

    // --- the body ---------------------------------------------------------
    const std::size_t have = buffer.size() - head_len;
    if (have > declared) {
        // Bytes past the declared length. No pipelining and no smuggled second
        // request: a server that treats the surplus as another request lets a
        // client desynchronise it from any proxy in front of it.
        reply(fd, refusal(400, "unexpected bytes after the declared body"));
        return;
    }

    std::size_t remaining = static_cast<std::size_t>(declared) - have;
    while (remaining > 0) {
        char chunk[4096];
        const std::size_t want =
            (remaining < sizeof(chunk)) ? remaining : sizeof(chunk);
        std::size_t got = 0;
        const IoResult r = read_some(fd, chunk, want, got);
        if (r != IoResult::Ok) {
            // A body shorter than declared is the client's error, and it is
            // worth answering: unlike the head case there IS a parsed request,
            // so the client learns what was wrong with it.
            reply(fd, refusal(400, "body shorter than the declared length"));
            return;
        }
        g_bytes_read += got;
        buffer.append(chunk, got);
        remaining -= got;
    }
    request.body = buffer.substr(head_len, static_cast<std::size_t>(declared));

    reply(fd, route_request(request, manager));
}

}  // namespace filemover
