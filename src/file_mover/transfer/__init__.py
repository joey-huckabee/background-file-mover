"""Transfer engine: coordinator, buffered copy engine, integrity, and retry.

Planned for Milestone 6. Implements the durable per-file workflow — verify claimed
identity, optionally hash the source and persist the manifest, copy to a
``.swit-partial-`` temporary file, flush + ``fsync``, verify size/hash, atomically
publish, revalidate source identity, and only then delete the claimed source.

See ``docs/ARCHITECTURE.md`` (durable per-file workflow) and ``docs/ROADMAP.md`` (M6).
"""

from __future__ import annotations
