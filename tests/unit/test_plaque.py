"""Laws of the showcase wall plaque (demos/showcase/_plaque.py).

The plaque exists to stop three conventions from drifting one demo at a time:
a maker's note is named-only, a note is capped, and a note is signed. Each of
those is a test here rather than a line in a review, per the ratchet rule —
the last test in this file is the enumerable-property form over every showcase
on disk, so a fourth demo cannot quietly answer differently.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from painted import Fidelity, Style
from painted.capabilities import Capabilities, use_capabilities
from painted.core.doc import Def, Defs, Prose, Section
from painted.core.errors import DeclarationError

_PROJECT = Path(__file__).resolve().parent.parent.parent
_SHOWCASE = _PROJECT / "demos" / "showcase"


# A plain import, resolving through the path conftest.py sets for the suite.
# It matters that this is the same module object the demos import: otherwise
# `isinstance(demo.PLAQUE, Plaque)` compares two classes from two loads and
# fails for a reason that has nothing to do with the code.
import _plaque as P


def _load(name: str):
    """Load a showcase module the way every demo loader does."""
    path = _SHOWCASE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_plaquetest_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_NOTE_ON = Fidelity(depth=1, visible=frozenset({"note"}))
_NOTE_OFF = Fidelity(depth=1)
_PLATE_WIDTH = 66  # mandelbrot's natural plate: 64 sample columns + its border


def _plaque(**kw):
    base = {
        "title": "Why the third color",
        "note": ("Alpha beta gamma.", "Delta epsilon zeta."),
        "maker": "Claude",
    }
    return P.Plaque(**{**base, **kw})


def _text(block) -> str:
    return "\n".join(
        "".join(cell.char for cell in block.row(r)).rstrip() for r in range(block.height)
    )


# --- The declaration ---


def test_note_tag_is_named_only() -> None:
    """The ruling, encoded: a note is asked for, never implied by depth.

    Depth is anonymous detail about the *subject*; who made a thing is not
    more detail about it. If this ever flips, it flips once, here.
    """
    assert P.NOTE_TAG.name == "note"
    assert P.NOTE_TAG.implied_at is None


def test_note_hidden_at_every_depth_without_the_flag() -> None:
    p = _plaque()
    for depth in range(4):
        assert P.render_plaque(p, fidelity=Fidelity(depth=depth), width=_PLATE_WIDTH) is None


def test_note_shown_at_every_depth_with_the_flag() -> None:
    p = _plaque()
    for depth in range(4):
        fid = Fidelity(depth=depth, visible=frozenset({"note"}))
        block = P.render_plaque(p, fidelity=fid, width=_PLATE_WIDTH)
        assert block is not None
        assert "Alpha beta gamma." in _text(block)


# --- The cap ---


def test_note_over_paragraph_cap_is_refused() -> None:
    with pytest.raises(DeclarationError, match="paragraphs"):
        _plaque(note=tuple(["Short."] * (P.MAX_NOTE_PARAGRAPHS + 1)))


def test_note_over_char_cap_is_refused() -> None:
    with pytest.raises(DeclarationError, match="characters"):
        _plaque(note=("x" * (P.MAX_NOTE_CHARS + 1),))


def test_longest_legal_note_fits_one_screen() -> None:
    """The cap is derived, not picked: the longest legal note is 24 rows.

    24 rows at the 66-column plate width is one standard terminal, and no
    taller than the work the note annotates. This is what makes MAX_NOTE_CHARS
    a number with a reason — raise it and this fails rather than letting notes
    sprawl past the picture they are about.
    """
    per = P.MAX_NOTE_CHARS // P.MAX_NOTE_PARAGRAPHS
    paras = [("word " * (per // 5))[:per] for _ in range(P.MAX_NOTE_PARAGRAPHS)]
    paras[0] += "x" * (P.MAX_NOTE_CHARS - sum(len(p) for p in paras))
    assert sum(len(p) for p in paras) == P.MAX_NOTE_CHARS
    block = P.render_plaque(_plaque(note=tuple(paras)), fidelity=_NOTE_ON, width=_PLATE_WIDTH)
    assert block is not None
    assert block.height <= 24, f"the longest legal note is {block.height} rows"


def test_malformed_plaques_are_refused_at_declaration() -> None:
    for kw, match in (
        ({"title": "  "}, "title"),
        ({"note": ()}, "empty"),
        ({"note": ("real.", "   ")}, "blank"),
        ({"maker": ""}, "maker"),
    ):
        with pytest.raises(DeclarationError, match=match):
            _plaque(**kw)


# --- The signature ---


def test_note_is_signed_and_the_signature_is_right_aligned() -> None:
    block = P.render_plaque(_plaque(), fidelity=_NOTE_ON, width=_PLATE_WIDTH)
    assert block is not None
    last = _text(block).splitlines()[-1]
    assert last.endswith("— Claude")
    assert last.startswith(" "), "the signature hangs at the right margin, not the left"


def test_sections_alone_render_without_a_signature() -> None:
    """A signature signs prose. Facts under the same rule are not signed."""
    p = _plaque(sections=(Section("Score", body=(Defs((Def("x", "1.0 Hz"),)),), tag="score"),))
    block = P.render_plaque(p, fidelity=Fidelity(depth=1, visible=frozenset({"score"})), width=60)
    assert block is not None
    text = _text(block)
    assert "Score" in text and "1.0 Hz" in text
    assert "Claude" not in text
    assert "Alpha beta gamma." not in text


# --- Width, and what it costs ---


def test_plaque_is_width_exact() -> None:
    p = _plaque()
    for width in (28, 40, 66, 80, 120):
        block = P.render_plaque(p, fidelity=_NOTE_ON, width=width)
        assert block is not None
        assert block.width == width, f"width {width} rendered {block.width}"


def test_too_narrow_names_what_it_withheld() -> None:
    """Law 6: the plaque that cannot fit says which content it dropped."""
    p = _plaque(sections=(Section("Score", body=(Prose("s"),), tag="score"),))
    fid = Fidelity(depth=1, visible=frozenset({"note", "score"}))
    block = P.render_plaque(p, fidelity=fid, width=P.MIN_PLAQUE_WIDTH - 1)
    assert block is not None
    text = _text(block)
    assert "withheld" in text
    assert "maker note" in text


def test_the_marker_names_only_what_was_actually_visible() -> None:
    """The evidence comes from the disclosure walk, so it cannot overclaim.

    A marker that listed every declared facet would name content the render
    would have skipped anyway — a location claim inflated into a verdict.
    """
    p = _plaque(sections=(Section("Score", body=(Prose("s"),), tag="score"),))
    narrow = P.MIN_PLAQUE_WIDTH - 1
    only_note = P.render_plaque(p, fidelity=_NOTE_ON, width=narrow)
    assert only_note is not None
    assert "Score" not in _text(only_note)


def test_nothing_visible_renders_nothing_at_all() -> None:
    """None, not an empty Block — an empty block still costs a gap row."""
    assert P.render_plaque(_plaque(), fidelity=_NOTE_OFF, width=_PLATE_WIDTH) is None
    assert P.render_plaque(_plaque(), fidelity=_NOTE_OFF, width=4) is None


# --- Carriers ---


def test_plaque_survives_a_glyphless_carrier() -> None:
    """No box-drawing, no em-dash — the label still reads and stays exact."""
    with use_capabilities(Capabilities(color=False, glyph=False, link=False)):
        block = P.render_plaque(_plaque(), fidelity=_NOTE_ON, width=_PLATE_WIDTH)
    assert block is not None
    text = _text(block)
    assert "─" not in text and "—" not in text
    assert "-- Claude" in text
    assert block.width == _PLATE_WIDTH


def test_over_long_title_is_marked_not_silently_clipped() -> None:
    block = P.render_plaque(_plaque(title="T" * 200), fidelity=_NOTE_ON, width=40)
    assert block is not None
    assert "…" in _text(block).splitlines()[0]


# --- The ratchet: no showcase answers these differently ---


def _showcase_sources() -> list[Path]:
    return sorted(p for p in _SHOWCASE.glob("*.py") if not p.name.startswith("_"))


def test_every_showcase_note_comes_from_the_shared_plaque() -> None:
    """The enumerable-property form of the convention, over the demos on disk.

    A showcase may skip the plaque entirely (most do). What it may not do is
    declare its own `note` facet with its own answer on `implied_at` — that is
    exactly the drift the shared Tag object exists to prevent. AST, not import:
    the rule is about what the source declares.
    """
    offenders = []
    for path in _showcase_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Tag"):
                continue
            # Positional and keyword forms both — `Tag(name="note", ...)` is the
            # same declaration wearing different syntax, and a ratchet that sees
            # only one of them ships with a documented way around it.
            named = [node.args[0]] if node.args else []
            named += [kw.value for kw in node.keywords if kw.arg == "name"]
            if any(isinstance(n, ast.Constant) and n.value == "note" for n in named):
                offenders.append(f"{path.name} declares its own Tag('note')")
    assert not offenders, "a maker's note is declared once, in _plaque.NOTE_TAG: " + "; ".join(
        offenders
    )


def test_mandelbrot_uses_the_shared_declaration_object() -> None:
    """The adopting demo takes the object, not a lookalike."""
    mb = _load("mandelbrot")
    assert P.NOTE_TAG in mb._TAGS
    assert isinstance(mb.PLAQUE, P.Plaque)
    assert mb.PLAQUE.maker == "Claude"


def test_mandelbrot_note_flag_still_changes_output() -> None:
    """The honesty rule end-to-end: a declared facet must change output."""
    mb = _load("mandelbrot")
    view = mb._fetch()
    plain = mb._render(view, Fidelity(depth=1), 80)
    noted = mb._render(view, Fidelity(depth=1, visible=frozenset({"note"})), 80)
    assert noted.height > plain.height
    assert "— Claude" in _text(noted)
    assert "— Claude" not in _text(plain)
    # `<=`, matching the existing pin in test_mandelbrot_demo.py: the plate is
    # fixed-size art that never grows past its 64-column sample grid. What the
    # plaque must not do is change that answer.
    assert noted.width == plain.width <= 80


def test_style_is_not_hardcoded_in_the_plaque() -> None:
    """The rule and the signature take their color from the palette, not hex.

    A demo-side component that reached past the palette would be teaching the
    opposite of the library it advertises.
    """
    source = (_SHOWCASE / "_plaque.py").read_text(encoding="utf-8")
    assert "#" not in source.split('"""', 2)[-1].replace("# ", "%%"), "no literal hex in _plaque"
    assert "current_palette()" in source
    assert Style(fg="red") != Style()  # sanity: Style comparison is meaningful
