"""Control plane: the Unix-domain-socket protocol, server, client, and dispatcher.

Planned for Milestone 3. The CLI and service communicate over an ``AF_UNIX`` stream
socket using length-prefixed UTF-8 JSON messages; submission is idempotent by
client-supplied ``request_id``. The control server runs on a small dedicated thread
pool so a saturated transfer pool never blocks status/health queries.

See ``docs/ARCHITECTURE.md`` (control protocol) and ``docs/ROADMAP.md`` (M3).
"""

from __future__ import annotations
