"""Durable job state: models, the state machine, and the SQLite repository.

Milestone 1 ships the enum vocabulary (:mod:`file_mover.jobs.models`); the record
dataclasses, repository protocol, and SQLite-backed implementation land in
Milestone 4 (see ``docs/ROADMAP.md``).
"""

from __future__ import annotations
