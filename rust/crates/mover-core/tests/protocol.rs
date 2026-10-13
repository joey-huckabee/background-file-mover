use mover_core::{
    DeliveryPolicy, FilePhase, FileSpec, Handoff, ProtocolError, Recording, Submission,
};

fn submission() -> Submission {
    Submission::new(
        "recorder-a",
        "run-42",
        "/mnt/current",
        vec![
            FileSpec::new("video/camera.bin", None).unwrap(),
            FileSpec::new("telemetry/events.bin", Some(0)).unwrap(),
        ],
    )
    .unwrap()
}

fn job(delete: bool) -> Recording {
    Recording::new(
        submission(),
        DeliveryPolicy {
            destination_id: "archive-v1".into(),
            group_by_generator: true,
            delete_source_after_commit: delete,
        },
    )
    .unwrap()
}

fn claim_all(job: &mut Recording) {
    job.confirm_acceptance();
    job.confirm_claim(0, 100_000_000_000).unwrap();
    job.confirm_claim(1, 0).unwrap();
}

fn publish_all(job: &mut Recording) {
    claim_all(job);
    for i in 0..2 {
        job.confirm_verification(i).unwrap();
        job.confirm_publication(i).unwrap();
    }
}

#[test]
fn acceptance_and_partial_claims_never_release_paths() {
    let mut j = job(true);
    assert_eq!(j.handoff(), Handoff::Pending);
    assert_eq!(j.confirm_claim(0, 5), Err(ProtocolError::InvalidTransition));
    j.confirm_acceptance();
    assert_eq!(j.handoff(), Handoff::Pending);
    j.confirm_claim(0, 100_000_000_000).unwrap();
    assert_eq!(j.handoff(), Handoff::Pending);
    assert_eq!(j.actual_bytes_total(), None);
    assert_eq!(
        j.confirm_verification(0),
        Err(ProtocolError::InvalidTransition)
    );
    j.confirm_claim(1, 0).unwrap();
    assert_eq!(j.handoff(), Handoff::Ready202);
    assert_eq!(j.actual_bytes_total(), Some(100_000_000_000));
}

#[test]
fn expected_size_mismatch_does_not_confirm_claim() {
    let mut j = job(true);
    j.confirm_acceptance();
    assert_eq!(
        j.confirm_claim(1, 1),
        Err(ProtocolError::ExpectedSizeMismatch)
    );
    assert_eq!(j.file_phase(1), Some(FilePhase::Pending));
    j.confirm_claim(1, 0).unwrap();
    assert_eq!(j.file_phase(1), Some(FilePhase::Claimed));
}

#[test]
fn replay_preserves_handoff_and_pinned_policy() {
    let mut j = job(true);
    assert_eq!(j.replay(&submission()), Ok(Handoff::Pending));
    claim_all(&mut j);
    assert_eq!(j.replay(&submission()), Ok(Handoff::Ready202));
    assert_eq!(j.policy().destination_id, "archive-v1");
    assert!(j.policy().group_by_generator);
    for (generator, id, path, error) in [
        (
            "recorder-a",
            "run-42",
            "/mnt/new",
            ProtocolError::ConflictingReplay,
        ),
        (
            "recorder-a",
            "run-43",
            "/mnt/current",
            ProtocolError::DifferentSubmission,
        ),
        (
            "recorder-b",
            "run-42",
            "/mnt/current",
            ProtocolError::DifferentSubmission,
        ),
    ] {
        let candidate =
            Submission::new(generator, id, path, submission().files().to_vec()).unwrap();
        assert_eq!(j.replay(&candidate), Err(error));
    }
}

#[test]
fn publication_and_commit_require_all_prior_evidence() {
    let mut j = job(true);
    claim_all(&mut j);
    assert_eq!(
        j.confirm_publication(0),
        Err(ProtocolError::InvalidTransition)
    );
    assert_eq!(j.confirm_commit(), Err(ProtocolError::InvalidTransition));
    j.confirm_verification(0).unwrap();
    j.confirm_publication(0).unwrap();
    assert_eq!(j.confirm_commit(), Err(ProtocolError::InvalidTransition));
    assert!(!j.cleanup_authorized(0, true));
    j.confirm_verification(1).unwrap();
    j.confirm_publication(1).unwrap();
    j.confirm_commit().unwrap();
    assert!(j.cleanup_authorized(0, true));
}

#[test]
fn cleanup_requires_job_policy_current_permission_and_set_commit() {
    for delete in [false, true] {
        for current in [false, true] {
            let mut j = job(delete);
            publish_all(&mut j);
            assert!(!j.cleanup_authorized(0, current));
            j.confirm_commit().unwrap();
            assert_eq!(j.cleanup_authorized(0, current), delete && current);
            if delete && current {
                j.confirm_source_removed(0, current).unwrap();
                assert!(!j.cleanup_authorized(0, current));
                j.confirm_source_removed(0, false).unwrap();
                assert_eq!(j.replay(&submission()), Ok(Handoff::Ready202));
            } else {
                assert_eq!(
                    j.confirm_source_removed(0, current),
                    Err(ProtocolError::InvalidTransition)
                );
                assert_eq!(j.file_phase(0), Some(FilePhase::Published));
            }
        }
    }
}

#[test]
fn repeated_claim_cannot_change_recorded_size() {
    let mut j = job(true);
    claim_all(&mut j);
    j.confirm_claim(0, 100_000_000_000).unwrap();
    assert_eq!(j.confirm_claim(0, 7), Err(ProtocolError::InvalidTransition));
    assert_eq!(j.actual_bytes_total(), Some(100_000_000_000));
}

#[test]
fn path_traversal_and_reserved_names_are_rejected() {
    for path in [
        "", "/video", "../video", "a/../b", "a/./b", "a//b", "a/", "a\\b", "a/\0b",
    ] {
        assert_eq!(
            FileSpec::new(path, None),
            Err(ProtocolError::InvalidRelativePath),
            "{path:?}"
        );
    }
    for path in [
        "COMMITTED.json",
        ".staging/file",
        "a/.control/file",
        ".file-mover/file",
    ] {
        assert_eq!(FileSpec::new(path, None), Err(ProtocolError::ReservedPath));
    }
    assert_eq!(
        FileSpec::new("camera-a/video.bin", None)
            .unwrap()
            .relative_path(),
        "camera-a/video.bin"
    );
    assert!(FileSpec::new("camera-b/video.bin", Some(0)).is_ok());
}

#[test]
fn duplicate_and_prefix_conflicts_are_order_independent() {
    for names in [
        vec!["video", "video/file"],
        vec!["video/file", "video"],
        vec!["video", "video"],
        vec!["video", "video-other", "video/file"],
    ] {
        let files = names
            .into_iter()
            .map(|n| FileSpec::new(n, None).unwrap())
            .collect();
        assert_eq!(
            Submission::new("a", "42", "/mnt/current", files),
            Err(ProtocolError::PathConflict)
        );
    }
    let files = ["video", "video2/file"]
        .into_iter()
        .map(|n| FileSpec::new(n, None).unwrap())
        .collect();
    assert!(Submission::new("a", "42", "/mnt/current", files).is_ok());
}

#[test]
fn empty_requests_and_unknown_files_do_not_advance() {
    assert_eq!(
        Submission::new("a", "42", "/mnt/current", vec![]),
        Err(ProtocolError::EmptyRecording)
    );
    assert_eq!(
        Submission::new("", "42", "/mnt/current", submission().files().to_vec()),
        Err(ProtocolError::EmptyIdentity)
    );
    let mut j = job(true);
    j.confirm_acceptance();
    assert_eq!(j.confirm_claim(2, 0), Err(ProtocolError::UnknownFile));
    assert_eq!(j.file_phase(2), None);
    assert!(!j.cleanup_authorized(2, true));
}

#[test]
fn aggregate_overflow_is_not_reported_as_small_recording() {
    let files = ["first", "second"]
        .into_iter()
        .map(|n| FileSpec::new(n, None).unwrap())
        .collect();
    let input = Submission::new("a", "large", "/mnt/current", files).unwrap();
    let mut j = Recording::new(input, job(false).policy().clone()).unwrap();
    j.confirm_acceptance();
    j.confirm_claim(0, u64::MAX).unwrap();
    j.confirm_claim(1, 1).unwrap();
    assert_eq!(j.actual_bytes_total(), None);
}
