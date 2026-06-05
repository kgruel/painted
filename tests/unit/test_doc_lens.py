"""Tests for the doc lens (doc-IR -> Block, the ``to_block`` projector).

Covers the disclosure predicate (the spine), the Def term-fidelity that proves
the help dissolution, and the width contract.
"""

from painted.core.block import Block
from painted.core.cell import Style
from painted.core.fidelity import Fidelity
from painted.core.zoom import Zoom
from painted.views.lens.doc import (
    Code,
    Def,
    Defs,
    Doc,
    Figure,
    Items,
    Prose,
    Section,
    doc_lens,
)
from tests.helpers import block_to_text


def _render(doc, *, depth=1, visible=frozenset(), width=60, lines=0):
    fid = Fidelity(depth=depth, visible=visible, lines=lines)
    return block_to_text(doc_lens(doc, fidelity=fid, width=width))


class TestDisclosureDepth:
    """min_depth gates a node against fidelity.depth (the -v/-vv ladder)."""

    def test_node_hidden_below_min_depth(self):
        doc = Doc(None, (Prose("deep", min_depth=Zoom.DETAILED),))
        assert "deep" not in _render(doc, depth=Zoom.SUMMARY)

    def test_node_shown_at_min_depth(self):
        doc = Doc(None, (Prose("deep", min_depth=Zoom.DETAILED),))
        assert "deep" in _render(doc, depth=Zoom.DETAILED)

    def test_node_shown_above_min_depth(self):
        doc = Doc(None, (Prose("deep", min_depth=Zoom.DETAILED),))
        assert "deep" in _render(doc, depth=Zoom.FULL)


class TestDisclosureTag:
    """tag gates a node against fidelity.visible (opt-in semantic layers)."""

    def test_tagged_node_hidden_without_tag(self):
        doc = Doc(None, (Prose("why", tag="rationale"),))
        assert "why" not in _render(doc, depth=Zoom.FULL)

    def test_tagged_node_shown_with_tag(self):
        doc = Doc(None, (Prose("why", tag="rationale"),))
        assert "why" in _render(doc, visible=frozenset({"rationale"}))

    def test_tag_is_orthogonal_to_depth(self):
        """A tagged node stays hidden at max depth until its tag is requested."""
        doc = Doc(None, (Prose("why", tag="rationale"),))
        assert "why" not in _render(doc, depth=Zoom.FULL, visible=frozenset({"other"}))


class TestDefs:
    """Defs subsume HelpFlag — the term is kept intact (no lossy downcast)."""

    def test_term_preserved_verbatim(self):
        """The old help_args_to_flags dropped `short`; Def keeps the whole term."""
        doc = Doc(None, (Defs((Def("-v, --verbose", "Detailed output"),)),))
        text = _render(doc)
        assert "-v, --verbose" in text
        assert "Detailed output" in text

    def test_detail_hidden_below_detailed(self):
        doc = Doc(None, (Defs((Def("-q", "Quiet", detail="Implies --static."),)),))
        assert "Implies --static." not in _render(doc, depth=Zoom.SUMMARY)

    def test_detail_shown_at_detailed(self):
        doc = Doc(None, (Defs((Def("-q", "Quiet", detail="Implies --static."),)),))
        assert "Implies --static." in _render(doc, depth=Zoom.DETAILED)

    def test_lines_budget_caps_items(self):
        defs = Defs(tuple(Def(f"-{c}", c) for c in "abcde"))
        text = _render(Doc(None, (defs,)), lines=2)
        assert "a" in text and "b" in text
        assert "-e" not in text


class TestItems:
    def test_unordered_marker(self):
        doc = Doc(None, (Items(("alpha", "beta")),))
        text = _render(doc)
        assert "- alpha" in text
        assert "- beta" in text

    def test_ordered_marker(self):
        doc = Doc(None, (Items(("alpha", "beta"), ordered=True),))
        text = _render(doc)
        assert "1. alpha" in text
        assert "2. beta" in text


class TestSection:
    def test_heading_and_hint_rendered(self):
        doc = Doc(None, (Section("Zoom", hint="(what to show)", body=(Prose("body"),)),))
        text = _render(doc)
        assert "Zoom (what to show)" in text
        assert "body" in text

    def test_hidden_section_hides_its_body(self):
        doc = Doc(None, (Section("Gone", body=(Prose("inner"),), min_depth=Zoom.FULL),))
        assert "inner" not in _render(doc, depth=Zoom.SUMMARY)


class TestCode:
    def test_inline_text_rendered(self):
        doc = Doc(None, (Code(text="x = 1"),))
        assert "x = 1" in _render(doc)

    def test_unresolved_ref_is_placeholder(self):
        doc = Doc(None, (Code(ref="py:painted.cell:Style#definition"),))
        assert "py:painted.cell:Style#definition" in _render(doc)


class TestWidthContract:
    """A given width is honored exactly (clip/pad), per the width contract."""

    def test_output_width_matches_request(self):
        doc = Doc(
            "Title that is fairly long and may exceed the width budget here",
            (
                Section(
                    "Group",
                    hint="(hint)",
                    body=(
                        Prose("A paragraph long enough to require word wrapping at this width."),
                        Defs((Def("-v, --verbose", "Detailed output", detail="more"),)),
                        Items(("one", "two"), ordered=True),
                    ),
                ),
            ),
        )
        for width in (20, 40, 80):
            block = doc_lens(doc, fidelity=Fidelity(depth=Zoom.DETAILED), width=width)
            assert block.width == width

    def test_empty_doc_is_empty_block(self):
        block = doc_lens(Doc(None, ()), width=40)
        assert block.height == 0


class TestFigure:
    """Figure embeds a real Block (doc == demo)."""

    def test_block_is_embedded(self):
        fig = Figure(Block.text("LIVE", Style(bold=True)))
        text = _render(Doc(None, (fig,)))
        assert "LIVE" in text

    def test_caption_uses_doc_width_not_block_width(self):
        """Regression: caption was clipped to the (narrow) block's width."""
        long_caption = "A caption that is far wider than the tiny embedded block"
        fig = Figure(Block.text("x", Style()), caption=long_caption)
        text = _render(Doc(None, (fig,)), width=70)
        # The whole caption survives (word-wrapped), not truncated to ~1 col.
        assert "wider than the tiny embedded block" in text
