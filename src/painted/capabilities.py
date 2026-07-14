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

from contextvars import ContextVar, Token
from contextlib import AbstractContextManager
from dataclasses import dataclass


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
