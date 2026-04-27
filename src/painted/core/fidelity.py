"""Fidelity: three-axis rendering specification.

Fidelity encodes *how much* to show across three independent dimensions:

  depth   — structural disclosure level (0=minimal, 1=summary, 2=detailed, 3=full).
             Maps 1:1 to the old Zoom values. Lens functions receive fidelity.depth
             where they previously received zoom.

  visible — which semantic layers are present (consumer-defined tags).
             Empty frozenset means "nothing extra". Use fidelity.shows(tag) to test.

  chars   — max display width for string values (0 = unlimited).
  lines   — max items to show per collection (0 = unlimited).

CliContext carries a Fidelity. The backward-compat ctx.zoom property
returns Zoom(fidelity.depth) so callers that use ctx.zoom continue to work.

``Depth`` is an alias for ``Zoom`` — either name is fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .zoom import Zoom

# Alias: depth is an int 0-3 mapping to Zoom values.
Depth = Zoom


@dataclass(frozen=True)
class Fidelity:
    """Three-axis rendering specification.

    Axes:
      depth   — structural disclosure (0=minimal, 1=summary, 2=detailed, 3=full)
      visible — which semantic layers are present (consumer-defined tags)
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
