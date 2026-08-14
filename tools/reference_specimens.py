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
            (
                "cpu",
                [12, 18, 25, 38, 52, 67, 71, 63, 58, 72, 88, 95, 90, 77, 64, 55, 61, 73, 82, 79],
                p.accent,
            ),
            (
                "net",
                [40, 42, 38, 55, 80, 76, 30, 28, 33, 90, 85, 44, 40, 38, 36, 60, 72, 50, 45, 41],
                p.success,
            ),
            (
                "mem",
                [55, 58, 61, 60, 63, 66, 70, 68, 72, 75, 79, 82, 80, 77, 74, 71, 69, 66, 63, 60],
                p.warning,
            ),
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
    filled = render_big("paint", Style(fg="cyan"), format=BigTextFormat.FILLED)
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
        tagline = Block.text("A semantic renderer for the terminal.", p.muted)
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


# --- Public capability coverage ----------------------------------------------
# This is the curated public grouping consumed by /reference. CATALOG above
# remains the one specimen registry; these declarations only say which existing
# PANELS evidence (if any) supports a capability-oriented reference entry.
#
# Keep the frozen capability names explicit. They are product concepts, not a
# taxonomy inferred from module paths or specimen filenames.
FROZEN_CAPABILITY_FAMILIES: dict[str, tuple[str, ...]] = {
    "rendering-model": (
        "cells",
        "spans",
        "lines",
        "blocks",
        "buffers",
        "composition",
        "borders",
        "width",
        "wrapping",
    ),
    "lenses-and-views": ("lenses", "views"),
    "data-and-controls": (
        "tables",
        "records",
        "progress",
        "meters",
        "spinners",
        "callouts",
        "inputs",
        "lists",
    ),
    "meaning-and-style": (
        "palette",
        "theme",
        "icons",
        "semantic marks",
        "vocabularies",
    ),
    "cli-disclosure": (
        "fidelity",
        "budgets",
        "formats",
        "help",
        "completion",
        "prompts",
    ),
    "interaction": (
        "refs",
        "links",
        "hit testing",
        "mouse",
        "cursor",
        "focus",
        "search",
        "layers",
    ),
    "delivery": ("static", "live", "stream-surface", "interactive"),
    "operations": (
        "diagnostics",
        "logging",
        "traceback rendering",
        "profiling",
        "testing",
    ),
    "publishing": ("document IR", "HTML publishing"),
}


REFERENCE_FAMILIES: tuple[dict[str, object], ...] = (
    {
        "id": "rendering-model",
        "title": "Build exact terminal output",
        "summary": "Start with immutable render values, then compose and fit rectangular output to the available cells.",
        "entries": (
            {
                "id": "render-values",
                "title": "Cell → Span → Line → Block",
                "summary": "The immutable values that carry characters, styles, runs, rows, and rectangles.",
                "covers": ("cells", "spans", "lines", "blocks"),
                "mode": "link",
                "href": "/guides/primitives-and-blocks/",
                "link_label": "Read the primitives guide",
            },
            {
                "id": "buffers",
                "title": "Buffers and bounded views",
                "summary": "Mutable cell destinations sit beneath frame assembly and interactive surfaces.",
                "covers": ("buffers",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/core/buffer.py",
                "link_label": "Inspect buffer.py",
            },
            {
                "id": "composition-and-borders",
                "title": "Compose on the cell grid",
                "summary": "Real blocks joined at integer cell gaps and wrapped with shipped border vocabularies.",
                "covers": ("composition", "borders"),
                "mode": "specimen",
                "specimen_ids": ("spacing_cells", "chrome_borders"),
            },
            {
                "id": "width",
                "title": "Fit the available width",
                "summary": "Width-aware composition and truncation preserve the rectangular contract.",
                "covers": ("width",),
                "mode": "link",
                "href": "/guides/composition-layout/",
                "link_label": "Read the composition guide",
            },
            {
                "id": "wrapping",
                "title": "Wrap block text deliberately",
                "summary": "Block text declares its wrapping policy and materializes display-width-aware rows.",
                "covers": ("wrapping",),
                "mode": "link",
                "href": "/guides/primitives-and-blocks/",
                "link_label": "Read the block text guide",
            },
        ),
    },
    {
        "id": "lenses-and-views",
        "title": "Turn data into views",
        "summary": "Lenses choose a representation from data, detail, and width; views provide reusable render shapes.",
        "entries": (
            {
                "id": "lenses-and-views",
                "title": "Lenses and reusable views",
                "summary": "Two genuine lenses render a numeric mapping and a hierarchy as terminal blocks.",
                "covers": ("lenses", "views"),
                "mode": "specimen",
                "specimen_ids": ("comp_chart", "comp_tree"),
            },
        ),
    },
    {
        "id": "data-and-controls",
        "title": "Present data and control state",
        "summary": "Use stateful view helpers for dense data, progress, selection, feedback, and text entry.",
        "entries": (
            {
                "id": "tables",
                "title": "Tables",
                "summary": "Columns, alignment, selection state, and visible rows rendered by table().",
                "covers": ("tables",),
                "mode": "specimen",
                "specimen_ids": ("comp_table",),
            },
            {
                "id": "records",
                "title": "Record views",
                "summary": "Timestamped record lines, timelines, and maps adapt detail and content to width.",
                "covers": ("records",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/views/record.py",
                "link_label": "Inspect record.py",
            },
            {
                "id": "progress",
                "title": "Progress",
                "summary": "Determinate progress rendered at several semantic palette roles.",
                "covers": ("progress",),
                "mode": "specimen",
                "specimen_ids": ("comp_progress",),
            },
            {
                "id": "meters",
                "title": "Meters",
                "summary": "Meter state and formatters add labeled measurements beyond a bare progress bar.",
                "covers": ("meters",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/views/components/_meter.py",
                "link_label": "Inspect the meter source",
            },
            {
                "id": "spinners",
                "title": "Spinner frame sets",
                "summary": "A static inventory of shipped frames and one selected frame; animation is not claimed here.",
                "covers": ("spinners",),
                "mode": "specimen",
                "specimen_ids": ("comp_spinner",),
            },
            {
                "id": "callouts-and-inputs",
                "title": "Callouts and text input",
                "summary": "Focused component APIs render message hierarchy and editable input state.",
                "covers": ("callouts", "inputs"),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/tree/main/src/painted/views/components",
                "link_label": "Browse component sources",
            },
            {
                "id": "lists",
                "title": "Selection lists",
                "summary": "ListState drives cursor position and selected-row styling.",
                "covers": ("lists",),
                "mode": "specimen",
                "specimen_ids": ("comp_listview",),
            },
        ),
    },
    {
        "id": "meaning-and-style",
        "title": "Keep meaning distinct from styling",
        "summary": "Semantic roles, themes, icons, marks, and vocabularies let hosts adapt presentation without changing meaning.",
        "entries": (
            {
                "id": "palette",
                "title": "Semantic palettes",
                "summary": "Five semantic roles and shipped palette presets rendered through their real Style values.",
                "covers": ("palette",),
                "mode": "specimen",
                "specimen_ids": ("colors_palette", "colors_presets"),
            },
            {
                "id": "theme",
                "title": "Themes",
                "summary": "Theme binds semantic roles and component styling; website surface tokens are not a terminal specimen.",
                "covers": ("theme",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/theme.py",
                "link_label": "Inspect theme.py",
            },
            {
                "id": "icons",
                "title": "Icon vocabularies",
                "summary": "The same component swaps between Unicode and ASCII icon sets.",
                "covers": ("icons",),
                "mode": "specimen",
                "specimen_ids": ("glyphs_iconset", "glyphs_box"),
            },
            {
                "id": "marks-and-vocabularies",
                "title": "Semantic marks and vocabularies",
                "summary": "Named marks preserve denotation while a vocabulary selects host-appropriate glyphs and styles.",
                "covers": ("semantic marks", "vocabularies"),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/vocabulary.py",
                "link_label": "Inspect vocabulary.py",
            },
        ),
    },
    {
        "id": "cli-disclosure",
        "title": "Control disclosure and CLI affordances",
        "summary": "Resolve detail, output budgets, formats, help, completion, and prompts around one rendering contract.",
        "entries": (
            {
                "id": "fidelity-and-budgets",
                "title": "Fidelity and budgets",
                "summary": "A declared disclosure ladder and a constrained rendering budget applied to genuine blocks.",
                "covers": ("fidelity", "budgets"),
                "mode": "specimen",
                "specimen_ids": ("disclosure_q", "disclosure_v", "disclosure_budget"),
            },
            {
                "id": "formats",
                "title": "Output formats",
                "summary": "The same monitor data emitted as terminal cells, plain text, and JSON.",
                "covers": ("formats",),
                "mode": "specimen",
                "specimen_ids": ("monitor_default", "monitor_plain", "monitor_json"),
            },
            {
                "id": "help",
                "title": "CLI help",
                "summary": "Help builds structured usage, arguments, and command sections from argparse metadata.",
                "covers": ("help",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/cli/help.py",
                "link_label": "Inspect the help source",
            },
            {
                "id": "completion",
                "title": "Completion",
                "summary": "Shell completion is documented as candidates, actions, and host integration.",
                "covers": ("completion",),
                "mode": "link",
                "href": "/docs/completion/",
                "link_label": "Open the completion document",
            },
            {
                "id": "prompts",
                "title": "Prompts",
                "summary": "Prompt cells and validation behavior are published as semantic documentation.",
                "covers": ("prompts",),
                "mode": "link",
                "href": "/docs/prompts/",
                "link_label": "Open the prompts document",
            },
        ),
    },
    {
        "id": "interaction",
        "title": "Carry denotation into interaction",
        "summary": "Refs survive rendering; hosts use them for links, hit testing, pointer input, focus, search, cursor, and layered routing.",
        "entries": (
            {
                "id": "refs-and-links",
                "title": "Refs become links in HTML",
                "summary": "Ref-tagged cells resolve through a declared RefScheme to genuine HTML anchors.",
                "covers": ("refs", "links"),
                "mode": "specimen",
                "specimen_ids": ("refs_anchors",),
            },
            {
                "id": "hit-testing",
                "title": "Hit testing",
                "summary": "Refs propagate through composition to coordinate probes and host frame resolution.",
                "covers": ("hit testing",),
                "mode": "link",
                "href": "/demos/patterns/hit_testing/",
                "link_label": "Open the hit-testing demo",
            },
            {
                "id": "mouse",
                "title": "Mouse input",
                "summary": "Mouse decoding turns terminal escape sequences into bounded button and coordinate events.",
                "covers": ("mouse",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/mouse.py",
                "link_label": "Inspect mouse.py",
            },
            {
                "id": "cursor",
                "title": "Cursor state",
                "summary": "A bounded cursor supports clamp and wrap semantics for navigable domains.",
                "covers": ("cursor",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/cursor.py",
                "link_label": "Inspect cursor.py",
            },
            {
                "id": "focus",
                "title": "Focus state",
                "summary": "Focus distinguishes navigation from widget-owned keyboard capture.",
                "covers": ("focus",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/focus.py",
                "link_label": "Inspect focus.py",
            },
            {
                "id": "search",
                "title": "Search state",
                "summary": "Immutable query and selection state composes with exact, prefix, and fuzzy filtering.",
                "covers": ("search",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/search.py",
                "link_label": "Inspect search.py",
            },
            {
                "id": "layers",
                "title": "Layer routing",
                "summary": "Layers route input top-down and paint modal state bottom-up.",
                "covers": ("layers",),
                "mode": "link",
                "href": "/guides/tui-core-surface-layers/",
                "link_label": "Read the Surface and layers guide",
            },
        ),
    },
    {
        "id": "delivery",
        "title": "Choose a delivery surface",
        "summary": "Publish once, update in place, consume a stream, or run an interactive Surface without pretending those lifecycles are static images.",
        "entries": (
            {
                "id": "static-delivery",
                "title": "Static delivery",
                "summary": "One generated Block published as a stable HTML fragment.",
                "covers": ("static",),
                "mode": "specimen",
                "specimen_ids": ("monitor_default",),
            },
            {
                "id": "live-delivery",
                "title": "Live delivery",
                "summary": "In-place updates are lifecycle behavior; the runnable demo and source show the host contract without faking motion.",
                "covers": ("live",),
                "mode": "link",
                "href": "/demos/patterns/live/",
                "link_label": "Open the live-delivery demo",
            },
            {
                "id": "stream-surface",
                "title": "StreamSurface",
                "summary": "A stream-driven Surface coordinates async values, rendering, and terminal ownership.",
                "covers": ("stream-surface",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/cli/stream_surface.py",
                "link_label": "Inspect stream_surface.py",
            },
            {
                "id": "interactive-delivery",
                "title": "Interactive Surface",
                "summary": "Keyboard, mouse, resize, frame delivery, and teardown belong to the interactive host lifecycle.",
                "covers": ("interactive",),
                "mode": "link",
                "href": "/learn/surface/",
                "link_label": "Learn the Surface rung",
            },
        ),
    },
    {
        "id": "operations",
        "title": "Inspect and verify runtime behavior",
        "summary": "Diagnostics, logs, tracebacks, profiling, and test hosts expose failures and performance without changing application meaning.",
        "entries": (
            {
                "id": "diagnostics-and-tracebacks",
                "title": "Diagnostics and traceback rendering",
                "summary": "Structured diagnostic and exception representations are published in the diagnostics document.",
                "covers": ("diagnostics", "traceback rendering"),
                "mode": "link",
                "href": "/docs/diagnostics/",
                "link_label": "Open the diagnostics document",
            },
            {
                "id": "logging",
                "title": "Logging",
                "summary": "Host-aware diagnostic plumbing keeps logs usable around terminal-owned output.",
                "covers": ("logging",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/diagnostics.py",
                "link_label": "Inspect diagnostics.py",
            },
            {
                "id": "profiling",
                "title": "View profiling",
                "summary": "The profiling helper measures view calls and reports the most expensive render paths.",
                "covers": ("profiling",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/views/_profile.py",
                "link_label": "Inspect the profiling helper",
            },
            {
                "id": "testing",
                "title": "Surface testing",
                "summary": "A test host captures frames and events without requiring a real interactive terminal.",
                "covers": ("testing",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/tui/testing.py",
                "link_label": "Inspect the testing host",
            },
        ),
    },
    {
        "id": "publishing",
        "title": "Publish semantic documents",
        "summary": "Document structure owns prose while Painted figures remain cell-derived islands in HTML.",
        "entries": (
            {
                "id": "document-ir",
                "title": "Document IR",
                "summary": "A semantic document tree models sections, prose, definitions, code, and Painted figures.",
                "covers": ("document IR",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/core/doc.py",
                "link_label": "Inspect the document IR",
            },
            {
                "id": "html-publishing",
                "title": "HTML publishing",
                "summary": "The publisher maps document structure to semantic HTML and delegates terminal figures to render_html.",
                "covers": ("HTML publishing",),
                "mode": "link",
                "href": "https://github.com/kgruel/painted/blob/main/src/painted/publish.py",
                "link_label": "Inspect the HTML publisher",
            },
        ),
    },
)


def main() -> None:
    """Browse every specimen in the terminal — the same Blocks the site renders."""
    for name, block in CATALOG.items():
        print_block(Block.text(f"── {name} ", Style(dim=True)))
        print_block(block)
        print()


if __name__ == "__main__":
    main()
