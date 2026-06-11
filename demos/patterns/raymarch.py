#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""SDF raymarcher — donut generalized into a renderer.

The curriculum's summit re-derives its rung zero: donut.c's hardcoded torus
projection is replaced by a general renderer where the torus is just one
signed-distance field among others. The new concept is the *scene as an
expression tree*: frozen SDF primitives (sphere, torus, plane) composed by
operators (union, smooth-union), evaluated by one pure function — painted's
own ethos mirrored in the content. A sphere threads the torus like a chain
link, smooth-blending where they pass; an orbiting camera changes every ray
every frame, so this is also the lane's true whole-frame-churn pole.

Fidelity is a budget decision, demonstrated: live frames render the full
lit scene — half-block cells, two color samples each, soft shadows — at
30fps, every frame near the writer's style-run worst case (hundreds of
distinct truecolor pairs, measured by the delivery gauge). The stream's
final yield bumps `quality`, and the settled frame — like any static pose
— buys the one thing a live budget can't: a 2x2 supersampled, anti-aliased
portrait. Same scene, same pure render; only the state asked for more. A
pipe receives the pose carried honestly by the classic luminance ramp
(.,-~:;=!*#$@) alone.

    uv run demos/patterns/raymarch.py                # one portrait pose
    uv run demos/patterns/raymarch.py --live         # orbit, then settle
    uv run demos/patterns/raymarch.py --frame 200 -v # later pose + legend
    uv run demos/patterns/raymarch.py -vv            # bordered, march stats
    uv run demos/patterns/raymarch.py -q             # one-line pose census
    uv run demos/patterns/raymarch.py --json         # the pose as data
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import lru_cache

from painted import (
    Block,
    CliContext,
    Line,
    Span,
    Style,
    Zoom,
    border,
    join_horizontal,
    join_vertical,
    run_cli,
    truncate,
    ROUNDED,
)
from painted.cli import HelpArg
from painted.palette import current_palette


# --- Data: the pose is time plus an ambition ---


@dataclass(frozen=True)
class Shot:
    frame: int
    quality: int = 0  # 0 = live (one ray per half-pixel), 1 = settled anti-aliased portrait


DEFAULT_FRAME = 110


def _fetch(frame: int = DEFAULT_FRAME) -> Shot:
    return Shot(frame=frame, quality=1)  # a static pose is always the portrait


_FPS = 30
_MAX_FRAMES = 900  # ~30s of orbit, then the scene settles into its portrait


async def _fetch_stream(start: int = 0, frames: int = _MAX_FRAMES) -> AsyncIterator[Shot]:
    """Orbit at the budget, then settle: the last yield asks for quality."""
    budget = 1.0 / _FPS
    last = start
    for frame in range(start, start + frames):
        last = frame
        yield Shot(frame=frame)
        await asyncio.sleep(budget)
    yield Shot(frame=last, quality=1)


# --- The scene: frozen SDF primitives composed by operators ---


@dataclass(frozen=True)
class Sphere:
    cx: float
    cy: float
    cz: float
    r: float


@dataclass(frozen=True)
class Torus:
    ring: float  # ring radius (center of tube to axis)
    tube: float  # tube radius


@dataclass(frozen=True)
class Plane:
    y: float


@dataclass(frozen=True)
class Union:
    a: Node
    b: Node


@dataclass(frozen=True)
class SmoothUnion:
    a: Node
    b: Node
    k: float


Node = Sphere | Torus | Plane | Union | SmoothUnion


def _sdf(node: Node, x: float, y: float, z: float) -> float:
    """The reference evaluator — the readable spec of every node's distance."""
    if isinstance(node, Sphere):
        return math.sqrt((x - node.cx) ** 2 + (y - node.cy) ** 2 + (z - node.cz) ** 2) - node.r
    if isinstance(node, Torus):
        q = math.sqrt(x * x + z * z) - node.ring
        return math.sqrt(q * q + y * y) - node.tube
    if isinstance(node, Plane):
        return y - node.y
    if isinstance(node, Union):
        return min(_sdf(node.a, x, y, z), _sdf(node.b, x, y, z))
    a, b = _sdf(node.a, x, y, z), _sdf(node.b, x, y, z)
    h = max(node.k - abs(a - b), 0.0) / node.k
    return min(a, b) - h * h * node.k * 0.25


SdfFn = Callable[[float, float, float], float]


def _compile(node: Node) -> SdfFn:
    """Tree → closure. Same distances as _sdf (law-pinned), march-loop fast."""
    if isinstance(node, Sphere):
        cx, cy, cz, r = node.cx, node.cy, node.cz, node.r

        def d_sphere(x: float, y: float, z: float) -> float:
            return math.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) - r

        return d_sphere
    if isinstance(node, Torus):
        ring, tube = node.ring, node.tube

        def d_torus(x: float, y: float, z: float) -> float:
            q = math.sqrt(x * x + z * z) - ring
            return math.sqrt(q * q + y * y) - tube

        return d_torus
    if isinstance(node, Plane):
        py = node.y

        def d_plane(x: float, y: float, z: float) -> float:
            return y - py

        return d_plane
    if isinstance(node, Union):
        da, db = _compile(node.a), _compile(node.b)

        def d_union(x: float, y: float, z: float) -> float:
            a = da(x, y, z)
            b = db(x, y, z)
            return a if a < b else b

        return d_union
    da, db, k = _compile(node.a), _compile(node.b), node.k

    def d_smooth(x: float, y: float, z: float) -> float:
        a = da(x, y, z)
        b = db(x, y, z)
        h = k - (a - b if a > b else b - a)
        if h < 0.0:
            return a if a < b else b
        h /= k
        return (a if a < b else b) - h * h * k * 0.25

    return d_smooth


_TORUS = Torus(ring=1.5, tube=0.5)
_FLOOR = Plane(y=-1.6)
_BLEND_K = 0.45
_SPHERE_R = 0.42
_SPHERE_STEP = 0.045  # radians of thread orbit per frame
_CAM_STEP = 0.022  # radians of camera orbit per frame


def _sphere_at(frame: int) -> Sphere:
    """The threading orbit: a circle through the hole, chain-link style."""
    th = frame * _SPHERE_STEP
    ring = _TORUS.ring
    return Sphere(cx=ring + ring * math.cos(th), cy=ring * math.sin(th), cz=0.0, r=_SPHERE_R)


def _scene(frame: int) -> Node:
    """The whole scene for one pose — pure data, composed."""
    return Union(_FLOOR, SmoothUnion(_TORUS, _sphere_at(frame), _BLEND_K))


# --- The march: sphere tracing, normals, light ---

_W, _H = 64, 22
_FOV_Y = 2 * _H / _W  # character cells are ~2:1; the screen plane un-squashes
_FOCAL = 1.5  # narrows the frustum so the subject fills the frame
_EPS = 0.012
_FAR = 14.0
_MAX_STEPS = 48
_LIGHT = (0.487, 0.779, -0.395)  # normalized key light direction


def _camera(frame: int) -> tuple[tuple[float, float, float], ...]:
    """Eye + orthonormal basis (right, up, forward), orbiting the origin."""
    th = frame * _CAM_STEP
    eye = (5.0 * math.sin(th), 1.9 + 0.7 * math.sin(th * 0.43), 5.0 * math.cos(th))
    fwd = (-eye[0], -eye[1], -eye[2])
    fl = math.sqrt(sum(c * c for c in fwd))
    fwd = (fwd[0] / fl, fwd[1] / fl, fwd[2] / fl)
    right = (fwd[2], 0.0, -fwd[0])  # cross(fwd, world-up), y-up world
    rl = math.sqrt(right[0] ** 2 + right[2] ** 2)
    right = (right[0] / rl, 0.0, right[2] / rl)
    up = (
        fwd[1] * right[2] - fwd[2] * right[1],
        fwd[2] * right[0] - fwd[0] * right[2],
        fwd[0] * right[1] - fwd[1] * right[0],
    )
    return eye, right, up, fwd


def _march(
    sdf: SdfFn,
    ox: float,
    oy: float,
    oz: float,
    dx: float,
    dy: float,
    dz: float,
) -> tuple[float, int]:
    """Sphere-trace one ray: (hit distance or -1, steps spent)."""
    t = 0.0
    for step in range(_MAX_STEPS):
        d = sdf(ox + t * dx, oy + t * dy, oz + t * dz)
        if d < _EPS:
            return t, step + 1
        t += d
        if t > _FAR:
            return -1.0, step + 1
    return -1.0, _MAX_STEPS


def _normal(sdf: SdfFn, x: float, y: float, z: float) -> tuple[float, float, float]:
    h = _EPS * 0.5
    nx = sdf(x + h, y, z) - sdf(x - h, y, z)
    ny = sdf(x, y + h, z) - sdf(x, y - h, z)
    nz = sdf(x, y, z + h) - sdf(x, y, z - h)
    nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / nl, ny / nl, nz / nl


def _soft_shadow(sdf: SdfFn, x: float, y: float, z: float) -> float:
    """March toward the light; nearby geometry darkens in proportion."""
    lx, ly, lz = _LIGHT
    t = _EPS * 8
    res = 1.0
    for _ in range(24):
        d = sdf(x + t * lx, y + t * ly, z + t * lz)
        if d < _EPS:
            return 0.0
        res = min(res, 8.0 * d / t)
        t += d
        if t > _FAR:
            break
    return res


# --- Tracing a frame: luminance grid (live) or lit-color grid (portrait) ---


@lru_cache(maxsize=4)
def _trace(shot: Shot) -> tuple[list[list[int]], int, int]:
    """Cell-res luminance for one pose: (-1 empty / 0-11 ramp), hits, steps."""
    sdf = _compile(_scene(shot.frame))
    (ex, ey, ez), right, up, fwd = _camera(shot.frame)
    grid: list[list[int]] = []
    hits = steps_spent = 0
    for py in range(_H):
        v = (1.0 - 2.0 * (py + 0.5) / _H) * _FOV_Y
        row: list[int] = []
        for px in range(_W):
            u = 2.0 * (px + 0.5) / _W - 1.0
            dx = fwd[0] * _FOCAL + u * right[0] + v * up[0]
            dy = fwd[1] * _FOCAL + u * right[1] + v * up[1]
            dz = fwd[2] * _FOCAL + u * right[2] + v * up[2]
            dl = math.sqrt(dx * dx + dy * dy + dz * dz)
            t, steps = _march(sdf, ex, ey, ez, dx / dl, dy / dl, dz / dl)
            steps_spent += steps
            if t < 0:
                row.append(-1)
                continue
            hits += 1
            hx, hy, hz = ex + t * dx / dl, ey + t * dy / dl, ez + t * dz / dl
            nx, ny, nz = _normal(sdf, hx, hy, hz)
            lum = max(0.0, nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2])
            # The ramp is the live view's color space: the floor carries its
            # checker dimly so the subject owns the bright end, same materials
            # as the portrait.
            if _sdf(_FLOOR, hx, hy, hz) < _EPS * 2:
                lum *= 0.40 if (math.floor(hx) + math.floor(hz)) % 2 == 0 else 0.30
            row.append(min(11, int((0.08 + 0.92 * lum) * 11.99)))
        grid.append(row)
    return grid, hits, steps_spent


# Portrait materials and sky, low to high: rgb tuples lerped by the lighting.
_MAT_TORUS = (232, 93, 74)
_MAT_SPHERE = (74, 163, 232)
_MAT_FLOOR_A = (64, 64, 72)
_MAT_FLOOR_B = (44, 44, 52)
_SKY_TOP = (24, 26, 48)
_SKY_HORIZON = (92, 70, 110)


def _material(frame: int, x: float, y: float, z: float) -> tuple[int, int, int]:
    """Nearest leaf wins; the floor carries a checker so the orbit reads."""
    dt = _sdf(_TORUS, x, y, z)
    ds = _sdf(_sphere_at(frame), x, y, z)
    df = _sdf(_FLOOR, x, y, z)
    if df < dt and df < ds:
        return _MAT_FLOOR_A if (math.floor(x) + math.floor(z)) % 2 == 0 else _MAT_FLOOR_B
    if ds < dt:
        return _MAT_SPHERE
    return _MAT_TORUS


def _shade_rgb(lum: float, mat: tuple[int, int, int]) -> tuple[int, int, int]:
    g = math.sqrt(min(1.0, lum))  # cheap gamma so shadow falloff reads
    return (int(mat[0] * g), int(mat[1] * g), int(mat[2] * g))


def _sky(v: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, 1.0 - (v + _FOV_Y) / (2 * _FOV_Y)))
    return tuple(
        int(_SKY_TOP[c] + (_SKY_HORIZON[c] - _SKY_TOP[c]) * t) for c in range(3)
    )  # type: ignore[return-value]


def _ss(shot: Shot) -> int:
    """Samples per axis per half-pixel: the settle buys anti-aliasing."""
    return 2 if shot.quality >= 1 else 1


@lru_cache(maxsize=2)
def _trace_portrait(shot: Shot) -> tuple[list[list[tuple[int, int, int]]], int, int, int]:
    """Lit color, two half-pixels per cell: (2*_H rgb rows, hits, steps, rays).

    Soft-shadowed and skied; at quality 1 each half-pixel is a box-averaged
    2x2 supersample — the anti-aliased portrait a live budget can't afford
    but a single settled frame can.
    """
    sdf = _compile(_scene(shot.frame))
    (ex, ey, ez), right, up, fwd = _camera(shot.frame)
    ss = _ss(shot)
    hi_w, hi_h = _W * ss, 2 * _H * ss
    hits = steps_spent = 0
    hi: list[list[tuple[int, int, int]]] = []
    for py in range(hi_h):
        v = (1.0 - 2.0 * (py + 0.5) / hi_h) * _FOV_Y
        row: list[tuple[int, int, int]] = []
        for px in range(hi_w):
            u = 2.0 * (px + 0.5) / hi_w - 1.0
            dx = fwd[0] * _FOCAL + u * right[0] + v * up[0]
            dy = fwd[1] * _FOCAL + u * right[1] + v * up[1]
            dz = fwd[2] * _FOCAL + u * right[2] + v * up[2]
            dl = math.sqrt(dx * dx + dy * dy + dz * dz)
            t, steps = _march(sdf, ex, ey, ez, dx / dl, dy / dl, dz / dl)
            steps_spent += steps
            if t < 0:
                row.append(_sky(v))
                continue
            hits += 1
            hx, hy, hz = ex + t * dx / dl, ey + t * dy / dl, ez + t * dz / dl
            nx, ny, nz = _normal(sdf, hx, hy, hz)
            diff = max(0.0, nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2])
            shadow = _soft_shadow(sdf, hx + nx * _EPS * 4, hy + ny * _EPS * 4, hz + nz * _EPS * 4)
            lum = 0.14 + 0.86 * diff * shadow
            row.append(_shade_rgb(lum, _material(shot.frame, hx, hy, hz)))
        hi.append(row)
    if ss == 1:
        return hi, hits, steps_spent, hi_w * hi_h
    rows = [
        [
            tuple(
                sum(hi[py * ss + j][px * ss + i][c] for j in range(ss) for i in range(ss))
                // (ss * ss)
                for c in range(3)
            )
            for px in range(_W)
        ]
        for py in range(2 * _H)
    ]
    return rows, hits, steps_spent, hi_w * hi_h  # type: ignore[return-value]


# --- Render helpers ---

_RAMP = ".,-~:;=!*#$@"  # donut's ramp — the callback is the point


def _tier(idx: int) -> Style:
    """Ramp index → style: shading carried twice, by glyph and by weight."""
    accent = current_palette().accent
    if idx >= 8:
        return accent.merge(Style(bold=True))
    if idx <= 3:
        return accent.merge(Style(dim=True))
    return accent


def _grid_live(shot: Shot, width: int) -> Block:
    """The luminance grid as styled rows, run-coalesced like donut's."""
    grid, _hits, _steps = _trace(shot)
    rows: list[Block] = []
    for shade_row in grid:
        spans: list[Span] = []
        run, run_idx = [], shade_row[0]
        for idx in (*shade_row, None):  # sentinel flushes the last run
            if idx is not None and (idx == run_idx or (idx < 0 and run_idx < 0)):
                run.append(" " if idx < 0 else _RAMP[idx])
                continue
            if run:
                spans.append(Span("".join(run), Style() if run_idx < 0 else _tier(run_idx)))
            if idx is not None:
                run, run_idx = [" " if idx < 0 else _RAMP[idx]], idx
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _grid_portrait(shot: Shot, width: int) -> Block:
    """Half-block truecolor: every cell two lit pixels, fg over bg."""
    rgb, _hits, _steps, _rays = _trace_portrait(shot)
    rows: list[Block] = []
    for py in range(_H):
        top, bot = rgb[2 * py], rgb[2 * py + 1]
        spans = [
            Span("▀", Style(fg=f"#{t[0]:02x}{t[1]:02x}{t[2]:02x}", bg=f"#{b[0]:02x}{b[1]:02x}{b[2]:02x}"))
            for t, b in zip(top, bot)
        ]
        rows.append(Line(spans=tuple(spans)).to_block(min(_W, width)))
    return join_vertical(*rows)


def _grid(ctx: CliContext, shot: Shot, width: int) -> Block:
    """Capability picks the carrier: color terminals get the lit portrait
    (anti-aliased when the shot settles), pipes get the luminance ramp."""
    if ctx.use_ansi:
        return _grid_portrait(shot, width)
    return _grid_live(shot, width)


def _census(shot: Shot) -> Block:
    p = current_palette()
    th = shot.frame * _CAM_STEP
    tag = "portrait" if shot.quality >= 1 else "orbit"
    return join_horizontal(
        Block.text("raymarch", p.accent.merge(Style(bold=True))),
        Block.text(f"  frame {shot.frame:>3}  cam {th:5.2f}  {tag}", Style(dim=True)),
    )


def _legend(ctx: CliContext) -> Block:
    spans = [Span("shade ", Style(dim=True))]
    spans += [Span(ch, _tier(i)) for i, ch in enumerate(_RAMP)]
    if ctx.use_ansi:
        spans += [Span("   ", Style())]
        for name, mat in (("torus", _MAT_TORUS), ("sphere", _MAT_SPHERE), ("floor", _MAT_FLOOR_A)):
            spans += [
                Span("█", Style(fg=f"#{mat[0]:02x}{mat[1]:02x}{mat[2]:02x}")),
                Span(f"{name} ", Style(dim=True)),
            ]
    return Line(spans=tuple(spans)).to_block(58)


def _window(ctx: CliContext, shot: Shot, width: int, *extra: Block) -> Block:
    """The dressed viewing frame: scene, census, and any extras.

    Inner width pins to the trace grid — every row is sized against it, so
    the border never moves no matter what the data rows do.
    """
    w = min(width - 4, _W)
    rows = [_grid(ctx, shot, w), truncate(_census(shot), w)]
    rows += [truncate(b, w) for b in extra]
    return border(join_vertical(*rows), title="raymarch", chars=ROUNDED)


# --- Zoom renderers ---


def _render_minimal(shot: Shot, width: int) -> Block:
    return truncate(_census(shot), width)


def _render_full(ctx: CliContext, shot: Shot, width: int) -> Block:
    # Stats describe the grid actually displayed: portrait rays on a color
    # terminal (4x when the settle supersamples), ramp rays on a pipe.
    if ctx.use_ansi:
        _rows, hits, steps, rays = _trace_portrait(shot)
    else:
        _grid_vals, hits, steps = _trace(shot)
        rays = _W * _H
    stats = Block.text(
        f"frame {shot.frame}  ·  rays {rays}  ·  hit {hits / rays:.0%}  ·  "
        f"steps/ray {steps / rays:.1f}  ·  scene {_count_nodes(_scene(shot.frame))} nodes",
        Style(dim=True),
    )
    return _window(ctx, shot, width, _legend(ctx), stats)


def _count_nodes(node: Node) -> int:
    if isinstance(node, (Union, SmoothUnion)):
        return 1 + _count_nodes(node.a) + _count_nodes(node.b)
    return 1


def _render(ctx: CliContext, shot: Shot) -> Block:
    if ctx.zoom >= Zoom.FULL:
        return _render_full(ctx, shot, ctx.width)
    if ctx.zoom >= Zoom.DETAILED:
        return _window(ctx, shot, ctx.width, _legend(ctx))
    if ctx.zoom >= Zoom.SUMMARY:
        return _window(ctx, shot, ctx.width)
    return _render_minimal(shot, ctx.width)


# --- Entry point ---


def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    ns, rest = pre.parse_known_args(sys.argv[1:])

    return run_cli(
        rest,
        render=_render,
        fetch=lambda: _fetch(ns.frame),
        fetch_stream=lambda: _fetch_stream(),
        live_delivery="surface",
        live_meter=True,
        description=__doc__,
        prog="raymarch.py",
        help_args=[
            HelpArg(
                "--frame",
                "pose shown by static output (live orbits from 0)",
                default=str(DEFAULT_FRAME),
            ),
        ],
    )


if __name__ == "__main__":
    sys.exit(main())
