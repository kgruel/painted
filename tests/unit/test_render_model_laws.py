"""Executable gates for the render model's laws (docs/RENDER_MODEL.md §4).

Milestone 1 of ROADMAP_1.0.0.md: the laws the 2026-07-10 audit verified by
*reading* are pinned here by *test*, so every later milestone is measured
against pinned law rather than discipline. Gate specs come from
RENDER_MODEL.md §8 ("Gates specified by the audit"); the full evidence
tables live in docs/RENDER_MODEL_AUDIT.md and serve as the regression
reference for what each pin covers.

Pinned here:
- Law 4 (destination independence) — behavioral + static gates.
- Law 6 (omission evidence) — pins for the *existing* marked truncation
  paths, so the evidence cannot rot while remediation is designed (§7 Q2).
- Law 8 (no downstream policy) — import gate over the delivery modules,
  with ``core/doc.py`` as the one named exception.

Law 1's cross-host harness is integration-tier:
tests/integration/test_cross_host_content.py. Laws 2/3 are editorial /
per-app by design (RENDER_MODEL §4) and deliberately have no universal
gate. Law 5's height arm and law 7's signature wait on their milestones.
"""

from __future__ import annotations

import ast

from tests.helpers import PAINTED_SRC, _assert_no_imports, _iter_imported_modules, row_text

_PAINTED = PAINTED_SRC / "painted"


# =============================================================================
# Law 4 — Destination independence
#
# No destination capability or terminal geometry participates in fidelity
# resolution. The audit confirmed this by reading every Fidelity construction
# site; these two tests make the reading a regression gate.
# =============================================================================


def test_law4_fidelity_compiles_identically_across_destinations(monkeypatch, capsys):
    """Identical declarations + argv → identical Fidelity, whatever the terminal.

    Runs the full run_cli compile path (parse → parse_fidelity →
    detect_context) under opposed destination conditions. ctx.width MUST
    differ (proof the environment change was real, and that geometry lives in
    CliContext); ctx.fidelity MUST NOT.
    """
    from painted import Block, Style, Tag
    from painted.cli import CliContext, run_cli

    argv = ["-v", "--thinking", "--max-chars", "40"]
    declarations = dict(
        tags=[Tag("thinking", "Show reasoning", implied_at=3)],
        depth_aliases={"brief": 0, "full": 3},
        budgets=True,
    )

    def renderer(data: str, fidelity, width) -> Block:
        return Block.text("x", Style())

    def run_under(*, isatty: bool, columns: str) -> CliContext:
        monkeypatch.setattr("sys.stdout.isatty", lambda: isatty)
        monkeypatch.setenv("COLUMNS", columns)
        monkeypatch.setenv("LINES", "50" if isatty else "8")
        seen: dict[str, CliContext] = {}

        def fetch(ctx: CliContext) -> str:
            seen["ctx"] = ctx
            return "d"

        assert run_cli(argv, renderer=renderer, fetch=fetch, **declarations) == 0
        return seen["ctx"]

    tty_ctx = run_under(isatty=True, columns="200")
    pipe_ctx = run_under(isatty=False, columns="34")
    capsys.readouterr()  # swallow the two deliveries

    assert tty_ctx.width != pipe_ctx.width, (
        "test setup failed: the two runs saw the same geometry, so the "
        "destination-independence assertion below would be vacuous"
    )
    assert tty_ctx.fidelity == pipe_ctx.fidelity, (
        "law 4 violated: fidelity resolution read a destination fact "
        f"({tty_ctx.fidelity} under a TTY vs {pipe_ctx.fidelity} under a pipe)"
    )


def _destination_reads(node: ast.AST) -> list[str]:
    """Names/attributes that would read a destination fact."""
    forbidden = {"environ", "isatty", "get_terminal_size"}
    hits = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in forbidden:
            hits.append(f"{sub.id} (line {sub.lineno})")
        elif isinstance(sub, ast.Attribute) and sub.attr in forbidden:
            hits.append(f".{sub.attr} (line {sub.lineno})")
    return hits


def test_law4_fidelity_compilation_reads_no_destination_facts():
    """Static arm: core/fidelity.py and parse_fidelity never reference
    os.environ / isatty / get_terminal_size. detect_context is *supposed* to
    read those — into CliContext fields, never into a Fidelity — so the scan
    scopes to the compilation code, not the whole of cli/types.py.
    """
    fidelity_hits = _destination_reads(
        ast.parse((_PAINTED / "core" / "fidelity.py").read_text(encoding="utf-8"))
    )
    assert not fidelity_hits, f"core/fidelity.py reads destination facts: {fidelity_hits}"

    types_tree = ast.parse((_PAINTED / "cli" / "types.py").read_text(encoding="utf-8"))
    parse_fidelity_def = next(
        node
        for node in ast.walk(types_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "parse_fidelity"
    )
    compile_hits = _destination_reads(parse_fidelity_def)
    assert not compile_hits, f"parse_fidelity reads destination facts: {compile_hits}"


# =============================================================================
# Law 8 — No downstream policy
#
# Block, composition, Buffer, Writer, and the delivery surfaces carry no
# disclosure policy. The audit found this held by discipline, not
# construction; this gate is the construction. core/doc.py is the ONE
# sanctioned exception (the shared disclosure walk lives there for
# import-order reasons — see its docstring and DOC_IR_DESIGN.md); like
# _CLI_SEAMS, the exception is named, not a relaxation: it is asserted
# *real* below, so a stale allowlist fails too.
# =============================================================================

_LAW8_DOWNSTREAM_FILES = (
    "core/cell.py",
    "core/span.py",
    "core/block.py",
    "core/compose.py",
    "core/buffer.py",
    "core/writer.py",
    "inplace.py",
    "tui/surface.py",
    "tui/layer.py",
)
_DISCLOSURE_POLICY_PREFIXES = {"painted.core.fidelity", "painted.cli"}


def test_law8_downstream_modules_carry_no_disclosure_policy():
    for rel in _LAW8_DOWNSTREAM_FILES:
        _assert_no_imports(_PAINTED / rel, _DISCLOSURE_POLICY_PREFIXES)


def test_law8_named_exception_is_real():
    """core/doc.py must actually import the disclosure spec it is exempted
    for — if the disclosure walk ever moves out, the exemption comment in
    this file and the law-8 status note in RENDER_MODEL.md are stale and
    should be swept in the same change.
    """
    imported = _iter_imported_modules(PAINTED_SRC, _PAINTED / "core" / "doc.py")
    assert any(mod.startswith("painted.core.fidelity") for mod in sorted(imported)), (
        "core/doc.py no longer imports core.fidelity — remove its law-8 "
        "exemption here and update RENDER_MODEL.md §4"
    )


# =============================================================================
# Law 6 — Omission evidence: pins for the paths that mark today
#
# The audit's finding: marked/silent tracks the layer, and today's marked
# paths (lens/compose width loss) have NO test asserting the mark itself —
# only width bounds. These pins stop the existing evidence from disappearing
# silently while the remediation (§7 Q2) is designed. The inventory of
# silent paths is docs/RENDER_MODEL_AUDIT.md — deliberately NOT pinned:
# they are targets, not contracts.
# =============================================================================


class TestLaw6EvidencePins:
    def test_truncate_ellipsis_marks_the_cut(self):
        from painted.core._text_width import display_width, truncate_ellipsis

        marked = truncate_ellipsis("abcdefghij", 5, ellipsis="…")
        assert marked.endswith("…"), "width clipping left no mark"
        assert display_width(marked) <= 5
        # untouched when it fits — a mark without loss would be false evidence
        assert truncate_ellipsis("abc", 5, ellipsis="…") == "abc"

    def test_compose_truncate_marks_the_cut(self):
        from painted import Block, Style
        from painted.core.compose import truncate

        out = truncate(Block.text("abcdefghij", Style()), 5)
        assert out.width == 5
        assert row_text(out, 0) == "abcd…", "compose.truncate dropped its ambient mark"

    def test_compose_truncate_mark_degrades_with_ascii_icons(self):
        from painted import ASCII_ICONS, Block, Style, use_icons
        from painted.core.compose import truncate

        with use_icons(ASCII_ICONS):
            out = truncate(Block.text("abcdefghij", Style()), 7)
        assert row_text(out, 0).endswith(ASCII_ICONS.ellipsis)

    def test_fit_to_width_marks_narrowing(self):
        from painted import Block, Style
        from painted.core.compose import fit_to_width

        out = fit_to_width(Block.text("abcdefghij", Style()), 5)
        assert out.width == 5
        assert "…" in row_text(out, 0)

    def test_scalar_chars_budget_leaves_length_evidence(self):
        """The fidelity-chars marker: a string cut by the chars budget names
        what was lost ("... [N chars]") rather than pretending the value was
        short. (The audit's boundary-blur note — this marker and the width
        ellipsis can both fire — is a design question, not this pin's.)
        """
        from painted.core.fidelity import Fidelity
        from painted.views import shape_lens

        long_value = "x" * 300
        out = shape_lens(long_value, zoom=2, width=400, fidelity=Fidelity(depth=2, chars=50))
        text = row_text(out, 0)
        assert "[300 chars]" in text, "chars-budget loss left no length evidence"
        # default cap (no fidelity passed) leaves the same evidence
        out_default = shape_lens(long_value, zoom=2, width=400)
        assert "[300 chars]" in row_text(out_default, 0)

    def test_budget_fields_reports_dropped_columns(self):
        from painted.core.compose import budget_fields

        fit = budget_fields(["a" * 20, "b" * 20], 25)
        assert fit.dropped > 0, "whole-field drop reported no loss"

        exact = budget_fields(["ab", "cd"], 20)
        assert exact.dropped == 0, "no loss must report zero (false evidence)"
        assert exact.text == "ab · cd"

    def test_inplace_oversized_frame_marks_the_cut(self, monkeypatch):
        """The §7 Q2b resolution (0.10): InPlaceRenderer clips an oversized
        live frame with a named-loss marker — delivery-owned evidence per the
        ownership rule; silent tearing was the one answer the model forbade.
        (Full behavioral coverage: tests/unit/test_inplace_renderer.py.)
        """
        import io
        import os

        from painted import Block, Style
        from painted.core.compose import join_vertical
        from painted.inplace import InPlaceRenderer

        class _Tty(io.StringIO):
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr(
            "shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((80, 4))
        )
        tall = join_vertical(*(Block.text(f"r{i}", Style()) for i in range(8)), gap=0)
        stream = _Tty()
        with InPlaceRenderer(stream) as renderer:
            renderer.render(tall)
        assert "… +5 rows" in stream.getvalue(), "oversized-frame clip left no evidence"

        fitting = join_vertical(*(Block.text(f"r{i}", Style()) for i in range(3)), gap=0)
        stream = _Tty()
        with InPlaceRenderer(stream) as renderer:
            renderer.render(fitting)
        assert "rows" not in stream.getvalue(), "a mark without loss is false evidence"

    # --- 0.14 S1: the windowed offered-arm components adopt evidence_row -------
    #
    # list_view / table / data_explorer reserve their last body row for the
    # shared law-6 evidence row when content overflows the window, and are
    # byte-clean (no marker, full height for content) when it fits. Each site
    # pins both arms; the ambient-glyph sites pin Unicode + ASCII.

    def test_list_view_overflow_marks_and_fit_is_clean(self):
        from painted import Cursor, Style
        from painted.core.span import Line
        from painted.views import ListState, list_view

        wide = [Line.plain(f"entry-{i:02d}-payload") for i in range(20)]
        over = list_view(ListState(cursor=Cursor(count=20)), wide, visible_height=6)
        assert over.height == 6
        assert "15 more rows" in row_text(over, 5), "overflow left no scroll evidence"

        fit = list_view(ListState(cursor=Cursor(count=4)), wide[:4], visible_height=6)
        assert fit.height == 6
        blob = "\n".join(row_text(fit, y) for y in range(fit.height))
        assert "…" not in blob and "more rows" not in blob, "a mark without loss is false evidence"
        for i in range(4):
            assert f"entry-{i:02d}-payload" in row_text(fit, i)

    def test_list_view_evidence_degrades_with_ascii_icons(self):
        from painted import ASCII_ICONS, Cursor, use_icons
        from painted.core.span import Line
        from painted.views import ListState, list_view

        wide = [Line.plain(f"entry-{i:02d}-payload") for i in range(20)]
        with use_icons(ASCII_ICONS):
            over = list_view(ListState(cursor=Cursor(count=20)), wide, visible_height=6)
        row = row_text(over, 5)
        assert "…" not in row and row.lstrip().startswith("..."), "evidence glyph did not degrade"
        assert "15 more rows" in row

    def test_list_view_row_tail_ellipsis_marks_and_fits_clean(self):
        from painted import ASCII_ICONS, Cursor, use_icons
        from painted.core.span import Line
        from painted.views import ListState, list_view

        # An item wider than the allotted width is the component's own cut, so it
        # owes the mark — the ellipsizing path, not a silent Line.truncate.
        long_item = [Line.plain("a very long item that exceeds the width")]
        clipped = list_view(
            ListState(cursor=Cursor(count=1)), long_item, visible_height=2, width=12
        )
        assert row_text(clipped, 0).rstrip().endswith("…"), "row-tail cut left no mark"
        with use_icons(ASCII_ICONS):
            ascii_clip = list_view(
                ListState(cursor=Cursor(count=1)), long_item, visible_height=2, width=12
            )
        assert row_text(ascii_clip, 0).rstrip().endswith("..."), "row-tail mark did not degrade"

        # A row that fits keeps its exact bytes — no ellipsis intrudes.
        short_item = [Line.plain("short")]
        fit = list_view(ListState(cursor=Cursor(count=1)), short_item, visible_height=2, width=12)
        assert "…" not in row_text(fit, 0), "a mark without loss is false evidence"

    def test_table_overflow_marks_and_fit_is_clean(self):
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain("Item"), width=20)]
        rows = [[Line.plain(f"v{i}")] for i in range(10)]
        over = table(TableState(), cols, rows, visible_height=4)
        assert over.height == 6  # header + separator + 4 body rows (unchanged total)
        assert "7 more rows" in row_text(over, 5), "table overflow left no scroll evidence"

        fit = table(TableState(), cols, rows[:3], visible_height=4)
        blob = "\n".join(row_text(fit, y) for y in range(fit.height))
        assert "…" not in blob and "more rows" not in blob, "a mark without loss is false evidence"
        for i in range(3):
            assert f"v{i}" in row_text(fit, 2 + i)

    def test_table_evidence_degrades_with_ascii_icons(self):
        from painted import ASCII_ICONS, use_icons
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain("Item"), width=20)]
        rows = [[Line.plain(f"v{i}")] for i in range(10)]
        with use_icons(ASCII_ICONS):
            over = table(TableState(), cols, rows, visible_height=4)
        row = row_text(over, 5)
        assert "…" not in row and row.lstrip().startswith("..."), "table evidence did not degrade"
        assert "7 more rows" in row

    def test_data_explorer_overflow_marks_and_fit_is_clean(self):
        from painted.views import DataExplorerState, data_explorer

        data = {f"k{i}": i for i in range(20)}
        over = data_explorer(DataExplorerState(data=data), width=30, height=6)
        assert over.height == 6
        assert "15 more rows" in row_text(over, 5), "data_explorer overflow left no evidence"

        small = {f"k{i}": i for i in range(4)}
        fit = data_explorer(DataExplorerState(data=small), width=30, height=6)
        blob = "\n".join(row_text(fit, y) for y in range(fit.height))
        assert "…" not in blob and "more rows" not in blob, "a mark without loss is false evidence"
        for i in range(4):
            assert f"k{i}" in row_text(fit, i)

    def test_data_explorer_evidence_degrades_with_ascii_icons(self):
        from painted import ASCII_ICONS, use_icons
        from painted.views import DataExplorerState, data_explorer

        data = {f"k{i}": i for i in range(20)}
        with use_icons(ASCII_ICONS):
            over = data_explorer(DataExplorerState(data=data), width=30, height=6)
        row = row_text(over, 5)
        assert "…" not in row and row.lstrip().startswith("..."), (
            "explorer evidence did not degrade"
        )
        assert "15 more rows" in row

    def test_data_explorer_deep_prefix_marks_and_waiver(self):
        from painted import ASCII_ICONS, use_icons
        from painted.views import DataExplorerState, data_explorer

        # Indentation that exhausts the width drops the node identity — the
        # surviving prefix fragment carries the mark.
        deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        expanded = frozenset({("a",), ("a", "b"), ("a", "b", "c"), ("a", "b", "c", "d")})
        state = DataExplorerState(data=deep, expanded=expanded)
        narrow = data_explorer(state, width=6, height=8)
        deep_rows = [row_text(narrow, y) for y in range(8)]
        assert any(r.rstrip().endswith("…") for r in deep_rows), "deep-prefix cut left no mark"
        with use_icons(ASCII_ICONS):
            ascii_narrow = data_explorer(state, width=6, height=8)
        ascii_rows = [row_text(ascii_narrow, y) for y in range(8)]
        assert any(r.rstrip().endswith("...") for r in ascii_rows), (
            "deep-prefix mark did not degrade"
        )

        # The one-display-cell physical-space waiver: no room for both content
        # and mark, so the plain cut stands (pinned so the boundary can't drift).
        one_cell = data_explorer(state, width=1, height=8)
        assert "…" not in "\n".join(row_text(one_cell, y) for y in range(8)), (
            "waiver breached at w=1"
        )

        # A width that fits every prefix marks nothing.
        wide = data_explorer(state, width=40, height=8)
        assert "…" not in "\n".join(row_text(wide, y) for y in range(8)), (
            "false evidence when it fits"
        )

    # --- 0.14 S2: table wholly-hidden-column badge under Overflow.CLIP -------
    #
    # A CLIP cut that drops whole columns owes their exact count alongside the
    # ordinary right-edge clip mark (RENDER_MODEL law 6's own table example); a
    # cut that only shortens the last visible column keeps the plain mark, and
    # a table that fits is byte-identical to an unclipped (slack-width) render.

    def test_table_column_badge_counts_wholly_hidden_columns(self):
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain(h), width=10) for h in "ABCD"]
        rows = [[Line.plain(c * 10) for c in "abcd"]]

        # Total natural width 10*4 + 3 seps = 43; clipped to 15 columns drops
        # B, C, D wholly (their reserved-marker cutoff falls before B starts) —
        # exactly 3, not merely "some".
        clipped = table(TableState(), cols, rows, visible_height=2, width=15)
        assert clipped.width == 15
        header = row_text(clipped, 0)
        assert "+3c" in header, "wholly-hidden columns left no exposed count"
        assert header.rstrip().endswith("+3c")
        for letter in "BCD":
            assert letter not in header, f"column {letter} should be wholly clipped away"

        # A partial clip of the LAST visible column is not a column loss —
        # not counted, ordinary ellipsis mark only.
        single = [Column(header=Line.plain("Item"), width=20)]
        one_row = [[Line.plain("v" * 20)]]
        partial = table(TableState(), single, one_row, visible_height=2, width=10)
        text = row_text(partial, 2)
        assert text.rstrip().endswith("…"), "partial column clip lost its ordinary mark"
        assert "+" not in text, "a partially-visible column must not be counted"

    def test_table_column_badge_absent_when_it_fits(self):
        from painted.core.span import Line
        from painted.views import Column, TableState, table
        from tests.helpers import assert_blocks_equal

        cols = [Column(header=Line.plain("A"), width=5), Column(header=Line.plain("B"), width=5)]
        rows = [[Line.plain("aaaaa"), Line.plain("bbbbb")]]

        # Exact-fit (passed width == the table's natural width) must render
        # byte-identical to a slack render (width far beyond natural) — a mark
        # or a badge without loss is false evidence.
        exact = table(TableState(), cols, rows, visible_height=2, width=11)
        slack = table(TableState(), cols, rows, visible_height=2, width=200)
        assert exact.width == 11
        assert_blocks_equal(exact, slack)
        blob = "\n".join(row_text(exact, y) for y in range(exact.height))
        assert "…" not in blob and "+" not in blob, "a mark without loss is false evidence"

    def test_table_column_badge_degrades_with_ascii_icons(self):
        from painted import ASCII_ICONS, use_icons
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain(h), width=10) for h in "ABCD"]
        rows = [[Line.plain(c * 10) for c in "abcd"]]
        with use_icons(ASCII_ICONS):
            clipped = table(TableState(), cols, rows, visible_height=2, width=15)
        header = row_text(clipped, 0)
        assert "…" not in header and "..." in header, "column badge mark did not degrade"
        assert "+3c" in header

    def test_table_column_badge_degenerate_width_waives_to_ellipsis(self):
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain(h), width=5) for h in "ABC"]
        rows = [[Line.plain(c * 5) for c in "abc"]]

        # width=3: "… +3c" cannot possibly fit — the badge is waived, the plain
        # ellipsis (the minimal resolution-loss mark) stands. Pin the boundary.
        narrow = table(TableState(), cols, rows, visible_height=2, width=3)
        assert narrow.width == 3
        header = row_text(narrow, 0)
        assert "…" in header and "+" not in header, "degenerate width must waive the badge"

        # width=1: not even the plain ellipsis has room for content beside it —
        # the one cell left is the mark itself (compose.truncate's own waiver).
        one_cell = table(TableState(), cols, rows, visible_height=2, width=1)
        assert one_cell.width == 1
        assert row_text(one_cell, 0) == "…"

    def test_table_column_badge_renders_at_exact_marker_width(self):
        """Sol review finding 1: waive only when the marker cannot fit (cw >
        width, strict) — a marker that fits *exactly* is not degenerate. Three
        5-cell columns at width=5 (Unicode) / width=7 (ASCII): the stable
        fixed point is the badge occupying the entire allocation, all three
        columns wholly hidden — the S1 F=1 evidence-row precedent (when the
        allocation is only big enough for the evidence, the evidence IS the
        render).
        """
        from painted import ASCII_ICONS, use_icons
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain(h), width=5) for h in "ABC"]
        rows = [[Line.plain(c * 5) for c in "abc"]]

        exact = table(TableState(), cols, rows, visible_height=2, width=5)
        assert exact.width == 5
        assert row_text(exact, 0) == "… +3c"

        with use_icons(ASCII_ICONS):
            ascii_exact = table(TableState(), cols, rows, visible_height=2, width=7)
        assert ascii_exact.width == 7
        assert row_text(ascii_exact, 0) == "... +3c"

    def test_table_column_badge_absent_when_it_fits_ascii(self):
        from painted import ASCII_ICONS, use_icons
        from painted.core.span import Line
        from painted.views import Column, TableState, table
        from tests.helpers import assert_blocks_equal

        cols = [Column(header=Line.plain("A"), width=5), Column(header=Line.plain("B"), width=5)]
        rows = [[Line.plain("aaaaa"), Line.plain("bbbbb")]]

        with use_icons(ASCII_ICONS):
            exact = table(TableState(), cols, rows, visible_height=2, width=11)
            slack = table(TableState(), cols, rows, visible_height=2, width=200)
        assert exact.width == 11
        assert_blocks_equal(exact, slack)
        blob = "\n".join(row_text(exact, y) for y in range(exact.height))
        assert "..." not in blob and "+" not in blob, "a mark without loss is false evidence"

    def test_table_row_evidence_and_column_badge_coexist(self):
        """S1's row evidence and S2's column badge are independent axes — a
        table both taller and wider than its allocation owes both, each with
        its own exact count, in the same render.
        """
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain(h), width=10) for h in "ABCD"]
        rows = [[Line.plain(f"{c}{i}") for c in "abcd"] for i in range(10)]

        blk = table(TableState(), cols, rows, visible_height=4, width=15)

        assert blk.width == 15
        assert blk.height == 6  # header + separator + 4 body rows (unchanged total)

        # S2: the column badge — B, C, D wholly hidden, exact count 3 — marks
        # every row (the marker is folded into the uniform right-edge cut).
        header = row_text(blk, 0)
        assert "+3c" in header
        for letter in "BCD":
            assert letter not in header

        # S1: the last body row is the row-evidence row — 10 rows over a
        # 4-row window with 3 shown leaves exactly 7 hidden — surviving even
        # though its own text is itself column-clipped by the same cut.
        evidence = row_text(blk, 5)
        assert "7 more" in evidence, "row evidence count did not survive column clipping"
        assert "+3c" in evidence, "column badge must still mark the evidence row's own cut"

    def test_windowed_components_keep_selection_above_evidence(self):
        """Law-6 corollary: reserving the evidence row must not hide the selected
        final item behind it — the offset math clamps against the content
        capacity, so the last item stays visible above the mark."""
        from painted import Cursor
        from painted.core.span import Line
        from painted.views import (
            Column,
            DataExplorerState,
            ListState,
            TableState,
            data_explorer,
            list_view,
            table,
        )

        # list_view: select the final item, scroll it into view, render.
        items = [Line.plain(f"n{i}") for i in range(12)]
        lst = ListState(cursor=Cursor(index=11, count=12)).scroll_into_view(4)
        lblock = list_view(lst, items, visible_height=4)
        assert "n11" in row_text(lblock, 2), "list_view hid the selected final item"
        assert "…" in row_text(lblock, 3), "list_view dropped its evidence row"

        # table: same, over the body window (rows below the header + separator).
        cols = [Column(header=Line.plain("V"), width=6)]
        trows = [[Line.plain(f"n{i}")] for i in range(12)]
        tstate = TableState(cursor=Cursor(index=11, count=12)).scroll_into_view(4)
        tblock = table(tstate, cols, trows, visible_height=4)
        assert "n11" in row_text(tblock, 2 + 2), "table hid the selected final row"
        assert "…" in row_text(tblock, 2 + 3), "table dropped its evidence row"

        # data_explorer: End selects the last node; it must sit above the mark.
        data = {f"k{i}": i for i in range(12)}
        dstate = DataExplorerState(data=data).with_visible(4).end()
        dblock = data_explorer(dstate, width=30, height=4)
        assert "k11" in row_text(dblock, 2), "data_explorer hid the selected final node"
        assert "…" in row_text(dblock, 3), "data_explorer dropped its evidence row"

    # --- Exact-fit boundary: N == F must fit, not overflow ---------------------
    #
    # The overflow decision is ``content > F`` (capacity ``frame_capacity``). At
    # N == F content fits exactly — a wrong ``>=`` would reserve a row, drop the
    # last item, and mark it. These pins compare the exact-fit block byte-for-byte
    # (content rows) against a slack render that definitely fits, and assert no
    # marker in BOTH icon modes (the false marker differs by mode).

    def test_list_view_exact_fit_does_not_overflow(self):
        from painted import ASCII_ICONS, Cursor, use_icons
        from painted.core.span import Line
        from painted.views import ListState, list_view

        items = [Line.plain(f"e{i}-payload") for i in range(5)]
        state = ListState(cursor=Cursor(count=5))
        exact = list_view(state, items, visible_height=5)  # N == F
        slack = list_view(state, items, visible_height=6)  # N < F, surely fits
        assert exact.height == 5
        for i in range(5):
            assert exact.row(i) == slack.row(i), f"exact-fit row {i} diverged (a row was reserved)"
        assert "…" not in "\n".join(row_text(exact, y) for y in range(5)), "false evidence at N==F"
        # ASCII arm: same byte comparison, both renders inside the ASCII context —
        # a mode-specific fitting-path alteration (with or without a marker) is
        # caught, not just the presence of "...".
        with use_icons(ASCII_ICONS):
            ascii_exact = list_view(state, items, visible_height=5)
            ascii_slack = list_view(state, items, visible_height=6)
        assert ascii_exact.height == 5
        for i in range(5):
            assert ascii_exact.row(i) == ascii_slack.row(i), f"ASCII exact-fit row {i} diverged"

    def test_table_exact_fit_does_not_overflow(self):
        from painted import ASCII_ICONS, use_icons
        from painted.core.span import Line
        from painted.views import Column, TableState, table

        cols = [Column(header=Line.plain("Item"), width=10)]
        rows = [[Line.plain(f"v{i}")] for i in range(5)]
        exact = table(TableState(), cols, rows, visible_height=5)  # 5 body rows == F
        slack = table(TableState(), cols, rows, visible_height=6)
        assert exact.height == 7  # header + separator + 5 rows
        for y in range(7):
            assert exact.row(y) == slack.row(y), f"exact-fit row {y} diverged (a row was reserved)"
        assert "…" not in "\n".join(row_text(exact, y) for y in range(7)), "false evidence at N==F"
        with use_icons(ASCII_ICONS):
            ascii_exact = table(TableState(), cols, rows, visible_height=5)
            ascii_slack = table(TableState(), cols, rows, visible_height=6)
        assert ascii_exact.height == 7
        for y in range(7):
            assert ascii_exact.row(y) == ascii_slack.row(y), f"ASCII exact-fit row {y} diverged"

    def test_data_explorer_exact_fit_does_not_overflow(self):
        from painted import ASCII_ICONS, use_icons
        from painted.views import DataExplorerState, data_explorer

        data = {f"k{i}": i for i in range(5)}
        exact = data_explorer(DataExplorerState(data=data), width=20, height=5)  # N == F
        slack = data_explorer(DataExplorerState(data=data), width=20, height=6)
        assert exact.height == 5
        for i in range(5):
            assert exact.row(i) == slack.row(i), f"exact-fit row {i} diverged (a row was reserved)"
        assert "…" not in "\n".join(row_text(exact, y) for y in range(5)), "false evidence at N==F"
        with use_icons(ASCII_ICONS):
            ascii_exact = data_explorer(DataExplorerState(data=data), width=20, height=5)
            ascii_slack = data_explorer(DataExplorerState(data=data), width=20, height=6)
        assert ascii_exact.height == 5
        for i in range(5):
            assert ascii_exact.row(i) == ascii_slack.row(i), f"ASCII exact-fit row {i} diverged"

    def test_components_mark_overflow_at_degenerate_heights(self):
        """F=0 waives evidence (no body row exists); F=1 under overflow makes the
        single body row the evidence row (the assemble_frame / InPlaceRenderer
        precedent). Pinned per component so the boundary can't drift."""
        from painted import Cursor
        from painted.core.span import Line
        from painted.views import (
            Column,
            DataExplorerState,
            ListState,
            TableState,
            data_explorer,
            list_view,
            table,
        )

        # list_view — zero-height at F=0, single evidence row at F=1.
        items = [Line.plain(f"n{i}") for i in range(8)]
        z = list_view(ListState(cursor=Cursor(count=8)), items, visible_height=0)
        assert z.height == 0, "F=0 list_view must be zero-height (evidence waived)"
        one = list_view(ListState(cursor=Cursor(count=8)), items, visible_height=1)
        assert one.height == 1 and "…" in row_text(one, 0), "F=1 list_view: the row is evidence"

        # table — header + separator always render; F=0 has no body row (no
        # evidence), F=1 under overflow makes the one body row the evidence row.
        cols = [Column(header=Line.plain("V"), width=8)]
        rows = [[Line.plain(f"n{i}")] for i in range(8)]
        z = table(TableState(), cols, rows, visible_height=0)
        assert z.height == 2, "F=0 table: header + separator only"
        assert "…" not in "\n".join(row_text(z, y) for y in range(2)), (
            "F=0 table marked nothing shown"
        )
        one = table(TableState(), cols, rows, visible_height=1)
        assert one.height == 3 and "…" in row_text(one, 2), (
            "F=1 table: the one body row is evidence"
        )

        # data_explorer — zero-height at F=0, single evidence row at F=1.
        data = {f"k{i}": i for i in range(8)}
        z = data_explorer(DataExplorerState(data=data), width=20, height=0)
        assert z.height == 0, "F=0 data_explorer must be zero-height"
        one = data_explorer(DataExplorerState(data=data), width=20, height=1)
        assert one.height == 1 and "…" in row_text(one, 0), "F=1 data_explorer: the row is evidence"

    def test_resize_keeps_selection_above_evidence(self):
        """Finding-1 regression: with_visible (a resize) reconciles through the
        capacity like scroll_into_view — shrinking the frame so the selection
        would fall behind the reserved evidence row re-scrolls it into view."""
        from painted import Cursor
        from painted.core.span import Line
        from painted.views import Column, ListState, TableState, list_view, table

        # list_view: select item 9/10, scroll into a height-3 window, resize to 4.
        items = [Line.plain(f"n{i}") for i in range(10)]
        lst = ListState(cursor=Cursor(index=9, count=10)).scroll_into_view(3).with_visible(4)
        lblock = list_view(lst, items, visible_height=4)
        assert "n9" in row_text(lblock, 2), "list resize hid the selected final item"
        assert "…" in row_text(lblock, 3), "list resize dropped its evidence row"

        # table: same repro over the body window.
        cols = [Column(header=Line.plain("V"), width=6)]
        rows = [[Line.plain(f"n{i}")] for i in range(10)]
        tstate = TableState(cursor=Cursor(index=9, count=10)).scroll_into_view(3).with_visible(4)
        tblock = table(tstate, cols, rows, visible_height=4)
        assert "n9" in row_text(tblock, 2 + 2), "table resize hid the selected final row"
        assert "…" in row_text(tblock, 2 + 3), "table resize dropped its evidence row"
