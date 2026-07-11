"""``SQLiteJobRepository`` — authoritative durable job and file state.

Planned for Milestone 4. Opens the state database with ``foreign_keys=ON``,
``journal_mode=WAL``, ``synchronous=FULL`` and a ``busy_timeout``, gives each worker
thread its own connection, and applies schema migrations at startup. SQLite is the
durable work queue: the scheduler claims the next runnable file transactionally.

See ``docs/ROADMAP.md`` (M4).
"""

from __future__ import annotations
