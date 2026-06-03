# DESC: Regenerate the site's real-output panels (outputgen → committed HTML)
#
# Usage: ./dev panels <out-dir>
#   e.g. ./dev panels ../<site-worktree>/web/src/generated/panels
#
# The PANELS set in tools/outputgen.py captures painted demos at points on the
# "no cliffs" continuum and writes each as a standalone HTML fragment via
# render_html. The site imports these committed fragments. Re-run this whenever
# the demos, the PANELS manifest, the palette, or the renderer changes.
set -euo pipefail

OUT="${1:-}"
if [ -z "$OUT" ]; then
    echo "usage: ./dev panels <out-dir>" >&2
    echo "  e.g. ./dev panels ../<site-worktree>/web/src/generated/panels" >&2
    exit 2
fi

uv run python -m tools.outputgen --emit-panels "$OUT"
