"""The drift ratchet for formal models: has the code a model describes changed?

A model checker proves things about a model. The model is tied to the code only
by a hand-kept table, so a pass can outlive the code it described. This closes
that gap cheaply: each model keeps a ``sync.json`` naming the symbols it covers
and a hash of their ASTs. Tier 0 of ``./dev check`` recomputes the hash (no Java,
no imports of the code) and fails when they differ, pointing at ``./dev verify``.

The hash is over the AST with docstrings removed, so comments, docstrings and
formatting never trip it; any change to what the code does, does.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

__all__ = ["covered_hash", "load_manifest", "manifests"]


def manifests(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "verification").glob("*/sync.json"))


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def _strip_docstrings(node: ast.AST) -> None:
    for child in ast.walk(node):
        body = getattr(child, "body", None)
        if (
            isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            child.body = body[1:] or [ast.Pass()]


def _find(tree: ast.Module, dotted: str) -> ast.AST:
    scope: ast.AST = tree
    for name in dotted.split("."):
        for child in getattr(scope, "body", []):
            if (
                isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                and child.name == name
            ):
                scope = child
                break
        else:
            raise LookupError(dotted)
    return scope


def covered_hash(repo_root: Path, manifest: dict) -> str:
    """sha256 over the covered symbols' ASTs. A missing symbol raises LookupError:
    covered code that was renamed or removed is drift too."""
    tree = ast.parse((repo_root / manifest["file"]).read_text())
    digest = hashlib.sha256()
    for dotted in manifest["covered"]:
        node = _find(tree, dotted)
        _strip_docstrings(node)
        digest.update(dotted.encode())
        digest.update(ast.dump(node).encode())
    return digest.hexdigest()
