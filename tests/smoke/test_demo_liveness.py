"""Liveness smoke — every demo / the tour / every slide renders without raising.

The FLOOR tier of the golden→by-axis migration (see repo `golden-migration-plan.md`).
Demos stopped being pixel-golden fixtures — but they're also documentation, so they
must still RUN. This catches "feature X silently broke demo Y" without coupling any
contract to demo cosmetics: no snapshot, no re-bless, no style assertion. The bar is
deliberately low and deliberately broad — render every artifact, assert only that it
does not raise and is non-degenerate. Appearance/behavior regressions are the job of
the property / appearance / behavioral tiers, not this one.

Parametrized per artifact so a single failure names the broken demo, not "liveness".
"""

from __future__ import annotations

import importlib.util
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from painted import Fidelity, Zoom
from painted.tui.testing import TestSurface

_PROJECT = Path(__file__).resolve().parent.parent.parent
_DEMOS = _PROJECT / "demos"


def _render_demo(mod, zoom: Zoom, data: object):
    return mod._render(data, Fidelity(depth=int(zoom)), 80)


def _load(rel: str):
    """Import a demo module by file path (no sys.path mutation).

    Registered in sys.modules under a unique name so the demo's own dataclasses
    resolve their module — same trick the golden tests used.
    """
    path = _DEMOS / rel
    name = "_live_" + rel.replace("/", "_").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load demo: {rel}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --- Primitives: build a Block and print it to stdout ---

PRIMITIVES = [
    "cell",
    "compose",
    "diagnostics",
    "errors",
    "logging_handler",
    "paint",
    "refs",
    "span_line",
]


@pytest.mark.parametrize("name", PRIMITIVES)
def test_primitive_demo_renders(name: str) -> None:
    mod = _load(f"primitives/{name}.py")
    buf = StringIO()
    with redirect_stdout(buf):
        mod.demo()
    assert buf.getvalue().strip(), f"primitives/{name}.demo() produced no output"


# --- Patterns: _fetch() then _render(ctx, data) at every zoom ---

PATTERNS = [
    "denotation",
    "fidelity",
    "focus",
    "help",
    "hit_testing",
    "layers",
    "live",
    "monitor",
    "palette_icons",
    "profiler",
    "prompts",
    "responsive",
    "table",
    "testing",
    "timing",
]


@pytest.mark.parametrize("name", PATTERNS)
def test_pattern_demo_renders(name: str) -> None:
    mod = _load(f"patterns/{name}.py")
    data = mod._fetch()
    for zoom in Zoom:
        block = _render_demo(mod, zoom, data)
        assert block.width > 0, f"patterns/{name} rendered an empty block at {zoom.name}"


# --- Showcase: surface-delivered spectacle. Same pattern test shape
# (_fetch() then _render at every zoom); separated only as a presentation tier.
SHOWCASE = [
    "boids",
    "donut",
    "fire",
    "harmonograph",
    "life",
    "lorenz",
    "mandelbrot",
    "plasma",
    "raymarch",
    "starmap",
    "wireworld",
]


@pytest.mark.parametrize("name", SHOWCASE)
def test_showcase_demo_renders(name: str) -> None:
    mod = _load(f"showcase/{name}.py")
    data = mod._fetch()
    for zoom in Zoom:
        block = _render_demo(mod, zoom, data)
        assert block.width > 0, f"showcase/{name} rendered an empty block at {zoom.name}"


# rendering.py is the one deviant pattern: no _fetch/_render, flag-dispatched
# functions that print directly.
RENDERING_DEMOS = ["demo_explicit", "demo_custom", "demo_palette", "demo_help"]


@pytest.mark.parametrize("fn", RENDERING_DEMOS)
def test_rendering_pattern_demo_renders(fn: str) -> None:
    mod = _load("patterns/rendering.py")
    buf = StringIO()
    with redirect_stdout(buf):
        getattr(mod, fn)()
    assert buf.getvalue().strip(), f"patterns/rendering.{fn}() produced no output"


# --- Apps + examples: drive a few representative keys through TestSurface ---
# run_to_completion() is bounded by the input queue, so a trailing 'q' is courtesy,
# not a hang-guard. Keys are a light touch of on_key; behavior coverage lives in
# the behavioral tier, not here.

APPS = [
    ("apps/animation.py", "AnimationApp", ["x", "x", "space", "r", "q"]),
    ("apps/focus_form.py", "FocusFormApp", ["tab", "tab", "q"]),
    ("apps/layers.py", "LayersApp", ["s", "up", "enter", "q"]),
    ("apps/minimal.py", "MinimalApp", ["right", "c", "q"]),
    ("apps/mouse.py", "MouseApp", ["c", "q"]),
    ("apps/search_filter.py", "SearchFilterApp", ["tab", "down", "q"]),
    ("apps/viewport.py", "ViewportInspectorApp", ["down", "down", "q"]),
    ("apps/widgets.py", "WidgetsApp", ["right", "tab", "down", "q"]),
    ("examples/big_text.py", "BigTextDemo", ["q"]),
    ("examples/lenses.py", "LensesApp", ["v", "q"]),
    ("examples/theme_carnival.py", "PaletteCarnival", ["q"]),
]


@pytest.mark.parametrize("rel,cls,keys", APPS, ids=[a[0] for a in APPS])
def test_app_demo_renders(rel: str, cls: str, keys: list[str]) -> None:
    mod = _load(rel)
    app = getattr(mod, cls)()
    frames = TestSurface(app, width=80, height=24, input_queue=keys).run_to_completion()
    assert frames, f"{rel} captured no frames"
    assert frames[0].text, f"{rel} initial frame was empty"


def test_example_disk_renders() -> None:
    """disk.py rendered against SYNTHETIC volumes — never the real filesystem.

    Resolves open-decision #4: disk's `_scan()` walks real mounts following
    symlinks, which is non-deterministic and can hang a gate (it did). DiskApp's
    ctor seeds `current_entries` from `volumes[0]` and only re-scans on navigation,
    so synthetic volumes + an immediate quit render the demo's view with zero FS
    access. Liveness asserts the render path runs; the real scan is exercised by
    running the demo, not the gate.
    """
    mod = _load("examples/disk.py")
    volumes = (
        mod.Volume(
            mount="/synthetic",
            total_bytes=1_000_000,
            used_bytes=400_000,
            entries=(
                mod.DirEntry("docs", 250_000, is_dir=True, children=()),
                mod.DirEntry("notes.txt", 150_000),
            ),
        ),
    )
    app = mod.DiskApp(volumes=volumes)
    frames = TestSurface(app, width=80, height=24, input_queue=["q"]).run_to_completion()
    assert frames, "examples/disk.py captured no frames"


# --- Tour + slides ---


def test_tour_renders_all_slides_quiet() -> None:
    """tour.py -q path: build every slide and render each at every zoom, no TTY.

    build_slides() inserts demos/ on sys.path (so `import slide_loader` resolves)
    and run_quiet_mode renders the full slide x zoom matrix to stdout.
    """
    tour = _load("tour.py")
    slides, nav_sequence = tour.build_slides()
    assert slides, "tour built no slides"
    buf = StringIO()
    with redirect_stdout(buf):
        tour.run_quiet_mode(slides, nav_sequence)
    assert buf.getvalue().strip(), "tour quiet mode produced no output"


def test_slides_parse_and_validate() -> None:
    """Parse-level liveness: every slide .md parses and the set validates."""
    loader = _load("slide_loader.py")
    parsed = loader.load_slides_dir(_DEMOS / "slides")
    assert parsed, "no slides parsed from demos/slides"
    loader.validate_slides(parsed)  # raises on invalid grouping/zoom/order
