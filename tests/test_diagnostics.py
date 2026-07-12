"""Tests for environment capability diagnostics (deterministic on any host)."""

from __future__ import annotations

import pytest

from file_mover import diagnostics as diag
from file_mover.diagnostics import (
    CheckStatus,
    EnvironmentCheck,
    EnvironmentDoctor,
    Requirement,
    default_checks,
)


def _check(available: bool, requirement: Requirement = Requirement.REQUIRED) -> EnvironmentCheck:
    return EnvironmentCheck("probe", requirement, lambda: (available, "detail"))


@pytest.mark.requirement("L2-ENV-001")
def test_required_present_passes_and_missing_fails() -> None:
    assert _check(True).run().status is CheckStatus.PASS
    assert _check(False).run().status is CheckStatus.FAIL


@pytest.mark.requirement("L2-ENV-002")
def test_optional_missing_warns_not_fails() -> None:
    assert _check(False, Requirement.OPTIONAL).run().status is CheckStatus.WARN
    assert _check(True, Requirement.OPTIONAL).run().status is CheckStatus.PASS


@pytest.mark.requirement("L2-ENV-003")
def test_probe_exception_is_reported_never_raised() -> None:
    def _boom() -> tuple[bool, str]:
        raise RuntimeError("kaboom")

    result = EnvironmentCheck("probe", Requirement.REQUIRED, _boom).run()
    assert result.status is CheckStatus.FAIL
    assert "kaboom" in result.detail  # surfaced in the detail, not propagated


@pytest.mark.requirement("L2-ENV-001")
def test_report_ok_and_warnings_aggregate() -> None:
    report = EnvironmentDoctor([_check(True), _check(False, Requirement.OPTIONAL)]).run()
    assert report.ok is True  # no required failure
    assert len(report.warnings) == 1
    # A single required failure flips ok to False.
    assert EnvironmentDoctor([_check(False), _check(True)]).run().ok is False


@pytest.mark.requirement("L2-ENV-001")
def test_af_unix_and_fcntl_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "_socket_has_af_unix", lambda: True)
    assert diag._probe_af_unix()[0] is True
    monkeypatch.setattr(diag, "_socket_has_af_unix", lambda: False)
    assert diag._probe_af_unix()[0] is False
    monkeypatch.setattr(diag, "_fcntl_present", lambda: False)
    available, detail = diag._probe_fcntl()
    assert available is False and "process lock" in detail


@pytest.mark.requirement("L2-ENV-001")
def test_python_version_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "_interpreter_version", lambda: (3, 10))
    assert diag._probe_python_version()[0] is True
    monkeypatch.setattr(diag, "_interpreter_version", lambda: (3, 9))
    assert diag._probe_python_version()[0] is False


@pytest.mark.requirement("L2-ENV-001")
def test_hash_algorithm_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "_available_hash_algorithms", lambda: frozenset({"sha256"}))
    assert diag._probe_hash_algorithm("sha256")[0] is True
    assert diag._probe_hash_algorithm("blake2b")[0] is False


@pytest.mark.requirement("L2-ENV-002")
def test_optional_capability_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "_os_has", lambda name: name == "O_NOFOLLOW")
    assert diag._probe_o_nofollow()[0] is True
    assert diag._probe_kernel_copy()[0] is False


@pytest.mark.requirement("L2-ENV-001")
def test_sqlite_wal_probe_on_real_sqlite() -> None:
    # The bundled SQLite supports WAL on every CI target.
    assert diag._probe_sqlite_wal()[0] is True


@pytest.mark.requirement("L2-ENV-002")
def test_default_checks_include_kernel_copy_only_when_enabled() -> None:
    enabled = [c.name for c in default_checks(algorithm="sha256", use_kernel_copy=True)]
    disabled = [c.name for c in default_checks(algorithm="blake2b", use_kernel_copy=False)]
    assert "kernel-copy" in enabled and "kernel-copy" not in disabled
    assert "hash-algorithm[sha256]" in enabled and "hash-algorithm[blake2b]" in disabled
    # Every required capability is present in the set.
    required = {c.name for c in default_checks(algorithm="sha256", use_kernel_copy=True)}
    assert {"python-version", "af-unix-socket", "fcntl-lock", "sqlite-wal"} <= required
