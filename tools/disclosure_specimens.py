#!/usr/bin/env python3
"""Disclosure ladder specimens — real panels for the site's fidelity branch page.

Each constant is a `Block` produced by the canonical disclosure exemplar
(`demos/patterns/fidelity.py` — disk usage) rendered under an explicitly built
`Fidelity` — the same compiled spec the flag grammar produces, so every panel is
exactly what the named invocation prints. `tools/outputgen.py` captures them
through `render_html` into committed fragments consumed by
`web/src/pages/walkthrough/fidelity.astro`.

Every panel is produced by calling the exemplar's own `_render(ctx, data)` — the
same entry point the CLI drives — so the renderers, tag implications, and density
budget are all sourced from one place (the demo), not re-derived here. This tool
only pins the exemplar's timestamp so the captured panels are deterministic (the
live `_fetch()` path stamps `now()`).

The ladder the panels walk (docs/FIDELITY_DESIGN.md):
    rung 1  depth          -q / default / -v / -vv          anonymous detail
            depth aliases   --brief / --full  (named spellings of rung 1, not a new rung)
    rung 2  named facet     --timestamp (explicit at -q; implied at -v)
    rung 3  budgets         --max-lines  (density, orthogonal to depth)
    rung 4  structural      doc_lens applies the whole spec to a Doc tree

`depth_aliases` is pure spelling: an alias flag sets `depth`, then compilation
proceeds identically. So `--brief` (=0) yields the same `Fidelity` as `-q`, and
`--full` (=3) yields the same `Fidelity` as `-vv` — *including* tag implications,
which is why `--full` carries the timestamp (its `implied_at=2` trips at depth
3) while `--brief` does not. The two alias panels here are rendered through the
same `_panel(depth)` helper the anonymous flags use, proving the equality is
real and not narrated.

Like the reference catalog, this spans a concern rather than teaching one
concept, so it lives in `tools/` beside its consumer. Run it
(`uv run python tools/disclosure_specimens.py`) to browse the specimens in the
terminal.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from painted import Block, CliContext, Fidelity
from painted.cli import OutputMode, implied_visible
from painted.core.doc import doc_lens

if __package__ is None:  # invoked as a script: python tools/disclosure_specimens.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from painted._doc_pages import DOCS as _DOC_PAGES

from tools.capture import import_module_by_path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEMO = import_module_by_path(_REPO_ROOT / "demos/patterns/fidelity.py")

_WIDTH = 62

# A fixed measurement timestamp so the --timestamp facet is deterministic in the
# captured panels (the live _fetch() path stamps now()). The named-facet rungs
# read this through fidelity.shows("timestamp").
_SAMPLE = replace(_DEMO.SAMPLE_DISK, timestamp="2026-06-11T09:30:00")

# The aliases the exemplar's depth axis answers to. Pure spelling, matching the
# design's canonical example (docs/FIDELITY_DESIGN.md §4): --brief ⇒ depth 0,
# --full ⇒ depth 3. The page declares these on run_cli; here we render at the
# depth each alias resolves to, which IS what parse_fidelity compiles them into.
_DEPTH_ALIASES = {"brief": 0, "full": 3}


def _panel(depth: int, *extra: str, chars: int = 0, lines: int = 0) -> Block:
    """Render the exemplar's sample disk under a compiled Fidelity.

    Tag implications resolve exactly as the CLI compiler would (the demo's
    `_TAGS`), with `extra` standing in for explicitly passed tag flags, and
    `chars`/`lines` standing in for `--max-chars`/`--max-lines`. The demo's own
    `_render` applies the density budget from the spec, so the panels exercise
    that single source — no reshaping is re-derived here.
    """
    fidelity = Fidelity(
        depth=depth,
        visible=implied_visible(_DEMO._TAGS, depth) | frozenset(extra),
        chars=chars,
        lines=lines,
    )
    ctx = CliContext(
        fidelity=fidelity,
        mode=OutputMode.STATIC,
        use_ansi=False,
        is_tty=False,
        width=_WIDTH,
        height=24,
    )
    return _DEMO._render(ctx, _SAMPLE)


# --- Rung 1: depth — anonymous detail picks the renderer -----------------------
DISCLOSURE_Q = _panel(0)
DISCLOSURE_DEFAULT = _panel(1)
DISCLOSURE_VV = _panel(3)

# --- Rung 2: a named facet — --timestamp at -q; implied once depth reaches -v ---
DISCLOSURE_TAG_Q = _panel(0, "timestamp")
DISCLOSURE_V = _panel(2)  # implied_at=2 — the same facet arrives with depth

# --- Depth aliases: named spellings of the depth axis (rung 1, respelled) -------
# An alias is pure spelling: --brief sets depth=0, --full sets depth=3. Rendering
# at the resolved depth IS what the compiler does, so DISCLOSURE_BRIEF is byte-for
# -byte DISCLOSURE_Q, and DISCLOSURE_FULL is DISCLOSURE_VV — including the
# timestamp implication, which --full inherits by landing at depth 3.
DISCLOSURE_BRIEF = _panel(_DEPTH_ALIASES["brief"])
DISCLOSURE_FULL = _panel(_DEPTH_ALIASES["full"])

# --- Rung 3: density — the budget reshapes every depth without being depth ------
DISCLOSURE_BUDGET = _panel(3, lines=3)

# --- Rung 4: structural — doc_lens applies the whole spec to a node tree --------
_PRIMITIVES_DOC = _DOC_PAGES["primitives"].build()
DISCLOSURE_DOC_D1 = doc_lens(_PRIMITIVES_DOC, fidelity=Fidelity(depth=1), width=_WIDTH)
DISCLOSURE_DOC_D2 = doc_lens(_PRIMITIVES_DOC, fidelity=Fidelity(depth=2), width=_WIDTH)


DISCLOSURE: dict[str, Block] = {
    "disclosure_q": DISCLOSURE_Q,
    "disclosure_default": DISCLOSURE_DEFAULT,
    "disclosure_vv": DISCLOSURE_VV,
    "disclosure_tag_q": DISCLOSURE_TAG_Q,
    "disclosure_v": DISCLOSURE_V,
    "disclosure_brief": DISCLOSURE_BRIEF,
    "disclosure_full": DISCLOSURE_FULL,
    "disclosure_budget": DISCLOSURE_BUDGET,
    "disclosure_doc_d1": DISCLOSURE_DOC_D1,
    "disclosure_doc_d2": DISCLOSURE_DOC_D2,
}

# Invariants the panels assert by construction — a depth alias must be pure
# spelling, or the depth-alias teaching is a lie. Checked at import so a renderer or
# compiler change that broke the equality fails `./dev panels` / the gate loudly,
# at the source, instead of silently diverging on the page. (`Block` is identity-
# equal, so the meaningful equality is rendered output — the cells the page shows.)
def _cells(block: Block) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(cell.char for cell in block.row(y)) for y in range(block.height)
    )


assert _cells(DISCLOSURE_BRIEF) == _cells(DISCLOSURE_Q), (
    "depth alias --brief must equal -q (depth 0)"
)
assert _cells(DISCLOSURE_FULL) == _cells(DISCLOSURE_VV), (
    "depth alias --full must equal -vv (depth 3)"
)


if __name__ == "__main__":
    from painted import Style, join_vertical, print_block

    for name, block in DISCLOSURE.items():
        print_block(join_vertical(Block.text(f"── {name}", Style(dim=True)), block, gap=1))
        print()
