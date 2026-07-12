"""Source inventory, identity capture, and stability validation.

The :class:`SourceValidator` enumerates a submitted recording set deterministically,
rejects symbolic links and non-regular files, confirms every path stays beneath an
approved source root, and captures a device+inode+size+mtime fingerprint per file
(L2-FS-001, L2-POSIX-002/004/006). It optionally polls for stability — a defensive check
that a file is not still being written, which does **not** replace the orchestration
system's responsibility to submit only completed recordings.

All paths are real :class:`~pathlib.Path` objects and the approved roots are injected, so
the validator is host-independent and fully exercised in tests without a POSIX deploy.
"""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from file_mover.exceptions import InvalidSourceError, SourceNotStableError


@dataclass(frozen=True)
class FileIdentity:
    """A filesystem fingerprint used to detect change or replacement."""

    device_id: int
    inode: int
    size_bytes: int
    modified_time_ns: int


@dataclass(frozen=True)
class InventoryEntry:
    """One inventoried source file and its captured identity."""

    relative_path: str
    absolute_path: Path
    identity: FileIdentity


def identity_of(path: Path) -> FileIdentity:
    """Capture the :class:`FileIdentity` of ``path`` without following symlinks."""
    info = os.lstat(path)
    return FileIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


class SourceValidator:
    """Validates and inventories a submitted source set."""

    def __init__(
        self,
        *,
        claim_directory_name: str,
        reject_symbolic_links: bool = True,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialise the validator.

        Args:
            claim_directory_name: Staging directory name to exclude from discovery.
            reject_symbolic_links: Reject symbolic links found during inventory.
            sleeper: Sleep function for stability polling; injectable for tests.
        """
        self._claim_directory_name = claim_directory_name
        self._reject_symbolic_links = reject_symbolic_links
        self._sleeper = sleeper

    def validate_under_roots(self, path: Path, roots: Sequence[Path]) -> None:
        """Confirm ``path`` is equal to or nested within one of ``roots``.

        Raises:
            InvalidSourceError: If ``path`` is not beneath any approved root.
        """
        for root in roots:
            if path == root or path.is_relative_to(root):
                return
        raise InvalidSourceError(f"path {path} is not beneath an approved root")

    def inventory(
        self,
        source_root: Path,
        allowed_roots: Sequence[Path],
        *,
        file_list: Sequence[Path] | None = None,
    ) -> list[InventoryEntry]:
        """Enumerate the source files to claim, deterministically and safely.

        Args:
            source_root: The submitted source directory.
            allowed_roots: Approved source roots the inventory must stay within.
            file_list: An explicit set of files; when omitted the tree is walked.

        Returns:
            Inventory entries sorted by relative path.

        Raises:
            InvalidSourceError: If the set is empty, escapes the approved roots, or
                contains a symbolic link, a non-regular file, or an unreadable path.
        """
        self.validate_under_roots(source_root, allowed_roots)
        paths = list(file_list) if file_list is not None else self._walk(source_root)
        entries: list[InventoryEntry] = []
        for path in paths:
            try:
                info = os.lstat(path)
            except OSError as error:
                raise InvalidSourceError(f"cannot read source file {path}: {error}") from error
            if stat.S_ISLNK(info.st_mode):
                if self._reject_symbolic_links:
                    raise InvalidSourceError(f"symbolic links are not permitted: {path}")
                raise InvalidSourceError(f"symbolic-link following is not supported: {path}")
            if not stat.S_ISREG(info.st_mode):
                raise InvalidSourceError(f"not a regular file: {path}")
            self.validate_under_roots(Path(path), allowed_roots)
            relative = os.path.relpath(path, source_root)
            entries.append(
                InventoryEntry(
                    relative_path=Path(relative).as_posix(),
                    absolute_path=Path(path),
                    identity=FileIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns),
                )
            )
        if not entries:
            raise InvalidSourceError(f"no files to claim beneath {source_root}")
        entries.sort(key=lambda entry: entry.relative_path)
        return entries

    def check_stability(
        self, entries: Sequence[InventoryEntry], *, poll_count: int, poll_interval_seconds: float
    ) -> None:
        """Confirm each file's identity is unchanged across ``poll_count`` observations.

        Raises:
            SourceNotStableError: If any file's size, mtime, or inode changes.
        """
        for _ in range(max(0, poll_count - 1)):
            self._sleeper(poll_interval_seconds)
            for entry in entries:
                if identity_of(entry.absolute_path) != entry.identity:
                    raise SourceNotStableError(
                        f"source file changed during stabilisation: {entry.relative_path}"
                    )

    def _walk(self, source_root: Path) -> list[Path]:
        """Recursively collect regular-file paths, excluding the claim directory."""
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(source_root, followlinks=False):
            if self._claim_directory_name in dirnames:
                dirnames.remove(self._claim_directory_name)
            for name in filenames:
                found.append(Path(dirpath) / name)
        return found
