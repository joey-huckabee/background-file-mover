#ifndef FILEMOVER_FSOPS_HPP
#define FILEMOVER_FSOPS_HPP

// C2: the fd-relative filesystem layer.
//
// Traces: L2-SEC-001..007, L2-NFS-001..005, L2-NFS-007
//
// Every later milestone touches the disk through this. Two shapes in the API
// are load-bearing rather than stylistic:
//
// 1. Operations take a DirHandle and a *name*, never a path. L2-SEC-001
//    prohibits path-based operations on managed trees, and an API that cannot
//    express a path is a stronger guarantee than a rule saying not to write
//    one. `make fd-relative` enforces the rest.
//
// 2. Identity is a value that gets passed back in. classify() returns what it
//    saw; open_regular() takes that observation and refuses if the object has
//    changed underneath. The window between the two is exactly what L2-SEC-002
//    exists to close, and threading the identity through the signature makes
//    the check impossible to forget.
//
// What this layer deliberately does NOT do: decide policy. It reports what is
// there and refuses what is unsafe. Whether a rejected entry aborts a job or
// is retried belongs to the move engine.

#include <sys/stat.h>
#include <sys/types.h>

#include <string>
#include <vector>

namespace filemover {

// What an entry is, determined before anything acts on it (L2-SEC-004). A
// device node smuggled into a watched directory is a classic escalation trick
// against a privileged mover, so "not a regular file" is a first-class answer
// rather than an error case.
enum class EntryKind {
    Missing,
    Regular,
    Directory,
    Symlink,
    Fifo,
    Socket,
    BlockDevice,
    CharDevice,
    Unknown
};

const char* to_string(EntryKind kind);

// The tuple L2-SEC-002 compares across the classify/open boundary.
//
// On NFS these attributes are served from the client attribute cache, so a
// stale value weakens the check without failing it. That is an accepted
// residual risk recorded in docs/CYBERSECURITY.md §4.3, not an oversight; the
// mitigation (actimeo=0) is a mount option and therefore a deployment
// decision, which is why it lives in the qualification checklist instead of
// here.
struct FileIdentity {
    dev_t dev;
    ino_t ino;
    EntryKind kind;

    FileIdentity() : dev(0), ino(0), kind(EntryKind::Missing) {}
    bool same_object_as(const FileIdentity& other) const;
};

// How a same-filesystem move is performed (L2-SEC-007, L2-NFS-001/002).
//
// LinkThenUnlink is NOT a degraded path. NFSv3 has no equivalent operation and
// NFSv4's RENAME carries no no-replace flag, so on the mount where the
// recordings live this is what production runs on every move. Both strategies
// are tested as primary.
enum class MoveStrategy {
    RenameNoReplace,
    LinkThenUnlink
};

const char* to_string(MoveStrategy strategy);

// How the move engine should treat a failure (L2-NFS-004).
//
// ESTALE is Retryable rather than Fatal: over NFS it means a handle went away
// under us, which is an expected condition on a live export, not a fault.
enum class ErrorClass {
    Retryable,
    Denied,
    Fatal
};

ErrorClass classify_errno(int err);
const char* to_string(ErrorClass klass);

// An open directory descriptor. Everything else in this header operates
// relative to one of these.
class DirHandle {
  public:
    DirHandle();
    ~DirHandle();

    // The one place a path is unavoidable: somewhere the chain has to start.
    // Opened O_RDONLY|O_DIRECTORY|O_NOFOLLOW (L2-SEC-003), so a symlinked root
    // is refused rather than followed.
    bool open_root(const std::string& path, std::string& error);

    // Descends by name from an already-open directory. No path is ever
    // assembled, so there is nothing for a `..` component to traverse.
    bool open_child(const DirHandle& parent,
                    const std::string& name,
                    std::string& error);

    void close();
    bool is_open() const;

    // For the operations below. Exposed rather than friend-ing every function;
    // holding a descriptor is not the hazard, building a path is.
    int fd() const;

  private:
    DirHandle(const DirHandle&);
    DirHandle& operator=(const DirHandle&);
    int fd_;
};

// One entry from a directory listing.
struct DirEntry {
    std::string name;
    EntryKind kind;

    DirEntry() : kind(EntryKind::Unknown) {}
};

// Lists a directory through its held descriptor. `.` and `..` are never
// returned; they are not entries a caller should have to filter.
//
// The kind is taken from the readdir result where the filesystem supplies one
// and falls back to fstatat where it does not. That fallback is not defensive
// programming: NFS commonly answers DT_UNKNOWN, so on the mount where the
// recordings actually live the fallback is the normal path — the same shape as
// RENAME_NOREPLACE in L2-NFS-002.
//
// Silly-rename artifacts ARE returned. Filtering them here would hide them
// from a caller that needs to know they exist; is_silly_rename() classifies
// them (L2-NFS-005).
bool read_entries(const DirHandle& dir,
                  std::vector<DirEntry>& out,
                  std::string& error);

// fstatat with AT_SYMLINK_NOFOLLOW. A missing entry is reported as
// EntryKind::Missing with a true return: absence is an answer, not a failure.
bool classify(const DirHandle& dir,
              const std::string& name,
              FileIdentity& out,
              std::string& error);

// openat with O_NOFOLLOW, then fstat the descriptor and compare device, inode
// and type against `expected` — aborting on mismatch (L2-SEC-002).
//
// O_NOFOLLOW stops a symlink. It does not stop a *different regular file*
// being swapped in between the classify and the open, which is what this
// closes. On success the caller owns `fd_out` and must close it.
bool open_regular(const DirHandle& dir,
                  const std::string& name,
                  const FileIdentity& expected,
                  int& fd_out,
                  std::string& error);

// L2-SEC-005: refuses unless the object is a regular file owned by
// `trusted_uid`, and its parent is not world-writable without the sticky bit.
bool check_source_trust(const DirHandle& parent,
                        int file_fd,
                        uid_t trusted_uid,
                        std::string& error);

// L2-NFS-001: determine support by *attempting* the operation and observing
// EINVAL/ENOSYS/EOPNOTSUPP. Never inferred from a kernel version — support
// varies by filesystem as well as kernel, and SLES 12 GA, SP2 and SP5 differ.
bool detect_strategy(const DirHandle& dir,
                     MoveStrategy& out,
                     std::string& error);

// Moves `from` to `to`, refusing to clobber an existing target either way.
// `strategy` is explicit so both paths are exercised deliberately rather than
// whichever the test machine happens to support.
bool move_within(const DirHandle& from_dir,
                 const std::string& from_name,
                 const DirHandle& to_dir,
                 const std::string& to_name,
                 MoveStrategy strategy,
                 std::string& error);

// L2-NFS-003: after an interrupted LinkThenUnlink, both names point at one
// inode. That is the safe direction — nothing is lost — but recovery must tell
// it apart from a genuine collision, which the naive "target exists, fail"
// reading gets wrong. True when `to_name` is the same object as `from_name`.
bool is_interrupted_move(const DirHandle& from_dir,
                         const std::string& from_name,
                         const DirHandle& to_dir,
                         const std::string& to_name,
                         bool& interrupted,
                         std::string& error);

// L2-NFS-007: rename into a temporary name in the destination directory,
// fsync, then rename to the final name. A rename is atomic on the server but
// other clients may briefly observe neither name or both, so a consumer
// watching the destination must never see a partial object under its final
// name.
bool publish(const DirHandle& dir,
             const std::string& temp_name,
             const std::string& final_name,
             std::string& error);

// L2-NFS-005: unlinking a file another NFS client holds open does not remove
// it; the server renames it to .nfsXXXX in place. These must be tolerated
// during a walk rather than reported as unexpected entries.
bool is_silly_rename(const std::string& name);

// L2-SEC-006: validate an externally supplied path before it reaches any
// system call — absolute, no `..` components, no control characters, no
// embedded newlines. Applied to configuration and API input, not to names
// already inside a managed tree.
bool validate_external_path(const std::string& path, std::string& error);

// Test seam for the L2-SEC-002 race, invoked between the classify and the
// open inside open_regular.
//
// Not behind an #ifdef, for the reason C1's fault injection is not: the code
// exercised by the test must be the code that ships, and this is the check
// where that matters most. Default null; nothing in production installs one.
// The window it exposes cannot be hit reliably by test-side timing, which is
// why the seam exists at all.
typedef void (*PreOpenHook)(void* user_data);
void set_pre_open_hook(PreOpenHook hook, void* user_data);

}  // namespace filemover

#endif  // FILEMOVER_FSOPS_HPP
