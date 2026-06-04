#!/usr/bin/env python3
"""Reference catalog — real painted specimens for the public site's /reference page.

Each constant here is a `Block` built from painted's *real* API: actual
components, lenses, palettes, borders, glyph sets. `tools/outputgen.py` captures
them through `render_html` (cells → HTML) and writes one committed fragment per
card under the site's `generated/panels/` dir, where the Astro `/reference` page
imports them as `?raw`.

Laning (load-bearing — see web/README.md):
    The site's Claude-Design preview cards are COSMETIC recreations. This module
    is the opposite: every specimen below is genuine library output. The Design
    card's label tells us *which* feature to showcase; it does NOT dictate what
    the output looks like. We build the real Block and ship whatever `render_html`
    produces — we never tune a specimen to match the mock's polish. Where painted
    renders something less polished than the mock (uncolored chart bars, the
    brightened-ANSI swatches, the █/░ progress glyphs), that *is* the feature.

    Two Design cards have NO specimen here on purpose: `colors-theme` (the dark
    ink/panel/overlay surfaces) and `type-scale` (a web font ladder) are CSS
    design tokens, not renderer output — painted paints fg-styled glyphs on a
    transparent background and has no surface colors, font face, or px sizing.
    The `/reference` page labels those two "cosmetic" rather than faking them.

This is not a teaching demo (it spans the whole API rather than one concept), so
it lives in `tools/` beside its consumer rather than in the `demos/` ladder. Run
it (`uv run python tools/reference_specimens.py`) to browse every specimen in the
terminal — the same Blocks the site renders.
"""

from __future__ import annotations

from painted import (
    ASCII,
    ASCII_ICONS,
    DEFAULT_PALETTE,
    DOUBLE,
    HEAVY,
    LIGHT,
    MONO_PALETTE,
    NORD_PALETTE,
    PAINTED_PALETTE,
    ROUNDED,
    Align,
    Block,
    IconSet,
    Line,
    Style,
    border,
    current_palette,
    join_horizontal,
    join_vertical,
    print_block,
    use_icons,
    use_palette,
)
from painted.views import (
    BRAILLE,
    DOTS,
    LINE,
    BigTextFormat,
    Column,
    ListState,
    ProgressState,
    SpinnerState,
    TableState,
    chart_lens,
    list_view,
    progress_bar,
    render_big,
    sparkline,
    spinner,
    table,
    tree_lens,
)

# The palette the site renders under: vivid truecolor, matching the walkthrough's
# default. Color-specific specimens override this to show the palette they name.
_SITE_PALETTE = PAINTED_PALETTE


def _style_desc(style: Style) -> str:
    """Compact, honest descriptor of a Style — derived from the real object."""
    parts: list[str] = []
    if style.fg is not None:
        parts.append(f"fg={style.fg}")
    if style.bg is not None:
        parts.append(f"bg={style.bg}")
    for flag in ("bold", "italic", "underline", "reverse", "dim"):
        if getattr(style, flag):
            parts.append(flag)
    return f"Style({', '.join(parts)})"


# --- Components ---------------------------------------------------------------


def _comp_table() -> Block:
    """table() — header, separator, reverse-video selection (views/components)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        columns = [
            Column(Line.plain("name"), 11),
            Column(Line.plain("status"), 8),
            Column(Line.plain("latency"), 7, Align.END),
        ]
        rows = [
            [Line.plain("api-gateway"), Line.plain("ok", p.success), Line.plain("12ms")],
            [Line.plain("auth-svc"), Line.plain("ok", p.success), Line.plain("31ms")],
            [Line.plain("cache"), Line.plain("degraded", p.warning), Line.plain("140ms")],
            [Line.plain("worker-pool"), Line.plain("down", p.error), Line.plain("—")],
        ]
        state = TableState().with_count(len(rows)).move_to(1)  # select auth-svc
        return table(state, columns, rows, visible_height=len(rows))


def _comp_buttons() -> Block:
    """Action affordances + list_view — styled-text buttons, ▸-cursor selection (views/components)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        # Terminal "buttons" are styled text, not a component: primary = reverse
        # accent, secondary = plain, danger = error fg.
        primary = Block.text(" Save ", p.accent.merge(Style(reverse=True, bold=True)))
        secondary = Block.text(" Cancel ", Style())
        danger = Block.text(" Delete ", p.error.merge(Style(bold=True)))
        gap = Block.text("  ", Style())
        actions = join_horizontal(primary, gap, secondary, gap, danger)
        # Selection list: the ▸ cursor + accent highlight IS the interaction model.
        items = [Line.plain(t) for t in ("Overview", "Metrics", "Alerts", "Settings")]
        state = ListState().with_count(len(items)).move_to(2)  # Alerts active
        picker = list_view(
            state,
            items,
            visible_height=len(items),
            selected_style=p.accent.merge(Style(bold=True)),
            cursor_char="▸",
        )
        return join_vertical(actions, Block.empty(1, 1), picker, gap=0)


def _comp_card() -> Block:
    """The card idiom — border(ROUNDED) wrapping a reverse-video title bar plus
    label/value rows, with a real progress_bar() for the cpu metric."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        inner = 30  # inner width between the vertical border cells
        # Reverse-video title bar: service name left, status right, full-width fill.
        bar_style = Style(fg="cyan", reverse=True, bold=True)
        name = Block.text(" api-gateway", bar_style)
        dot = Block.text("● ", p.success.merge(Style(reverse=True, bold=True)))
        ok = Block.text("ok ", bar_style)
        spacer = Block.text(" " * (inner - name.width - dot.width - ok.width), bar_style)
        title_bar = join_horizontal(name, spacer, dot, ok)

        def kv(label: str, value: Block) -> Block:
            return join_horizontal(Block.text(" " + label.ljust(12), Style()), value)

        rows = [
            kv("replicas", Block.text("2/3 ready", Style())),
            kv("uptime", Block.text("12d 4h", p.muted)),
            kv("latency", Block.text("12ms", p.accent)),
            kv(
                "cpu",
                join_horizontal(
                    progress_bar(ProgressState(0.78), 10),
                    Block.text(" 78%", p.muted),
                ),
            ),
        ]
        body = join_vertical(title_bar, *rows, gap=0)
        return border(body, chars=ROUNDED, style=Style(fg="cyan"))


def _comp_chart() -> Block:
    """chart_lens — {label: number} dict to labeled horizontal bars at zoom 3 (views/lens/chart.py)."""
    data = {
        "us-east": 820,
        "us-west": 540,
        "eu-west": 670,
        "ap-south": 310,
        "sa-east": 190,
    }
    # chart_lens reads only the IconSet (bar glyphs), never the palette: every
    # cell is emitted with bare Style(). So no use_palette wrapper here — it
    # would be inert and falsely imply palette-theming the lens never applies.
    return chart_lens(data, zoom=3, width=40)


def _comp_listview() -> Block:
    """list_view() — ListState cursor marks the selection with a ▸ prefix (views/components)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        items = [Line.plain(label) for label in ("Status", "Charts", "Tree", "Carnival", "Logs")]
        state = ListState().with_count(len(items)).move_to(1)  # cursor on "Charts"
        # Default: reverse-video selection (selected_style defaults to Style(reverse=True)).
        default = list_view(state, items, visible_height=len(items))
        # Override: same cursor, but an accent fg style instead of reverse video.
        accent = list_view(
            state,
            items,
            visible_height=len(items),
            selected_style=p.accent.merge(Style(bold=True)),
        )
        return join_vertical(
            default,
            Block.empty(1, 1),
            accent,
            Block.text("selected_style → accent (no reverse)", p.muted),
            gap=0,
        )


def _comp_progress() -> Block:
    """progress_bar() — █ fill / ░ empty across four palette roles (views/components)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        rows = (
            ("build", 0.45, p.accent),
            ("deploy", 0.78, p.success),
            ("disk", 0.93, p.warning),
            ("errors", 0.16, p.error),
        )
        lines = []
        for label, value, role in rows:
            bar = progress_bar(
                ProgressState(value=value),
                24,
                filled_style=role.merge(Style(bold=True)),
                empty_style=p.muted,
            )
            lines.append(
                join_horizontal(
                    Block.text(label, p.muted, width=8),
                    bar,
                    Block.text("  ", Style()),
                    Block.text(f"{round(value * 100):>3}%", role),
                    gap=0,
                )
            )
        return join_vertical(*lines, gap=0)


def _comp_sparkline() -> Block:
    """sparkline() — numeric sequences as relative-magnitude bar glyphs (views/components)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        series = (
            ("cpu", [12, 18, 25, 38, 52, 67, 71, 63, 58, 72, 88, 95, 90, 77, 64, 55, 61, 73, 82, 79], p.accent),
            ("net", [40, 42, 38, 55, 80, 76, 30, 28, 33, 90, 85, 44, 40, 38, 36, 60, 72, 50, 45, 41], p.success),
            ("mem", [55, 58, 61, 60, 63, 66, 70, 68, 72, 75, 79, 82, 80, 77, 74, 71, 69, 66, 63, 60], p.warning),
        )
        lines = [
            join_horizontal(
                Block.text(label, p.muted, width=5),
                sparkline(values, width=20, style=style),
                Block.text(f"  {int(max(values))}%", p.muted),
            )
            for label, values, style in series
        ]
        return join_vertical(*lines, gap=0)


def _comp_spinner() -> Block:
    """spinner() — the live frame indicator plus the three shipped frame sets."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        # A live spinner leading a row of semantic status glyphs.
        working = SpinnerState(frame=1, frames=DOTS)
        status_row = join_horizontal(
            spinner(working, style=p.accent),
            Block.text(" connecting  ", p.muted),
            Block.text("● ", p.success),
            Block.text("ready  ", p.muted),
            Block.text("⚡ ", p.warning),
            Block.text("retrying  ", p.muted),
            Block.text("✗ ", p.error),
            Block.text("failed", p.muted),
        )
        # The three frame sets that ship, each at a representative frame, with
        # its full glyph sequence pulled from the real SpinnerFrames tuple.
        sets = (
            ("DOTS", DOTS, 2, p.accent),
            ("LINE", LINE, 1, p.success),
            ("BRAILLE", BRAILLE, 3, p.warning),
        )
        set_lines = [
            join_horizontal(
                spinner(SpinnerState(frame=idx, frames=frames), style=style),
                Block.text(f"  {name:<8}", style.merge(Style(bold=True))),
                Block.text(" ".join(frames.frames), p.muted),
            )
            for name, frames, idx, style in sets
        ]
        return join_vertical(status_row, Block.empty(1, 1), *set_lines, gap=0)


def _comp_tree() -> Block:
    """tree_lens — branch chars from the lens, styled name+size via node_renderer (views/lens/tree.py)."""
    KB, MB = 1024, 1024 * 1024

    def _human_size(n: int) -> str:
        if n >= MB:
            return f"{n / MB:.1f}M"
        if n >= KB:
            return f"{n / KB:.0f}K"
        return f"{n}B"

    def _dir_total(node: object) -> int:
        if isinstance(node, tuple) and len(node) == 2:  # (label, children) root form
            return _dir_total(node[1])
        if isinstance(node, dict):
            return sum(_dir_total(v) for v in node.values())
        return node if isinstance(node, (int, float)) else 0  # type: ignore[return-value]

    with use_palette(_SITE_PALETTE):
        p = current_palette()

        def node_renderer(key: str, value: object, depth: int) -> Block:
            is_dir = isinstance(value, (dict, tuple))
            name = f"{key}/" if is_dir else key
            return join_horizontal(
                Block.text(name, p.accent if is_dir else p.muted),
                Block.text(f"  {_human_size(int(_dir_total(value)))}", p.muted),
            )

        # Tuple (label, children) root form avoids the lens's synthetic "root" node.
        tree = (
            "painted",
            {
                "src": {"core": 840 * KB, "views": 610 * KB, "tui": 390 * KB},
                "tests": {"unit": 520 * KB, "property": 460 * KB},
                "demos": {"examples": 720 * KB, "patterns": 480 * KB},
            },
        )
        return tree_lens(tree, zoom=4, width=32, node_renderer=node_renderer)


# --- Colors -------------------------------------------------------------------


def _colors_palette() -> Block:
    """Palette — the 5 semantic roles of DEFAULT_PALETTE, each in its own style."""
    with use_palette(DEFAULT_PALETTE):
        p = current_palette()
        roles = (
            ("●", "success", p.success),
            ("⚡", "warning", p.warning),
            ("✗", "error", p.error),
            ("▸", "accent", p.accent),
            ("·", "muted", p.muted),
        )
        lines = [
            join_horizontal(
                Block.text(f"{glyph} ", style),
                Block.text(name, style.merge(Style(bold=True)), width=9),
                Block.text(_style_desc(style), p.muted),
            )
            for glyph, name, style in roles
        ]
        return join_vertical(*lines, gap=0)


def _colors_ansi() -> Block:
    """ANSI 16 — each index as a real bg-styled chip (core/_color.py)."""
    # bg is the index 0–15; render_html resolves it through painted's
    # authoritative _BASIC_RGB table, so 'red' is the brightened #c00000
    # (not VGA #800000). Each chip is labelled with its own index.
    with use_palette(PAINTED_PALETTE):
        muted = current_palette().muted
        light_swatches = (3, 7, 10, 11, 14, 15)  # indices whose RGB reads light

        def chip(idx: int) -> Block:
            ink = 0 if idx in light_swatches else 15  # black ink on light swatches
            return Block.text(f" {idx:>2} ", Style(bg=idx, fg=ink, bold=True))

        def swatches(base: int) -> Block:
            return join_horizontal(*(chip(base + i) for i in range(8)), gap=1)

        return join_vertical(
            join_horizontal(Block.text("normal", muted, width=7), swatches(0)),
            join_horizontal(Block.text("bright", muted, width=7), swatches(8)),
            gap=0,
        )


def _colors_presets() -> Block:
    """Palette presets — NORD's fg color roles vs MONO's modifier-only roles (palette.py)."""
    roles = ("success", "warning", "error", "accent", "muted")

    def _mods(style: Style) -> str:
        flags = [f for f in ("bold", "italic", "underline", "reverse", "dim") if getattr(style, f)]
        return "+".join(flags) if flags else "plain"

    with use_palette(NORD_PALETTE):
        np = current_palette()
        nord_styles = {r: getattr(np, r) for r in roles}
        nord_muted = np.muted
    with use_palette(MONO_PALETTE):
        mp = current_palette()
        mono_styles = {r: getattr(mp, r) for r in roles}
        mono_muted = mp.muted

    rows = []
    for role in roles:
        ns, ms = nord_styles[role], mono_styles[role]
        nord_cell = join_horizontal(
            Block.text("██ ", ns),
            Block.text(role, nord_muted, width=8),
        )
        mono_cell = join_horizontal(
            Block.text(role, ms, width=8),
            Block.text(_mods(ms), mono_muted),
        )
        rows.append(join_horizontal(nord_cell, Block.text("  ", nord_muted), mono_cell))

    head = join_horizontal(
        Block.text("NORD fg", Style(bold=True), width=11),
        Block.text("  MONO modifiers", Style(bold=True)),
    )
    return join_vertical(head, *rows, gap=0)


def _colors_vivid() -> Block:
    """PAINTED_PALETTE — the vivid truecolor ramp, swatch + name + hex (palette.py)."""
    with use_palette(PAINTED_PALETTE):
        # Names label the ramp in series order; the swatch Style AND the displayed
        # hex are both read straight off the real series (no hand-typed colors, and
        # it tracks the palette instead of KeyError-ing if the hexes ever change).
        names = ("green", "yellow", "red", "cyan", "blue", "magenta", "orange")
        rows = [
            join_horizontal(
                Block.text("█████  ", style),
                Block.text(name, Style(bold=True), width=9),
                Block.text(str(style.fg), Style(dim=True)),
                gap=0,
            )
            for name, style in zip(names, current_palette().series)
        ]
        return join_vertical(*rows, gap=0)


# --- Spacing ------------------------------------------------------------------


def _chrome_borders() -> Block:
    """BorderChars — corners are characters, not radii (core/borders.py)."""
    specs = (
        (ROUNDED, "cyan", "ROUNDED"),
        (HEAVY, "magenta", "HEAVY"),
        (DOUBLE, "green", "DOUBLE"),
        (LIGHT, "blue", "LIGHT"),
        (ASCII, "white", "ASCII"),
    )
    boxes = []
    for chars, color, label in specs:
        box = border(Block.empty(5, 1), chars=chars, style=Style(fg=color))
        caption = Block.text(label.center(box.width), Style(dim=True))
        boxes.append(join_vertical(box, caption, gap=0))
    return join_horizontal(*boxes, gap=3)


def _chrome_elevation() -> Block:
    """Style modifiers as elevation — reverse/bold/dim, painted's depth without shadow (core/cell.py)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        tiers = (
            (Style(reverse=True), "selected", "Style(reverse)", " api-gateway "),
            (Style(bold=True), "focused", "Style(bold)", "auth-svc"),
            (Style(), "resting", "Style()", "cache"),
            (Style(dim=True), "inactive", "Style(dim)", "worker-pool"),
        )
        lines = [
            join_horizontal(
                Block.text(sample, style, width=14),
                Block.text(tier, p.muted, width=10),
                Block.text(desc, p.muted),
            )
            for style, tier, desc, sample in tiers
        ]
        return join_vertical(*lines, gap=0)


def _spacing_cells() -> Block:
    """Cell grid — spacing is an exact integer cell count (core/compose.py)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        # Bar fill = the accent role's own color, so the grid stays
        # palette-faithful rather than a hardcoded hue.
        bar_bg = Style(bg=p.accent.fg)
        # The renderer's spacing scale: integer cell multiples (the mock's px
        # tokens divided by 4). Each bar below is literally this many cells wide.
        scale = (
            ("sp-1", 1),
            ("sp-2", 2),
            ("sp-3", 3),
            ("sp-4", 4),
            ("sp-5", 6),
            ("sp-6", 8),
            ("sp-7", 12),
            ("sp-8", 16),
        )
        rows = [
            join_horizontal(
                Block.text(name, p.accent, width=6),
                Block.empty(n, 1, bar_bg),  # an exact n-cell block
                Block.text(f" {n}×", p.muted),
            )
            for name, n in scale
        ]
        return join_vertical(*rows, gap=0)


# --- Type ---------------------------------------------------------------------


def _type_bigtext() -> Block:
    """render_big — FILLED solid blocks vs OUTLINE box-drawing (views/big_text.py)."""
    filled = render_big("show", Style(fg="cyan"), format=BigTextFormat.FILLED)
    outline = render_big("paint", Style(fg="yellow"), format=BigTextFormat.OUTLINE)
    return join_vertical(filled, Block.empty(1, 1), outline, gap=0)


def _type_modifiers() -> Block:
    """Style flags — the bare ANSI modifiers, then roles composed via .merge() (core/cell.py)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        # Row 1: the five bare modifiers, each word wearing exactly one flag.
        flags = [
            Block.text("bold", Style(bold=True)),
            Block.text("italic", Style(italic=True)),
            Block.text("underline", Style(underline=True)),
            Block.text("dim", Style(dim=True)),
            Block.text(" reverse ", Style(reverse=True)),
        ]
        # Row 2: Style.merge() composes a semantic palette role with a modifier.
        combos = [
            Block.text("accent + bold", p.accent.merge(Style(bold=True))),
            Block.text("error + bold", p.error.merge(Style(bold=True))),
            Block.text("success", p.success),
            Block.text("warning + italic", p.warning.merge(Style(italic=True))),
        ]
        return join_vertical(
            join_horizontal(*flags, gap=2),
            Block.empty(1, 1),
            join_horizontal(*combos, gap=2),
            gap=0,
        )


def _logo_wordmark() -> Block:
    """render_big — the painted brand wordmark as cell-buffer big text (views/big_text.py)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        wordmark = render_big("painted", p.accent, size=2, format=BigTextFormat.FILLED)
        tagline = Block.text("One library. Print to TUI. One dependency.", p.muted)
        return join_vertical(wordmark, Block.empty(1, 1), tagline, gap=0)


# --- Brand --------------------------------------------------------------------


def _glyphs_iconset() -> Block:
    """IconSet — the glyph vocabulary, with its ASCII fallback (icon_set.py)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        uni, asc = IconSet(), ASCII_ICONS
        rows = (
            ("spinner", " ".join(uni.spinner), " ".join(asc.spinner)),
            (
                "progress",
                uni.progress_fill * 5 + uni.progress_empty * 5,
                asc.progress_fill * 5 + asc.progress_empty * 5,
            ),
            ("sparkline", " ".join(uni.sparkline), " ".join(asc.sparkline)),
            (
                "tree",
                f"{uni.tree_branch}{uni.tree_last}{uni.tree_indent}",
                f"{asc.tree_branch}{asc.tree_last}{asc.tree_indent}",
            ),
            ("status", f"{uni.check} {uni.cross}", f"{asc.check} {asc.cross}"),
        )
        lines = [
            join_horizontal(
                Block.text(slot, p.muted, width=10),
                Block.text(glyphs, p.accent, width=26),
                Block.text("ascii  ", p.muted),
                Block.text(fallback, p.muted),
            )
            for slot, glyphs, fallback in rows
        ]
        return join_vertical(*lines, gap=0)


def _glyphs_box() -> Block:
    """Glyphs in functional context + use_icons() swap (icon_set.py)."""
    with use_palette(_SITE_PALETTE):
        p = current_palette()
        uni = IconSet()
        # Status glyphs as they appear *inside* rendered output, never
        # decoratively — each carries a semantic palette role.
        status = join_horizontal(
            Block.text(f"{uni.check} ", p.success),
            Block.text("connected", Style(), width=11),
            Block.text(f"{uni.cross} ", p.error),
            Block.text("failed", Style(), width=9),
            Block.text("> ", p.accent),
            Block.text("cursor", Style()),
        )
        # "Ambient & swappable" — the SAME progress bar, its fill glyph drawn
        # from the IconSet, rendered under the unicode set then ASCII_ICONS.
        caption = Block.text("use_icons() swaps the fill glyph — same bar:", p.muted)
        bar_uni = join_horizontal(
            Block.text("unicode  ", p.muted),
            progress_bar(ProgressState(value=0.62), 18),
        )
        with use_icons(ASCII_ICONS):
            bar_ascii = join_horizontal(
                Block.text("ascii    ", p.muted),
                progress_bar(ProgressState(value=0.62), 18),
            )
        return join_vertical(status, Block.empty(1, 1), caption, bar_uni, bar_ascii, gap=0)


# --- Registry -----------------------------------------------------------------
# Panel name (→ generated/panels/<name>.html, → outputgen PANELS data_attr) maps
# to its real Block. Mirrors the Design card ids 1:1 for traceability. The two
# cosmetic cards (colors-theme, type-scale) have no entry here by design.

COMP_TABLE = _comp_table()
COMP_BUTTONS = _comp_buttons()
COMP_CARD = _comp_card()
COMP_CHART = _comp_chart()
COMP_LISTVIEW = _comp_listview()
COMP_PROGRESS = _comp_progress()
COMP_SPARKLINE = _comp_sparkline()
COMP_SPINNER = _comp_spinner()
COMP_TREE = _comp_tree()

COLORS_PALETTE = _colors_palette()
COLORS_ANSI = _colors_ansi()
COLORS_PRESETS = _colors_presets()
COLORS_VIVID = _colors_vivid()

CHROME_BORDERS = _chrome_borders()
CHROME_ELEVATION = _chrome_elevation()
SPACING_CELLS = _spacing_cells()

TYPE_BIGTEXT = _type_bigtext()
TYPE_MODIFIERS = _type_modifiers()
LOGO_WORDMARK = _logo_wordmark()

GLYPHS_ICONSET = _glyphs_iconset()
GLYPHS_BOX = _glyphs_box()

CATALOG: dict[str, Block] = {
    "comp_table": COMP_TABLE,
    "comp_buttons": COMP_BUTTONS,
    "comp_card": COMP_CARD,
    "comp_chart": COMP_CHART,
    "comp_listview": COMP_LISTVIEW,
    "comp_progress": COMP_PROGRESS,
    "comp_sparkline": COMP_SPARKLINE,
    "comp_spinner": COMP_SPINNER,
    "comp_tree": COMP_TREE,
    "colors_palette": COLORS_PALETTE,
    "colors_ansi": COLORS_ANSI,
    "colors_presets": COLORS_PRESETS,
    "colors_vivid": COLORS_VIVID,
    "chrome_borders": CHROME_BORDERS,
    "chrome_elevation": CHROME_ELEVATION,
    "spacing_cells": SPACING_CELLS,
    "type_bigtext": TYPE_BIGTEXT,
    "type_modifiers": TYPE_MODIFIERS,
    "logo_wordmark": LOGO_WORDMARK,
    "glyphs_iconset": GLYPHS_ICONSET,
    "glyphs_box": GLYPHS_BOX,
}


def main() -> None:
    """Browse every specimen in the terminal — the same Blocks the site renders."""
    for name, block in CATALOG.items():
        print_block(Block.text(f"── {name} ", Style(dim=True)))
        print_block(block)
        print()


if __name__ == "__main__":
    main()
