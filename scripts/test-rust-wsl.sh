#!/usr/bin/env bash
# Every Rust validation includes zigbuild, ELF audit and SLES execution.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$repo_dir/scripts/check-rust-sles.py"
