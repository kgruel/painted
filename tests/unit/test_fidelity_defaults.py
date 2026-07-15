"""Icon scoping: the glyph facet installs an ASCII IconSet, scoped and restored.

The §9.4 pairing at the paint()/run_cli install sites: a host narrowing
``glyph=False`` also installs an ASCII-safe ``IconSet``, so the two never
disagree. Glyph resolves from the *destination encoding* (§9.3), not ANSI-ness —
a UTF-8 pipe keeps Unicode carriers even with color off, and the install is a
scoped bracket that restores the ambient icons on exit.
"""

from __future__ import annotations

import io

from painted import Block, Style, paint
from painted.cli import CliContext, CliRunner, Fidelity, OutputMode, Zoom
from painted.icon_set import ASCII_ICONS, current_icons, reset_icons


class _Stream:
    """A writable stream with an explicit ``encoding`` and ``isatty`` — the two
    signals the host bracket resolves glyph and color from, held independent."""

    def __init__(self, *, encoding: str | None, isatty: bool) -> None:
        self._buf = io.StringIO()
        self.encoding = encoding
        self._isatty = isatty

    def write(self, s: str) -> int:
        return self._buf.write(s)

    def flush(self) -> None: ...

    def isatty(self) -> bool:
        return self._isatty


def _ctx(*, use_ansi: bool) -> CliContext:
    return CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=OutputMode.STATIC,
        use_ansi=use_ansi,
        is_tty=use_ansi,
        width=80,
        height=24,
    )


# --- paint(): glyph resolves from the destination file (PAINT_DESIGN §8) ---


def test_paint_ascii_destination_uses_ascii_icons_during_render():
    """An ASCII-encoded destination narrows glyph → ASCII icons for the lens call."""
    reset_icons()
    captured = None

    def spy_lens(data, zoom, width):
        nonlocal captured
        captured = current_icons()
        return Block.text(str(data), Style())

    paint({"a": 1}, lens=spy_lens, file=_Stream(encoding="ascii", isatty=False))

    assert captured is ASCII_ICONS
    assert current_icons() is not ASCII_ICONS  # scoped: restored after
    reset_icons()


def test_paint_ascii_destination_does_not_leak_ascii_icons():
    """The ASCII install is a scoped bracket — ambient icons restored after."""
    reset_icons()
    default_icons = current_icons()

    paint({"a": 1}, file=_Stream(encoding="ascii", isatty=False))

    assert current_icons() is default_icons
    assert current_icons() is not ASCII_ICONS
    reset_icons()


def test_paint_utf8_pipe_keeps_unicode_icons():
    """A UTF-8 pipe: color is off (not a TTY) but glyph does NOT co-narrow — the
    encoding still carries carriers, so the Unicode IconSet stays (§9.3)."""
    reset_icons()
    default_icons = current_icons()
    captured = None

    def spy_lens(data, zoom, width):
        nonlocal captured
        captured = current_icons()
        return Block.text(str(data), Style())

    paint({"a": 1}, lens=spy_lens, file=_Stream(encoding="utf-8", isatty=False))

    assert captured is default_icons
    assert captured is not ASCII_ICONS
    reset_icons()


def test_paint_utf8_tty_keeps_default_icons():
    """An ANSI render to a UTF-8 terminal touches icons not at all."""
    reset_icons()
    default_icons = current_icons()

    paint({"a": 1}, file=_Stream(encoding="utf-8", isatty=True))

    assert current_icons() is default_icons
    reset_icons()


# --- run_cli: glyph resolves from stdout's encoding (§9.3) ---


def test_run_cli_ascii_destination_uses_ascii_icons_during_render(monkeypatch):
    """run_cli's renderer sees ASCII icons when the destination narrows glyph."""
    import sys

    monkeypatch.setattr(sys, "stdout", _Stream(encoding="ascii", isatty=False))
    reset_icons()
    captured = None

    def renderer(data, fidelity, width):
        nonlocal captured
        captured = current_icons()
        return Block.text("ok", Style())

    CliRunner(renderer=renderer, fetch=lambda: "data")._dispatch(_ctx(use_ansi=False))

    assert captured is ASCII_ICONS
    assert current_icons() is not ASCII_ICONS  # scoped: restored after
    reset_icons()


def test_run_cli_utf8_pipe_keeps_unicode_icons(monkeypatch):
    """A UTF-8 pipe keeps Unicode icons even with color off — glyph does not
    co-narrow with color (the superseded conflation, §9.3)."""
    import sys

    monkeypatch.setattr(sys, "stdout", _Stream(encoding="utf-8", isatty=False))
    reset_icons()
    default_icons = current_icons()
    captured = None

    def renderer(data, fidelity, width):
        nonlocal captured
        captured = current_icons()
        return Block.text("ok", Style())

    CliRunner(renderer=renderer, fetch=lambda: "data")._dispatch(_ctx(use_ansi=False))

    assert captured is default_icons
    assert current_icons() is default_icons  # never installed, nothing to leak
    reset_icons()
