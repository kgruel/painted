"""Tests for HTML rendering of Blocks."""

from painted import Block, Style
from painted.core.html import render_html


def test_render_html_wide_chars_do_not_emit_placeholder_spaces():
    block = Block.text("A世B", Style())
    assert render_html(block) == '<pre class="painted-output">A世B\n</pre>\n'


def test_render_html_named_color_uses_painted_table_not_css_keyword():
    """A named color resolves through painted's ANSI table — same as its int
    index — not the browser's CSS keyword. CSS keywords disagree with painted's
    _BASIC_RGB (keyword "red" is #ff0000, but painted red is #800000), so the
    old keyword passthrough was unfaithful to what painted actually renders.
    """
    # "green" is NAMED_COLORS index 2 -> _BASIC_RGB (0,128,0) -> #008000
    assert "color: #008000" in render_html(Block.text("g", Style(fg="green")))
    # red is index 1 -> #800000, NOT the CSS keyword "red" (#ff0000)
    red = render_html(Block.text("r", Style(fg="red")))
    assert "color: #800000" in red
    assert "color: red" not in red
    # A named color renders identically to its integer index.
    assert render_html(Block.text("c", Style(fg="cyan"))) == render_html(
        Block.text("c", Style(fg=6))
    )
