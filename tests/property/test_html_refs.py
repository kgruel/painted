"""Property laws for HTML anchor delivery (REFS_DESIGN §6, §8).

These live in their own file (not ``test_writer_output.py``) so the ANSI writer
laws and the HTML anchor laws can evolve without collision.

Laws:
  * Anchor balance — every ``<a>`` render_html emits is closed.
  * href escaping — no raw ``<``/``>``/``"`` survives into an ``href`` attribute,
    however adversarial the URI a resolver returns.
  * Inertness — with no declared scheme, a ref-less block renders byte-identically
    whether or not schemes are declared, and never grows an anchor.
"""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from painted import Block, Style, join_horizontal, join_vertical
from painted.core.html import render_html
from painted.refs import RefScheme, reset_refs, use_refs

# Values carrying the exact chars that would break out of an attribute if
# unescaped: quotes, angle brackets, ampersands, plus benign fillers.
_ADVERSARIAL = st.text(alphabet="ab<>&\"':/= ", max_size=8)

# A ref string: sometimes scheme-less (inert), sometimes an "x:" scheme the
# fixture below declares, carrying an adversarial value.
_REF = st.one_of(
    st.none(),
    _ADVERSARIAL,  # may or may not contain a colon → maybe scheme-less
    _ADVERSARIAL.map(lambda v: f"x:{v}"),
)

_CHARS = st.text(alphabet="ab世<>& ", min_size=1, max_size=1)
_HREF_ATTR = re.compile(r'href="([^"]*)"')

# A resolver whose URI is itself adversarial — guarantees the escaper is the only
# thing standing between a resolver and attribute breakout.
_ADVERSARIAL_SCHEME = RefScheme("x", lambda v: f'https://h/{v}?q="<>&')


@st.composite
def _refed_blocks(draw: st.DrawFn) -> Block:
    """A small block whose cells carry a mix of refs (some inert, some 'x:')."""
    n_cols = draw(st.integers(min_value=1, max_value=5))
    n_rows = draw(st.integers(min_value=1, max_value=3))
    rows: list[Block] = []
    for _ in range(n_rows):
        cells = [Block.text(draw(_CHARS), Style(), ref=draw(_REF)) for _ in range(n_cols)]
        rows.append(join_horizontal(*cells))
    return join_vertical(*rows)


@given(_refed_blocks())
def test_anchor_tags_balance(block: Block) -> None:
    with use_refs(_ADVERSARIAL_SCHEME):
        out = render_html(block)
    reset_refs()
    assert out.count("<a ") == out.count("</a>"), f"unbalanced <a> runs: {out!r}"


@given(_refed_blocks())
def test_no_unescaped_quote_or_angle_in_href(block: Block) -> None:
    with use_refs(_ADVERSARIAL_SCHEME):
        out = render_html(block)
    reset_refs()
    for value in _HREF_ATTR.findall(out):
        # The regex already guarantees no raw '"' inside (it delimits the group);
        # angle brackets must have been escaped to entities too.
        assert "<" not in value, f"unescaped '<' in href: {value!r}"
        assert ">" not in value, f"unescaped '>' in href: {value!r}"


@given(st.text(alphabet="abc 世", max_size=12), st.booleans())
def test_refless_block_byte_identical_regardless_of_schemes(text: str, declare: bool) -> None:
    # A block with NO refs renders identically whether or not schemes exist —
    # the byte-for-byte guarantee that upgrading without declaring a scheme is a
    # no-op (REFS_DESIGN §9).
    block = Block.text(text, Style(fg="green"))

    reset_refs()
    baseline = render_html(block)

    if declare:
        with use_refs(_ADVERSARIAL_SCHEME):
            under_scheme = render_html(block)
        reset_refs()
    else:
        under_scheme = render_html(block)

    assert under_scheme == baseline
    assert "<a " not in under_scheme
