#ifndef FILEMOVER_CONFIG_HPP
#define FILEMOVER_CONFIG_HPP

// INI configuration loader.
//
// Pure parsing and validation over an in-memory string; the file-reading
// wrapper is a thin adapter. Strict posture: unknown sections and keys,
// duplicates, and malformed lines are hard errors reported as file:line.
//
// Traces: L2-CFG-001..011, L1-SYS-019, L1-SYS-020
//
// Accepted syntax (L3-CPP-033):
//   [section]            section header
//   key = value          leading/trailing whitespace trimmed on both sides;
//                        value may contain spaces and '=' characters
//   ; comment            full-line comments only ('#' also accepted);
//   # comment            inline comments are NOT supported
//   (blank line)
//
// Schema (grows only by coordinated change, L3-CPP-036):
//   [http]    bind            optional, default "127.0.0.1", no whitespace
//             port            optional, default 8080, range 1..65535
//             max_body_bytes  optional, default 65536, range 1..16777216
//   [jobs]    workers         optional, default 4, range 1..64
//   [storage] database_path   REQUIRED, non-empty, no embedded NUL
//   [retry]   max_attempts        optional, default 3,     range 1..100
//             backoff_initial_ms  optional, default 1000,  range 1..3600000
//             backoff_max_ms      optional, default 60000, range 1..3600000
//             Cross-field: backoff_initial_ms <= backoff_max_ms (L2-RTY-005)
//
// The section is [storage] rather than the [journal] of the inherited
// design: ADR-0010 chose SQLite over an append-only journal, and a
// configuration key should not name a mechanism the project rejected.

#include <cstdint>
#include <string>

namespace filemover {

struct Config {
    std::string http_bind;
    std::uint16_t http_port;
    std::uint32_t http_max_body_bytes;
    unsigned jobs_workers;
    std::string storage_database_path;
    unsigned retry_max_attempts;
    std::uint32_t retry_backoff_initial_ms;
    std::uint32_t retry_backoff_max_ms;

    // L3-CPP-039: documented defaults for every optional parameter.
    Config()
        : http_bind("127.0.0.1"),
          http_port(8080),
          http_max_body_bytes(65536),
          jobs_workers(4),
          storage_database_path(),
          retry_max_attempts(3),
          retry_backoff_initial_ms(1000),
          retry_backoff_max_ms(60000) {}
};

// Parse and validate configuration text.
//
// L3-CPP-034: Every rejection tied to a line SHALL be reported as
//             "<origin>:<line>: <message>".
// L3-CPP-035: ALL issues SHALL be reported together, newline-separated,
//             rather than stopping at the first. Parsing continues past a
//             bad line so one run of the loader lists everything wrong with
//             the file (L2-CFG-008).
// L3-CPP-036: Unknown sections and unknown keys SHALL be rejected.
// L3-CPP-037: Duplicate keys within a section, and duplicate section
//             headers, SHALL be rejected.
// L3-CPP-038: Integers SHALL parse strictly — base 10, whole token, no sign
//             characters, range enforced.
// L3-CPP-039: Missing required parameters SHALL be reported by qualified
//             name; optional parameters SHALL take their documented default.
// L3-CPP-040: This function SHALL perform no I/O. `origin` is used only to
//             prefix messages, so the entire validation matrix is testable
//             without touching a disk.
//
// On failure: returns false, `error` is non-empty, `out` is unmodified.
bool load_config_from_string(const std::string& text,
                             const std::string& origin,
                             Config& out,
                             std::string& error);

// Read `path` and delegate to load_config_from_string (origin = path).
// An unopenable file is an error naming the path with strerror detail.
bool load_config_file(const std::string& path,
                      Config& out,
                      std::string& error);

// True when `magic` is a known network filesystem's statfs f_type.
//
// Split out from the check below so it is exhaustively testable without an
// actual NFS mount, which CI does not have.
bool is_network_filesystem_magic(unsigned long magic);

// L2-JOB-008: the SQLite state database must live on a local filesystem.
// SQLite's locking relies on POSIX advisory locks that NFS implements
// unreliably, and this deployment puts recordings on NFS — so the mistake is
// available to make. Returns false and fills `reason` when the path resolves
// onto a network filesystem, or when it cannot be checked at all.
//
// This performs I/O and therefore lives OUTSIDE load_config_from_string,
// which L3-CPP-040 requires to stay pure. Call it at service startup, after
// configuration has parsed.
bool storage_path_is_local(const std::string& path, std::string& reason);

}  // namespace filemover

#endif  // FILEMOVER_CONFIG_HPP
