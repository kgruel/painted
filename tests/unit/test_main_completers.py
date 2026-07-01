"""The front door's T3 dynamic completers (slice 5): demos + docs names.

painted dogfoods the `.completer` seam — demo and doc names are runtime data no
static `choices` can hold, so the `demos`/`docs` commands hang a completer that
discovers them. The demos completer must stay render-free (the no-renderer-on-TAB
guarantee for the first-party binary); the docs completer legitimately loads the
renderer because the doc registry *is* doc-IR.
"""

from __future__ import annotations

from painted.__main__ import _complete_demo_names, _complete_doc_names, main
from painted.cli import Candidate, CompletionContext


class TestDemoCompleter:
    def test_returns_described_candidates(self):
        cands = _complete_demo_names(CompletionContext())
        assert cands and all(isinstance(c, Candidate) for c in cands)
        assert all(c.description for c in cands)  # every demo has a docstring line

    def test_includes_a_known_demo(self):
        names = {c.value for c in _complete_demo_names(CompletionContext())}
        assert "plasma" in names

    def test_excludes_tour(self):
        # tour is its own command (group == ""), not a demos value
        names = {c.value for c in _complete_demo_names(CompletionContext())}
        assert "tour" not in names


class TestDocCompleter:
    def test_returns_described_candidates(self):
        cands = _complete_doc_names(CompletionContext())
        assert cands and all(isinstance(c, Candidate) for c in cands)
        assert "primitives" in {c.value for c in cands}


class TestGateEndToEnd:
    """The completer reaches the wire through the real run_app gate."""

    def _complete(self, line, capsys, monkeypatch):
        monkeypatch.setenv("_PAINTED_COMPLETE", "zsh")
        monkeypatch.setenv("COMP_LINE", line)
        monkeypatch.setenv("COMP_POINT", str(len(line)))
        assert main([]) == 0
        return capsys.readouterr().out.splitlines()

    def test_demos_tab_emits_names(self, capsys, monkeypatch):
        values = {ln.split(":")[0] for ln in self._complete("painted demos ", capsys, monkeypatch)}
        assert "plasma" in values
        assert "boids" in values

    def test_demos_prefix_filters(self, capsys, monkeypatch):
        values = {
            ln.split(":")[0] for ln in self._complete("painted demos pl", capsys, monkeypatch)
        }
        assert "plasma" in values
        assert "boids" not in values  # filtered by the "pl" prefix

    def test_demo_alias_also_completes(self, capsys, monkeypatch):
        values = {ln.split(":")[0] for ln in self._complete("painted demo ", capsys, monkeypatch)}
        assert "plasma" in values

    def test_docs_tab_emits_names(self, capsys, monkeypatch):
        values = {ln.split(":")[0] for ln in self._complete("painted docs ", capsys, monkeypatch)}
        assert "primitives" in values
        # dogfood: the completion page the feature documents now completes itself.
        assert "completion" in values


class TestRenderFree:
    """`painted demos <TAB>` must not pull the renderer — the lazy __main__ +
    render-free discovery promise, checked in a fresh subprocess."""

    def _block_loaded(self, comp_line: str) -> bool:
        import json
        import os
        import subprocess
        import sys

        env = dict(
            os.environ, _PAINTED_COMPLETE="zsh", COMP_LINE=comp_line, COMP_POINT=str(len(comp_line))
        )
        probe = (
            "import painted.__main__ as m; m.main([]); import sys, json; "
            "print(json.dumps('painted.core.block' in sys.modules))"
        )
        out = subprocess.run(
            [sys.executable, "-c", probe], env=env, capture_output=True, text=True, check=True
        )
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_demos_completion_is_render_free(self):
        assert self._block_loaded("painted demos ") is False

    def test_bare_completion_is_render_free(self):
        assert self._block_loaded("painted ") is False
