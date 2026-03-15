"""Tests for HTML rendering of Blocks."""

from painted import Block, Style
from painted.core.html import render_html


def test_render_html_wide_chars_do_not_emit_placeholder_spaces():
    block = Block.text("A世B", Style())
    assert render_html(block) == '<pre class="painted-output">A世B\n</pre>\n'
