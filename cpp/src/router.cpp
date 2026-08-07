// C5: route table and handlers.
// Traces: L2-CTL-005, L2-CTL-014

#include "filemover/router.hpp"

#include <vector>

#include "filemover/api_codec.hpp"

namespace filemover {
namespace {

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
