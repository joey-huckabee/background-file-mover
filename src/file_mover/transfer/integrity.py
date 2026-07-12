"""``IntegrityVerifier`` — configurable file hashing and constant-time comparison.

Hashes are computed with :mod:`hashlib` (SHA-256/SHA-512/BLAKE2b) reading through a
bounded buffer (L3-INT-001/002); digests are compared with :func:`hmac.compare_digest`
(L3-INT-006). The verifier is stateless and host-independent.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from file_mover.jobs.models import HashAlgorithm


class IntegrityVerifier:
    """Computes and compares file hashes for integrity verification."""

    def __init__(self, *, algorithm: HashAlgorithm, buffer_size_bytes: int) -> None:
        """Initialise the verifier.

        Args:
            algorithm: The hash algorithm to use.
            buffer_size_bytes: Bounded read-buffer size.
        """
        self._algorithm = algorithm
        self._buffer_size_bytes = buffer_size_bytes

    def hash_file(self, path: Path) -> str:
        """Return the hex digest of ``path`` read through a bounded buffer."""
        digest = hashlib.new(self._algorithm.value)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(self._buffer_size_bytes)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def compare(expected: str, actual: str) -> bool:
        """Return whether two hex digests match, in constant time."""
        return hmac.compare_digest(expected, actual)
