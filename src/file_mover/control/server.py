"""``ControlSocketServer`` — accepts local control connections for the service.

Planned for Milestone 3. Binds the Unix socket (handling stale-socket recovery
safely: refuse if a live server answers, remove only a confirmed-dead socket, never
delete an unexpected regular file), then serves one request per connection on a small
control thread pool. Malformed or oversized messages are rejected without crashing the
service.

See ``docs/ROADMAP.md`` (M3).
"""

from __future__ import annotations
