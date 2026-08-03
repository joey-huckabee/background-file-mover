// Strict-subset JSON parser tests (ADR-0009).
// Traces: L2-JSON-002..005, L3-CPP-016..024
//
// This is predominantly a *rejection* suite. ADR-0009 defines the parser by
// what it refuses, so most of the value is in confirming that each refusal
// actually happens rather than that valid input round-trips.

#include "catch2/catch.hpp"

#include "filemover/json.hpp"

#include <string>
#include <vector>

using filemover::json::Limits;
using filemover::json::Value;

namespace {

// Returns true on success. On failure the error is required to be non-empty
// by L3-CPP-019, asserted centrally here so every rejection case gets the
// check for free.
bool accepts(const std::string& input) {
    Value v;
    std::string error;
    const bool ok = filemover::json::parse(input, v, error);
    if (!ok) {
        REQUIRE(error.empty() == false);
    }
    return ok;
}

bool accepts(const std::string& input, const Limits& limits) {
    Value v;
    std::string error;
    const bool ok = filemover::json::parse(input, v, error, limits);
    if (!ok) {
        REQUIRE(error.empty() == false);
    }
    return ok;
}

Value must_parse(const std::string& input) {
    Value v;
    std::string error;
    const bool ok = filemover::json::parse(input, v, error);
    REQUIRE(ok == true);
    return v;
}

}  // namespace

TEST_CASE("accepts the documented subset", "[json][L3-CPP-016]") {
    REQUIRE(accepts("{}") == true);
    REQUIRE(accepts("{\"a\":\"b\"}") == true);
    REQUIRE(accepts("{\"a\":true,\"b\":false}") == true);
    REQUIRE(accepts("{\"a\":0,\"b\":-1,\"c\":42}") == true);
    REQUIRE(accepts("{\"a\":{\"b\":\"c\"}}") == true);
    REQUIRE(accepts("{\"a\":[1,2,3]}") == true);
    REQUIRE(accepts("  {  \"a\"  :  \"b\"  }  ") == true);
    REQUIRE(accepts("{\"a\":\"b\"}\n") == true);
}

TEST_CASE("string values round-trip exactly", "[json][L3-CPP-023]") {
    const Value v = must_parse(
        "{\"plain\":\"hello\","
        "\"quote\":\"a\\\"b\","
        "\"backslash\":\"a\\\\b\","
        "\"newline\":\"a\\nb\","
        "\"tab\":\"a\\tb\","
        "\"solidus\":\"a\\/b\","
        "\"unicode\":\"\\u00e9\","
        "\"astral\":\"\\ud83d\\ude00\"}");

    REQUIRE(v.is_object() == true);
    REQUIRE(v.find("plain")->as_string() == std::string("hello"));
    REQUIRE(v.find("quote")->as_string() == std::string("a\"b"));
    REQUIRE(v.find("backslash")->as_string() == std::string("a\\b"));
    REQUIRE(v.find("newline")->as_string() == std::string("a\nb"));
    REQUIRE(v.find("tab")->as_string() == std::string("a\tb"));
    REQUIRE(v.find("solidus")->as_string() == std::string("a/b"));
    // U+00E9 encodes as two bytes; U+1F600 as the four-byte form.
    REQUIRE(v.find("unicode")->as_string() == std::string("\xc3\xa9"));
    REQUIRE(v.find("astral")->as_string() == std::string("\xf0\x9f\x98\x80"));
}

TEST_CASE("integers parse across the int64 range", "[json][L3-CPP-022]") {
    const Value v = must_parse(
        "{\"zero\":0,\"neg\":-7,\"max\":9223372036854775807,"
        "\"min\":-9223372036854775808}");

    REQUIRE(v.find("zero")->as_int() == 0);
    REQUIRE(v.find("neg")->as_int() == -7);
    REQUIRE(v.find("max")->as_int() == 9223372036854775807LL);
    REQUIRE(v.find("min")->as_int() == (-9223372036854775807LL - 1));
}

TEST_CASE("top-level value must be an object", "[json][L3-CPP-017]") {
    REQUIRE(accepts("[]") == false);
    REQUIRE(accepts("[1,2]") == false);
    REQUIRE(accepts("\"bare string\"") == false);
    REQUIRE(accepts("42") == false);
    REQUIRE(accepts("true") == false);
    REQUIRE(accepts("null") == false);
}

TEST_CASE("rejection errors name the offending byte offset",
          "[json][L3-CPP-019]") {
    // L3-CPP-019 has two halves. The non-empty half is asserted centrally in
    // accepts(); the offset half had no test at all until this one, even though
    // the parser has always reported it. An error that says only "invalid
    // literal" about a 4 KB request body is not diagnosable, which is the whole
    // reason the requirement asks for a position.
    struct Row {
        const char* input;
        const char* expected;  // substring, so the message wording stays free
    };
    const Row rows[] = {
        {"nope", "at offset 0"},               // fails on the very first byte
        {"{,}", "at offset 1"},                // first byte inside the object
        {"{\"a\" 1}", "at offset 5"},          // the missing ':'
        {"{\"a\": tru}", "at offset 6"},       // truncated literal
        {"{\"a\":01}", "at offset 6"},         // the digit after the leading 0
        {"{\"a\":1,}", "at offset 7"},         // trailing comma, at the brace
    };

    for (std::size_t i = 0; i < sizeof(rows) / sizeof(rows[0]); ++i) {
        INFO("input " << rows[i].input);
        Value v;
        std::string error;
        REQUIRE(filemover::json::parse(rows[i].input, v, error) == false);
        CHECK(error.empty() == false);
        CHECK(error.find(rows[i].expected) != std::string::npos);
    }
}

TEST_CASE("trailing content after the value is rejected",
          "[json][L3-CPP-024]") {
    // The picojson defect that motivated whole-input consumption: a body
    // that parses "successfully" while carrying unread bytes lets one
    // document be read two different ways.
    REQUIRE(accepts("{\"a\":\"b\"}garbage") == false);
    REQUIRE(accepts("{\"a\":\"b\"}{\"c\":\"d\"}") == false);
    REQUIRE(accepts("{\"a\":\"b\"} null") == false);
    REQUIRE(accepts("{\"a\":\"b\"}\x01") == false);
}

TEST_CASE("duplicate member names are rejected", "[json][L3-CPP-017]") {
    // RFC 8259 leaves this undefined. Parsers that silently pick first-wins
    // or last-wins disagree with each other, which is the classic
    // auth-bypass differential.
    REQUIRE(accepts("{\"a\":\"1\",\"a\":\"2\"}") == false);
    REQUIRE(accepts("{\"a\":\"1\",\"b\":\"2\",\"a\":\"3\"}") == false);
    REQUIRE(accepts("{\"a\":{\"x\":1},\"a\":{\"x\":2}}") == false);
    // Distinct names that merely look similar remain acceptable.
    REQUIRE(accepts("{\"a\":\"1\",\"A\":\"2\"}") == true);
}

TEST_CASE("structural malformations are rejected", "[json][L3-CPP-017]") {
    REQUIRE(accepts("") == false);
    REQUIRE(accepts("   ") == false);
    REQUIRE(accepts("{") == false);
    REQUIRE(accepts("}") == false);
    REQUIRE(accepts("{\"a\"}") == false);
    REQUIRE(accepts("{\"a\":}") == false);
    REQUIRE(accepts("{:\"b\"}") == false);
    REQUIRE(accepts("{\"a\":\"b\",}") == false);   // trailing comma
    REQUIRE(accepts("{\"a\":[1,]}") == false);     // trailing comma in array
    REQUIRE(accepts("{a:\"b\"}") == false);        // unquoted key
    REQUIRE(accepts("{'a':'b'}") == false);        // single quotes
    REQUIRE(accepts("{\"a\":\"b\"} // comment") == false);
    REQUIRE(accepts("{/* c */\"a\":\"b\"}") == false);
    REQUIRE(accepts("{\"a\":\"b\"") == false);     // unterminated object
    REQUIRE(accepts("{\"a\":[1,2}") == false);     // unterminated array
    REQUIRE(accepts("{\"a\":\"b}") == false);      // unterminated string
}

TEST_CASE("a leading byte-order mark is rejected", "[json][L3-CPP-017]") {
    REQUIRE(accepts("\xef\xbb\xbf{\"a\":\"b\"}") == false);
}

TEST_CASE("embedded NUL is rejected", "[json][L3-CPP-018]") {
    // Escaped: the four-hex-digit escape for code point zero.
    REQUIRE(accepts("{\"a\":\"x\\u0000y\"}") == false);
    REQUIRE(accepts("{\"\\u0000\":\"b\"}") == false);
    // Raw: a literal zero byte inside the quoted string.
    std::string raw = "{\"a\":\"x";
    raw.push_back('\0');
    raw += "y\"}";
    REQUIRE(accepts(raw) == false);
}

TEST_CASE("unescaped control characters are rejected", "[json][L3-CPP-018]") {
    for (int c = 0x01; c < 0x20; ++c) {
        std::string s = "{\"a\":\"x";
        s.push_back(static_cast<char>(c));
        s += "\"}";
        REQUIRE(accepts(s) == false);
    }
    // The same characters are acceptable when properly escaped.
    REQUIRE(accepts("{\"a\":\"x\\u0001y\"}") == true);
}

TEST_CASE("surrogate handling rejects unpaired halves", "[json][L3-CPP-018]") {
    REQUIRE(accepts("{\"a\":\"\\ud800\"}") == false);          // lone high
    REQUIRE(accepts("{\"a\":\"\\udc00\"}") == false);          // lone low
    REQUIRE(accepts("{\"a\":\"\\ud800\\ud800\"}") == false);   // high + high
    REQUIRE(accepts("{\"a\":\"\\ud800x\"}") == false);         // high + text
    REQUIRE(accepts("{\"a\":\"\\ud800\\u0041\"}") == false);   // high + BMP
    REQUIRE(accepts("{\"a\":\"\\ud83d\\ude00\"}") == true);    // valid pair
}

TEST_CASE("malformed escapes are rejected", "[json][L3-CPP-018]") {
    REQUIRE(accepts("{\"a\":\"\\q\"}") == false);       // unknown escape
    REQUIRE(accepts("{\"a\":\"\\u00\"}") == false);     // truncated
    REQUIRE(accepts("{\"a\":\"\\uZZZZ\"}") == false);   // bad hex
    REQUIRE(accepts("{\"a\":\"\\u00g1\"}") == false);   // bad hex digit
    REQUIRE(accepts("{\"a\":\"x\\\"}") == false);       // dangling backslash
}

TEST_CASE("invalid UTF-8 is rejected", "[json][L3-CPP-018]") {
    REQUIRE(accepts("{\"a\":\"\x80\"}") == false);              // stray cont.
    REQUIRE(accepts("{\"a\":\"\xc0\xaf\"}") == false);          // overlong 2
    REQUIRE(accepts("{\"a\":\"\xe0\x80\xaf\"}") == false);      // overlong 3
    REQUIRE(accepts("{\"a\":\"\xf0\x80\x80\xaf\"}") == false);  // overlong 4
    REQUIRE(accepts("{\"a\":\"\xed\xa0\x80\"}") == false);      // raw surrogate
    REQUIRE(accepts("{\"a\":\"\xf5\x80\x80\x80\"}") == false);  // > U+10FFFF
    REQUIRE(accepts("{\"a\":\"\xc3\"}") == false);              // truncated
    REQUIRE(accepts("{\"a\":\"\xff\"}") == false);              // invalid lead
    REQUIRE(accepts("{\"a\":\"\xc3\xa9\"}") == true);           // valid U+00E9
}

TEST_CASE("floating point and exponents are rejected", "[json][L3-CPP-022]") {
    // ADR-0009 rejects floats outright: no API field is float-typed, and
    // float parsing carries a disproportionate share of the CVE history.
    REQUIRE(accepts("{\"a\":1.5}") == false);
    REQUIRE(accepts("{\"a\":1.0}") == false);
    REQUIRE(accepts("{\"a\":1e3}") == false);
    REQUIRE(accepts("{\"a\":1E3}") == false);
    REQUIRE(accepts("{\"a\":1.5e3}") == false);
}

TEST_CASE("malformed numbers are rejected", "[json][L3-CPP-022]") {
    REQUIRE(accepts("{\"a\":01}") == false);          // leading zero
    REQUIRE(accepts("{\"a\":007}") == false);
    REQUIRE(accepts("{\"a\":+1}") == false);          // leading plus
    REQUIRE(accepts("{\"a\":.5}") == false);          // bare fraction
    REQUIRE(accepts("{\"a\":5.}") == false);          // trailing point
    REQUIRE(accepts("{\"a\":-}") == false);           // lone minus
    REQUIRE(accepts("{\"a\":NaN}") == false);
    REQUIRE(accepts("{\"a\":Infinity}") == false);
    REQUIRE(accepts("{\"a\":-Infinity}") == false);
    REQUIRE(accepts("{\"a\":0x10}") == false);
    REQUIRE(accepts("{\"a\":--1}") == false);
    REQUIRE(accepts("{\"a\":0}") == true);
    REQUIRE(accepts("{\"a\":-0}") == true);
}

TEST_CASE("integers outside int64 are rejected", "[json][L3-CPP-022]") {
    REQUIRE(accepts("{\"a\":9223372036854775808}") == false);   // max + 1
    REQUIRE(accepts("{\"a\":-9223372036854775809}") == false);  // min - 1
    REQUIRE(accepts("{\"a\":99999999999999999999999}") == false);
    REQUIRE(accepts("{\"a\":9223372036854775807}") == true);
    REQUIRE(accepts("{\"a\":-9223372036854775808}") == true);
}

TEST_CASE("literals other than true/false are rejected", "[json][L3-CPP-017]") {
    REQUIRE(accepts("{\"a\":null}") == false);
    REQUIRE(accepts("{\"a\":True}") == false);
    REQUIRE(accepts("{\"a\":tru}") == false);
    REQUIRE(accepts("{\"a\":falsey}") == false);
    REQUIRE(accepts("{\"a\":undefined}") == false);
}

TEST_CASE("nesting depth is bounded", "[json][L3-CPP-021]") {
    // Depth is checked before descending, so an adversarial document cannot
    // drive the stack past the limit regardless of how deep it claims to go.
    Limits limits;
    limits.max_depth = 4;

    REQUIRE(accepts("{\"a\":{\"b\":{\"c\":1}}}", limits) == true);
    REQUIRE(accepts("{\"a\":{\"b\":{\"c\":{\"d\":1}}}}", limits) == false);

    std::string deep;
    for (int i = 0; i < 100000; ++i) deep += "{\"a\":";
    deep += "1";
    for (int i = 0; i < 100000; ++i) deep += "}";
    REQUIRE(accepts(deep, limits) == false);

    std::string arrays = "{\"a\":";
    for (int i = 0; i < 100000; ++i) arrays += "[";
    REQUIRE(accepts(arrays, limits) == false);
}

TEST_CASE("size limits are enforced", "[json][L3-CPP-021]") {
    Limits limits;
    limits.max_input_bytes = 128;
    limits.max_string_bytes = 16;
    limits.max_members = 4;
    limits.max_elements = 4;

    REQUIRE(accepts("{\"a\":\"" + std::string(64, 'x') + "\"}", limits)
            == false);
    REQUIRE(accepts("{\"a\":\"" + std::string(8, 'x') + "\"}", limits) == true);

    REQUIRE(accepts("{\"a\":1,\"b\":2,\"c\":3,\"d\":4,\"e\":5}", limits)
            == false);
    REQUIRE(accepts("{\"a\":[1,2,3,4,5]}", limits) == false);

    REQUIRE(accepts("{\"a\":\"" + std::string(4096, 'x') + "\"}", limits)
            == false);
}

TEST_CASE("every prefix of a valid document is rejected without crashing",
          "[json][L3-CPP-020]") {
    // Truncation is the most common malformed input in practice — a client
    // that dies mid-request. No prefix may be accepted, and none may crash.
    const std::string valid =
        "{\"source\":\"/a/b\",\"dest\":\"/c/d\",\"n\":42,\"ok\":true,"
        "\"nested\":{\"k\":[1,2]}}";

    for (std::size_t i = 0; i < valid.size(); ++i) {
        REQUIRE(accepts(valid.substr(0, i)) == false);
    }
    REQUIRE(accepts(valid) == true);
}

TEST_CASE("arbitrary byte soup never crashes the parser", "[json][L3-CPP-020]") {
    // Deterministic pseudo-random bytes; a cheap stand-in for the fuzzer
    // that runs the same entry point under libFuzzer (ADR-0008).
    std::uint32_t seed = 0x12345678u;
    for (int iteration = 0; iteration < 2000; ++iteration) {
        std::string s;
        const std::size_t len = 1 + (seed % 64);
        for (std::size_t i = 0; i < len; ++i) {
            seed = seed * 1103515245u + 12345u;
            s.push_back(static_cast<char>((seed >> 16) & 0xFF));
        }
        Value v;
        std::string error;
        // The only requirement is that this returns rather than terminating.
        const bool ok = filemover::json::parse(s, v, error);
        if (!ok) {
            REQUIRE(error.empty() == false);
        }
    }
}

TEST_CASE("escape() output parses back to the original", "[json][L3-CPP-023]") {
    std::vector<std::string> cases;
    cases.push_back("plain");
    cases.push_back("with \"quotes\"");
    cases.push_back("with \\backslash");
    cases.push_back("with\nnewline\tand\ttabs");
    cases.push_back("\xc3\xa9 accented");
    cases.push_back("");

    std::string control;
    for (int c = 0x01; c < 0x20; ++c) control.push_back(static_cast<char>(c));
    cases.push_back(control);

    for (std::size_t i = 0; i < cases.size(); ++i) {
        const std::string doc =
            "{\"k\":\"" + filemover::json::escape(cases[i]) + "\"}";
        Value v;
        std::string error;
        REQUIRE(filemover::json::parse(doc, v, error) == true);
        REQUIRE(v.find("k")->as_string() == cases[i]);
    }
}
