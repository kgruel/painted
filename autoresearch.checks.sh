#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

./dev check > /tmp/painted-autoresearch-checks.log 2>&1 || {
  tail -80 /tmp/painted-autoresearch-checks.log
  exit 1
}
