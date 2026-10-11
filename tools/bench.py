"""Scenario baselines for painted's pipeline (roadmap M8).

    python -m tools.bench                       # run, print the report
    python -m tools.bench --save docs/baselines/baseline.json
    python -m tools.bench --compare docs/baselines/baseline.json

A baseline, not a budget: nothing here fails the gate. Each scenario records
median and p95 latency, peak traced allocation, and exact counters (output
bytes, write calls, changed cells, modules loaded). Counters are deterministic
and comparable across machines; timings are only comparable on the machine
that recorded them, so ``--compare`` flags timing drift but never fails.

The scenario list follows ROADMAP_1.0.0.md Milestone 8: cold imports, help,
completion, domain state -> Block at each zoom, composition, the four
serializations, sparse/full Buffer diffs, host viewport composition, key input
-> flushed frame, and large table / tree / traceback / dashboard renders.
The report renders through painted itself (``table_lens``).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

Counters = dict[str, int]
Run = Callable[[], Counters | None]

LIVE_BUDGET_US = 33_333  # one frame at 30 fps
DRIFT_RATIO = 1.25  # --compare flags a median slower than this


@dataclass(frozen=True)
class Scenario:
    name: str
    group: str
    setup: Callable[[], Run]
    frame: bool = False  # a live-frame scenario: count samples over LIVE_BUDGET_US


class _CountingStream(io.StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty = tty
        self.writes = 0

    def isatty(self) -> bool:
        return self._tty

    def write(self, s: str) -> int:
        self.writes += 1
        return super().write(s)


# --- Fixtures: representative domain state ---------------------------------


def _records(n: int) -> list[dict]:
    states = ("ok", "degraded", "down")
    return [
        {"id": i, "service": f"svc-{i % 37:02d}", "state": states[i % 3], "p50_ms": i * 0.7}
        for i in range(n)
    ]


def _nested(depth: int, fan: int) -> dict:
    if depth == 0:
        return {"value": 1, "label": "leaf"}
    return {f"node{i}": _nested(depth - 1, fan) for i in range(fan)}


def _status() -> dict:
    return {
        "service": "ingest",
        "healthy": True,
        "hosts": [{"name": f"h{i}", "load": i / 10, "tags": ["a", "b"]} for i in range(12)],
        "config": _nested(3, 3),
    }


def _deep_exception() -> BaseException:
    def recurse(n: int) -> None:
        if n == 0:
            raise ValueError("the innermost failure")
        recurse(n - 1)

    try:
        try:
            recurse(20)
        except ValueError as inner:
            raise RuntimeError("while handling the batch") from inner
    except RuntimeError as exc:
        return exc
    raise AssertionError("unreachable")


# --- Scenarios ---------------------------------------------------------------


def _import(module: str) -> Callable[[], Run]:
    code = (
        "import sys, time; t = time.perf_counter_ns(); import "
        + module
        + "; print(time.perf_counter_ns() - t, sum(m.startswith('painted') for m in sys.modules))"
    )

    def setup() -> Run:
        def run() -> Counters:
            out = subprocess.run(
                [sys.executable, "-X", "frozen_modules=off", "-c", code],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
            return {"_ns": int(out[0]), "modules": int(out[1])}

        return run

    return setup


def _help() -> Run:
    from painted import Block
    from painted.cli import run_cli

    def run() -> Counters:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
            run_cli(["-h"], fetch=dict, renderer=lambda d, f, w: Block.text("x"), prog="bench")
        return {"bytes": len(out.getvalue())}

    return run


def _completion() -> Run:
    from painted.cli import AppCommand, Tag, complete_app

    cmds = [
        AppCommand(f"cmd{i}", f"Command {i}", lambda a: 0, tags=[Tag("thinking", "Show it")])
        for i in range(20)
    ]

    def run() -> Counters:
        return {"candidates": len(complete_app(cmds, ["cmd3"], "--"))}

    return run


def _project(zoom: int) -> Callable[[], Run]:
    def setup() -> Run:
        from painted.views.lens.shape import transcribe

        data = _status()

        def run() -> Counters:
            block = transcribe(data, zoom, 100)
            return {"cells": block.width * block.height}

        return run

    return setup


def _dashboard() -> Run:
    from painted import Block, Style, border, join_horizontal, join_vertical
    from painted.views import sparkline, table_lens, tree_lens

    rows = _records(40)
    tree = _nested(3, 4)
    series = [float((i * 7) % 23) for i in range(60)]

    def run() -> Counters:
        left = border(table_lens(rows, 2, 60), title="services")
        right = join_vertical(
            border(tree_lens(tree, 2, 50), title="config"),
            border(sparkline(series, 48), title="load"),
        )
        block = join_vertical(
            Block.text("ingest — dashboard", Style(bold=True)),
            join_horizontal(left, right, gap=1),
        )
        return {"cells": block.width * block.height}

    return run


def _block_for_serialization():
    from painted.views import table_lens

    return table_lens(_records(200), 2, 100)


def _serialize(kind: str) -> Callable[[], Run]:
    def setup() -> Run:
        from painted.core.html import render_html
        from painted.core.writer import print_block

        block = _block_for_serialization()
        data = _records(200)

        def run() -> Counters:
            if kind == "html":
                return {"bytes": len(render_html(block))}
            if kind == "json":
                return {"bytes": len(json.dumps(data, default=str))}
            stream = _CountingStream(tty=kind == "ansi")
            print_block(block, stream)
            return {"bytes": len(stream.getvalue()), "writes": stream.writes}

        return run

    return setup


def _diff(fraction: float) -> Callable[[], Run]:
    def setup() -> Run:
        from painted import Style
        from painted.core.buffer import Buffer

        w, h = 200, 60
        prev = Buffer(w, h)
        cur = Buffer(w, h)
        step = max(1, round(1 / fraction))
        for i in range(0, w * h, step):
            cur.put_text(i % w, i // w, "x", Style(fg="green"))

        def run() -> Counters:
            return {"changed_cells": len(cur.diff(prev))}

        return run

    return setup


def _host(scroll: bool) -> Callable[[], Run]:
    def setup() -> Run:
        from painted import Block, join_vertical
        from painted.host import HostViewport

        content = join_vertical(*(Block.text(f"line {i}") for i in range(5000)))
        vp = HostViewport(content_id="bench")
        vp.set_geometry(100, 50)
        vp.install(content, reason=None)
        vp.frame()

        def run() -> Counters:
            if scroll:
                vp.route_key("down")
            frame = vp.frame()
            return {"rows": frame.block.height}

        return run

    return setup


def _key_to_frame() -> Run:
    from painted import Style
    from painted.core.span import Line
    from painted.tui import Surface, TestSurface
    from painted.views import ListState, list_view

    items = [Line.plain(f"item {i}") for i in range(1000)]

    class ListApp(Surface):
        def __init__(self) -> None:
            super().__init__()
            self.state = ListState().with_count(len(items)).with_visible(38)

        def render(self) -> None:
            buf = self._buf
            buf.fill(0, 0, buf.width, buf.height, " ", Style())
            list_view(self.state, items, 38, width=buf.width).paint(buf)

        def on_key(self, key: str) -> None:
            # Step the selection, scrolling it into view, wrapping at the end, so
            # every sample is a real one-row move.
            at_end = self.state.selected == len(items) - 1
            moved = self.state.move_to(0) if at_end else self.state.move_down()
            self.state = moved.scroll_into_view(38)

    stream = _CountingStream(tty=True)
    app = ListApp()
    harness = TestSurface(app, width=100, height=40, stream=stream, write_ansi=True)
    frames = harness.run_to_completion()

    def run() -> Counters:
        stream.writes = 0
        before = len(stream.getvalue())
        app.on_key("j")
        app._dirty = True
        app.update()
        harness._render_and_capture(frames)
        frame = frames.pop()
        return {
            "changed_cells": len(frame.writes),
            "writes": stream.writes,
            "bytes": len(stream.getvalue()) - before,
        }

    return run


def _large(kind: str) -> Callable[[], Run]:
    def setup() -> Run:
        from painted import Zoom
        from painted.views import render_traceback, table_lens, tree_lens

        if kind == "table":
            rows = _records(2000)
            render = lambda: table_lens(rows, 2, 120)  # noqa: E731
        elif kind == "tree":
            tree = _nested(5, 5)
            render = lambda: tree_lens(tree, 3, 120)  # noqa: E731
        else:
            exc = _deep_exception()
            render = lambda: render_traceback(exc, Zoom.FULL, 120)  # noqa: E731

        def run() -> Counters:
            block = render()
            return {"rows": block.height}

        return run

    return setup


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("import painted", "cold", _import("painted")),
    Scenario("import painted.views", "cold", _import("painted.views")),
    Scenario("import painted.cli", "cold", _import("painted.cli")),
    Scenario("import painted.tui", "cold", _import("painted.tui")),
    Scenario("help (-h)", "cli", _help),
    Scenario("completion", "cli", _completion),
    *(Scenario(f"transcribe zoom {z}", "project", _project(z)) for z in range(4)),
    Scenario("dashboard compose", "compose", _dashboard),
    *(Scenario(f"serialize {k}", "serialize", _serialize(k)) for k in ("plain", "ansi", "html", "json")),
    Scenario("buffer diff sparse", "diff", _diff(0.01)),
    Scenario("buffer diff full", "diff", _diff(1.0)),
    Scenario("host frame (static)", "host", _host(scroll=False), frame=True),
    Scenario("host frame (scroll)", "host", _host(scroll=True), frame=True),
    Scenario("key -> flushed frame", "host", _key_to_frame, frame=True),
    Scenario("large table (2000 rows)", "large", _large("table")),
    Scenario("large tree (5x5)", "large", _large("tree")),
    Scenario("traceback (depth 20, chained)", "large", _large("traceback")),
)


# --- Measurement -------------------------------------------------------------


def _measure(s: Scenario, iterations: int) -> dict:
    run = s.setup()
    cold = s.group == "cold"
    n = max(5, iterations // 10) if cold else iterations
    for _ in range(0 if cold else min(5, n)):
        run()  # warm caches, lazy imports, ambient lookups

    samples: list[int] = []
    counters: Counters | None = None
    for _ in range(n):
        t = time.perf_counter_ns()
        counters = run() or {}
        elapsed = time.perf_counter_ns() - t
        samples.append(counters.pop("_ns", elapsed))

    peak = 0
    if not cold:
        tracemalloc.start()
        run()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

    samples.sort()
    result = {
        "group": s.group,
        "n": n,
        "median_us": round(statistics.median(samples) / 1000, 1),
        "p95_us": round(samples[min(n - 1, int(n * 0.95))] / 1000, 1),
        "peak_kib": round(peak / 1024, 1),
        "counters": counters or {},
    }
    if s.frame:
        result["over_budget"] = sum(x / 1000 > LIVE_BUDGET_US for x in samples)
    return result


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_all(iterations: int, only: str | None) -> dict:
    from importlib.metadata import version

    scenarios = [s for s in SCENARIOS if only is None or only in s.name or only == s.group]
    return {
        "meta": {
            "painted": version("painted"),
            "commit": _git_commit(),
            "date": date.today().isoformat(),
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.machine()}",
            "iterations": iterations,
        },
        "scenarios": {s.name: _measure(s, iterations) for s in scenarios},
    }


# --- Reporting ---------------------------------------------------------------


def _fmt_counters(c: Counters) -> str:
    return " ".join(f"{k}={v}" for k, v in c.items())


def report(result: dict, baseline: dict | None) -> list[str]:
    """Print the run as a table; return the names whose median drifted."""
    from painted import print_block
    from painted.views import table_lens

    base = (baseline or {}).get("scenarios", {})
    drifted: list[str] = []
    rows = []
    for name, r in result["scenarios"].items():
        row = {
            "scenario": name,
            "median µs": r["median_us"],
            "p95 µs": r["p95_us"],
            "peak KiB": r["peak_kib"],
            "over budget": r.get("over_budget", ""),
            "counters": _fmt_counters(r["counters"]),
        }
        if baseline is not None:
            b = base.get(name)
            if b is None:
                row["vs base"] = "new"
            else:
                ratio = r["median_us"] / b["median_us"] if b["median_us"] else 1.0
                flag = ""
                if ratio > DRIFT_RATIO:
                    flag = " SLOWER"
                    drifted.append(name)
                if b["counters"] != r["counters"]:
                    flag += " COUNTERS"
                    drifted.append(name)
                row["vs base"] = f"{ratio:.2f}x{flag}"
        rows.append(row)
    meta = result["meta"]
    print(
        f"painted {meta['painted']} @ {meta['commit']} — python {meta['python']}, "
        f"{meta['platform']}, {meta['iterations']} iterations"
    )
    print_block(table_lens(rows, 2))  # natural width: never clip the counters
    return drifted


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="./dev bench", description=__doc__.split("\n")[0])
    p.add_argument("--iterations", type=int, default=200)
    p.add_argument("--only", help="run scenarios whose name contains this, or one group")
    p.add_argument("--save", type=Path, help="write the run as a JSON baseline")
    p.add_argument("--compare", type=Path, help="compare against a saved baseline")
    args = p.parse_args(argv)

    result = run_all(args.iterations, args.only)
    baseline = json.loads(args.compare.read_text()) if args.compare else None
    drifted = report(result, baseline)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(result, indent=2) + "\n")
        print(f"saved {args.save}")
    if drifted:
        print(f"drift (informational): {', '.join(dict.fromkeys(drifted))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
