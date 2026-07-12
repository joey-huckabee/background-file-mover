"""Tests for the transfer engine: copy, integrity, publish, delete, and retry."""

from __future__ import annotations

import errno
import hashlib
import logging
from pathlib import Path

import pytest

from file_mover.claiming import FileClaimManager
from file_mover.configuration import IntegrityConfig, StabilityConfig
from file_mover.exceptions import CopyError, DestinationWriteError
from file_mover.jobs.models import (
    ControlSignal,
    ErrorDisposition,
    ExistingDestinationPolicy,
    HashAlgorithm,
    IntegrityMode,
    JobState,
)
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.logging_config import GATE
from file_mover.manifests import ManifestWriter
from file_mover.submission import JobSubmissionService, SubmissionRequest
from file_mover.transfer.control_signals import JobControlSignals
from file_mover.transfer.coordinator import TransferCoordinator
from file_mover.transfer.copy_engine import BufferedFileCopyEngine, CopyOutcome
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.transfer.retry import ErrorClassifier, compute_backoff
from file_mover.validation import SourceValidator

_BUFFER = 64 * 1024


def _coordinator(
    tmp_path: Path,
    repo: SQLiteJobRepository,
    *,
    integrity_enabled: bool = True,
    integrity_mode: IntegrityMode = IntegrityMode.SOURCE_AND_DESTINATION_HASH,
    policy: ExistingDestinationPolicy = ExistingDestinationPolicy.FAIL,
    copy_engine: object | None = None,
) -> TransferCoordinator:
    return TransferCoordinator(
        repository=repo,
        copy_engine=copy_engine  # type: ignore[arg-type]
        or BufferedFileCopyEngine(
            buffer_size_bytes=_BUFFER, temporary_file_prefix=".swit-partial-"
        ),
        integrity_verifier=IntegrityVerifier(
            algorithm=HashAlgorithm.SHA256, buffer_size_bytes=_BUFFER
        ),
        error_classifier=ErrorClassifier(),
        claim_directory_name=".swit-moving",
        integrity_enabled=integrity_enabled,
        integrity_mode=integrity_mode,
        destination_policy=policy,
        retry_initial_delay_seconds=10.0,
        retry_max_delay_seconds=900.0,
        clock=lambda: 1000.0,
    )


def _submit(
    tmp_path: Path, repo: SQLiteJobRepository, files: dict[str, bytes]
) -> tuple[str, Path, Path]:
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir(exist_ok=True)
    dest_root.mkdir(exist_ok=True)
    for name, content in files.items():
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    submission = JobSubmissionService(
        validator=SourceValidator(
            claim_directory_name=".swit-moving", reject_symbolic_links=True, sleeper=lambda _s: None
        ),
        claim_manager=FileClaimManager(claim_directory_name=".swit-moving"),
        manifest_writer=ManifestWriter(tmp_path / "manifests"),
        repository=repo,
        allowed_source_roots=[source_root],
        allowed_destination_roots=[dest_root],
        stability=StabilityConfig(enabled=False, poll_count=2, poll_interval_seconds=0.0),
        integrity=IntegrityConfig(
            enabled=True,
            mode=IntegrityMode.SOURCE_AND_DESTINATION_HASH,
            algorithm=HashAlgorithm.SHA256,
        ),
        job_id_factory=lambda: "job-1",
    )
    result = submission.submit(SubmissionRequest("req-1", "scn", source_root, dest_root))
    assert result.accepted and result.job_id is not None
    return result.job_id, source_root, dest_root


@pytest.mark.requirement("L2-DPR-006")
@pytest.mark.requirement("L2-DEL-001")
@pytest.mark.requirement("L2-POSIX-011")
@pytest.mark.requirement("L2-DST-004")
@pytest.mark.requirement("L2-STO-002")
def test_full_transfer_publishes_and_deletes_source(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(
        tmp_path, repo, {"host01.dat": b"aaa", "sub/host02.dat": b"bbbb"}
    )
    coordinator = _coordinator(tmp_path, repo)

    assert coordinator.process_job(job_id) is JobState.COMPLETED
    # Destinations published with correct content.
    assert (dest_root / "host01.dat").read_bytes() == b"aaa"
    assert (dest_root / "sub" / "host02.dat").read_bytes() == b"bbbb"
    # Claimed sources deleted; no temp files remain.
    staging = source_root / ".swit-moving" / job_id
    assert not (staging / "host01.dat").exists()
    assert not any(p.name.startswith(".swit-partial-") for p in dest_root.rglob("*"))
    job = repo.get_job(job_id)
    assert job is not None and job.state is JobState.COMPLETED
    assert job.bytes_copied == 7
    repo.close()


@pytest.mark.requirement("L2-DPR-003")
@pytest.mark.parametrize(
    ("enabled", "mode"),
    [
        (False, IntegrityMode.METADATA),
        (True, IntegrityMode.METADATA),
        (True, IntegrityMode.SOURCE_HASH),
    ],
)
def test_transfer_across_integrity_modes(
    tmp_path: Path, enabled: bool, mode: IntegrityMode
) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    coordinator = _coordinator(tmp_path, repo, integrity_enabled=enabled, integrity_mode=mode)
    assert coordinator.process_job(job_id) is JobState.COMPLETED
    assert (dest_root / "a.dat").read_bytes() == b"hello"
    repo.close()


@pytest.mark.requirement("L3-INT-007")
@pytest.mark.requirement("L2-DEL-004")
def test_hash_mismatch_retains_source_and_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    coordinator = _coordinator(tmp_path, repo)
    # Force differing source/destination digests (path-dependent "hash").
    monkeypatch.setattr(IntegrityVerifier, "hash_file", lambda _self, path: str(path))

    assert coordinator.process_job(job_id) is JobState.MANUAL_INTERVENTION
    # Source retained in staging; destination not published; temp retained.
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()
    assert not (dest_root / "a.dat").exists()
    assert any(p.name.startswith(".swit-partial-") for p in dest_root.iterdir())
    repo.close()


@pytest.mark.requirement("L2-DST-003")
@pytest.mark.requirement("L2-DST-001")
def test_existing_destination_collision_is_manual(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    (dest_root / "a.dat").write_bytes(b"DIFFERENT")  # pre-existing, differing destination
    coordinator = _coordinator(tmp_path, repo, policy=ExistingDestinationPolicy.FAIL)

    assert coordinator.process_job(job_id) is JobState.MANUAL_INTERVENTION
    assert (dest_root / "a.dat").read_bytes() == b"DIFFERENT"  # never overwritten
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()  # source retained
    repo.close()


@pytest.mark.requirement("L2-DST-002")
def test_existing_identical_destination_is_reused(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    (dest_root / "a.dat").write_bytes(b"hello")  # already present and identical
    coordinator = _coordinator(tmp_path, repo, policy=ExistingDestinationPolicy.VERIFY_AND_REUSE)

    assert coordinator.process_job(job_id) is JobState.COMPLETED
    assert (dest_root / "a.dat").read_bytes() == b"hello"
    # Claimed source dropped (idempotent completion).
    assert not (source_root / ".swit-moving" / job_id / "a.dat").exists()
    repo.close()


class _FailingCopyEngine:
    """A copy engine whose copy_to_temp always raises the given error."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def copy_to_temp(self, *_args: object, **_kwargs: object) -> CopyOutcome:
        raise self._error

    def publish(self, *_args: object, **_kwargs: object) -> None:  # pragma: no cover - unused
        raise AssertionError("publish should not be called")


@pytest.mark.requirement("L2-RTY-005")
@pytest.mark.requirement("L2-RTY-003")
@pytest.mark.requirement("L2-COPY-009")
@pytest.mark.requirement("L2-ARC-003")
def test_retryable_failure_schedules_retry(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    failure = CopyError("nfs stalled")
    failure.__cause__ = OSError(errno.EIO, "I/O error")
    coordinator = _coordinator(tmp_path, repo, copy_engine=_FailingCopyEngine(failure))

    assert coordinator.process_job(job_id) is JobState.RETRY_WAIT
    job = repo.get_job(job_id)
    assert job is not None
    assert job.next_retry_time == 1000.0 + 10.0  # clock + first backoff
    assert job.attempt_count == 1
    # Source retained.
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()
    repo.close()


@pytest.mark.requirement("L2-RTY-002")
def test_permanent_failure_retains_and_fails(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    failure = CopyError("permission")
    failure.__cause__ = OSError(errno.EACCES, "permission denied")
    coordinator = _coordinator(tmp_path, repo, copy_engine=_FailingCopyEngine(failure))

    assert coordinator.process_job(job_id) is JobState.FAILED_RETAINED
    repo.close()


class _ShortCopyEngine(BufferedFileCopyEngine):
    """A copy engine that under-reports the byte count to force a size mismatch."""

    def copy_to_temp(
        self,
        source: Path,
        destination_dir: Path,
        job_id: str,
        file_id: str,
        **kwargs: object,
    ) -> CopyOutcome:
        outcome = super().copy_to_temp(source, destination_dir, job_id, file_id, **kwargs)
        return CopyOutcome(outcome.temporary_path, outcome.bytes_written - 1)


@pytest.mark.requirement("L2-DPR-003")
def test_size_mismatch_is_manual_and_retains(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    engine = _ShortCopyEngine(buffer_size_bytes=_BUFFER, temporary_file_prefix=".swit-partial-")
    coordinator = _coordinator(tmp_path, repo, integrity_enabled=False, copy_engine=engine)
    assert coordinator.process_job(job_id) is JobState.MANUAL_INTERVENTION
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()  # retained
    assert not (dest_root / "a.dat").exists()
    repo.close()


@pytest.mark.requirement("L2-DEL-003")
@pytest.mark.requirement("L2-POSIX-007")
@pytest.mark.requirement("L2-CLN-005")
def test_missing_claimed_source_fails_and_retains(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    (source_root / ".swit-moving" / job_id / "a.dat").unlink()  # claimed source vanished
    coordinator = _coordinator(tmp_path, repo)
    assert coordinator.process_job(job_id) is JobState.FAILED_RETAINED
    repo.close()


@pytest.mark.requirement("L2-DEL-002")
def test_unexpected_staging_file_is_not_deleted(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    # A stray file that is NOT a durable claimed record appears in the staging directory.
    surprise = source_root / ".swit-moving" / job_id / "surprise.dat"
    surprise.write_bytes(b"not claimed")
    coordinator = _coordinator(tmp_path, repo)

    assert coordinator.process_job(job_id) is JobState.COMPLETED
    # Deletion is driven by claimed file records; the mover never rescans the staging
    # directory and deletes whatever it finds, so the stray file survives.
    assert not (source_root / ".swit-moving" / job_id / "a.dat").exists()
    assert surprise.exists()
    repo.close()


@pytest.mark.requirement("L2-DST-002")
def test_identical_destination_reused_by_size_only(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    (dest_root / "a.dat").write_bytes(b"world")  # same size; integrity disabled -> reused
    coordinator = _coordinator(
        tmp_path,
        repo,
        integrity_enabled=False,
        integrity_mode=IntegrityMode.METADATA,
        policy=ExistingDestinationPolicy.VERIFY_AND_REUSE,
    )
    assert coordinator.process_job(job_id) is JobState.COMPLETED
    repo.close()


@pytest.mark.requirement("L2-RTY-005")
def test_compute_backoff_zero_attempt_uses_initial() -> None:
    assert compute_backoff(0, initial_seconds=5.0, maximum_seconds=100.0) == 5.0


@pytest.mark.requirement("L2-RTY-001")
def test_error_classifier() -> None:
    classifier = ErrorClassifier()
    assert classifier.classify(_os_error(errno.EIO)) is ErrorDisposition.RETRY
    assert classifier.classify(_os_error(errno.ENOSPC)) is ErrorDisposition.RETAIN_AND_FAIL
    assert classifier.classify(_os_error(errno.EXDEV)) is ErrorDisposition.REJECT_JOB
    assert classifier.classify(RuntimeError("?")) is ErrorDisposition.RETAIN_AND_FAIL


@pytest.mark.requirement("L2-RTY-005")
def test_compute_backoff_is_bounded() -> None:
    assert compute_backoff(1, initial_seconds=10.0, maximum_seconds=900.0) == 10.0
    assert compute_backoff(3, initial_seconds=10.0, maximum_seconds=900.0) == 40.0
    assert compute_backoff(20, initial_seconds=10.0, maximum_seconds=900.0) == 900.0


@pytest.mark.requirement("L3-INT-001")
@pytest.mark.requirement("L3-INT-006")
@pytest.mark.requirement("L3-PY-002")
def test_integrity_verifier_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "f.dat"
    path.write_bytes(b"some bytes")
    verifier = IntegrityVerifier(algorithm=HashAlgorithm.SHA256, buffer_size_bytes=4)
    assert verifier.hash_file(path) == hashlib.sha256(b"some bytes").hexdigest()
    assert IntegrityVerifier.compare("a", "a") is True
    assert IntegrityVerifier.compare("a", "b") is False


@pytest.mark.requirement("L2-COPY-006")
@pytest.mark.requirement("L2-DPR-005")
@pytest.mark.requirement("L3-PY-003")
@pytest.mark.requirement("L2-DPR-001")
@pytest.mark.requirement("L2-POSIX-008")
@pytest.mark.requirement("L2-COPY-005")
@pytest.mark.requirement("L2-COPY-007")
def test_copy_engine_creates_temp_exclusively(tmp_path: Path) -> None:
    source = tmp_path / "src.dat"
    source.write_bytes(b"payload")
    dest_dir = tmp_path / "dest"
    engine = BufferedFileCopyEngine(buffer_size_bytes=3, temporary_file_prefix=".swit-partial-")
    outcome = engine.copy_to_temp(source, dest_dir, "job", "file")
    assert outcome.bytes_written == 7
    assert outcome.temporary_path.read_bytes() == b"payload"
    # A second copy to the same temp path fails (exclusive create).
    with pytest.raises(DestinationWriteError):
        engine.copy_to_temp(source, dest_dir, "job", "file")
    # Publishing moves the temp to the final name.
    final = tmp_path / "final.dat"
    engine.publish(outcome.temporary_path, final)
    assert final.read_bytes() == b"payload"
    assert not outcome.temporary_path.exists()


def _os_error(code: int) -> OSError:
    return OSError(code, "err")


def _lifecycle_coordinator(
    repo: SQLiteJobRepository, signals: JobControlSignals, *, resume: bool
) -> TransferCoordinator:
    # A 4-byte buffer so a 10-byte file spans several chunks and can be stopped mid-copy.
    engine = BufferedFileCopyEngine(
        buffer_size_bytes=4, temporary_file_prefix=".swit-partial-", use_kernel_copy=False
    )
    return TransferCoordinator(
        repository=repo,
        copy_engine=engine,
        integrity_verifier=IntegrityVerifier(algorithm=HashAlgorithm.SHA256, buffer_size_bytes=4),
        error_classifier=ErrorClassifier(),
        claim_directory_name=".swit-moving",
        integrity_enabled=False,
        integrity_mode=IntegrityMode.METADATA,
        destination_policy=ExistingDestinationPolicy.FAIL,
        retry_initial_delay_seconds=10.0,
        retry_max_delay_seconds=900.0,
        clock=lambda: 1000.0,
        signals=signals,
        resume_partial_files=resume,
    )


@pytest.mark.requirement("L2-LIF-002")
def test_process_job_pauses_on_signal_and_keeps_partial(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"0123456789"})
    signals = JobControlSignals()
    signals.request(job_id, ControlSignal.PAUSE)  # request before the tick runs the copy
    assert _lifecycle_coordinator(repo, signals, resume=True).process_job(job_id) is JobState.PAUSED
    assert repo.get_job(job_id).state is JobState.PAUSED
    partials = list(dest_root.rglob(".swit-partial-*"))
    assert partials and partials[0].stat().st_size == 4  # one 4-byte buffer, fsynced
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()  # source retained
    repo.close()


@pytest.mark.requirement("L2-LIF-001")
@pytest.mark.requirement("L2-LIF-003")
def test_process_job_cancels_on_signal_and_discards_partial(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"0123456789"})
    signals = JobControlSignals()
    signals.request(job_id, ControlSignal.CANCEL)
    result = _lifecycle_coordinator(repo, signals, resume=True).process_job(job_id)
    assert result is JobState.CANCELLED_RETAINED
    assert repo.get_job(job_id).state is JobState.CANCELLED_RETAINED
    assert not list(dest_root.rglob(".swit-partial-*"))  # partial discarded
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()  # source retained
    repo.close()


@pytest.mark.requirement("L2-RSM-001")
def test_pause_then_resume_completes_via_coordinator(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"0123456789"})
    signals = JobControlSignals()
    signals.request(job_id, ControlSignal.PAUSE)
    coordinator = _lifecycle_coordinator(repo, signals, resume=True)
    assert coordinator.process_job(job_id) is JobState.PAUSED
    # Operator resumes: requeue and drop the pause signal, then the next tick continues it.
    signals.clear(job_id)
    repo.transition_job(job_id, JobState.QUEUED)
    assert coordinator.process_job(job_id) is JobState.COMPLETED
    assert (dest_root / "a.dat").read_bytes() == b"0123456789"  # exact resume, no corruption
    assert not list(dest_root.rglob(".swit-partial-*"))
    repo.close()


@pytest.mark.requirement("L2-RSM-003")
def test_corrupt_resumed_partial_is_discarded_and_routed_to_manual(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})  # 5 bytes
    file_id = repo.list_files(job_id)[0].file_id
    # Plant an oversized (crash-torn) partial so the resumed copy fails the size check.
    (dest_root / f".swit-partial-{job_id}-{file_id}").write_bytes(b"garbage-larger-than-source")
    coordinator = _lifecycle_coordinator(repo, JobControlSignals(), resume=True)
    assert coordinator.process_job(job_id) is JobState.MANUAL_INTERVENTION
    assert not list(dest_root.rglob(".swit-partial-*"))  # corrupt partial discarded
    assert not (dest_root / "a.dat").exists()  # unverified bytes never published
    assert (source_root / ".swit-moving" / job_id / "a.dat").exists()  # source retained
    repo.close()


@pytest.mark.requirement("L3-PY-014")
def test_completion_log_carries_structured_job_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    with caplog.at_level(logging.INFO, logger="file_mover.transfer.coordinator"):
        _coordinator(tmp_path, repo).process_job(job_id)
    completed = [r for r in caplog.records if "job completed" in r.getMessage()]
    assert completed and getattr(completed[-1], "job_id", None) == job_id  # structured field
    repo.close()


@pytest.mark.requirement("L3-PY-014")
@pytest.mark.skipif(not __debug__, reason="DEBUG logging is stripped under python -O")
def test_debug_events_carry_job_and_file_ids(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GATE, "enabled", True)
    monkeypatch.setattr(GATE, "debug", True)  # open the gate so guarded DEBUG lines run
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    with caplog.at_level(logging.DEBUG, logger="file_mover.transfer.file"):
        _coordinator(tmp_path, repo).process_job(job_id)
    with_both = [
        r
        for r in caplog.records
        if getattr(r, "job_id", None) == job_id and getattr(r, "file_id", None)
    ]
    assert with_both, "no DEBUG record carried both job_id and file_id"
    repo.close()


@pytest.mark.requirement("L3-PY-014")
def test_gate_off_suppresses_debug_records(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GATE, "debug", False)  # gate closed -> guarded DEBUG lines skipped
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, _dest_root = _submit(tmp_path, repo, {"a.dat": b"hello"})
    with caplog.at_level(logging.DEBUG, logger="file_mover.transfer.file"):
        _coordinator(tmp_path, repo).process_job(job_id)
    assert not [r for r in caplog.records if r.levelno == logging.DEBUG]
    repo.close()


@pytest.mark.requirement("L2-RSM-002")
@pytest.mark.requirement("L2-LIF-004")
def test_pause_with_resume_disabled_drops_partial_and_restarts_from_zero(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_id, _source_root, dest_root = _submit(tmp_path, repo, {"a.dat": b"0123456789"})
    signals = JobControlSignals()
    signals.request(job_id, ControlSignal.PAUSE)
    coordinator = _lifecycle_coordinator(repo, signals, resume=False)  # resume DISABLED
    assert coordinator.process_job(job_id) is JobState.PAUSED
    # With resume disabled the paused partial is dropped (it could not be resumed cleanly).
    assert not list(dest_root.rglob(".swit-partial-*"))
    # Resuming restarts the file from zero and completes rather than failing.
    signals.clear(job_id)
    repo.transition_job(job_id, JobState.QUEUED)
    assert coordinator.process_job(job_id) is JobState.COMPLETED
    assert (dest_root / "a.dat").read_bytes() == b"0123456789"
    repo.close()
