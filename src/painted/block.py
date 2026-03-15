"""Backwards-compatible re-export from painted.core.block."""

from .core.block import *  # noqa: F401,F403
from .core.block import (  # noqa: F401 — used internally
    _ascii_cells,
    _ascii_row_tuple,
    _cached_cell,
    _cells_from_text,
    _char_wrap,
    _freeze_cell_rows,
    _freeze_id_rows,
    _get_cell_map,
    _pad_row,
    _space_cells,
    _style_cell_maps,
    _take_word_prefix,
    _word_wrap,
)
