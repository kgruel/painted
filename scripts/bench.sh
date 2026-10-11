#!/usr/bin/env bash
# DESC: Scenario baselines (informational, not gated) — tools/bench.py
#
# Usage: ./dev bench [--iterations N] [--only NAME|GROUP] [--save PATH] [--compare PATH]
#   ./dev bench --compare docs/baselines/baseline.json   # drift vs the recorded baseline
#
# See docs/PERFORMANCE.md for the scenario list and the comparison process.
set -euo pipefail
source "$(dirname "$0")/lib/dev.sh"
run_uv python -m tools.bench "$@"
