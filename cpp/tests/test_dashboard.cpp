// Operator dashboard tests (C7, L2-DASH-001..003).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// These assert against dashboard_html() -- the string the binary actually
// serves -- rather than against src/dashboard.cpp. scripts/assert-dashboard-safe.sh
// scans the source; this scans the artifact. Two checks of one rule on purpose:
// the gate can be deleted in a commit, and these cannot be satisfied by a page
// that is not the one shipped.

#include "catch2/catch.hpp"

#include "filemover/dashboard.hpp"

#include <cctype>
#include <string>

using filemover::dashboard_content_type;
using filemover::dashboard_html;

namespace {

// Case-insensitive substring search. The page is ASCII and this is test code,
// so <cctype> is fine here -- L3-CPP-052's locale rule governs the untrusted-
// input parsers in src/, not a test helper searching a compile-time constant.
bool contains_ci(const std::string& haystack, const std::string& needle) {
    if (needle.empty() || needle.size() > haystack.size()) {
        return false;
    }
    for (std::size_t i = 0; i + needle.size() <= haystack.size(); ++i) {
        std::size_t j = 0;
        while (j < needle.size() &&
               std::tolower(static_cast<unsigned char>(haystack[i + j])) ==
                   std::tolower(static_cast<unsigned char>(needle[j]))) {
            ++j;
        }
        if (j == needle.size()) {
            return true;
        }
    }
    return false;
}

}  // namespace

TEST_CASE("the served page never writes to an HTML-parsing sink",
          "[dashboard][L2-DASH-003]") {
    const std::string& page = dashboard_html();
    REQUIRE(page.empty() == false);

    // Each of these hands a string to the HTML parser. A filesystem path is
    // attacker-chosen input -- whoever can create a file names it -- and the
    // operator's browser holds the one session with authority over this
    // service. Checked against the artifact, so a page assembled some other
    // way in future is still covered.
    CHECK(contains_ci(page, "innerHTML") == false);
    CHECK(contains_ci(page, "outerHTML") == false);
    CHECK(contains_ci(page, "insertAdjacentHTML") == false);
    CHECK(contains_ci(page, "document.write") == false);
    CHECK(contains_ci(page, "srcdoc") == false);
}

TEST_CASE("the served page inserts values as text nodes",
          "[dashboard][L2-DASH-003]") {
    // The positive half. Banning the sinks proves nothing if the page also
    // stopped rendering data: a page that inserts nothing passes every
    // prohibition above.
    const std::string& page = dashboard_html();
    CHECK(page.find("textContent") != std::string::npos);
    CHECK(page.find("createTextNode") != std::string::npos);
}

TEST_CASE("the served page fetches nothing from the network",
          "[dashboard][L2-DASH-002]") {
    // L2-DASH-002. The service runs on an isolated network, so a page that
    // pulls a font or a stylesheet from a CDN is a page that renders blank
    // where it is deployed -- and hands a third party script execution in the
    // operator's browser where it does not.
    const std::string& page = dashboard_html();
    CHECK(page.find("http://") == std::string::npos);
    CHECK(page.find("https://") == std::string::npos);
    CHECK(page.find("@import") == std::string::npos);
    CHECK(contains_ci(page, "<link") == false);

    // The one request it does make is same-origin and relative.
    CHECK(page.find("\"/api/status\"") != std::string::npos);
}

TEST_CASE("the page is a complete standalone document",
          "[dashboard][L2-DASH-001][L2-DASH-002]") {
    const std::string& page = dashboard_html();
    CHECK(page.compare(0, 15, "<!DOCTYPE html>") == 0);
    CHECK(page.find("</html>") != std::string::npos);
    // Styles and script are inline, which is what "no external resources"
    // means in practice.
    CHECK(page.find("<style>") != std::string::npos);
    CHECK(page.find("<script>") != std::string::npos);
}

TEST_CASE("the page polls on a fixed interval", "[dashboard][L2-DASH-001]") {
    // L2-DASH-001 says a fixed interval, and it is a requirement rather than a
    // detail: an adaptive poll speeds up when the service is busiest, which is
    // when the bounded handler pool (ADR-0013) has least to spare.
    const std::string& page = dashboard_html();
    CHECK(page.find("setInterval") != std::string::npos);
}

TEST_CASE("the page is served as UTF-8 HTML", "[dashboard][L2-DASH-002]") {
    const std::string type = dashboard_content_type();
    CHECK(type.find("text/html") != std::string::npos);
    // Explicit charset. Without one a browser may sniff the encoding from
    // content, and text that is inert in UTF-8 need not be in whatever it
    // guesses instead.
    CHECK(contains_ci(type, "charset=utf-8") == true);
    CHECK(dashboard_html().find("<meta charset=\"utf-8\">") !=
          std::string::npos);
}
