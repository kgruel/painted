"""Renderer: the framework-seam renderer contract, as a type.

The render model's central unit is one semantic renderer reused unchanged
across progressively capable hosts (docs/RENDERER_CONTRACT_DESIGN.md §1). Its
canonical shape:

    def renderer(data, fidelity: Fidelity, width: int | None) -> Block: ...

  data     — domain state, whatever ``fetch`` produced; painted never interprets it.
  fidelity — the compiled disclosure spec, intact (never decomposed into kwargs).
  width    — the offered allocation: the columns the host actually gives the
             renderer, ``None`` when the destination has no real geometry to
             offer (exact when offered, natural sizing when ``None``).
  returns  — a content ``Block``; never writes, never exits, never consults delivery.

``Renderer`` lives in ``painted.core`` — shared rendering vocabulary beside the
``Fidelity`` spec it references, following the established split (the spec in
core, the grammar that compiles into it in cli). Core placement is deliberate:
the 0.13 host rung runs the same renderer through ``Surface``, and ``tui``
imports nothing from ``cli`` (§3). ``painted.cli`` re-exports it for convenience.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from .block import Block
    from .fidelity import Fidelity

__all__ = ["Renderer"]

T = TypeVar("T")

# A type alias, not a Protocol: the contract is a plain callable shape, and the
# concept filter (§3) found nothing a nominal type would carry that the three
# explicit inputs do not already make visible. Block/Fidelity are forward refs
# so the alias costs no runtime imports (core.renderer stays stdlib-only).
Renderer = Callable[[T, "Fidelity", "int | None"], "Block"]
