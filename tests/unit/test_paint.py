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


def test_show_format_is_inert_on_scalar():
    """format has no effect at all — a scalar renders identically with or without it.

    Guards against the coincidence that str(42) happens to parse as JSON: the
    assertion is equality-to-no-format, not a JSON shape.
    """
    plain, with_fmt = io.StringIO(), io.StringIO()
    with pytest.warns(DeprecationWarning):
        show(42, file=plain)
    with pytest.warns(DeprecationWarning):
        show(42, format="json", file=with_fmt)
    assert with_fmt.getvalue() == plain.getvalue() == "42\n"


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


# --------------------------------------------------------------------------- #
# Transcription (Slice 2) — no-lens paint() transcribes the declared shape,
# never inferring arrangement, at any depth.
# --------------------------------------------------------------------------- #


def _is_chart(text: str) -> bool:
    # chart_lens emits a "[N values, min–max]" header in every colour mode;
    # transcription (items / key-value) never does. Robust across ANSI/plain —
    # plain-mode charts use ASCII bar glyphs, so glyph-matching is not mode-safe.
    return "values" in text


def _paint(subject, **kw) -> str:
    buf = io.StringIO()
    paint(subject, file=buf, **kw)
    return buf.getvalue()


def test_numeric_list_transcribes_as_items_not_chart():
    out = _paint([1, 2, 3])
    assert not _is_chart(out)
    assert "1" in out and "2" in out and "3" in out


def test_nested_numeric_list_stays_items_recursive():
    """The refusal is recursive — a numeric list nested in a dict is NOT charted."""
    out = _paint({"xs": [1, 2, 3]})
    assert not _is_chart(out)
    assert "xs" in out


def test_nested_dict_transcribes_not_tree():
    """A nested dict transcribes as nested key/value, not a tree drawing."""
    out = _paint({"outer": {"inner": "v"}})
    assert "outer" in out and "inner" in out and "v" in out


def test_bare_tuple_transcribes_as_items():
    out = _paint((10, 20, 30))
    assert not _is_chart(out)
    assert "10" in out and "20" in out and "30" in out


def test_dataclass_transcribes_declared_fields():
    from dataclasses import dataclass

    @dataclass
    class Server:
        name: str
        port: int

    out = _paint(Server("api", 8080))
    assert "name" in out and "api" in out and "port" in out and "8080" in out


def test_namedtuple_transcribes_declared_fields():
    from typing import NamedTuple

    class Point(NamedTuple):
        x: int
        y: int

    out = _paint(Point(3, 4))
    assert "x" in out and "y" in out and "3" in out and "4" in out


def test_plain_enum_transcribes_as_type_member():
    from enum import Enum

    class Status(Enum):
        DOWN = "down"

    assert _paint(Status.DOWN).strip() == "Status.DOWN"


def test_int_enum_transcribes_as_member_not_value():
    """IntEnum subclasses int but is a declared schema — Type.MEMBER, not '9'.

    Guards the display.py scalar-short-circuit exclusion: without it, isinstance
    int would str() the value before the renderer's Enum branch.
    """
    from enum import IntEnum

    class Level(IntEnum):
        HIGH = 9

    assert _paint(Level.HIGH).strip() == "Level.HIGH"


def test_explicit_chart_lens_still_interprets():
    from painted.views import chart_lens

    assert _is_chart(_paint([1, 2, 3], lens=chart_lens))


def test_explicit_shape_lens_still_infers():
    """lens=shape_lens restores the old inferring behaviour (a chart)."""
    from painted.views import shape_lens

    assert _is_chart(_paint([1, 2, 3], lens=shape_lens))


def test_transcribe_recurses_as_transcription_directly():
    """Unit-level: transcribe() never re-enters inference at depth."""
    import io as _io

    from painted.core.writer import print_block
    from painted.views.lens.shape import transcribe

    buf = _io.StringIO()
    print_block(transcribe({"series": [4, 8, 2]}, 2, 40), buf, use_ansi=False)
    assert not _is_chart(buf.getvalue())


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
