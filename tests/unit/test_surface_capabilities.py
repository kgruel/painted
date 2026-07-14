"""The Surface host capability bracket (§9.3 Surface row, §9.4, §9.1).

The framework Surface owns the terminal, so it resolves and installs the
capability bracket at frame time — spanning ``render()`` through ``_flush()`` —
from its *own writer*, the single snapshot the facets and that writer's
serialization share. The alt screen establishes ANSI *control* only: ``color``
still consults NO_COLOR + depth, ``glyph`` the encoding, ``link`` the writer's
hyperlink config. When glyph is False the frame also installs an ASCII IconSet.

Two shapes: the pure per-facet resolver (``resolve_surface_capabilities``) and
the wiring — that a live frame installs the bracket, pairs the IconSet, and
restores on exit — driven through ``TestSurface``.
"""

from __future__ import annotations

import io

from painted import ASCII_ICONS, Block, Capabilities, Style, current_capabilities, current_icons
from painted.capabilities import resolve_surface_capabilities
from painted.core.writer import ColorDepth, Writer
from painted.tui import Surface
from painted.tui.testing import TestSurface


class _Utf8Stream(io.StringIO):
    """A StringIO reporting a UTF-8 encoding (the base's is read-only ``None``)."""

    # A plain class attribute shadows the base's read-only ``encoding`` descriptor.
    encoding = "utf-8"


# --- The pure per-facet resolver (§9.3 Surface row) ---


class TestResolveSurfaceCapabilities:
    def test_fully_capable_terminal(self):
        caps = resolve_surface_capabilities(
            _Utf8Stream(), no_color=False, depth_is_none=False, hyperlinks=True
        )
        assert caps == Capabilities(color=True, glyph=True, link=True)

    def test_no_color_narrows_color_only(self):
        """NO_COLOR narrows color; glyph and link are untouched (no co-narrowing)."""
        caps = resolve_surface_capabilities(
            _Utf8Stream(), no_color=True, depth_is_none=False, hyperlinks=True
        )
        assert caps == Capabilities(color=False, glyph=True, link=True)

    def test_colorless_depth_narrows_color(self):
        """A colorless destination (ColorDepth.NONE) narrows color — the alt screen
        establishing control support does not imply colour."""
        caps = resolve_surface_capabilities(
            _Utf8Stream(), no_color=False, depth_is_none=True, hyperlinks=True
        )
        assert caps == Capabilities(color=False, glyph=True, link=True)

    def test_ascii_encoding_narrows_glyph(self):
        caps = resolve_surface_capabilities(
            io.StringIO(), no_color=False, depth_is_none=False, hyperlinks=True
        )  # StringIO.encoding is None → unknowable → conservative False
        assert caps.glyph is False

    def test_hyperlinks_off_narrows_link(self):
        """link keeps its serializer-configuration meaning — not bare alt-screen-ness."""
        caps = resolve_surface_capabilities(
            _Utf8Stream(), no_color=False, depth_is_none=False, hyperlinks=False
        )
        assert caps.link is False


# --- The wiring: the frame installs the bracket from the writer, and restores ---


class _CapRecorderApp(Surface):
    """A Surface that records the ambient capabilities + icons during render()."""

    def __init__(self) -> None:
        super().__init__()
        self.seen_caps: Capabilities | None = None
        self.seen_icons: object = None

    def render(self) -> None:
        self.seen_caps = current_capabilities()
        self.seen_icons = current_icons()
        if self._buf is not None:
            Block.text("x", Style()).paint(self._buf, 0, 0)


def _run_one_frame(app: _CapRecorderApp) -> None:
    TestSurface(app, width=10, height=3, input_queue=["q"]).run_to_completion()


def test_frame_installs_bracket_from_writer_and_pairs_ascii_icons():
    """TestSurface's writer is a StringIO (encoding None → glyph False), BASIC
    depth, no_color=False: color/link True, glyph False → ASCII IconSet paired
    for the frame (§9.4)."""
    app = _CapRecorderApp()
    _run_one_frame(app)

    assert app.seen_caps == Capabilities(color=True, glyph=False, link=True)
    assert app.seen_icons is ASCII_ICONS  # glyph False → the §9.4 pairing


def test_frame_bracket_restores_on_exit():
    """The per-frame scope is a bracket: ambient capabilities + icons are restored
    once the frame's render/flush completes."""
    app = _CapRecorderApp()
    _run_one_frame(app)

    assert current_capabilities() == Capabilities()  # default restored
    assert current_icons() is not ASCII_ICONS


def test_utf8_terminal_keeps_unicode_icons():
    """A glyph-capable (UTF-8) terminal keeps its Unicode IconSet — glyph does not
    co-narrow, and no ASCII pairing fires."""
    app = _CapRecorderApp()
    harness = TestSurface(app, width=10, height=3, input_queue=["q"])
    # Represent a real UTF-8 terminal: a glyph-capable stream, colour-capable depth.
    default_icons = current_icons()
    app._writer = Writer(_Utf8Stream(), color_depth=ColorDepth.BASIC, no_color=False)
    harness.run_to_completion()

    assert app.seen_caps == Capabilities(color=True, glyph=True, link=True)
    assert app.seen_icons is default_icons
    assert app.seen_icons is not ASCII_ICONS


def test_no_color_terminal_narrows_color_keeps_glyph():
    """NO_COLOR on a UTF-8 terminal narrows color but not glyph — the Surface reads
    the snapshot from its own writer, so the bracket and that writer agree (§9.1)."""
    app = _CapRecorderApp()
    harness = TestSurface(app, width=10, height=3, input_queue=["q"])
    app._writer = Writer(_Utf8Stream(), color_depth=ColorDepth.BASIC, no_color=True)
    harness.run_to_completion()

    assert app.seen_caps == Capabilities(color=False, glyph=True, link=True)
