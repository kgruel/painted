"""Guardrail: prevent regressions to len() for display width.

In display-critical modules, string display width must use wcwidth/wcswidth
semantics (see painted._text_width).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_LIB_ROOT = Path(__file__).resolve().parent.parent.parent

# Paths relative to _LIB_ROOT — used for both file access and allowlist keys
_REL_PATHS = [
    "src/painted/core/block.py",
    "src/painted/core/compose.py",
    "src/painted/views/lens/shape.py",
    "src/painted/views/components/_text_input.py",
    "src/painted/views/components/_data_explorer.py",
]

TARGET_MODULES = [(_LIB_ROOT / p, p) for p in _REL_PATHS]

# Heuristic: arguments containing these tokens are likely string/text.
_SUSPICIOUS_ARG_RE = re.compile(
    r"(\.text\b|\btext\b|\btitle\b|\bcontent\b|\bword\b|\bkeys\b|\bkey\b|\bprefix\b|\bplaceholder\b|\bsummary\b|\bleaf\b|\bch\b)"
)

# Allowlist of len() calls that are intentionally about indices or collection
# sizes. Keys are (path, enclosing_function, source_snippet) — the function
# name, not a line number, so unrelated edits and reformatting don't churn the
# ratchet; only touching the named function's own len() moves it.
ALLOWLIST = {
    # _run_width: len() is the display width for text proven ASCII one line up.
    ("src/painted/core/block.py", "_run_width", "len(text)"),
    # _take_runs_prefix: codepoint cursor bound, not a width measure.
    ("src/painted/core/block.py", "_take_runs_prefix", "len(text)"),
    ("src/painted/views/components/_text_input.py", "insert", "len(ch)"),
    ("src/painted/views/components/_text_input.py", "delete_forward", "len(self.text)"),
    ("src/painted/views/components/_text_input.py", "move_right", "len(self.text)"),
    ("src/painted/views/components/_text_input.py", "move_end", "len(self.text)"),
    ("src/painted/views/components/_text_input.py", "set_text", "len(text)"),
    ("src/painted/views/components/_text_input.py", "_ensure_visible", "len(text)"),
}


def _enclosing_function(tree: ast.Module, lineno: int) -> str:
    """Name of the innermost function containing lineno ('<module>' if none)."""
    innermost = "<module>"
    innermost_span = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            if node.lineno <= lineno <= end:
                span = end - node.lineno
                if innermost_span is None or span < innermost_span:
                    innermost = node.name
                    innermost_span = span
    return innermost


def test_no_new_len_on_text_variables_in_display_modules():
    violations: list[tuple[str, str, str]] = []

    for abs_path, rel_key in TARGET_MODULES:
        src = abs_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=rel_key)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "len":
                continue
            if len(node.args) != 1 or node.keywords:
                continue

            arg_src = ast.get_source_segment(src, node.args[0]) or ""
            if not _SUSPICIOUS_ARG_RE.search(arg_src):
                continue

            call_src = ast.get_source_segment(src, node) or "len(?)"
            func = _enclosing_function(tree, node.lineno)
            key = (rel_key, func, call_src)
            if key not in ALLOWLIST:
                violations.append((rel_key, f"{func}:{node.lineno}", call_src))

    if violations:
        formatted = "\n".join(f"- {p}:{ln}: {src}" for p, ln, src in violations)
        allow = "\n".join(f"- {p}:{ln}: {src}" for p, ln, src in sorted(ALLOWLIST))
        raise AssertionError(
            "Unexpected len() on likely text variables in display-critical modules.\n\n"
            "Violations:\n"
            f"{formatted}\n\n"
            "If this len() is intentional (non-display), add it to ALLOWLIST.\n"
            "Current ALLOWLIST:\n"
            f"{allow}\n"
        )
