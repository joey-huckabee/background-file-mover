"""Tests for the copy engine's kernel-assisted and buffered strategies."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from file_mover.exceptions import CopyError
from file_mover.transfer.copy_engine import BufferedFileCopyEngine

# Longer than the tiny buffer below, so the copy loop runs several iterations.
_PAYLOAD = b"background file mover kernel copy payload 0123456789" * 4


def _engine(*, use_kernel_copy: bool) -> BufferedFileCopyEngine:
    # A 4-byte buffer forces many copy_file_range / read-write iterations.
    return BufferedFileCopyEngine(
        buffer_size_bytes=4, temporary_file_prefix=".swit-partial-", use_kernel_copy=use_kernel_copy
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
