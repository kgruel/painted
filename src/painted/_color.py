"""Backwards-compatible re-export from painted.core._color."""

from .core._color import *  # noqa: F401,F403
from .core._color import (  # noqa: F401 — used internally
    _idx_to_rgb,
    _nearest_basic,
    _rgb_to_256,
    _rgb_to_basic,
)
