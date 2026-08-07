// The hostile battery (C5).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-CTL-002, L2-CTL-004, L2-CTL-005, L2-SEC-009
//
// The battery fires FIRST, then the same server instance completes a real
// request. That ordering is the point: it proves the server is not merely
// rejecting bad input but is still working afterwards. A suite that only
// checks status codes would pass against a server that had wedged itself.

#include "catch2/catch.hpp"

#include "filemover/http_service.hpp"
#include "filemover/server.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstring>
#include <string>

using filemover::Config;
using filemover::ConnectionServer;
using filemover::HttpServiceOptions;
using filemover::JobManager;

namespace {

// One manager and one server, shared by every case in a section, so the
// "still works afterwards" claim is about the instance the battery attacked.
class ServiceFixture {
  public:
    ServiceFixture() {
        char tmpl[] = "/tmp/fm-http-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        root_ = made;

        Config cfg;
        cfg.jobs_workers = 1;
        cfg.storage_database_path = db();
        manager_ = new JobManager(db(), cfg);
        std::string error;
        REQUIRE(manager_->start(error) == true);

        options_.max_head_bytes = 1024;
        options_.max_body_bytes = 4096;
        g_options = &options_;
        g_manager = manager_;

        filemover::ServerOptions server_options;
        server_options.handlers = 2;
        server_options.recv_timeout_ms = 1000;
        server_options.send_timeout_ms = 1000;
        REQUIRE(server_.start("127.0.0.1", 0, server_options, dispatch, 0,
                              error) == true);
    }

    ~ServiceFixture() {
        server_.shutdown();
        manager_->shutdown();
        delete manager_;
        ::unlink((db() + "-wal").c_str());
        ::unlink((db() + "-shm").c_str());
        ::unlink(db().c_str());
        ::rmdir(root_.c_str());
    }

    std::uint16_t port() const { return server_.port(); }
    std::string db() const { return root_ + "/state.db"; }

    // Sends raw bytes and returns everything the server says back.
    std::string exchange(const std::string& raw) const {
        const int fd = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
        REQUIRE(fd >= 0);
        struct sockaddr_in addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port());
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        REQUIRE(::connect(fd, reinterpret_cast<struct sockaddr*>(&addr),
                          sizeof(addr)) == 0);
        if (!raw.empty()) {
            REQUIRE(::send(fd, raw.data(), raw.size(), MSG_NOSIGNAL) > 0);
        }
        std::string out;
        char buf[1024];
        for (;;) {
            const ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
            if (n <= 0) {
                break;
            }
            out.append(buf, static_cast<std::size_t>(n));
        }
        ::close(fd);
        return out;
    }

  private:
    ServiceFixture(const ServiceFixture&);
    ServiceFixture& operator=(const ServiceFixture&);

    static HttpServiceOptions* g_options;
    static JobManager* g_manager;

    static void dispatch(int fd, void* /*user*/) {
        filemover::serve_connection(fd, *g_options, *g_manager);
    }

    std::string root_;
    JobManager* manager_;
    HttpServiceOptions options_;
    ConnectionServer server_;
};

HttpServiceOptions* ServiceFixture::g_options = 0;
JobManager* ServiceFixture::g_manager = 0;

bool has_status(const std::string& response, const char* code) {
    return response.find(code) != std::string::npos;
}

}  // namespace

TEST_CASE("the hostile battery, then the same instance still works",
          "[httpservice][L2-CTL-004][L2-CTL-005]") {
    ServiceFixture fx;

    SECTION("the battery runs and the server survives it") {
        // 1. Garbage that is not a request line at all.
        CHECK(has_status(fx.exchange("\x01\x02\x03 not http\r\n\r\n"), "400"));

        // 2. A head larger than the cap. 431 rather than 400: the request may
        //    be perfectly well formed and simply too big to buffer.
        std::string big = "GET /healthz HTTP/1.1\r\n";
        big += "X-Pad: " + std::string(4096, 'a') + "\r\n\r\n";
        CHECK(has_status(fx.exchange(big), "431"));

        // 3. A declared gigabyte. Refused WITHOUT reading it -- see the
        //    dedicated test below, which asserts the bytes were never read.
        std::string huge = "POST /api/jobs/x/pause HTTP/1.1\r\n";
        huge += "Content-Length: 1073741824\r\n\r\n";
        CHECK(has_status(fx.exchange(huge), "413"));

        // 4. Chunked, which L2-CTL-002 forbids outright.
        std::string chunked = "POST /api/jobs/x/pause HTTP/1.1\r\n";
        chunked += "Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n";
        CHECK(has_status(fx.exchange(chunked), "400"));

        // 5. Bytes past the declared body. No pipelining and no smuggled
        //    second request -- the surplus desynchronises this server from any
        //    proxy in front of it.
        std::string trailing = "POST /api/jobs/x/pause HTTP/1.1\r\n";
        trailing += "Content-Length: 2\r\n\r\nab";
        trailing += "GET /healthz HTTP/1.1\r\n\r\n";
        CHECK(has_status(fx.exchange(trailing), "400"));

        // 6. The routing refusals.
        CHECK(has_status(fx.exchange("GET /nope HTTP/1.1\r\n\r\n"), "404"));
        const std::string wrong_method =
            fx.exchange("GET /api/jobs/x/pause HTTP/1.1\r\n\r\n");
        CHECK(has_status(wrong_method, "405"));
        CHECK(wrong_method.find("Allow:") != std::string::npos);

        // 7. A client that connects and says nothing is timed out and cannot
        //    hold the service (L2-SEC-009).
        CHECK(fx.exchange("").empty() == true);

        // --- and now the point of the whole test ---------------------------
        //
        // Every case above could pass against a server that had wedged itself,
        // because each opens its own connection and a wedged server would
        // simply close them. This is the assertion that distinguishes
        // "rejected the input" from "survived rejecting the input".
        const std::string healthy =
            fx.exchange("GET /healthz HTTP/1.1\r\n\r\n");
        CHECK(has_status(healthy, "200"));
        CHECK(healthy.find("ok") != std::string::npos);
    }
}

TEST_CASE("an oversized declaration is refused without reading the body",
          "[httpservice][L2-CTL-005]") {
    // The status code alone does not prove this. A server that reads the whole
    // body and THEN answers 413 passes a status check while still being the
    // denial of service the cap exists to prevent, so the bytes actually read
    // are what gets asserted.
    ServiceFixture fx;
    HttpServiceOptions options;
    options.max_head_bytes = 1024;
    options.max_body_bytes = 128;

    int pair[2] = {-1, -1};
    REQUIRE(::socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, pair) == 0);

    std::string head = "POST /api/jobs/x/pause HTTP/1.1\r\n";
    head += "Content-Length: 1073741824\r\n\r\n";
    // A body far larger than the cap, but small enough to fit the socket
    // buffer so the write does not block the test.
    const std::string body(8192, 'x');
    REQUIRE(::send(pair[1], head.data(), head.size(), MSG_NOSIGNAL) > 0);
    REQUIRE(::send(pair[1], body.data(), body.size(), MSG_NOSIGNAL) > 0);

    Config cfg;
    cfg.jobs_workers = 1;
    cfg.storage_database_path = fx.db();
    JobManager manager(fx.db(), cfg);

    filemover::serve_connection(pair[0], options, manager);
    const std::size_t read_bytes = filemover::last_connection_bytes_read();

    // Only the head, and whatever arrived alongside it in the same segment --
    // never the declared gigabyte, and not the 8 KB already queued either.
    INFO("bytes read = " << read_bytes);
    CHECK(read_bytes < 4096u);

    ::close(pair[0]);
    ::close(pair[1]);
}

TEST_CASE("a body shorter than declared is answered, not left hanging",
          "[httpservice][L2-CTL-004]") {
    ServiceFixture fx;
    std::string short_body = "POST /api/jobs/x/pause HTTP/1.1\r\n";
    short_body += "Content-Length: 100\r\n\r\nonly-a-few";
    // The client stops sending and closes. The read fails, and unlike the
    // head case there IS a parsed request, so the client is told what was
    // wrong rather than getting a silent disconnect.
    CHECK(has_status(fx.exchange(short_body), "400"));
    CHECK(has_status(fx.exchange("GET /healthz HTTP/1.1\r\n\r\n"), "200"));
}

TEST_CASE("a well-formed request with an exact body is routed",
          "[httpservice][L2-CTL-005]") {
    ServiceFixture fx;
    std::string request = "POST /api/jobs/ghost/pause HTTP/1.1\r\n";
    request += "Content-Type: application/json\r\n";
    request += "Content-Length: 2\r\n\r\n{}";
    // Routed, reaching the manager, which refuses an unknown job with 404.
    // The body is consumed exactly -- a driver that read past it would block
    // until the deadline instead of answering.
    CHECK(has_status(fx.exchange(request), "404"));
}
