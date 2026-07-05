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
the full stack with source, a caret, and redacted locals. The same declared
exception discloses more as you turn zoom up.

Run: uv run demos/primitives/diagnostics.py
"""

import traceback

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


def _fetch_quota() -> None:
    """The raising frame: plain locals render, sensitive names mask."""
    retries = 3
    endpoint = "quota.internal:9443"
    api_key = "sk-live-4242424242424242"
    db_password = "hunter2"
    raise TimeoutError(f"{endpoint} unreachable after {retries} retries")


def _with_secrets() -> BaseException:
    try:
        _fetch_quota()
    except TimeoutError as exc:
        return exc


def _grouped() -> BaseException:
    """Parallel startup checks failing together — ExceptionGroup is the tree."""
    try:
        raise ExceptionGroup(
            "startup checks failed",
            [
                ValueError("port 'eight' is not a number"),
                ExceptionGroup("database", [ConnectionError("primary unreachable")]),
                KeyError("region"),
            ],
        )
    except ExceptionGroup as exc:
        return exc


def _label(text: str) -> Block:
    return Block.text(f"  {text}", Style(dim=True))


def _section(label: str, block: Block) -> Block:
    return join_vertical(_label(label), Block.text("", Style()), block)


def _stdlib_render(exc: BaseException) -> Block:
    """stdlib's wall of text, dimmed — the 'before' painted renders the delta against."""
    lines = "".join(traceback.format_exception(exc)).rstrip("\n").split("\n")
    return join_vertical(*(Block.text(line, Style(dim=True), width=_WIDTH) for line in lines))


def build_output() -> Block:
    exc = _chained()
    gap = Block.text("", Style())
    return join_vertical(
        gap,
        _section("before — stdlib traceback.format_exception, the wall of text", _stdlib_render(exc)),
        gap,
        _section("after — the same exception as a record tree (DETAILED)", render_traceback(exc, Zoom.DETAILED, _WIDTH)),
        gap,
        _section("MINIMAL — type + message + innermost frame", render_traceback(exc, Zoom.MINIMAL, _WIDTH)),
        gap,
        _section("SUMMARY — the frame stack, chains summarized", render_traceback(exc, Zoom.SUMMARY, _WIDTH)),
        gap,
        _section(
            "SUMMARY, suppress=['diagnostics'] — matching frames fold to one line",
            render_traceback(exc, Zoom.SUMMARY, _WIDTH, suppress=["diagnostics"]),
        ),
        gap,
        _section(
            "FULL — budgeted locals; sensitive names mask to ∙∙∙ redacted",
            render_traceback(_with_secrets(), Zoom.FULL, _WIDTH),
        ),
        gap,
        _section("ExceptionGroup, SUMMARY — the shape without the depth", render_traceback(_grouped(), Zoom.SUMMARY, _WIDTH)),
        gap,
        _section("ExceptionGroup, DETAILED — every branch of the tree", render_traceback(_grouped(), Zoom.DETAILED, _WIDTH)),
        gap,
    )


output = build_output()


def demo() -> None:
    print_block(output)


if __name__ == "__main__":
    demo()
