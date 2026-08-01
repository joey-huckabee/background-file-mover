// M2 test suite: JSON codec boundary + picojson characterization.
// Assertions use natural order: actual == expected.

#define PICOJSON_USE_INT64
#include <picojson/picojson.h>   // characterization tests only (L2-JSON-003)

#include "catch2/catch.hpp"
#include "filemover/api_codec.hpp"

using filemover::Job;
using filemover::JobState;
using filemover::SubmitRequest;

TEST_CASE("decode accepts exactly {source, dest} with non-empty strings",
          "[m2][L3-CPP-016]") {
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
          "[m2][L3-CPP-017][L3-CPP-019]") {
    struct Case {
        const char* name;
        const char* body;
    };
    const Case cases[] = {
        {"empty body", ""},
        {"truncated object", "{\"source\": \"/a\", \"dest\""},
        {"garbage bytes", "\x01\x02\x03\x04"},
        {"top-level array", "[\"/a\", \"/b\"]"},
        {"top-level string", "\"/a\""},
        {"top-level number", "42"},
        {"missing source", "{\"dest\": \"/b\"}"},
        {"missing dest", "{\"source\": \"/a\"}"},
        {"source wrong type", "{\"source\": 5, \"dest\": \"/b\"}"},
        {"dest wrong type", "{\"source\": \"/a\", \"dest\": null}"},
        {"empty source", "{\"source\": \"\", \"dest\": \"/b\"}"},
        {"empty dest", "{\"source\": \"/a\", \"dest\": \"\"}"},
        {"unknown member",
         "{\"source\": \"/a\", \"dest\": \"/b\", \"mode\": \"fast\"}"},
        {"nested unknown first",
         "{\"overwrite\": true, \"source\": \"/a\", \"dest\": \"/b\"}"},
    };

    for (const Case& c : cases) {
        SubmitRequest req;
        req.source = "sentinel-src";
        req.dest = "sentinel-dst";
        std::string error;

        INFO(c.name);
        CHECK(filemover::decode_submit_request(c.body, req, error) == false);
        CHECK(error.empty() == false);
        CHECK(req.source == "sentinel-src");
        CHECK(req.dest == "sentinel-dst");
    }
}

TEST_CASE("decode rejects trailing content after the JSON value",
          "[m2][L3-CPP-024]") {
    SubmitRequest req;
    std::string error;

    CHECK(filemover::decode_submit_request(
              "{\"source\": \"/a\", \"dest\": \"/b\"}garbage",
              req, error) == false);
    CHECK(error == "trailing content after JSON value");

    CHECK(filemover::decode_submit_request(
              "{\"source\": \"/a\", \"dest\": \"/b\"} {}",
              req, error) == false);

    // Trailing whitespace alone is fine.
    CHECK(filemover::decode_submit_request(
              "{\"source\": \"/a\", \"dest\": \"/b\"} \t\r\n ",
              req, error) == true);
}

TEST_CASE("decode rejects embedded NUL in string members",
          "[m2][L3-CPP-018]") {
    SubmitRequest req;
    std::string error;

    const bool ok = filemover::decode_submit_request(
        "{\"source\": \"/a\\u0000/etc/passwd\", \"dest\": \"/b\"}",
        req, error);

    CHECK(ok == false);
    CHECK(error.find("NUL") != std::string::npos);
}

TEST_CASE("decode survives pathological input sizes", "[m2][L3-CPP-020]") {
    SubmitRequest req;
    std::string error;

    // Very long single token (1 MiB path). Size policy is HTTP-level
    // (L1-013); the codec itself must simply not misbehave.
    const std::string long_path(1024 * 1024, 'x');
    const std::string body =
        "{\"source\": \"/" + long_path + "\", \"dest\": \"/b\"}";
    CHECK(filemover::decode_submit_request(body, req, error) == true);
    CHECK(req.source.size() == long_path.size() + 1);

    // Deeply nested arrays as an unknown member value must be rejected
    // cleanly, not crash.
    std::string nest(4096, '[');
    nest += std::string(4096, ']');
    const std::string nested_body =
        "{\"source\": \"/a\", \"dest\": \"/b\", \"x\": " + nest + "}";
    CHECK(filemover::decode_submit_request(nested_body, req, error) == false);
}

TEST_CASE("encode_job emits every member and round-trips exactly",
          "[m2][L3-CPP-022][L3-CPP-023]") {
    Job job("job-7", "/in/tab\t.ch10", "/out/quote\"and\\slash", 1111);
    job.transition(JobState::Renaming, 2222);
    job.transition(JobState::Failed, 3333, "rename failed: \"EEXIST\"\n");
    job.bytes_total = 9876543210u;   // > 32-bit to exercise int64 path
    job.bytes_moved = 123u;

    const std::string encoded = filemover::encode_job(job);

    picojson::value v;
    const std::string parse_err = picojson::parse(v, encoded);
    REQUIRE(parse_err.empty() == true);
    REQUIRE(v.is<picojson::object>() == true);
    const picojson::object& o = v.get<picojson::object>();

    CHECK(o.size() == 10u);
    CHECK(o.at("id").get<std::string>() == "job-7");
    CHECK(o.at("source").get<std::string>() == "/in/tab\t.ch10");
    CHECK(o.at("dest").get<std::string>() == "/out/quote\"and\\slash");
    CHECK(o.at("state").get<std::string>() == "FAILED");
    CHECK(o.at("created_at_ms").get<std::int64_t>() == 1111);
    CHECK(o.at("updated_at_ms").get<std::int64_t>() == 3333);
    CHECK(o.at("finished_at_ms").get<std::int64_t>() == 3333);
    CHECK(o.at("bytes_total").get<std::int64_t>() == 9876543210);
    CHECK(o.at("bytes_moved").get<std::int64_t>() == 123);
    CHECK(o.at("error").get<std::string>() == "rename failed: \"EEXIST\"\n");
}

TEST_CASE("encode_job_list wraps jobs in a stable envelope", "[m2]") {
    std::vector<Job> jobs;
    jobs.push_back(Job("a", "/1", "/2", 10));
    jobs.push_back(Job("b", "/3", "/4", 20));

    picojson::value v;
    REQUIRE(picojson::parse(v, filemover::encode_job_list(jobs)).empty() ==
            true);
    const picojson::array& arr =
        v.get<picojson::object>().at("jobs").get<picojson::array>();
    CHECK(arr.size() == 2u);
    CHECK(arr[0].get<picojson::object>().at("id").get<std::string>() == "a");
    CHECK(arr[1].get<picojson::object>().at("id").get<std::string>() == "b");
}

TEST_CASE("encode_error escapes hostile messages", "[m2][L3-CPP-023]") {
    const std::string hostile = "</script>\"quotes\" and \x01 control";
    picojson::value v;
    REQUIRE(picojson::parse(v, filemover::encode_error(hostile)).empty() ==
            true);
    CHECK(v.get<picojson::object>().at("error").get<std::string>() == hostile);
}

// --- picojson characterization (L2-JSON-003): pin the vendored behaviors
// --- the codec relies on, so a future tag bump fails loudly.

TEST_CASE("picojson: parse error reporting is non-empty on malformed input",
          "[m2][characterization]") {
    picojson::value v;
    CHECK(picojson::parse(v, std::string("{\"a\":")).empty() == false);
    CHECK(picojson::parse(v, std::string("nul")).empty() == false);
    // Pinned finding: the string-overload of parse() stops at the end of
    // the first JSON value and reports NO error for trailing bytes. The
    // codec compensates (L3-CPP-024). If a future tag bump changes this,
    // this assertion fails loudly and the codec check gets revisited.
    CHECK(picojson::parse(v, std::string("{}trailing")).empty() == true);
}

TEST_CASE("picojson: integers survive int64 round-trip under "
          "PICOJSON_USE_INT64",
          "[m2][characterization]") {
    picojson::value v;
    REQUIRE(picojson::parse(v, std::string("9007199254740993")).empty() ==
            true);
    REQUIRE(v.is<std::int64_t>() == true);
    CHECK(v.get<std::int64_t>() == 9007199254740993LL);  // 2^53 + 1
}

TEST_CASE("picojson: invalid escape sequences and bare control characters "
          "are rejected",
          "[m2][characterization]") {
    picojson::value v;
    CHECK(picojson::parse(v, std::string("\"bad \\q escape\"")).empty() ==
          false);
    std::string bare_ctl = "\"a";
    bare_ctl += '\x01';
    bare_ctl += "b\"";
    CHECK(picojson::parse(v, bare_ctl).empty() == false);
}

TEST_CASE("picojson: serialize escapes quotes, backslashes, and controls",
          "[m2][characterization]") {
    const std::string original = "q\"b\\c\tnl\nend";
    const std::string serialized = picojson::value(original).serialize();

    CHECK(serialized.find('\t') == std::string::npos);
    CHECK(serialized.find('\n') == std::string::npos);

    picojson::value back;
    REQUIRE(picojson::parse(back, serialized).empty() == true);
    CHECK(back.get<std::string>() == original);
}
