"""Tests for the doc lens (doc-IR -> Block, the ``to_block`` projector).

Covers the disclosure predicate (the spine), the Def term-fidelity that proves
the help dissolution, and the width contract.
"""

from painted.core.block import Block
from painted.core.cell import Style
from painted.core.fidelity import Fidelity
from painted.core.zoom import Zoom
from painted.core.doc import (
    Code,
    Def,
    Defs,
    Doc,
    Figure,
    Items,
    Link,
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


class TestDefsTier:
    """Defs density is a tier keyed on eff: names @0, columns @1, +detail @2."""

    def test_compact_shows_terms_only(self):
        """At eff == 0 a Defs collapses to a terse terms-only line (no summaries)."""
        doc = Doc(None, (Defs((Def("-q, --quiet", "Minimal output"),)),))
        # Top-level Defs (min_depth 0) is at eff == 0 only at depth MINIMAL.
        text = _render(doc, depth=Zoom.MINIMAL)
        assert "-q, --quiet" in text
        assert "Minimal output" not in text

    def test_expanded_shows_columns(self):
        doc = Doc(None, (Defs((Def("-q, --quiet", "Minimal output"),)),))
        text = _render(doc, depth=Zoom.SUMMARY)  # eff == 1
        assert "-q, --quiet" in text
        assert "Minimal output" in text


class TestCascade:
    """A Section consumes its min_depth and passes the remaining eff to its body,
    so a Defs nested under a group heading is one tier compacter than a top-level
    Defs at the same global depth (the default-help discriminator)."""

    def test_nested_defs_compacter_than_top_level(self):
        nested = Section("Group", body=(Defs((Def("-q", "Quiet"),)),), min_depth=Zoom.SUMMARY)
        top = Defs((Def("-v", "Verbose"),))
        text = _render(Doc(None, (top, nested)), depth=Zoom.SUMMARY)
        # Top-level Defs (eff 1) shows its summary; the nested Defs (eff 0) does not.
        assert "Verbose" in text
        assert "Quiet" not in text
        assert "-q" in text  # the nested term is still present, just compact

    def test_section_heading_is_binary_at_compact_tier(self):
        """Headings show whenever the section is visible — even at eff == 0 — so a
        gated guide section reveals fully, while help groups stay terse via the
        Defs names-tier, not by hiding headings."""
        doc = Doc(
            None, (Section("Why", body=(Defs((Def("-q", "Quiet"),)),), min_depth=Zoom.SUMMARY),)
        )
        assert "Why" in _render(doc, depth=Zoom.SUMMARY)  # section eff == 0


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

    def test_unresolved_src_is_placeholder(self):
        doc = Doc(None, (Code(src="py:painted.cell:Style#definition"),))
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


class TestInlineLink:
    """The Inline union's first rich member: Link rides the denotation channel.

    ``doc_lens`` renders ``Link.text`` with ``ref=target`` stamped on its
    cells — the same per-cell channel the writer's OSC 8 emission and
    ``render_html``'s anchor wrapping already resolve at delivery. The tuple
    arm's plain ``str`` IS the text span; it stamps nothing.
    """

    @staticmethod
    def _refs(block):
        return {block.cell_ref(x, y) for y in range(block.height) for x in range(block.width)} - {
            None
        }

    def test_link_cells_carry_target_str_spans_do_not(self):
        doc = Doc(None, (Prose(("see ", Link("docs", "fact:1"), " now")),))
        block = doc_lens(doc, fidelity=Fidelity(depth=Zoom.FULL))
        assert block_to_text(block).strip() == "see docs now"
        assert [block.cell_ref(x, 0) for x in range(4, 8)] == ["fact:1"] * 4
        assert block.cell_ref(0, 0) is None
        assert block.cell_ref(9, 0) is None

    def test_link_ref_survives_word_wrap(self):
        doc = Doc(None, (Prose((Link("linked words", "fact:1"),)),))
        block = doc_lens(doc, fidelity=Fidelity(depth=Zoom.FULL), width=6)
        assert block.height >= 2
        assert block.cell_ref(0, 0) == "fact:1"
        assert block.cell_ref(0, 1) == "fact:1"

    def test_def_summary_takes_inline(self):
        doc = Doc(None, (Defs((Def("-v", ("verbose, ", Link("docs", "fact:2"))),)),))
        block = doc_lens(doc, fidelity=Fidelity(depth=Zoom.DETAILED), width=40)
        assert "verbose, docs" in block_to_text(block)
        assert self._refs(block) == {"fact:2"}

    def test_items_entry_takes_inline(self):
        doc = Doc(None, (Items(((Link("a link", "fact:3"),), "plain")),))
        block = doc_lens(doc, fidelity=Fidelity(depth=Zoom.FULL), width=30)
        assert "a link" in block_to_text(block)
        assert self._refs(block) == {"fact:3"}

    def test_plain_str_prose_stamps_nothing(self):
        doc = Doc(None, (Prose("no links here"),))
        block = doc_lens(doc, fidelity=Fidelity(depth=Zoom.FULL), width=20)
        assert self._refs(block) == set()
