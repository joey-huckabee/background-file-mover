"""Project-wide constants: on-disk markers, default paths, and protocol values.

These are the stable vocabulary shared across subsystems. On-disk staging markers
use the ``swit`` prefix so that partially-transferred artifacts are unmistakably
owned by this service on a shared NFS mount, while the operator-facing command,
package, and install paths use the generic ``file-mover`` name (the "hybrid"
naming decision recorded in ``docs/ROADMAP.md``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

# ── Application identity ──────────────────────────────────────────────────────
APP_NAME: Final = "file-mover"
"""Operator-facing application / CLI command name."""

PACKAGE_NAME: Final = "file_mover"
"""Importable Python package name."""

# ── On-disk staging markers (SWIT-prefixed; see the hybrid naming decision) ───
CLAIM_DIRECTORY_NAME: Final = ".swit-moving"
"""Default per-source staging directory into which submitted files are claimed."""

TEMPORARY_FILE_PREFIX: Final = ".swit-partial-"
"""Default prefix for in-progress destination files, published atomically on completion."""

# ── Default install paths (Linux; overridable via configuration) ──────────────
DEFAULT_CONFIG_PATH: Final = Path("/etc/file-mover/file-mover.ini")
DEFAULT_STATE_DIRECTORY: Final = Path("/var/lib/file-mover")
DEFAULT_RUNTIME_DIRECTORY: Final = Path("/run/file-mover")
DEFAULT_LOG_DIRECTORY: Final = Path("/var/log/file-mover")
DEFAULT_SOCKET_PATH: Final = Path("/run/file-mover/control.sock")
DEFAULT_DATABASE_PATH: Final = Path("/var/lib/file-mover/jobs.db")

# ── Transfer defaults ─────────────────────────────────────────────────────────
DEFAULT_COPY_BUFFER_SIZE_BYTES: Final = 8 * 1024 * 1024
"""Default bounded copy-buffer size (8 MiB)."""

MINIMUM_COPY_BUFFER_SIZE_BYTES: Final = 64 * 1024
"""Configuration floor for the copy buffer (64 KiB)."""

# ── Control protocol ──────────────────────────────────────────────────────────
PROTOCOL_VERSION: Final = 1
"""Version of the length-prefixed JSON control protocol spoken over the Unix socket."""

LENGTH_PREFIX_BYTES: Final = 4
"""Width of the big-endian message length prefix framing each control message."""

DEFAULT_MAXIMUM_MESSAGE_BYTES: Final = 1024 * 1024
"""Default maximum accepted control-message size (1 MiB), rejected before allocation."""
