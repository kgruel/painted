"""Tests for the doc-IR publisher (doc node tree -> semantic HTML).

Pins the OCR-trap contract: chrome arrives as real web semantics read straight
off the tree (a nested Section is an <h3>, never a bold span), while the Figure
island is the one node that routes through Block -> HTML. Disclosure must agree
with the lens — both projectors iterate the same visible_body walk.
"""

from __future__ import annotations

from painted.core.block import Block
from painted.core.cell import Style
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
from painted.core.fidelity import Fidelity
from painted.core.zoom import Zoom

from painted._doc_pages import DOCS
from tests.helpers import block_to_text
from painted.publish import published_fidelity, to_html
from painted.refs import RefScheme, use_refs
from tools.outputgen import emit_doc_pages


def _full(doc: Doc) -> str:
    return to_html(doc, fidelity=Fidelity(depth=Zoom.FULL))


class TestSemanticChrome:
    """The OCR-trap pin: structure is read off the tree, not recovered from cells."""

    def test_title_is_h1(self):
        html = _full(Doc("My Title", ()))
        assert "<h1>My Title</h1>" in html
        assert "font-weight: bold" not in html  # not a styled span

    def test_section_heading_level_is_tree_depth(self):
        inner = Section("Inner", body=(Prose("deep"),))
        outer = Section("Outer", body=(inner,))
        html = _full(Doc(None, (outer,)))
        assert "<h2>Outer</h2>" in html
        assert "<h3>Inner</h3>" in html
        assert "<section>" in html

    def test_prose_is_paragraph(self):
        html = _full(Doc(None, (Prose("a paragraph"),)))
        assert "<p>a paragraph</p>" in html

    def test_defs_is_definition_list(self):
        defs = Defs((Def("-v, --verbose", "Detailed output", detail="Stacks."),))
        html = _full(Doc(None, (defs,)))
        assert "<dt>-v, --verbose</dt>" in html
        assert "<dd>Detailed output</dd>" in html
        assert '<dd class="detail">Stacks.</dd>' in html  # eff >= 2 at FULL

    def test_items_list_kind(self):
        html = _full(Doc(None, (Items(("a", "b")), Items(("c",), ordered=True))))
        assert "<ul>\n<li>a</li>" in html
        assert "<ol>\n<li>c</li>" in html

    def test_code_block_with_language(self):
        html = _full(Doc(None, (Code(text="x = 1"),)))
        assert '<pre><code class="language-python">x = 1</code></pre>' in html

    def test_unresolved_code_src_is_placeholder(self):
        html = _full(Doc(None, (Code(src="py:painted.cell:Style#definition"),)))
        assert "[code: py:painted.cell:Style#definition]" in html

    def test_text_is_escaped(self):
        html = _full(Doc(None, (Prose("<script>alert(1)</script>"),)))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestFigureIsland:
    """Figure is the ONE node that routes through Block -> HTML."""

    def test_figure_embeds_rendered_block(self):
        fig = Figure(Block.text("LIVE", Style(bold=True)), caption="real output")
        html = _full(Doc(None, (fig,)))
        assert "<figure>" in html
        assert '<pre class="painted-output">' in html  # core/html.py's wrapper
        assert "<figcaption>real output</figcaption>" in html


class TestDisclosureParity:
    """Both projectors iterate the same visible_body walk — same fidelity in,
    same nodes out."""

    DOC = Doc(
        None,
        (
            Prose("always"),
            Prose("deep", min_depth=Zoom.DETAILED),
            Prose("why", tag="rationale"),
            Section("Group", body=(Defs((Def("-q", "Quiet"),)),), min_depth=Zoom.SUMMARY),
        ),
    )

    def test_hidden_in_lens_hidden_in_html(self):
        fid = Fidelity(depth=Zoom.SUMMARY)
        text = block_to_text(doc_lens(self.DOC, fidelity=fid, width=60))
        html = to_html(self.DOC, fidelity=fid)
        for fragment in ("deep", "why"):
            assert fragment not in text
            assert fragment not in html
        assert "always" in text and "always" in html

    def test_defs_compact_tier_matches_lens(self):
        """The nested Defs sits at eff == 0 (cascade): terms-only in BOTH sinks."""
        fid = Fidelity(depth=Zoom.SUMMARY)
        html = to_html(self.DOC, fidelity=fid)
        assert "<dl>" not in html
        assert '<p class="defs-compact">-q</p>' in html
        assert "Quiet" not in html

    def test_lines_budget_applies(self):
        doc = Doc(None, (Items(("one", "two", "three")),))
        html = to_html(doc, fidelity=Fidelity(depth=Zoom.FULL, lines=2))
        assert "<li>two</li>" in html
        assert "three" not in html


class TestPublishedFidelity:
    """A published page is the full document: max depth, every authored tag on."""

    def test_collects_nested_tags(self):
        doc = Doc(
            None,
            (
                Prose("why", tag="rationale"),
                Section("S", body=(Prose("aside", tag="aside"),)),
            ),
        )
        fid = published_fidelity(doc)
        assert fid.depth == Zoom.FULL
        assert fid.shows("rationale") and fid.shows("aside")

    def test_default_publish_shows_everything(self):
        html = to_html(DOCS["primitives"].build())
        assert "Design note" in html  # the tag="rationale" section
        assert "Why this matters" in html  # the min_depth=2 section


class TestEmit:
    def test_one_fragment_per_registry_entry(self, tmp_path):
        written = emit_doc_pages(repo_root=tmp_path, out_dir=tmp_path)
        # one HTML fragment per page, plus the registry index the site lists from
        assert {p.name for p in written} == {f"{name}.html" for name in DOCS} | {"index.json"}
        for p in written:
            if p.name == "index.json":
                continue
            assert p.read_text(encoding="utf-8").startswith('<article class="painted-doc">')

    def test_index_lists_the_registry(self, tmp_path):
        import json

        emit_doc_pages(repo_root=tmp_path, out_dir=tmp_path)
        entries = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert [e["name"] for e in entries] == list(DOCS)
        assert all(e["description"] == DOCS[e["name"]].description for e in entries)


class TestCompletionPage:
    """The 'completion' doc-IR page (dogfoods the feature it documents)."""

    def test_registered(self):
        assert "completion" in DOCS
        assert isinstance(DOCS["completion"].build(), Doc)

    def test_renders_at_every_depth(self):
        doc = DOCS["completion"].build()
        for depth in (Zoom.MINIMAL, Zoom.DETAILED, Zoom.FULL):
            block = doc_lens(doc, fidelity=Fidelity(depth=depth), width=80)
            assert block.height > 0, depth

    def test_figures_render(self):
        # guards the lazy producer import + the column math in _candidate_gallery.
        from painted._doc_pages import _candidate_gallery, _reflections_diagram

        for fig in (_candidate_gallery(), _reflections_diagram()):
            assert fig.width > 0 and fig.height > 0

    def test_has_rationale_layer(self):
        from painted._docs_cli import _collect_tags

        names = {tag.name for tag in _collect_tags(DOCS["completion"].build())}
        assert "rationale" in names  # so `painted docs completion --rationale` exists

    def test_publishes_figure_and_rationale(self):
        html = to_html(DOCS["completion"].build())
        assert "<figure>" in html  # the live producer gallery routed through render_html
        assert "Design note" in html  # the tag="rationale" section


class TestPromptsPage:
    """The 'prompts' doc-IR page (dogfoods the DECLARED rung it documents)."""

    def test_registered(self):
        assert "prompts" in DOCS
        assert isinstance(DOCS["prompts"].build(), Doc)

    def test_renders_at_every_depth(self):
        doc = DOCS["prompts"].build()
        for depth in (Zoom.MINIMAL, Zoom.DETAILED, Zoom.FULL):
            block = doc_lens(doc, fidelity=Fidelity(depth=depth), width=80)
            assert block.height > 0, depth

    def test_figures_render(self):
        # guards the lazy PromptSession import + the real non-interactive
        # resolution both galleries drive.
        from painted._doc_pages import _prompt_record_gallery, _prompt_refusal_gallery

        for fig in (_prompt_record_gallery(), _prompt_refusal_gallery()):
            assert fig.width > 0 and fig.height > 0

    def test_record_gallery_shows_real_default_lines(self):
        from painted._doc_pages import _prompt_record_gallery
        from tests.helpers import block_to_text

        text = block_to_text(_prompt_record_gallery())
        assert "force: no (default)" in text
        assert "scope: local (default)" in text

    def test_refusal_gallery_names_the_real_flag(self):
        from painted._doc_pages import _prompt_refusal_gallery
        from tests.helpers import block_to_text

        text = block_to_text(_prompt_refusal_gallery())
        assert "--overwrite" in text
        assert "stdin is not a terminal" in text

    def test_has_rationale_layer(self):
        from painted._docs_cli import _collect_tags

        names = {tag.name for tag in _collect_tags(DOCS["prompts"].build())}
        assert "rationale" in names  # so `painted docs prompts --rationale` exists

    def test_publishes_figure_and_rationale(self):
        html = to_html(DOCS["prompts"].build())
        assert "<figure>" in html  # the live resolver galleries routed through render_html
        assert "Design note" in html  # the tag="rationale" section


class TestInlineLink:
    """Link in the publisher: resolved through the SAME resolve_ref choke
    point the cell deliveries use — identical inertness in both worlds."""

    DOC = Doc(None, (Prose(("see ", Link("the docs", "docs:primitives"), " first")),))

    def test_undeclared_scheme_is_inert_plain_text(self):
        html = _full(self.DOC)
        assert "<p>see the docs first</p>" in html
        assert "<a " not in html  # painted never invents URIs

    def test_declared_scheme_becomes_an_anchor(self):
        with use_refs(RefScheme("docs", lambda v: f"https://painted.dev/docs/{v}")):
            html = _full(self.DOC)
        assert '<a href="https://painted.dev/docs/primitives">the docs</a>' in html

    def test_resolver_declining_with_none_is_inert(self):
        with use_refs(RefScheme("docs", lambda v: None)):
            html = _full(self.DOC)
        assert "<a " not in html
        assert "see the docs first" in html

    def test_link_text_and_uri_are_escaped(self):
        doc = Doc(None, (Prose((Link("a <b> & c", "docs:x"),)),))
        with use_refs(RefScheme("docs", lambda v: 'https://x/?q="1"')):
            html = _full(doc)
        assert "a &lt;b&gt; &amp; c" in html
        assert "&quot;1&quot;" in html
        assert "<b>" not in html

    def test_def_summary_and_items_entries_take_inline(self):
        doc = Doc(
            None,
            (
                Defs((Def("-v", ("more, ", Link("docs", "docs:v"))),)),
                Items(((Link("entry", "docs:e"),),)),
            ),
        )
        with use_refs(RefScheme("docs", lambda v: f"https://x/{v}")):
            html = _full(doc)
        assert '<dd>more, <a href="https://x/v">docs</a></dd>' in html
        assert '<li><a href="https://x/e">entry</a></li>' in html

    def test_disclosure_parity_holds_for_links(self):
        """A hidden node's links are hidden in both sinks — the shared walk."""
        doc = Doc(None, (Prose((Link("deep", "docs:d"),), min_depth=Zoom.DETAILED),))
        fid = Fidelity(depth=Zoom.SUMMARY)
        assert "deep" not in to_html(doc, fidelity=fid)
        assert "deep" not in block_to_text(doc_lens(doc, fidelity=fid, width=40))
