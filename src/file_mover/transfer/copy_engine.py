"""``BufferedFileCopyEngine`` — bounded-memory copy to a temporary destination.

Planned for Milestone 6. Reads and writes in a bounded ``while`` loop using a
configurable buffer (floor 64 KiB, default 8 MiB), writing to a ``.swit-partial-``
temporary file created exclusively (``O_EXCL``, ``O_NOFOLLOW``). It flushes and
``os.fsync``s the file (and the destination directory) before verification and atomic
publication, and emits throttled progress rather than per-chunk events.

See ``docs/ROADMAP.md`` (M6).
"""

from __future__ import annotations
