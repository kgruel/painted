"""Tree lens: hierarchical data with branch characters."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity

from ...core._text_width import display_width, truncate_ellipsis, truncate
from ...core.block import Block
from ...core.cell import EMPTY_CELL, Style
from ...core.compose import join_vertical

if TYPE_CHECKING:
    from ...icon_set import IconSet

# Type alias for node renderer callback
NodeRenderer = Callable[[str, Any, int], Block]


def _get_tree_icons(icons: IconSet | None) -> tuple[str, str, str, str]:
    """Get tree branch characters from icons or ambient defaults."""
    from ...icon_set import current_icons

    ic = icons or current_icons()
    return ic.tree_branch, ic.tree_last, ic.tree_indent, ic.tree_space


def tree_lens(
    data: Any,
    zoom: int,
    width: int,
    *,
    node_renderer: NodeRenderer | None = None,
    icons: IconSet | None = None,
    fidelity: Fidelity | None = None,
) -> Block:
    """Render hierarchical data as an indented tree with branch characters.

    Supports:
    - Nested dicts: keys as nodes, values as children
    - Tuples (label, children): explicit tree structure
    - Objects with .children attribute: node protocol

    Zoom levels:
    - 0: Root label + child count
    - 1: Root + immediate children (single line each)
    - 2+: Full tree, depth expands with zoom

    Args:
        data: Tree data in supported format.
        zoom: Zoom level (0-4).
        width: Available width in characters.
        node_renderer: Optional (key, value, depth) -> Block for custom node formatting.
            Branch characters are added automatically; return content only.
        icons: Optional IconSet override (uses ambient if None).

    Returns:
        Block with rendered tree.
    """
    if width <= 0:
        return Block.empty(0, 1)

    label, children = _tree_extract(data)
    tree_branch, tree_last, tree_indent, tree_space = _get_tree_icons(icons)

    if zoom <= 0:
        # Root label + count only
        count = len(children) if children else 0
        text = f"{label} [{count}]" if count else label
        return _tree_truncate(text, width)

    # Build tree rows
    rows: list[Block] = []

    # Root node
    if node_renderer is not None:
        root_block = node_renderer(label, data, 0)
        # Truncate if needed
        if root_block.width > width:
            root_block = Block.text(_truncate_ellipsis(label, width), Style(), width=width)
        rows.append(root_block)
    else:
        rows.append(_tree_truncate(label, width))

    if children:
        _tree_render_children_themed(
            children,
            zoom - 1,
            width,
            "",
            rows,
            1,  # depth
            tree_branch,
            tree_last,
            tree_indent,
            tree_space,
            node_renderer,
        )

    return join_vertical(*rows) if rows else Block.empty(width, 1)


def _tree_extract(data: Any) -> tuple[str, list[tuple[str, Any]] | None]:
    """Extract (label, children) from various tree representations."""
    # Tuple form: (label, children)
    if isinstance(data, tuple) and len(data) == 2:
        label, children = data
        if isinstance(label, str) and (children is None or isinstance(children, (list, dict))):
            if children is None:
                return label, None
            if isinstance(children, dict):
                return label, [(str(k), v) for k, v in children.items()]
            return label, [(str(i), c) for i, c in enumerate(children)]

    # Dict: keys as children
    if isinstance(data, dict):
        if not data:
            return "{}", None
        # Root is implicit, children are key-value pairs
        return "root", [(str(k), v) for k, v in data.items()]

    # Node protocol: has .children attribute
    if hasattr(data, "children") and hasattr(data, "__str__"):
        children_attr = data.children
        if isinstance(children_attr, (list, tuple)):
            child_list = [(str(i), c) for i, c in enumerate(children_attr)]
            return str(data), child_list if child_list else None
        return str(data), None

    # Leaf node
    return str(data), None


def _tree_render_children_themed(
    children: list[tuple[str, Any]],
    remaining_zoom: int,
    width: int,
    prefix: str,
    rows: list[Block],
    depth: int,
    tree_branch: str,
    tree_last: str,
    tree_indent: str,
    tree_space: str,
    node_renderer: NodeRenderer | None,
) -> None:
    """Recursively render children with themed branch characters."""
    for i, (key, value) in enumerate(children):
        is_last = i == len(children) - 1
        branch = tree_last if is_last else tree_branch
        continuation = tree_space if is_last else tree_indent

        _, grandchildren = _tree_extract(value)

        # Calculate available width for content
        branch_prefix = prefix + branch
        content_width = width - display_width(branch_prefix)

        if content_width <= 0:
            continue

        if remaining_zoom <= 0 or grandchildren is None:
            # Leaf or zoom exhausted
            if node_renderer is not None:
                content_block = node_renderer(key, value, depth)
                # Prefix with branch chars
                row_cells = list(
                    Block.text(branch_prefix, Style(), width=display_width(branch_prefix)).row(0)
                )
                # Add content (truncated if needed)
                for cell in content_block.row(0)[:content_width]:
                    row_cells.append(cell)
                # Pad to full width
                while len(row_cells) < width:
                    row_cells.append(EMPTY_CELL)
                rows.append(Block([row_cells], width))
            else:
                # Default formatting
                if grandchildren:
                    text = f"{key} [{len(grandchildren)}]"
                else:
                    # Show value for leaf nodes
                    if value is None or isinstance(value, (str, int, float, bool)):
                        text = f"{key}: {value}"
                    else:
                        text = key
                row_text = branch_prefix + _truncate_ellipsis(text, content_width)
                rows.append(Block.text(row_text, Style(), width=width))
        else:
            # Expand this branch
            if node_renderer is not None:
                content_block = node_renderer(key, value, depth)
                row_cells = list(
                    Block.text(branch_prefix, Style(), width=display_width(branch_prefix)).row(0)
                )
                for cell in content_block.row(0)[:content_width]:
                    row_cells.append(cell)
                # Pad to full width
                while len(row_cells) < width:
                    row_cells.append(EMPTY_CELL)
                rows.append(Block([row_cells], width))
            else:
                row_text = branch_prefix + _truncate_ellipsis(key, content_width)
                rows.append(Block.text(row_text, Style(), width=width))

            _tree_render_children_themed(
                grandchildren,
                remaining_zoom - 1,
                width,
                prefix + continuation,
                rows,
                depth + 1,
                tree_branch,
                tree_last,
                tree_indent,
                tree_space,
                node_renderer,
            )


def _tree_truncate(text: str, width: int) -> Block:
    """Create a single-row block, truncating if needed."""
    if display_width(text) > width:
        text = truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
    return Block.text(text, Style(), width=width)


def _truncate_ellipsis(text: str, width: int) -> str:
    """Truncate text with ellipsis if it exceeds width."""
    return truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
