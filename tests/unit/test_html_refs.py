"""HTML anchor delivery for refs (REFS_DESIGN §6).

``render_html`` wraps cells whose ref resolves to a URI through an ambient
``RefScheme`` in an ``<a href>`` anchor. The seam is read ambiently (no
signature change); an undeclared/scheme-less/declined ref is inert — no anchor,
no data-attribute. ``<a>`` wraps ``<span>``, never interleaved; adjacent cells
sharing a resolved href share one anchor; an anchor never crosses a row.
"""

from __future__ import annotations

import pytest

from painted import Block, Style, join_horizontal, join_vertical
from painted.core.html import render_html
from painted.refs import RefScheme, reset_refs, use_refs

_PRE = '<pre class="painted-output">'


@pytest.fixture
def fact_scheme():
    """A declared ``f`` scheme resolving ``f:v`` → ``u/v``; reset after."""
    with use_refs(RefScheme("f", lambda v: f"u/{v}")):
        yield
    reset_refs()


def test_resolved_ref_wraps_content_in_anchor(fact_scheme):
    out = render_html(Block.text("hello", Style(), ref="f:1"))
    assert out == f'{_PRE}<a href="u/1">hello</a>\n</pre>\n'


def test_anchor_wraps_span_never_interleaved(fact_scheme):
    # Styled + refed cell: <a> is the outer tag, <span> the inner.
    out = render_html(Block.text("x", Style(fg="red"), ref="f:1"))
    assert out == f'{_PRE}<a href="u/1"><span style="color: #c00000">x</span></a>\n</pre>\n'


def test_coalesces_across_style_change_within_one_ref(fact_scheme):
    # One ref, two style runs → one anchor, two spans.
    block = join_horizontal(
        Block.text("AB", Style(fg="red"), ref="f:1"),
        Block.text("CD", Style(fg="green"), ref="f:1"),
    )
    out = render_html(block)
    assert out.count("<a ") == 1
    assert out.count("</a>") == 1
    assert out.count("<span") == 2
    assert '<a href="u/1"><span' in out


def test_ref_change_within_one_style_run_splits_anchors(fact_scheme):
    # Constant style, ref changes → two anchors back-to-back.
    block = join_horizontal(
        Block.text("AB", Style(), ref="f:1"),
        Block.text("CD", Style(), ref="f:2"),
    )
    out = render_html(block)
    assert out == f'{_PRE}<a href="u/1">AB</a><a href="u/2">CD</a>\n</pre>\n'


def test_wide_char_cell_inside_anchor(fact_scheme):
    # Wide glyph emits one char (no placeholder space) inside the anchor.
    out = render_html(Block.text("世", Style(), ref="f:1"))
    assert out == f'{_PRE}<a href="u/1">世</a>\n</pre>\n'


def test_anchor_does_not_cross_row_boundary(fact_scheme):
    block = join_vertical(
        Block.text("A", Style(), ref="f:1"),
        Block.text("B", Style(), ref="f:1"),
    )
    out = render_html(block)
    # Same href both rows, but each row's anchor opens and closes within the row.
    assert out == f'{_PRE}<a href="u/1">A</a>\n<a href="u/1">B</a>\n</pre>\n'
    assert out.count("<a ") == 2
    assert out.count("</a>") == 2


def test_adjacent_ref_then_inert_then_bare(fact_scheme):
    block = join_horizontal(
        Block.text("A", Style(), ref="f:1"),
        Block.text("B", Style(), ref="nope:1"),  # undeclared scheme → inert
        Block.text("C", Style()),  # no ref
    )
    out = render_html(block)
    assert out == f'{_PRE}<a href="u/1">A</a>BC\n</pre>\n'


def test_per_cell_grid_takes_precedence_over_uniform(fact_scheme):
    # A per-cell grid drives anchors cell-by-cell.
    block = Block(
        [[Block.text("XY", Style()).row(0)[i] for i in range(2)]], 2, refs=[["f:1", None]]
    )
    out = render_html(block)
    assert out == f'{_PRE}<a href="u/1">X</a>Y\n</pre>\n'


# --- Inert cases table -------------------------------------------------------
# Every path that must emit NO anchor and NO data-attribute. Output must be
# byte-identical to the same block with no ref at all.


@pytest.mark.parametrize(
    "ref",
    [
        "sidebar",  # scheme-less (no colon)
        "undeclared:1",  # scheme no RefScheme declares
        "f:decline",  # declared scheme whose resolver returns None
    ],
)
def test_inert_refs_emit_no_anchor(ref):
    with use_refs(RefScheme("f", lambda v: None if v == "decline" else f"u/{v}")):
        refed = render_html(Block.text("hi", Style(), ref=ref))
    plain = render_html(Block.text("hi", Style()))
    assert "<a " not in refed
    assert "data-ref" not in refed
    assert refed == plain
    reset_refs()


def test_no_declared_schemes_is_byte_identical():
    # An app that declares nothing sees byte-identical output for refed blocks.
    reset_refs()
    refed = render_html(Block.text("hi", Style(fg="green"), ref="f:1"))
    plain = render_html(Block.text("hi", Style(fg="green")))
    assert refed == plain


# --- Escaping ----------------------------------------------------------------


def test_href_escapes_adversarial_resolver_output():
    # Quotes/angles/ampersands in a resolver's URI must not break the attribute.
    with use_refs(RefScheme("x", lambda v: 'https://h/?a=1&b="><script>')):
        out = render_html(Block.text("hi", Style(), ref="x:1"))
    reset_refs()
    assert 'href="https://h/?a=1&amp;b=&quot;&gt;&lt;script&gt;"' in out
    # No raw quote/angle escaped out of the attribute value.
    assert '"><script>' not in out


def test_resolver_that_raises_propagates_unwrapped():
    def boom(_v: str) -> str:
        raise RuntimeError("resolver fault")

    with use_refs(RefScheme("x", boom)):
        with pytest.raises(RuntimeError, match="resolver fault"):
            render_html(Block.text("hi", Style(), ref="x:1"))
    reset_refs()


def test_ref_resolved_once_per_render():
    calls: list[str] = []

    def counting(v: str) -> str:
        calls.append(v)
        return f"u/{v}"

    # Same ref on many cells across rows → resolver called once for that ref.
    block = join_vertical(
        Block.text("AAAA", Style(), ref="f:1"),
        Block.text("BBBB", Style(), ref="f:1"),
    )
    with use_refs(RefScheme("f", counting)):
        render_html(block)
    reset_refs()
    assert calls == ["1"]
