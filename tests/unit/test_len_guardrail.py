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
# ratchet; only touching the named function's own len() moves it. The value is
# the exact occurrence count within that function: a duplicate call added
# under an existing key is a new suspicious call and still trips the ratchet.
ALLOWLIST: dict[tuple[str, str, str], int] = {
    # _take_runs_prefix / _rest_runs: codepoint cursor bounds, not width measures.
    ("src/painted/core/block.py", "_take_runs_prefix", "len(text)"): 2,
    ("src/painted/core/block.py", "_rest_runs", "len(text)"): 1,
    ("src/painted/views/components/_text_input.py", "insert", "len(ch)"): 1,
    ("src/painted/views/components/_text_input.py", "delete_forward", "len(self.text)"): 1,
    ("src/painted/views/components/_text_input.py", "move_right", "len(self.text)"): 1,
    ("src/painted/views/components/_text_input.py", "move_end", "len(self.text)"): 1,
    ("src/painted/views/components/_text_input.py", "set_text", "len(text)"): 1,
    ("src/painted/views/components/_text_input.py", "_ensure_visible", "len(text)"): 3,
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
    counts: dict[tuple[str, str, str], int] = {}
    linenos: dict[tuple[str, str, str], list[int]] = {}

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
            counts[key] = counts.get(key, 0) + 1
            linenos.setdefault(key, []).append(node.lineno)

    violations = [
        (key, count) for key, count in sorted(counts.items()) if count > ALLOWLIST.get(key, 0)
    ]
    if violations:
        formatted = "\n".join(
            f"- {p}:{fn}: {src} x{count} (allowed {ALLOWLIST.get((p, fn, src), 0)}; "
            f"lines {linenos[(p, fn, src)]})"
            for (p, fn, src), count in violations
        )
        allow = "\n".join(
            f"- {p}:{fn}: {src} x{n}" for (p, fn, src), n in sorted(ALLOWLIST.items())
        )
        raise AssertionError(
            "Unexpected len() on likely text variables in display-critical modules.\n\n"
            "Violations:\n"
            f"{formatted}\n\n"
            "If this len() is intentional (non-display), add it to ALLOWLIST with its count.\n"
            "Current ALLOWLIST:\n"
            f"{allow}\n"
        )

    # Shrink-only in both dimensions: an allowlist entry whose calls are gone
    # (or fewer) is stale — ratchet it down rather than leaving headroom a new
    # suspicious call could hide in.
    stale = [(key, n) for key, n in sorted(ALLOWLIST.items()) if counts.get(key, 0) < n]
    assert not stale, (
        "Stale ALLOWLIST entries (actual count below allowed — remove or lower them):\n"
        + "\n".join(
            f"- {p}:{fn}: {src} allowed {n}, found {counts.get((p, fn, src), 0)}"
            for (p, fn, src), n in stale
        )
    )
