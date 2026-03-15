"""Backwards-compatible re-export from painted.core.compose."""

from .core.compose import *  # noqa: F401,F403
from .core.compose import (  # noqa: F401 — used internally
    _SPACE_CELL,
    _border_cell,
    _border_cell_cache,
    _halign_offset,
    _valign_offset,
)
