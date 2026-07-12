"""Tests for the copy engine's kernel-assisted and buffered strategies."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from file_mover.exceptions import CopyError
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.ratelimit import RateLimiter

# Longer than the tiny buffer below, so the copy loop runs several iterations.
_PAYLOAD = b"background file mover kernel copy payload 0123456789" * 4


def _engine(
    *, use_kernel_copy: bool, rate_limiter: RateLimiter | None = None
) -> BufferedFileCopyEngine:
    # A 4-byte buffer forces many copy_file_range / read-write iterations.
    return BufferedFileCopyEngine(
        buffer_size_bytes=4,
        temporary_file_prefix=".swit-partial-",
        use_kernel_copy=use_kernel_copy,
        rate_limiter=rate_limiter,
    )


def _source(tmp_path: Path, content: bytes = _PAYLOAD) -> Path:
    path = tmp_path / "src.dat"
    path.write_bytes(content)
    return path


@pytest.mark.requirement("L2-COPY-011")
@pytest.mark.requirement("L3-PY-009")
@pytest.mark.skipif(
    not hasattr(os, "copy_file_range"), reason="requires os.copy_file_range (POSIX)"
)
def test_kernel_copy_transfers_correct_bytes(tmp_path: Path) -> None:
    # Exercises the real os.copy_file_range path end to end.
    source = _source(tmp_path)
    outcome = _engine(use_kernel_copy=True).copy_to_temp(source, tmp_path / "dest", "job", "file")
    assert outcome.bytes_written == len(_PAYLOAD)
    assert outcome.temporary_path.read_bytes() == _PAYLOAD


@pytest.mark.requirement("L2-COPY-011")
def test_buffered_copy_transfers_correct_bytes(tmp_path: Path) -> None:
    source = _source(tmp_path)
    outcome = _engine(use_kernel_copy=False).copy_to_temp(source, tmp_path / "dest", "job", "file")
    assert outcome.bytes_written == len(_PAYLOAD)
    assert outcome.temporary_path.read_bytes() == _PAYLOAD


@pytest.mark.requirement("L3-PY-009")
def test_kernel_copy_falls_back_on_unsupported_errno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def _unsupported(*_args: object, **_kwargs: object) -> int:
        calls.append(1)
        raise OSError(errno.ENOSYS, "not implemented")

    monkeypatch.setattr("os.copy_file_range", _unsupported, raising=False)
    source = _source(tmp_path)
    outcome = _engine(use_kernel_copy=True).copy_to_temp(source, tmp_path / "dest", "job", "file")
    assert calls  # the kernel copy was attempted
    assert outcome.temporary_path.read_bytes() == _PAYLOAD  # then the buffered fallback ran
    assert outcome.bytes_written == len(_PAYLOAD)


@pytest.mark.requirement("L3-PY-009")
def test_kernel_copy_discards_partial_output_on_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _partial_then_cross_device(_src_fd: int, dst_fd: int, _count: int, *_a: object) -> int:
        os.write(dst_fd, b"GARBAGE")  # write bogus partial bytes, then decline
        raise OSError(errno.EXDEV, "cross-device")

    monkeypatch.setattr("os.copy_file_range", _partial_then_cross_device, raising=False)
    source = _source(tmp_path)
    outcome = _engine(use_kernel_copy=True).copy_to_temp(source, tmp_path / "dest", "job", "file")
    # The partial garbage must be discarded and the file re-copied cleanly.
    assert outcome.temporary_path.read_bytes() == _PAYLOAD
    assert outcome.bytes_written == len(_PAYLOAD)


@pytest.mark.requirement("L3-PY-009")
def test_kernel_copy_propagates_genuine_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _io_error(*_args: object, **_kwargs: object) -> int:
        raise OSError(errno.EIO, "I/O error")

    monkeypatch.setattr("os.copy_file_range", _io_error, raising=False)
    source = _source(tmp_path)
    with pytest.raises(CopyError):
        _engine(use_kernel_copy=True).copy_to_temp(source, tmp_path / "dest", "job", "file")


@pytest.mark.requirement("L2-COPY-011")
def test_disabled_kernel_copy_never_calls_copy_file_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("copy_file_range must not be called when disabled")

    monkeypatch.setattr("os.copy_file_range", _forbidden, raising=False)
    source = _source(tmp_path)
    outcome = _engine(use_kernel_copy=False).copy_to_temp(source, tmp_path / "dest", "job", "file")
    assert outcome.temporary_path.read_bytes() == _PAYLOAD


@pytest.mark.requirement("L2-BWL-001")
@pytest.mark.requirement("L3-PY-011")
def test_active_rate_limit_forces_buffered_path_and_paces_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("copy_file_range must be bypassed when a rate limit is active")

    monkeypatch.setattr("os.copy_file_range", _forbidden, raising=False)
    slept: list[float] = []
    # 4 B/s with a 4-byte buffer: the first 4-byte chunk drains the burst, each later
    # chunk incurs a 1.0s deficit sleep. Frozen clock so nothing refills.
    limiter = RateLimiter(4, clock=lambda: 0.0, sleeper=slept.append)
    source = _source(tmp_path)
    # use_kernel_copy=True, but the active limit must still force the buffered loop.
    outcome = _engine(use_kernel_copy=True, rate_limiter=limiter).copy_to_temp(
        source, tmp_path / "dest", "job", "file"
    )
    assert outcome.temporary_path.read_bytes() == _PAYLOAD  # kernel copy was never called
    assert outcome.bytes_written == len(_PAYLOAD)
    assert slept  # throughput was throttled in the buffered loop


@pytest.mark.requirement("L2-BWL-004")
def test_unlimited_rate_limiter_still_allows_kernel_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    used_kernel: list[int] = []
    real = getattr(os, "copy_file_range", None)

    def _record(*args: object, **kwargs: object) -> int:
        used_kernel.append(1)
        assert real is not None
        return real(*args, **kwargs)  # type: ignore[arg-type]

    if real is not None:
        monkeypatch.setattr("os.copy_file_range", _record, raising=False)
    slept: list[float] = []
    limiter = RateLimiter(0, sleeper=slept.append)  # unlimited: no path forcing, no pacing
    source = _source(tmp_path)
    outcome = _engine(use_kernel_copy=True, rate_limiter=limiter).copy_to_temp(
        source, tmp_path / "dest", "job", "file"
    )
    assert outcome.temporary_path.read_bytes() == _PAYLOAD
    assert slept == []  # an unlimited limiter never sleeps
    if real is not None:
        assert used_kernel  # the kernel path stayed available when unlimited
