"""``ErrorClassifier`` and retry scheduling with bounded exponential backoff.

Planned for Milestone 6. Classifies operational errors into an
:class:`~file_mover.jobs.models.ErrorDisposition` (retry / retain-and-fail /
reject-job / service-fatal) from the ``errno`` and stage — e.g. ``ESTALE``/``EIO``/
``ETIMEDOUT`` are retryable, ``ENOSPC``/``EACCES`` are retained for operator action,
``EXDEV`` on an expected same-filesystem claim is a configuration failure. Attempt
count and next-retry time are persisted so retries survive a restart.

See ``docs/ROADMAP.md`` (M6).
"""

from __future__ import annotations
