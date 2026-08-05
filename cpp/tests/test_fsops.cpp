// fd-relative filesystem layer tests (C2).
// Assertions use natural order: actual == expected (L3-CPP-014).
//
// Traces: L2-SEC-001..007, L2-NFS-001..005, L2-NFS-007
//
// Two things these tests do deliberately.
//
// Both move strategies are exercised explicitly rather than whichever the test
// machine happens to support. L2-NFS-002 makes linkat+unlinkat a primary
// tested path because it is what production runs on the NFS mount, and a test
// that used whatever detect_strategy returned would silently stop covering it
// on any filesystem with RENAME_NOREPLACE.
//
// The symlink-swap race is driven through the pre-open seam rather than by
// timing. The window between fstatat and openat cannot be hit reliably from
// outside, and a test that tried would pass by luck and fail in CI.

#include "catch2/catch.hpp"

#include "filemover/fsops.hpp"

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#include <string>

using filemover::DirHandle;
using filemover::EntryKind;
using filemover::ErrorClass;
using filemover::FileIdentity;
using filemover::MoveStrategy;

namespace {

class TempTree {
  public:
    TempTree() {
        char tmpl[] = "/tmp/fm-fsops-XXXXXX";
        const char* made = mkdtemp(tmpl);
        REQUIRE(made != 0);
        path_ = made;
    }

    ~TempTree() {
        // Best-effort recursive removal without shelling out: L2-SEC-008
        // forbids system(3) anywhere in this project, and a test that reached
        // for `rm -rf` would be the first violation of a rule the build now
        // enforces.
        remove_tree(path_);
    }

    const std::string& path() const { return path_; }

    std::string child(const std::string& name) const {
        return path_ + "/" + name;
    }

    void write_file(const std::string& name, const std::string& contents) const {
        const int fd = ::open(child(name).c_str(), O_WRONLY | O_CREAT | O_TRUNC,
                              0600);
        REQUIRE(fd >= 0);
        if (!contents.empty()) {
            const ssize_t written =
                ::write(fd, contents.data(), contents.size());
            REQUIRE(written == static_cast<ssize_t>(contents.size()));
        }
        REQUIRE(::close(fd) == 0);
    }

  private:
    TempTree(const TempTree&);
    TempTree& operator=(const TempTree&);

    static void remove_tree(const std::string& dir) {
        // Only ever one level deep in these tests; recursion is not needed and
        // opendir would add an include for no benefit.
        static const char* const kNames[] = {
            "src.txt",   "dst.txt",     "other.txt", "a.txt",  "b.txt",
            "tmp.part",  "final.txt",   "link",      "fifo",   "sub/inner.txt",
            ".nfs0001",  "swapped.txt", "probe.txt", 0};
        for (int i = 0; kNames[i] != 0; ++i) {
            ::unlink((dir + "/" + kNames[i]).c_str());
        }
        ::rmdir((dir + "/sub").c_str());
        ::rmdir(dir.c_str());
    }

    std::string path_;
};

DirHandle* open_tree(TempTree& tree, DirHandle& handle) {
    std::string error;
    REQUIRE(handle.open_root(tree.path(), error) == true);
    return &handle;
}

FileIdentity classify_ok(const DirHandle& dir, const std::string& name) {
    FileIdentity id;
    std::string error;
    INFO("classify error: " << error);
    REQUIRE(filemover::classify(dir, name, id, error) == true);
    return id;
}

}  // namespace

// --- directory handles ---------------------------------------------------

TEST_CASE("a directory root opens and a missing one does not",
          "[fsops][L2-SEC-003]") {
    TempTree tree;
    DirHandle dir;
    open_tree(tree, dir);
    CHECK(dir.is_open() == true);

    DirHandle missing;
    std::string error;
    CHECK(missing.open_root(tree.child("nope"), error) == false);
    CHECK(error.empty() == false);
}

TEST_CASE("a symlinked root is refused, not followed",
          "[fsops][L2-SEC-003]") {
    TempTree tree;
    REQUIRE(::mkdir(tree.child("sub").c_str(), 0700) == 0);
    REQUIRE(::symlink(tree.child("sub").c_str(), tree.child("link").c_str()) ==
            0);

    DirHandle dir;
    std::string error;
    // O_NOFOLLOW makes this ELOOP rather than a successful open of the target.
    CHECK(dir.open_root(tree.child("link"), error) == false);
    CHECK(dir.is_open() == false);
}

TEST_CASE("a name containing a separator is refused",
          "[fsops][L2-SEC-001]") {
    TempTree tree;
    DirHandle dir;
    open_tree(tree, dir);

    // The API takes names, not paths. Rejecting a separator is what makes the
    // "no path-based operations" rule structural rather than advisory.
    FileIdentity id;
    std::string error;
    CHECK(filemover::classify(dir, "sub/inner.txt", id, error) == false);
    CHECK(filemover::classify(dir, "..", id, error) == false);
    CHECK(filemover::classify(dir, "", id, error) == false);
}

// --- classification ------------------------------------------------------

TEST_CASE("entries are classified by type before anything acts on them",
          "[fsops][L2-SEC-004]") {
    TempTree tree;
    tree.write_file("src.txt", "hello");
    REQUIRE(::mkdir(tree.child("sub").c_str(), 0700) == 0);
    REQUIRE(::symlink(tree.child("src.txt").c_str(),
                      tree.child("link").c_str()) == 0);
    REQUIRE(::mkfifo(tree.child("fifo").c_str(), 0600) == 0);

    DirHandle dir;
    open_tree(tree, dir);

    CHECK(classify_ok(dir, "src.txt").kind == EntryKind::Regular);
    CHECK(classify_ok(dir, "sub").kind == EntryKind::Directory);
    // The symlink is reported as a symlink, not as what it points at.
    CHECK(classify_ok(dir, "link").kind == EntryKind::Symlink);
    CHECK(classify_ok(dir, "fifo").kind == EntryKind::Fifo);
}

TEST_CASE("an absent entry is an answer, not a failure",
          "[fsops][L2-SEC-004]") {
    TempTree tree;
    DirHandle dir;
    open_tree(tree, dir);

    FileIdentity id;
    std::string error;
    // A caller checking for a destination collision should not have to
    // distinguish "not there" from "the query broke".
    REQUIRE(filemover::classify(dir, "dst.txt", id, error) == true);
    CHECK(id.kind == EntryKind::Missing);
    CHECK(error.empty() == true);
}

// --- opening with identity verification ----------------------------------

TEST_CASE("a regular file opens and reports the same identity",
          "[fsops][L2-SEC-002]") {
    TempTree tree;
    tree.write_file("src.txt", "hello");
    DirHandle dir;
    open_tree(tree, dir);

    const FileIdentity id = classify_ok(dir, "src.txt");
    int fd = -1;
    std::string error;
    REQUIRE(filemover::open_regular(dir, "src.txt", id, fd, error) == true);
    CHECK(fd >= 0);
    ::close(fd);
}

TEST_CASE("only regular files are opened", "[fsops][L2-SEC-004]") {
    TempTree tree;
    REQUIRE(::mkdir(tree.child("sub").c_str(), 0700) == 0);
    REQUIRE(::mkfifo(tree.child("fifo").c_str(), 0600) == 0);
    DirHandle dir;
    open_tree(tree, dir);

    int fd = -1;
    std::string error;
    CHECK(filemover::open_regular(dir, "sub", classify_ok(dir, "sub"), fd,
                                  error) == false);
    CHECK(fd == -1);
    CHECK(filemover::open_regular(dir, "fifo", classify_ok(dir, "fifo"), fd,
                                  error) == false);
    CHECK(fd == -1);
}

namespace {

// Replaces src.txt with a *different* regular file, by renaming a file
// prepared in advance over it. Installed as the pre-open hook so the swap
// lands inside the window between fstatat and openat.
//
// Renaming rather than unlink-then-recreate, and the difference is not
// cosmetic. The first version of this test recreated the file in place and the
// check did not fire: the kernel handed the new file the inode it had just
// freed, so dev/ino matched and the swap was invisible. Renaming a prepared
// file guarantees a distinct inode -- and is what an attacker would actually
// do, since it is atomic and leaves no window where the name is absent.
//
// Worth recording as a residual limit of the L2-SEC-002 check: it compares
// dev/ino/type, so a replacement that manages to reuse the inode would pass
// it. The requirement specifies those attributes, and nothing cheaper is
// available on a POSIX filesystem, but "identity" here means "the same
// dev/ino", not "provably the same object".
struct Swapper {
    std::string doomed;
    std::string prepared;
    int calls;

    Swapper() : calls(0) {}
};

void swap_file(void* user) {
    Swapper* s = static_cast<Swapper*>(user);
    s->calls += 1;
    ::rename(s->prepared.c_str(), s->doomed.c_str());
}

}  // namespace

TEST_CASE("a file swapped between classify and open is refused",
          "[fsops][L2-SEC-002]") {
    TempTree tree;
    tree.write_file("src.txt", "original");
    tree.write_file("swapped.txt", "attacker");
    DirHandle dir;
    open_tree(tree, dir);

    const FileIdentity id = classify_ok(dir, "src.txt");
    // Distinct inodes, asserted rather than assumed -- the whole test depends
    // on it, and it is exactly what silently failed the first time.
    REQUIRE(classify_ok(dir, "swapped.txt").ino != id.ino);

    Swapper swapper;
    swapper.doomed = tree.child("src.txt");
    swapper.prepared = tree.child("swapped.txt");
    filemover::set_pre_open_hook(swap_file, &swapper);

    int fd = -1;
    std::string error;
    const bool opened = filemover::open_regular(dir, "src.txt", id, fd, error);

    filemover::set_pre_open_hook(0, 0);

    // The replacement is an ordinary regular file, so O_NOFOLLOW does nothing
    // here. Only the dev/ino comparison catches it -- which is the entire
    // reason L2-SEC-002 exists on top of L2-SEC-003.
    CHECK(swapper.calls == 1);
    CHECK(opened == false);
    CHECK(fd == -1);
    CHECK(error.find("changed between classification and open") !=
          std::string::npos);
}

TEST_CASE("a symlink put in place of a regular file is refused",
          "[fsops][L2-SEC-003]") {
    TempTree tree;
    tree.write_file("src.txt", "original");
    tree.write_file("other.txt", "target");
    DirHandle dir;
    open_tree(tree, dir);
    const FileIdentity id = classify_ok(dir, "src.txt");

    // Replace the regular file with a symlink after classification.
    REQUIRE(::unlink(tree.child("src.txt").c_str()) == 0);
    REQUIRE(::symlink(tree.child("other.txt").c_str(),
                      tree.child("src.txt").c_str()) == 0);

    int fd = -1;
    std::string error;
    CHECK(filemover::open_regular(dir, "src.txt", id, fd, error) == false);
    CHECK(fd == -1);
    CHECK(error.find("symbolic link") != std::string::npos);
}

// --- strategy detection and moving ---------------------------------------

TEST_CASE("the move strategy is detected by attempting the operation",
          "[fsops][L2-NFS-001]") {
    TempTree tree;
    DirHandle dir;
    open_tree(tree, dir);

    MoveStrategy strategy = MoveStrategy::LinkThenUnlink;
    std::string error;
    REQUIRE(filemover::detect_strategy(dir, strategy, error) == true);

    // Either answer is correct -- which one depends on the filesystem under
    // /tmp, and that is the point: capability is never inferred from a kernel
    // version. What matters is that the probe reaches a verdict without
    // disturbing anything.
    CHECK((strategy == MoveStrategy::RenameNoReplace ||
           strategy == MoveStrategy::LinkThenUnlink));
    CHECK(classify_ok(dir, "probe.txt").kind == EntryKind::Missing);
}

TEST_CASE("both move strategies move a file", "[fsops][L2-SEC-007][L2-NFS-002]") {
    // Explicitly parameterised rather than using whatever detect_strategy
    // returns: linkat+unlinkat is what production runs on NFS, so it must be
    // covered on every machine that runs these tests.
    const MoveStrategy strategies[2] = {MoveStrategy::RenameNoReplace,
                                        MoveStrategy::LinkThenUnlink};
    for (int i = 0; i < 2; ++i) {
        TempTree tree;
        tree.write_file("src.txt", "payload");
        DirHandle dir;
        open_tree(tree, dir);

        std::string error;
        INFO("strategy: " << filemover::to_string(strategies[i]));
        REQUIRE(filemover::move_within(dir, "src.txt", dir, "dst.txt",
                                       strategies[i], error) == true);

        CHECK(classify_ok(dir, "src.txt").kind == EntryKind::Missing);
        CHECK(classify_ok(dir, "dst.txt").kind == EntryKind::Regular);
    }
}

TEST_CASE("neither strategy will clobber an existing target",
          "[fsops][L2-SEC-007][L2-NFS-002]") {
    const MoveStrategy strategies[2] = {MoveStrategy::RenameNoReplace,
                                        MoveStrategy::LinkThenUnlink};
    for (int i = 0; i < 2; ++i) {
        TempTree tree;
        tree.write_file("src.txt", "payload");
        tree.write_file("dst.txt", "PRECIOUS");
        DirHandle dir;
        open_tree(tree, dir);

        std::string error;
        INFO("strategy: " << filemover::to_string(strategies[i]));
        CHECK(filemover::move_within(dir, "src.txt", dir, "dst.txt",
                                     strategies[i], error) == false);

        // Both names still present, and the destination untouched. This is the
        // no-clobber property: RENAME_NOREPLACE provides it directly, linkat
        // provides it by failing EEXIST.
        CHECK(classify_ok(dir, "src.txt").kind == EntryKind::Regular);
        CHECK(classify_ok(dir, "dst.txt").kind == EntryKind::Regular);
    }
}

TEST_CASE("an interrupted link/unlink pair is not a collision",
          "[fsops][L2-NFS-003]") {
    TempTree tree;
    tree.write_file("src.txt", "payload");
    DirHandle dir;
    open_tree(tree, dir);

    // Exactly the state a crash between linkat and unlinkat leaves: both names
    // on one inode. Reproduced with a hard link, which needs no crash and no
    // NFS.
    REQUIRE(::link(tree.child("src.txt").c_str(),
                   tree.child("dst.txt").c_str()) == 0);

    bool interrupted = false;
    std::string error;
    REQUIRE(filemover::is_interrupted_move(dir, "src.txt", dir, "dst.txt",
                                           interrupted, error) == true);
    // The naive reading -- "the target exists, therefore collision" -- would
    // fail a move that had all but completed.
    CHECK(interrupted == true);
}

TEST_CASE("a genuine collision is distinguished from an interrupted move",
          "[fsops][L2-NFS-003]") {
    TempTree tree;
    tree.write_file("src.txt", "ours");
    tree.write_file("dst.txt", "someone else's");
    DirHandle dir;
    open_tree(tree, dir);

    bool interrupted = true;
    std::string error;
    REQUIRE(filemover::is_interrupted_move(dir, "src.txt", dir, "dst.txt",
                                           interrupted, error) == true);
    CHECK(interrupted == false);
}

// --- publishing ----------------------------------------------------------

TEST_CASE("publishing is a two-hop rename inside the destination directory",
          "[fsops][L2-NFS-007]") {
    TempTree tree;
    tree.write_file("tmp.part", "complete payload");
    DirHandle dir;
    open_tree(tree, dir);

    std::string error;
    REQUIRE(filemover::publish(dir, "tmp.part", "final.txt", error) == true);

    CHECK(classify_ok(dir, "tmp.part").kind == EntryKind::Missing);
    CHECK(classify_ok(dir, "final.txt").kind == EntryKind::Regular);
}

TEST_CASE("publishing a missing temporary is an error",
          "[fsops][L2-NFS-007]") {
    TempTree tree;
    DirHandle dir;
    open_tree(tree, dir);

    std::string error;
    CHECK(filemover::publish(dir, "tmp.part", "final.txt", error) == false);
    CHECK(error.empty() == false);
}

// --- NFS artifacts and errno classification ------------------------------

TEST_CASE("silly-rename artifacts are recognised", "[fsops][L2-NFS-005]") {
    CHECK(filemover::is_silly_rename(".nfs0001") == true);
    CHECK(filemover::is_silly_rename(".nfsA1B2C3D4") == true);
    // Not artifacts: the bare prefix, and ordinary dotfiles.
    CHECK(filemover::is_silly_rename(".nfs") == false);
    CHECK(filemover::is_silly_rename(".nfsrc") == true);
    CHECK(filemover::is_silly_rename("recording.mp4") == false);
    CHECK(filemover::is_silly_rename(".hidden") == false);
    CHECK(filemover::is_silly_rename("") == false);
}

TEST_CASE("ESTALE is retryable rather than a fault", "[fsops][L2-NFS-004]") {
    // The one that matters: on a live export a handle going away under us is
    // expected, and calling it fatal would fail moves a retry completes.
    CHECK(filemover::classify_errno(ESTALE) == ErrorClass::Retryable);
    CHECK(filemover::classify_errno(EAGAIN) == ErrorClass::Retryable);
    CHECK(filemover::classify_errno(ENOSPC) == ErrorClass::Retryable);

    CHECK(filemover::classify_errno(EACCES) == ErrorClass::Denied);
    CHECK(filemover::classify_errno(EPERM) == ErrorClass::Denied);
    CHECK(filemover::classify_errno(EROFS) == ErrorClass::Denied);

    CHECK(filemover::classify_errno(EEXIST) == ErrorClass::Fatal);
    CHECK(filemover::classify_errno(EINVAL) == ErrorClass::Fatal);
}

// --- external path validation --------------------------------------------

TEST_CASE("external paths are validated before use", "[fsops][L2-SEC-006]") {
    std::string error;

    CHECK(filemover::validate_external_path("/srv/recordings/a.mp4", error) ==
          true);

    CHECK(filemover::validate_external_path("", error) == false);
    CHECK(filemover::validate_external_path("relative/path", error) == false);
    CHECK(filemover::validate_external_path("/srv/../etc/shadow", error) ==
          false);
    CHECK(filemover::validate_external_path("/srv/..", error) == false);
    CHECK(filemover::validate_external_path("/srv/a\nb", error) == false);
    CHECK(filemover::validate_external_path(std::string("/srv/a\0b", 8),
                                            error) == false);

    // A component merely containing dots is fine; only an exact ".." is a
    // traversal. A substring search for ".." would reject this.
    CHECK(filemover::validate_external_path("/srv/my..file", error) == true);
    CHECK(filemover::validate_external_path("/srv/...", error) == true);
}

// --- misuse of a closed handle -------------------------------------------

TEST_CASE("every operation on a closed directory fails cleanly",
          "[fsops][L2-SEC-001]") {
    DirHandle closed;
    DirHandle other;
    std::string error;
    REQUIRE(closed.is_open() == false);

    FileIdentity id;
    CHECK(filemover::classify(closed, "x", id, error) == false);
    CHECK(error.empty() == false);

    int fd = -1;
    FileIdentity expected;
    expected.kind = EntryKind::Regular;
    CHECK(filemover::open_regular(closed, "x", expected, fd, error) == false);
    CHECK(fd == -1);

    MoveStrategy strategy = MoveStrategy::RenameNoReplace;
    CHECK(filemover::detect_strategy(closed, strategy, error) == false);
    CHECK(filemover::move_within(closed, "a", other, "b",
                                 MoveStrategy::RenameNoReplace, error) ==
          false);
    CHECK(filemover::publish(closed, "a", "b", error) == false);
    CHECK(filemover::check_source_trust(closed, 0, ::getuid(), error) == false);

    DirHandle child;
    CHECK(child.open_child(closed, "sub", error) == false);
}

TEST_CASE("closing a directory handle is idempotent", "[fsops][L2-SEC-001]") {
    TempTree tree;
    DirHandle dir;
    open_tree(tree, dir);
    dir.close();
    dir.close();
    CHECK(dir.is_open() == false);
    CHECK(dir.fd() < 0);
}

TEST_CASE("a subdirectory opens by name from its parent",
          "[fsops][L2-SEC-001]") {
    TempTree tree;
    REQUIRE(::mkdir(tree.child("sub").c_str(), 0700) == 0);
    DirHandle root;
    open_tree(tree, root);

    DirHandle sub;
    std::string error;
    REQUIRE(sub.open_child(root, "sub", error) == true);
    CHECK(sub.is_open() == true);

    // No path is assembled anywhere, so there is nothing for a `..` component
    // to traverse -- it is rejected as a name instead.
    DirHandle escape;
    CHECK(escape.open_child(root, "..", error) == false);
    CHECK(escape.open_child(root, "sub/deeper", error) == false);
    CHECK(escape.open_child(root, "missing", error) == false);
}

TEST_CASE("enum names round-trip to stable tokens", "[fsops][L2-SEC-004]") {
    // Logged per tree and per rejected entry, so the tokens are an operator
    // interface rather than debug output.
    CHECK(std::string(filemover::to_string(EntryKind::Regular)) == "REGULAR");
    CHECK(std::string(filemover::to_string(EntryKind::Symlink)) == "SYMLINK");
    CHECK(std::string(filemover::to_string(EntryKind::Missing)) == "MISSING");
    CHECK(std::string(filemover::to_string(EntryKind::BlockDevice)) ==
          "BLOCK_DEVICE");
    CHECK(std::string(filemover::to_string(EntryKind::CharDevice)) ==
          "CHAR_DEVICE");
    CHECK(std::string(filemover::to_string(EntryKind::Socket)) == "SOCKET");
    CHECK(std::string(filemover::to_string(EntryKind::Directory)) ==
          "DIRECTORY");
    CHECK(std::string(filemover::to_string(EntryKind::Fifo)) == "FIFO");
    CHECK(std::string(filemover::to_string(EntryKind::Unknown)) == "UNKNOWN");

    CHECK(std::string(filemover::to_string(MoveStrategy::RenameNoReplace)) ==
          "RENAME_NOREPLACE");
    CHECK(std::string(filemover::to_string(MoveStrategy::LinkThenUnlink)) ==
          "LINK_THEN_UNLINK");

    CHECK(std::string(filemover::to_string(ErrorClass::Retryable)) ==
          "RETRYABLE");
    CHECK(std::string(filemover::to_string(ErrorClass::Denied)) == "DENIED");
    CHECK(std::string(filemover::to_string(ErrorClass::Fatal)) == "FATAL");
}

TEST_CASE("moving refuses a name that is not a plain entry name",
          "[fsops][L2-SEC-001]") {
    TempTree tree;
    tree.write_file("src.txt", "payload");
    DirHandle dir;
    open_tree(tree, dir);

    std::string error;
    CHECK(filemover::move_within(dir, "src.txt", dir, "sub/dst.txt",
                                 MoveStrategy::RenameNoReplace, error) ==
          false);
    CHECK(filemover::move_within(dir, "../src.txt", dir, "dst.txt",
                                 MoveStrategy::LinkThenUnlink, error) == false);
    CHECK(filemover::publish(dir, "src.txt", "a/b", error) == false);

    // Nothing moved.
    CHECK(classify_ok(dir, "src.txt").kind == EntryKind::Regular);
}

TEST_CASE("a move of a missing source fails under both strategies",
          "[fsops][L2-SEC-007]") {
    const MoveStrategy strategies[2] = {MoveStrategy::RenameNoReplace,
                                        MoveStrategy::LinkThenUnlink};
    for (int i = 0; i < 2; ++i) {
        TempTree tree;
        DirHandle dir;
        open_tree(tree, dir);
        std::string error;
        INFO("strategy: " << filemover::to_string(strategies[i]));
        CHECK(filemover::move_within(dir, "src.txt", dir, "dst.txt",
                                     strategies[i], error) == false);
        CHECK(error.empty() == false);
    }
}

// --- source trust --------------------------------------------------------

TEST_CASE("a source owned by the trusted uid is accepted",
          "[fsops][L2-SEC-005]") {
    TempTree tree;
    tree.write_file("src.txt", "payload");
    DirHandle dir;
    open_tree(tree, dir);

    int fd = -1;
    std::string error;
    REQUIRE(filemover::open_regular(dir, "src.txt",
                                    classify_ok(dir, "src.txt"), fd,
                                    error) == true);

    CHECK(filemover::check_source_trust(dir, fd, ::getuid(), error) == true);

    // A different uid is refused. Using our own uid + 1 avoids needing root to
    // create a file owned by someone else.
    CHECK(filemover::check_source_trust(dir, fd, ::getuid() + 1, error) ==
          false);
    CHECK(error.find("trusted uid") != std::string::npos);
    ::close(fd);
}

TEST_CASE("a world-writable source directory without the sticky bit is refused",
          "[fsops][L2-SEC-005]") {
    TempTree tree;
    tree.write_file("src.txt", "payload");
    REQUIRE(::chmod(tree.path().c_str(), 0777) == 0);

    DirHandle dir;
    open_tree(tree, dir);
    int fd = -1;
    std::string error;
    REQUIRE(filemover::open_regular(dir, "src.txt",
                                    classify_ok(dir, "src.txt"), fd,
                                    error) == true);

    // Any local user could rename our source away between operations.
    CHECK(filemover::check_source_trust(dir, fd, ::getuid(), error) == false);
    CHECK(error.find("world-writable") != std::string::npos);

    // The sticky bit closes it, which is why /tmp itself is acceptable.
    REQUIRE(::chmod(tree.path().c_str(), 01777) == 0);
    CHECK(filemover::check_source_trust(dir, fd, ::getuid(), error) == true);
    ::close(fd);
    REQUIRE(::chmod(tree.path().c_str(), 0700) == 0);
}
