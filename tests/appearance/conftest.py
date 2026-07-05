"""Appearance fixture — structured char+style snapshots of rendered Blocks.

The successor to the demo-goldens for the *appearance* axis. The old goldens
captured `block_to_text(use_ansi=False)` — the character layer only — so the
entire Style dimension (color, bold, dim, reverse, …) was invisible to them. An
appearance snapshot serializes the cell grid itself: each row as coalesced runs
of identical style, each run carrying its set style fields. That is the contract
object (painted *is* a grid of styled cells), not the writer's lossy ANSI
projection — so a palette role flipping green→red, or a header losing bold, shows
up as a precise one-line diff instead of sailing through a stripped text match.

Why structured JSON and not raw ANSI: the legacy golden normalizer right-strips
every line, which would silently corrupt a trailing SGR reset. Structured runs
are normalizer-safe, diff-stable, and human-readable. The writer's ANSI *bytes*
are a separate concern, covered by the totality properties in
`tests/property/test_writer_output.py`.

Snapshots live under `tests/appearance/snapshots/<module>/<test>/<name>.json`.
Regenerate with `--update-appearance`; the git diff is the review.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from painted.core._row_ops import iter_row_spans
from painted.core.block import Block
from painted.core.cell import Style

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"

# Ambient palette/icons/borders are reset around every test by the suite-wide
# `_reset_ambient_state` fixture (root conftest) — so a snapshot captures the
# style the scenario set explicitly, not a leaked ambient one.

_ATTRS = ("bold", "italic", "underline", "reverse", "dim")


def _style_fields(style: Style) -> dict:
    """Only the *set* style fields, in a fixed order, for stable diffs."""
    out: dict = {}
    if style.fg is not None:
        out["fg"] = style.fg
    if style.bg is not None:
        out["bg"] = style.bg
    for attr in _ATTRS:
        if getattr(style, attr):
            out[attr] = True
    return out


def _row_runs(row_cells, row_refs=None) -> list[dict]:
    """Coalesce a row into runs of identical style *and* ref.

    `iter_row_spans` yields one span per visible glyph (wide chars as a lead +
    placeholder pair); we merge consecutive spans that share a style and a ref. A
    run's text is the visible glyphs (placeholders dropped), matching
    `row_visible_text`. A run carries a `ref` key only when its denotation is
    non-None — so a ref-less block serializes byte-identically to before the ref
    dimension existed, and refs surface as a precise diff exactly as Style does.
    """
    runs: list[dict] = []
    cur_text: list[str] = []
    cur_style: Style | None = None
    cur_ref: str | None = None

    def flush() -> None:
        if cur_style is not None:
            run = {"text": "".join(cur_text), **_style_fields(cur_style)}
            if cur_ref is not None:
                run["ref"] = cur_ref
            runs.append(run)

    for span in iter_row_spans(row_cells, row_refs):
        glyph = span.cells[0].char
        style = span.cells[0].style
        ref = span.refs[0] if span.refs is not None else None
        if cur_style is not None and style == cur_style and ref == cur_ref:
            cur_text.append(glyph)
        else:
            flush()
            cur_text = [glyph]
            cur_style = style
            cur_ref = ref
    flush()
    return runs


def _ref_row(block: Block, y: int):
    """The ref row for a block row: per-cell grid, uniform block ref, or None."""
    if block._refs is not None:
        return block._refs[y]
    if block.ref is not None:
        return (block.ref,) * block.width
    return None


def serialize_block(block: Block) -> dict:
    """Serialize a Block to a structured char+style+ref map (rows of runs)."""
    return {
        "width": block.width,
        "height": block.height,
        "rows": [_row_runs(block.row(y), _ref_row(block, y)) for y in range(block.height)],
    }


@dataclass
class Appearance:
    """Compare a rendered Block against a committed structured snapshot."""

    test_module: str
    test_name: str
    update: bool

    def assert_block(self, block: Block, name: str) -> None:
        """Compare `block`'s char+style serialization against `<name>.json`."""
        payload = serialize_block(block)
        # ensure_ascii=False keeps 世/→/█ literal in the diff; trailing newline
        # for clean git blobs. No line-level rstrip — the structure is exact.
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

        path = SNAPSHOTS_DIR / self.test_module / self.test_name / f"{name}.json"

        if self.update:
            # Explicit regeneration (--update): write and pass.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return

        if not path.exists():
            # Bootstrap a missing snapshot as a reviewable artifact, then FAIL.
            # Auto-passing here would let a new scenario, a typo'd name=, or a
            # deleted snapshot go green on first run with no red→green transition
            # proving the assertion binds — breaking "git diff is the review".
            # Writing then failing yields the artifact AND the proof: review the
            # new <name>.json, commit it, re-run to green.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            pytest.fail(
                f"Appearance snapshot bootstrapped (first run): {path}\n"
                f"Review the new snapshot and re-run — it must transition red→green "
                f"to prove the assertion binds. Use --update to regenerate silently."
            )

        expected = path.read_text()
        if text != expected:
            diff = "".join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    text.splitlines(keepends=True),
                    fromfile=str(path),
                    tofile="actual",
                )
            )
            pytest.fail(f"Appearance mismatch for {path}:\n{diff}")


@pytest.fixture
def appearance(request: pytest.FixtureRequest) -> Appearance:
    return Appearance(
        test_module=request.node.module.__name__,
        test_name=request.node.name,
        update=request.config.getoption("--update-appearance"),
    )
