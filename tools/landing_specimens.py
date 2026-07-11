#!/usr/bin/env python3
"""Landing specimens — the public site's front door, rendered by the real library.

Companion to `tools/reference_specimens.py`. Where that module is the exhaustive
catalog, this is the *landing page's* painted centerpiece: the brand hero plus the
three "door" cards that route a visitor deeper into the site. `tools/outputgen.py`
captures each constant here through `render_html` (cells → HTML) and writes one
committed fragment per panel under the site's `generated/panels/` dir, where the
Astro `index.astro` imports them as `?raw`.

Laning (load-bearing — see web/README.md):
    The site chrome around these panels (nav, footer, page layout) is ordinary
    token-skinned HTML — it has to be sticky, responsive, and clickable, which a
    fixed-width cell grid is not. These panels are the opposite: genuine library
    output, the *display* layer. The split is display ↔ interactivity, not
    chrome ↔ content. Anything painted renders (the wordmark, the cards) is real;
    anything that needs a click, a hover, or reflow is the browser's job.

    Color is sourced honestly: every hue below is read off `PAINTED_PALETTE.series`
    (the vivid categorical ramp), never hand-typed CSS. The wordmark spends the
    ramp letter-by-letter; each door wears one ramp hue. So "colorful" here is the
    palette the renderer actually ships, not decoration bolted on in the stylesheet.

Each door is its OWN panel (its own `<pre>`), so the site makes it clickable by
wrapping the whole fragment in a single `<a>` — no per-cell coordinate overlay
needed. (The general-form "many links inside one render" component is deliberately
NOT built yet: nothing here needs sub-panel hotspots — dissolution test.)

Run it (`uv run python tools/landing_specimens.py`) to browse the front door in the
terminal — the same Blocks the site renders.
"""

from __future__ import annotations

from painted import (
    ROUNDED,
    Block,
    PAINTED_PALETTE,
    Style,
    border,
    current_palette,
    join_horizontal,
    join_vertical,
    print_block,
    use_palette,
)
from painted.views import BigTextFormat, render_big

# The site renders under the vivid truecolor skin; the hero + doors take their
# color from this palette's categorical ramp.
_SITE_PALETTE = PAINTED_PALETTE


def _series_hue(i: int) -> Style:
    """The i-th hue of the site palette's categorical ramp (read live, not typed)."""
    with use_palette(_SITE_PALETTE):
        return current_palette().series[i]


# --- Hero ---------------------------------------------------------------------


def _hero() -> Block:
    """render_big, one ramp hue per letter — the wordmark spends the whole series.

    `painted` is seven letters and `PAINTED_PALETTE.series` is seven hues, so the
    mapping is 1:1 and exhaustive. Glyphs are fixed-width (5 cells each at size=2),
    so rendering letter-by-letter and re-joining at gap=1 reproduces the one-shot
    `render_big("painted")` spacing exactly — only now each letter carries its own
    color straight off the ramp.

    size=2 (the 5-row font) on purpose: a web hero has no reason to want the 3-row
    font's compactness, and at 3 cells wide the round letters (p/a/d) can't resolve
    a clean stem-plus-bowl. The 5×5 glyphs are unambiguous — the legible default for
    display-size text.
    """
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        series = current_palette().series
        word = "painted"
        letters = [
            render_big(ch, series[i % len(series)], size=2, format=BigTextFormat.FILLED)
            for i, ch in enumerate(word)
        ]
        wordmark = join_horizontal(*letters, gap=1)
        tagline = Block.text("Python data  →  terminal pixels.", p.muted)
        return join_vertical(wordmark, Block.empty(1, 1), tagline, gap=0)


# --- Doors --------------------------------------------------------------------


def _door(
    glyph: str, label: str, blurb: str, hint: str, hue: Style, *, soon: bool = False
) -> Block:
    """One routing card: a ROUNDED border in the door's ramp hue, a reverse-video
    title bar (glyph + name, with a `→` affordance or a `soon` badge), and two body
    lines. Each door is a standalone panel so the site can wrap it in one anchor."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        inner = 34
        bar_style = hue.merge(Style(reverse=True, bold=True))

        left = Block.text(f" {glyph} {label}", bar_style)
        badge = "soon " if soon else "→ "
        right = Block.text(badge, bar_style)
        spacer = Block.text(" " * (inner - left.width - right.width), bar_style)
        title_bar = join_horizontal(left, spacer, right)

        blurb_line = Block.text(" " + blurb, hue, width=inner)
        hint_line = Block.text(" " + hint, p.muted, width=inner)
        body = join_vertical(
            title_bar,
            Block.empty(inner, 1),
            blurb_line,
            hint_line,
            gap=0,
        )
        return border(body, chars=ROUNDED, style=(p.muted if soon else hue))


def _door_walkthrough() -> Block:
    """Cyan door → the monotonic-enhancement walkthrough."""
    return _door(
        "▸",
        "walkthrough",
        "one dataset, every surface",
        "print → live → TUI, monotonic",
        _series_hue(3),  # cyan
    )


def _door_reference() -> Block:
    """Green door → the reference catalog."""
    return _door(
        "◆",
        "reference",
        "components · colors · glyphs",
        "every panel is real output",
        _series_hue(0),  # green
    )


def _door_guides() -> Block:
    """Orange door → the guides (not yet shipped). Hollow ◇ to reference's filled
    ◆ — filled = shipped/real, hollow = soon."""
    return _door(
        "◇",
        "guides",
        "task-shaped, level by level",
        "landing next",
        _series_hue(6),  # orange
        soon=True,
    )


# --- Registry -----------------------------------------------------------------
# Panel name (→ generated/panels/<name>.html, → outputgen PANELS data_attr) maps
# to its real Block. Mirrors reference_specimens.py's CATALOG shape.

HERO = _hero()
DOOR_WALKTHROUGH = _door_walkthrough()
DOOR_REFERENCE = _door_reference()
DOOR_GUIDES = _door_guides()

LANDING: dict[str, Block] = {
    "hero": HERO,
    "door_walkthrough": DOOR_WALKTHROUGH,
    "door_reference": DOOR_REFERENCE,
    "door_guides": DOOR_GUIDES,
}


def main() -> None:
    """Browse the front door in the terminal — the same Blocks the site renders."""
    for name, block in LANDING.items():
        print_block(Block.text(f"── {name} ", Style(dim=True)))
        print_block(block)
        print()


if __name__ == "__main__":
    main()
