"""Background File Mover — a durable, standard-library-only transfer coordinator.

The package moves completed simulation recording sets from a local NFS mount to a
remote processing filesystem independently of the simulation orchestration, using
transaction-like ``claim -> copy(temp) -> verify -> publish -> delete-source``
semantics so that recordings are never lost.

This is the Milestone 1 (Foundation) baseline: the requirement documents, the
package skeleton, the exception/enum/constant vocabulary, and the CLI surface are
in place. Behavioral subsystems (configuration, control socket, SQLite job state,
claiming, transfer, recovery) are introduced in later milestones — see
``docs/ROADMAP.md``.
"""

from __future__ import annotations

from importlib import metadata

__all__ = ["__version__"]

try:
    # Single source of truth: the version declared in ``pyproject.toml`` and baked into the
    # installed distribution metadata. Bumping the release version therefore touches only
    # ``pyproject.toml``; this value follows on the next install/build.
    __version__ = metadata.version("background-file-mover")
except metadata.PackageNotFoundError:  # pragma: no cover - source tree without installed metadata
    __version__ = "0.0.0+unknown"
