// C3: the move engine.
// Traces: L1-SEC-001, L1-SEC-002, L1-SYS-015, L2-XFR-001, L2-XFR-004,
//         L2-JOB-014, L2-SEC-011

#include "filemover/mover.hpp"

#include <unistd.h>

#include <sstream>

namespace filemover {
namespace {

// Clock values are supplied by the caller everywhere else in this project
// (job.hpp is explicit that it never reads a clock). The engine needs
// monotonically increasing timestamps for the state transitions and has no
// clock of its own, so it derives them from the job's existing timestamps.
// This keeps the engine testable without an injected clock, which C4 will add
// when scheduling needs one.
std::int64_t next_tick(std::int64_t previous) { return previous + 1; }

}  // namespace

const char* to_string(MoveOutcome outcome) {
    switch (outcome) {
        case MoveOutcome::Completed:            return "COMPLETED";
        case MoveOutcome::Rejected:             return "REJECTED";
        case MoveOutcome::AbortedBeforeCommit:  return "ABORTED_BEFORE_COMMIT";
        case MoveOutcome::HaltedAfterCommit:    return "HALTED_AFTER_COMMIT";
        case MoveOutcome::FailedExternal:       return "FAILED_EXTERNAL";
    }
    return "REJECTED";
}

const char* to_string(MovePhase phase) {
    switch (phase) {
        case MovePhase::Validate:       return "VALIDATE";
        case MovePhase::RecordRenaming: return "RECORD_RENAMING";
        case MovePhase::Commit:         return "COMMIT";
        case MovePhase::RecordMoved:    return "RECORD_MOVED";
        case MovePhase::Publish:        return "PUBLISH";
        case MovePhase::RecordDone:     return "RECORD_DONE";
    }
    return "VALIDATE";
}

std::string MoveEngine::staging_name(const std::string& job_id) {
    // Hybrid naming, a locked decision: the operator-facing name is generic,
    // on-disk staging markers are SWIT-prefixed so an in-flight artifact on a
    // shared NFS mount is unmistakably ours.
    return ".swit-partial-" + job_id;
}

MoveEngine::MoveEngine(JobStore& store)
    : store_(store),
      progress_(0),
      progress_user_(0),
      hook_(0),
      hook_user_(0) {}

void MoveEngine::set_progress(ProgressFn fn, void* user_data) {
    progress_ = fn;
    progress_user_ = user_data;
}

void MoveEngine::set_phase_hook(PhaseHook hook, void* user_data) {
    hook_ = hook;
    hook_user_ = user_data;
}

MoveOutcome MoveEngine::execute(const std::string& job_id,
                                const MoveRequest& request,
                                MoveStrategy strategy,
                                std::string& error) {
    error.clear();

    // ---- phase 1: validate. No side effects, so anything here is Rejected.
    if (!validate_external_path(request.source_dir, error) ||
        !validate_external_path(request.dest_dir, error)) {
        return MoveOutcome::Rejected;
    }

    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    if (!store_.load(job_id, job, found, error)) {
        return MoveOutcome::Rejected;
    }
    if (!found) {
        // L2-JOB-013: the intent must already be durable. An engine that
        // recorded it here would be choosing when "before any filesystem
        // action" starts, which is the caller's decision to have made.
        error = "mover: no durable record for job '" + job_id +
                "'; intent must be recorded before any filesystem action "
                "(L2-JOB-013)";
        return MoveOutcome::Rejected;
    }

    DirHandle source_dir;
    DirHandle dest_dir;
    if (!source_dir.open_root(request.source_dir, error) ||
        !dest_dir.open_root(request.dest_dir, error)) {
        return MoveOutcome::Rejected;
    }

    FileIdentity source_id;
    if (!classify(source_dir, request.source_name, source_id, error)) {
        return MoveOutcome::Rejected;
    }
    if (source_id.kind == EntryKind::Missing) {
        error = "mover: source '" + request.source_name + "' does not exist";
        return MoveOutcome::Rejected;
    }
    if (source_id.kind != EntryKind::Regular) {
        // L2-SEC-004. A device node smuggled into a watched directory is a
        // classic escalation trick against a privileged mover.
        error = std::string("mover: refusing '") + request.source_name +
                "': it is a " + to_string(source_id.kind) +
                ", not a regular file";
        return MoveOutcome::Rejected;
    }

    // Opening with identity verification is what closes the swap window
    // (L2-SEC-002). The descriptor is held only to prove the object did not
    // change; the move itself is name-based against the same directory
    // descriptor.
    int source_fd = -1;
    if (!open_regular(source_dir, request.source_name, source_id, source_fd,
                      error)) {
        return MoveOutcome::Rejected;
    }

    std::uint64_t total_bytes = 0;
    {
        // Size is read for the progress callback only. It is not a correctness
        // input: a rename moves whatever is there.
        FileIdentity again;
        if (classify(source_dir, request.source_name, again, error)) {
            total_bytes = job.bytes_total;
        }
    }
    ::close(source_fd);

    if (progress_ != 0) {
        progress_(0, total_bytes, progress_user_);
    }
    if (hook_ != 0) {
        hook_(MovePhase::Validate, hook_user_);
    }

    // ---- phase 2: durable QUEUED -> RENAMING. Before the commit point.
    const std::string staging = staging_name(job_id);
    const std::int64_t tick = next_tick(job.updated_at_ms);

    // Idempotent for the same reason the post-commit path is, and it is easy
    // to miss here because "everything before the commit point is disposable"
    // sounds like nothing needs care. The filesystem work is disposable; the
    // durable record is not. A crash between phase 2 and phase 3 leaves the
    // job in RENAMING with the source still in place, and re-driving must
    // continue from there rather than re-issue a transition the store will
    // correctly refuse.
    if (job.state == JobState::Done) {
        return MoveOutcome::Completed;
    }
    if (job.state == JobState::Failed) {
        error = "mover: job '" + job_id +
                "' is already FAILED; refusing to resurrect it";
        return MoveOutcome::Rejected;
    }
    if (job.state == JobState::Queued &&
        store_.record_transition(job_id, JobState::Renaming, tick, "",
                                 CommitPhase::BeforeCommitPoint, error) !=
        WriteFailureAction::None) {
        // L2-JOB-014 before the commit point: nothing has happened, the source
        // is untouched, and the entry is discarded. Acting without a durable
        // record is what leaves an orphaned file nobody can account for.
        return MoveOutcome::AbortedBeforeCommit;
    }
    if (hook_ != 0) {
        hook_(MovePhase::RecordRenaming, hook_user_);
    }

    // ---- phase 3: THE COMMIT POINT. One rename, out of the source directory.
    if (!move_within(source_dir, request.source_name, dest_dir, staging,
                     strategy, error)) {
        // Still before the commit point in effect: the rename did not happen,
        // so the source remains at its original name.
        std::string ignored;
        store_.record_transition(job_id, JobState::Failed,
                                 next_tick(tick), error,
                                 CommitPhase::BeforeCommitPoint, ignored);
        return MoveOutcome::AbortedBeforeCommit;
    }
    if (hook_ != 0) {
        hook_(MovePhase::Commit, hook_user_);
    }

    return finish_after_commit(job_id, request, dest_dir, staging,
                               next_tick(tick), total_bytes, error);
}

MoveOutcome MoveEngine::finish_after_commit(const std::string& job_id,
                                            const MoveRequest& request,
                                            DirHandle& dest_dir,
                                            const std::string& staging,
                                            std::int64_t tick,
                                            std::uint64_t total_bytes,
                                            std::string& error) {
    // Everything below the commit point must be idempotent (L1-SEC-002), and
    // that has to include the *state machine*, not just the filesystem. The
    // first version of this re-issued every transition unconditionally, so
    // re-driving a job already in TRANSFERRING failed with "illegal
    // transition: TRANSFERRING -> TRANSFERRING" -- correct of the store to
    // refuse, and wrong of the engine to ask. The crash suite caught it at
    // three of the five kill points.
    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    if (!store_.load(job_id, job, found, error) || !found) {
        if (error.empty()) {
            error = "mover: no durable record for job '" + job_id + "'";
        }
        return MoveOutcome::HaltedAfterCommit;
    }

    if (job.state == JobState::Done) {
        // Already finished by a previous attempt. Re-driving reaches the same
        // state, which is what idempotent means here.
        return MoveOutcome::Completed;
    }
    if (job.state == JobState::Failed) {
        error = "mover: job '" + job_id +
                "' is already FAILED; refusing to resurrect it";
        return MoveOutcome::HaltedAfterCommit;
    }

    // ---- phase 4: durable RENAMING -> TRANSFERRING. After the commit point.
    if (job.state == JobState::Renaming &&
        store_.record_transition(job_id, JobState::Transferring, tick, "",
                                 CommitPhase::AfterCommitPoint, error) !=
        WriteFailureAction::None) {
        // L2-JOB-014 after the commit point: the move is real but unrecorded.
        // Halt. The flag is best-effort -- if the store is unwritable, this
        // write fails too, which is why the requirement also demands a
        // high-severity log. The log is the guarantee.
        std::string ignored;
        store_.mark_needs_attention(job_id, error, ignored);
        return MoveOutcome::HaltedAfterCommit;
    }
    if (hook_ != 0) {
        hook_(MovePhase::RecordMoved, hook_user_);
    }

    // ---- phase 5: publish. Idempotent: re-driving reaches the same state.
    //
    // A previous attempt may already have published, in which case the staging
    // name is gone and the final name is present. That is success, not a
    // missing file -- so the state is read before concluding anything.
    FileIdentity staged;
    FileIdentity final_id;
    std::string probe_error;
    const bool saw_staged =
        classify(dest_dir, staging, staged, probe_error) &&
        staged.kind != EntryKind::Missing;
    const bool saw_final =
        classify(dest_dir, request.dest_name, final_id, probe_error) &&
        final_id.kind != EntryKind::Missing;

    if (saw_staged) {
        if (!publish(dest_dir, staging, request.dest_name, error)) {
            std::string ignored;
            store_.mark_needs_attention(job_id, error, ignored);
            return MoveOutcome::HaltedAfterCommit;
        }
    } else if (!saw_final) {
        // Neither name is present past the commit point: the object we moved
        // has been removed by something else.
        error = "mover: job '" + job_id +
                "' is past the commit point but neither the staged nor the "
                "final name exists; the delivered object was removed "
                "externally (L2-SEC-011)";
        std::string ignored;
        store_.mark_needs_attention(job_id, error, ignored);
        return MoveOutcome::FailedExternal;
    }
    if (progress_ != 0) {
        progress_(total_bytes, total_bytes, progress_user_);
    }
    if (hook_ != 0) {
        hook_(MovePhase::Publish, hook_user_);
    }

    // ---- phase 6: durable TRANSFERRING -> DONE.
    if (store_.record_transition(job_id, JobState::Done, next_tick(tick), "",
                                 CommitPhase::AfterCommitPoint, error) !=
        WriteFailureAction::None) {
        // Delivered but unrecorded: reality and the record disagree, which is
        // precisely the ambiguity L1-SEC-002 exists to prevent.
        std::string ignored;
        store_.mark_needs_attention(job_id, error, ignored);
        return MoveOutcome::HaltedAfterCommit;
    }
    if (hook_ != 0) {
        hook_(MovePhase::RecordDone, hook_user_);
    }

    return MoveOutcome::Completed;
}

MoveOutcome MoveEngine::recover(const std::string& job_id,
                                const MoveRequest& request,
                                MoveStrategy strategy,
                                std::string& error) {
    error.clear();

    DirHandle source_dir;
    DirHandle dest_dir;
    if (!source_dir.open_root(request.source_dir, error) ||
        !dest_dir.open_root(request.dest_dir, error)) {
        return MoveOutcome::Rejected;
    }

    const std::string staging = staging_name(job_id);

    // Decided from what is on disk, never from what was recorded. A crash can
    // leave the record behind the filesystem by exactly one step, so the
    // filesystem is the authority on how far the move got.
    MoveState state = MoveState::NotStarted;
    if (!classify_move_state(source_dir, request.source_name, dest_dir, staging,
                             state, error)) {
        return MoveOutcome::Rejected;
    }

    Job job(std::string(), std::string(), std::string(), 0);
    bool found = false;
    if (!store_.load(job_id, job, found, error) || !found) {
        if (error.empty()) {
            error = "mover: no durable record for job '" + job_id + "'";
        }
        return MoveOutcome::Rejected;
    }
    const std::int64_t tick = next_tick(job.updated_at_ms);

    switch (state) {
        case MoveState::NotStarted:
            // The commit never happened. Everything before it is disposable,
            // so start again from the top.
            return execute(job_id, request, strategy, error);

        case MoveState::Interrupted: {
            // The NFS path: linkat landed, unlinkat did not, so both names
            // reference one inode. Finishing the unlinkat completes the commit
            // rather than restarting it -- treating this as a collision would
            // fail a move that had all but completed.
            if (!move_within(source_dir, request.source_name, dest_dir, staging,
                             MoveStrategy::LinkThenUnlink, error)) {
                std::string ignored;
                store_.mark_needs_attention(job_id, error, ignored);
                return MoveOutcome::HaltedAfterCommit;
            }
            return finish_after_commit(job_id, request, dest_dir, staging, tick,
                                       job.bytes_total, error);
        }

        case MoveState::Completed:
            // Committed; phase 5 may or may not have run. Publishing is
            // idempotent, so re-driving is always safe.
            return finish_after_commit(job_id, request, dest_dir, staging, tick,
                                       job.bytes_total, error);

        case MoveState::Collision: {
            error = "mover: '" + staging +
                    "' exists and is not the object we moved; refusing to "
                    "clobber it";
            std::string ignored;
            store_.record_transition(job_id, JobState::Failed, tick, error,
                                     CommitPhase::AfterCommitPoint, ignored);
            return MoveOutcome::HaltedAfterCommit;
        }

        case MoveState::BothMissing: {
            // L2-SEC-011. Quarantine by endpoint security produces exactly
            // this by removing the source after intent was recorded. It is a
            // modelled outcome, not an assertion failure -- and explicitly not
            // retried automatically, because retrying cannot conjure a file
            // something else removed on purpose.
            //
            // Checked last: a published destination makes Completed the right
            // answer even when the staging name is gone, so BothMissing must
            // not be concluded before the final name has been looked for.
            FileIdentity final_id;
            std::string probe_error;
            if (classify(dest_dir, request.dest_name, final_id, probe_error) &&
                final_id.kind != EntryKind::Missing) {
                return finish_after_commit(job_id, request, dest_dir, staging,
                                           tick, job.bytes_total, error);
            }
            error = "mover: neither source nor staged destination exists for "
                    "job '" + job_id +
                    "'; the source was removed externally (L2-SEC-011). Not "
                    "retrying automatically.";
            std::string ignored;
            store_.record_transition(job_id, JobState::Failed, tick, error,
                                     CommitPhase::AfterCommitPoint, ignored);
            return MoveOutcome::FailedExternal;
        }
    }

    error = "mover: unhandled move state";
    return MoveOutcome::Rejected;
}

}  // namespace filemover
