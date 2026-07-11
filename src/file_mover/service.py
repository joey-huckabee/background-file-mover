"""The long-running ``BackgroundMoverService`` and its startup/shutdown lifecycle.

Introduced across Milestones 3 and 7. The service acquires a singleton process lock,
opens and migrates the SQLite state, reconciles interrupted jobs, binds the control
socket, and then runs two responsibilities on separate thread pools: a control server
(status/health/submit) and a transfer scheduler that treats SQLite as the durable
queue. SIGTERM/SIGINT only set a shutdown event; the drain sequence lets in-flight
work reach a safe, recoverable checkpoint before exit.

See ``docs/ARCHITECTURE.md`` (service lifecycle) and ``docs/ROADMAP.md`` (M3, M7).
"""

from __future__ import annotations
