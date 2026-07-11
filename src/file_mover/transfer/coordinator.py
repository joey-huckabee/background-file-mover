"""``TransferCoordinator`` — drives files through the durable transfer workflow.

Planned for Milestone 6. Owns authoritative state transitions: it updates the SQLite
repository transactionally at each stage and *then* emits observational
``TransferEvent`` objects to subscribers (structured logs, runtime statistics). A
bounded ``ThreadPoolExecutor`` (``max_concurrent_files``) performs the copies; the
coordinator decides overall job completion. Event-subscriber failures never affect
durable state or the transfer itself.

See ``docs/ROADMAP.md`` (M6).
"""

from __future__ import annotations
