// REST API codec tests.
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L3-CPP-025..032
//
// The four picojson characterization tests this suite inherited are gone.
// They existed to pin a vendored parser's quirks so a tag bump would fail
// loudly; with the parser project-owned (ADR-0006) that role belongs to
// test_json.cpp, which specifies the behaviour rather than characterizing
// someone else's.

#include "catch2/catch.hpp"

#include "filemover/api_codec.hpp"
#include "filemover/json.hpp"

#include <string>
#include <vector>

using filemover::Job;
using filemover::JobState;
using filemover::SubmitRequest;

namespace {

// Parses codec output back for verification. Uses the parser's general
// limits rather than the codec's stricter submit limits, since encoded
// output legitimately nests deeper than a submit body.
filemover::json::Value reparse(const std::string& encoded) {
    filemover::json::Value v;
    std::string error;
    const bool ok = filemover::json::parse(encoded, v, error);
    INFO("parse error: " << error);
    REQUIRE(ok == true);
    return v;
}

}  // namespace

TEST_CASE("decode accepts exactly {source, dest} with non-empty strings",
          "[codec][L3-CPP-025]") {
    SubmitRequest req;
    std::string error;

    const bool ok = filemover::decode_submit_request(
        "{\"source\": \"/data/in/a.ch10\", \"dest\": \"/data/out/a.ch10\"}",
        req, error);

    CHECK(ok == true);
    CHECK(req.source == "/data/in/a.ch10");
    CHECK(req.dest == "/data/out/a.ch10");
    CHECK(error.empty() == true);
}

TEST_CASE("decode rejects structural violations and leaves out unmodified",
          "[codec][L3-CPP-026][L3-CPP-027]") {
    struct Case {
        const char* name;
        const char* body;
    };
    const Case cases[] = {
        {"empty body", ""},
        {"whitespace only", "   \t\n"},
        {"truncated object", "{\"source\": \"/a\", \"dest\""},
        {"garbage bytes", "\x01\x02\x03\x04"},
        {"top-level array", "[\"/a\", \"/b\"]"},
        {"top-level string", "\"/a\""},
        {"top-level number", "42"},
        {"missing source", "{\"dest\": \"/b\"}"},
        {"missing dest", "{\"source\": \"/a\"}"},
        {"both missing", "{}"},
        {"source wrong type", "{\"source\": 5, \"dest\": \"/b\"}"},
        {"source is object", "{\"source\": {}, \"dest\": \"/b\"}"},
        {"dest wrong type", "{\"source\": \"/a\", \"dest\": null}"},
        {"dest is bool", "{\"source\": \"/a\", \"dest\": true}"},
        {"empty source", "{\"source\": \"\", \"dest\": \"/b\"}"},
        {"empty dest", "{\"source\": \"/a\", \"dest\": \"\"}"},
        {"unknown member",
         "{\"source\": \"/a\", \"dest\": \"/b\", \"mode\": \"fast\"}"},
        {"unknown member first",
         "{\"overwrite\": true, \"source\": \"/a\", \"dest\": \"/b\"}"},
        {"duplicate source", "{\"source\": \"/a\", \"source\": \"/c\", \"dest\": \"/b\"}"},
    };

    for (const Case& c : cases) {
        SubmitRequest req;
        req.source = "sentinel-src";
        req.dest = "sentinel-dst";
        std::string error;

        INFO(c.name);
        CHECK(filemover::decode_submit_request(c.body, req, error) == false);
        CHECK(error.empty() == false);
        // L3-CPP-027: the output is untouched on any rejection, so a caller
        // reusing the struct cannot mistake stale data for a decoded request.
        CHECK(req.source == "sentinel-src");
        CHECK(req.dest == "sentinel-dst");
    }
}

TEST_CASE("decode rejects trailing content after the JSON value",
          "[codec][L3-CPP-026]") {
    SubmitRequest req;
    std::string error;

    CHECK(filemover::decode_submit_request(
              "{\"source\": \"/a\", \"dest\": \"/b\"}garbage",
              req, error) == false);
    CHECK(error.find("trailing") != std::string::npos);

    CHECK(filemover::decode_submit_request(
              "{\"source\": \"/a\", \"dest\": \"/b\"} {}",
              req, error) == false);

    // Trailing whitespace alone is fine.
    CHECK(filemover::decode_submit_request(
              "{\"source\": \"/a\", \"dest\": \"/b\"} \t\r\n ",
              req, error) == true);
}

TEST_CASE("decode rejects embedded NUL in string members",
          "[codec][L3-CPP-026]") {
    SubmitRequest req;
    std::string error;

    // A path truncated at a NUL is the classic way to make a validated
    // string and an opened file disagree.
    const bool ok = filemover::decode_submit_request(
        "{\"source\": \"/a\\u0000/etc/passwd\", \"dest\": \"/b\"}",
        req, error);

    CHECK(ok == false);
    CHECK(error.find("NUL") != std::string::npos);
}

TEST_CASE("decode bounds path length at PATH_MAX", "[codec][L3-CPP-031]") {
    SubmitRequest req;
    std::string error;

    // 4096 is PATH_MAX including the NUL, so a path at or beyond it cannot
    // be opened. The inherited spec expected a 1 MiB path to be ACCEPTED,
    // deferring the size question entirely to the HTTP layer. That is
    // rejected here: accepting a path that provably cannot be used only
    // moves the failure somewhere with less context to explain it.
    const std::string huge(1024 * 1024, 'x');
    const std::string body =
        "{\"source\": \"/" + huge + "\", \"dest\": \"/b\"}";
    CHECK(filemover::decode_submit_request(body, req, error) == false);
    CHECK(error.empty() == false);

    // A long-but-usable path is still accepted.
    const std::string ok_path(3000, 'y');
    const std::string ok_body =
        "{\"source\": \"/" + ok_path + "\", \"dest\": \"/b\"}";
    CHECK(filemover::decode_submit_request(ok_body, req, error) == true);
    CHECK(req.source.size() == ok_path.size() + 1);
}

TEST_CASE("decode survives pathological input without crashing",
          "[codec][L3-CPP-028]") {
    SubmitRequest req;
    std::string error;

    // Deep nesting as an unknown member value must be rejected cleanly.
    std::string nest(4096, '[');
    nest += std::string(4096, ']');
    const std::string nested =
        "{\"source\": \"/a\", \"dest\": \"/b\", \"x\": " + nest + "}";
    CHECK(filemover::decode_submit_request(nested, req, error) == false);

    // Every prefix of a valid body is rejected, never accepted or fatal.
    const std::string valid = "{\"source\":\"/a\",\"dest\":\"/b\"}";
    for (std::size_t i = 0; i < valid.size(); ++i) {
        INFO("prefix length " << i);
        CHECK(filemover::decode_submit_request(valid.substr(0, i), req, error)
              == false);
    }

    // Deterministic byte soup: the contract is that it returns, not what it
    // returns.
    std::uint32_t seed = 0x2468aceu;
    for (int iteration = 0; iteration < 1000; ++iteration) {
        std::string s;
        const std::size_t len = 1 + (seed % 48);
        for (std::size_t i = 0; i < len; ++i) {
            seed = seed * 1103515245u + 12345u;
            s.push_back(static_cast<char>((seed >> 16) & 0xFF));
        }
        SubmitRequest scratch;
        std::string scratch_error;
        if (!filemover::decode_submit_request(s, scratch, scratch_error)) {
            CHECK(scratch_error.empty() == false);
        }
    }
}

TEST_CASE("encode_job emits every member and round-trips exactly",
          "[codec][L3-CPP-029][L3-CPP-030]") {
    Job job("job-7", "/in/tab\t.ch10", "/out/quote\"and\\slash", 1111);
    REQUIRE(job.transition(JobState::Renaming, 2222) == true);
    REQUIRE(job.transition(JobState::Failed, 3333,
                           "rename failed: \"EEXIST\"\n") == true);
    job.bytes_total = 9876543210u;   // > 32-bit, exercises the int64 path
    job.bytes_moved = 123u;

    const filemover::json::Value v = reparse(filemover::encode_job(job));

    REQUIRE(v.is_object() == true);
    CHECK(v.as_object().size() == 10u);
    CHECK(v.find("id")->as_string() == std::string("job-7"));
    CHECK(v.find("source")->as_string() == std::string("/in/tab\t.ch10"));
    CHECK(v.find("dest")->as_string() == std::string("/out/quote\"and\\slash"));
    CHECK(v.find("state")->as_string() == std::string("FAILED"));
    CHECK(v.find("created_at_ms")->as_int() == 1111);
    CHECK(v.find("updated_at_ms")->as_int() == 3333);
    CHECK(v.find("finished_at_ms")->as_int() == 3333);
    CHECK(v.find("bytes_total")->as_int() == 9876543210LL);
    CHECK(v.find("bytes_moved")->as_int() == 123);
    CHECK(v.find("error")->as_string() ==
          std::string("rename failed: \"EEXIST\"\n"));
}

TEST_CASE("encode_job clamps byte counters that exceed int64",
          "[codec][L3-CPP-029]") {
    // JSON integers are int64 (ADR-0009). A uint64 above that range would
    // wrap to negative if cast blindly; a negative byte count in an operator
    // dashboard is a bug report, so it clamps instead.
    Job job("j", "/a", "/b", 1);
    job.bytes_total = 18446744073709551615ull;  // UINT64_MAX

    const filemover::json::Value v = reparse(filemover::encode_job(job));
    CHECK(v.find("bytes_total")->as_int() == 9223372036854775807LL);
}

TEST_CASE("encode_job_list wraps jobs in a stable envelope", "[codec]") {
    std::vector<Job> jobs;
    jobs.push_back(Job("a", "/1", "/2", 10));
    jobs.push_back(Job("b", "/3", "/4", 20));

    const filemover::json::Value v =
        reparse(filemover::encode_job_list(jobs));

    const filemover::json::Value* list = v.find("jobs");
    REQUIRE(list != 0);
    REQUIRE(list->is_array() == true);
    REQUIRE(list->as_array().size() == 2u);
    CHECK(list->as_array()[0].find("id")->as_string() == std::string("a"));
    CHECK(list->as_array()[1].find("id")->as_string() == std::string("b"));
}

TEST_CASE("encode_job_list handles an empty collection", "[codec]") {
    const std::vector<Job> none;
    const filemover::json::Value v =
        reparse(filemover::encode_job_list(none));
    REQUIRE(v.find("jobs") != 0);
    CHECK(v.find("jobs")->as_array().empty() == true);
}

TEST_CASE("encode_error escapes hostile messages",
          "[codec][L3-CPP-030]") {
    const std::string hostile = "</script>\"quotes\" and \x01 control";
    const filemover::json::Value v =
        reparse(filemover::encode_error(hostile));
    CHECK(v.find("error")->as_string() == hostile);
}

TEST_CASE("encoded output survives a round-trip through the parser",
          "[codec][L3-CPP-030]") {
    // Whatever the codec emits must be readable by the parser that guards
    // the same interface. A divergence between them is a protocol bug that
    // only shows up against a real client.
    const char* nasty[] = {
        "plain",
        "with \"quotes\"",
        "with \\backslashes\\",
        "tab\there",
        "newline\nhere",
        "\xc3\xa9 accented",
        "\xf0\x9f\x98\x80 astral",
    };

    for (std::size_t i = 0; i < sizeof(nasty) / sizeof(nasty[0]); ++i) {
        Job job(nasty[i], nasty[i], nasty[i], 1);
        INFO("case " << i);
        const filemover::json::Value v = reparse(filemover::encode_job(job));
        CHECK(v.find("id")->as_string() == std::string(nasty[i]));
        CHECK(v.find("source")->as_string() == std::string(nasty[i]));
    }
}
