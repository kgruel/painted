"""Shape lens: auto-dispatching renderer based on data shape."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from ...core._text_width import display_width, truncate, truncate_ellipsis

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity
from ...core.block import Block
from ...core.cell import Style
from ...core.compose import fit_to_width, join_horizontal, join_vertical

# Sampling limits for large data at zoom >= 2
_MAX_DICT_ITEMS = 20
_MAX_LIST_ITEMS = 20
_MAX_STR_DISPLAY = 200

# Absolute recursion floor for the built-in path. Zoom-decrement already bounds
# recursion for well-behaved data, but a high zoom on a deep (or cyclic) structure
# defeats it — this is the hard stop. At the floor we emit a muted `…` instead of
# descending.
_MAX_DEPTH = 6

# Container markers, rendered in the palette's muted role.
_CYCLE_MARKER = "↻ <cycle>"
_DEPTH_MARKER = "…"


def _is_namedtuple(x: Any) -> bool:
    """A tuple carrying the NamedTuple protocol (declared field schema)."""
    return isinstance(x, tuple) and hasattr(x, "_fields") and hasattr(x, "_asdict")


def _muted_marker(text: str, width: int) -> Block:
    """A width-exact marker in the palette's muted role (cycle/depth sentinels)."""
    from ...palette import current_palette

    style = current_palette().muted
    if display_width(text) > width:
        text = truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
    return Block.text(text, style, width=width)


def _is_numeric_sequence(data: Any) -> bool:
    """Check if data is a non-empty list/tuple of all numbers."""
    if not isinstance(data, (list, tuple)) or not data:
        return False
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in data)


def shape_lens(content: Any, zoom: int, width: int, *, fidelity: Fidelity | None = None) -> Block:
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

    This is the *interpreting* renderer: it infers arrangement (chart/tree) from
    shape. paint() takes it only via an explicit ``lens=shape_lens``; paint()'s
    no-lens default is ``transcribe`` (below), which never infers.
    """
    return _shape_lens(content, zoom, width, fidelity, frozenset(), 0, infer=True)


def transcribe(content: Any, zoom: int, width: int, *, fidelity: Fidelity | None = None) -> Block:
    """Transcribe a subject by the shape it *declares* — never inferring one.

    paint()'s no-lens default (PAINT_DESIGN §3). Identical to ``shape_lens``
    except the three inference stanzas are dropped: a numeric sequence stays
    items (not a chart), a numeric or nested dict stays a key/value table (not a
    chart or tree). Declared schemas still transcribe their declared structure
    (dataclass / NamedTuple -> fields, Enum -> ``Type.MEMBER``). The refusal is
    recursive: nested values transcribe as transcription, so inference never
    re-enters at depth.
    """
    return _shape_lens(content, zoom, width, fidelity, frozenset(), 0, infer=False)


def _shape_lens(
    content: Any,
    zoom: int,
    width: int,
    fidelity: Fidelity | None,
    seen: frozenset[int],
    depth: int,
    *,
    infer: bool,
) -> Block:
    """The recursive worker, shared by `shape_lens` (infer=True) and `transcribe`
    (infer=False). Threads cycle state (`seen` = container ids on the current
    path), an absolute `depth` counter, and `infer` through the built-in path;
    the public entries seed all three. When `infer` is False the three inference
    stanzas (dict->chart, dict->tree, numeric-seq->chart) are skipped and `infer`
    is threaded into the container helpers so nested values transcribe too.
    Scalars are leaves and skip the guards; every container is guarded before it
    descends."""
    if width <= 0:
        return Block.empty(0, 1)

    if content is None:
        return _render_scalar(content, zoom, width, fidelity)

    # Declared schema: an Enum renders as the scalar `TypeName.MEMBER` (checked
    # before the numeric/str scalar branch so IntEnum/StrEnum honor the name).
    if isinstance(content, Enum):
        return _render_enum(content, width)

    if isinstance(content, bool):
        # Check bool before int since bool is subclass of int
        return _render_scalar(content, zoom, width, fidelity)

    if isinstance(content, (str, int, float)):
        return _render_scalar(content, zoom, width, fidelity)

    # From here down every branch recurses into children. A self-referential or
    # pathologically deep structure would otherwise blow the stack — guard both
    # before descending: cycle first (tighter), then the absolute floor.
    if id(content) in seen:
        return _muted_marker(_CYCLE_MARKER, width)
    if depth >= _MAX_DEPTH:
        return _muted_marker(_DEPTH_MARKER, width)
    seen = seen | {id(content)}
    depth += 1

    # Dict: infer chart (all-numeric) / tree (nested) only when inferring;
    # otherwise transcribe straight to the key/value table.
    if isinstance(content, dict):
        if content and infer:
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

                return chart_lens(content, zoom, width, fidelity=fidelity)

            if any_nested:
                from .tree import tree_lens

                return tree_lens(content, zoom, width, fidelity=fidelity)

        return _render_dict(content, zoom, width, fidelity, seen, depth, infer=infer)

    # Declared schema: a dataclass instance renders its fields through the dict
    # machinery. `repr=False` is declared suppression — honor it by dropping the
    # field. Every value routes back through the budgeted recursive path.
    if is_dataclass(content) and not isinstance(content, type):
        rendered = {f.name: getattr(content, f.name) for f in fields(content) if f.repr}
        return _render_dict(rendered, zoom, width, fidelity, seen, depth, infer=infer)

    # Declared schema: a NamedTuple renders its `_asdict()` through the dict path.
    if _is_namedtuple(content):
        return _render_dict(
            dict(content._asdict()), zoom, width, fidelity, seen, depth, infer=infer
        )

    # Auto-dispatch: numeric sequences -> chart (only when inferring)
    if infer and _is_numeric_sequence(content):
        from .chart import chart_lens

        return chart_lens(content, zoom, width, fidelity=fidelity)

    # list / tuple both transcribe as items (a tuple declares order). A NamedTuple
    # was handled above; a bare tuple lands here. The type label keeps the
    # zoom<=0 count honest — a tuple must not report itself as "list[N]".
    if isinstance(content, (list, tuple)):
        label = "tuple" if isinstance(content, tuple) else "list"
        return _render_list(
            list(content), zoom, width, fidelity, seen, depth, infer=infer, label=label
        )

    # frozenset is not a subclass of set, so it must be named explicitly — both
    # declare an unordered collection and transcribe as tags.
    if isinstance(content, (set, frozenset)):
        return _render_set(content, zoom, width)

    # Fallback: treat as string representation
    return _render_scalar(str(content), zoom, width, fidelity)


def _render_enum(value: Enum, width: int) -> Block:
    """Render an Enum member as the scalar `TypeName.MEMBER`, width-exact.

    A composite/zero Flag value has `.name is None` (no single declared member);
    fall back to the enum's own str() — `Perm(0)`, `Perm.R|W`, `0` — never the
    misleading `TypeName.None`.
    """
    name = value.name
    label = f"{type(value).__name__}.{name}" if name is not None else str(value)
    style = Style()
    if display_width(label) > width:
        label = truncate_ellipsis(label, width) if width > 1 else truncate(label, width)
    return Block.text(label, style, width=width)


def _render_scalar(value: Any, zoom: int, width: int, fidelity: Fidelity | None = None) -> Block:
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
    max_str = fidelity.chars if fidelity and fidelity.chars > 0 else _MAX_STR_DISPLAY
    text = _format_value(value)
    if isinstance(value, str) and display_width(text) > max_str:
        original_chars = len(value)
        text = truncate(text, max_str) + f"... [{original_chars} chars]"
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


def _render_dict(
    d: dict,
    zoom: int,
    width: int,
    fidelity: Fidelity | None,
    seen: frozenset[int],
    depth: int,
    *,
    infer: bool,
) -> Block:
    """Render dict at zoom levels. `infer` is threaded to the recursive value
    render so nested values follow the same transcribe/interpret discipline."""
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
        val_block = _shape_lens(
            value, max(0, zoom - 1), val_col_width, fidelity, seen, depth, infer=infer
        )
        return join_horizontal(key_block, val_block)

    rows: list[Block] = []
    key_style = Style(bold=True)

    # Sample items if too many
    max_items = fidelity.lines if fidelity and fidelity.lines > 0 else _MAX_DICT_ITEMS
    items = list(d.items())
    truncated = len(items) - max_items if len(items) > max_items else 0
    if truncated:
        items = items[:max_items]

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
        val_block = _shape_lens(
            value, nested_zoom, val_col_width, fidelity, seen, depth, infer=infer
        )

        row = join_horizontal(key_block, val_block)
        rows.append(row)

    if truncated:
        footer = Block.text(f"... +{truncated} more", Style(dim=True), width=width)
        rows.append(footer)

    if not rows:
        return Block.text("{}", style, width=width)

    return join_vertical(*rows)


def _render_list(
    lst: list,
    zoom: int,
    width: int,
    fidelity: Fidelity | None,
    seen: frozenset[int],
    depth: int,
    *,
    infer: bool,
    label: str = "list",
) -> Block:
    """Render list at zoom levels. `infer` is threaded to the recursive item
    render so nested items follow the same transcribe/interpret discipline.
    `label` names the sequence type for the zoom<=0 count (bare tuples pass
    "tuple" so the count doesn't misreport them as a list)."""
    style = Style()

    if zoom <= 0:
        # Count only
        text = f"{label}[{len(lst)}]"
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
    max_items = fidelity.lines if fidelity and fidelity.lines > 0 else _MAX_LIST_ITEMS
    truncated = len(lst) - max_items if len(lst) > max_items else 0
    visible = lst[:max_items] if truncated else lst

    rows: list[Block] = []
    prefix_width = 2  # "- "
    item_width = max(1, width - prefix_width)

    for item in visible:
        # Render item recursively with reduced zoom
        nested_zoom = max(0, zoom - 1)
        item_block = _shape_lens(item, nested_zoom, item_width, fidelity, seen, depth, infer=infer)

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

    # Fit to exact width: the "- " prefix can push a row past its budget at narrow
    # widths; this clamps every row (and, via recursion, nested lists) to the contract.
    return fit_to_width(join_vertical(*rows), width)


def _render_set(s: set | frozenset, zoom: int, width: int) -> Block:
    """Render set/frozenset at zoom levels."""
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
    if isinstance(item, tuple):
        # Mirror the list summary; a bare tuple item must not fall through to a
        # raw repr byte-sliced to 10 chars.
        return f"tuple[{len(item)}]"
    if isinstance(item, set):
        return f"set[{len(item)}]"
    return str(item)[:10]
