"""Direct requirement tests added during the v0.4.0 traceability audit.

These cover implemented data-safety and configuration behaviours that previously lacked
``@pytest.mark.requirement`` markers, so the trace matrix understated coverage. Each test
targets one behaviour of ``SourceValidator`` (inventory/identity), ``FileClaimManager``
(same-filesystem claim), ``BufferedFileCopyEngine`` (durable temp + directory fsync), or
``ConfigurationLoader`` (contextual validation errors).
"""

from __future__ import annotations

import dataclasses
import os
import socket
from pathlib import Path

import pytest

from file_mover.claiming import FileClaimManager
from file_mover.configuration import ConfigurationLoader, ConfigurationValidationError
from file_mover.exceptions import ClaimError, InvalidSourceError
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.validation import SourceValidator, identity_of

_POSIX_ONLY = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="POSIX filesystem semantics required here"
)


def _validator() -> SourceValidator:
    return SourceValidator(claim_directory_name=".swit-moving", reject_symbolic_links=True)


def _recordings(tmp_path: Path, files: dict[str, bytes]) -> Path:
    root = tmp_path / "recordings"
    root.mkdir()
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


# --- filesystem identity (L2-FS-001/002/003) ---


@pytest.mark.requirement("L2-FS-001")
def test_inventory_records_device_and_inode(tmp_path: Path) -> None:
    root = _recordings(tmp_path, {"a.dat": b"data"})
    entries = _validator().inventory(root, [root])
    assert len(entries) == 1
    stat = (root / "a.dat").stat()
    assert entries[0].identity.device_id == stat.st_dev
    assert entries[0].identity.inode == stat.st_ino


@pytest.mark.requirement("L2-FS-002")
def test_claim_preserves_and_reverifies_identity(tmp_path: Path) -> None:
    root = _recordings(tmp_path, {"a.dat": b"data"})
    entries = _validator().inventory(root, [root])
    pre_identity = entries[0].identity
    staging, _claimed = FileClaimManager(claim_directory_name=".swit-moving").claim(
        entries, root, "job"
    )
    # os.replace preserves the inode; the claim re-verifies identity after the move
    # (a mismatch would raise ClaimError), so the claimed file is provably the same object.
    assert identity_of(staging / "a.dat") == pre_identity


@pytest.mark.requirement("L2-FS-003")
def test_claim_rejects_cross_filesystem_source(tmp_path: Path) -> None:
    root = _recordings(tmp_path, {"a.dat": b"data"})
    entries = _validator().inventory(root, [root])
    # Force a device mismatch: the source appears to live on a different filesystem than
    # the staging directory, so the claim must refuse it rather than do a non-atomic move.
    other_device = dataclasses.replace(
        entries[0], identity=dataclasses.replace(entries[0].identity, device_id=-1)
    )
    manager = FileClaimManager(claim_directory_name=".swit-moving")
    with pytest.raises(ClaimError, match="different filesystem"):
        manager.claim([other_device], root, "job")


# --- inventory rules (L2-POSIX-001/003/004/005) ---


@pytest.mark.requirement("L2-POSIX-001")
def test_inventory_rejects_missing_source_root_without_creating_it(tmp_path: Path) -> None:
    missing = tmp_path / "recordings"  # never created
    with pytest.raises(InvalidSourceError):
        _validator().inventory(missing, [missing])
    assert not missing.exists()  # not auto-created


@pytest.mark.requirement("L2-POSIX-003")
def test_inventory_rejects_uninspectable_requested_path(tmp_path: Path) -> None:
    root = _recordings(tmp_path, {"a.dat": b"data"})
    absent = root / "does-not-exist.dat"
    with pytest.raises(InvalidSourceError):
        _validator().inventory(root, [root], file_list=[str(absent)])


@pytest.mark.requirement("L2-POSIX-004")
def test_inventory_is_deterministic_sorted_order(tmp_path: Path) -> None:
    root = _recordings(tmp_path, {"z.dat": b"z", "a.dat": b"a", "m/b.dat": b"b", "m/a.dat": b"a"})
    order = [entry.relative_path for entry in _validator().inventory(root, [root])]
    assert order == sorted(order)


@pytest.mark.requirement("L2-POSIX-005")
def test_inventory_excludes_the_claim_directory(tmp_path: Path) -> None:
    root = _recordings(tmp_path, {"a.dat": b"data"})
    stale = root / ".swit-moving" / "old-job"
    stale.mkdir(parents=True)
    (stale / "b.dat").write_bytes(b"claimed earlier")
    order = [entry.relative_path for entry in _validator().inventory(root, [root])]
    assert order == ["a.dat"]  # nothing under .swit-moving is discovered


# --- durable destination writes (L2-POSIX-009/010/012, L2-DPR-002, L2-COPY-008) ---


def _recording_fsync(monkeypatch: pytest.MonkeyPatch, calls: list[int]) -> None:
    real_fsync = os.fsync

    def _fsync(fd: int) -> None:
        calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _fsync)


@pytest.mark.requirement("L2-POSIX-010")
@pytest.mark.requirement("L2-COPY-008")
@pytest.mark.requirement("L2-DPR-002")
def test_copy_fsyncs_the_temporary_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    _recording_fsync(monkeypatch, calls)
    source = tmp_path / "src.dat"
    source.write_bytes(b"payload")
    engine = BufferedFileCopyEngine(buffer_size_bytes=3, temporary_file_prefix=".swit-partial-")
    engine.copy_to_temp(source, tmp_path / "dest", "job", "file")
    assert calls, "the temporary destination must be fsynced before verification"


@_POSIX_ONLY
@pytest.mark.requirement("L2-POSIX-012")
def test_publish_fsyncs_the_destination_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "src.dat"
    source.write_bytes(b"payload")
    engine = BufferedFileCopyEngine(buffer_size_bytes=8, temporary_file_prefix=".swit-partial-")
    outcome = engine.copy_to_temp(source, tmp_path / "dest", "job", "file")
    calls: list[int] = []
    _recording_fsync(monkeypatch, calls)
    engine.publish(outcome.temporary_path, tmp_path / "final.dat")
    assert calls, "publication must fsync the destination directory after the atomic rename"


@_POSIX_ONLY
@pytest.mark.requirement("L2-POSIX-009")
def test_temp_creation_requests_o_nofollow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen_flags: list[int] = []
    real_open = os.open

    def _recording_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        seen_flags.append(flags)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", _recording_open)
    source = tmp_path / "src.dat"
    source.write_bytes(b"payload")
    engine = BufferedFileCopyEngine(buffer_size_bytes=8, temporary_file_prefix=".swit-partial-")
    engine.copy_to_temp(source, tmp_path / "dest", "job", "file")
    # The exclusive create must set O_NOFOLLOW so a pre-planted symlink cannot be followed.
    assert any(flags & os.O_NOFOLLOW for flags in seen_flags)


# --- configuration error model (L2-CFG-010) ---


@pytest.mark.requirement("L2-CFG-010")
def test_unknown_option_error_lists_the_valid_options(tmp_path: Path) -> None:
    ini = tmp_path / "file-mover.ini"
    ini.write_text(
        "[transfer]\n"
        "max_concurrent_jobs = 1\n"
        "max_concurrent_files = 2\n"
        "copy_buffer_size_bytes = 8388608\n"
        "retry_limit = 10\n"
        "retry_initial_delay_seconds = 10\n"
        "retry_max_delay_seconds = 900\n"
        "bogus_option = 1\n",  # unknown -> error should describe the valid options
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationValidationError) as caught:
        ConfigurationLoader().load(ini)
    messages = " ".join(issue.message for issue in caught.value.issues)
    assert "valid options" in messages and "max_concurrent_files" in messages
