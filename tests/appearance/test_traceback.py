"""Traceback rendering ladder — pins render_traceback's structured appearance.

Every exception comes from ``_tb_fixture.py`` (frames entirely within that module),
so basenames + line numbers + source lines are deterministic across machines — the
snapshot is a real projection, not a machine-specific one. The scenarios pin the
load-bearing behaviors: the zoom ladder, source+caret, the suppress fold, the chain
connectives, the group tree, and FULL-zoom redacted locals.
"""

from __future__ import annotations

from painted.core.zoom import Zoom
from painted.views import render_traceback

from tests.appearance import _tb_fixture

_WIDTH = 68


def test_chained_ladder(appearance) -> None:
    exc = _tb_fixture.make_chained()
    for z in (Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED):
        appearance.assert_block(render_traceback(exc, z, _WIDTH), f"chained-{z.name.lower()}")


def test_context_chain(appearance) -> None:
    exc = _tb_fixture.make_context()
    appearance.assert_block(render_traceback(exc, Zoom.DETAILED, _WIDTH), "context")


def test_group_tree(appearance) -> None:
    exc = _tb_fixture.make_group()
    appearance.assert_block(render_traceback(exc, Zoom.DETAILED, _WIDTH), "group")


def test_suppress_fold(appearance) -> None:
    # Fold every fixture frame — the whole stack collapses to one muted line.
    exc = _tb_fixture.make_chained()
    block = render_traceback(exc, Zoom.SUMMARY, _WIDTH, suppress=["_tb_fixture"])
    appearance.assert_block(block, "suppressed")


def test_full_locals_redacted(appearance) -> None:
    # FULL: source ±3 + locals; `password` is masked, `count`/`note` render.
    exc = _tb_fixture.make_simple()
    appearance.assert_block(render_traceback(exc, Zoom.FULL, _WIDTH), "full-locals")
