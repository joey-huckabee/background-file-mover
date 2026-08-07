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
    const char* targets[] = {"/", "/nope", "/api", "/api/jobs",
                             "/api/jobs/id", "/api/jobs/id/frobnicate",
                             "/api/jobs/id/pause/extra"};
    for (std::size_t i = 0; i < 7; ++i) {
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
