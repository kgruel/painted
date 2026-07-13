"""The framework's default renderer: transcription behind the contract.

``run_cli`` renders by **transcription** when neither ``render=`` nor
``renderer=`` is declared (docs/RENDERER_CONTRACT_DESIGN.md §4) — "optional
renderer" dissolves: there is always a renderer; the default one transcribes.
The renderer contract is ``(data, fidelity, width) → Block``; painted's
transcription lens is ``(content, zoom, width, *, fidelity)``. This module is
the small bridge between the two.

It lives at the **root**, not in ``cli/``: the CLI layer may import ``core`` and
root but not ``views`` (the layer boundary and its two-seam tripwire,
tests/unit/test_architecture_invariants.py), while a root module may compose
``core`` + ``views`` — the same layering ``paint()`` uses (``display.py`` →
``transcribe``). The runner references this root function and installs it as the
default renderer, so no cli→views crossing is minted. The renderer stays private
(§4): a public "reference renderer" name waits for a composing consumer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.block import Block
    from .core.fidelity import Fidelity


def transcription_renderer(state: object, fidelity: Fidelity, width: int | None) -> Block:
    """``run_cli``'s default renderer (§4): transcribe the fetched data through
    the ``(data, fidelity, width)`` contract.

    It is a *default renderer, not a ``paint()`` call*: ``paint()`` re-derives
    its own width and ANSI from ambient state, which would discard the compiled
    Fidelity and the offered width — painted fabricating facts against itself
    (§4). This does fidelity adaptation only — maps ``fidelity.depth`` onto the
    zoom argument and passes the compiled spec through the existing ``fidelity=``
    keyword *intact*, never decomposed into loose facet kwargs (§1).
    ``transcribe`` already carries the ``width: int | None`` law, so a ``None``
    offer (a pipe) transcribes natural. The import is lazy so ``import painted``
    never pays for the views layer on this account."""
    from .views.lens.shape import transcribe

    return transcribe(state, fidelity.depth, width, fidelity=fidelity)
