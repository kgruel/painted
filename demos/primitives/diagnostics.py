#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""render_traceback — an exception as a record tree.

A traceback is structured data, not a wall of text: frames are records on a
continuous gutter rail, and cause/context chains are the tree that connects
them. Capturing the exception is the *declaration*; render_traceback projects
that captured tree at a zoom level — a one-line summary, the frame stack, or
the full stack with source and a caret. The same declared exception discloses
more as you turn zoom up.

Run: uv run demos/primitives/diagnostics.py
"""

from painted import Block, Style, Zoom, join_vertical, print_block
from painted.views import render_traceback

_WIDTH = 72


def _chained() -> BaseException:
    """A RuntimeError caused by a ValueError — frames stay in this file, so the
    basenames and line numbers render deterministically."""
    try:
        try:
            config = {"port": "eight"}
            int(config["port"])
        except ValueError as cause:
            raise RuntimeError("could not start server") from cause
    except RuntimeError as exc:
        return exc


def _label(text: str) -> Block:
    return Block.text(f"  {text}", Style(dim=True))


def _section(label: str, block: Block) -> Block:
    return join_vertical(_label(label), Block.text("", Style()), block)


def build_output() -> Block:
    exc = _chained()
    return join_vertical(
        Block.text("", Style()),
        _section("MINIMAL — type + message + innermost frame", render_traceback(exc, Zoom.MINIMAL, _WIDTH)),
        Block.text("", Style()),
        _section("SUMMARY — the frame stack, chains summarized", render_traceback(exc, Zoom.SUMMARY, _WIDTH)),
        Block.text("", Style()),
        _section("DETAILED — source with a caret, chain fully rendered", render_traceback(exc, Zoom.DETAILED, _WIDTH)),
        Block.text("", Style()),
        _section(
            "SUMMARY, suppress=['diagnostics'] — matching frames fold to one line",
            render_traceback(exc, Zoom.SUMMARY, _WIDTH, suppress=["diagnostics"]),
        ),
        Block.text("", Style()),
    )


output = build_output()


def demo() -> None:
    print_block(output)


if __name__ == "__main__":
    demo()
