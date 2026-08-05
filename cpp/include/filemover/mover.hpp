#ifndef FILEMOVER_MOVER_HPP
#define FILEMOVER_MOVER_HPP

// C3: the move engine — one atomic commit point.
//
// Traces: L1-SEC-001, L1-SEC-002, L1-SYS-015, L2-XFR-001, L2-XFR-004,
//         L2-JOB-014, L2-SEC-011
//
// v1.0.0 moves files by same-filesystem rename and does nothing else. There is
// no copying here: L1-SYS-015 was rewritten to remove the cross-filesystem
// clause because it contradicted L1-SEC-007, and L2-XFR-002 and the L2-COPY
// family are deferred to v1.1 with it. See docs/C3-PLAN.md §1 before adding
// anything that reads or writes file contents.
//
// The single commit point is the rename out of the source directory. Before it
// nothing has happened and the source is untouched; after it the source no
// longer exists under its original name and every remaining step is
// idempotent. No path deletes a source whose destination is not in place,
// structurally rather than by care: the source is never deleted at all, it is
// renamed, and one syscall both removes the old name and creates the new one.

#include <cstdint>
#include <string>

#include "filemover/fsops.hpp"
#include "filemover/store.hpp"

namespace filemover {

// What a caller asked for. Directories are absolute paths, validated before
// use (L2-SEC-006); names are plain entry names inside them, never paths.
struct MoveRequest {
    std::string source_dir;
    std::string source_name;
    std::string dest_dir;
    std::string dest_name;
};

// L2-XFR-001. Retained even though v1.0.0 has a single strategy: the
// cross-filesystem copy returns at v1.1, and an interface introduced then would
// be a change to every caller rather than an addition behind one.
//
// A same-filesystem rename moves every byte at once, so this fires exactly
// twice — 0/size and size/size. That is not a placeholder: a caller that
// renders progress should behave correctly when a move is instantaneous, and
// discovering otherwise at v1.1 would be discovering it in the copy path.
typedef void (*ProgressFn)(std::uint64_t bytes_done,
                           std::uint64_t bytes_total,
                           void* user_data);

// How a move ended. Distinguished rather than collapsed into a bool because
// L2-JOB-014 requires opposite handling either side of the commit point, and a
// caller cannot choose correctly from a failure it cannot tell apart.
enum class MoveOutcome {
    Completed,
    Rejected,             // refused before anything happened
    AbortedBeforeCommit,  // L2-JOB-014: nothing happened, source untouched
    HaltedAfterCommit,    // L2-JOB-014: real but unrecorded; needs an operator
    FailedExternal        // L2-SEC-011: neither source nor destination present
};

const char* to_string(MoveOutcome outcome);

// The phases a move passes through, in order. Public because the crash suite
// kills between each adjacent pair and has to name them, and because an
// operator reading a log wants the phase name rather than a number.
enum class MovePhase {
    Validate,       // 1: no side effects
    RecordRenaming, // 2: durable QUEUED -> RENAMING
    Commit,         // 3: the rename out of the source directory  <== COMMIT
    RecordMoved,    // 4: durable RENAMING -> TRANSFERRING
    Publish,        // 5: fsync and rename to the final name (idempotent)
    RecordDone      // 6: durable TRANSFERRING -> DONE
};

const char* to_string(MovePhase phase);

class MoveEngine {
  public:
    // The store must already hold the job in QUEUED: L2-JOB-013 requires the
    // intent to be durable before any filesystem action, and an engine that
    // recorded it itself would be deciding when that happened.
    explicit MoveEngine(JobStore& store);

    // Runs a move to completion or to a classified failure. `error` is set on
    // every non-Completed outcome and includes errno text where a syscall
    // failed (L2-XFR-004).
    MoveOutcome execute(const std::string& job_id,
                        const MoveRequest& request,
                        MoveStrategy strategy,
                        std::string& error);

    // Re-drives a job whose previous attempt was interrupted, deciding from
    // what is on disk rather than from what was recorded. See
    // docs/C3-PLAN.md §5.
    MoveOutcome recover(const std::string& job_id,
                        const MoveRequest& request,
                        MoveStrategy strategy,
                        std::string& error);

    void set_progress(ProgressFn fn, void* user_data);

    // The staging name a committed-but-unpublished object occupies, derived
    // from the job id. Exposed because recovery has to look for it, and a
    // caller that guessed the format would be coupled to this file anyway.
    //
    // SWIT-prefixed so an in-flight artifact on a shared NFS mount is
    // unmistakably ours — a locked decision in docs/ROADMAP.md.
    static std::string staging_name(const std::string& job_id);

    // Test seam: invoked after each phase completes, with the phase that just
    // finished. Default null; nothing in production installs one.
    //
    // Not behind an #ifdef, for the reason C1's fault injection is not — the
    // code the crash suite exercises must be the code that ships, and this is
    // the component where that matters most.
    typedef void (*PhaseHook)(MovePhase completed, void* user_data);
    void set_phase_hook(PhaseHook hook, void* user_data);

  private:
    MoveEngine(const MoveEngine&);
    MoveEngine& operator=(const MoveEngine&);

    // Phases 4 to 6, shared by execute() and recover(). Everything here is
    // past the commit point, which is why it is one function: the failure
    // handling is identical whether we just committed or are re-driving a
    // commit from a previous process, and duplicating it would be duplicating
    // the L2-JOB-014 verdict.
    MoveOutcome finish_after_commit(const std::string& job_id,
                                    const MoveRequest& request,
                                    DirHandle& dest_dir,
                                    const std::string& staging,
                                    std::int64_t tick,
                                    std::uint64_t total_bytes,
                                    std::string& error);

    JobStore& store_;
    ProgressFn progress_;
    void* progress_user_;
    PhaseHook hook_;
    void* hook_user_;
};

}  // namespace filemover

#endif  // FILEMOVER_MOVER_HPP
