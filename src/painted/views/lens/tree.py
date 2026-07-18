"""Tree lens: hierarchical data with branch characters."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity

from ...core._row_ops import take_row_prefix
from ...core._text_width import display_width, truncate_ellipsis, truncate
from ...core.block import Block
from ...core.cell import EMPTY_CELL, Cell, Style
from ...core.compose import join_vertical
from ...core.errors import ContractError

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
            Branch characters are added automatically; return content only. The
            returned Block must be exactly one row (height 1) — a node slot is an
            offer of height 1; a taller Block raises ContractError (it is not
            silently cropped to its first row).
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
        # No branch prefix at the root; the callback owns the full width. Same
        # content-aware fitting as every child — never substitute the label.
        rows.append(_node_row(node_renderer, label, data, 0, "", width, width))
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
    # Nodes dropped because indentation exhausts the width budget owe evidence
    # (RENDER_MODEL law 6): a muted ``… N nodes hidden`` line. Dropped siblings
    # are accumulated into the *current contiguous run* and flushed before the
    # next rendered sibling (and at parent exit), so the evidence sits where the
    # dropped group was — correct even when an unequal-width IconSet lets some
    # siblings drop while a later one fits (no equal-prefix-width assumption).
    skipped = 0  # nodes in the pending contiguous run of width-dropped siblings

    def flush_dropped() -> None:
        nonlocal skipped
        if skipped:
            rows.append(_subtree_drop_evidence(skipped, width))
            skipped = 0

    for i, (key, value) in enumerate(children):
        is_last = i == len(children) - 1
        branch = tree_last if is_last else tree_branch
        continuation = tree_space if is_last else tree_indent

        _, grandchildren = _tree_extract(value)

        # Calculate available width for content
        branch_prefix = prefix + branch
        content_width = width - display_width(branch_prefix)

        if content_width <= 0:
            # This node and every descendant the current zoom would render are
            # dropped; count them (no recursion below, so a skip nested in a
            # skipped subtree is folded into this one count, never re-emitted).
            skipped += _count_visible_nodes([(key, value)], remaining_zoom)
            continue

        # A sibling renders — close out any pending dropped run at its position.
        flush_dropped()

        if remaining_zoom <= 0 or grandchildren is None:
            # Leaf or zoom exhausted
            if node_renderer is not None:
                rows.append(
                    _node_row(node_renderer, key, value, depth, branch_prefix, content_width, width)
                )
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
                rows.append(
                    _node_row(node_renderer, key, value, depth, branch_prefix, content_width, width)
                )
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

    flush_dropped()  # trailing run of dropped siblings at parent exit


def _render_node(node_renderer: NodeRenderer, key: str, value: Any, depth: int) -> Block:
    """Call ``node_renderer`` and enforce the one-row node-slot contract.

    A tree node slot is an offer of height 1 — the host-rung exactness precedent
    (a frame offer is honored exactly, never cropped or padded into compliance)
    carried to the lens seam. A returned Block of any other height is a contract
    violation raised loudly (ERRORS_DESIGN — ContractError, contract-time), never
    a silent crop to its first row.
    """
    block = node_renderer(key, value, depth)
    if block.height != 1:
        raise ContractError(
            f"node_renderer returned a Block of height {block.height}; a tree node "
            "slot is an offer of height 1 (return exactly one row)"
        )
    return block


def _fit_callback_row(content: Block, budget: int) -> tuple[list[Cell], list[str | None]]:
    """Fit a callback's one-row content to ``budget`` columns (law 6).

    The callback owns its cells — we render them, never substitute the label —
    and its refs travel with them. Returns ``(cells, refs)`` of display width
    ``<= budget`` (the parallel ref lane, one entry per cell); the caller lays
    the row down with the branch prefix and padding.

    A callback commonly returns a width-padded row, so a cut that discards only
    *semantically neutral* blanks is no loss and marks nothing. "Neutral" is
    conservative: a cell equal to ``EMPTY_CELL`` carrying no ref. Background /
    underline / reverse styling on a blank is visible on the HTML and buffer
    surfaces (even where the ANSI writer trims trailing spaces), and a ref on a
    blank is a denotation — both are content, and cutting them owes the ambient
    ellipsis, with the physical-space waiver when content + marker cannot both
    fit (``budget`` no wider than the marker).
    """
    row = content.row(0)
    # The parallel ref lane, one entry per cell — cell_ref folds a uniform
    # block ref and a per-cell grid into the same read. Kept cells slice their
    # refs from it (a prefix stays a prefix), so refs travel with their cells.
    refs = [content.cell_ref(x, 0) for x in range(content.width)]
    if content.width <= budget:
        return list(row), refs  # fits — nothing discarded

    kept, _, _ = take_row_prefix(row, budget)
    if all(cell == EMPTY_CELL for cell in row[len(kept) :]) and all(
        r is None for r in refs[len(kept) :]
    ):
        return kept, refs[: len(kept)]  # only neutral padding discarded — a mark would be false

    from ...icon_set import current_icons

    ellipsis = current_icons().ellipsis
    ell_w = display_width(ellipsis)
    if budget <= ell_w:
        return kept, refs[: len(kept)]  # no room for content + marker — the plain cut stands
    marked, _, _ = take_row_prefix(row, budget - ell_w)
    marked_refs = list(refs[: len(marked)])
    ellipsis_cells = list(Block.text(ellipsis, Style()).row(0))
    marked.extend(ellipsis_cells)
    marked_refs.extend([None] * len(ellipsis_cells))  # the mark denotes nothing
    return marked, marked_refs


def _node_row(
    node_renderer: NodeRenderer,
    key: str,
    value: Any,
    depth: int,
    branch_prefix: str,
    content_width: int,
    width: int,
) -> Block:
    """Assemble one node row: branch prefix + fitted callback content, padded to
    ``width``. Shared by the root (empty prefix, full width) and every child, so
    the one-row contract and content-aware fitting apply through one path. The
    fitted content's refs are carried into the row; branch glyphs, the ellipsis
    mark, and padding carry none (the ref lane stays ``None`` when nothing does).
    """
    content = _render_node(node_renderer, key, value, depth)
    branch_cells = list(
        Block.text(branch_prefix, Style(), width=display_width(branch_prefix)).row(0)
    )
    fitted_cells, fitted_refs = _fit_callback_row(content, content_width)
    row_cells = branch_cells + fitted_cells
    row_refs: list[str | None] = [None] * len(branch_cells) + fitted_refs
    while len(row_cells) < width:
        row_cells.append(EMPTY_CELL)
        row_refs.append(None)
    refs = [row_refs] if any(r is not None for r in row_refs) else None
    return Block([row_cells], width, refs=refs)


def _count_visible_nodes(children: list[tuple[str, Any]], remaining_zoom: int) -> int:
    """Count the nodes the current zoom/expansion would render for ``children``.

    Mirrors the render exactly: a node is one row, and its children render only
    while ``remaining_zoom > 0`` — width-agnostic, because this is the count owed
    when *width* (not zoom) drops a subtree, so it reflects what the zoom would
    have shown rather than the raw subtree. A skip nested inside a skipped
    subtree is folded into this one count, never re-emitted.

    A cyclic node is redrawn by the renderer at every level until the zoom budget
    runs out, so the count must too. The walk is iterative by zoom level, keyed
    by container identity with a multiplicity (a big int): identity keeps a cycle
    frontier bounded to its distinct containers, while the multiplicity preserves
    every occurrence the renderer would draw — a finite, exact count with no
    unbounded recursion. Repro: a self-referential value dropped at
    ``remaining_zoom=4`` owes 5 (the node redrawn at zoom levels 4,3,2,1,0).
    """
    if remaining_zoom < 0 or not children:
        return 0
    total = 0
    # id(value) -> (value, occurrences) at the current zoom level.
    frontier: dict[int, tuple[Any, int]] = {}
    for _key, value in children:
        v, m = frontier.get(id(value), (value, 0))
        frontier[id(value)] = (v, m + 1)
    rz = remaining_zoom
    while frontier:
        total += sum(mult for _v, mult in frontier.values())
        if rz <= 0:
            break
        nxt: dict[int, tuple[Any, int]] = {}
        for value, mult in frontier.values():
            _, grandchildren = _tree_extract(value)
            if grandchildren is None:
                continue
            for _ck, child in grandchildren:
                v, m = nxt.get(id(child), (child, 0))
                nxt[id(child)] = (v, m + mult)
        frontier = nxt
        rz -= 1
    return total


def _subtree_drop_evidence(count: int, width: int) -> Block:
    """A muted ``… N nodes hidden`` line for a width-dropped sibling group.

    Reuses the shared law-6 evidence-row vocabulary (``views._frame.evidence_row``)
    through its caller-wording seam — the same ambient ellipsis + ``muted`` role
    every other omission mark degrades through, width-exact — rather than
    inventing a second evidence idiom in the lens.
    """
    from .._frame import evidence_row

    noun = "node" if count == 1 else "nodes"
    return evidence_row(0, 0, width, label=f"{count} {noun} hidden")


def _tree_truncate(text: str, width: int) -> Block:
    """Create a single-row block, truncating if needed."""
    if display_width(text) > width:
        text = truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
    return Block.text(text, Style(), width=width)


def _truncate_ellipsis(text: str, width: int) -> str:
    """Truncate text with ellipsis if it exceeds width."""
    return truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
