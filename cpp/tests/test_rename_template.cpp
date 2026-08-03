// Rename template expansion tests.
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L3-CPP-042..045

#include "catch2/catch.hpp"

#include "filemover/rename_template.hpp"

#include <string>

using filemover::RenameContext;

namespace {

std::string expand(const std::string& templ,
                   const std::string& name,
                   std::int64_t at_ms = 0,
                   std::uint64_t seq = 0) {
    RenameContext ctx;
    ctx.at_ms = at_ms;
    ctx.sequence = seq;

    std::string out;
    std::string error;
    INFO("template: " << templ << "  name: " << name);
    REQUIRE(filemover::expand_rename_template(templ, name, ctx, out, error)
            == true);
    CHECK(error.empty() == true);
    return out;
}

bool rejects(const std::string& templ, const std::string& name) {
    RenameContext ctx;
    std::string out = "sentinel";
    std::string error;
    const bool ok =
        filemover::expand_rename_template(templ, name, ctx, out, error);
    if (!ok) {
        CHECK(error.empty() == false);
        CHECK(out == std::string("sentinel"));  // unmodified on failure
    }
    return !ok;
}

}  // namespace

TEST_CASE("expands every documented field", "[rename][L3-CPP-042]") {
    CHECK(expand("{name}", "a.tar.gz") == std::string("a.tar.gz"));
    CHECK(expand("{stem}", "a.tar.gz") == std::string("a.tar"));
    CHECK(expand("{ext}", "a.tar.gz") == std::string("gz"));
    CHECK(expand("{stem}-copy.{ext}", "a.tar.gz") ==
          std::string("a.tar-copy.gz"));
    CHECK(expand("literal", "a.dat") == std::string("literal"));
}

TEST_CASE("a leading dot is not an extension separator",
          "[rename][L3-CPP-042]") {
    // ".bashrc" is all stem and no extension. The alternative reading makes
    // {stem} expand to empty, which L3-CPP-044 then rejects — a confusing
    // failure for an ordinary filename.
    CHECK(expand("{stem}", ".bashrc") == std::string(".bashrc"));
    CHECK(expand("{stem}", "README") == std::string("README"));

    // {ext} is empty for both, so it is checked with a literal prefix rather
    // than alone: a bare "{ext}" expands to the empty string, which
    // L3-CPP-044 rejects outright. Asserting it "expands to empty" would be
    // asserting behavior the requirement forbids — the exact error the
    // inherited milestone logged against its own test suite, reproduced here
    // before being caught the same way.
    CHECK(expand("x{ext}", ".bashrc") == std::string("x"));
    CHECK(expand("x{ext}", "README") == std::string("x"));
}

TEST_CASE("timestamps render as UTC from the supplied millis",
          "[rename][L3-CPP-042][L3-CPP-045]") {
    // Cross-checked against:  date -u -d @1754040615 +%Y%m%dT%H%M%S
    // 1754040615250 ms = 2025-08-01T09:30:15.250Z
    CHECK(expand("{ts}", "x", 1754040615250LL) ==
          std::string("20250801T093015.250"));

    // The epoch itself, as a fixed point that cannot drift with the clock.
    CHECK(expand("{ts}", "x", 0) == std::string("19700101T000000.000"));

    // No clock is read: the same inputs always give the same output.
    CHECK(expand("{ts}", "x", 1754040615250LL) ==
          expand("{ts}", "x", 1754040615250LL));
}

TEST_CASE("sequence is zero-padded to six digits", "[rename][L3-CPP-042]") {
    CHECK(expand("{seq}", "x", 0, 0) == std::string("000000"));
    CHECK(expand("{seq}", "x", 0, 42) == std::string("000042"));
    CHECK(expand("{seq}", "x", 0, 999999) == std::string("999999"));
    // Beyond six digits it widens rather than truncating — a truncated
    // sequence would silently collide with an earlier one.
    CHECK(expand("{seq}", "x", 0, 1234567) == std::string("1234567"));
}

TEST_CASE("malformed templates are rejected by name",
          "[rename][L3-CPP-043]") {
    CHECK(rejects("{nosuch}", "a.dat") == true);
    CHECK(rejects("{name", "a.dat") == true);       // unclosed
    CHECK(rejects("name}", "a.dat") == true);       // stray close
    CHECK(rejects("{}", "a.dat") == true);          // empty field
    CHECK(rejects("{NAME}", "a.dat") == true);      // case-sensitive
    CHECK(rejects("{name}{", "a.dat") == true);
}

TEST_CASE("an expansion that could escape its directory is rejected",
          "[rename][L3-CPP-044]") {
    // Validating the RESULT rather than only the template is what makes this
    // airtight: every field below is legal, and the escape comes from the
    // source filename flowing through it.
    CHECK(rejects("{name}", "../evil") == true);
    CHECK(rejects("{name}", "a/b") == true);
    CHECK(rejects("{stem}", "..") == true);
    CHECK(rejects("..", "a.dat") == true);
    CHECK(rejects(".", "a.dat") == true);
    CHECK(rejects("", "a.dat") == true);            // empty result
    CHECK(rejects("{ext}", "noextension") == true); // expands to empty

    std::string with_nul = "a";
    with_nul.push_back('\0');
    with_nul += "b";
    CHECK(rejects("{name}", with_nul) == true);
}

TEST_CASE("expansion never crashes on arbitrary input",
          "[rename][L3-CPP-045]") {
    std::uint32_t seed = 0x5eed1234u;
    for (int iteration = 0; iteration < 2000; ++iteration) {
        std::string templ;
        std::string name;
        const std::size_t tl = seed % 24;
        const std::size_t nl = 1 + ((seed >> 8) % 24);
        for (std::size_t i = 0; i < tl; ++i) {
            seed = seed * 1103515245u + 12345u;
            templ.push_back(static_cast<char>((seed >> 16) & 0xFF));
        }
        for (std::size_t i = 0; i < nl; ++i) {
            seed = seed * 1103515245u + 12345u;
            name.push_back(static_cast<char>((seed >> 16) & 0xFF));
        }

        RenameContext ctx;
        std::string out;
        std::string error;
        // The contract is that it returns, not what it returns.
        if (!filemover::expand_rename_template(templ, name, ctx, out, error)) {
            CHECK(error.empty() == false);
        }
    }
}
