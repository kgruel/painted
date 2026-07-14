"""Capabilities: ambient render-capability policy — which visual carriers a delivery supports.

Three facets a renderer consults when *choosing content*, not when
serializing it (RENDERER_CONTRACT_DESIGN.md §9). A frozen value in a
ContextVar, read where it is consumed — exactly where ``current_palette()``
is read today.

Usage:
    from painted.capabilities import current_capabilities, use_capabilities, Capabilities

    caps = current_capabilities()
    if caps.color:
        ...

    # Override ambient capabilities (setter)
    use_capabilities(Capabilities(color=False))

    # Scoped override (context manager)
    with use_capabilities(Capabilities(color=False, link=False)):
        ...
"""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO


@dataclass(frozen=True)
class Capabilities:
    """Which visual carriers the destination supports — a renderer input.

    Each facet answers one question a renderer asks when choosing content, not
    when serializing it (§9.1). Booleans deliberately: *how much* color or
    *which* glyph are the mechanisms this vocabulary fences off (``ColorDepth``,
    ``IconSet``), never re-decided here.
    """

    # May the renderer choose a color-bearing form over a color-free one?
    color: bool = True
    # May non-ASCII carrier families (not named icon slots) be chosen as content?
    glyph: bool = True
    # Is this delivery's serializer configured to emit link carriers (OSC 8 / anchors)?
    link: bool = True


# --- ContextVar delivery ---

DEFAULT_CAPABILITIES = Capabilities()

_capabilities: ContextVar[Capabilities] = ContextVar("capabilities", default=DEFAULT_CAPABILITIES)


class _CapabilitiesOverride(AbstractContextManager[None]):
    def __init__(self, token: Token[Capabilities]) -> None:
        self._token = token
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            _capabilities.reset(self._token)
            self._active = False
        return False


def current_capabilities() -> Capabilities:
    """Get the ambient capabilities."""

    return _capabilities.get()


def use_capabilities(caps: Capabilities) -> AbstractContextManager[None]:
    """Set the ambient capabilities for the current context.

    Capabilities are set immediately (setter semantics) and the return value can
    be used as a context manager for scoped overrides:

        use_capabilities(Capabilities(color=False))  # ambient until changed again

        with use_capabilities(Capabilities(color=False)):
            ...  # restored on exit
    """

    token = _capabilities.set(caps)
    return _CapabilitiesOverride(token)


def reset_capabilities() -> None:
    """Reset to the default capabilities (all facets ``True``)."""

    _capabilities.set(DEFAULT_CAPABILITIES)


# --- Host resolution ---
#
# The `run_cli`/`paint()` bracket. Both hosts deliver to a destination stream and
# resolve the same per-facet snapshot from it (§9.3, PAINT_DESIGN §8), so the
# resolution lives once here rather than duplicated at each host. Cross-repo hosts
# resolve their own (glyph in particular is host policy for siftd/loops) — this is
# the in-repo default, not the only mapping.

# A representative non-ASCII carrier glyph (full block). The glyph facet gates
# whether a renderer may reach for *carrier families* like half-block portraits,
# box-drawing charts, and unicode ramps — this probes whether the destination's
# encoding can carry one, rather than name-matching a codec allowlist.
_CARRIER_PROBE = "█"  # █


def _stream_carries_unicode(stream: TextIO) -> bool:
    """Does this destination's encoding carry non-ASCII carrier glyphs? (§9.3)

    ``True`` for a UTF-8-capable stream (a UTF-8 pipe is glyph-capable — glyph
    does *not* co-narrow with color), ``False`` for a known-ASCII destination, and
    conservatively ``False`` when the encoding is unknowable. Probes the encoding
    with a representative carrier glyph so any Unicode-capable codec resolves
    ``True`` and any narrow codec resolves ``False`` — no codec allowlist to drift.
    """
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return False
    try:
        _CARRIER_PROBE.encode(encoding)
    except (LookupError, UnicodeError):
        return False
    return True


def resolve_no_color() -> bool:
    """The one NO_COLOR read for a delivery, resolved as ``Writer`` resolves it.

    A host reads this **once** per delivery and feeds the result to both consumers
    of the snapshot — the ``color`` facet and the serializing ``Writer`` (§9.1) —
    so a mid-run env change cannot split content choice from serialization. An
    explicit ``no_color=`` override, where a host has one, wins over this; these
    hosts have none, so the environment is the whole story.
    """
    return bool(os.environ.get("NO_COLOR"))


def resolve_host_capabilities(stream: TextIO, *, use_ansi: bool, no_color: bool) -> Capabilities:
    """Resolve the ``run_cli``/``paint()`` host bracket per facet (§9.3).

    - **color** — ``use_ansi and not no_color``. ANSI off (``--plain``, a non-TTY)
      or the ``no_color`` snapshot narrows it. ``no_color`` is the caller's single
      NO_COLOR read (``resolve_no_color``), passed here *and* into the delivery's
      Writer so the two never split (§9.1). The depth conjunct from the §9.3 table
      is vacuous for these hosts: neither forces a ``ColorDepth``, and a non-TTY —
      where the writer would resolve ``NONE`` — already has ``use_ansi=False`` (a
      real TTY never detects ``NONE``).
    - **glyph** — the destination encoding (``_stream_carries_unicode``); §9.4
      pairs an ASCII-safe ``IconSet`` at the install site whenever this is
      ``False``.
    - **link** — ``use_ansi``. The ANSI serializer emits OSC 8 carriers and these
      hosts always enable hyperlinks; a plain destination emits none. Never bare
      TTY-ness (§9.3).
    """
    return Capabilities(
        color=use_ansi and not no_color,
        glyph=_stream_carries_unicode(stream),
        link=use_ansi,
    )


def resolve_surface_capabilities(
    stream: TextIO, *, no_color: bool, depth_is_none: bool, hyperlinks: bool
) -> Capabilities:
    """Resolve the ``Surface`` host bracket per facet (§9.3 Surface row).

    The alt-screen establishes ANSI *control* support only — it implies none of
    the facets:

    - **color** — ``not no_color and not depth_is_none``. There is no ``use_ansi``
      gate (the alt screen is always ANSI), so color still consults the one
      NO_COLOR/depth snapshot: a ``NO_COLOR`` environment or a colorless
      destination (``ColorDepth.NONE``) narrows it.
    - **glyph** — the destination encoding, as everywhere.
    - **link** — the serializer's ``hyperlinks`` configuration, kept as its
      serializer-configuration meaning (not bare alt-screen-ness).

    Every input is read from the Surface's *own writer* — the single snapshot both
    the facets and that writer's serialization share (§9.1).
    """
    return Capabilities(
        color=(not no_color) and not depth_is_none,
        glyph=_stream_carries_unicode(stream),
        link=hyperlinks,
    )
