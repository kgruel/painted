#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

./dev check > /tmp/painted-autoresearch-focus-checks.log 2>&1 || {
  tail -80 /tmp/painted-autoresearch-focus-checks.log
  exit 1
}
