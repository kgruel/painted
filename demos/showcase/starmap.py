#!/usr/bin/env python3
"""Starmap — the night sky, every star a link.

The catalog is frozen data: sixty-four bright stars with real coordinates,
magnitudes, and spectral tints, plus the classic constellation figures. The
sky is a pure projection of that catalog around a drifting right-ascension
center — time comes from the harness, twinkle from a deterministic hash.
Every star glyph carries a ``star:<article>`` ref; with the scheme declared,
link deliveries turn the sky into a chart you can click — each star opens
its Wikipedia page (OSC 8 on a TTY, ``<a href>`` in HTML). The same render
serves the static chart, the animated pan, and ``--json`` (the raw catalog).

    uv run demos/showcase/starmap.py             # tonight's chart (winter hexagon)
    uv run demos/showcase/starmap.py --live      # pan the whole celestial sphere
    uv run demos/showcase/starmap.py -v          # + names on the bright stars
    uv run demos/showcase/starmap.py -vv         # + catalog table with resolved links
    uv run demos/showcase/starmap.py -q          # one-line census
    uv run demos/showcase/starmap.py --json      # the catalog as data
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

from painted import (
    Block,
    Fidelity,
    RefScheme,
    Style,
    join_horizontal,
    join_vertical,
    resolve_ref,
    truncate,
    use_refs,
)
from painted.capabilities import current_capabilities
from painted.palette import current_palette

from _harness import plate, showcase_main

# Declared in main() around the delivery, never at module scope (a module-scope
# use_refs would leak into every later render in this process). The render never
# requires it — an undeclared ref is inert, the sky still draws.
STAR_SCHEME = RefScheme("star", lambda value: f"https://en.wikipedia.org/wiki/{value}")


# --- The catalog: frozen data ---

# Approximate spectral-class tints (O/B blue through M orange-red).
_O = "#9bb0ff"
_B = "#aabfff"
_A = "#cad7ff"
_F = "#f8f7ff"
_G = "#fff4ea"
_K = "#ffd2a1"
_M = "#ff9e6b"


@dataclass(frozen=True)
class Star:
    name: str  # display name
    article: str  # Wikipedia article — the ref's value part
    ra: float  # right ascension, degrees (J2000, approximate)
    dec: float  # declination, degrees
    mag: float  # apparent magnitude
    color: str  # spectral tint, '#rrggbb'


def _star(name: str, article: str, ra_h: float, dec: float, mag: float, color: str) -> Star:
    return Star(name, article, ra_h * 15.0, dec, mag, color)


CATALOG: tuple[Star, ...] = (
    # Orion
    _star("Betelgeuse", "Betelgeuse", 5.919, 7.407, 0.50, _M),
    _star("Rigel", "Rigel", 5.242, -8.202, 0.13, _B),
    _star("Bellatrix", "Bellatrix", 5.418, 6.350, 1.64, _B),
    _star("Mintaka", "Mintaka", 5.533, -0.299, 2.23, _O),
    _star("Alnilam", "Alnilam", 5.604, -1.202, 1.69, _B),
    _star("Alnitak", "Alnitak", 5.679, -1.943, 1.77, _O),
    _star("Saiph", "Saiph", 5.796, -9.670, 2.09, _B),
    # Canis Major / Minor
    _star("Sirius", "Sirius", 6.752, -16.716, -1.46, _A),
    _star("Mirzam", "Beta_Canis_Majoris", 6.378, -17.956, 1.98, _B),
    _star("Adhara", "Adhara", 6.977, -28.972, 1.50, _B),
    _star("Wezen", "Wezen", 7.140, -26.393, 1.84, _F),
    _star("Procyon", "Procyon", 7.655, 5.225, 0.34, _F),
    _star("Gomeisa", "Gomeisa", 7.453, 8.289, 2.89, _B),
    # Gemini / Taurus / Auriga
    _star("Castor", "Castor_(star)", 7.577, 31.888, 1.58, _A),
    _star("Pollux", "Pollux_(star)", 7.755, 28.026, 1.14, _K),
    _star("Alhena", "Alhena", 6.629, 16.399, 1.93, _A),
    _star("Aldebaran", "Aldebaran", 4.599, 16.509, 0.85, _K),
    _star("Elnath", "Elnath", 5.438, 28.608, 1.65, _B),
    _star("Capella", "Capella", 5.278, 45.998, 0.08, _G),
    _star("Menkalinan", "Beta_Aurigae", 5.992, 44.947, 1.90, _A),
    # Southern winter sky
    _star("Canopus", "Canopus", 6.399, -52.696, -0.74, _F),
    _star("Arneb", "Alpha_Leporis", 5.545, -17.822, 2.58, _F),
    # Ursa Major (the Dipper) / Ursa Minor
    _star("Dubhe", "Dubhe", 11.062, 61.751, 1.79, _K),
    _star("Merak", "Merak", 11.031, 56.383, 2.37, _A),
    _star("Phecda", "Phecda", 11.897, 53.695, 2.44, _A),
    _star("Megrez", "Megrez", 12.257, 57.033, 3.31, _A),
    _star("Alioth", "Alioth", 12.900, 55.960, 1.77, _A),
    _star("Mizar", "Mizar", 13.399, 54.925, 2.04, _A),
    _star("Alkaid", "Eta_Ursae_Majoris", 13.792, 49.313, 1.86, _B),
    _star("Polaris", "Polaris", 2.530, 89.264, 1.98, _F),
    _star("Kochab", "Beta_Ursae_Minoris", 14.845, 74.155, 2.08, _K),
    # Cassiopeia (the W)
    _star("Caph", "Beta_Cassiopeiae", 0.153, 59.150, 2.27, _F),
    _star("Schedar", "Alpha_Cassiopeiae", 0.675, 56.537, 2.24, _K),
    _star("Gamma Cas", "Gamma_Cassiopeiae", 0.945, 60.717, 2.47, _B),
    _star("Ruchbah", "Delta_Cassiopeiae", 1.430, 60.235, 2.68, _A),
    _star("Segin", "Epsilon_Cassiopeiae", 1.907, 63.670, 3.38, _B),
    # Summer triangle and around
    _star("Vega", "Vega", 18.616, 38.784, 0.03, _A),
    _star("Deneb", "Deneb", 20.690, 45.280, 1.25, _A),
    _star("Sadr", "Gamma_Cygni", 20.371, 40.257, 2.23, _F),
    _star("Albireo", "Albireo", 19.512, 27.960, 3.18, _K),
    _star("Altair", "Altair", 19.846, 8.868, 0.77, _A),
    _star("Tarazed", "Gamma_Aquilae", 19.771, 10.613, 2.72, _K),
    _star("Rasalhague", "Alpha_Ophiuchi", 17.582, 12.560, 2.08, _A),
    # Spring sky
    _star("Arcturus", "Arcturus", 14.261, 19.182, -0.05, _K),
    _star("Izar", "Epsilon_Bootis", 14.750, 27.074, 2.37, _K),
    _star("Alphecca", "Alpha_Coronae_Borealis", 15.578, 26.715, 2.23, _A),
    _star("Spica", "Spica", 13.420, -11.161, 0.97, _B),
    _star("Regulus", "Regulus", 10.139, 11.967, 1.36, _B),
    _star("Denebola", "Denebola", 11.818, 14.572, 2.14, _A),
    _star("Algieba", "Gamma_Leonis", 10.333, 19.842, 2.08, _K),
    _star("Alphard", "Alphard", 9.460, -8.659, 1.98, _K),
    # Scorpius / the deep south
    _star("Antares", "Antares", 16.490, -26.432, 1.06, _M),
    _star("Shaula", "Lambda_Scorpii", 17.560, -37.104, 1.62, _B),
    _star("Rigil Kentaurus", "Alpha_Centauri", 14.660, -60.834, -0.27, _G),
    _star("Hadar", "Hadar", 14.064, -60.373, 0.61, _B),
    _star("Acrux", "Acrux", 12.443, -63.099, 0.76, _B),
    _star("Mimosa", "Beta_Crucis", 12.795, -59.689, 1.25, _B),
    _star("Gacrux", "Gacrux", 12.519, -57.113, 1.64, _M),
    _star("Imai", "Delta_Crucis", 12.252, -58.749, 2.79, _B),
    _star("Achernar", "Achernar", 1.629, -57.237, 0.46, _B),
    _star("Fomalhaut", "Fomalhaut", 22.961, -29.622, 1.16, _A),
    # Autumn sky
    _star("Markab", "Alpha_Pegasi", 23.079, 15.205, 2.48, _B),
    _star("Scheat", "Beta_Pegasi", 23.063, 28.083, 2.42, _M),
    _star("Algenib", "Gamma_Pegasi", 0.221, 15.184, 2.84, _B),
    _star("Alpheratz", "Alpheratz", 0.140, 29.091, 2.06, _B),
    _star("Mirach", "Beta_Andromedae", 1.162, 35.621, 2.05, _M),
    _star("Almach", "Gamma_Andromedae", 2.065, 42.330, 2.26, _K),
    _star("Mirfak", "Alpha_Persei", 3.405, 49.861, 1.79, _F),
    _star("Algol", "Algol", 3.136, 40.956, 2.12, _B),
)

# Constellation figures as edges between catalog names. Drawn dim — furniture,
# not data; the stars overwrite where they land.
FIGURES: tuple[tuple[str, str], ...] = (
    # Orion
    ("Betelgeuse", "Bellatrix"),
    ("Bellatrix", "Mintaka"),
    ("Mintaka", "Alnilam"),
    ("Alnilam", "Alnitak"),
    ("Alnitak", "Betelgeuse"),
    ("Alnitak", "Saiph"),
    ("Saiph", "Rigel"),
    ("Rigel", "Mintaka"),
    # The Dipper
    ("Dubhe", "Merak"),
    ("Merak", "Phecda"),
    ("Phecda", "Megrez"),
    ("Megrez", "Dubhe"),
    ("Megrez", "Alioth"),
    ("Alioth", "Mizar"),
    ("Mizar", "Alkaid"),
    # Cassiopeia's W
    ("Caph", "Schedar"),
    ("Schedar", "Gamma Cas"),
    ("Gamma Cas", "Ruchbah"),
    ("Ruchbah", "Segin"),
    # Summer triangle (asterism) + Cygnus spine
    ("Vega", "Deneb"),
    ("Deneb", "Altair"),
    ("Altair", "Vega"),
    ("Deneb", "Sadr"),
    ("Sadr", "Albireo"),
    # Canis Major
    ("Sirius", "Mirzam"),
    ("Sirius", "Adhara"),
    ("Adhara", "Wezen"),
    # Gemini axis
    ("Castor", "Pollux"),
    ("Pollux", "Alhena"),
    # Crux
    ("Acrux", "Gacrux"),
    ("Mimosa", "Imai"),
    # The Pointers
    ("Rigil Kentaurus", "Hadar"),
    # Great Square of Pegasus
    ("Markab", "Scheat"),
    ("Scheat", "Alpheratz"),
    ("Alpheratz", "Algenib"),
    ("Algenib", "Markab"),
    # Andromeda chain / Perseus
    ("Alpheratz", "Mirach"),
    ("Mirach", "Almach"),
    ("Mirfak", "Algol"),
    # Scorpius axis
    ("Antares", "Shaula"),
)


@dataclass(frozen=True)
class Sky:
    frame: int
    ra_center: float  # degrees
    dec_center: float  # degrees
    stars: tuple[Star, ...]


# --- Fetch: snapshot and stream ---

_DEFAULT_RA = 96.0  # 6.4h — the winter hexagon
_DEFAULT_DEC = 4.0
_FPS = 12
_DRIFT = 0.25  # degrees of RA per frame, westward pan
_MAX_FRAMES = 1440  # one full circuit of the sphere (~2 min)


def _sky(frame: int) -> Sky:
    return Sky(
        frame=frame,
        ra_center=(_DEFAULT_RA + frame * _DRIFT) % 360.0,
        dec_center=_DEFAULT_DEC,
        stars=CATALOG,
    )


def _fetch() -> Sky:
    return _sky(0)


async def _fetch_stream() -> AsyncIterator[Sky]:
    budget = 1.0 / _FPS
    for frame in range(_MAX_FRAMES):
        yield _sky(frame)
        await asyncio.sleep(budget)


# --- Projection and plotting ---

_RA_SPAN = 110.0  # degrees of RA across the chart
_ROWS = 26
_LABEL_MAG = 1.3  # stars at least this bright get names at DETAILED+

# Glyph rungs, faint to bright; magnitude picks the rung, twinkle nudges it.
_RUNGS = ("·", "*", "✧", "✦")


def _rung(mag: float) -> int:
    if mag <= 0.2:
        return 3
    if mag <= 1.2:
        return 2
    if mag <= 2.2:
        return 1
    return 0


def _twinkle(name: str, frame: int) -> int:
    """Deterministic scintillation: a hash, never random() (gate-stable)."""
    b = hashlib.md5(f"{name}:{frame // 4}".encode()).digest()[0]
    if b < 40:
        return -1
    if b >= 216:
        return 1
    return 0


_CellsGrid = dict[tuple[int, int], tuple[str, Style, str | None]]


def _grid_size(width: int | None) -> tuple[int, int]:
    w = 96 if width is None else max(40, min(width - 4, 96))
    return w, _ROWS


def _project(sky: Sky, w: int, h: int, ra: float, dec: float) -> tuple[int, int]:
    """Chart projection: east to the left, north up, cell aspect corrected."""
    deg_col = _RA_SPAN / w
    deg_row = 2.0 * deg_col  # terminal cells are ~2x taller than wide
    dx = ((ra - sky.ra_center + 180.0) % 360.0) - 180.0
    x = round(w / 2 - dx / deg_col)
    y = round(h / 2 - (dec - sky.dec_center) / deg_row)
    return x, y


def _plot(sky: Sky, w: int, h: int, labels: bool) -> tuple[_CellsGrid, list[Star]]:
    """Project the catalog into a sparse cell grid. Pure function of the Sky."""
    p = current_palette()
    cells: _CellsGrid = {}
    by_name = {s.name: s for s in sky.stars}

    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < w and 0 <= y < h

    # Figures first: dim furniture the stars may overwrite.
    for a_name, b_name in FIGURES:
        a, b = by_name[a_name], by_name[b_name]
        x0, y0 = _project(sky, w, h, a.ra, a.dec)
        x1, y1 = _project(sky, w, h, b.ra, b.dec)
        # A figure edge never spans the seam of the projection; a wrapped
        # endpoint lands far off-grid, and sampling would smear the line
        # across the whole chart. Skip those edges.
        if abs(x1 - x0) > w:
            continue
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(1, steps):
            xi = round(x0 + (x1 - x0) * i / steps)
            yi = round(y0 + (y1 - y0) * i / steps)
            if in_bounds(xi, yi):
                cells.setdefault((xi, yi), ("·", p.muted.merge(Style(dim=True)), None))

    # Stars, faintest first so the bright ones win contested cells.
    visible: list[Star] = []
    for star in sorted(sky.stars, key=lambda s: s.mag, reverse=True):
        x, y = _project(sky, w, h, star.ra, star.dec)
        if not in_bounds(x, y):
            continue
        visible.append(star)
        rung = _rung(star.mag)
        if star.mag > 0.5:
            rung = min(3, max(0, rung + _twinkle(star.name, sky.frame)))
        style = Style(fg=star.color, bold=rung == 3)
        cells[(x, y)] = (_RUNGS[rung], style, f"star:{star.article}")

    # Names beside the brightest stars — written only into empty cells, whole
    # or not at all, so a label never chews into a neighboring star or figure.
    # Right of the star first, left as the fallback (figures often crowd one side).
    if labels:
        label_style = p.muted
        for star in visible:
            if star.mag > _LABEL_MAG:
                continue
            x, y = _project(sky, w, h, star.ra, star.dec)
            for text, x0 in ((f" {star.name}", x + 1), (f"{star.name} ", x - len(star.name) - 1)):
                targets = [(x0 + i, y) for i in range(len(text))]
                if all(in_bounds(tx, ty) and (tx, ty) not in cells for tx, ty in targets):
                    for (tx, ty), ch in zip(targets, text):
                        cells[(tx, ty)] = (ch, label_style, f"star:{star.article}")
                    break

    visible.sort(key=lambda s: s.mag)
    return cells, visible


_PLAIN = Style()


def _chart(cells: _CellsGrid, w: int, h: int) -> Block:
    """The sparse grid as a Block: consecutive cells with one (style, ref)
    become one run — refs ride Block.text and survive the joins."""
    rows: list[Block] = []
    for y in range(h):
        segments: list[Block] = []
        run: list[str] = []
        run_key: tuple[Style, str | None] = (_PLAIN, None)
        for x in range(w):
            ch, style, ref = cells.get((x, y), (" ", _PLAIN, None))
            key = (style, ref)
            if key != run_key and run:
                segments.append(Block.text("".join(run), run_key[0], ref=run_key[1]))
                run = []
            run_key = key
            run.append(ch)
        segments.append(Block.text("".join(run), run_key[0], ref=run_key[1]))
        rows.append(join_horizontal(*segments))
    return join_vertical(*rows)


# --- Render helpers ---


def _census(sky: Sky, visible: list[Star]) -> Block:
    p = current_palette()
    brightest = visible[0].name if visible else "none"
    return join_horizontal(
        Block.text("starmap", p.accent.merge(Style(bold=True))),
        Block.text(
            f"  RA {sky.ra_center / 15.0:>4.1f}h  dec {sky.dec_center:+.0f}°"
            f"  ·  {len(visible):>2} stars  ·  brightest {brightest}",
            Style(dim=True),
        ),
    )


def _legend() -> Block:
    p = current_palette()
    return join_horizontal(
        Block.text("mag  ", Style(dim=True)),
        Block.text("✦", Style(fg=_A, bold=True)),
        Block.text(" <0.2  ", Style(dim=True)),
        Block.text("✧", Style(fg=_A)),
        Block.text(" <1.2  ", Style(dim=True)),
        Block.text("*", Style(fg=_A)),
        Block.text(" <2.2  ", Style(dim=True)),
        Block.text("·", Style(fg=_A)),
        Block.text(" faint   ", Style(dim=True)),
        Block.text("star:<article>", p.accent),
        Block.text(" → wikipedia", Style(dim=True)),
    )


def _links_live() -> bool:
    """Honesty for the gesture hint: advertise ⌘-click only when this delivery
    actually emits links — link-capable output AND a declared scheme that
    resolves."""
    return current_capabilities().link and resolve_ref("star:Sirius") is not None


def _window(
    sky: Sky, width: int | None, *, labels: bool, legend: bool, hint: bool
) -> tuple[Block, list[Star]]:
    w, h = _grid_size(width)
    cells, visible = _plot(sky, w, h, labels)
    rows = [_chart(cells, w, h), truncate(_census(sky, visible), w)]
    if legend:
        rows.append(truncate(_legend(), w))
    if hint:
        tip = Block.text("⌘-click a star → wikipedia", Style(dim=True))
        pad_w = max(0, w - tip.width)
        rows.append(join_horizontal(Block.text(" " * pad_w, _PLAIN), tip))
    framed = plate(*rows, title="the night sky")
    return framed, visible


def _catalog_table(visible: list[Star], width: int | None) -> Block:
    """The brightest of what's in view, each ref through resolve_ref — URIs
    when the scheme is declared, inert (and honestly so) when it isn't."""
    p = current_palette()
    rows: list[Block] = []
    shown = visible[:12]
    for star in shown:
        uri = resolve_ref(f"star:{star.article}")
        target = Block.text(uri, p.accent) if uri else Block.text("inert — no scheme declared", p.muted)
        rows.append(
            join_horizontal(
                Block.text(f"  {star.name:<16}", Style(fg=star.color)),
                Block.text(f"{star.mag:>5.2f}  ", Style(dim=True)),
                Block.text(f"{star.ra / 15.0:>5.2f}h {star.dec:>+6.1f}°  ", Style(dim=True)),
                target,
            )
        )
    if len(visible) > len(shown):
        rows.append(Block.text(f"  … and {len(visible) - len(shown)} fainter", Style(dim=True)))
    block = join_vertical(*rows) if rows else Block.text("  (empty sky)", Style(dim=True))
    return truncate(block, width) if width is not None else block


# --- Zoom renderers ---


def _render_minimal(sky: Sky, width: int | None) -> Block:
    w, h = _grid_size(width)
    _cells, visible = _plot(sky, w, h, labels=False)
    block = _census(sky, visible)
    return truncate(block, width) if width is not None else block


def _render_summary(sky: Sky, width: int | None, hint: bool) -> Block:
    framed, _visible = _window(sky, width, labels=False, legend=False, hint=hint)
    return truncate(framed, width) if width is not None else framed


def _render_detailed(sky: Sky, width: int | None, hint: bool) -> Block:
    framed, _visible = _window(sky, width, labels=True, legend=True, hint=hint)
    return truncate(framed, width) if width is not None else framed


def _render_full(sky: Sky, width: int | None, hint: bool) -> Block:
    framed, visible = _window(sky, width, labels=True, legend=True, hint=hint)
    block = join_vertical(
        framed,
        Block.text("", _PLAIN),
        Block.text("  in view, by brightness", Style(dim=True)),
        Block.text("", _PLAIN),
        _catalog_table(visible, width),
    )
    return truncate(block, width) if width is not None else block


def _render(sky: Sky, fidelity: Fidelity, width: int | None) -> Block:
    hint = _links_live()
    depth = fidelity.depth
    if depth >= 3:
        return _render_full(sky, width, hint)
    if depth >= 2:
        return _render_detailed(sky, width, hint)
    if depth >= 1:
        return _render_summary(sky, width, hint)
    return _render_minimal(sky, width)


# --- Entry point ---


def main() -> int:
    # The scheme stays here, not in the harness: resolving a star id to a URL is
    # this demo's whole lesson, and a harness that owned it would be teaching it.
    with use_refs(STAR_SCHEME):
        return showcase_main(
            doc=__doc__,
            file=__file__,
            renderer=_render,
            fetch=lambda ns: _fetch(),
            fetch_stream=lambda ns: _fetch_stream(),
        )


if __name__ == "__main__":
    sys.exit(main())
