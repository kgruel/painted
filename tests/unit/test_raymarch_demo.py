"""Law tests for the raymarch pattern demo.

The demo's lesson is a scene as an SDF expression tree evaluated by a pure
function, and liveness can't catch wrong geometry. Laws over the field
(analytic distances, operator algebra, Lipschitz), the march (occupancy,
unit normals), and the quality contract (live ramp vs half-block portrait,
pipe honesty) — no pose cosmetics are pinned.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import math
import sys
from pathlib import Path

from painted import Zoom
from tests.helpers import block_to_text, static_ctx

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "patterns" / "raymarch.py"


def _load():
    spec = importlib.util.spec_from_file_location("_raymarch_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_raymarch_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


rm = _load()

# A deterministic lattice of probe points spanning the scene's reach.
_PROBES = [
    (x * 0.7, y * 0.6, z * 0.7) for x in range(-4, 5) for y in range(-3, 4) for z in range(-4, 5)
]


# --- Field laws: the tree means what the formulas say ---


def test_compiled_closures_match_the_reference_evaluator() -> None:
    scene = rm._scene(frame=110)
    fast = rm._compile(scene)
    for x, y, z in _PROBES:
        assert math.isclose(fast(x, y, z), rm._sdf(scene, x, y, z), abs_tol=1e-12)


def test_sphere_distance_is_analytic() -> None:
    s = rm.Sphere(cx=1.0, cy=-2.0, cz=0.5, r=0.75)
    for x, y, z in _PROBES:
        want = math.dist((x, y, z), (1.0, -2.0, 0.5)) - 0.75
        assert math.isclose(rm._sdf(s, x, y, z), want, abs_tol=1e-12)


def test_torus_distance_is_analytic_at_landmarks() -> None:
    t = rm.Torus(ring=1.5, tube=0.5)
    assert math.isclose(rm._sdf(t, 2.0, 0.0, 0.0), 0.0, abs_tol=1e-12)  # outer equator
    assert math.isclose(rm._sdf(t, 1.0, 0.0, 0.0), 0.0, abs_tol=1e-12)  # inner equator
    assert math.isclose(rm._sdf(t, 0.0, 0.0, 0.0), 1.0, abs_tol=1e-12)  # hole center
    assert math.isclose(rm._sdf(t, 0.0, 4.0, 0.0), math.hypot(1.5, 4.0) - 0.5, abs_tol=1e-12)


def test_union_is_min_and_smooth_union_is_bounded() -> None:
    a = rm.Sphere(cx=-1.0, cy=0.0, cz=0.0, r=0.8)
    b = rm.Sphere(cx=1.0, cy=0.3, cz=0.0, r=0.6)
    k = 0.45
    for x, y, z in _PROBES:
        da, db = rm._sdf(a, x, y, z), rm._sdf(b, x, y, z)
        assert rm._sdf(rm.Union(a, b), x, y, z) == min(da, db)
        smooth = rm._sdf(rm.SmoothUnion(a, b, k), x, y, z)
        assert min(da, db) - k / 4 - 1e-12 <= smooth <= min(da, db) + 1e-12


def test_scene_field_is_lipschitz() -> None:
    """A marchable SDF never lies by more than the distance traveled."""
    scene = rm._scene(frame=42)
    f = rm._compile(scene)
    for p, q in zip(_PROBES, _PROBES[1:]):
        df = abs(f(*p) - f(*q))
        assert df <= math.dist(p, q) + 1e-9


def test_thread_orbit_passes_through_the_hole() -> None:
    """The chain link is real: mid-orbit, the sphere sits in the hole."""
    half_orbit = round(math.pi / rm._SPHERE_STEP)
    s = rm._sphere_at(half_orbit)
    assert math.hypot(s.cx, s.cy, s.cz) < 0.1


# --- March laws ---


def test_normals_are_unit_length_at_hits() -> None:
    scene = rm._compile(rm._scene(frame=110))
    (ex, ey, ez), _r, _u, (fx, fy, fz) = rm._camera(110)
    t, _steps = rm._march(scene, ex, ey, ez, fx, fy, fz)
    assert t > 0, "the camera axis ray should hit the scene"
    nx, ny, nz = rm._normal(scene, ex + t * fx, ey + t * fy, ez + t * fz)
    assert math.isclose(math.hypot(nx, ny, nz), 1.0, abs_tol=1e-6)


def test_trace_occupancy_is_sane() -> None:
    # Subject + floor fill a healthy band: visible but not a wall.
    for frame in (0, 70, 110):
        _grid, hits, _steps = rm._trace(rm.Shot(frame=frame))
        assert 0.30 < hits / (rm._W * rm._H) < 0.90, f"frame {frame}"


def test_trace_shades_within_the_ramp() -> None:
    grid, _hits, _steps = rm._trace(rm.Shot(frame=110))
    indices = {idx for row in grid for idx in row}
    assert indices <= set(range(-1, 12))
    assert max(indices) >= 0, "no lit cells at all"


# --- Quality contract: live ramp, half-block portrait, pipe honesty ---


def test_live_grid_glyphs_come_only_from_the_ramp() -> None:
    text = block_to_text(rm._grid_live(rm.Shot(frame=110), 80))
    assert set(text) <= set(rm._RAMP) | {" ", "\n"}


def test_portrait_is_half_blocks_on_a_capable_terminal() -> None:
    ctx = dataclasses.replace(static_ctx(Zoom.SUMMARY), use_ansi=True)
    text = block_to_text(rm._grid(ctx, rm.Shot(frame=110, quality=1), 80))
    assert set(text) <= {"▀", " ", "\n"}


def test_portrait_falls_back_to_the_ramp_for_pipes() -> None:
    ctx = static_ctx(Zoom.SUMMARY)  # use_ansi=False
    text = block_to_text(rm._grid(ctx, rm.Shot(frame=110, quality=1), 80))
    assert set(text) <= set(rm._RAMP) | {" ", "\n"}


def test_static_pose_is_always_the_portrait() -> None:
    assert rm._fetch(frame=110).quality == 1


# --- Purity and motion ---


def test_scene_is_a_pure_function_of_the_shot() -> None:
    for zoom in Zoom:
        ctx = static_ctx(zoom)
        shot = rm.Shot(frame=123)
        assert block_to_text(rm._render(ctx, shot)) == block_to_text(rm._render(ctx, shot))


def test_orbit_actually_moves() -> None:
    ctx = static_ctx(Zoom.SUMMARY)
    a = block_to_text(rm._render(ctx, rm.Shot(frame=0)))
    b = block_to_text(rm._render(ctx, rm.Shot(frame=30)))
    assert a != b


def test_stream_settles_into_the_portrait() -> None:
    async def collect() -> list:
        return [shot async for shot in rm._fetch_stream(start=5, frames=3)]

    shots = asyncio.run(collect())
    assert [s.frame for s in shots] == [5, 6, 7, 7]
    assert [s.quality for s in shots] == [0, 0, 0, 1]
