#ifndef FILEMOVER_ROUTER_HPP
#define FILEMOVER_ROUTER_HPP

// C5: route table and handlers for the REST control plane.
//
// Traces: L2-CTL-005, L2-CTL-014
//
// Every handler here is a pure function of the parsed request and the job
// manager. Nothing in this header knows about sockets, threads or timeouts,
// which is L2-CTL-014 and is what makes the whole route matrix -- including the
// error cases, which are the ones that rot -- testable without opening a
// socket.

#include <string>

#include "filemover/http_parser.hpp"
#include "filemover/manager.hpp"

namespace filemover {

// Dispatches one request. Never throws, never blocks on the network, and
// returns a response for every input including the ones it refuses.
//
// `manager` may be a manager that has not been started; the lifecycle commands
// then answer 503 (NotRunning) rather than failing some other way, which is the
// behaviour an operator gets if they reach the API during startup.
http::Response route_request(const http::Request& request, JobManager& manager);

// The status code a lifecycle command's result maps onto.
//
// Exposed for the tests, and because the mapping is a decision rather than an
// implementation detail: CommandResult was made a typed enum in C4 precisely so
// this could be a total function over it instead of prose parsed out of an
// error string.
//
//   Ok           -> 200
//   UnknownJob   -> 404
//   InvalidState -> 409  (the request is well-formed; the job's state refuses)
//   NotRunning   -> 503  (temporary, and Retry-After-shaped)
//   StoreError   -> 500  (ours, not the client's)
int status_for(CommandResult result);

}  // namespace filemover

#endif  // FILEMOVER_ROUTER_HPP
