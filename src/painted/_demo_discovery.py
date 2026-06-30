"""Demo discovery — the render-free half of the demos CLI.

Split out of ``_demo_cli.py`` so the completion path can list demo names without
dragging the renderer onto the no-renderer-on-TAB path: ``_demo_cli`` imports
``painted`` (Block, Style, …) to *render* the demo list, but discovery itself is
pure ``ast``/``pathlib`` — finding files and reading their docstrings. The
``demos`` completer imports only this module, so ``painted demos <TAB>`` stays
light. ``_demo_cli`` re-exports these names, so existing importers are unaffected.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# DemoEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoEntry:
    name: str  # "fidelity"
    group: str  # "patterns"
    path: Path  # absolute path to .py file
    description: str  # first line of docstring
    invocations: tuple[str, ...] = ()  # "uv run ..." lines from docstring
    has_main: bool = True  # False for primitives/apps


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_CACHE: list[DemoEntry] | None = None

_GROUPS = ("primitives", "patterns", "apps", "examples", "showcase")


def _find_demos_root() -> Path | None:
    """Locate the demos/ directory across dev checkout and installed wheel."""
    here = Path(__file__).resolve()
    candidates = (
        # Dev checkout: src/painted/_demo_discovery.py -> src/painted -> src -> project root
        here.parent.parent.parent / "demos",
        # Installed wheel: demos/ is force-included under the package itself
        # (site-packages/painted/demos), so it sits beside this module.
        here.parent / "demos",
        # Last resort: running from a project root that has a demos/ tree
        Path.cwd() / "demos",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _parse_demo(path: Path, group: str) -> DemoEntry | None:
    """Extract demo metadata via ast without executing the file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return None

    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.split("\n")[0].strip() if docstring else path.stem

    # Extract invocation lines: lines starting with whitespace + "uv run"
    invocations: list[str] = []
    for line in docstring.split("\n"):
        stripped = line.strip()
        if stripped.startswith("uv run"):
            invocations.append(stripped)

    # has_main: check for top-level def main or async def main
    has_main = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        for node in ast.iter_child_nodes(tree)
    )

    return DemoEntry(
        name=path.stem,
        group=group,
        path=path.resolve(),
        description=first_line,
        invocations=tuple(invocations),
        has_main=has_main,
    )


def discover_demos() -> list[DemoEntry]:
    """Find all demos, sorted by group then name. Cached."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    root = _find_demos_root()
    if root is None:
        _CACHE = []
        return _CACHE

    entries: list[DemoEntry] = []
    for group in _GROUPS:
        group_dir = root / group
        if not group_dir.is_dir():
            continue
        for path in sorted(group_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            entry = _parse_demo(path, group)
            if entry is not None:
                entries.append(entry)

    # Also discover tour.py at demos root
    tour_path = root / "tour.py"
    if tour_path.exists():
        entry = _parse_demo(tour_path, "")
        if entry is not None:
            entries.append(entry)

    _CACHE = entries
    return _CACHE
