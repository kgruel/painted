"""Shared helpers for tests.

These are intentionally lightweight and dependency-free (beyond painted itself),
and are used across unit + golden tests to avoid copy-pasting utilities.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

from painted import Block, Cell, CliContext, Fidelity, Style, Zoom
from painted.cli import OutputMode
from painted.core.writer import print_block

REPO_ROOT = Path(__file__).resolve().parents[1]
PAINTED_SRC = REPO_ROOT / "src"


def static_ctx(
    zoom: Zoom, *, visible: tuple[str, ...] = (), lines: int = 0, chars: int = 0
) -> CliContext:
    """Build a deterministic CliContext for golden/snapshot testing.

    ``visible`` sets fidelity facets explicitly — this harness builds the
    spec directly, so tag implications are the caller's to state (use
    ``painted.cli.implied_visible`` to mirror what the CLI would compile).
    ``lines``/``chars`` set the density budget (the ``--max-lines``/``--max-chars``
    ceilings); 0 leaves that dimension unlimited.
    """
    return CliContext(
        fidelity=Fidelity(depth=int(zoom), visible=frozenset(visible), lines=lines, chars=chars),
        mode=OutputMode.STATIC,
        use_ansi=False,
        is_tty=False,
        width=80,
        height=24,
    )


def block_to_text(block: Block, *, use_ansi: bool = False) -> str:
    """Render a Block into plain text (or ANSI) via painted.writer.print_block()."""
    buf = io.StringIO()
    print_block(block, buf, use_ansi=use_ansi)
    return buf.getvalue()


def row_text(block: Block, row_idx: int) -> str:
    """Return the characters for a single block row."""
    return "".join(c.char for c in block.row(row_idx))


def text_block(lines: list[str], style: Style | None = None, *, ref: str | None = None) -> Block:
    """Build a Block from text lines, padding rows to uniform width."""
    style = style or Style()
    width = max((len(ln) for ln in lines), default=0)
    rows: list[list[Cell]] = []
    for line in lines:
        row = [Cell(ch, style) for ch in line]
        row += [Cell(" ", style)] * (width - len(line))
        rows.append(row)
    return Block(rows, width, ref=ref)


def capture_content_blocks(argv, *, render, **run_cli_kwargs):
    """Run run_cli, capturing every content Block the renderer returns.

    The cross-host harness (RENDER_MODEL.md law 1, Milestone 1): every
    delivery path — static print_block, in-place live, plain streaming —
    receives its content Block from the declared render fn, so wrapping that
    fn observes the Block *before* delivery dress (live_meter) and
    serialization. This is deliberately test-side plumbing: Milestone 1 adds
    guards without changing public APIs.

    Returns ``(exit_code, blocks)`` — one Block per render call, in order.
    """
    from painted.cli import run_cli

    captured: list[Block] = []

    def recording_render(ctx: CliContext, data):
        block = render(ctx, data)
        captured.append(block)
        return block

    exit_code = run_cli(list(argv), render=recording_render, **run_cli_kwargs)
    return exit_code, captured


def assert_blocks_equal(a: Block, b: Block) -> None:
    """Assert two Blocks are cell-for-cell identical (chars, styles, refs)."""
    assert (a.width, a.height) == (b.width, b.height), (
        f"block geometry differs: {a.width}x{a.height} vs {b.width}x{b.height}"
    )
    for y in range(a.height):
        assert a.row(y) == b.row(y), f"row {y} differs:\n  {row_text(a, y)!r}\n  {row_text(b, y)!r}"


# =============================================================================
# AST import scanning (shared by the architecture and render-model law gates)
# =============================================================================


def _module_name_for_file(src_root: Path, py_file: Path) -> str:
    rel = py_file.relative_to(src_root).with_suffix("")
    return ".".join(rel.parts)


def _resolve_relative_module(current_pkg: str, *, level: int, module: str | None) -> str:
    """Resolve an ast.ImportFrom into an absolute module path.

    Examples (current_pkg="painted.views"):
      - from ._components import x      => painted.views._components
      - from ..app import Surface       => painted.app
    """
    if level <= 0:
        return module or ""

    pkg_parts = current_pkg.split(".") if current_pkg else []
    up = level - 1
    base_parts = pkg_parts[: max(0, len(pkg_parts) - up)]
    base = ".".join(base_parts)
    if not module:
        return base
    return f"{base}.{module}" if base else module


def _iter_imported_modules(src_root: Path, py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    current_mod = _module_name_for_file(src_root, py_file)
    current_pkg = current_mod.rsplit(".", 1)[0] if "." in current_mod else current_mod

    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative_module(current_pkg, level=node.level, module=node.module)
            if node.module is not None:
                imported.add(base)
            else:
                # from .. import foo, bar
                for alias in node.names:
                    imported.add(f"{base}.{alias.name}" if base else alias.name)

    return imported


def _assert_no_imports(py_file: Path, forbidden_prefixes: set[str]) -> None:
    imported = _iter_imported_modules(PAINTED_SRC, py_file)

    forbidden = []
    for mod in sorted(imported):
        if any(mod == p or mod.startswith(f"{p}.") for p in forbidden_prefixes):
            forbidden.append(mod)

    assert not forbidden, f"{py_file} imports forbidden modules: {forbidden}"
