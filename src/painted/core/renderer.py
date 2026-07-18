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
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from .block import Block
    from .fidelity import Fidelity

__all__ = ["Renderer", "HeightRenderer"]

T = TypeVar("T")
# The data type is an *input* — contravariant, the variance a Callable already
# gives ``Renderer`` structurally. A Protocol must declare it (a plain ``T`` in
# an argument position is flagged), so ``HeightRenderer`` uses its own
# contravariant var while the ``Renderer`` alias keeps the module ``T``.
T_contra = TypeVar("T_contra", contravariant=True)

# A type alias, not a Protocol: the contract is a plain callable shape, and the
# concept filter (§3) found nothing a nominal type would carry that the three
# explicit inputs do not already make visible. Block/Fidelity are forward refs
# so the alias costs no runtime imports (core.renderer stays stdlib-only).
Renderer = Callable[[T, "Fidelity", "int | None"], "Block"]


class HeightRenderer(Protocol[T_contra]):
    """The height-aware renderer contract — the offered arm of the dual
    allocation contract (docs/HOST_RUNG_DESIGN.md §4).

        def renderer(data, fidelity, width, *, height: int | None) -> Block: ...

    Identical to ``Renderer`` but for one added input: a keyword-only ``height``
    the host offers per delivery. ``height`` has **no default** — the host always
    passes it explicitly (``height=None`` on a gated-off delivery, an integer on
    a gated-on one), so an omitted offer is an observable decision in the call,
    never Python's accidental defaulting (§4). When passed an integer ``H`` the
    returned Block must have exactly ``H`` rows (the conditional honesty property,
    §5); ``height=None`` means natural sizing, the omitted arm.

    A ``Protocol`` rather than a ``Callable`` alias because ``Callable`` cannot
    spell a keyword-only parameter. The parameter name *is* the acceptance
    declaration (``height_renderer=`` on the binding), so no separate boolean can
    drift from the callable's real shape. Generic in the ``data`` type, which is
    an input — contravariant, the variance ``Renderer``'s Callable already has
    structurally. Block/Fidelity stay forward refs under
    ``from __future__ import annotations`` so this costs no runtime import —
    ``core.renderer`` stays stdlib-only.
    """

    def __call__(
        self, data: T_contra, fidelity: Fidelity, width: int | None, *, height: int | None
    ) -> Block: ...
