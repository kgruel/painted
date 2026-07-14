from __future__ import annotations

import ast
import sys
from dataclasses import is_dataclass
from pathlib import Path

import pytest

from tests.helpers import (
    _assert_no_imports,
    _iter_imported_modules,
    _module_name_for_file,
    _resolve_relative_module,
)


def _painted_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "painted"


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


def test_vocabulary_does_not_import_cli_or_argparse() -> None:
    """Honesty rule 4 (structural): vocabularies generate no CLI flags.

    A mark classifies data; it is not user grammar. The rule is pinned here so
    ``vocabulary.py`` can never grow a ``cli``/``argparse`` dependency — the
    kebab-name regex is a deliberate local duplicate of ``cli.types``' precisely
    so the two stay decoupled (see docs/VOCABULARIES_DESIGN.md §1).
    """
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    _assert_no_imports(painted_root / "vocabulary.py", {"painted.cli", "argparse"})


def test_refs_does_not_import_cli_or_argparse() -> None:
    """Ref schemes generate no CLI flags (REFS_DESIGN §4, mirroring vocabularies
    rule 4). ``refs.py`` classifies a denotation channel; it is not user grammar,
    so it must never grow a ``cli``/``argparse`` dependency — pinned structurally
    here, the same way ``vocabulary.py`` is pinned above.
    """
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    _assert_no_imports(painted_root / "refs.py", {"painted.cli", "argparse"})


def test_public_names_do_not_shadow_submodules() -> None:
    """No package may re-export a public name that collides with one of its own
    submodule filenames (review #1 — closes the class, not just the instance).

    A collision is a latent import-order trap: ``from pkg import name`` consults
    ``pkg.__dict__`` first, so once *anything* imports the like-named submodule,
    the binding flips to the module and permanently shadows the re-exported
    function — e.g. ``from painted.views import profile`` returned the
    ``profile.py`` module instead of the ``profile()`` context manager after any
    ``import painted.views.profile``. The structural fix is to keep the public
    surface and the file namespace disjoint: backing submodules are private
    (``_name.py``). This guard fails the moment a future name re-collides.
    """
    import importlib
    import pkgutil

    import painted

    collisions: dict[str, list[str]] = {}

    def _check(pkg) -> None:
        path = getattr(pkg, "__path__", None)
        if path is None:
            return  # a module, not a package — no submodules to shadow
        public = set(getattr(pkg, "__all__", ()))
        submodules = {m.name for m in pkgutil.iter_modules(path)}
        shadowed = sorted(public & submodules)
        if shadowed:
            collisions[pkg.__name__] = shadowed

    _check(painted)
    for info in pkgutil.walk_packages(painted.__path__, prefix="painted."):
        if not info.ispkg:
            continue
        _check(importlib.import_module(info.name))

    assert not collisions, (
        "public __all__ names collide with submodule files (latent import-order "
        f"shadow): {collisions}. Rename each backing submodule to _name.py so the "
        "public surface and file namespace stay disjoint (review #1)."
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
    from painted.views import (
        DataExplorerState,
        ListState,
        ProgressState,
        SpinnerState,
        TableState,
        TextInputState,
    )
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
    allowed_seams: frozenset[tuple[str, str]] = frozenset(),
) -> list[str]:
    """Check that a layer doesn't import from forbidden layers.

    ``allowed_seams`` carves narrow, file-scoped exceptions: each ``(relative
    file path, imported module)`` pair is a documented crossing that the guard
    permits. Anything else crossing the boundary still fails — the exception is
    a seam, not a blanket relaxation.
    """
    violations = []
    for py_file in _layer_files(painted_root, layer):
        rel = str(py_file.relative_to(src_root))
        imported = _iter_imported_modules(src_root, py_file)
        for mod in sorted(imported):
            target_layer = _layer_of(mod)
            if target_layer in forbidden_layers:
                key = (layer, target_layer)
                if key in _KNOWN_VIOLATIONS:
                    continue
                if (rel, mod) in allowed_seams:
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


# The live-delivery seams: the two-tier live-delivery contract
# (docs/LIVE_DELIVERY_DESIGN.md) makes the CLI framework the orchestrator of
# BOTH live tiers — ephemeral (InPlaceRenderer, in root) and sustained
# (Surface, in tui). StreamSurface is the cli-private adapter that hosts a
# fetch_stream on an alt screen, so it must subclass tui's Surface; and both
# tiers dress their frames with the delivery-cost gauge, whose renderer is
# views' public cost_meter — re-implementing it in cli would undo the
# component graduation. These are the ONLY sanctioned crossings; every other
# cli file stays tui- and views-free (both imports are lazy where it matters,
# so `import painted` never pays for either).
#
# Seams are framework→library only — cli reaching down into views/tui. The
# reverse direction is never a seam: a library module needing the framework
# means the code is in the wrong layer, not that the boundary needs a hole.
# Each seam is file-scoped to one (file, target) pair, serves a ratified
# contract, and exists only because dissolving it (duplicating the code in
# cli, or demoting it below the boundary) was honestly worse.
#
# TRIPWIRE (ratified 2026-06-10): this set never grows past two. Both
# entries are delivery concerns — cli orchestrating how frames reach the
# terminal — so a third legitimate seam is evidence that a delivery layer
# exists and wants a name. The response is to extract it (move the seam
# files below the boundary, shrinking this set back toward zero), never to
# add a third entry. The allowlist is a pressure gauge, not a budget.
_CLI_SEAMS = frozenset(
    {
        ("painted/cli/stream_surface.py", "painted.tui.surface"),
        ("painted/cli/live_meter.py", "painted.views"),
    }
)


def test_cli_does_not_import_tui() -> None:
    """cli/ may import core/ and root, but not tui/ or views/.

    Exception: the documented live-delivery seams (see _CLI_SEAMS).
    """
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent
    violations = _check_layer_boundary(
        painted_root, src_root, "cli", {"tui", "views"}, allowed_seams=_CLI_SEAMS
    )
    assert not violations, "cli/ imports higher layers:\n" + "\n".join(violations)


def test_tui_does_not_import_views_or_cli() -> None:
    """tui/ may import core/ and root, but not views/ or cli/."""
    painted_root = Path(__file__).resolve().parents[2] / "src" / "painted"
    src_root = painted_root.parent
    violations = _check_layer_boundary(painted_root, src_root, "tui", {"views", "cli"})
    assert not violations, "tui/ imports sibling layers:\n" + "\n".join(violations)


def test_public_modules_do_not_import_private_symbols_from_siblings() -> None:
    """Public modules may use internal modules, but not private sibling symbols.

    Exceptions (deliberate intra-package sharing, not accidental coupling):

    * ``painted._color`` — shared internal for color conversions; used across
      multiple rendering modules in the same package.
    * ``painted.cli.complete`` — cli-internal shared utilities (``_tolerant_split``,
      ``_walk_preceding``) used by both ``complete.py`` (canonical home) and
      ``completion_shell.py`` (transport). Analogous to the ``core``-internal
      exception above: both modules are in ``painted.cli`` and the sharing is
      intentional, not a coupling leak.
    """
    # Modules whose private symbols may be imported by public sibling modules.
    # Keep this list narrow and document each entry above.
    _ALLOWED_SOURCES = {"painted._color", "painted.cli.complete"}

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
                if alias.name.startswith("_") and base not in _ALLOWED_SOURCES:
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


# --- Raise sites name a painted exception class (docs/ERRORS_DESIGN.md §6) ----
#
# The hierarchy is only load-bearing if new code keeps using it: a bare
# `raise ValueError`/`raise RuntimeError` in src/painted is a classification
# the design doc says must be made explicitly (DeclarationError / ContractError
# / LifecycleError). Only deliberately-exempt modules are named.
_BARE_RAISE_EXEMPT_FILES = {
    "_doc_pages.py",  # dev-only docs server — environmental failure, not a painted contract
}
_BARE_RAISE_CLASSES = {"ValueError", "RuntimeError"}


def test_raise_sites_use_painted_exception_classes() -> None:
    painted_root = _painted_root()
    violations: list[str] = []
    for py_file in sorted(painted_root.rglob("*.py")):
        if py_file.name in _BARE_RAISE_EXEMPT_FILES:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            exc = node.exc
            name = None
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            elif isinstance(exc, ast.Name):
                name = exc.id
            if name in _BARE_RAISE_CLASSES:
                violations.append(
                    f"{py_file.relative_to(painted_root.parent)}:{node.lineno} "
                    f"raises bare {name} (classify it per docs/ERRORS_DESIGN.md §4, "
                    "or exempt the module with rationale)"
                )

    assert not violations, "Bare stdlib raises outside the exemption list:\n" + "\n".join(
        violations
    )


# --- No semantic-renderer read of use_ansi (RENDERER_CONTRACT_DESIGN §9.5) ----
#
# capabilities.py replaced ctx.use_ansi as the vocabulary for content-structure
# carrier choices (color/glyph/link). The two former readers (raymarch, starmap)
# converted to current_capabilities() in M5-c; this gate keeps them converted and
# stops a new demo from reintroducing the proxy inside a render path.
#
# The exemption is structural, not name-based: a delivery call passing
# `use_ansi=ctx.use_ansi` straight through to a serializer (print_block, Writer
# construction) is host territory — it decides how an already-rendered Block
# reaches the terminal, never what the Block *contains*. Any other read of
# `.use_ansi` anywhere in demos/ or _demo_cli.py fails the gate, regardless of
# which function it sits in — a use_ansi-steered branch inside
# `_handle_interactive` is exactly the leak this must catch.
_USE_ANSI_DELIVERY_CALLEES = frozenset({"print_block", "Writer"})


def _is_use_ansi_delivery_argument(attribute: ast.Attribute, parent: ast.AST | None) -> bool:
    if not isinstance(parent, ast.keyword) or parent.arg != "use_ansi":
        return False
    call = getattr(parent, "_use_ansi_call", None)
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name in _USE_ANSI_DELIVERY_CALLEES


def test_demos_render_paths_do_not_read_use_ansi() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    targets = sorted((repo_root / "demos").rglob("*.py")) + [
        repo_root / "src" / "painted" / "_demo_cli.py"
    ]
    violations: list[str] = []
    for py_file in targets:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

        parent_of: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    kw._use_ansi_call = node  # type: ignore[attr-defined]
            for child in ast.iter_child_nodes(node):
                parent_of[id(child)] = node

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and node.attr == "use_ansi"):
                continue
            if _is_use_ansi_delivery_argument(node, parent_of.get(id(node))):
                continue
            violations.append(
                f"{py_file.relative_to(repo_root)}:{node.lineno} "
                "reads .use_ansi outside a delivery call's use_ansi= argument — a "
                "semantic-renderer path; use painted.capabilities.current_capabilities() "
                "instead (docs/RENDERER_CONTRACT_DESIGN.md §9.5)"
            )

    assert not violations, "use_ansi read on a render path:\n" + "\n".join(violations)
