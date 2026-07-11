"""Control-socket client used by the CLI to reach the running service.

Planned for Milestone 3. Connects to the Unix socket, sends a single framed request
with a client-generated ``request_id`` and ``protocol_version``, and returns the
decoded response. When no service is listening the client reports service-unavailable
(``ExitCode.SERVICE_UNAVAILABLE``) and never starts its own transfer process.

See ``docs/ROADMAP.md`` (M3).
"""

from __future__ import annotations
