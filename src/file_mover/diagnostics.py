"""Environment capability diagnostics for ``file-mover doctor``.

Verifies that the running interpreter and platform provide the standard-library and OS
features the service depends on — *before* an operator relies on it. Each capability is a
small :class:`EnvironmentCheck` (a strategy): a name, a requirement level, and a detection
callable. :class:`EnvironmentDoctor` runs the set and aggregates a
:class:`DiagnosticsReport`. Rendering and CLI wiring live elsewhere (a Fowler separation of
concerns): this module decides *what is true about the host*, not how it is presented.

Required capabilities missing → ``FAIL`` (a deploy gate); optional ones missing → ``WARN``.
The individual detection helpers are module-level so tests can simulate a capability being
present or absent on any host, and every probe is exception-safe so a diagnostic never
crashes (L2-ENV-001..003, L1-ROB-001).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import signal
import socket
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_MIN_PYTHON = (3, 10)


class CheckStatus(str, Enum):
    """Outcome of one capability check."""

    PASS = "pass"  # nosec B105 - a check-status label, not a credential
    WARN = "warn"
    FAIL = "fail"


class Requirement(str, Enum):
    """Whether a capability is mandatory or a graceful-degradation nicety."""

    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class CheckResult:
    """The result of running one :class:`EnvironmentCheck`."""

    name: str
    requirement: Requirement
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class EnvironmentCheck:
    """One capability probe: a name, its requirement level, and a detection callable."""

    name: str
    requirement: Requirement
    probe: Callable[[], tuple[bool, str]]

    def run(self) -> CheckResult:
        """Run the probe, mapping availability + requirement to a status (never raises)."""
        try:
            available, detail = self.probe()
        except Exception as error:  # pylint: disable=broad-exception-caught
            available, detail = False, f"probe raised: {error}"  # a probe must not crash doctor
        if available:
            status = CheckStatus.PASS
        elif self.requirement is Requirement.REQUIRED:
            status = CheckStatus.FAIL
        else:
            status = CheckStatus.WARN
        return CheckResult(self.name, self.requirement, status, detail)


@dataclass(frozen=True)
class DiagnosticsReport:
    """The aggregate outcome of an environment diagnostic run."""

    results: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        """Whether no *required* capability failed."""
        return all(result.status is not CheckStatus.FAIL for result in self.results)

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        """The optional capabilities that are unavailable."""
        return tuple(result for result in self.results if result.status is CheckStatus.WARN)


class EnvironmentDoctor:
    """Runs a set of environment checks and aggregates their report."""

    def __init__(self, checks: Sequence[EnvironmentCheck]) -> None:
        """Initialise with the checks to run (copied defensively)."""
        self._checks = tuple(checks)

    def run(self) -> DiagnosticsReport:
        """Run every check and return the aggregate report."""
        return DiagnosticsReport(tuple(check.run() for check in self._checks))


# Detection helpers (module-level so tests can simulate present/absent).


def _interpreter_version() -> tuple[int, int]:
    return sys.version_info[:2]


def _os_has(name: str) -> bool:
    return hasattr(os, name)


def _socket_has_af_unix() -> bool:
    return hasattr(socket, "AF_UNIX")


def _fcntl_present() -> bool:
    return importlib.util.find_spec("fcntl") is not None


def _signals_present() -> bool:
    return hasattr(signal, "SIGTERM") and hasattr(signal, "SIGINT")


def _available_hash_algorithms() -> frozenset[str]:
    return frozenset(hashlib.algorithms_available)


def _sqlite_supports_wal() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        conn = sqlite3.connect(str(Path(directory) / "wal-probe.db"))
        try:
            row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        finally:
            conn.close()
    return bool(row) and str(row[0]).lower() == "wal"


# Probes: each returns (available, human-readable detail).


def _probe_python_version() -> tuple[bool, str]:
    major, minor = _interpreter_version()
    ok = (major, minor) >= _MIN_PYTHON
    return ok, f"Python {major}.{minor} ({'>=' if ok else '<'} 3.10 required)"


def _probe_af_unix() -> tuple[bool, str]:
    if _socket_has_af_unix():
        return True, "socket.AF_UNIX available"
    return False, "socket.AF_UNIX unavailable — the control plane cannot bind (POSIX only)"


def _probe_fcntl() -> tuple[bool, str]:
    if _fcntl_present():
        return True, "fcntl available"
    return False, "fcntl unavailable — the singleton process lock cannot be held (POSIX only)"


def _probe_signals() -> tuple[bool, str]:
    if _signals_present():
        return True, "SIGTERM/SIGINT available"
    return False, "SIGTERM/SIGINT unavailable — graceful shutdown is unsupported"


def _probe_sqlite_wal() -> tuple[bool, str]:
    if _sqlite_supports_wal():
        return True, f"SQLite {sqlite3.sqlite_version} supports WAL journaling"
    return False, f"SQLite {sqlite3.sqlite_version} does not support WAL journaling"


def _probe_hash_algorithm(algorithm: str) -> tuple[bool, str]:
    if algorithm in _available_hash_algorithms():
        return True, f"hash algorithm {algorithm!r} available"
    return False, f"hash algorithm {algorithm!r} not in hashlib.algorithms_available"


def _probe_kernel_copy() -> tuple[bool, str]:
    if _os_has("copy_file_range"):
        return True, "os.copy_file_range available (kernel-assisted copy)"
    return False, "os.copy_file_range unavailable — copies use the buffered fallback"


def _probe_o_nofollow() -> tuple[bool, str]:
    if _os_has("O_NOFOLLOW"):
        return True, "os.O_NOFOLLOW available"
    return False, "os.O_NOFOLLOW unavailable — temporary-file symlink hardening is reduced"


def default_checks(*, algorithm: str, use_kernel_copy: bool) -> list[EnvironmentCheck]:
    """Build the standard capability check set for the given configuration.

    The kernel-copy check is included only when ``use_kernel_copy`` is enabled, so a
    deployment that has deliberately disabled it is not warned about an unused feature.
    """
    checks = [
        EnvironmentCheck("python-version", Requirement.REQUIRED, _probe_python_version),
        EnvironmentCheck("af-unix-socket", Requirement.REQUIRED, _probe_af_unix),
        EnvironmentCheck("fcntl-lock", Requirement.REQUIRED, _probe_fcntl),
        EnvironmentCheck("posix-signals", Requirement.REQUIRED, _probe_signals),
        EnvironmentCheck("sqlite-wal", Requirement.REQUIRED, _probe_sqlite_wal),
        EnvironmentCheck(
            f"hash-algorithm[{algorithm}]",
            Requirement.REQUIRED,
            lambda: _probe_hash_algorithm(algorithm),
        ),
        EnvironmentCheck("o-nofollow", Requirement.OPTIONAL, _probe_o_nofollow),
    ]
    if use_kernel_copy:
        checks.append(EnvironmentCheck("kernel-copy", Requirement.OPTIONAL, _probe_kernel_copy))
    return checks
