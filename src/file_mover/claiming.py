"""``FileClaimManager`` — atomically claim source files into a staging directory.

Claiming moves each submitted file, with an atomic same-filesystem ``os.replace``, into a
per-job staging directory beneath the source root (``<source>/.swit-moving/<job>/``), so
the next simulation run cannot overwrite the submitted paths (L1-SYS-004). Identity is
revalidated immediately before the move and confirmed immediately after (L2-FS-002); a
claim onto a different filesystem is refused (L2-FS-003).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from file_mover.exceptions import ClaimError, SourceChangedError
from file_mover.validation import FileIdentity, identity_of

if TYPE_CHECKING:
    from collections.abc import Sequence

    from file_mover.validation import InventoryEntry


@dataclass(frozen=True)
class ClaimedFile:
    """A file that has been moved into the staging directory."""

    relative_path: str
    claimed_path: Path
    identity: FileIdentity


class FileClaimManager:
    """Moves inventoried source files into a per-job staging directory."""

    def __init__(self, *, claim_directory_name: str) -> None:
        """Initialise the claim manager.

        Args:
            claim_directory_name: Name of the staging directory beneath the source root.
        """
        self._claim_directory_name = claim_directory_name

    def claim(
        self, entries: Sequence[InventoryEntry], source_root: Path, job_id: str
    ) -> tuple[Path, list[ClaimedFile]]:
        """Claim all ``entries`` into ``<source_root>/<claim_dir>/<job_id>/``.

        Returns:
            The staging directory and the list of claimed files.

        Raises:
            ClaimError: If the staging directory or a move fails, or a file is on a
                different filesystem than the staging directory.
            SourceChangedError: If a file's identity changed since inventory.
        """
        staging = Path(source_root) / self._claim_directory_name / job_id
        try:
            staging.mkdir(parents=True, exist_ok=False)
            staging_device = staging.stat().st_dev
        except OSError as error:
            raise ClaimError(f"cannot create staging directory {staging}: {error}") from error

        claimed: list[ClaimedFile] = []
        for entry in entries:
            if entry.identity.device_id != staging_device:
                raise ClaimError(
                    f"source {entry.relative_path} is on a different filesystem "
                    "than the staging directory"
                )
            if identity_of(entry.absolute_path) != entry.identity:
                raise SourceChangedError(f"source changed before claim: {entry.relative_path}")
            destination = staging / entry.relative_path
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                entry.absolute_path.replace(destination)
            except OSError as error:
                raise ClaimError(f"cannot claim {entry.relative_path}: {error}") from error
            if identity_of(destination) != entry.identity:
                raise ClaimError(f"claimed file identity mismatch: {entry.relative_path}")
            claimed.append(ClaimedFile(entry.relative_path, destination, entry.identity))
        return staging, claimed
