"""``CommandDispatcher`` — maps control commands to their handlers.

Planned for Milestone 3. Uses an explicit ``{command_name: handler}`` mapping (never
dynamic dispatch on user-supplied names); unknown commands are rejected with a typed
error. Handlers are thin adapters over the query, submission, and recovery services.

See ``docs/ROADMAP.md`` (M3).
"""

from __future__ import annotations
