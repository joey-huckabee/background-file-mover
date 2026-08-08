#ifndef FILEMOVER_DASHBOARD_HPP
#define FILEMOVER_DASHBOARD_HPP

// C7: the operator dashboard.
//
// Traces: L2-DASH-001, L2-DASH-002, L2-DASH-003
//
// One embedded page, served from the binary. No file is read at runtime and no
// resource is fetched from the network (L2-DASH-002): the service is deployed
// as a single executable (L1-SYS-002), so a dashboard that loaded a stylesheet
// from a CDN would be a dashboard that goes blank on the isolated network this
// runs on -- and would hand a third party the ability to run script in the one
// browser session with authority over this service.
//
// L2-DASH-003 IS THE REASON THIS FILE HAS A GATE. Every dynamic value reaching
// the page is a filesystem path or an error string, and a path is
// attacker-influenced in exactly the way the L1-SEC invariants already assume:
// whoever can create a file chooses its name. Assigning such a name to
// innerHTML is script execution in the operator's browser. The page therefore
// inserts text through textContent and createTextNode ONLY -- which removes the
// injection path rather than escaping it, so there is no escaping function left
// to get wrong. scripts/assert-dashboard-safe.sh fails the build if innerHTML,
// outerHTML, document.write, insertAdjacentHTML or eval ever appear here.

#include <string>

namespace filemover {

// The page itself: a complete HTML document, self-contained.
//
// Returned by reference to a static string rather than built per request. It is
// constant, it is served on every dashboard load, and copying ~8 KB per request
// to hand back a value would be work done for nothing.
const std::string& dashboard_html();

// The Content-Type the page is served with, including the charset.
//
// Explicit and always UTF-8. Without a charset a browser may sniff the encoding
// from content, and a path crafted to look like a different encoding is one of
// the ways text that was safely escaped in one charset stops being safe in
// another. It is a smaller hole than innerHTML and it closes the same way:
// leave the browser nothing to decide.
const char* dashboard_content_type();

}  // namespace filemover

#endif  // FILEMOVER_DASHBOARD_HPP
