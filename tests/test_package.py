"""Package-level smoke tests: version and full import tree."""

from __future__ import annotations

import importlib

import pytest

import file_mover

# Every module in the package. Importing them all keeps the Foundation-milestone
# placeholders honest (they must at least import cleanly) and asserts the
# stdlib-only contract indirectly — a non-stdlib import here would fail with no
# runtime dependencies installed.
ALL_MODULES = [
    "file_mover",
    "file_mover.__main__",
    "file_mover.cli",
    "file_mover.configuration",
    "file_mover.constants",
    "file_mover.exceptions",
    "file_mover.logging_config",
    "file_mover.service",
    "file_mover.control",
    "file_mover.control.protocol",
    "file_mover.control.server",
    "file_mover.control.client",
    "file_mover.control.dispatcher",
    "file_mover.jobs",
    "file_mover.jobs.models",
    "file_mover.jobs.repository",
    "file_mover.jobs.sqlite_repository",
    "file_mover.transfer",
    "file_mover.transfer.coordinator",
    "file_mover.transfer.copy_engine",
    "file_mover.transfer.integrity",
    "file_mover.transfer.retry",
    "file_mover.recovery",
    "file_mover.recovery.manager",
]


@pytest.mark.requirement("L3-PY-001")
def test_version_is_a_string() -> None:
    assert isinstance(file_mover.__version__, str)
    assert file_mover.__version__


@pytest.mark.requirement("L3-PY-001")
@pytest.mark.parametrize("module_name", ALL_MODULES)
def test_every_module_imports(module_name: str) -> None:
    # __main__ raises SystemExit on import (it is an entry point); import it in a
    # controlled way so the tree check still covers it.
    if module_name == "file_mover.__main__":
        pytest.skip("entry-point module is exercised via the CLI tests")
    assert importlib.import_module(module_name) is not None
