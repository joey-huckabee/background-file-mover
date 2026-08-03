// HTTP/1.1 request parser tests.
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L3-CPP-046..052
//
// Predominantly a rejection suite, per docs/HAND-ROLLED-COMPONENTS.md §2.2.
// All five obligatory properties of §2.3 are asserted: prefix sweep, output
// unmodified on failure, non-empty error on rejection, arbitrary bytes
// return rather than terminate, and every bound has a test that trips it.

#include "catch2/catch.hpp"

#include "filemover/http_parser.hpp"

#include <clocale>
#include <cstdio>
#include <string>

using filemover::http::HeadParse;
using filemover::http::Request;
using filemover::http::Response;

namespace {

const std::size_t kMaxHead = 8192;
const std::uint64_t kMaxBody = 65536;

const char* kValidHead =
    "POST /api/jobs HTTP/1.1\r\n"
    "Host: localhost\r\n"
    "Content-Length: 2\r\n"
    "\r\n";

HeadParse parse(const std::string& data,
                Request& out,
                std::size_t& head_len,
                std::string& error) {
    return filemover::http::parse_request_head(data, kMaxHead, out, head_len,
                                               error);
}

// Returns the verdict, asserting the shared contract on every rejection:
// non-empty error, and `out` untouched (L3-CPP-049).
HeadParse verdict(const std::string& data) {
    Request out;
    out.method = "SENTINEL";
    out.target = "/sentinel";
    std::size_t head_len = 12345;
    std::string error;

    const HeadParse r = parse(data, out, head_len, error);
    if (r != HeadParse::Ok) {
        CHECK(out.method == std::string("SENTINEL"));
        CHECK(out.target == std::string("/sentinel"));
        if (r != HeadParse::NeedMore) {
            CHECK(error.empty() == false);
        }
    }
    return r;
}

bool bad(const std::string& data) { return verdict(data) == HeadParse::Bad; }

}  // namespace

TEST_CASE("parses a well-formed request head", "[http][L3-CPP-046]") {
    Request req;
    std::size_t head_len = 0;
    std::string error;

    REQUIRE(parse(kValidHead, req, head_len, error) == HeadParse::Ok);
    CHECK(error.empty() == true);
    CHECK(req.method == std::string("POST"));
    CHECK(req.target == std::string("/api/jobs"));
    CHECK(req.version == std::string("HTTP/1.1"));
    CHECK(head_len == std::string(kValidHead).size());
    CHECK(req.headers.size() == 2u);
    CHECK(req.headers.at("host") == std::string("localhost"));
}

TEST_CASE("header names are lowercased and values OWS-trimmed",
          "[http][L3-CPP-047]") {
    Request req;
    std::size_t head_len = 0;
    std::string error;
    const std::string data =
        "GET / HTTP/1.1\r\n"
        "HOST:   Example.COM   \r\n"
        "X-Mixed-Case:\tvalue\t\r\n"
        "\r\n";

    REQUIRE(parse(data, req, head_len, error) == HeadParse::Ok);
    CHECK(req.headers.count("host") == 1u);
    CHECK(req.headers.count("HOST") == 0u);
    // The value keeps its case; only the name is normalized.
    CHECK(req.headers.at("host") == std::string("Example.COM"));
    CHECK(req.headers.at("x-mixed-case") == std::string("value"));
}

TEST_CASE("header parsing does not depend on the process locale",
          "[http][L3-CPP-052]") {
    // Classification uses explicit ranges rather than <cctype>, which is
    // locale-sensitive. The concrete hazard is Turkish: `std::tolower('I')`
    // under tr_TR does not yield 'i' — the Turkish lowercase of I is dotless
    // 'ı', which is not representable in one byte, so the call returns 'I'
    // unchanged. A locale-sensitive parser would key this header under
    // "iF-mATCH" instead of "if-match" and every lookup would miss.
    //
    // The input therefore has to contain a capital 'I' in a header name, or
    // the test passes for the wrong reason. kValidHead does not.
    const std::string data =
        "GET / HTTP/1.1\r\n"
        "IF-MATCH: \"tag\"\r\n"
        "CONTENT-LENGTH: 0\r\n"
        "\r\n";

    const char* saved = std::setlocale(LC_ALL, NULL);
    const std::string previous(saved != NULL ? saved : "C");

    std::setlocale(LC_ALL, "C");
    Request a;
    std::size_t la = 0;
    std::string ea;
    const HeadParse ra = parse(data, a, la, ea);

    // When the locale is not generated on this machine setlocale returns NULL
    // and leaves the locale alone. Say so, rather than reporting a pass that
    // only re-ran the "C" case.
    const bool turkish = std::setlocale(LC_ALL, "tr_TR.UTF-8") != NULL;
    Request b;
    std::size_t lb = 0;
    std::string eb;
    const HeadParse rb = parse(data, b, lb, eb);

    std::setlocale(LC_ALL, previous.c_str());

    if (!turkish) {
        WARN("tr_TR.UTF-8 unavailable; locale independence was inspected, "
             "not executed (L3-CPP-052 verification I)");
    }

    CHECK(ra == HeadParse::Ok);
    CHECK(rb == HeadParse::Ok);
    CHECK(a.headers.at("if-match") == std::string("\"tag\""));
    CHECK(b.headers.at("if-match") == std::string("\"tag\""));
    CHECK(b.headers.count("iF-mATCH") == 0u);
    CHECK(a.headers.at("content-length") == b.headers.at("content-length"));
    CHECK(a.method == b.method);
}

TEST_CASE("every proper prefix of a valid head yields NeedMore",
          "[http][L3-CPP-049]") {
    // The property that makes a streaming parser safe: no prefix is ever
    // accepted, and none is misreported as malformed.
    const std::string valid(kValidHead);
    for (std::size_t i = 0; i < valid.size(); ++i) {
        INFO("prefix length " << i);
        CHECK(verdict(valid.substr(0, i)) == HeadParse::NeedMore);
    }
    CHECK(verdict(valid) == HeadParse::Ok);
}

TEST_CASE("malformed request lines are rejected", "[http][L3-CPP-046]") {
    CHECK(bad("GET /\r\n\r\n") == true);                        // two fields
    CHECK(bad("GET / HTTP/1.1 extra\r\n\r\n") == true);         // four fields
    CHECK(bad("get / HTTP/1.1\r\n\r\n") == true);               // lowercase
    CHECK(bad("G3T / HTTP/1.1\r\n\r\n") == true);               // non-alpha
    CHECK(bad("VERYLONGMETHODNAME / HTTP/1.1\r\n\r\n") == true);
    CHECK(bad("GET api/jobs HTTP/1.1\r\n\r\n") == true);        // no leading /
    CHECK(bad("GET / HTTP/2.0\r\n\r\n") == true);
    CHECK(bad("\r\n\r\n") == true);                             // empty line
}

TEST_CASE("bare-LF framing is NeedMore, not Bad", "[http][L3-CPP-049]") {
    // Not a malformed head — an INCOMPLETE one. The parser looks for
    // CRLFCRLF, which bare LF never produces, so the request simply never
    // completes and the head cap (L3-CPP-048) or the socket timeout ends it.
    //
    // Rejecting it as Bad would be wrong in a subtle way: it would mean
    // treating "I have not seen the terminator yet" as "this can never be
    // valid", which is the judgement a streaming parser is not entitled to
    // make on a prefix.
    CHECK(verdict("GET / HTTP/1.1\n\n") == HeadParse::NeedMore);
    CHECK(verdict("GET / HTTP/1.1\nHost: a\n\n") == HeadParse::NeedMore);

    // And it is bounded rather than accepted: past the cap it becomes
    // TooLarge, so bare-LF cannot hold a connection open indefinitely.
    std::string over = "GET / HTTP/1.1\n";
    over += std::string(kMaxHead, 'x');
    over += "\n\n";
    CHECK(verdict(over) == HeadParse::TooLarge);
}

TEST_CASE("control characters and whitespace in the target are rejected",
          "[http][L3-CPP-046]") {
    std::string with_ctl = "GET /a";
    with_ctl.push_back('\x01');
    with_ctl += " HTTP/1.1\r\n\r\n";
    CHECK(bad(with_ctl) == true);

    std::string with_nul = "GET /a";
    with_nul.push_back('\0');
    with_nul += " HTTP/1.1\r\n\r\n";
    CHECK(bad(with_nul) == true);
}

TEST_CASE("duplicate headers are rejected", "[http][L3-CPP-047]") {
    // A map assignment would take the last value. Two parties disagreeing
    // about which duplicate wins is how request smuggling works.
    CHECK(bad("GET / HTTP/1.1\r\nContent-Length: 1\r\n"
              "Content-Length: 2\r\n\r\n") == true);
    // Case-insensitive: the names collide after lowercasing.
    CHECK(bad("GET / HTTP/1.1\r\nHost: a\r\nHOST: b\r\n\r\n") == true);
    // Distinct names are fine.
    CHECK(verdict("GET / HTTP/1.1\r\nHost: a\r\nAccept: b\r\n\r\n") ==
          HeadParse::Ok);
}

TEST_CASE("obs-fold continuation lines are rejected", "[http][L3-CPP-047]") {
    CHECK(bad("GET / HTTP/1.1\r\nHost: a\r\n obs-folded\r\n\r\n") == true);
    CHECK(bad("GET / HTTP/1.1\r\nHost: a\r\n\tobs-folded\r\n\r\n") == true);
}

TEST_CASE("malformed headers are rejected", "[http][L3-CPP-047]") {
    CHECK(bad("GET / HTTP/1.1\r\nNoColonHere\r\n\r\n") == true);
    CHECK(bad("GET / HTTP/1.1\r\n: emptyname\r\n\r\n") == true);
    CHECK(bad("GET / HTTP/1.1\r\nBad Name: v\r\n\r\n") == true);
    CHECK(bad("GET / HTTP/1.1\r\nBad(Name): v\r\n\r\n") == true);

    std::string ctl_value = "GET / HTTP/1.1\r\nHost: a";
    ctl_value.push_back('\x01');
    ctl_value += "b\r\n\r\n";
    CHECK(bad(ctl_value) == true);
}

TEST_CASE("the header count is bounded", "[http][L3-CPP-047]") {
    std::string head = "GET / HTTP/1.1\r\n";
    for (int i = 0; i < 64; ++i) {
        char name[32];
        (void)std::snprintf(name, sizeof(name), "h%d", i);
        head += name;
        head += ": v\r\n";
    }
    head += "\r\n";
    CHECK(verdict(head) == HeadParse::Ok);  // exactly 64 is allowed

    std::string over = "GET / HTTP/1.1\r\n";
    for (int i = 0; i < 65; ++i) {
        char name[32];
        (void)std::snprintf(name, sizeof(name), "h%d", i);
        over += name;
        over += ": v\r\n";
    }
    over += "\r\n";
    CHECK(bad(over) == true);
}

TEST_CASE("the head size is bounded", "[http][L3-CPP-048]") {
    // No terminator, over the cap -> TooLarge rather than NeedMore forever.
    const std::string huge(kMaxHead + 1, 'x');
    CHECK(verdict(huge) == HeadParse::TooLarge);

    // Under the cap and unterminated is still NeedMore.
    const std::string small(64, 'x');
    CHECK(verdict(small) == HeadParse::NeedMore);
}

TEST_CASE("Content-Length policy is strict", "[http][L3-CPP-050]") {
    struct Case {
        const char* value;
        bool ok;
        int status;
    };
    const Case cases[] = {
        {"0", true, 0},
        {"2", true, 0},
        {"", false, 400},
        {"+2", false, 400},
        {"-2", false, 400},
        {" 2", false, 400},
        {"2 ", false, 400},
        {"2,2", false, 400},
        {"0x10", false, 400},
        {"2.0", false, 400},
        {"abc", false, 400},
        {"99999999999999999999999999", false, 413},  // overflow, not wrap
    };

    for (std::size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        Request req;
        req.headers["content-length"] = cases[i].value;
        std::uint64_t length = 999;
        int status = 0;
        std::string error;

        INFO("Content-Length: \"" << cases[i].value << "\"");
        const bool ok = filemover::http::content_length_for(
            req, kMaxBody, length, status, error);
        CHECK(ok == cases[i].ok);
        if (!ok) {
            CHECK(status == cases[i].status);
            CHECK(error.empty() == false);
        }
    }
}

TEST_CASE("an absent Content-Length means zero", "[http][L3-CPP-050]") {
    Request req;
    std::uint64_t length = 999;
    int status = 0;
    std::string error;
    CHECK(filemover::http::content_length_for(req, kMaxBody, length, status,
                                              error) == true);
    CHECK(length == 0u);
}

TEST_CASE("any Transfer-Encoding is refused", "[http][L3-CPP-050]") {
    // No chunked decoder exists, so there is nothing to desync — but
    // ignoring the header is what lets a TE/CL disagreement smuggle a
    // request past an intermediary.
    const char* values[] = {"chunked", "identity", "gzip", "CHUNKED", ""};
    for (std::size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
        Request req;
        req.headers["transfer-encoding"] = values[i];
        req.headers["content-length"] = "5";
        std::uint64_t length = 0;
        int status = 0;
        std::string error;
        INFO("Transfer-Encoding: \"" << values[i] << "\"");
        CHECK(filemover::http::content_length_for(req, kMaxBody, length,
                                                  status, error) == false);
        CHECK(status == 400);
    }
}

TEST_CASE("the body size is bounded", "[http][L3-CPP-050]") {
    Request req;
    req.headers["content-length"] = "65537";
    std::uint64_t length = 0;
    int status = 0;
    std::string error;
    CHECK(filemover::http::content_length_for(req, 65536, length, status,
                                              error) == false);
    CHECK(status == 413);

    req.headers["content-length"] = "65536";
    CHECK(filemover::http::content_length_for(req, 65536, length, status,
                                              error) == true);
    CHECK(length == 65536u);
}

TEST_CASE("responses serialize with correct framing", "[http][L3-CPP-051]") {
    Response res;
    res.status = 201;
    res.content_type = "application/json";
    res.body = "{\"id\":\"job-000001\"}";

    const std::string wire = filemover::http::serialize_response(res);
    CHECK(wire.find("HTTP/1.1 201 Created\r\n") == 0u);
    CHECK(wire.find("Content-Length: 19\r\n") != std::string::npos);
    CHECK(wire.find("Connection: close\r\n") != std::string::npos);
    CHECK(wire.find("\r\n\r\n") != std::string::npos);
    CHECK(wire.find("Allow:") == std::string::npos);
    // Body follows the blank line intact.
    CHECK(wire.substr(wire.find("\r\n\r\n") + 4) == res.body);
}

TEST_CASE("405 responses carry an Allow header", "[http][L3-CPP-051]") {
    Response res;
    res.status = 405;
    res.allow = "GET, POST";
    const std::string wire = filemover::http::serialize_response(res);
    CHECK(wire.find("HTTP/1.1 405 Method Not Allowed\r\n") == 0u);
    CHECK(wire.find("Allow: GET, POST\r\n") != std::string::npos);
}

TEST_CASE("every status the serializer knows has a reason phrase",
          "[http][L3-CPP-051]") {
    // One case per arm of the switch. Without this the table was only 30%
    // covered, and a wrong reason phrase for, say, 413 would have shipped.
    struct Row {
        int status;
        const char* line;
    };
    const Row rows[] = {
        {200, "HTTP/1.1 200 OK\r\n"},
        {201, "HTTP/1.1 201 Created\r\n"},
        {400, "HTTP/1.1 400 Bad Request\r\n"},
        {404, "HTTP/1.1 404 Not Found\r\n"},
        {405, "HTTP/1.1 405 Method Not Allowed\r\n"},
        {409, "HTTP/1.1 409 Conflict\r\n"},
        {413, "HTTP/1.1 413 Payload Too Large\r\n"},
        {431, "HTTP/1.1 431 Request Header Fields Too Large\r\n"},
        // Not a case in the switch — it is the initializer, so it arrives
        // here through the default arm.
        {500, "HTTP/1.1 500 Internal Server Error\r\n"},
        // Anything unknown must also fall back rather than emit garbage.
        {599, "HTTP/1.1 599 Internal Server Error\r\n"},
    };

    for (std::size_t i = 0; i < sizeof(rows) / sizeof(rows[0]); ++i) {
        INFO("status " << rows[i].status);
        Response res;
        res.status = rows[i].status;
        const std::string wire = filemover::http::serialize_response(res);
        CHECK(wire.find(rows[i].line) == 0u);
    }
}

TEST_CASE("a complete but oversized head is TooLarge", "[http][L3-CPP-048]") {
    // Distinct from the dribbling-client case: here the terminator is present,
    // so the size check on the far side of `find` is what has to fire.
    std::string data = "GET / HTTP/1.1\r\n";
    while (data.size() < kMaxHead + 64) {
        data += "X-Pad: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n";
    }
    data += "\r\n";

    Request out;
    std::size_t head_len = 0;
    std::string error;
    CHECK(parse(data, out, head_len, error) == HeadParse::TooLarge);
    CHECK(error.empty() == false);
}

TEST_CASE("lines not terminated by CRLF inside a complete head are Bad",
          "[http][L3-CPP-046]") {
    // These reach the parser only because a well-formed CRLFCRLF appears
    // later in the buffer; the bytes before it are still framed wrong. A
    // parser that tolerated them would disagree with any peer that does not.

    // Request line ends at a bare LF.
    CHECK(bad("a\nb HTTP/1.1\r\n\r\n") == true);
    // Head begins with a bare LF, so the first line is empty.
    CHECK(bad("\nGET / HTTP/1.1\r\n\r\n") == true);
    // A header line ends at a bare LF.
    CHECK(bad("GET / HTTP/1.1\r\nHost: a\nX-Other: b\r\n\r\n") == true);
}

TEST_CASE("arbitrary bytes never crash the parser", "[http][L3-CPP-049]") {
    std::uint32_t seed = 0x0badc0deu;
    for (int iteration = 0; iteration < 3000; ++iteration) {
        std::string s;
        const std::size_t len = 1 + (seed % 96);
        for (std::size_t i = 0; i < len; ++i) {
            seed = seed * 1103515245u + 12345u;
            s.push_back(static_cast<char>((seed >> 16) & 0xFF));
        }
        Request out;
        std::size_t head_len = 0;
        std::string error;
        // The contract is that it returns, not what it returns.
        const HeadParse r = parse(s, out, head_len, error);
        if (r == HeadParse::Bad || r == HeadParse::TooLarge) {
            CHECK(error.empty() == false);
        }
    }
}
