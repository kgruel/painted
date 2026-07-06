"""Tests for paint() — the single entry point (0.8+) — and the deprecated show() alias.

Slice 1 scope: the name, the closed kwarg surface, the file-aware ANSI detection
(the isatty fix), and show()'s warn-and-narrow deprecation. The transcription
front door (dict/list identity, declared schemas, recursion) lands in Slice 2 —
here paint() still routes its no-lens default through shape_lens, so this file
does not pin the rendered *shape* of containers (that changes in Slice 2).
"""

import io

import pytest

import painted
from painted import Block, Style, paint, show
from painted.core.writer import ColorDepth, Writer


class _FakeTTY(io.StringIO):
    """A StringIO that claims to be a terminal — to drive the ANSI path."""

    def isatty(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# paint() — exported and closed kwarg surface
# --------------------------------------------------------------------------- #


def test_paint_is_exported_at_package_root():
    assert "paint" in painted.__all__
    assert painted.paint is paint


def test_paint_signature_is_closed_no_format():
    """The kwarg surface admits nothing outside the meaning channels + file.

    format left paint() entirely (§8): passing it is a TypeError, not a silent
    accept — proves the closure law is enforced by the signature.
    """
    with pytest.raises(TypeError):
        paint({"a": 1}, format="json")  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# paint() — the base-case paths
# --------------------------------------------------------------------------- #


def test_paint_no_arg_prints_blank_line():
    """The sole print() parity concession (§11 Slice 1 (a))."""
    buf = io.StringIO()
    paint(file=buf)
    assert buf.getvalue() == "\n"


def test_paint_scalar_is_str_plus_newline():
    buf = io.StringIO()
    paint("deploying", file=buf)
    assert buf.getvalue() == "deploying\n"


def test_paint_none_scalar_prints_none():
    buf = io.StringIO()
    paint(None, file=buf)
    assert buf.getvalue() == "None\n"


def test_paint_block_is_delivered():
    buf = io.StringIO()
    paint(Block.text("hello", Style()), file=buf)
    assert "hello" in buf.getvalue()


def test_paint_mapping_transcribes_keys_and_values():
    """dict → key/value (stable across Slice 1→2; only inference changes later)."""
    buf = io.StringIO()
    paint({"status": "ok"}, file=buf)
    out = buf.getvalue()
    assert "status" in out and "ok" in out


# --------------------------------------------------------------------------- #
# paint() — the isatty fix (§8 contract: ANSI is a property of the destination)
# --------------------------------------------------------------------------- #


def test_paint_to_stringio_is_plain():
    """A non-tty destination renders plain — no ANSI escapes."""
    buf = io.StringIO()
    paint(Block.text("hi", Style(fg="red")), file=buf)
    assert "\x1b" not in buf.getvalue()


def test_paint_to_a_tty_destination_emits_ansi():
    tty = _FakeTTY()
    paint(Block.text("hi", Style(fg="red")), file=tty)
    assert "\x1b" in tty.getvalue()


def test_paint_reads_the_resolved_file_not_stdout(monkeypatch):
    """The fix: even when stdout IS a tty, paint(x, file=StringIO()) stays plain.

    The pre-0.8 helper read sys.stdout.isatty() and ignored the passed file, so
    this would have emitted ANSI. paint() consults the destination.
    """
    monkeypatch.setattr("sys.stdout", _FakeTTY())
    buf = io.StringIO()
    paint(Block.text("hi", Style(fg="red")), file=buf)
    assert "\x1b" not in buf.getvalue()


# --------------------------------------------------------------------------- #
# show() — deprecated, warn-and-narrow
# --------------------------------------------------------------------------- #


def test_show_emits_deprecation_warning():
    buf = io.StringIO()
    with pytest.warns(DeprecationWarning, match="paint"):
        show({"a": 1}, file=buf)


def test_show_no_longer_honours_format_json():
    """Warn-and-narrow: format is accepted (no TypeError) but ignored — not JSON."""
    buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show({"a": 1}, format="json", file=buf)
    out = buf.getvalue()
    assert out.strip() != '{"a": 1}'  # would be json.dumps if format were honoured
    assert "a" in out  # it rendered instead


def test_show_stays_bug_compatible_reads_stdout(monkeypatch):
    """show() preserves the pre-0.8 sys.stdout-based detection (the un-fixed bug).

    Contrast with test_paint_reads_the_resolved_file_not_stdout: same inputs,
    show() emits ANSI because it reads stdout, paint() stays plain.
    """
    monkeypatch.setattr("sys.stdout", _FakeTTY())
    buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show(Block.text("hi", Style(fg="red")), file=buf)
    assert "\x1b" in buf.getvalue()


# --------------------------------------------------------------------------- #
# NO_COLOR — ambient colour-off in the writer layer (§8, Q4)
# --------------------------------------------------------------------------- #


def _sgr(writer: Writer, style: Style) -> str:
    return writer.apply_style(style)


def test_no_color_flag_suppresses_colour_keeps_bold():
    w = Writer(io.StringIO(), no_color=True)
    sgr = _sgr(w, Style(fg="red", bold=True))
    assert "1" in sgr  # bold survives
    assert "31" not in sgr  # red (base 30 + 1) is gone


def test_colour_present_when_not_no_color():
    w = Writer(io.StringIO(), no_color=False)
    assert "31" in _sgr(w, Style(fg="red"))


def test_no_color_env_present_and_nonempty_suppresses(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    w = Writer(io.StringIO())  # ambient resolution
    assert "31" not in _sgr(w, Style(fg="red"))


def test_no_color_env_empty_is_treated_as_unset(monkeypatch):
    """no-color.org: honoured only when present AND non-empty."""
    monkeypatch.setenv("NO_COLOR", "")
    w = Writer(io.StringIO())
    assert "31" in _sgr(w, Style(fg="red"))


def test_forced_color_depth_opts_out_of_ambient_no_color(monkeypatch):
    """An explicit color_depth is a programmatic override — NO_COLOR does not
    reach forced-depth callers (keeps existing colour tests deterministic)."""
    monkeypatch.setenv("NO_COLOR", "1")
    w = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR)
    assert "31" in _sgr(w, Style(fg="red"))


def test_explicit_no_color_beats_forced_depth():
    w = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR, no_color=True)
    assert "31" not in _sgr(w, Style(fg="red"))
