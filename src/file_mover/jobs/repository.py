"""``JobRepository`` protocol and the durable record dataclasses.

Planned for Milestone 4. Defines the narrow ``Protocol`` the coordinator depends on
(insert job, claim next runnable file, transition state, record errors) plus the
frozen ``JobRecord``/``FileRecord`` dataclasses. A concrete SQLite implementation
lives in :mod:`file_mover.jobs.sqlite_repository`; tests substitute an in-memory fake.

See ``docs/ARCHITECTURE.md`` (durable state) and ``docs/ROADMAP.md`` (M4).
"""

from __future__ import annotations
