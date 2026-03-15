#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

cd "$REPO_ROOT"

./dev check > /tmp/painted-import-surface-autoresearch-checks.log 2>&1 || {
  tail -80 /tmp/painted-import-surface-autoresearch-checks.log
  exit 1
}

PYTHONPATH=src uv run python - <<'PY'
import sys

import painted.core

loaded = {m for m in sys.modules if m == "painted.cli" or m.startswith("painted.cli.")}
loaded |= {m for m in sys.modules if m == "painted.views" or m.startswith("painted.views.")}
loaded |= {m for m in sys.modules if m == "painted.tui" or m.startswith("painted.tui.")}

assert not loaded, f"painted.core imported higher layers: {sorted(loaded)}"

from painted import Block, Zoom, run_cli, show

assert Block.__name__ == "Block"
assert Zoom.__name__ == "Zoom"
assert callable(run_cli)
assert callable(show)
PY
