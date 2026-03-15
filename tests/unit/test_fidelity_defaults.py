"""Icon scoping: plain renders use ASCII icons without leaking to later renders."""

from __future__ import annotations

import io

from painted import Block, Format, Style, show
from painted.cli import CliContext, OutputMode, Zoom, run_cli
from painted.icon_set import ASCII_ICONS, current_icons, reset_icons


def test_plain_render_does_not_leak_ascii_icons(monkeypatch):
    """After a Format.PLAIN render, ambient icons must be restored."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    reset_icons()
    default_icons = current_icons()

    show({"a": 1}, format=Format.PLAIN, file=io.StringIO())

    assert current_icons() is default_icons
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_plain_render_uses_ascii_icons_during_render(monkeypatch):
    """Format.PLAIN must use ASCII icons for the lens call, not Unicode."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    reset_icons()
    captured_icons = None

    def spy_lens(data, zoom, width):
        nonlocal captured_icons
        captured_icons = current_icons()
        return Block.text(str(data), Style())

    show({"a": 1}, format=Format.PLAIN, lens=spy_lens, file=io.StringIO())

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
        render=lambda ctx, data: Block.text("ok", Style()),
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

    def render(ctx, data):
        nonlocal captured_icons
        captured_icons = current_icons()
        return Block.text("ok", Style())

    run_cli(
        [],
        render=render,
        fetch=lambda: "data",
    )

    assert captured_icons is ASCII_ICONS
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_ansi_render_keeps_default_icons(monkeypatch):
    """Format.ANSI render should not touch icons at all."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    reset_icons()
    default_icons = current_icons()

    show({"a": 1}, format=Format.ANSI, file=io.StringIO())

    assert current_icons() is default_icons
    reset_icons()
