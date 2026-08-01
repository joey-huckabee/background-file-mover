// Project-owned strict-subset JSON parser (ADR-0006, ADR-0009).
// Traces: L2-JSON-001..005
//
// Recursive descent with an explicit depth counter checked before every
// descent. No exception escapes this translation unit; failures are reported
// through the (bool, error) contract.

#include "filemover/json.hpp"

#include <cstdio>
#include <limits>

namespace filemover {
namespace json {
namespace {

const char* const kWhitespace = " \t\n\r";

bool is_ws(unsigned char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

bool is_digit(unsigned char c) { return c >= '0' && c <= '9'; }

int hex_value(unsigned char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// Appends `cp` to `out` as UTF-8. Callers guarantee cp <= 0x10FFFF and that
// cp is not a surrogate.
void append_utf8(std::string& out, std::uint32_t cp) {
    if (cp < 0x80) {
        out.push_back(static_cast<char>(cp));
    } else if (cp < 0x800) {
        out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else if (cp < 0x10000) {
        out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
}

class Parser {
public:
    Parser(const std::string& input, const Limits& limits)
        : s_(input), n_(input.size()), i_(0), limits_(limits) {}

    bool run(Value& out, std::string& error) {
        error_.clear();

        if (n_ > limits_.max_input_bytes) {
            return fail("input exceeds the configured maximum size", error);
        }
        // ADR-0009: a leading byte-order mark is rejected rather than skipped.
        if (n_ >= 3 && static_cast<unsigned char>(s_[0]) == 0xEF &&
            static_cast<unsigned char>(s_[1]) == 0xBB &&
            static_cast<unsigned char>(s_[2]) == 0xBF) {
            return fail("leading byte-order mark is not permitted", error);
        }

        skip_ws();
        if (at_end()) {
            return fail("input is empty", error);
        }
        // ADR-0009: the top-level value must be an object.
        if (peek() != '{') {
            return fail("top-level value must be an object", error);
        }
        if (!parse_value(out, 1)) {
            return fail(error_, error);
        }
        skip_ws();
        // L3-CPP-024 / ADR-0009: whole-input consumption. A parser that
        // silently ignores trailing bytes lets one document be read two ways.
        if (!at_end()) {
            return fail("unexpected trailing content after the JSON value",
                        error);
        }
        return true;
    }

private:
    bool at_end() const { return i_ >= n_; }
    unsigned char peek() const { return static_cast<unsigned char>(s_[i_]); }

    void skip_ws() {
        while (i_ < n_ && is_ws(static_cast<unsigned char>(s_[i_]))) ++i_;
    }

    bool fail(const std::string& msg, std::string& error) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), " at offset %lu",
                      static_cast<unsigned long>(i_));
        error = msg + buf;
        return false;
    }

    bool set_error(const std::string& msg) {
        if (error_.empty()) error_ = msg;
        return false;
    }

    // Depth is checked BEFORE descending (ADR-0009), so an adversarial
    // "[[[[..." can never drive the stack past the limit.
    bool parse_value(Value& out, std::size_t depth) {
        if (depth > limits_.max_depth) {
            return set_error("maximum nesting depth exceeded");
        }
        if (at_end()) return set_error("unexpected end of input");

        const unsigned char c = peek();
        switch (c) {
            case '{': return parse_object(out, depth);
            case '[': return parse_array(out, depth);
            case '"': {
                std::string v;
                if (!parse_string(v)) return false;
                out.set_string(v);
                return true;
            }
            case 't':
                if (!literal("true")) return false;
                out.set_bool(true);
                return true;
            case 'f':
                if (!literal("false")) return false;
                out.set_bool(false);
                return true;
            case 'n':
                // ADR-0009 does not list null among accepted member values.
                return set_error("null is not an accepted value");
            default:
                if (c == '-' || is_digit(c)) return parse_number(out);
                return set_error("unexpected character");
        }
    }

    bool literal(const char* word) {
        const std::size_t len = std::string(word).size();
        if (n_ - i_ < len || s_.compare(i_, len, word) != 0) {
            return set_error("invalid literal");
        }
        i_ += len;
        return true;
    }

    bool parse_object(Value& out, std::size_t depth) {
        ++i_;  // consume '{'
        out.set_object();
        std::vector<Member>& members = out.mutable_object();

        skip_ws();
        if (at_end()) return set_error("unterminated object");
        if (peek() == '}') {
            ++i_;
            return true;
        }

        for (;;) {
            skip_ws();
            if (at_end()) return set_error("unterminated object");
            if (peek() != '"') {
                // Catches unquoted keys, single-quoted keys, and a trailing
                // comma before '}'.
                return set_error("object member name must be a quoted string");
            }
            std::string key;
            if (!parse_string(key)) return false;

            // ADR-0009: duplicates are rejected, not resolved.
            for (std::size_t k = 0; k < members.size(); ++k) {
                if (members[k].key == key) {
                    return set_error("duplicate object member name");
                }
            }
            if (members.size() >= limits_.max_members) {
                return set_error("object exceeds the maximum member count");
            }

            skip_ws();
            if (at_end() || peek() != ':') {
                return set_error("expected ':' after member name");
            }
            ++i_;
            skip_ws();

            members.push_back(Member());
            members.back().key = key;
            if (!parse_value(members.back().value, depth + 1)) return false;

            skip_ws();
            if (at_end()) return set_error("unterminated object");
            if (peek() == ',') {
                ++i_;
                continue;
            }
            if (peek() == '}') {
                ++i_;
                return true;
            }
            return set_error("expected ',' or '}' in object");
        }
    }

    bool parse_array(Value& out, std::size_t depth) {
        ++i_;  // consume '['
        out.set_array();
        std::vector<Value>& elems = out.mutable_array();

        skip_ws();
        if (at_end()) return set_error("unterminated array");
        if (peek() == ']') {
            ++i_;
            return true;
        }

        for (;;) {
            skip_ws();
            if (at_end()) return set_error("unterminated array");
            // A trailing comma lands here as ']' and is rejected by
            // parse_value's "unexpected character".
            if (elems.size() >= limits_.max_elements) {
                return set_error("array exceeds the maximum element count");
            }
            elems.push_back(Value());
            if (!parse_value(elems.back(), depth + 1)) return false;

            skip_ws();
            if (at_end()) return set_error("unterminated array");
            if (peek() == ',') {
                ++i_;
                continue;
            }
            if (peek() == ']') {
                ++i_;
                return true;
            }
            return set_error("expected ',' or ']' in array");
        }
    }

    // Validates a raw (unescaped) UTF-8 sequence starting at i_, appending it
    // to `out`. Rejects overlong forms, surrogates encoded directly, and
    // truncated sequences — all of which are ways to smuggle a byte sequence
    // past a naive consumer.
    bool consume_utf8(std::string& out) {
        const unsigned char c = peek();
        std::size_t len;
        unsigned char lo2 = 0x80, hi2 = 0xBF;

        if (c < 0x80) {
            len = 1;
        } else if (c >= 0xC2 && c <= 0xDF) {
            len = 2;
        } else if (c >= 0xE0 && c <= 0xEF) {
            len = 3;
            if (c == 0xE0) lo2 = 0xA0;              // reject overlong
            if (c == 0xED) hi2 = 0x9F;              // reject surrogates
        } else if (c >= 0xF0 && c <= 0xF4) {
            len = 4;
            if (c == 0xF0) lo2 = 0x90;              // reject overlong
            if (c == 0xF4) hi2 = 0x8F;              // reject > U+10FFFF
        } else {
            // 0x80-0xBF stray continuation, or 0xC0/0xC1/0xF5-0xFF.
            return set_error("invalid UTF-8 lead byte in string");
        }

        if (n_ - i_ < len) return set_error("truncated UTF-8 sequence");
        for (std::size_t k = 1; k < len; ++k) {
            const unsigned char cc = static_cast<unsigned char>(s_[i_ + k]);
            const unsigned char lo = (k == 1) ? lo2 : 0x80;
            const unsigned char hi = (k == 1) ? hi2 : 0xBF;
            if (cc < lo || cc > hi) {
                return set_error("invalid UTF-8 continuation byte in string");
            }
        }
        out.append(s_, i_, len);
        i_ += len;
        return true;
    }

    bool parse_hex4(std::uint32_t& cp) {
        if (n_ - i_ < 4) return set_error("truncated \\u escape");
        std::uint32_t v = 0;
        for (int k = 0; k < 4; ++k) {
            const int d = hex_value(static_cast<unsigned char>(s_[i_ + k]));
            if (d < 0) return set_error("invalid hex digit in \\u escape");
            v = (v << 4) | static_cast<std::uint32_t>(d);
        }
        i_ += 4;
        cp = v;
        return true;
    }

    bool parse_string(std::string& out) {
        ++i_;  // consume opening quote
        out.clear();

        for (;;) {
            if (at_end()) return set_error("unterminated string");
            if (out.size() > limits_.max_string_bytes) {
                return set_error("string exceeds the maximum length");
            }

            const unsigned char c = peek();
            if (c == '"') {
                ++i_;
                return true;
            }
            if (c < 0x20) {
                // Includes a raw NUL and every other control character.
                return set_error("unescaped control character in string");
            }
            if (c != '\\') {
                if (!consume_utf8(out)) return false;
                continue;
            }

            ++i_;  // consume backslash
            if (at_end()) return set_error("unterminated escape sequence");
            const unsigned char e = peek();
            ++i_;
            switch (e) {
                case '"':  out.push_back('"');  break;
                case '\\': out.push_back('\\'); break;
                case '/':  out.push_back('/');  break;
                case 'b':  out.push_back('\b'); break;
                case 'f':  out.push_back('\f'); break;
                case 'n':  out.push_back('\n'); break;
                case 'r':  out.push_back('\r'); break;
                case 't':  out.push_back('\t'); break;
                case 'u': {
                    std::uint32_t cp = 0;
                    if (!parse_hex4(cp)) return false;
                    if (cp == 0) {
                        // L3-CPP-018 / ADR-0009: an embedded NUL truncates
                        // the value anywhere it reaches a C API.
                        return set_error("embedded NUL is not permitted");
                    }
                    if (cp >= 0xD800 && cp <= 0xDBFF) {
                        // High surrogate: a valid low surrogate must follow.
                        if (n_ - i_ < 2 || s_[i_] != '\\' || s_[i_ + 1] != 'u') {
                            return set_error("lone high surrogate");
                        }
                        i_ += 2;
                        std::uint32_t lo = 0;
                        if (!parse_hex4(lo)) return false;
                        if (lo < 0xDC00 || lo > 0xDFFF) {
                            return set_error("invalid low surrogate");
                        }
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                    } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                        return set_error("lone low surrogate");
                    }
                    append_utf8(out, cp);
                    break;
                }
                default:
                    return set_error("unrecognized escape character");
            }
        }
    }

    // Integers only. ADR-0009 rejects floats outright: the API has no
    // float-typed field, and float parsing is a disproportionate share of the
    // complexity and the CVE history.
    bool parse_number(Value& out) {
        const std::size_t start = i_;
        bool negative = false;

        if (peek() == '-') {
            negative = true;
            ++i_;
            if (at_end()) return set_error("number has no digits");
        }
        // '+' is not permitted as a leading sign, and is not consumed above,
        // so it falls through to the digit check below.
        if (at_end() || !is_digit(peek())) {
            return set_error("number has no digits");
        }

        if (peek() == '0') {
            ++i_;
            if (!at_end() && is_digit(peek())) {
                return set_error("leading zeros are not permitted");
            }
        } else {
            while (!at_end() && is_digit(peek())) ++i_;
        }

        if (!at_end() && (peek() == '.' )) {
            return set_error("floating-point values are not accepted");
        }
        if (!at_end() && (peek() == 'e' || peek() == 'E')) {
            return set_error("exponent notation is not accepted");
        }

        // Accumulate with an explicit overflow guard rather than strtoll, so
        // the range check is visible and does not depend on errno handling.
        const std::uint64_t limit =
            negative ? static_cast<std::uint64_t>(
                           -(std::numeric_limits<std::int64_t>::min() + 1)) + 1
                     : static_cast<std::uint64_t>(
                           std::numeric_limits<std::int64_t>::max());
        std::uint64_t acc = 0;
        for (std::size_t k = start + (negative ? 1 : 0); k < i_; ++k) {
            const std::uint64_t d =
                static_cast<std::uint64_t>(s_[k] - '0');
            if (acc > (limit - d) / 10) {
                return set_error("integer is out of the representable range");
            }
            acc = acc * 10 + d;
        }

        if (negative) {
            out.set_int(acc == 0 ? 0
                                 : -static_cast<std::int64_t>(acc - 1) - 1);
        } else {
            out.set_int(static_cast<std::int64_t>(acc));
        }
        return true;
    }

    const std::string& s_;
    const std::size_t n_;
    std::size_t i_;
    const Limits& limits_;
    std::string error_;
};

}  // namespace

Value::Value() : type_(Type::Bool), bool_(false), int_(0) {}

const Value* Value::find(const std::string& key) const {
    for (std::size_t i = 0; i < members_.size(); ++i) {
        if (members_[i].key == key) return &members_[i].value;
    }
    return 0;
}

void Value::set_bool(bool v) {
    type_ = Type::Bool;
    bool_ = v;
}

void Value::set_int(std::int64_t v) {
    type_ = Type::Int;
    int_ = v;
}

void Value::set_string(const std::string& v) {
    type_ = Type::String;
    string_ = v;
}

void Value::set_array() {
    type_ = Type::Array;
    array_.clear();
}

void Value::set_object() {
    type_ = Type::Object;
    members_.clear();
}

Limits::Limits()
    : max_depth(4),
      max_input_bytes(64 * 1024),
      max_string_bytes(4096),
      max_members(64),
      max_elements(64) {}

bool parse(const std::string& input,
           Value& out,
           std::string& error,
           const Limits& limits) {
    Parser p(input, limits);
    return p.run(out, error);
}

bool parse(const std::string& input, Value& out, std::string& error) {
    const Limits limits;
    return parse(input, out, error, limits);
}

std::string escape(const std::string& in) {
    std::string out;
    out.reserve(in.size() + 8);
    for (std::size_t i = 0; i < in.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(in[i]);
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x",
                                  static_cast<unsigned>(c));
                    out += buf;
                } else {
                    out.push_back(static_cast<char>(c));
                }
        }
    }
    return out;
}

}  // namespace json
}  // namespace filemover
