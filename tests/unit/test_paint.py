"""Tests for paint() — the single entry point (0.8+) — and the deprecated show() alias.

Covers the name and closed kwarg surface, the file-aware ANSI detection (the
isatty fix), the transcription front door (dict/list identity, declared schemas
— dataclass/NamedTuple/Enum — and recursion that never re-infers at depth), the
0.8 deferred base cases (Exception→str, abstract Mapping/Sequence→str; §3), the
NO_COLOR contract, and show()'s warn-and-narrow deprecation (warns, drops
format, retains its inferring body). Consolidates the former test_show.py.
"""

import io

import pytest

import painted
from painted import Block, Style, Zoom, paint, show
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


def test_paint_block_ignores_an_explicit_lens():
    """Precedence pin (docstring): a Block is already painted, so paint() delivers
    it directly and never consults ``lens=``. Inherited from show() and
    defensible — there is nothing for a lens to interpret on a Block."""

    def boom(data, zoom, width):
        raise AssertionError("lens called for a Block subject")

    buf = io.StringIO()
    paint(Block.text("direct", Style()), lens=boom, file=buf)
    assert "direct" in buf.getvalue()


def test_paint_scalar_with_explicit_lens_calls_the_lens():
    """The scalar short-circuit is guarded by ``lens is None`` — an explicit lens
    overrides it. Load-bearing: dropping that guard would str() the scalar before
    the lens ran, so the wrapped form would never appear."""

    def wrap(data, zoom, width):
        return Block.text(f"[{data}]", Style())

    buf = io.StringIO()
    paint("hi", lens=wrap, file=buf)
    assert "[hi]" in buf.getvalue()


def test_paint_mapping_transcribes_keys_and_values():
    """dict → key/value (stable across Slice 1→2; only inference changes later)."""
    buf = io.StringIO()
    paint({"status": "ok"}, file=buf)
    out = buf.getvalue()
    assert "status" in out and "ok" in out


# --------------------------------------------------------------------------- #
# paint() — zoom (the disclosure channel) reaches the render, unpinned
# --------------------------------------------------------------------------- #
# These use a NON-DEFAULT zoom (SUMMARY, not the DETAILED=2 default): the entry
# points resolve `zoom = 2 if zoom is None else zoom`, and mutating that to a
# flat `zoom = 2` must FAIL here. A test that passed DETAILED would be blind to
# exactly that mutation (2 == 2) — the gap that let it slip through before.


def test_paint_passes_zoom_through_to_the_lens():
    """The disclosure channel reaches the lens verbatim — a spy captures it.

    Load-bearing against `zoom = 2` (dropping the caller's value): SUMMARY (1)
    is not the default, so a flattened zoom would arrive as 2 and fail here.
    """
    received: dict = {}

    def spy_lens(data, zoom, width):
        received["zoom"] = zoom
        return Block.text("ok", Style())

    buf = io.StringIO()
    paint("hello", zoom=Zoom.SUMMARY, lens=spy_lens, file=buf)
    assert received["zoom"] == Zoom.SUMMARY


def test_show_passes_zoom_through_to_the_lens():
    """The show() alias resolves zoom the same way — pinned so the shared
    `zoom = 2 if zoom is None else zoom` cannot silently flatten there either."""
    received: dict = {}

    def spy_lens(data, zoom, width):
        received["zoom"] = zoom
        return Block.text("ok", Style())

    buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show("hello", zoom=Zoom.SUMMARY, lens=spy_lens, file=buf)
    assert received["zoom"] == Zoom.SUMMARY


def test_paint_summary_zoom_is_compact_one_line():
    """zoom=SUMMARY collapses a dict to one inline `key: value` line — not the
    DETAILED key/value table. A flattened `zoom = 2` would render the table
    (multiple lines), so the single-line assertion catches it."""
    buf = io.StringIO()
    paint({"host": "prod-1", "status": "ok"}, zoom=Zoom.SUMMARY, file=buf)
    out = buf.getvalue()
    assert "host: prod-1" in out
    assert out.count("\n") == 1  # single line


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


def test_show_no_args_prints_blank_line_still_warning():
    """The no-arg blank-line affordance survives on the alias — and still warns
    (restored from the dropped test_show.py pin)."""
    buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show(file=buf)
    assert buf.getvalue() == "\n"


def test_show_str_enum_drifts_to_type_member():
    """Accepted 0.8 drift (§9): show() shares paint()'s scalar exclusion, so a
    top-level StrEnum now renders Type.MEMBER (was str(value))."""
    from enum import Enum

    class Color(str, Enum):
        RED = "red"

    buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show(Color.RED, file=buf)
    assert buf.getvalue().strip() == "Color.RED"


def test_show_int_enum_drifts_to_type_member():
    """The IntEnum half of the same accepted drift (§9)."""
    from enum import IntEnum

    class Level(IntEnum):
        HIGH = 9

    buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show(Level.HIGH, file=buf)
    assert buf.getvalue().strip() == "Level.HIGH"


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


def test_show_retains_inferring_body_where_paint_transcribes():
    """§9's reason show() is a *retained* alias, not a thin forward: its default
    is the shape_lens *inferring* body, which paint() dropped for transcription.
    show([1,2,3]) infers a chart; paint([1,2,3]) transcribes items. This is the
    one behaviour that cannot forward to paint()."""
    show_buf = io.StringIO()
    with pytest.warns(DeprecationWarning):
        show([1, 2, 3], file=show_buf)
    assert _is_chart(show_buf.getvalue())  # show still infers a chart
    assert not _is_chart(_paint([1, 2, 3]))  # paint transcribes items


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


def test_transcription_refuses_charts_recursively():
    """RECURSIVE (§3): inference never re-enters at depth. At the nested zoom a
    chart is a bare sparkline with no "[N values]" header, so digit-presence —
    not _is_chart — is the mode- and zoom-safe discriminator: a sparkline has no
    digits, transcribed items keep theirs. Each case exercises a distinct
    recursion seam that must thread `infer`.
    """
    cases = {
        "dict single-key fast path": _paint({"only": [11, 22, 33]}),
        "dict multi-item loop": _paint({"xs": [11, 22, 33], "n": 5}),
        "list item seam": _paint([[11, 22, 33]]),
    }
    for label, out in cases.items():
        assert "11" in out and "22" in out and "33" in out, f"{label}: {out!r}"


def test_nested_dict_transcribes_not_tree():
    """A nested dict transcribes as nested key/value, not a tree drawing.

    The tree the inferring path would draw *also* contains every key/value, so
    key-presence alone cannot tell transcription from a tree. The load-bearing
    assertion is the contrast against the inferring path plus the absence of the
    tree's own artifacts (a synthetic ``root`` node and branch glyphs).
    """
    from painted.views import shape_lens

    out = _paint({"outer": {"inner": "v"}})
    assert "outer" in out and "inner" in out and "v" in out
    assert out != _paint({"outer": {"inner": "v"}}, lens=shape_lens)
    assert "root" not in out and "--" not in out  # no tree drawing


def test_bare_tuple_transcribes_as_items():
    out = _paint((10, 20, 30))
    assert not _is_chart(out)
    assert "10" in out and "20" in out and "30" in out


def test_frozenset_transcribes_as_set_tags():
    """frozenset is NOT a subclass of set, so the set branch must name it
    explicitly — otherwise it falls through to the str() fallback and renders
    'frozenset({...})'. Load-bearing: the tag form appears, the repr form does
    not."""
    out = _paint(frozenset({1, 2, 3}))
    assert "[1]" in out and "[2]" in out and "[3]" in out  # set-tag form
    assert "frozenset(" not in out  # not the str() fallback


def test_tuple_count_label_is_honest_at_low_zoom():
    """At zoom<=0 a sequence renders its type + count. A bare tuple must report
    'tuple[N]', not 'list[N]' — _render_list receives list(content) and would
    otherwise misname it."""
    assert _paint((1, 2, 3), zoom=0).strip() == "tuple[3]"
    assert _paint([1, 2, 3], zoom=0).strip() == "list[3]"


def test_tuple_item_summarizes_like_a_list_item():
    """A tuple *item* inside a list at zoom 1 must summarize as 'tuple[N]' —
    mirroring the list summary — not a raw repr byte-sliced to 10 chars."""
    out = _paint([(1, 2), (3, 4)], zoom=1)
    assert "tuple[2]" in out
    assert "(1, 2)" not in out  # not the raw-repr slice


def test_frozenset_item_summarizes_like_a_set_item():
    """A frozenset *item* inside a list at zoom 1 must summarize as 'set[N]' —
    frozenset is not a `set` subclass, so an unwidened isinstance falls through
    to the raw repr byte-sliced to 10 chars ('frozenset(')."""
    out = _paint([frozenset({1, 2}), frozenset({3, 4})], zoom=1)
    assert "set[2]" in out
    assert "frozenset(" not in out  # not the raw-repr slice


# --- Deferred base cases (PAINT_DESIGN §3, ratified 2026-07-06) -------------
# These pin behaviours that are DEFERRED in 0.8, not bugs. Whoever implements
# the deferred feature updates a failing test here on purpose.


def test_exception_renders_message_not_traceback_deferred():
    """§3 defers Exception→render_traceback: paint(exc) prints str(exc), not a
    traceback. Load-bearing: the message is present and the traceback header
    (the exception type) is absent — a render_traceback would show 'ValueError'."""
    out = _paint(ValueError("boom"))
    assert out.strip() == "boom"
    assert "ValueError" not in out  # not the traceback rendering


def test_abstract_mapping_renders_via_str_deferred():
    """§3 keys container dispatch on concrete dict/list/tuple. A MappingProxyType
    is a Mapping but not a dict, so it renders via str() — contrast against the
    concrete dict, which transcribes."""
    from types import MappingProxyType

    proxy = _paint(MappingProxyType({"a": 1, "b": 2}))
    assert proxy != _paint({"a": 1, "b": 2})  # proxy str()s, dict transcribes
    assert "{" in proxy and "'a'" in proxy  # the str() form, not 'a: 1'


def test_abstract_sequence_renders_via_str_deferred():
    """range is a Sequence but not a list/tuple → str(), not transcribed items."""
    out = _paint(range(3))
    assert "range(" in out
    assert out != _paint([0, 1, 2])  # list transcribes, range str()s


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


def test_str_enum_transcribes_as_member_not_value():
    """StrEnum subclasses str — the same scalar-exclusion path as IntEnum (a
    production StrEnum, cursor.CursorMode, ships today)."""
    from enum import Enum

    class Color(str, Enum):
        RED = "red"

    assert _paint(Color.RED).strip() == "Color.RED"


def test_flag_zero_and_composite_are_not_type_dot_none():
    """A zero/composite Flag has `.name is None` — must fall back to str(), never
    the misleading 'Type.None'. Guards the _render_enum fix."""
    from enum import Flag, auto

    class Perm(Flag):
        R = auto()
        W = auto()

    assert _paint(Perm(0)).strip() == "Perm(0)"  # str() fallback, not 'Perm.None'
    assert _paint(Perm.R | Perm.W).strip() == "Perm.R|W"  # named composite


def test_dataclass_container_field_recurses_as_transcription():
    """WIDE + RECURSIVE intersection: a declared-schema field that is a container
    transcribes — its numeric list is items, not a chart (exercises the
    dataclass -> _render_dict -> value recursion seam)."""
    from dataclasses import dataclass

    @dataclass
    class Metrics:
        label: str
        samples: list

    out = _paint(Metrics("lat", [11, 22, 33]))
    assert "label" in out and "lat" in out
    assert "11" in out and "22" in out and "33" in out  # samples items, not charted


def test_explicit_chart_lens_still_interprets():
    from painted.views import chart_lens

    assert _is_chart(_paint([1, 2, 3], lens=chart_lens))


def test_explicit_shape_lens_still_infers():
    """lens=shape_lens restores the old inferring behaviour (a chart)."""
    from painted.views import shape_lens

    assert _is_chart(_paint([1, 2, 3], lens=shape_lens))


def test_transcribe_direct_refuses_chart_at_depth():
    """Unit-level: transcribe() never re-enters inference at depth. Distinct
    two-digit values a sparkline can't coincidentally contain."""
    import io as _io

    from painted.core.writer import print_block
    from painted.views.lens.shape import transcribe

    buf = _io.StringIO()
    print_block(transcribe({"series": [11, 22, 33]}, 2, 60), buf, use_ansi=False)
    out = buf.getvalue()
    assert "11" in out and "22" in out and "33" in out, out


def _sgr(writer: Writer, style: Style) -> str:
    return writer.apply_style(style)


def test_no_color_flag_suppresses_colour_keeps_bold():
    w = Writer(io.StringIO(), no_color=True)
    sgr = _sgr(w, Style(fg="red", bold=True))
    assert "1" in sgr  # bold survives
    assert "31" not in sgr  # red (base 30 + 1) is gone


def test_colour_present_when_not_no_color():
    # Force a positive depth to isolate the NO_COLOR axis: a non-TTY StringIO would
    # otherwise resolve ColorDepth.NONE, which now suppresses colour on its own (§9.4).
    w = Writer(io.StringIO(), no_color=False, color_depth=ColorDepth.BASIC)
    assert "31" in _sgr(w, Style(fg="red"))


def test_no_color_env_present_and_nonempty_suppresses(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    w = Writer(io.StringIO())  # ambient resolution
    assert "31" not in _sgr(w, Style(fg="red"))


def test_no_color_env_empty_is_treated_as_unset(monkeypatch):
    """no-color.org: honoured only when present AND non-empty."""
    monkeypatch.setenv("NO_COLOR", "")
    # Force a positive depth to isolate the NO_COLOR axis from the destination's own
    # colorlessness: a non-TTY StringIO resolves ColorDepth.NONE, now suppression (§9.4).
    w = Writer(io.StringIO(), color_depth=ColorDepth.BASIC)
    assert "31" in _sgr(w, Style(fg="red"))


def test_forced_color_depth_still_honours_env_no_color(monkeypatch):
    """A forced color_depth is orthogonal to NO_COLOR — it must NOT bypass it.
    PaintedHandler snapshots a *detected* depth and passes it as a forced depth;
    coupling NO_COLOR to color_depth made all logging ignore NO_COLOR. The escape
    hatch for callers that need colour regardless of env is explicit no_color=False."""
    monkeypatch.setenv("NO_COLOR", "1")
    w = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR)
    assert "31" not in _sgr(w, Style(fg="red"))  # env wins over a forced depth
    w2 = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR, no_color=False)
    assert "31" in _sgr(w2, Style(fg="red"))  # explicit opt-out is the escape hatch


def test_explicit_no_color_beats_forced_depth():
    w = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR, no_color=True)
    assert "31" not in _sgr(w, Style(fg="red"))


def test_painted_handler_honours_no_color(monkeypatch):
    """The real-world NO_COLOR path: PaintedHandler renders each record through a
    Writer built with a FORCED (snapshotted) color_depth — exactly what it does on
    every emit. NO_COLOR must reach that forced-depth writer, or piped/CI logs
    carry the ANSI colour the user asked to suppress.

    The pre-fix vacuous version passed a StringIO whose *detected* depth was NONE,
    so the handler took the plain-text branch and never exercised the coloured
    writer at all — it would pass even if the writer ignored NO_COLOR entirely.
    Forcing TRUECOLOR drives the SGR path: under NO_COLOR every emitted SGR
    parameter must be a non-colour attribute (reset / bold / dim / …), never a
    colour code — and at least one styling attribute must survive, proving the
    coloured path ran (rather than the assertion passing on empty output).
    """
    import logging
    import re

    from painted.diagnostics import PaintedHandler

    monkeypatch.setenv("NO_COLOR", "1")
    buf = io.StringIO()
    # Force a depth, as the handler does when it snapshots a *detected* depth.
    handler = PaintedHandler(stream=buf, color_depth=ColorDepth.TRUECOLOR)
    logger = logging.getLogger("test_paint_no_color_forced_depth")
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("a log line that must not be coloured")

    out = buf.getvalue()
    # Every SGR parameter must be a non-colour attribute: reset(0) or an
    # intensity/underline/reverse flag. A colour would surface as 30-37 / 40-47 /
    # 90-97 / 38 / 48 (or the extended 5;n · 2;r;g;b forms), all of which NO_COLOR
    # must strip even under a forced depth.
    flags = {"0", "1", "2", "3", "4", "7"}
    params = [p for seq in re.findall(r"\x1b\[([0-9;]*)m", out) for p in seq.split(";")]
    colour = [p for p in params if p not in flags]
    assert not colour, f"NO_COLOR must strip fg/bg even under a forced depth; saw {colour}"
    # A styling attribute (dim from the muted timestamp) survived — the coloured
    # SGR path ran, so the "no colour" assertion above isn't vacuously green.
    assert any(p in {"1", "2", "3", "4", "7"} for p in params)
