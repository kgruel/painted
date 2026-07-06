"""HTML rendering for Blocks.

Renders Blocks into <pre> output suitable for docs. Mirrors the traversal
pattern in painted.writer.write_block_ansi (row-by-row, coalescing runs
of identical style).
"""

from __future__ import annotations

import html as _html

from .block import Block
from .cell import NAMED_COLORS, Style
from ._color import _idx_to_rgb
from ._row_ops import iter_row_spans
from ..refs import resolve_ref

_BASE_FG = "var(--painted-fg, var(--text))"
_BASE_BG = "var(--painted-bg, var(--code-bg))"


def _color_to_css(color: str | int | None) -> str | None:
    if color is None:
        return None
    if isinstance(color, int):
        r, g, b = _idx_to_rgb(color)
        return f"#{r:02x}{g:02x}{b:02x}"
    if isinstance(color, str):
        if color.startswith("#") and len(color) == 7:
            return color
        name = color.lower()
        if name in NAMED_COLORS:
            # A named color IS its ANSI index — resolve it through painted's own
            # color table (same path as an int), not the browser's CSS keyword.
            # CSS keywords disagree with painted's _BASIC_RGB (e.g. keyword "red"
            # is #FF0000 but painted red is #800000), so keyword passthrough was
            # unfaithful to what painted actually renders.
            r, g, b = _idx_to_rgb(NAMED_COLORS[name])
            return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _style_to_css(style: Style) -> str:
    parts: list[str] = []
    fg_css = _color_to_css(style.fg)
    bg_css = _color_to_css(style.bg)

    if style.reverse:
        parts.append(f"color: {bg_css if bg_css is not None else _BASE_BG}")
        parts.append(f"background-color: {fg_css if fg_css is not None else _BASE_FG}")
    else:
        if fg_css is not None:
            parts.append(f"color: {fg_css}")
        if bg_css is not None:
            parts.append(f"background-color: {bg_css}")
    if style.bold:
        parts.append("font-weight: bold")
    if style.italic:
        parts.append("font-style: italic")
    if style.underline:
        parts.append("text-decoration: underline")
    if style.dim:
        parts.append("opacity: 0.6")
    return "; ".join(parts)


def _refs_row(block: Block, row_idx: int) -> tuple[str | None, ...] | None:
    """The ref annotations for one row, or None when the row carries no refs.

    Mirrors ``Block.cell_ref``: a per-cell grid takes precedence; absent it, a
    uniform whole-block ref applies to every cell; absent both, the row is
    ref-less and the anchor state machine never fires.
    """
    if block._refs is not None:
        return block._refs[row_idx]
    if block.ref is not None:
        return (block.ref,) * block.width
    return None


def render_html(block: Block) -> str:
    """Render a Block into HTML.

    Returns a <pre class="painted-output"> wrapper containing optional
    <span style="..."> runs for styled cells. Cells whose ref resolves to a URI
    through an ambient ``RefScheme`` (``use_refs``) are wrapped in an ``<a href>``
    anchor; the resolver seam is read ambiently, so there is no signature change.
    """
    out: list[str] = ['<pre class="painted-output">']

    # Resolve each distinct ref once per call — the choke point may run app code.
    resolved: dict[str, str | None] = {}

    def _href(ref: str | None) -> str | None:
        if ref is None:
            return None
        if ref not in resolved:
            # An empty-string URI is "no URI" — <a href=""> is a self-link to
            # the current page, not a resolved denotation. Same fold as the
            # ANSI writer's inert branch, so the two deliveries agree.
            resolved[ref] = resolve_ref(ref) or None
        return resolved[ref]

    for row_idx in range(block.height):
        last_css: str | None = None
        span_open = False
        # Anchor state runs alongside the span state: <a> wraps <span>, and the
        # two are independent state machines — a ref-only transition must fire
        # even when style is unchanged. Transitions key on the REF, not the
        # resolved href (mirroring the ANSI writer's last_ref), so a ref change
        # re-anchors even when two refs resolve to the same URI. open_ref is
        # non-None only while an anchor is actually open — a ref that resolves
        # to no URI leaves it None, so a later return to a linked ref reopens.
        # An anchor never crosses a row boundary.
        open_ref: str | None = None
        refs_row = _refs_row(block, row_idx)

        for row_span in iter_row_spans(block.row(row_idx), refs_row):
            cell = row_span.cells[0]
            ref = row_span.refs[0] if row_span.refs is not None else None
            href = _href(ref)

            target_ref = ref if href is not None else None
            if target_ref != open_ref:
                # Close inner-then-outer, in reverse-open order, before switching.
                if span_open:
                    out.append("</span>")
                    span_open = False
                    last_css = None
                if open_ref is not None:
                    out.append("</a>")
                if href is not None:
                    out.append(f'<a href="{_html.escape(href, quote=True)}">')
                open_ref = target_ref

            css = _style_to_css(cell.style)
            if not css:
                if span_open:
                    out.append("</span>")
                    span_open = False
                    last_css = None
                out.append(_html.escape(cell.char))
                continue

            if css != last_css:
                if span_open:
                    out.append("</span>")
                out.append(f'<span style="{_html.escape(css, quote=True)}">')
                span_open = True
                last_css = css

            out.append(_html.escape(cell.char))

        if span_open:
            out.append("</span>")
        if open_ref is not None:
            out.append("</a>")
        out.append("\n")

    out.append("</pre>\n")
    return "".join(out)
