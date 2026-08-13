#!/usr/bin/env python3
"""Harmonograph Lab — play the four-pendulum score as an instrument.

The companion to the harmonograph showcase. The showcase keeps a pure
``Performance -> Block`` boundary; this example adds an immutable application
state around the same score and raster. Select a control, tune it, switch
presets, pause the breathing phase, or reset the current score.

    uv run demos/examples/harmonograph_lab.py

Keys:
  up/down or j/k  select a control
  left/right      tune the selected value
  [ / ]           tune by a larger step
  1-4             choose a preset
  space            pause/resume
  r                reset the current preset
  ?                help
  q                quit
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType

from painted import (
    Block,
    HEAVY,
    Style,
    border,
    current_icons,
    fit_to_width,
    join_horizontal,
    join_vertical,
    pad,
)
from painted.palette import current_palette
from painted.tui import Surface


def _load_showcase() -> ModuleType:
    """Load the sibling showcase in dev checkouts and installed wheels."""
    here = Path(__file__).resolve()
    candidates = (
        here.parent.parent / "showcase" / "harmonograph.py",  # repo or packaged demos/
        here.parent.parent.parent / "showcase" / "harmonograph.py",  # defensive layout
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise RuntimeError("harmonograph_lab needs the sibling showcase/harmonograph.py")
    name = "_painted_harmonograph_showcase"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load harmonograph showcase: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hm = _load_showcase()

_X0_DAMPING = 6 / 7
_X1_DAMPING = 10 / 7
_Y1_DAMPING = 9 / 7
_X1_DRIFT = 13 / 21
_Y0_DRIFT = 11 / 21
_Y1_DRIFT = 23 / 21
_Y1_PHASE = 1.32 / 1.57


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    score: object


def _score(
    xf0: float,
    xf1: float,
    yf0: float,
    yf1: float,
    *,
    damping: float,
    phase: float,
    drift: float,
) -> object:
    """Build a score from expressive controls, keeping the base amplitudes."""
    base = hm.SCORE
    x0, x1 = base.x
    y0, y1 = base.y
    return hm.Score(
        x=(
            replace(
                x0,
                frequency=xf0,
                phase=0.0,
                damping=damping * _X0_DAMPING,
                drift=drift,
            ),
            replace(
                x1,
                frequency=xf1,
                phase=phase,
                damping=damping * _X1_DAMPING,
                drift=-drift * _X1_DRIFT,
            ),
        ),
        y=(
            replace(
                y0,
                frequency=yf0,
                phase=0.18,
                damping=damping,
                drift=drift * _Y0_DRIFT,
            ),
            replace(
                y1,
                frequency=yf1,
                phase=phase * _Y1_PHASE,
                damping=damping * _Y1_DAMPING,
                drift=-drift * _Y1_DRIFT,
            ),
        ),
    )


PRESETS: tuple[Preset, ...] = (
    Preset("Rosette", "near-tuned 3:2 figure", hm.SCORE),
    Preset(
        "Orbit",
        "slow 1:1 breathing loops",
        _score(2.0, 2.027, 2.0, 1.983, damping=0.0042, phase=1.20, drift=0.0018),
    ),
    Preset(
        "Weave",
        "cross-ratio textile field",
        _score(4.0, 3.031, 3.0, 4.019, damping=0.0031, phase=1.44, drift=0.0025),
    ),
    Preset(
        "Crown",
        "bright five-lobed bloom",
        _score(5.0, 5.017, 4.0, 4.029, damping=0.0048, phase=1.67, drift=0.0014),
    ),
)


@dataclass(frozen=True)
class Control:
    id: str
    label: str
    step: float
    minimum: float
    maximum: float


CONTROLS: tuple[Control, ...] = (
    Control("x_ratio", "x ratio", 0.05, 0.25, 2.0),
    Control("y_ratio", "y ratio", 0.05, 0.25, 2.0),
    Control("x_detune", "x detune", 0.002, -0.20, 0.20),
    Control("y_detune", "y detune", 0.002, -0.20, 0.20),
    Control("damping", "damping", 0.0004, 0.0004, 0.0200),
    Control("phase", "phase", 0.05, 0.0, 3.14),
    Control("drift", "drift", 0.0002, 0.0, 0.0100),
)


@dataclass(frozen=True)
class Tuning:
    x_ratio: float
    y_ratio: float
    x_detune: float
    y_detune: float
    damping: float
    phase: float
    drift: float


def tuning_from_score(score: object) -> Tuning:
    x0, x1 = score.x
    y0, y1 = score.y
    return Tuning(
        x_ratio=x0.frequency / y0.frequency,
        y_ratio=y0.frequency / x0.frequency,
        x_detune=x1.frequency - x0.frequency,
        y_detune=y1.frequency - y0.frequency,
        damping=y0.damping,
        phase=x1.phase,
        drift=x0.drift,
    )


def score_from_tuning(tuning: Tuning, base_score: object) -> object:
    """Apply lab controls without mutating the preset's frozen score."""
    if tuning == tuning_from_score(base_score):
        return base_score
    x0, x1 = base_score.x
    y0, y1 = base_score.y
    # x ratio is anchored to y's first oscillator; y ratio is anchored to x's.
    # The simultaneous form uses the preset fundamentals so both remain stable
    # instead of feeding the adjusted value back around a ratio cycle.
    x_base = y0.frequency * tuning.x_ratio
    y_base = x0.frequency * tuning.y_ratio
    return hm.Score(
        x=(
            replace(
                x0,
                frequency=x_base,
                damping=tuning.damping * _X0_DAMPING,
                drift=tuning.drift,
            ),
            replace(
                x1,
                frequency=x_base + tuning.x_detune,
                phase=tuning.phase,
                damping=tuning.damping * _X1_DAMPING,
                drift=-tuning.drift * _X1_DRIFT,
            ),
        ),
        y=(
            replace(
                y0,
                frequency=y_base,
                damping=tuning.damping,
                drift=tuning.drift * _Y0_DRIFT,
            ),
            replace(
                y1,
                frequency=y_base + tuning.y_detune,
                phase=tuning.phase * _Y1_PHASE,
                damping=tuning.damping * _Y1_DAMPING,
                drift=-tuning.drift * _Y1_DRIFT,
            ),
        ),
    )


@dataclass(frozen=True)
class LabState:
    preset: int = 0
    tuning: Tuning = Tuning(1.5, 2 / 3, 0.013, 0.017, 0.0035, 1.57, 0.0021)
    selected: int = 0
    frame: int = 0
    paused: bool = False
    help_open: bool = False
    width: int = 100
    height: int = 30


def initial_state(preset: int = 0) -> LabState:
    return LabState(preset=preset, tuning=tuning_from_score(PRESETS[preset].score))


def select_control(state: LabState, delta: int) -> LabState:
    return replace(state, selected=(state.selected + delta) % len(CONTROLS))


def tune(state: LabState, delta: int, *, coarse: bool = False) -> LabState:
    control = CONTROLS[state.selected]
    old = getattr(state.tuning, control.id)
    step = control.step * (5 if coarse else 1)
    value = min(control.maximum, max(control.minimum, old + delta * step))
    return replace(state, tuning=replace(state.tuning, **{control.id: value}))


def choose_preset(state: LabState, index: int) -> LabState:
    preset = PRESETS[index]
    return replace(
        state,
        preset=index,
        tuning=tuning_from_score(preset.score),
        frame=0,
        paused=False,
    )


def reset(state: LabState) -> LabState:
    return choose_preset(state, state.preset)


def current_score(state: LabState) -> object:
    return score_from_tuning(state.tuning, PRESETS[state.preset].score)


def _value(control: Control, tuning: Tuning) -> str:
    value = getattr(tuning, control.id)
    if control.id in {"damping", "drift"}:
        return f"{value:.4f}"
    if control.id.endswith("detune"):
        return f"{value:+.3f}"
    return f"{value:.2f}"


def _gauge(control: Control, tuning: Tuning, width: int) -> Block:
    width = max(1, width)
    value = getattr(tuning, control.id)
    proportion = (value - control.minimum) / (control.maximum - control.minimum)
    position = min(width - 1, max(0, round(proportion * (width - 1))))
    p = current_palette()
    icons = current_icons()
    spans = tuple(
        Block.text(
            icons.rank_top if i == position else icons.rule,
            p.accent if i == position else p.muted,
        )
        for i in range(width)
    )
    return join_horizontal(*spans)


def render_rack(
    state: LabState,
    width: int,
    *,
    compact: bool = False,
    max_rows: int | None = None,
) -> Block:
    p = current_palette()
    width = max(0, width)
    if compact:
        short = max_rows is not None and max_rows <= 2
        rows: list[Block] = []
        if not short:
            rows.append(
                Block.text(
                    f"INSTRUMENT · {PRESETS[state.preset].name}",
                    p.accent.merge(Style(bold=True)),
                    width=width,
                )
            )
        control_budget = len(CONTROLS)
        if max_rows is not None:
            reserved = 0 if short else 2
            control_budget = max(1, min(len(CONTROLS), max_rows - reserved))
        start = min(
            max(0, state.selected - control_budget // 2),
            len(CONTROLS) - control_budget,
        )
        visible_controls = tuple(enumerate(CONTROLS))[start : start + control_budget]
    else:
        rows = [
            Block.text("INSTRUMENT", p.accent.merge(Style(bold=True)), width=width),
            Block.text(
                f"preset {state.preset + 1}/{len(PRESETS)}  {PRESETS[state.preset].name}",
                Style(bold=True),
                width=width,
            ),
            Block.text(PRESETS[state.preset].description, p.muted, width=width),
            Block.empty(width, 1),
        ]
        visible_controls = tuple(enumerate(CONTROLS))
    label_width = 10
    value_width = 8
    for index, control in visible_controls:
        active = index == state.selected
        marker = current_icons().arrow if active else " "
        style = p.accent.merge(Style(bold=True)) if active else Style()
        label = Block.text(f"{marker} {control.label:<{label_width}}", style)
        value = Block.text(f"{_value(control, state.tuning):>{value_width}}", style)
        gauge_width = max(1, width - label.width - value.width - 2)
        if compact or gauge_width < 5:
            row = join_horizontal(label, value, gap=1)
        else:
            row = join_horizontal(label, _gauge(control, state.tuning, gauge_width), value, gap=1)
        rows.append(fit_to_width(row, width))
    if compact:
        if max_rows is None or len(rows) < max_rows:
            rows.append(
                Block.text(
                    f"{'RUNNING' if not state.paused else 'PAUSED'} · 1-4 preset · ? help",
                    p.success if not state.paused else p.warning,
                    width=width,
                )
            )
    else:
        rows.extend(
            (
                Block.empty(width, 1),
                Block.text(
                    "RUNNING" if not state.paused else "PAUSED",
                    p.success if not state.paused else p.warning,
                    width=width,
                ),
                Block.text("1-4 preset  ? help", p.muted, width=width),
            )
        )
    return join_vertical(*rows)


def render_help(width: int) -> Block:
    p = current_palette()
    width = max(24, min(width, 58))
    rows = (
        Block.text("HARMONOGRAPH LAB", p.accent.merge(Style(bold=True))),
        Block.empty(None, 1),
        Block.text("up/down · j/k", Style(bold=True)),
        Block.text("select a parameter", p.muted),
        Block.text("left/right", Style(bold=True)),
        Block.text("fine adjustment", p.muted),
        Block.text("[ / ]", Style(bold=True)),
        Block.text("coarse adjustment", p.muted),
        Block.text("1-4", Style(bold=True)),
        Block.text("load a preset", p.muted),
        Block.text("space · r", Style(bold=True)),
        Block.text("pause/resume · reset preset", p.muted),
        Block.empty(None, 1),
        Block.text("? or Esc closes this card", p.accent),
    )
    return border(pad(join_vertical(*rows), left=2, right=2, top=1, bottom=1), chars=HEAVY)


def _frame_block(state: LabState, width: int, height: int) -> Block:
    """Compose one exact-size frame; Surface only paints the finished Block."""
    width, height = max(0, width), max(0, height)
    if width == 0 or height == 0:
        return Block.empty(width, height)

    p = current_palette()
    title = Block.text(
        f" HARMONOGRAPH LAB  {PRESETS[state.preset].name} ",
        p.accent.merge(Style(bold=True)),
    )
    status = Block.text(
        f"frame {state.frame:04d}  {'paused' if state.paused else 'live'}",
        p.warning if state.paused else p.muted,
    )
    header = fit_to_width(join_horizontal(title, status, gap=2), width)
    footer = Block.text(
        " ↑↓ select  ←→ tune  [ ] coarse  1-4 preset  space pause  r reset  ? help  q quit ",
        p.muted,
        width=width,
    )
    body_h = max(0, height - 2)
    if body_h == 0:
        return header if height == 1 else join_vertical(header, footer)

    performance = hm.Performance(frame=state.frame, score=current_score(state))
    wide = width >= 88
    if wide:
        rack_width = min(38, max(30, width // 3))
        plot_width = max(1, width - rack_width - 1)
        plot = hm.render_plate(performance, plot_width, body_h)
        rack = render_rack(state, rack_width, compact=rack_width < 34)
        body = join_horizontal(
            fit_to_width(plot, plot_width),
            fit_to_width(rack, rack_width),
            gap=1,
        )
    else:
        rack_h = min(len(CONTROLS) + 3, max(1, body_h - min(8, max(1, body_h // 2))))
        plot_h = max(1, body_h - rack_h)
        plot = hm.render_plate(performance, max(1, width), plot_h)
        rack = render_rack(state, width, compact=True, max_rows=rack_h)
        body = join_vertical(plot, rack)

    body = fit_to_width(body, width)
    if body.height < body_h:
        body = join_vertical(body, Block.empty(width, body_h - body.height))
    elif body.height > body_h:
        from painted import vslice

        body = vslice(body, 0, body_h)
    return join_vertical(header, body, footer)


class HarmonographLab(Surface):
    def __init__(self, *, state: LabState | None = None) -> None:
        super().__init__(fps_cap=30)
        self.state = state or initial_state()
        self._started = False

    def layout(self, width: int, height: int) -> None:
        self.state = replace(self.state, width=width, height=height)

    def update(self) -> None:
        if not self._started:
            self._started = True
            return
        if self.state.paused or self.state.help_open:
            return
        self.state = replace(self.state, frame=self.state.frame + 1)
        self.mark_dirty()

    def render(self) -> None:
        buf = self._buf
        buf.fill(0, 0, buf.width, buf.height, " ", Style())
        _frame_block(self.state, buf.width, buf.height).paint(buf, 0, 0)
        if self.state.help_open:
            overlay = render_help(buf.width - 4)
            x = max(0, (buf.width - overlay.width) // 2)
            y = max(0, (buf.height - overlay.height) // 2)
            overlay.paint(buf, x, y)

    def on_key(self, key: str) -> None:
        state = self.state
        if state.help_open:
            if key in {"?", "escape", "q"}:
                self.state = replace(state, help_open=False)
            return
        if key == "q":
            self.quit()
        elif key == "?":
            self.state = replace(state, help_open=True)
        elif key in {"up", "k"}:
            self.state = select_control(state, -1)
        elif key in {"down", "j", "tab"}:
            self.state = select_control(state, 1)
        elif key == "shift_tab":
            self.state = select_control(state, -1)
        elif key == "left":
            self.state = tune(state, -1)
        elif key == "right":
            self.state = tune(state, 1)
        elif key == "[":
            self.state = tune(state, -1, coarse=True)
        elif key == "]":
            self.state = tune(state, 1, coarse=True)
        elif key in {"1", "2", "3", "4"}:
            self.state = choose_preset(state, int(key) - 1)
            self._started = False
        elif key == "space":
            self.state = replace(state, paused=not state.paused)
        elif key == "r":
            self.state = reset(state)
            self._started = False


async def main() -> int:
    await HarmonographLab().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
