"""``RecoveryManager`` — reconciles interrupted jobs at service startup.

Planned for Milestone 7. Inspects every job in a non-terminal state (CLAIMING,
HASHING, COPYING, VERIFYING, PUBLISHING, SOURCE_CLEANUP, RETRY_WAIT) and decides its
disposition from observable filesystem state plus durable records — never from
assumptions about what the previous process probably finished. It resumes, retries, or
routes to manual intervention, and no new queued work is processed until reconciliation
completes.

See ``docs/ARCHITECTURE.md`` (recovery) and ``docs/ROADMAP.md`` (M7).
"""

from __future__ import annotations
