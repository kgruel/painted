"""Import-smoke tier — the cheapest test that can fail.

`test_architecture_invariants.py` only AST-*parses* source; it never executes an
import, so it cannot catch an import-time cycle or a broken lazy-import entry.
This tier does.

On-brand for painted: the root package uses lazy imports specifically to dodge
cycles (see `painted.__init__._LAZY_IMPORTS`). A cycle surfaces here, not in the
static checks above it in the gate.

Each cycle/lazy check runs in a FRESH SUBPROCESS rather than by mutating this
interpreter's `sys.modules`. That is both more correct — a brand-new interpreter
is the truest "first import", so an order-dependent cycle cannot hide behind an
already-initialized module — and side-effect-free: evicting painted modules in
the shared test process would hand later tests a re-imported module with fresh
ContextVar state (ambient palette/icons), breaking the full single-process suite.
"""

from __future__ import annotations

import subprocess
import sys

import pkgutil

import painted


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )


def test_submodules_discovered() -> None:
    # Guard the guard: if discovery silently finds nothing, the cycle check below
    # would vacuously pass.
    names = sorted(m.name for m in pkgutil.walk_packages(painted.__path__, "painted."))
    assert len(names) > 20, f"suspiciously few painted submodules: {names}"


_FRESH_IMPORT_SCRIPT = """
import importlib, pkgutil, sys
import painted

names = sorted(m.name for m in pkgutil.walk_packages(painted.__path__, "painted."))
failures = []
for name in names:
    # Cold the painted.* cache so each module imports as if it were the FIRST
    # painted import — an order-dependent cycle cannot be masked by a cached module.
    for cached in [k for k in sys.modules if k == "painted" or k.startswith("painted.")]:
        del sys.modules[cached]
    try:
        importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - report any import-time failure
        failures.append(f"{name}: {exc!r}")

if failures:
    print("FAILURES||" + "||".join(failures))
    sys.exit(1)
print(f"OK||{len(names)}")
"""


def test_every_submodule_imports_as_fresh_first_import() -> None:
    """Every submodule imports cleanly from a cold cache (no import cycle)."""
    result = _run(_FRESH_IMPORT_SCRIPT)
    assert result.returncode == 0, (
        "submodule(s) failed to import as a fresh first import:\n"
        + result.stdout.replace("||", "\n")
        + result.stderr
    )
    assert result.stdout.startswith("OK||")


_LAZY_FACADE_SCRIPT = """
import sys
import painted

unresolved = []
for name in painted.__all__:
    try:
        getattr(painted, name)
    except AttributeError as exc:
        unresolved.append(f"{name}: {exc}")

if unresolved:
    print("UNRESOLVED||" + "||".join(unresolved))
    sys.exit(1)
print("OK")
"""


def test_lazy_facade_resolves_every_public_export() -> None:
    """Every name in painted.__all__ resolves through the lazy __getattr__.

    Catches a stale `_LAZY_IMPORTS` entry (wrong module path or attribute) — the
    failure mode the lazy facade trades for cold-start speed, invisible to static
    analysis.
    """
    result = _run(_LAZY_FACADE_SCRIPT)
    assert result.returncode == 0, (
        "painted.__all__ entries that do not resolve:\n"
        + result.stdout.replace("||", "\n")
        + result.stderr
    )


_LAZY_FACADE_COLD_SCRIPT = """
import sys
import painted

eager = sorted(
    name
    for name in sys.modules
    if name.startswith("painted.") and not name.startswith("painted._")
)
if eager:
    print("EAGER||" + "||".join(eager))
    sys.exit(1)
print("OK")
"""


def test_import_painted_does_not_eagerly_load_heavy_layers() -> None:
    """`import painted` stays cold: the root facade is fully lazy.

    The root package + `_LAZY_IMPORTS` exist to avoid eagerly pulling
    renderer/framework modules on bare `import painted`. Guard that promise.
    """
    result = _run(_LAZY_FACADE_COLD_SCRIPT)
    assert result.returncode == 0, (
        "import painted eagerly loaded submodules (lazy facade regressed):\n"
        + result.stdout.replace("||", "\n")
        + result.stderr
    )
