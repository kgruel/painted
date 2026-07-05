#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""The exception hierarchy — painted's faults have names, and painted renders them.

PaintedError is the root a consumer catches; its three subclasses each name a
behavioral contract: DeclarationError (fix the declaration), ContractError
(fix the value), LifecycleError (fix the call sequence). Each also inherits
the stdlib type it replaced, so existing `except ValueError` code keeps
working — but the *displayed* name now says which contract was broken. The
tree below is introspected from the classes; the faults below it are real —
each one raised by painted, caught as PaintedError, and rendered by the same
PaintedHandler that renders any log record. See docs/ERRORS_DESIGN.md.

Run: uv run demos/primitives/errors.py
"""

import argparse
import io
import logging
import sys

from painted import (
    Block,
    InPlaceRenderer,
    PaintedError,
    PaintedHandler,
    Style,
    Zoom,
    join_vertical,
    print_block,
)
from painted.cli import Tag, add_cli_args
from painted.core.cell import Cell
from painted.views import tree_lens

_WIDTH = 72

# One fixed timestamp for every record — the output is about the taxonomy,
# not about when the demo ran.
_CREATED = 1751600000.0

# The one-line behavioral contract per class — the lesson text; the shape of
# the tree itself is derived from the classes, not drawn.
_CONTRACTS = {
    "DeclarationError": "fix the declaration",
    "ContractError": "fix the value",
    "LifecycleError": "fix the call sequence",
}


def _hierarchy() -> tuple:
    """Introspect the real tree: subclasses and their stdlib co-parents."""
    children = {}
    for sub in sorted(PaintedError.__subclasses__(), key=lambda c: c.__name__):
        stdlib = ", ".join(
            b.__name__ for b in sub.__bases__ if not issubclass(b, PaintedError)
        )
        children[f"{sub.__name__} (also {stdlib}) — {_CONTRACTS[sub.__name__]}"] = {}
    return ("PaintedError", children)


def _declaration_fault() -> tuple:
    """A declared flag colliding with the framework's --json — raises before
    any rendering happens."""
    try:
        add_cli_args(argparse.ArgumentParser(), tags=[Tag("json", "collides")])
    except PaintedError as exc:
        return (type(exc), exc, exc.__traceback__)


def _contract_fault() -> tuple:
    """A two-character Cell — the atom's contract is one display cell."""
    try:
        Cell("ab", Style())
    except PaintedError as exc:
        return (type(exc), exc, exc.__traceback__)


def _lifecycle_fault() -> tuple:
    """render() outside the context manager — right call, wrong state."""
    try:
        InPlaceRenderer(io.StringIO()).render(Block.text("x", Style()))
    except PaintedError as exc:
        return (type(exc), exc, exc.__traceback__)


def _record(msg: str, exc_info: tuple) -> logging.LogRecord:
    record = logging.LogRecord("app.startup", logging.ERROR, __file__, 0, msg, (), exc_info)
    record.created = _CREATED
    return record


def _label(text: str) -> Block:
    return join_vertical(
        Block.text("", Style()), Block.text(f"  {text}", Style(dim=True)), Block.text("", Style())
    )


def demo() -> None:
    print_block(_label("the hierarchy — introspected from the classes, one root to catch"))
    print_block(tree_lens(_hierarchy(), Zoom.DETAILED, _WIDTH))

    print_block(_label("each contract broken for real — caught as PaintedError, logged (SUMMARY)"))
    summary = PaintedHandler(sys.stdout, zoom=Zoom.SUMMARY)
    summary.emit(_record("declaration rejected at startup", _declaration_fault()))
    summary.emit(_record("cell construction rejected", _contract_fault()))
    summary.emit(_record("renderer used outside its lifecycle", _lifecycle_fault()))

    print_block(_label("DETAILED — the record tree under the log line names the contract"))
    detailed = PaintedHandler(sys.stdout, zoom=Zoom.DETAILED)
    detailed.emit(_record("declaration rejected at startup", _declaration_fault()))


if __name__ == "__main__":
    demo()
