"""Length-prefixed JSON message framing shared by the control server and client.

Planned for Milestone 3. Provides ``encode_message``/``send_message``/
``receive_exactly``/``receive_message``: each message is a UTF-8 JSON object preceded
by a 4-byte big-endian length prefix (:data:`file_mover.constants.LENGTH_PREFIX_BYTES`).
Oversized frames are rejected before allocation; ``receive_exactly`` loops on ``recv``
until the full frame arrives or the peer closes.

See ``docs/ROADMAP.md`` (M3).
"""

from __future__ import annotations
