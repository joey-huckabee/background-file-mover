"""``IntegrityVerifier`` — configurable source/destination integrity checking.

Planned for Milestone 6. Supports the ``metadata``, ``source-hash``, and
``source-and-destination-hash`` modes using :mod:`hashlib` (SHA-256, SHA-512,
BLAKE2b) with a bounded read buffer, and compares digests with
``hmac.compare_digest``. Even with hashing disabled, identity and size are still
verified before source deletion. A mismatch retains both source and temporary
destination and blocks publication.

See ``docs/ROADMAP.md`` (M6).
"""

from __future__ import annotations
