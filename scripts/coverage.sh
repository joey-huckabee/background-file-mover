#!/usr/bin/env bash
# scripts/coverage.sh — local coverage convenience wrapper.
#
# Runs the pytest suite with the combined line+branch coverage gate
# (fail_under lives in pyproject.toml [tool.coverage.report]). Forwards any
# extra arguments through to pytest, e.g.:
#
#     bash scripts/coverage.sh                       # terminal report + gate
#     bash scripts/coverage.sh --cov-report=html     # also write htmlcov/
#
# For the CI-style XML report:  bash scripts/coverage.sh --cov-report=xml

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec poetry run pytest --cov --cov-report=term-missing "$@"
