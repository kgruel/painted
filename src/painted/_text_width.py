"""Backwards-compatible re-export from painted.core._text_width."""

from .core._text_width import *  # noqa: F401,F403
from .core._text_width import (  # noqa: F401 — used internally
    _char_width_cache,
    _display_width_cache,
)
