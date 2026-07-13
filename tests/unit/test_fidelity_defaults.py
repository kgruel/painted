"""Icon scoping: plain renders use ASCII icons without leaking to later renders."""

from __future__ import annotations

import io

from painted import Block, Style, paint
from painted.cli import CliContext, OutputMode, Zoom, run_cli
from painted.icon_set import ASCII_ICONS, current_icons, reset_icons


class _FakeTTY(io.StringIO):
    """A StringIO that claims to be a terminal — drives paint()'s ANSI path."""

    def isatty(self) -> bool:
        return True


def test_plain_render_does_not_leak_ascii_icons():
    """After a plain render (non-TTY file), ambient icons must be restored."""
    reset_icons()
    default_icons = current_icons()

    paint({"a": 1}, file=io.StringIO())  # StringIO.isatty() is False -> plain

    assert current_icons() is default_icons
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_plain_render_uses_ascii_icons_during_render():
    """A plain render must use ASCII icons for the lens call, not Unicode."""
    reset_icons()
    captured_icons = None

    def spy_lens(data, zoom, width):
        nonlocal captured_icons
        captured_icons = current_icons()
        return Block.text(str(data), Style())

    paint({"a": 1}, lens=spy_lens, file=io.StringIO())

    assert captured_icons is ASCII_ICONS
    # And restored after
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_run_cli_plain_does_not_leak_ascii_icons(monkeypatch):
    """run_cli with pipe output (use_ansi=False) must not leak ASCII icons."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    reset_icons()
    default_icons = current_icons()

    run_cli(
        [],
        renderer=lambda data, fidelity, width: Block.text("ok", Style()),
        fetch=lambda: "data",
    )

    assert current_icons() is default_icons
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_run_cli_plain_uses_ascii_icons_during_render(monkeypatch):
    """run_cli render callback must see ASCII icons when use_ansi=False."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    reset_icons()
    captured_icons = None

    def renderer(data, fidelity, width):
        nonlocal captured_icons
        captured_icons = current_icons()
        return Block.text("ok", Style())

    run_cli(
        [],
        renderer=renderer,
        fetch=lambda: "data",
    )

    assert captured_icons is ASCII_ICONS
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_ansi_render_keeps_default_icons():
    """An ANSI render (TTY file) should not touch icons at all."""
    reset_icons()
    default_icons = current_icons()

    paint({"a": 1}, file=_FakeTTY())  # isatty() True -> ANSI, no icon scoping

    assert current_icons() is default_icons
    reset_icons()
