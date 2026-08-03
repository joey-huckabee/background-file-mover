#ifndef FILEMOVER_HTTP_PARSER_HPP
#define FILEMOVER_HTTP_PARSER_HPP

// HTTP/1.1 request parsing and response serialization — pure functions.
//
// This header holds the PARSER ONLY. Route handling and the socket server
// live elsewhere and arrive with the job manager: a parser that forces its
// consumers to include the configuration and the job manager is doing more
// than one job (docs/HAND-ROLLED-COMPONENTS.md §1.2).
//
// Hand-rolled because cpp-httplib is unusable on the deployment toolchain —
// it routes with std::regex, unimplemented in libstdc++ before GCC 4.9
// (ADR-0012).
//
// Traces: L2-CTL-002, L2-CTL-003, L2-CTL-005, L2-CTL-015
//
// Accepted subset (ADR-0002):
//   GET and POST, Content-Length bodies only, Connection: close.
// Refused by design:
//   any Transfer-Encoding, obs-fold headers, duplicate headers, oversized
//   heads and bodies, bytes beyond the declared Content-Length.

#include <cstddef>
#include <cstdint>
#include <map>
#include <string>

namespace filemover {
namespace http {

struct Request {
    std::string method;   // verbatim token, uppercase A-Z
    std::string target;   // starts with '/'
    std::string version;  // "HTTP/1.0" or "HTTP/1.1"
    std::map<std::string, std::string> headers;  // names lowercased
    std::string body;
};

struct Response {
    int status;
    std::string content_type;
    std::string body;
    std::string allow;  // emitted as Allow when non-empty

    Response() : status(500), content_type("application/json") {}
};

enum class HeadParse {
    Ok,        // head complete and valid; head_len set
    NeedMore,  // no CRLFCRLF yet, and the cap is not yet exceeded
    Bad,       // malformed -> 400
    TooLarge   // head exceeds the cap -> 431
};

// Parse the request head from `data`, which may contain body bytes after the
// blank line.
//
// L3-CPP-046: the request line SHALL be METHOD SP target SP version CRLF,
//             with METHOD 1..16 characters of [A-Z], target beginning '/'
//             and free of whitespace and control characters, and version
//             exactly HTTP/1.0 or HTTP/1.1.
// L3-CPP-047: headers SHALL be `name: value` with token names lowercased on
//             output and values OWS-trimmed and free of control characters.
//             obs-fold continuation lines SHALL be rejected. More than 64
//             headers SHALL be rejected. A duplicate header name SHALL be
//             rejected.
// L3-CPP-048: absence of CRLFCRLF within `max_head` SHALL yield TooLarge.
// L3-CPP-049: any proper prefix of a valid head SHALL yield NeedMore, and
//             `out` SHALL be left unmodified except on Ok.
HeadParse parse_request_head(const std::string& data,
                             std::size_t max_head,
                             Request& out,
                             std::size_t& head_len,
                             std::string& error);

// Determine the body length a request declares.
//
// L3-CPP-050: an absent Content-Length SHALL mean zero. A present value SHALL
//             be strict base-10 digits consuming the whole token. Any
//             Transfer-Encoding SHALL be rejected with 400. A value above
//             `max_body` SHALL be rejected with 413.
bool content_length_for(const Request& request,
                        std::uint64_t max_body,
                        std::uint64_t& length,
                        int& http_status,
                        std::string& error);

// L3-CPP-051: a serialized response SHALL carry the status line, Content-Type,
//             Content-Length, Connection: close, an Allow header when the
//             response supplies one, CRLF framing throughout, then the body.
std::string serialize_response(const Response& response);

}  // namespace http
}  // namespace filemover

#endif  // FILEMOVER_HTTP_PARSER_HPP
