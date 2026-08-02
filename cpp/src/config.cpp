// INI configuration loader.
// Traces: L2-CFG-001..011, L3-CPP-033..040

#include "filemover/config.hpp"

#include <sys/vfs.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <set>
#include <sstream>
#include <vector>

namespace filemover {
namespace {

std::string trim(const std::string& s) {
    const char* ws = " \t\r";
    const std::string::size_type b = s.find_first_not_of(ws);
    if (b == std::string::npos) {
        return std::string();
    }
    const std::string::size_type e = s.find_last_not_of(ws);
    return s.substr(b, e - b + 1);
}

std::string at(const std::string& origin,
               unsigned line,
               const std::string& message) {
    std::ostringstream os;
    os << origin << ":" << line << ": " << message;  // L3-CPP-034
    return os.str();
}

// L3-CPP-038: strict base-10 unsigned parse — whole token, no sign,
// range-checked. strtoul would happily accept "80x" (stopping at 'x') and
// " 80" (skipping whitespace), so the end pointer and the leading character
// are both checked explicitly.
bool parse_uint(const std::string& token,
                unsigned long min_value,
                unsigned long max_value,
                unsigned long& value) {
    if (token.empty() || token[0] == '-' || token[0] == '+') {
        return false;
    }
    errno = 0;
    char* end = 0;
    const unsigned long parsed = std::strtoul(token.c_str(), &end, 10);
    if (errno != 0 || end == token.c_str() || *end != '\0') {
        return false;
    }
    if (parsed < min_value || parsed > max_value) {
        return false;
    }
    value = parsed;
    return true;
}

// Collects issues rather than returning on the first, per L2-CFG-008. An
// operator editing a config by hand should learn everything wrong with it in
// one run, not discover the next fault only after fixing the previous one and
// restarting.
class IssueLog {
public:
    void add(const std::string& message) { issues_.push_back(message); }
    bool empty() const { return issues_.empty(); }

    std::string joined() const {
        std::string out;
        for (std::size_t i = 0; i < issues_.size(); ++i) {
            if (i != 0) out += '\n';
            out += issues_[i];
        }
        return out;
    }

private:
    std::vector<std::string> issues_;
};

bool contains_nul(const std::string& s) {
    return s.find('\0') != std::string::npos;
}

}  // namespace

bool is_network_filesystem_magic(unsigned long magic) {
    // statfs f_type values from <linux/magic.h>. Listed numerically rather
    // than by macro because the macro set varies across the glibc versions
    // this has to build against, GCC 4.8.5 on SLES 12 included.
    //
    // Only genuinely networked or cluster-shared filesystems belong here.
    // A false positive refuses to start on a perfectly good local volume,
    // which is a worse failure than the one being prevented — so ext4, xfs,
    // btrfs, and tmpfs are deliberately absent and must stay that way.
    switch (magic) {
        case 0x6969UL:      // NFS_SUPER_MAGIC
        case 0xFF534D42UL:  // CIFS_MAGIC_NUMBER
        case 0x517BUL:      // SMB_SUPER_MAGIC
        case 0xFE534D42UL:  // SMB2_MAGIC_NUMBER
        case 0x73757245UL:  // CODA_SUPER_MAGIC
        case 0x5346414FUL:  // AFS_SUPER_MAGIC
        case 0x6B414653UL:  // OPENAFS_SUPER_MAGIC
        case 0x7461636FUL:  // OCFS2_SUPER_MAGIC (cluster-shared)
        case 0x01161970UL:  // GFS2_MAGIC (cluster-shared)
        case 0x0BD00BD0UL:  // LUSTRE_SUPER_MAGIC
        case 0x00C36400UL:  // CEPH_SUPER_MAGIC
            return true;
        default:
            return false;
    }
}

bool storage_path_is_local(const std::string& path, std::string& reason) {
    struct statfs info;
    if (::statfs(path.c_str(), &info) != 0) {
        reason = path + ": cannot determine filesystem type: " +
                 std::strerror(errno);
        return false;
    }
    if (is_network_filesystem_magic(
            static_cast<unsigned long>(info.f_type))) {
        reason = path +
                 ": the state database must live on a local filesystem; "
                 "SQLite's locking is unreliable over network filesystems "
                 "(L2-JOB-008, ADR-0010)";
        return false;
    }
    return true;
}

bool load_config_from_string(const std::string& text,
                             const std::string& origin,
                             Config& out,
                             std::string& error) {
    Config cfg;  // `out` stays untouched unless everything validates
    IssueLog issues;
    std::set<std::string> seen_sections;
    std::set<std::string> seen_keys;  // "section.key"
    std::string section;

    std::istringstream stream(text);
    std::string raw;
    unsigned line_no = 0;

    while (std::getline(stream, raw)) {
        ++line_no;
        const std::string line = trim(raw);

        if (line.empty() || line[0] == ';' || line[0] == '#') {
            continue;  // L3-CPP-033
        }

        if (line[0] == '[') {
            if (line.size() < 3 || line[line.size() - 1] != ']') {
                issues.add(at(origin, line_no, "malformed section header"));
                continue;
            }
            const std::string name = trim(line.substr(1, line.size() - 2));
            if (name.empty()) {
                issues.add(at(origin, line_no, "empty section name"));
                continue;
            }
            if (!seen_sections.insert(name).second) {
                issues.add(at(origin, line_no,  // L3-CPP-037
                              "duplicate section [" + name + "]"));
                continue;
            }
            if (name != "http" && name != "jobs" && name != "storage") {
                issues.add(at(origin, line_no,  // L3-CPP-036
                              "unknown section [" + name + "]"));
                // Still recorded as the current section, so its keys produce
                // "unknown key" rather than a confusing second complaint
                // about having no section at all.
            }
            section = name;
            continue;
        }

        const std::string::size_type eq = line.find('=');
        if (eq == std::string::npos) {
            issues.add(at(origin, line_no,
                          "expected 'key = value' or section header"));
            continue;
        }
        if (section.empty()) {
            issues.add(at(origin, line_no, "entry before any section header"));
            continue;
        }

        const std::string key = trim(line.substr(0, eq));
        const std::string value = trim(line.substr(eq + 1));
        if (key.empty()) {
            issues.add(at(origin, line_no, "empty key"));
            continue;
        }
        std::string qualified = section;
        qualified += '.';
        qualified += key;
        if (!seen_keys.insert(qualified).second) {
            std::string message = "duplicate key \"";
            message += key;
            message += "\" in [";
            message += section;
            message += "]";
            issues.add(at(origin, line_no, message));  // L3-CPP-037
            continue;
        }

        unsigned long n = 0;
        if (section == "http" && key == "bind") {
            if (value.empty() ||
                value.find_first_of(" \t") != std::string::npos) {
                issues.add(at(origin, line_no,
                              "http.bind must be non-empty without "
                              "whitespace"));
            } else {
                cfg.http_bind = value;
            }
        } else if (section == "http" && key == "port") {
            if (!parse_uint(value, 1, 65535, n)) {
                issues.add(at(origin, line_no,
                              "http.port must be an integer in 1..65535"));
            } else {
                cfg.http_port = static_cast<std::uint16_t>(n);
            }
        } else if (section == "http" && key == "max_body_bytes") {
            if (!parse_uint(value, 1, 16777216, n)) {
                issues.add(at(origin, line_no,
                              "http.max_body_bytes must be an integer in "
                              "1..16777216"));
            } else {
                cfg.http_max_body_bytes = static_cast<std::uint32_t>(n);
            }
        } else if (section == "jobs" && key == "workers") {
            if (!parse_uint(value, 1, 64, n)) {
                issues.add(at(origin, line_no,
                              "jobs.workers must be an integer in 1..64"));
            } else {
                cfg.jobs_workers = static_cast<unsigned>(n);
            }
        } else if (section == "storage" && key == "database_path") {
            if (value.empty()) {
                issues.add(at(origin, line_no,
                              "storage.database_path must be non-empty"));
            } else if (contains_nul(value)) {
                // The inherited header promised this check and never
                // implemented it. A NUL truncates the path anywhere it
                // reaches a C API, so what is validated and what is opened
                // would be different strings.
                issues.add(at(origin, line_no,
                              "storage.database_path must not contain an "
                              "embedded NUL"));
            } else {
                cfg.storage_database_path = value;
            }
        } else {
            std::string message = "unknown key \"";
            message += key;
            message += "\" in [";
            message += section;
            message += "]";
            issues.add(at(origin, line_no, message));  // L3-CPP-036
        }
    }

    if (cfg.storage_database_path.empty()) {  // L3-CPP-039
        issues.add(origin +
                   ": missing required parameter storage.database_path");
    }

    if (!issues.empty()) {
        error = issues.joined();
        return false;
    }

    out = cfg;
    error.clear();
    return true;
}

bool load_config_file(const std::string& path,
                      Config& out,
                      std::string& error) {
    std::ifstream file(path.c_str(), std::ios::binary);
    if (!file) {
        error = path + ": cannot open: " + std::strerror(errno);
        return false;
    }
    std::ostringstream contents;
    contents << file.rdbuf();
    return load_config_from_string(contents.str(), path, out, error);
}

}  // namespace filemover
