"""Module entry point: ``python -m file_mover``.

Delegates to :func:`file_mover.cli.main`, propagating its integer
:class:`~file_mover.jobs.models.ExitCode` as the process exit status. The
systemd unit invokes ``python3.10 -m file_mover --config ... service run``
through this path (see ``packaging/systemd/file-mover.service``).
"""

from __future__ import annotations

from file_mover.cli import main

raise SystemExit(main())
