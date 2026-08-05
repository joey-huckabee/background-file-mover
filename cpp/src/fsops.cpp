// C2: the fd-relative filesystem layer.
// Traces: L2-SEC-001..007, L2-NFS-001..005, L2-NFS-007

#include "filemover/fsops.hpp"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <sstream>

namespace filemover {
namespace {

// renameat2 is not reachable through libc on the deployment target.
//
// Measured rather than assumed: SLES 12 SP5 ships glibc 2.22 and the wrapper
// arrived in 2.28, so `renameat2(...)` compiles on a modern host and fails to
// link there. RENAME_NOREPLACE and SYS_renameat2 are likewise absent from the
// headers. L2-SEC-007 anticipates this and says to go through syscall(2).
//
// The syscall number is architecture-specific, so it is guarded rather than
// assumed. A silently wrong constant on a new architecture would not fail to
// build — it would call some *other* syscall, which is far worse than a
// compile error.
#if !defined(__x86_64__)
#error "SYS_renameat2 is hardcoded for x86_64; add the number for this target"
#endif

#ifndef FM_SYS_renameat2
#define FM_SYS_renameat2 316
#endif

#ifndef FM_RENAME_NOREPLACE
#define FM_RENAME_NOREPLACE (1 << 0)
#endif

int fm_renameat2(int olddirfd, const char* oldpath, int newdirfd,
                 const char* newpath, unsigned int flags) {
    return static_cast<int>(::syscall(FM_SYS_renameat2, olddirfd, oldpath,
                                      newdirfd, newpath, flags));
}

PreOpenHook g_pre_open_hook = 0;
void* g_pre_open_user = 0;

std::string errno_message(const std::string& what, int err) {
    std::ostringstream os;
    os << "fsops: " << what << ": " << ::strerror(err);
    return os.str();
}

EntryKind kind_from_mode(mode_t mode) {
    if (S_ISREG(mode)) {
        return EntryKind::Regular;
    }
    if (S_ISDIR(mode)) {
        return EntryKind::Directory;
    }
    if (S_ISLNK(mode)) {
        return EntryKind::Symlink;
    }
    if (S_ISFIFO(mode)) {
        return EntryKind::Fifo;
    }
    if (S_ISSOCK(mode)) {
        return EntryKind::Socket;
    }
    if (S_ISBLK(mode)) {
        return EntryKind::BlockDevice;
    }
    if (S_ISCHR(mode)) {
        return EntryKind::CharDevice;
    }
    return EntryKind::Unknown;
}

// A name, not a path: no separators, and neither of the directory entries that
// would let a caller step outside the tree the descriptor pins.
bool is_plain_name(const std::string& name) {
    if (name.empty() || name == "." || name == "..") {
        return false;
    }
    return name.find('/') == std::string::npos &&
           name.find('\0') == std::string::npos;
}

bool reject_bad_name(const std::string& name, std::string& error) {
    if (!is_plain_name(name)) {
        error = "fsops: '" + name +
                "' is not a plain entry name; this layer takes names relative "
                "to a directory descriptor, never paths (L2-SEC-001)";
        return true;
    }
    return false;
}

}  // namespace

const char* to_string(EntryKind kind) {
    switch (kind) {
        case EntryKind::Missing:     return "MISSING";
        case EntryKind::Regular:     return "REGULAR";
        case EntryKind::Directory:   return "DIRECTORY";
        case EntryKind::Symlink:     return "SYMLINK";
        case EntryKind::Fifo:        return "FIFO";
        case EntryKind::Socket:      return "SOCKET";
        case EntryKind::BlockDevice: return "BLOCK_DEVICE";
        case EntryKind::CharDevice:  return "CHAR_DEVICE";
        case EntryKind::Unknown:     return "UNKNOWN";
    }
    return "UNKNOWN";
}

const char* to_string(MoveStrategy strategy) {
    switch (strategy) {
        case MoveStrategy::RenameNoReplace: return "RENAME_NOREPLACE";
        case MoveStrategy::LinkThenUnlink:  return "LINK_THEN_UNLINK";
    }
    return "UNKNOWN";
}

const char* to_string(ErrorClass klass) {
    switch (klass) {
        case ErrorClass::Retryable: return "RETRYABLE";
        case ErrorClass::Denied:    return "DENIED";
        case ErrorClass::Fatal:     return "FATAL";
    }
    return "FATAL";
}

bool FileIdentity::same_object_as(const FileIdentity& other) const {
    return dev == other.dev && ino == other.ino && kind == other.kind;
}

ErrorClass classify_errno(int err) {
    switch (err) {
        // L2-NFS-004. ESTALE is the one that matters: on a live export a
        // handle going away under us is expected, and treating it as a fault
        // would fail moves that a retry completes.
        case ESTALE:
        case EAGAIN:
        case EINTR:
        case ENOMEM:
        case ENOSPC:
        case EBUSY:
        case ETIMEDOUT:
            return ErrorClass::Retryable;

        case EACCES:
        case EPERM:
        case EROFS:
            return ErrorClass::Denied;

        default:
            return ErrorClass::Fatal;
    }
}

// --- DirHandle -----------------------------------------------------------

DirHandle::DirHandle() : fd_(-1) {}

DirHandle::~DirHandle() { close(); }

void DirHandle::close() {
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
}

bool DirHandle::is_open() const { return fd_ >= 0; }

int DirHandle::fd() const { return fd_; }

bool DirHandle::open_root(const std::string& path, std::string& error) {
    close();
    // O_NOFOLLOW so a symlinked root is refused rather than followed
    // (L2-SEC-003); O_DIRECTORY so a regular file named as a root fails here
    // instead of at the first operation against it.
    const int fd = ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (fd < 0) {
        error = errno_message("cannot open root directory '" + path + "'",
                              errno);
        return false;
    }
    fd_ = fd;
    return true;
}

bool DirHandle::open_child(const DirHandle& parent,
                           const std::string& name,
                           std::string& error) {
    if (!parent.is_open()) {
        error = "fsops: parent directory is not open";
        return false;
    }
    if (reject_bad_name(name, error)) {
        return false;
    }
    close();
    const int fd = ::openat(parent.fd(), name.c_str(),
                            O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (fd < 0) {
        error = errno_message("cannot open subdirectory '" + name + "'", errno);
        return false;
    }
    fd_ = fd;
    return true;
}

// --- classification and opening -----------------------------------------

bool classify(const DirHandle& dir,
              const std::string& name,
              FileIdentity& out,
              std::string& error) {
    out = FileIdentity();
    if (!dir.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }
    if (reject_bad_name(name, error)) {
        return false;
    }

    struct stat st;
    if (::fstatat(dir.fd(), name.c_str(), &st, AT_SYMLINK_NOFOLLOW) != 0) {
        if (errno == ENOENT) {
            // Absence is an answer, not a failure. A caller checking for a
            // destination collision should not have to distinguish "not there"
            // from "the query broke".
            out.kind = EntryKind::Missing;
            return true;
        }
        error = errno_message("cannot stat '" + name + "'", errno);
        return false;
    }

    out.dev = st.st_dev;
    out.ino = st.st_ino;
    out.kind = kind_from_mode(st.st_mode);
    return true;
}

bool read_entries(const DirHandle& dir,
                  std::vector<DirEntry>& out,
                  std::string& error) {
    out.clear();
    if (!dir.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }

    // fdopendir takes ownership of the descriptor it is given and closedir
    // closes it, so it gets a duplicate. Handing it the DirHandle's own fd
    // would leave the handle holding a closed descriptor and every later
    // operation on it failing with EBADF -- a fault that would surface far
    // from its cause.
    const int dup_fd = ::dup(dir.fd());
    if (dup_fd < 0) {
        error = errno_message("cannot duplicate directory descriptor", errno);
        return false;
    }

    DIR* handle = ::fdopendir(dup_fd);
    if (handle == 0) {
        error = errno_message("cannot read directory", errno);
        ::close(dup_fd);
        return false;
    }
    // Start from the beginning: a duplicated descriptor shares its file offset
    // with the original, so a second listing would otherwise resume where the
    // first stopped and silently return nothing.
    ::rewinddir(handle);

    for (;;) {
        errno = 0;
        const struct dirent* ent = ::readdir(handle);
        if (ent == 0) {
            if (errno != 0) {
                error = errno_message("reading directory", errno);
                ::closedir(handle);
                out.clear();
                return false;
            }
            break;
        }

        const std::string name = ent->d_name;
        if (name == "." || name == "..") {
            continue;
        }

        DirEntry entry;
        entry.name = name;

        // d_type is an optimisation, not a guarantee. NFS commonly reports
        // DT_UNKNOWN, so on the mount the recordings live on this fstatat is
        // the normal path rather than a fallback.
        switch (ent->d_type) {
            case DT_REG:  entry.kind = EntryKind::Regular;     break;
            case DT_DIR:  entry.kind = EntryKind::Directory;   break;
            case DT_LNK:  entry.kind = EntryKind::Symlink;     break;
            case DT_FIFO: entry.kind = EntryKind::Fifo;        break;
            case DT_SOCK: entry.kind = EntryKind::Socket;      break;
            case DT_BLK:  entry.kind = EntryKind::BlockDevice; break;
            case DT_CHR:  entry.kind = EntryKind::CharDevice;  break;
            default: {
                struct stat st;
                if (::fstatat(dir.fd(), name.c_str(), &st,
                              AT_SYMLINK_NOFOLLOW) == 0) {
                    entry.kind = kind_from_mode(st.st_mode);
                } else if (errno == ENOENT) {
                    // Vanished between the readdir and the stat. Expected on a
                    // live tree, and not this function's problem to resolve --
                    // the caller sees Missing and decides.
                    entry.kind = EntryKind::Missing;
                } else {
                    entry.kind = EntryKind::Unknown;
                }
                break;
            }
        }
        out.push_back(entry);
    }

    ::closedir(handle);
    return true;
}

void set_pre_open_hook(PreOpenHook hook, void* user_data) {
    g_pre_open_hook = hook;
    g_pre_open_user = user_data;
}

bool open_regular(const DirHandle& dir,
                  const std::string& name,
                  const FileIdentity& expected,
                  int& fd_out,
                  std::string& error) {
    fd_out = -1;
    if (!dir.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }
    if (reject_bad_name(name, error)) {
        return false;
    }
    if (expected.kind != EntryKind::Regular) {
        // L2-SEC-004: only regular files are ever opened for work.
        error = std::string("fsops: refusing to open '") + name + "': it is a " +
                to_string(expected.kind) + ", not a regular file";
        return false;
    }

    // The race window L2-SEC-002 is about opens here. The seam lets a test
    // occupy it deterministically; production installs no hook.
    if (g_pre_open_hook != 0) {
        g_pre_open_hook(g_pre_open_user);
    }

    const int fd = ::openat(dir.fd(), name.c_str(), O_RDONLY | O_NOFOLLOW);
    if (fd < 0) {
        // ELOOP here is a symlink that O_NOFOLLOW refused — worth naming,
        // because "too many levels of symbolic links" reads as a loop rather
        // than as the deliberate rejection it is.
        if (errno == ELOOP) {
            error = "fsops: refusing to open '" + name +
                    "': it is a symbolic link (L2-SEC-003)";
            return false;
        }
        error = errno_message("cannot open '" + name + "'", errno);
        return false;
    }

    struct stat st;
    if (::fstat(fd, &st) != 0) {
        error = errno_message("cannot fstat opened '" + name + "'", errno);
        ::close(fd);
        return false;
    }

    FileIdentity actual;
    actual.dev = st.st_dev;
    actual.ino = st.st_ino;
    actual.kind = kind_from_mode(st.st_mode);

    if (!actual.same_object_as(expected)) {
        // Something replaced the entry between the classify and the open.
        // O_NOFOLLOW would not have caught it: the replacement can be an
        // ordinary regular file.
        std::ostringstream os;
        os << "fsops: '" << name
           << "' changed between classification and open"
           << " (expected dev=" << expected.dev << " ino=" << expected.ino
           << " " << to_string(expected.kind) << ", found dev=" << actual.dev
           << " ino=" << actual.ino << " " << to_string(actual.kind)
           << "); aborting (L2-SEC-002)";
        error = os.str();
        ::close(fd);
        return false;
    }

    fd_out = fd;
    return true;
}

bool check_source_trust(const DirHandle& parent,
                        int file_fd,
                        uid_t trusted_uid,
                        std::string& error) {
    if (!parent.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }

    struct stat fst;
    if (::fstat(file_fd, &fst) != 0) {
        error = errno_message("cannot fstat source descriptor", errno);
        return false;
    }
    if (!S_ISREG(fst.st_mode)) {
        error = "fsops: source is not a regular file";
        return false;
    }
    if (fst.st_uid != trusted_uid) {
        std::ostringstream os;
        os << "fsops: source is owned by uid " << fst.st_uid << ", not the "
           << "configured trusted uid " << trusted_uid
           << "; aborting (L2-SEC-005)";
        error = os.str();
        return false;
    }

    struct stat dst;
    if (::fstat(parent.fd(), &dst) != 0) {
        error = errno_message("cannot fstat source directory", errno);
        return false;
    }
    // World-writable without the sticky bit means any local user can rename
    // our source out from under us between operations.
    if ((dst.st_mode & S_IWOTH) != 0 && (dst.st_mode & S_ISVTX) == 0) {
        error =
            "fsops: source directory is world-writable without the sticky "
            "bit; any user could replace entries mid-move (L2-SEC-005)";
        return false;
    }
    return true;
}

// --- moving --------------------------------------------------------------

bool detect_strategy(const DirHandle& dir,
                     MoveStrategy& out,
                     std::string& error) {
    if (!dir.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }

    // Attempt the operation and read the errno, per L2-NFS-001. Support varies
    // by filesystem as well as kernel, so a version check would be wrong even
    // where it is convenient.
    //
    // Both names are deliberately absent, so a kernel that supports the flag
    // answers ENOENT — it got far enough to look — while one that does not
    // answers EINVAL/ENOSYS/EOPNOTSUPP before ever touching the directory.
    static const char* const kProbeFrom = ".swit-probe-src";
    static const char* const kProbeTo = ".swit-probe-dst";

    errno = 0;
    const int rc = fm_renameat2(dir.fd(), kProbeFrom, dir.fd(), kProbeTo,
                                FM_RENAME_NOREPLACE);
    const int err = errno;
    if (rc == 0) {
        // Should be unreachable: the probe names do not exist. If it somehow
        // succeeded we have just renamed something unexpected, so say so
        // rather than carry on.
        error = "fsops: RENAME_NOREPLACE probe unexpectedly succeeded";
        return false;
    }

    if (err == EINVAL || err == ENOSYS || err == EOPNOTSUPP) {
        out = MoveStrategy::LinkThenUnlink;
        return true;
    }
    if (err == ENOENT) {
        out = MoveStrategy::RenameNoReplace;
        return true;
    }

    error = errno_message("RENAME_NOREPLACE capability probe failed", err);
    return false;
}

bool move_within(const DirHandle& from_dir,
                 const std::string& from_name,
                 const DirHandle& to_dir,
                 const std::string& to_name,
                 MoveStrategy strategy,
                 std::string& error) {
    if (!from_dir.is_open() || !to_dir.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }
    if (reject_bad_name(from_name, error) || reject_bad_name(to_name, error)) {
        return false;
    }

    if (strategy == MoveStrategy::RenameNoReplace) {
        if (fm_renameat2(from_dir.fd(), from_name.c_str(), to_dir.fd(),
                         to_name.c_str(), FM_RENAME_NOREPLACE) != 0) {
            error = errno_message(
                "renameat2(RENAME_NOREPLACE) '" + from_name + "' -> '" +
                    to_name + "'",
                errno);
            return false;
        }
        return true;
    }

    // LinkThenUnlink. linkat fails EEXIST on an existing target, which is the
    // no-clobber property RENAME_NOREPLACE provides directly.
    //
    // The pair is not atomic together: a crash between them leaves both names
    // on one inode. That is the safe direction — nothing is lost — and
    // is_interrupted_move() is how recovery tells it apart from a collision.
    if (::linkat(from_dir.fd(), from_name.c_str(), to_dir.fd(),
                 to_name.c_str(), 0) != 0) {
        error = errno_message(
            "linkat '" + from_name + "' -> '" + to_name + "'", errno);
        return false;
    }
    if (::unlinkat(from_dir.fd(), from_name.c_str(), 0) != 0) {
        // The link exists, so the destination is complete; only the source
        // remains. Reported rather than swallowed, because the caller has to
        // know the source is still there.
        error = errno_message(
            "linkat succeeded but unlinkat of '" + from_name +
                "' failed; both names now reference one inode",
            errno);
        return false;
    }
    return true;
}

bool is_interrupted_move(const DirHandle& from_dir,
                         const std::string& from_name,
                         const DirHandle& to_dir,
                         const std::string& to_name,
                         bool& interrupted,
                         std::string& error) {
    interrupted = false;

    FileIdentity from;
    if (!classify(from_dir, from_name, from, error)) {
        return false;
    }
    FileIdentity to;
    if (!classify(to_dir, to_name, to, error)) {
        return false;
    }

    // Both present and the same inode: our own linkat landed and the unlinkat
    // did not. The naive reading — "the target exists, therefore collision" —
    // would fail a move that had all but completed.
    if (from.kind != EntryKind::Missing && to.kind != EntryKind::Missing) {
        interrupted = from.same_object_as(to);
    }
    return true;
}

bool publish(const DirHandle& dir,
             const std::string& temp_name,
             const std::string& final_name,
             std::string& error) {
    if (!dir.is_open()) {
        error = "fsops: directory is not open";
        return false;
    }
    if (reject_bad_name(temp_name, error) ||
        reject_bad_name(final_name, error)) {
        return false;
    }

    // fsync the file before it is given its final name, so a consumer watching
    // the destination never observes a complete-looking name over incomplete
    // data (L2-NFS-007, docs/CYBERSECURITY.md §4.5).
    const int fd = ::openat(dir.fd(), temp_name.c_str(), O_RDONLY | O_NOFOLLOW);
    if (fd < 0) {
        error = errno_message("cannot open '" + temp_name + "' to fsync",
                              errno);
        return false;
    }
    if (::fsync(fd) != 0) {
        error = errno_message("fsync of '" + temp_name + "'", errno);
        ::close(fd);
        return false;
    }
    ::close(fd);

    if (::renameat(dir.fd(), temp_name.c_str(), dir.fd(),
                   final_name.c_str()) != 0) {
        error = errno_message(
            "publishing '" + temp_name + "' as '" + final_name + "'", errno);
        return false;
    }

    // Directory fsync so the name itself is durable. Weakly defined on NFS --
    // durability there is server-side (§4.6) and is qualified on a real export
    // rather than claimed here -- but it is meaningful on the local
    // filesystems this also runs on.
    if (::fsync(dir.fd()) != 0) {
        error = errno_message("fsync of destination directory", errno);
        return false;
    }
    return true;
}

bool is_silly_rename(const std::string& name) {
    // The server picks the suffix, so match the prefix and require at least
    // one more character rather than pinning a length that varies.
    static const char kPrefix[] = ".nfs";
    const size_t prefix_len = sizeof(kPrefix) - 1;
    return name.size() > prefix_len &&
           name.compare(0, prefix_len, kPrefix) == 0;
}

bool validate_external_path(const std::string& path, std::string& error) {
    if (path.empty()) {
        error = "path is empty";
        return false;
    }
    if (path[0] != '/') {
        error = "path '" + path + "' is not absolute";
        return false;
    }

    for (std::string::size_type i = 0; i < path.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(path[i]);
        // Explicit ranges rather than <cctype>: the same locale reasoning as
        // the parsers (L3-CPP-052), and control characters are exactly what a
        // locale-sensitive check gets wrong.
        if (c < 0x20 || c == 0x7F) {
            std::ostringstream os;
            os << "path contains a control character (0x" << std::hex
               << static_cast<int>(c) << ") at offset " << std::dec << i;
            error = os.str();
            return false;
        }
    }

    // Component scan rather than a substring search for "..", so a legitimate
    // name like "my..file" is not rejected.
    std::string::size_type start = 0;
    while (start <= path.size()) {
        std::string::size_type end = path.find('/', start);
        if (end == std::string::npos) {
            end = path.size();
        }
        const std::string component = path.substr(start, end - start);
        if (component == "..") {
            error = "path '" + path + "' contains a '..' component";
            return false;
        }
        start = end + 1;
    }
    return true;
}

}  // namespace filemover
