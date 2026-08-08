// C5: route table and handlers.
// Traces: L2-CTL-005, L2-CTL-014

#include "filemover/router.hpp"

#include "filemover/dashboard.hpp"

#include <vector>

#include "filemover/api_codec.hpp"

namespace filemover {
namespace {

// How many jobs GET /api/status returns at most. Fixed here rather than taken
// from the request: the response is assembled in memory before it is written,
// so a client-chosen size is a client-chosen allocation.
const std::size_t kStatusJobLimit = 50;

http::Response make(int status, const std::string& body) {
    http::Response r;
    r.status = status;
    r.body = body;
    return r;
}

http::Response error_response(int status, const std::string& message) {
    return make(status, encode_error(message));
}

// 405 carries Allow. Without it a client cannot tell which methods the route
// does take, and L2-CTL-005 requires the header rather than merely the code.
http::Response method_not_allowed(const std::string& allow) {
    http::Response r =
        error_response(405, "method not allowed on this route");
    r.allow = allow;
    return r;
}

// Splits the target on '/', discarding empty segments, and drops any query
// string. Routing is on the path alone; a query is not part of the identity of
// the resource here, and treating "/api/jobs/x?y" as a different route from
// "/api/jobs/x" is how a 404 appears for a request that looked right.
std::vector<std::string> path_segments(const std::string& target) {
    std::vector<std::string> out;
    const std::string::size_type query = target.find('?');
    const std::string path =
        (query == std::string::npos) ? target : target.substr(0, query);

    std::string::size_type i = 0;
    while (i < path.size()) {
        while (i < path.size() && path[i] == '/') {
            ++i;
        }
        const std::string::size_type start = i;
        while (i < path.size() && path[i] != '/') {
            ++i;
        }
        if (i > start) {
            out.push_back(path.substr(start, i - start));
        }
    }
    return out;
}

// Splits an absolute path into the directory and the final component.
//
// The API speaks in paths; the mover speaks in a directory and a name, because
// every filesystem operation is fd-relative against a held DirHandle
// (L2-SEC-001). This is the one place that conversion happens, so the split
// rule is written down once rather than guessed at per call site.
//
// Refuses anything that is not absolute or has no name after the last slash. A
// trailing slash means a directory was named where a file was required, and
// accepting it would produce a move with an empty source name.
bool split_path(const std::string& path, std::string& dir, std::string& name) {
    if (path.empty() || path[0] != '/') {
        return false;
    }
    const std::string::size_type slash = path.rfind('/');
    if (slash == std::string::npos || slash + 1 >= path.size()) {
        return false;
    }
    // "/file" has its directory at position 0, which is "/" rather than "".
    dir = (slash == 0) ? std::string("/") : path.substr(0, slash);
    name = path.substr(slash + 1);
    return true;
}

}  // namespace

int status_for(CommandResult result) {
    switch (result) {
        case CommandResult::Ok:           return 200;
        case CommandResult::UnknownJob:   return 404;
        case CommandResult::InvalidState: return 409;
        case CommandResult::NotRunning:   return 503;
        case CommandResult::StoreError:   return 500;
    }
    // Unreachable while the enum is handled exhaustively above, which -Werror
    // with -Wswitch guarantees. 500 rather than 200: an unmapped result is our
    // fault, and answering OK to something we did not understand is the worst
    // available option.
    return 500;
}

http::Response route_request(const http::Request& request,
                             JobManager& manager) {
    const std::vector<std::string> seg = path_segments(request.target);

    // GET /healthz -- deliberately touches nothing. A liveness probe that
    // queries the store reports the store's health, not the service's, and
    // fails during exactly the incident it exists to survive.
    if (seg.size() == 1 && seg[0] == "healthz") {
        if (request.method != "GET" && request.method != "HEAD") {
            return method_not_allowed("GET, HEAD");
        }
        return make(200, "{\"status\":\"ok\"}");
    }

    // GET / -- the operator dashboard (L2-DASH-001, L2-DASH-002).
    //
    // Served from the binary, not from disk. The service ships as one
    // executable (L1-SYS-002), and reading the page from a path at request time
    // would add a filesystem dependency to the control plane and a directory an
    // operator could be persuaded to point somewhere else.
    if (seg.empty()) {
        if (request.method != "GET" && request.method != "HEAD") {
            return method_not_allowed("GET, HEAD");
        }
        http::Response page = make(200, dashboard_html());
        page.content_type = dashboard_content_type();
        return page;
    }

    // GET /api/status -- what the dashboard polls (L2-DASH-001).
    if (seg.size() == 2 && seg[0] == "api" && seg[1] == "status") {
        if (request.method != "GET" && request.method != "HEAD") {
            return method_not_allowed("GET, HEAD");
        }

        JobManager::StatusSnapshot snapshot;
        std::string error;
        // The cap is the router's decision, not the client's. Honouring a
        // ?limit= would let an unauthenticated caller choose the size of a
        // response that is built in memory before it is written.
        const CommandResult result =
            manager.status(kStatusJobLimit, snapshot, error);
        if (result != CommandResult::Ok) {
            return error_response(status_for(result), error);
        }
        return make(200, encode_status(snapshot, kStatusJobLimit));
    }

    // POST /api/jobs -- create a job under a freshly allocated id.
    if (seg.size() == 2 && seg[0] == "api" && seg[1] == "jobs") {
        if (request.method != "POST") {
            return method_not_allowed("POST");
        }

        SubmitRequest submission;
        std::string decode_error;
        if (!decode_submit_request(request.body, submission, decode_error)) {
            // L2-CTL-005: malformed JSON is 400 with a JSON body. The decoder's
            // message names the offending field or byte offset, which is more
            // use to a client than "bad request".
            return error_response(400, decode_error);
        }

        MoveRequest move;
        if (!split_path(submission.source, move.source_dir,
                        move.source_name) ||
            !split_path(submission.dest, move.dest_dir, move.dest_name)) {
            return error_response(
                400,
                "source and dest must be absolute paths naming a file");
        }

        std::string job_id;
        std::string submit_error;
        const CommandResult result =
            manager.submit(move, job_id, submit_error);
        if (result != CommandResult::Ok) {
            return error_response(status_for(result), submit_error);
        }
        // 202, not 200: the job is recorded and queued, and the move has not
        // happened yet. Answering 200 would tell a client the file had moved.
        return make(202, "{\"job_id\":\"" + job_id + "\"}");
    }

    // /api/jobs/{id}/{action}
    if (seg.size() == 4 && seg[0] == "api" && seg[1] == "jobs") {
        const std::string& id = seg[2];
        const std::string& action = seg[3];

        const bool known_action = (action == "pause" || action == "resume" ||
                                   action == "cancel" || action == "retry");
        if (!known_action) {
            return error_response(404, "no such route");
        }
        if (request.method != "POST") {
            // The route exists; the method does not. 405 rather than 404 is
            // the difference between "you asked for the wrong thing" and "you
            // asked the wrong way", and a client can act on the second.
            return method_not_allowed("POST");
        }
        if (id.empty()) {
            return error_response(400, "job id is empty");
        }

        std::string error;
        CommandResult result = CommandResult::StoreError;
        std::string body;

        if (action == "pause") {
            result = manager.pause(id, error);
        } else if (action == "resume") {
            result = manager.resume(id, error);
        } else if (action == "cancel") {
            result = manager.cancel(id, error);
        } else {
            std::string new_job_id;
            result = manager.retry(id, new_job_id, error);
            if (result == CommandResult::Ok) {
                // Retry creates a NEW job (L2-RTY-006), so the response has to
                // name it. A client told only "OK" would have no way to follow
                // the attempt it just started.
                body = "{\"job_id\":\"" + new_job_id + "\"}";
            }
        }

        const int status = status_for(result);
        if (result == CommandResult::Ok) {
            return make(status, body.empty() ? "{\"status\":\"ok\"}" : body);
        }
        // The manager's message is the useful part -- it says which state
        // refused and why -- so it is passed through rather than replaced with
        // a generic string keyed off the status code.
        return error_response(status, error);
    }

    return error_response(404, "no such route");
}

}  // namespace filemover
