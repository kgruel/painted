"""Shape lens: auto-dispatching renderer based on data shape."""

from __future__ import annotations

from typing import Any

from ...core._text_width import display_width, truncate, truncate_ellipsis
from ...core.block import Block
from ...core.cell import Style
from ...core.compose import join_horizontal, join_vertical

# Sampling limits for large data at zoom >= 2
_MAX_DICT_ITEMS = 20
_MAX_LIST_ITEMS = 20
_MAX_STR_DISPLAY = 200


def _is_numeric_sequence(data: Any) -> bool:
    """Check if data is a non-empty list/tuple of all numbers."""
    if not isinstance(data, (list, tuple)) or not data:
        return False
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in data)


def _is_labeled_numeric(data: Any) -> bool:
    """Check if data is a non-empty dict with all numeric values."""
    if not isinstance(data, dict) or not data:
        return False
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in data.values())


def _is_hierarchical(data: Any) -> bool:
    """Check if data is a dict containing nested dict/list values."""
    if not isinstance(data, dict) or not data:
        return False
    return any(isinstance(v, (dict, list)) and v for v in data.values())


def shape_lens(content: Any, zoom: int, width: int) -> Block:
    """Auto-dispatching renderer: picks the best strategy based on data shape.

    Dispatch rules:
    - Numeric sequences (list/tuple of numbers) -> chart_lens
    - Labeled numeric dicts (all values are numbers) -> chart_lens
    - Hierarchical dicts (nested dict/list values) -> tree_lens
    - Everything else -> built-in shape rendering

    Zoom levels (for built-in rendering):
    - 0: minimal (type/count)
    - 1: summary (keys or truncated values)
    - 2: full (complete representation)

    For nested structures, each nesting level reduces effective zoom by 1.
    """
    if width <= 0:
        return Block.empty(0, 1)

    if content is None:
        return _render_scalar(content, zoom, width)

    if isinstance(content, bool):
        # Check bool before int since bool is subclass of int
        return _render_scalar(content, zoom, width)

    if isinstance(content, (str, int, float)):
        return _render_scalar(content, zoom, width)

    # Auto-dispatch for dicts in one pass over values
    if isinstance(content, dict):
        if content:
            values = content.values()
            all_numeric = True
            any_nested = False
            for v in values:
                is_numeric = isinstance(v, (int, float)) and not isinstance(v, bool)
                if not is_numeric:
                    all_numeric = False
                if isinstance(v, (dict, list)) and v:
                    any_nested = True
                if any_nested and not all_numeric:
                    break

            if all_numeric:
                from .chart import chart_lens

                return chart_lens(content, zoom, width)

            if any_nested:
                from .tree import tree_lens

                return tree_lens(content, zoom, width)

        return _render_dict(content, zoom, width)

    # Auto-dispatch: numeric sequences -> chart
    if _is_numeric_sequence(content):
        from .chart import chart_lens

        return chart_lens(content, zoom, width)

    if isinstance(content, list):
        return _render_list(content, zoom, width)

    if isinstance(content, set):
        return _render_set(content, zoom, width)

    # Fallback: treat as string representation
    return _render_scalar(str(content), zoom, width)


def _render_scalar(value: Any, zoom: int, width: int) -> Block:
    """Render scalar values (str, int, float, bool, None) at zoom levels."""
    style = Style()

    if zoom <= 0:
        # Type name only
        type_name = type(value).__name__
        return Block.text(type_name, style, width=width)

    if zoom == 1:
        # Truncated value
        text = _format_value(value)
        if display_width(text) > width:
            text = truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
        return Block.text(text, style, width=width)

    # zoom >= 2: full value (with length indicator for long strings)
    text = _format_value(value)
    if isinstance(value, str) and display_width(text) > _MAX_STR_DISPLAY:
        original_chars = len(value)
        text = truncate(text, _MAX_STR_DISPLAY) + f"... [{original_chars} chars]"
    if display_width(text) > width:
        text = truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
    return Block.text(text, style, width=width)


def _format_value(value: Any) -> str:
    """Format a value for display."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    return str(value)


def _render_dict(d: dict, zoom: int, width: int) -> Block:
    """Render dict at zoom levels."""
    style = Style()

    if zoom <= 0:
        # Count only
        text = f"dict[{len(d)}]"
        return Block.text(text, style, width=width)

    if zoom == 1:
        # Compact key: value pairs, comma-separated
        if not d:
            text = "{}"
        else:
            pairs = ", ".join(f"{k}: {v}" for k, v in d.items())
            if display_width(pairs) > width:
                pairs = truncate_ellipsis(pairs, width) if width > 1 else truncate(pairs, width)
            text = pairs
        return Block.text(text, style, width=width)

    # zoom >= 2: key-value table
    if not d:
        return Block.text("{}", style, width=width)

    if len(d) == 1:
        ((key, value),) = d.items()
        key_style = Style(bold=True)
        key_text = f"{key}:"
        key_col_width = min(display_width(key_text) + 1, width // 2)
        if display_width(key_text) > key_col_width:
            key_text = (
                truncate_ellipsis(key_text, key_col_width)
                if key_col_width > 1
                else truncate(key_text, key_col_width)
            )
        val_col_width = max(1, width - key_col_width)
        key_block = Block.text(key_text, key_style, width=key_col_width)
        val_block = shape_lens(value, max(0, zoom - 1), val_col_width)
        return join_horizontal(key_block, val_block)

    rows: list[Block] = []
    key_style = Style(bold=True)

    # Sample items if too many
    items = list(d.items())
    truncated = len(items) - _MAX_DICT_ITEMS if len(items) > _MAX_DICT_ITEMS else 0
    if truncated:
        items = items[:_MAX_DICT_ITEMS]

    # Calculate key column width (max key length + 2 for ": ")
    max_key_len = max((display_width(str(k)) for k, _ in items), default=0)
    key_col_width = min(max_key_len + 2, width // 2)
    val_col_width = max(1, width - key_col_width)

    for key, value in items:
        key_text = str(key) + ":"
        if display_width(key_text) > key_col_width:
            key_text = (
                truncate_ellipsis(key_text, key_col_width)
                if key_col_width > 1
                else truncate(key_text, key_col_width)
            )
        key_block = Block.text(key_text, key_style, width=key_col_width)

        # Render value recursively with reduced zoom
        nested_zoom = max(0, zoom - 1)
        val_block = shape_lens(value, nested_zoom, val_col_width)

        row = join_horizontal(key_block, val_block)
        rows.append(row)

    if truncated:
        footer = Block.text(f"... +{truncated} more", Style(dim=True), width=width)
        rows.append(footer)

    if not rows:
        return Block.text("{}", style, width=width)

    return join_vertical(*rows)


def _render_list(lst: list, zoom: int, width: int) -> Block:
    """Render list at zoom levels."""
    style = Style()

    if zoom <= 0:
        # Count only
        text = f"list[{len(lst)}]"
        return Block.text(text, style, width=width)

    if zoom == 1:
        # First N items inline, comma-separated
        if not lst:
            text = "[]"
        else:
            items: list[str] = []
            total_len = 0
            for item in lst:
                item_str = _summarize_item(item)
                # Check if adding this item would exceed width
                sep_len = 2 if items else 0  # ", "
                item_w = display_width(item_str)
                if total_len + sep_len + item_w > width - 3:  # reserve for "..."
                    items.append("...")
                    break
                items.append(item_str)
                total_len += sep_len + item_w
            text = ", ".join(items)
        return Block.text(text, style, width=width)

    # zoom >= 2: vertical list
    if not lst:
        return Block.text("[]", style, width=width)

    # Sample items if too many
    truncated = len(lst) - _MAX_LIST_ITEMS if len(lst) > _MAX_LIST_ITEMS else 0
    visible = lst[:_MAX_LIST_ITEMS] if truncated else lst

    rows: list[Block] = []
    prefix_width = 2  # "- "
    item_width = max(1, width - prefix_width)

    for item in visible:
        # Render item recursively with reduced zoom
        nested_zoom = max(0, zoom - 1)
        item_block = shape_lens(item, nested_zoom, item_width)

        # Prefix with "- "
        prefix_block = Block.text("- ", Style(dim=True))

        # Join prefix with first row of item, keep remaining rows aligned
        if item_block.height == 1:
            row = join_horizontal(prefix_block, item_block)
            rows.append(row)
        else:
            # Multi-row item: prefix first row, indent remaining
            from ...core.cell import Cell

            first_row_cells = [Cell("-", Style(dim=True)), Cell(" ", Style())]
            first_row_cells.extend(item_block.row(0))
            rows.append(Block([first_row_cells], len(first_row_cells)))

            for row_idx in range(1, item_block.height):
                indent_cells = [Cell(" ", Style()), Cell(" ", Style())]
                indent_cells.extend(item_block.row(row_idx))
                rows.append(Block([indent_cells], len(indent_cells)))

    if truncated:
        footer = Block.text(f"... +{truncated} more", Style(dim=True), width=width)
        rows.append(footer)

    return join_vertical(*rows)


def _render_set(s: set, zoom: int, width: int) -> Block:
    """Render set at zoom levels."""
    style = Style()

    if zoom <= 0:
        # Count only
        text = f"set[{len(s)}]"
        return Block.text(text, style, width=width)

    # zoom >= 1: inline tags [a] [b] [c]
    if not s:
        return Block.text("{}", style, width=width)

    tags: list[str] = []
    total_len = 0

    for item in sorted(s, key=str):
        tag = f"[{item}]"
        sep_len = 1 if tags else 0  # space separator
        if total_len + sep_len + display_width(tag) > width:
            break
        tags.append(tag)
        total_len += sep_len + display_width(tag)

    text = " ".join(tags)
    return Block.text(text, style, width=width)


def _summarize_item(item: Any) -> str:
    """Create a short summary string for a list item."""
    if item is None:
        return "None"
    if isinstance(item, bool):
        return str(item)
    if isinstance(item, str):
        if display_width(item) > 10:
            return truncate_ellipsis(item, 10) if 10 > 1 else truncate(item, 10)
        return item
    if isinstance(item, (int, float)):
        return str(item)
    if isinstance(item, dict):
        return f"dict[{len(item)}]"
    if isinstance(item, list):
        return f"list[{len(item)}]"
    if isinstance(item, set):
        return f"set[{len(item)}]"
    return str(item)[:10]
