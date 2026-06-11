"""Fidelity: the compiled disclosure spec.

Fidelity is what the flag grammar (``-v``, ``--thinking``, ``--max-lines``)
compiles into — the disclosure half of the CLI contract
(docs/FIDELITY_DESIGN.md). Its fields:

  depth   — anonymous detail: how closely am I looking (0=minimal, 1=summary,
             2=detailed, 3=full; open int above that). The rung-1 axis.

  visible — named facets: which toggleable layers are present. Tags whose
             flag was passed or whose ``implied_at`` the depth reached,
             fully resolved at compile time. Use fidelity.shows(tag); empty
             frozenset means "nothing extra".

  chars   — max display width for string values (0 = unlimited).
  lines   — max items to show per collection (0 = unlimited).

CliContext carries a Fidelity whole — renderers consuming beyond rung 1
receive the spec intact, never exploded into kwargs. ``ctx.zoom`` is the
rung-1 porthole onto it: ``Zoom(min(depth, 3))``, blessed permanently.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

__all__ = ["Fidelity"]


@dataclass(frozen=True)
class Fidelity:
    """The compiled disclosure spec.

    Fields:
      depth   — anonymous detail (0=minimal, 1=summary, 2=detailed, 3=full)
      visible — named facets present, resolved at compile time
      chars   — character budget per text block (0=unlimited)
      lines   — line budget per section (0=unlimited)
    """

    depth: int = 1
    visible: frozenset[str] = field(default_factory=frozenset)
    chars: int = 0
    lines: int = 0

    def shows(self, tag: str) -> bool:
        """True if tag is explicitly in the visible set. Empty set = nothing extra."""
        return tag in self.visible

    def with_depth(self, depth: int) -> Fidelity:
        return replace(self, depth=depth)

    def with_visible(self, *tags: str) -> Fidelity:
        return replace(self, visible=frozenset(tags))

    def with_density(self, *, chars: int = 0, lines: int = 0) -> Fidelity:
        return replace(self, chars=chars, lines=lines)

    @property
    def has_char_limit(self) -> bool:
        return self.chars > 0

    @property
    def has_line_limit(self) -> bool:
        return self.lines > 0
