// Route table tests (C5).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-CTL-005, L2-CTL-014
//
// Not one socket in this file. That is L2-CTL-014 being useful rather than
// merely satisfied: the error matrix is the part of a routing layer that rots
// unnoticed, and it is exercised here at the cost of a function call.

#include "catch2/catch.hpp"

#include "filemover/router.hpp"

#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#include <string>

using filemover::CommandResult;
using filemover::Config;
using filemover::JobManager;
using filemover::route_request;
using filemover::status_for;
using filemover::http::Request;
using filemover::http::Response;

namespace {

Request make_request(const std::string& method, const std::string& target) {
    Request r;
    r.method = method;
    r.target = target;
    r.version = "HTTP/1.1";
    return r;
}

// A manager over a throwaway database. Started only where the test needs the
// difference between "running" and "not".
class ManagerFixture {
  public:
    ManagerFixture() {
        char tmpl[] = "/tmp/fm-router-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        root_ = made;
        manager_ = new JobManager(db(), config());
    }

    ~ManagerFixture() {
        manager_->shutdown();
        delete manager_;
        ::unlink((db() + "-wal").c_str());
        ::unlink((db() + "-shm").c_str());
        ::unlink(db().c_str());
        ::rmdir(root_.c_str());
    }

    JobManager& manager() { return *manager_; }
    std::string db() const { return root_ + "/state.db"; }

    void start() {
        std::string error;
        REQUIRE(manager_->start(error) == true);
    }

  private:
    ManagerFixture(const ManagerFixture&);
    ManagerFixture& operator=(const ManagerFixture&);

    Config config() const {
        Config c;
        c.jobs_workers = 1;
        c.storage_database_path = db();
        return c;
    }

    std::string root_;
    JobManager* manager_;
};

}  // namespace

TEST_CASE("every CommandResult maps to a status", "[router][L2-CTL-005]") {
    // A total function over the enum. CommandResult was made typed in C4 so
    // this could be exactly that, rather than prose parsed from an error.
    CHECK(status_for(CommandResult::Ok) == 200);
    CHECK(status_for(CommandResult::UnknownJob) == 404);
    CHECK(status_for(CommandResult::InvalidState) == 409);
    CHECK(status_for(CommandResult::NotRunning) == 503);
    CHECK(status_for(CommandResult::StoreError) == 500);
}

TEST_CASE("health is answered without touching the manager",
          "[router][L2-CTL-012]") {
    ManagerFixture fx;  // deliberately not started
    const Response r = route_request(make_request("GET", "/healthz"),
                                     fx.manager());
    CHECK(r.status == 200);
    CHECK(r.body.find("ok") != std::string::npos);

    // A liveness probe that queried the store would report the store's health
    // and fail during exactly the incident it exists to survive.
    const Response head = route_request(make_request("HEAD", "/healthz"),
                                        fx.manager());
    CHECK(head.status == 200);
}

TEST_CASE("an unknown route is 404 with a JSON body", "[router][L2-CTL-005]") {
    ManagerFixture fx;
    // "/api/jobs" is deliberately absent: it is a real route now (POST creates
    // a job), and a GET against it answers 405 rather than 404.
    //
    // "/" left this list in C7 for the same reason -- it serves the dashboard.
    // "/api/status" likewise. Both have their own cases below.
    const char* targets[] = {"/nope", "/api", "/api/statuses",
                             "/api/jobs/id", "/api/jobs/id/frobnicate",
                             "/api/jobs/id/pause/extra"};
    for (std::size_t i = 0; i < 6; ++i) {
        INFO("target " << targets[i]);
        const Response r =
            route_request(make_request("GET", targets[i]), fx.manager());
        CHECK(r.status == 404);
        CHECK(r.content_type == std::string("application/json"));
        CHECK(r.body.empty() == false);
    }
}

TEST_CASE("a known route with the wrong method is 405 and says Allow",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;
    fx.start();

    const char* methods[] = {"GET", "PUT", "DELETE", "PATCH"};
    for (std::size_t i = 0; i < 4; ++i) {
        INFO("method " << methods[i]);
        const Response r = route_request(
            make_request(methods[i], "/api/jobs/abc/pause"), fx.manager());
        CHECK(r.status == 405);
        // Without Allow a client cannot tell what the route does take. 405 is
        // "you asked the wrong way"; the header is what makes that actionable.
        CHECK(r.allow == std::string("POST"));
    }

    const Response health =
        route_request(make_request("POST", "/healthz"), fx.manager());
    CHECK(health.status == 405);
    CHECK(health.allow.find("GET") != std::string::npos);
}

TEST_CASE("lifecycle commands on an unknown job are 404",
          "[router][L2-CTL-005][L2-LIF-005]") {
    ManagerFixture fx;
    fx.start();

    const char* actions[] = {"pause", "resume", "cancel", "retry"};
    for (std::size_t i = 0; i < 4; ++i) {
        INFO("action " << actions[i]);
        const std::string target =
            std::string("/api/jobs/ghost/") + actions[i];
        const Response r =
            route_request(make_request("POST", target), fx.manager());
        CHECK(r.status == 404);
        CHECK(r.body.empty() == false);
    }
}

TEST_CASE("POST /api/jobs creates a job and answers 202 with its id",
          "[router][L2-CTL-005][L2-JOB-015]") {
    ManagerFixture fx;
    fx.start();

    Request r = make_request("POST", "/api/jobs");
    r.body = "{\"source\":\"/src/a.dat\",\"dest\":\"/dst/a.dat\"}";
    const Response response = route_request(r, fx.manager());

    // 202, not 200: the job is recorded and queued, and the move has not
    // happened. 200 would tell a client the file had already moved.
    CHECK(response.status == 202);
    CHECK(response.body.find("job_id") != std::string::npos);

    // A second submission must get a DIFFERENT id. The sequence is committed
    // before it is handed out, so a repeat would let a new job overwrite the
    // record of an old one -- which is the whole reason L2-JOB-015 exists.
    const Response second = route_request(r, fx.manager());
    CHECK(second.status == 202);
    CHECK(second.body != response.body);
}

TEST_CASE("POST /api/jobs rejects malformed and non-absolute paths",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;
    fx.start();

    const char* bodies[] = {
        "not json at all",
        "{",
        "{\"source\":\"relative/a\",\"dest\":\"/dst/a\"}",
        "{\"source\":\"/src/a\",\"dest\":\"relative/a\"}",
        // A trailing slash names a directory where a file was required, and
        // accepting it would build a move with an empty source name.
        "{\"source\":\"/src/\",\"dest\":\"/dst/a\"}",
    };
    for (std::size_t i = 0; i < 5; ++i) {
        INFO("body " << bodies[i]);
        Request r = make_request("POST", "/api/jobs");
        r.body = bodies[i];
        const Response response = route_request(r, fx.manager());
        CHECK(response.status == 400);
        CHECK(response.body.find('{') != std::string::npos);
    }
}

TEST_CASE("GET /api/jobs is 405 with Allow, not 404",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;
    fx.start();
    const Response r =
        route_request(make_request("GET", "/api/jobs"), fx.manager());
    CHECK(r.status == 405);
    CHECK(r.allow == std::string("POST"));
}

TEST_CASE("creating a job against a stopped manager is 503",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;  // never started
    Request r = make_request("POST", "/api/jobs");
    r.body = "{\"source\":\"/src/a\",\"dest\":\"/dst/a\"}";
    const Response response = route_request(r, fx.manager());
    // Checked before a sequence number is allocated, so a command against a
    // stopped manager does not burn an id to find that out.
    CHECK(response.status == 503);
}

TEST_CASE("a command against a stopped manager is 503, not a crash",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;  // never started
    const Response r = route_request(
        make_request("POST", "/api/jobs/anything/pause"), fx.manager());
    // What an operator gets if they reach the API during startup. 503 is
    // temporary and retryable; 500 would tell them to open a bug.
    CHECK(r.status == 503);
}

TEST_CASE("a query string does not change the route",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;
    fx.start();
    // Treating "/healthz?x=1" as a different route from "/healthz" is how a
    // 404 appears for a request that looked right to whoever sent it.
    const Response r =
        route_request(make_request("GET", "/healthz?verbose=1"), fx.manager());
    CHECK(r.status == 200);
}

TEST_CASE("redundant slashes route the same way", "[router][L2-CTL-005]") {
    ManagerFixture fx;
    fx.start();
    const Response r = route_request(
        make_request("POST", "//api//jobs//abc//pause"), fx.manager());
    // Empty segments are discarded, so this is the same route. It answers 404
    // because the job does not exist -- not because the path was rejected.
    CHECK(r.status == 404);
}

TEST_CASE("the error body is JSON for every refusal",
          "[router][L2-CTL-005]") {
    ManagerFixture fx;
    fx.start();
    const Response cases[] = {
        route_request(make_request("GET", "/nope"), fx.manager()),
        route_request(make_request("GET", "/api/jobs/x/pause"), fx.manager()),
        route_request(make_request("POST", "/api/jobs/x/pause"), fx.manager()),
    };
    for (std::size_t i = 0; i < 3; ++i) {
        INFO("case " << i << " status " << cases[i].status);
        CHECK(cases[i].status >= 400);
        CHECK(cases[i].content_type == std::string("application/json"));
        // L2-CTL-005 requires a JSON error body, not merely a status code.
        CHECK(cases[i].body.find('{') != std::string::npos);
    }
}

// --- the dashboard routes (C7) --------------------------------------------

TEST_CASE("GET / serves the dashboard as HTML", "[router][L2-DASH-001]") {
    ManagerFixture fx;  // deliberately not started
    const Response r = route_request(make_request("GET", "/"), fx.manager());
    CHECK(r.status == 200);
    CHECK(r.content_type.find("text/html") != std::string::npos);
    CHECK(r.body.compare(0, 15, "<!DOCTYPE html>") == 0);

    // Served whether or not the manager is running. The page's own job is to
    // report that the service is down, and a dashboard that 503s when the
    // thing it monitors is unhealthy vanishes during the incident it exists
    // for.
    CHECK(r.body.empty() == false);
}

TEST_CASE("the dashboard route refuses methods that are not reads",
          "[router][L2-DASH-001][L2-CTL-005]") {
    ManagerFixture fx;
    const Response r = route_request(make_request("POST", "/"), fx.manager());
    CHECK(r.status == 405);
    CHECK(r.allow == std::string("GET, HEAD"));
}

TEST_CASE("GET /api/status reports counts and live queue depth",
          "[router][L2-DASH-001]") {
    ManagerFixture fx;
    fx.start();
    const Response r = route_request(make_request("GET", "/api/status"),
                                     fx.manager());
    CHECK(r.status == 200);
    CHECK(r.content_type == std::string("application/json"));
    CHECK(r.body.find("\"running\":true") != std::string::npos);
    CHECK(r.body.find("\"runnable\":") != std::string::npos);
    CHECK(r.body.find("\"active\":") != std::string::npos);
    CHECK(r.body.find("\"jobs\":[") != std::string::npos);

    // Every state present, so the page need not special-case absence
    // (L2-JOB-006), and keyed by the same token to_string(JobState) emits --
    // two spellings is how a counter reads zero forever and nobody notices.
    CHECK(r.body.find("\"QUEUED\":") != std::string::npos);
    CHECK(r.body.find("\"DONE\":") != std::string::npos);
    CHECK(r.body.find("\"FAILED\":") != std::string::npos);

    // The cap is reported, not merely applied.
    CHECK(r.body.find("\"limit\":") != std::string::npos);
    CHECK(r.body.find("\"truncated\":false") != std::string::npos);
}

TEST_CASE("status against a stopped manager is 503, not an empty success",
          "[router][L2-DASH-001]") {
    // A dashboard rendering "0 jobs" for a service that is not running is
    // worse than one saying it cannot reach the service: the first is a
    // confident wrong answer.
    ManagerFixture fx;  // not started
    const Response r = route_request(make_request("GET", "/api/status"),
                                     fx.manager());
    CHECK(r.status == 503);
    CHECK(r.content_type == std::string("application/json"));
}

TEST_CASE("a path containing markup survives the API as text",
          "[router][L2-DASH-003]") {
    // THE case L2-DASH-003 exists for. A filename is attacker-chosen -- whoever
    // can create a file names it -- and it must arrive at the browser as DATA:
    // escaped where JSON requires it, never turned into markup on the way.
    //
    // The payload is an img tag rather than a script tag, because a script tag
    // cannot be a filename: "</script>" contains a slash, and a slash is the
    // one byte a POSIX filename cannot hold. `<img src=x onerror=...>` needs
    // none, which makes it the shape this actually has to survive. Getting
    // that wrong would have produced a test passing against an input no
    // attacker can create.
    //
    // The page then inserts it with createTextNode, asserted separately in
    // test_dashboard.cpp. This half proves the value reaches the page intact
    // rather than being mangled, dropped, or re-encoded en route.
    ManagerFixture fx;
    fx.start();

    Request submit = make_request("POST", "/api/jobs");
    submit.body =
        "{\"source\":\"/tmp/<img src=x onerror=alert(1)>.mp4\","
        "\"dest\":\"/tmp/out.mp4\"}";
    const Response created = route_request(submit, fx.manager());
    REQUIRE(created.status == 202);

    const Response status = route_request(make_request("GET", "/api/status"),
                                          fx.manager());
    REQUIRE(status.status == 200);

    // Present, and still the same characters. The API does NOT HTML-escape:
    // escaping for HTML inside a JSON payload is how a value ends up
    // double-escaped in one consumer and raw in another, and it would not
    // help anyway -- the defence is the text node, not the encoding.
    CHECK(status.body.find("<img src=x onerror=alert(1)>") !=
          std::string::npos);
    // ...and the payload is still well-formed JSON: nothing in the name has
    // broken out of the string.
    CHECK(status.body.find("\"source\":\"/tmp/<img") != std::string::npos);
}
