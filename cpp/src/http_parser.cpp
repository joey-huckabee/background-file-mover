// HTTP/1.1 request parsing and response serialization.
// Traces: L3-CPP-046..051

#include "filemover/http_parser.hpp"

#include <cstdio>
#include <sstream>

namespace filemover {
namespace http {
namespace {

// Character classification is done with explicit ranges, never <cctype>.
//
// std::isalnum and std::tolower are LOCALE-SENSITIVE. A parser sitting on
// untrusted network input must not change what it accepts because something
// elsewhere in the process called setlocale — the same reasoning that made
// the JSON parser use explicit tables rather than library classification.
bool is_upper_alpha(char c) { return c >= 'A' && c <= 'Z'; }
bool is_digit(char c) { return c >= '0' && c <= '9'; }
bool is_lower_alpha(char c) { return c >= 'a' && c <= 'z'; }

bool is_ctl(char c) {
    const unsigned char u = static_cast<unsigned char>(c);
    return u < 0x20 || u == 0x7f;
}

char to_lower_ascii(char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
}

bool valid_method(const std::string& token) {
    if (token.empty() || token.size() > 16) return false;
    for (std::size_t i = 0; i < token.size(); ++i) {
        if (!is_upper_alpha(token[i])) return false;
    }
    return true;
}

bool valid_target(const std::string& target) {
    if (target.empty() || target[0] != '/') return false;
    for (std::size_t i = 0; i < target.size(); ++i) {
        const char c = target[i];
        if (c == ' ' || c == '\t' || is_ctl(c)) return false;
    }
    return true;
}

// Deliberately stricter than RFC 7230's token grammar, which also permits
// !#$%&'*+.^_`|~ . The API's header set needs none of them, and a parser
// that accepts less has less to get wrong.
bool valid_header_name(const std::string& name) {
    if (name.empty()) return false;
    for (std::size_t i = 0; i < name.size(); ++i) {
        const char c = name[i];
        if (!(is_lower_alpha(c) || is_upper_alpha(c) || is_digit(c) ||
              c == '-' || c == '_')) {
            return false;
        }
    }
    return true;
}

std::string lower_ascii(const std::string& s) {
    std::string out(s);
    for (std::size_t i = 0; i < out.size(); ++i) {
        out[i] = to_lower_ascii(out[i]);
    }
    return out;
}

std::string trim_ows(const std::string& s) {
    const std::string::size_type b = s.find_first_not_of(" \t");
    if (b == std::string::npos) return std::string();
    const std::string::size_type e = s.find_last_not_of(" \t");
    return s.substr(b, e - b + 1);
}

}  // namespace

HeadParse parse_request_head(const std::string& data,
                             std::size_t max_head,
                             Request& out,
                             std::size_t& head_len,
                             std::string& error) {
    const std::string::size_type end = data.find("\r\n\r\n");
    if (end == std::string::npos) {
        // L3-CPP-048: the cap is checked before the head is complete, so a
        // client dribbling bytes forever is bounded rather than unbounded.
        if (data.size() > max_head) {
            error = "request head exceeds limit";
            return HeadParse::TooLarge;
        }
        return HeadParse::NeedMore;  // L3-CPP-049
    }
    if (end + 4 > max_head) {
        error = "request head exceeds limit";
        return HeadParse::TooLarge;
    }

    const std::string head = data.substr(0, end + 2);
    std::istringstream lines(head);
    std::string line;

    if (!std::getline(lines, line) || line.empty() ||
        line[line.size() - 1] != '\r') {
        error = "malformed request line";
        return HeadParse::Bad;
    }
    line.erase(line.size() - 1);

    const std::string::size_type sp1 = line.find(' ');
    const std::string::size_type sp2 =
        (sp1 == std::string::npos) ? std::string::npos
                                   : line.find(' ', sp1 + 1);
    if (sp1 == std::string::npos || sp2 == std::string::npos ||
        line.find(' ', sp2 + 1) != std::string::npos) {
        error = "malformed request line";  // L3-CPP-046
        return HeadParse::Bad;
    }

    // Built into a local and copied out only on success (L3-CPP-049), so a
    // caller reusing a Request cannot mistake stale fields for a parse.
    Request parsed;
    parsed.method = line.substr(0, sp1);
    parsed.target = line.substr(sp1 + 1, sp2 - sp1 - 1);
    parsed.version = line.substr(sp2 + 1);

    if (!valid_method(parsed.method)) {
        error = "invalid method token";
        return HeadParse::Bad;
    }
    if (!valid_target(parsed.target)) {
        error = "invalid request target";
        return HeadParse::Bad;
    }
    if (parsed.version != "HTTP/1.1" && parsed.version != "HTTP/1.0") {
        error = "unsupported HTTP version";
        return HeadParse::Bad;
    }

    std::size_t count = 0;
    while (std::getline(lines, line)) {
        if (line.empty() || line[line.size() - 1] != '\r') {
            error = "malformed header framing";
            return HeadParse::Bad;
        }
        line.erase(line.size() - 1);
        if (line.empty()) break;

        // obs-fold: a header value continued on the next line. Deprecated by
        // RFC 7230 and a classic desync primitive, because intermediaries
        // disagree about how to unfold it.
        if (line[0] == ' ' || line[0] == '\t') {
            error = "obs-fold header continuation rejected";  // L3-CPP-047
            return HeadParse::Bad;
        }

        const std::string::size_type colon = line.find(':');
        if (colon == std::string::npos) {
            error = "header without ':'";
            return HeadParse::Bad;
        }
        const std::string name = line.substr(0, colon);
        const std::string value = trim_ows(line.substr(colon + 1));
        if (!valid_header_name(name)) {
            error = "invalid header name";
            return HeadParse::Bad;
        }
        for (std::size_t i = 0; i < value.size(); ++i) {
            if (is_ctl(value[i])) {
                error = "control character in header value";
                return HeadParse::Bad;
            }
        }
        if (++count > 64) {
            error = "too many headers";  // L3-CPP-047
            return HeadParse::Bad;
        }

        const std::string key = lower_ascii(name);
        // A map assignment would silently take the last value. Two parties
        // disagreeing about which duplicate wins is exactly how request
        // smuggling works, so a duplicate is refused outright rather than
        // resolved.
        if (parsed.headers.count(key) != 0) {
            error = "duplicate header \"";
            error += key;
            error += "\"";
            return HeadParse::Bad;
        }
        parsed.headers[key] = value;
    }

    out = parsed;
    head_len = end + 4;
    error.clear();
    return HeadParse::Ok;
}

bool content_length_for(const Request& request,
                        std::uint64_t max_body,
                        std::uint64_t& length,
                        int& http_status,
                        std::string& error) {
    // No chunked decoder exists, so there is nothing to desync. Any
    // Transfer-Encoding at all is refused rather than ignored — ignoring it
    // is what lets a TE/CL disagreement smuggle a second request.
    if (request.headers.count("transfer-encoding") != 0) {
        http_status = 400;  // L3-CPP-050
        error = "Transfer-Encoding is not supported";
        return false;
    }

    const std::map<std::string, std::string>::const_iterator it =
        request.headers.find("content-length");
    if (it == request.headers.end()) {
        length = 0;
        return true;
    }

    const std::string& value = it->second;
    if (value.empty()) {
        http_status = 400;
        error = "invalid Content-Length";
        return false;
    }

    // Digits only, whole token, accumulated with an explicit overflow guard.
    // strtoull would accept a leading '+', leading whitespace, and a partial
    // parse, all of which are ways to disagree with another parser.
    std::uint64_t parsed = 0;
    const std::uint64_t limit = static_cast<std::uint64_t>(-1);
    for (std::size_t i = 0; i < value.size(); ++i) {
        const char c = value[i];
        if (!is_digit(c)) {
            http_status = 400;
            error = "invalid Content-Length";
            return false;
        }
        const std::uint64_t digit = static_cast<std::uint64_t>(c - '0');
        if (parsed > (limit - digit) / 10) {
            http_status = 413;
            error = "request body exceeds limit";
            return false;
        }
        parsed = parsed * 10 + digit;
    }

    if (parsed > max_body) {
        http_status = 413;  // L3-CPP-050
        error = "request body exceeds limit";
        return false;
    }

    length = parsed;
    return true;
}

std::string serialize_response(const Response& response) {
    const char* reason = "Internal Server Error";
    switch (response.status) {
        case 200: reason = "OK"; break;
        case 201: reason = "Created"; break;
        case 400: reason = "Bad Request"; break;
        case 404: reason = "Not Found"; break;
        case 405: reason = "Method Not Allowed"; break;
        case 409: reason = "Conflict"; break;
        case 413: reason = "Payload Too Large"; break;
        case 431: reason = "Request Header Fields Too Large"; break;
        // 500 is deliberately absent: it is the initializer above, so a case
        // for it would be an identical branch to the default.
        default: break;
    }

    std::ostringstream os;  // L3-CPP-051
    os << "HTTP/1.1 " << response.status << " " << reason << "\r\n"
       << "Content-Type: " << response.content_type << "\r\n"
       << "Content-Length: " << response.body.size() << "\r\n"
       << "Connection: close\r\n";
    if (!response.allow.empty()) {
        os << "Allow: " << response.allow << "\r\n";
    }
    os << "\r\n" << response.body;
    return os.str();
}

}  // namespace http
}  // namespace filemover
