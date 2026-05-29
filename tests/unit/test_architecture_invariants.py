from __future__ import annotations

import ast
import sys
from dataclasses import is_dataclass
from pathlib import Path

import pytest


def _painted_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "painted"


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
    painted_src = Path(__file__).resolve().parents[2] / "src"
    imported = _iter_imported_modules(painted_src, py_file)

    forbidden = []
    for mod in sorted(imported):
        if any(mod == p or mod.startswith(f"{p}.") for p in forbidden_prefixes):
            forbidden.append(mod)

    assert not forbidden, f"{py_file} imports forbidden modules: {forbidden}"


def test_block_defensively_freezes_rows() -> None:
    from painted.core.block import Block
    from painted.core.cell import Cell, Style

    style = Style()
    rows = [[Cell("a", style), Cell("b", style)]]

    block = Block(rows, width=2)

    # Mutate the caller-owned list-of-lists after construction: must not affect Block.
    rows[0][0] = Cell("x", style)
    rows.append([Cell("y", style), Cell("z", style)])

    assert block.height == 1
    assert [c.char for c in block.row(0)] == ["a", "b"]

    assert isinstance(block._rows, tuple)
    assert isinstance(block._rows[0], tuple)
    assert isinstance(block.row(0), tuple)

    with pytest.raises(TypeError):
        block.row(0)[0] = Cell("q", style)  # type: ignore[misc]

    with pytest.raises(AttributeError):
        block.width = 3  # type: ignore[misc]


def _dataclass_frozen_from_decorators(class_def: ast.ClassDef) -> bool | None:
    for decorator in class_def.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
            return False
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "dataclass"
        ):
            for kw in decorator.keywords:
                if (
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    return True
            return False
    return None


def test_state_dataclasses_declared_frozen() -> None:
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"

    must_be_frozen = {
        "Region",
        "Cell",
        "Style",
        "Span",
        "Line",
        "BorderChars",
        "Focus",
        "Search",
        "Lens",
        "Cursor",
        "Viewport",
        "CliContext",
        "Fidelity",
        "Palette",
        "IconSet",
        "Theme",
    }

    for py_file in painted_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            if node.name.endswith("State") or node.name in must_be_frozen:
                frozen = _dataclass_frozen_from_decorators(node)
                assert frozen is True, (
                    f"{py_file}: class {node.name} must be @dataclass(frozen=True)"
                )


def test_block_rows_private_not_accessed_outside_block() -> None:
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    block_files = {painted_root / "core" / "block.py"}

    for py_file in painted_root.rglob("*.py"):
        if py_file in block_files:
            continue
        assert "._rows" not in py_file.read_text(encoding="utf-8"), (
            f"{py_file} accesses Block._rows directly"
        )


def test_runtime_state_dataclasses_are_frozen() -> None:
    from painted.views.components.data_explorer import DataExplorerState
    from painted.views.components.list_view import ListState
    from painted.views.components.progress import ProgressState
    from painted.views.components.spinner import SpinnerState
    from painted.views.components.table import TableState
    from painted.views.components.text_input import TextInputState
    from painted.core.borders import BorderChars
    from painted.core.cell import Cell, Style
    from painted.cursor import Cursor
    from painted.cli import CliContext
    from painted.core.fidelity import Fidelity
    from painted.focus import Focus
    from painted.icon_set import IconSet
    from painted.palette import Palette
    from painted.theme import Theme
    from painted.tui import Region
    from painted.search import Search
    from painted.core.span import Line, Span
    from painted.viewport import Viewport

    for cls in (
        Region,
        Cell,
        Style,
        Span,
        Line,
        BorderChars,
        Focus,
        Search,
        Cursor,
        Viewport,
        CliContext,
        Fidelity,
        Palette,
        IconSet,
        Theme,
        SpinnerState,
        ProgressState,
        ListState,
        TextInputState,
        TableState,
        DataExplorerState,
    ):
        assert is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


# =============================================================================
# Layer boundary enforcement
#
# Allowed dependency direction: core ← views ← cli ← tui
# Each layer may only import from layers to its left (and root shared modules).
#
# Known violation: views/record.py imports Zoom from cli.types.
# Zoom is shared rendering vocabulary that should move out of cli/ — tracked
# in follow-up.md item 3. The allowlist below makes this explicit.
# =============================================================================

_KNOWN_VIOLATIONS: set[tuple[str, str]] = set()


def _layer_of(mod: str) -> str:
    """Classify a painted module into its architectural layer."""
    for layer in ("core", "views", "cli", "tui"):
        if mod == f"painted.{layer}" or mod.startswith(f"painted.{layer}."):
            return layer
    return "root"


def _layer_files(painted_root: Path, layer: str) -> list[Path]:
    """Get all .py files in a layer directory."""
    return sorted((painted_root / layer).rglob("*.py"))


def _check_layer_boundary(
    painted_root: Path,
    src_root: Path,
    layer: str,
    forbidden_layers: set[str],
) -> list[str]:
    """Check that a layer doesn't import from forbidden layers."""
    violations = []
    for py_file in _layer_files(painted_root, layer):
        imported = _iter_imported_modules(src_root, py_file)
        for mod in sorted(imported):
            target_layer = _layer_of(mod)
            if target_layer in forbidden_layers:
                key = (layer, target_layer)
                if key in _KNOWN_VIOLATIONS:
                    continue
                violations.append(
                    f"{py_file.relative_to(src_root)} imports {mod} ({layer} → {target_layer})"
                )
    return violations


def test_core_is_self_contained() -> None:
    """core/ must not import from views/, cli/, or tui/."""
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent
    violations = _check_layer_boundary(painted_root, src_root, "core", {"views", "cli", "tui"})
    assert not violations, "core/ imports higher layers:\n" + "\n".join(violations)


def test_views_do_not_import_cli_or_tui() -> None:
    """views/ may import core/ and root, but not cli/ or tui/."""
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent
    violations = _check_layer_boundary(painted_root, src_root, "views", {"cli", "tui"})
    assert not violations, "views/ imports framework layers:\n" + "\n".join(violations)


def test_cli_does_not_import_tui() -> None:
    """cli/ may import core/ and root, but not tui/ or views/."""
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent
    violations = _check_layer_boundary(painted_root, src_root, "cli", {"tui", "views"})
    assert not violations, "cli/ imports higher layers:\n" + "\n".join(violations)


def test_tui_does_not_import_views_or_cli() -> None:
    """tui/ may import core/ and root, but not views/ or cli/."""
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent
    violations = _check_layer_boundary(painted_root, src_root, "tui", {"views", "cli"})
    assert not violations, "tui/ imports sibling layers:\n" + "\n".join(violations)


def test_public_modules_do_not_import_private_symbols_from_siblings() -> None:
    """Public modules may use internal modules, but not private sibling symbols.

    Exception: `painted._color` is the shared internal for color conversions.
    """
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent

    def imported_private_symbols(py_file: Path) -> list[str]:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        current_mod = _module_name_for_file(src_root, py_file)
        current_pkg = current_mod.rsplit(".", 1)[0] if "." in current_mod else current_mod

        bad: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            base = _resolve_relative_module(current_pkg, level=node.level, module=node.module)
            for alias in node.names:
                if alias.name.startswith("_") and base != "painted._color":
                    bad.append(f"{base}:{alias.name}")
        return bad

    violations: list[str] = []
    for py_file in sorted(painted_root.rglob("*.py")):
        if py_file.name.startswith("_") and py_file.name != "__init__.py":
            continue
        # Skip core-internal imports (core modules may use each other's privates)
        if (painted_root / "core") in py_file.parents:
            continue
        for item in imported_private_symbols(py_file):
            violations.append(f"{py_file.relative_to(src_root)} imports {item}")

    assert not violations, "Public modules import private sibling symbols:\n" + "\n".join(
        violations
    )


# =============================================================================
# Invariant audit remediation guards (docs/plans/2026-05-29-invariant-audit-remediation.md)
#
# These mechanize three documented invariants the checks above did not cover.
# Each is the generalized form: it catches the whole class, with an explicit
# allowlist for deliberate exceptions, so a future regression fails loudly.
# =============================================================================


# --- Test A: zero runtime dependencies beyond the vetted exception ----------
#
# CLAUDE.md: "Zero runtime dependencies beyond wcwidth (the single vetted
# exception)." wcwidth is the only third-party package painted may import at
# runtime; everything else must be stdlib or painted itself. Type-only imports
# under `if TYPE_CHECKING:` are exempt (they never execute at runtime).
_ALLOWED_RUNTIME_DEPS = {"wcwidth"}


def _is_type_checking_test(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Name):
        return expr.id == "TYPE_CHECKING"
    if isinstance(expr, ast.Attribute):
        return expr.attr == "TYPE_CHECKING"
    return False


def _iter_runtime_imports(node: ast.AST):
    """Yield Import/ImportFrom nodes that execute at runtime.

    Descends into functions/classes (lazy imports count) but skips the body of
    `if TYPE_CHECKING:` blocks, while still visiting their runtime else-branch.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.If) and _is_type_checking_test(child.test):
            for sub in child.orelse:
                yield from _iter_runtime_imports(sub)
            continue
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child
        yield from _iter_runtime_imports(child)


def _runtime_top_packages(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    packages: set[str] = set()
    for node in _iter_runtime_imports(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                packages.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (level > 0) are always painted-internal.
            if node.level == 0 and node.module:
                packages.add(node.module.split(".")[0])
    return packages


def test_runtime_imports_are_stdlib_or_allowlisted() -> None:
    painted_root = _painted_root()
    violations: list[str] = []
    for py_file in sorted(painted_root.rglob("*.py")):
        for pkg in sorted(_runtime_top_packages(py_file)):
            if pkg in sys.stdlib_module_names:
                continue
            if pkg == "painted" or pkg in _ALLOWED_RUNTIME_DEPS:
                continue
            violations.append(f"{py_file.relative_to(painted_root.parent)} imports {pkg}")

    assert not violations, (
        "Non-stdlib runtime imports outside the allowlist "
        f"{sorted(_ALLOWED_RUNTIME_DEPS)}:\n" + "\n".join(violations)
    )


# --- Test B: dataclasses frozen unless explicitly allowlisted as mutable -----
#
# Inverts the blind spot in test_state_dataclasses_declared_frozen (which only
# inspects names ending in "State" or a hardcoded set). Here EVERY dataclass is
# frozen-or-fail; only deliberately-mutable types are named.
_MUTABLE_DATACLASSES = {
    "FrameRecord",  # _timer.py — per-frame timing accumulator, mutated in place
    "CliRunner",  # cli/runner.py — runtime parser cache + callable handler holder
}


def test_dataclasses_frozen_unless_allowlisted() -> None:
    painted_root = _painted_root()
    violations: list[str] = []
    for py_file in painted_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            frozen = _dataclass_frozen_from_decorators(node)
            # None => not a dataclass; True => frozen; False => mutable dataclass.
            if frozen is False and node.name not in _MUTABLE_DATACLASSES:
                violations.append(
                    f"{py_file.relative_to(painted_root.parent)}: {node.name} "
                    "is a dataclass but not frozen (add frozen=True, or allowlist "
                    "if intentionally mutable)"
                )

    assert not violations, "Non-frozen dataclasses outside the allowlist:\n" + "\n".join(violations)


# --- Test C: frozen dataclasses must guard mutable-collection fields ---------
#
# A frozen dataclass storing a caller-supplied list/dict/set is still mutable
# through that reference (cf. test_block_defensively_freezes_rows). Such a field
# must be coerced to an immutable form in __post_init__, OR be allowlisted when
# true immutability is impractical. Fields declared init=False are internal
# (caches) — not part of the constructor contract — so they're exempt.
_MUTABLE_COLLECTION_HEADS = {
    "list",
    "dict",
    "set",
    "List",
    "Dict",
    "Set",
    "Sequence",
    "Mapping",
    "MutableSequence",
    "MutableMapping",
}
_FROZEN_FIELD_ALLOWLIST = {
    # nested arbitrary structure produced internally by profile(); deep-freeze
    # is impractical and a shallow proxy would fake immutability.
    ("ProfileResult", "flame_dict"),
}


def _annotation_container_heads(ann: ast.expr) -> list[str]:
    """Top-level container type names in an annotation (descends unions only)."""
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        return _annotation_container_heads(ann.left) + _annotation_container_heads(ann.right)
    if isinstance(ann, ast.Subscript):
        head = ann.value
        if isinstance(head, ast.Name):
            return [head.id]
        if isinstance(head, ast.Attribute):
            return [head.attr]
    if isinstance(ann, ast.Name):
        return [ann.id]
    if isinstance(ann, ast.Attribute):
        return [ann.attr]
    return []


def _field_is_init_false(value: ast.expr | None) -> bool:
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    is_field = (isinstance(func, ast.Name) and func.id == "field") or (
        isinstance(func, ast.Attribute) and func.attr == "field"
    )
    if not is_field:
        return False
    return any(
        kw.arg == "init" and isinstance(kw.value, ast.Constant) and kw.value.value is False
        for kw in value.keywords
    )


def test_frozen_dataclasses_guard_mutable_collection_fields() -> None:
    painted_root = _painted_root()
    violations: list[str] = []
    for py_file in painted_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if _dataclass_frozen_from_decorators(node) is not True:
                continue
            # __post_init__ is the static proxy for "coerces its inputs".
            has_post_init = any(
                isinstance(m, ast.FunctionDef) and m.name == "__post_init__" for m in node.body
            )
            if has_post_init:
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                if _field_is_init_false(stmt.value):
                    continue
                field_name = stmt.target.id
                if (node.name, field_name) in _FROZEN_FIELD_ALLOWLIST:
                    continue
                heads = _annotation_container_heads(stmt.annotation)
                if any(h in _MUTABLE_COLLECTION_HEADS for h in heads):
                    violations.append(
                        f"{py_file.relative_to(painted_root.parent)}: "
                        f"{node.name}.{field_name} is a mutable-collection field on a "
                        "frozen dataclass without __post_init__ coercion (coerce to a "
                        "tuple/immutable form, or allowlist)"
                    )

    assert not violations, (
        "Unguarded mutable-collection fields on frozen dataclasses:\n" + "\n".join(violations)
    )


def test_frozen_collection_fields_defensively_copied() -> None:
    """Runtime companion to Test C: caller-owned sequences are coerced to tuples.

    Mirrors test_block_defensively_freezes_rows for the two types fixed in the
    invariant-audit remediation.
    """
    from painted.cli import AppCommand
    from painted.icon_set import IconSet
    from painted.cli.help import HelpArg

    args = [HelpArg(name="--since")]
    cmd = AppCommand("log", "show log", lambda argv: 0, help_args=args)
    assert isinstance(cmd.help_args, tuple)
    args.append(HelpArg(name="--until"))
    assert len(cmd.help_args) == 1  # caller mutation does not leak in

    frames = ["a", "b", "c"]
    icons = IconSet(spinner=frames)
    assert isinstance(icons.spinner, tuple)
    frames.append("d")
    assert len(icons.spinner) == 3
