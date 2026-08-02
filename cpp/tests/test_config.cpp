// Configuration loader tests.
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L3-CPP-033..040, L2-CFG-001..011
//
// The whole validation matrix runs without touching a disk, because
// load_config_from_string performs no I/O (L3-CPP-040). Only the two
// filesystem-facing cases at the end need real paths.

#include "catch2/catch.hpp"

#include "filemover/config.hpp"

#include <string>
#include <vector>

using filemover::Config;

namespace {

// Minimal text that validates, for tests that need a valid baseline.
const char* kMinimal = "[storage]\ndatabase_path = /var/lib/fm/state.db\n";

bool accepts(const std::string& text) {
    Config cfg;
    std::string error;
    const bool ok =
        filemover::load_config_from_string(text, "test.ini", cfg, error);
    if (!ok) {
        INFO("error: " << error);
        CHECK(error.empty() == false);
    }
    return ok;
}

std::string error_for(const std::string& text) {
    Config cfg;
    std::string error;
    const bool ok =
        filemover::load_config_from_string(text, "test.ini", cfg, error);
    CHECK(ok == false);
    return error;
}

std::size_t issue_count(const std::string& error) {
    if (error.empty()) return 0;
    std::size_t n = 1;
    for (std::size_t i = 0; i < error.size(); ++i) {
        if (error[i] == '\n') ++n;
    }
    return n;
}

}  // namespace

TEST_CASE("accepts a minimal valid configuration", "[config][L3-CPP-033]") {
    Config cfg;
    std::string error;
    REQUIRE(filemover::load_config_from_string(kMinimal, "test.ini", cfg,
                                               error) == true);
    CHECK(error.empty() == true);
    CHECK(cfg.storage_database_path == std::string("/var/lib/fm/state.db"));
}

TEST_CASE("applies documented defaults for every optional parameter",
          "[config][L3-CPP-039]") {
    Config cfg;
    std::string error;
    REQUIRE(filemover::load_config_from_string(kMinimal, "test.ini", cfg,
                                               error) == true);

    CHECK(cfg.http_bind == std::string("127.0.0.1"));
    CHECK(cfg.http_port == 8080);
    CHECK(cfg.http_max_body_bytes == 65536u);
    CHECK(cfg.jobs_workers == 4u);
}

TEST_CASE("the bind default is loopback", "[config][L3-CPP-039]") {
    // Not a style preference. v1.0.0 ships no authentication, so the bind
    // address is the only access control there is (see the security note in
    // docs/L1-REQ.md). A default of 0.0.0.0 would expose an unauthenticated
    // control plane to the network on first start.
    Config cfg;
    std::string error;
    REQUIRE(filemover::load_config_from_string(kMinimal, "test.ini", cfg,
                                               error) == true);
    CHECK(cfg.http_bind == std::string("127.0.0.1"));
}

TEST_CASE("accepts the documented syntax", "[config][L3-CPP-033]") {
    CHECK(accepts("; leading comment\n"
                  "# hash comment too\n"
                  "\n"
                  "[http]\n"
                  "  bind = 0.0.0.0\n"
                  "  port=9000\n"
                  "\n"
                  "[jobs]\n"
                  "workers = 8\n"
                  "\n"
                  "[storage]\n"
                  "database_path = /var/lib/fm/state.db\n") == true);

    // Values may contain '=' and spaces.
    Config cfg;
    std::string error;
    REQUIRE(filemover::load_config_from_string(
                "[storage]\ndatabase_path = /var/lib/a b=c/state.db\n",
                "test.ini", cfg, error) == true);
    CHECK(cfg.storage_database_path ==
          std::string("/var/lib/a b=c/state.db"));
}

TEST_CASE("inline comments are not supported", "[config][L3-CPP-033]") {
    // A ';' after a value is part of the value, not a comment. Documented
    // rather than implemented, so it is pinned here: silently truncating a
    // path at a ';' would be far worse than keeping it.
    Config cfg;
    std::string error;
    REQUIRE(filemover::load_config_from_string(
                "[storage]\ndatabase_path = /var/db ; not a comment\n",
                "test.ini", cfg, error) == true);
    CHECK(cfg.storage_database_path ==
          std::string("/var/db ; not a comment"));
}

TEST_CASE("every line-level error is reported as origin:line: message",
          "[config][L3-CPP-034]") {
    const std::string error = error_for(
        "[storage]\n"
        "database_path = /ok\n"
        "bogus_key = 1\n");
    CHECK(error == std::string(
                       "test.ini:3: unknown key \"bogus_key\" in [storage]"));
}

TEST_CASE("all issues are reported together, not just the first",
          "[config][L3-CPP-035]") {
    // L2-CFG-008. An operator editing a config by hand should learn
    // everything wrong with it in one run, rather than discovering the next
    // fault only after fixing the previous one and restarting.
    const std::string error = error_for(
        "[http]\n"
        "port = 99999\n"          // out of range
        "unknown_one = x\n"       // unknown key
        "[nosuch]\n"              // unknown section
        "[jobs]\n"
        "workers = abc\n"         // not an integer
        "[storage]\n"
        "database_path = /ok\n");

    CHECK(issue_count(error) == 4u);
    CHECK(error.find("test.ini:2:") != std::string::npos);
    CHECK(error.find("test.ini:3:") != std::string::npos);
    CHECK(error.find("test.ini:4:") != std::string::npos);
    CHECK(error.find("test.ini:6:") != std::string::npos);
}

TEST_CASE("a missing required parameter is named", "[config][L3-CPP-039]") {
    const std::string error = error_for("[http]\nport = 9000\n");
    CHECK(error.find("storage.database_path") != std::string::npos);
    CHECK(error.find("missing required parameter") != std::string::npos);
}

TEST_CASE("unknown sections and keys are rejected", "[config][L3-CPP-036]") {
    CHECK(accepts("[nope]\nx = 1\n") == false);
    CHECK(accepts("[http]\nnot_a_key = 1\n") == false);
    // The schema is deliberately closed. [rename] and [transfer] arrive with
    // their milestones, by coordinated change, not by loosening this.
    CHECK(accepts("[rename]\ntemplate = x\n") == false);
    CHECK(accepts("[transfer]\nstrategy = copy\n") == false);
}

TEST_CASE("duplicates are rejected", "[config][L3-CPP-037]") {
    CHECK(accepts("[storage]\ndatabase_path = /a\ndatabase_path = /b\n")
          == false);
    CHECK(accepts("[http]\nport = 1\n[http]\nbind = 1.2.3.4\n") == false);
    // The same key name in different sections is fine.
    CHECK(accepts("[http]\nport = 80\n[storage]\ndatabase_path = /a\n")
          == true);
}

TEST_CASE("malformed lines are rejected", "[config][L3-CPP-034]") {
    CHECK(accepts("[storage\ndatabase_path = /a\n") == false);  // unterminated
    CHECK(accepts("[]\ndatabase_path = /a\n") == false);        // empty name
    CHECK(accepts("[ ]\ndatabase_path = /a\n") == false);       // whitespace
    CHECK(accepts("no_section_yet = 1\n") == false);
    CHECK(accepts("[storage]\njust_a_word\n") == false);        // no '='
    CHECK(accepts("[storage]\n = value\n") == false);           // empty key
}

TEST_CASE("an unterminated section header says so precisely",
          "[config][L3-CPP-034]") {
    // The inherited notes recorded a test-expectation bug here: an
    // unterminated "[storage" produces "malformed section header", which is
    // more precise than a generic parse failure. Pinned so it stays precise.
    const std::string error = error_for("[storage\n");
    CHECK(error.find("malformed section header") != std::string::npos);
    CHECK(error.find("test.ini:1:") != std::string::npos);
}

TEST_CASE("integers parse strictly", "[config][L3-CPP-038]") {
    CHECK(accepts("[http]\nport = 80x\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = 0x50\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = 80.0\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = -1\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = +80\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = \n[storage]\ndatabase_path=/a\n") == false);
    CHECK(accepts("[http]\nport = 80\n[storage]\ndatabase_path=/a\n")
          == true);
}

TEST_CASE("integer ranges are enforced at both ends",
          "[config][L3-CPP-038]") {
    CHECK(accepts("[http]\nport = 0\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = 65536\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[http]\nport = 65535\n[storage]\ndatabase_path=/a\n")
          == true);

    CHECK(accepts("[jobs]\nworkers = 0\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[jobs]\nworkers = 65\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts("[jobs]\nworkers = 64\n[storage]\ndatabase_path=/a\n")
          == true);

    CHECK(accepts("[http]\nmax_body_bytes = 0\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts(
              "[http]\nmax_body_bytes = 16777217\n[storage]\ndatabase_path=/a\n")
          == false);
    CHECK(accepts(
              "[http]\nmax_body_bytes = 16777216\n[storage]\ndatabase_path=/a\n")
          == true);
}

TEST_CASE("an embedded NUL in the database path is rejected",
          "[config][L3-CPP-036]") {
    // The inherited header promised this check and never implemented it. A
    // NUL truncates the path anywhere it reaches a C API, so the validated
    // string and the opened file would differ.
    std::string text = "[storage]\ndatabase_path = /var/lib/fm";
    text.push_back('\0');
    text += "/evil.db\n";
    CHECK(accepts(text) == false);
}

TEST_CASE("http.bind rejects empty and whitespace-bearing values",
          "[config][L3-CPP-036]") {
    CHECK(accepts("[http]\nbind = \n[storage]\ndatabase_path=/a\n") == false);
    CHECK(accepts("[http]\nbind = 1.2.3.4 5\n[storage]\ndatabase_path=/a\n")
          == false);
}

TEST_CASE("the output is left unmodified on any rejection",
          "[config][L3-CPP-035]") {
    Config cfg;
    cfg.http_port = 4242;
    cfg.storage_database_path = "sentinel";
    std::string error;

    CHECK(filemover::load_config_from_string("[http]\nport = 99999\n",
                                             "test.ini", cfg, error) == false);
    CHECK(cfg.http_port == 4242);
    CHECK(cfg.storage_database_path == std::string("sentinel"));
}

TEST_CASE("arbitrary input never crashes the loader",
          "[config][L3-CPP-033]") {
    std::uint32_t seed = 0x13572468u;
    for (int iteration = 0; iteration < 2000; ++iteration) {
        std::string s;
        const std::size_t len = 1 + (seed % 96);
        for (std::size_t i = 0; i < len; ++i) {
            seed = seed * 1103515245u + 12345u;
            s.push_back(static_cast<char>((seed >> 16) & 0xFF));
        }
        Config cfg;
        std::string error;
        // The contract is that it returns, not what it returns.
        if (!filemover::load_config_from_string(s, "fuzz.ini", cfg, error)) {
            CHECK(error.empty() == false);
        }
    }
}

// --- filesystem-facing (L2-JOB-008) --------------------------------------

TEST_CASE("network filesystem magics are classified correctly",
          "[config][L3-CPP-040]") {
    // Split out from the statfs call so it is exhaustively testable without
    // an NFS mount, which CI does not have.
    CHECK(filemover::is_network_filesystem_magic(0x6969UL) == true);      // NFS
    CHECK(filemover::is_network_filesystem_magic(0xFF534D42UL) == true);  // CIFS
    CHECK(filemover::is_network_filesystem_magic(0x01161970UL) == true);  // GFS2
    CHECK(filemover::is_network_filesystem_magic(0x0BD00BD0UL) == true);  // Lustre

    // Local filesystems must NOT be flagged. A false positive refuses to
    // start on a perfectly good volume, which is worse than the failure
    // being prevented.
    CHECK(filemover::is_network_filesystem_magic(0xEF53UL) == false);      // ext4
    CHECK(filemover::is_network_filesystem_magic(0x58465342UL) == false);  // xfs
    CHECK(filemover::is_network_filesystem_magic(0x9123683EUL) == false);  // btrfs
    CHECK(filemover::is_network_filesystem_magic(0x01021994UL) == false);  // tmpfs
    CHECK(filemover::is_network_filesystem_magic(0UL) == false);
}

TEST_CASE("a local path passes the storage location check",
          "[config][L3-CPP-040]") {
    std::string reason;
    // /tmp is local in every environment this runs in.
    CHECK(filemover::storage_path_is_local("/tmp", reason) == true);
    CHECK(reason.empty() == true);
}

TEST_CASE("an unresolvable storage path is reported, not assumed local",
          "[config][L3-CPP-040]") {
    std::string reason;
    CHECK(filemover::storage_path_is_local("/no/such/path/anywhere", reason)
          == false);
    CHECK(reason.empty() == false);
}
