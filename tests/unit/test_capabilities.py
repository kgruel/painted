"""Capabilities: ambient render-capability channel with ContextVar delivery."""

from __future__ import annotations

import pytest

from painted.capabilities import (
    Capabilities,
    current_capabilities,
    reset_capabilities,
    use_capabilities,
)
from painted.core.block import Block
from painted.core.cell import Style


def test_capabilities_is_frozen():
    caps = Capabilities()
    with pytest.raises(AttributeError):
        caps.color = False  # type: ignore[misc]


def test_unbracketed_default_is_all_true():
    reset_capabilities()
    caps = current_capabilities()
    assert caps == Capabilities(color=True, glyph=True, link=True)


def test_narrowing_via_bracket():
    reset_capabilities()
    with use_capabilities(Capabilities(color=False, glyph=False, link=False)):
        caps = current_capabilities()
        assert caps.color is False
        assert caps.glyph is False
        assert caps.link is False
    assert current_capabilities() == Capabilities()


def test_setter_semantics_persist_until_changed():
    reset_capabilities()
    use_capabilities(Capabilities(color=False))
    assert current_capabilities().color is False
    use_capabilities(Capabilities(link=False))
    assert current_capabilities() == Capabilities(color=True, glyph=True, link=False)
    reset_capabilities()


def test_nesting_restores_exact_prior_value():
    reset_capabilities()
    outer = Capabilities(color=False)
    use_capabilities(outer)

    with use_capabilities(Capabilities(glyph=False)):
        assert current_capabilities() == Capabilities(glyph=False)

    assert current_capabilities() == outer
    reset_capabilities()


def test_nesting_restores_on_exception():
    reset_capabilities()
    outer = Capabilities(link=False)
    use_capabilities(outer)

    with pytest.raises(RuntimeError):
        with use_capabilities(Capabilities(color=False)):
            assert current_capabilities().color is False
            raise RuntimeError("boom")

    assert current_capabilities() == outer
    reset_capabilities()


def test_reset_capabilities_restores_default():
    use_capabilities(Capabilities(color=False, glyph=False, link=False))
    reset_capabilities()
    assert current_capabilities() == Capabilities()


# --- The honesty gate (§9.3): a declared facet must change output ---


def _ramp_renderer(level: int) -> Block:
    """A tiny test renderer choosing a unicode ramp vs an ASCII ramp by ``glyph``."""

    if current_capabilities().glyph:
        chars = "▁▂▃▄▅▆▇█"
    else:
        chars = "_.-~^*#@"
    return Block.text(chars[level], Style())


def test_glyph_false_changes_rendered_carrier():
    reset_capabilities()

    with use_capabilities(Capabilities(glyph=True)):
        unicode_block = _ramp_renderer(7)

    with use_capabilities(Capabilities(glyph=False)):
        ascii_block = _ramp_renderer(7)

    unicode_char = unicode_block.row(0)[0].char
    ascii_char = ascii_block.row(0)[0].char
    assert unicode_char != ascii_char
    assert unicode_char == "█"
    assert ascii_char == "@"
