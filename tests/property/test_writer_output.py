"""Writer-stage laws — the Block -> ANSI/HTML projection, fuzzed.

This is the pipeline stage the demo-goldens never touched: every golden rendered
with `use_ansi=False`, so the writer's SGR generation, color down-conversion, and
HTML escaping have only ever had example-based unit coverage. The appearance tier
(structured char+style snapshots) deliberately bypasses this stage, delegating
"the bytes are correct" to a property — this is that property.

Three totality/safety laws:
  * SGR generation is TOTAL — any (Style, ColorDepth) yields a valid SGR sequence
    (`ESC[<digits and semicolons>m`) or the empty string, never a crash or a
    malformed escape. Covers truecolor->256->16 down-conversion across every depth.
  * PLAIN mode is escape-free — `print_block(use_ansi=False)` emits zero `ESC`,
    for any styled block. (The pipe/redirect contract: no ANSI ever leaks to a file.)
  * HTML is injection-safe and well-formed — `render_html` escapes all cell content
    (no raw `<`/`>` from a cell reaches the output) and emits balanced `<span>` runs,
    for arbitrary cell text including the HTML metacharacters.
"""

from __future__ import annotations

import io
import re

from hypothesis import given
from hypothesis import strategies as st

from painted import Block, Style
from painted.core.cell import NAMED_COLORS, Cell
from painted.core.html import render_html
from painted.core.writer import ColorDepth, Writer, print_block, render_block_ansi
from painted.refs import RefScheme, use_refs

_DEPTHS = list(ColorDepth)
_NAMED = sorted(NAMED_COLORS)

# A color is any value Style.fg/bg accepts: 256-index int, #rrggbb hex, or a name.
_colors = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=255),
    st.from_regex(r"#[0-9a-fA-F]{6}", fullmatch=True),
    st.sampled_from(_NAMED),
)


@st.composite
def _styles(draw: st.DrawFn) -> Style:
    return Style(
        fg=draw(_colors),
        bg=draw(_colors),
        bold=draw(st.booleans()),
        dim=draw(st.booleans()),
        italic=draw(st.booleans()),
        underline=draw(st.booleans()),
        reverse=draw(st.booleans()),
    )


_SGR_BODY = re.compile(r"[0-9;]+")
_TAG = re.compile(r"</?(?:pre|span)[^>]*>")
# Text that includes the HTML metacharacters the escaper must neutralize.
_html_text = st.text(alphabet=st.sampled_from(list("ab 12<>&\"'/=")), max_size=24)


@given(style=_styles(), depth=st.sampled_from(_DEPTHS))
def test_apply_style_is_total_and_valid_sgr(style: Style, depth: ColorDepth) -> None:
    """Any (Style, depth) yields a valid SGR sequence or empty — never a crash."""
    w = Writer(io.StringIO(), color_depth=depth)
    sgr = w.apply_style(style)
    if sgr:
        assert sgr.startswith("\x1b[") and sgr.endswith("m")
        body = sgr[2:-1]
        assert _SGR_BODY.fullmatch(body), f"malformed SGR body {body!r} for {style} @ {depth.name}"


@given(
    color=_colors.filter(lambda c: c is not None), fg=st.booleans(), depth=st.sampled_from(_DEPTHS)
)
def test_color_codes_are_total_digit_params(color, fg: bool, depth: ColorDepth) -> None:
    """Down-conversion of any color at any depth returns digit-only SGR params."""
    w = Writer(io.StringIO(), color_depth=depth)
    codes = w._color_codes(color, foreground=fg, depth=depth)
    assert isinstance(codes, list)
    assert all(c.isdigit() for c in codes), (
        f"non-digit SGR param in {codes} for {color!r} @ {depth.name}"
    )


@given(text=_html_text, style=_styles())
def test_plain_mode_emits_no_escape_sequences(text: str, style: Style) -> None:
    """print_block(use_ansi=False) never leaks an ANSI escape, for any styled block."""
    block = Block.text(text, style)
    buf = io.StringIO()
    print_block(block, buf, use_ansi=False)
    assert "\x1b" not in buf.getvalue()


# A ref is one of: None, a resolvable ``fact:`` ref, an undeclared-scheme ref
# (inert), or a scheme-less ref (inert). Mixing all four exercises the OSC 8
# state machine's open/close transitions alongside its honesty gates.
_ref = st.one_of(
    st.none(),
    st.from_regex(r"fact:[a-z0-9]{1,6}", fullmatch=True),
    st.from_regex(r"other:[a-z0-9]{1,6}", fullmatch=True),
    st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True),
)
# Non-greedy capture of an OSC 8 sequence's params, up to its ST terminator.
_OSC8 = re.compile(r"\x1b\]8;;(.*?)\x1b\\")


@st.composite
def _ref_block(draw: st.DrawFn) -> Block:
    n = draw(st.integers(min_value=1, max_value=8))
    chars = draw(st.lists(st.sampled_from(list("ab12")), min_size=n, max_size=n))
    refs = draw(st.lists(_ref, min_size=n, max_size=n))
    row = [Cell(c, Style()) for c in chars]
    return Block([row], n, refs=[refs])


@given(block=_ref_block())
def test_render_block_ansi_osc8_is_balanced_and_terminated(block: Block) -> None:
    """No unterminated OSC 8 in any ANSI output: every introducer is ST-terminated
    and opens (non-empty URI) exactly balance closes (empty). The resolver
    deviates from its contract for single-char values (empty string instead of
    None) — the writer must fold that into the inert branch, not emit an
    empty-target OSC 8 that desyncs the state machine."""
    w = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR)
    with use_refs(RefScheme("fact", lambda v: "" if len(v) == 1 else f"https://x/{v}")):
        out = render_block_ansi(block, w)

    introducers = out.count("\x1b]8;;")
    matches = _OSC8.findall(out)
    assert len(matches) == introducers, "an OSC 8 introducer was left unterminated"
    opens = sum(1 for m in matches if m)
    closes = sum(1 for m in matches if not m)
    assert opens == closes, f"unbalanced OSC 8: {opens} opens vs {closes} closes"


@given(block=_ref_block())
def test_plain_mode_emits_no_escape_sequences_even_with_refs(block: Block) -> None:
    """Refs never leak into the pipe: PLAIN mode stays escape-free, scheme or not."""
    buf = io.StringIO()
    with use_refs(RefScheme("fact", lambda v: f"https://x/{v}")):
        print_block(block, buf, use_ansi=False)
    assert "\x1b" not in buf.getvalue()


@given(text=_html_text, style=_styles())
def test_render_html_escapes_content_and_balances_spans(text: str, style: Style) -> None:
    """render_html escapes all cell content and emits balanced span runs."""
    block = Block.text(text, style)
    out = render_html(block)

    assert out.count("<span") == out.count("</span>"), "unbalanced <span> runs"

    # Strip the tags we deliberately emit; whatever remains is escaped cell content,
    # so no raw '<' or '>' may survive (the escaper turns them into entities).
    content = _TAG.sub("", out)
    assert "<" not in content, f"unescaped '<' leaked from cell content: {content!r}"
    assert ">" not in content, f"unescaped '>' leaked from cell content: {content!r}"
