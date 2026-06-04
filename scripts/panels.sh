# DESC: Regenerate the site's real-output panels (outputgen → committed HTML)
#
# Usage: ./dev panels [out-dir]
#   ./dev panels                 # default: web/src/generated/panels (in-repo)
#   ./dev panels path/to/panels  # override target
#
# The PANELS set in tools/outputgen.py captures painted demos/specimens through
# render_html and writes each as a standalone HTML fragment the Astro site (web/)
# imports. Since the docs-site fold these live in-repo, so the default target is
# web/src/generated/panels and `./dev check` verifies they're current — a renderer
# change that forgets to regen fails the gate. Re-run whenever the demos, the
# PANELS manifest, the palette, or the renderer changes.
set -euo pipefail

OUT="${1:-}"
if [ -n "$OUT" ]; then
    uv run python -m tools.outputgen --emit-panels "$OUT"
else
    uv run python -m tools.outputgen --emit-panels
fi
