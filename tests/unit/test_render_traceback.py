"""Unit tier — render_traceback structure: chains, groups, suppress, redact.

render_traceback projects an exception (or a captured TracebackException) into a
Block. These tests pin the *declared-meaning* behaviors — a chain connective, a
group tree, a suppress fold, a redacted local — plus the honesty rule (a declared
capability must change output) and the two input paths.
"""

from __future__ import annotations

import traceback

import pytest

from painted.core.zoom import Zoom
from painted.views import render_traceback
from painted.views._traceback import (
    _byte_to_char,
    _caret,
    default_redact,
)

from tests.helpers import block_to_text


def _chained() -> BaseException:
    try:
        try:
            raise ValueError("root cause")
        except ValueError as err:
            raise RuntimeError("higher level") from err
    except RuntimeError as exc:
        return exc


def _context() -> BaseException:
    try:
        try:
            raise ValueError("first")
        except ValueError:
            raise RuntimeError("during handling")
    except RuntimeError as exc:
        return exc


def _grouped() -> BaseException:
    try:
        raise ExceptionGroup("multi", [ValueError("a"), TypeError("b")])
    except ExceptionGroup as exc:
        return exc


_SECRET = "".join(["s", "k", "-", "x", "y", "z"])  # assembled, not a grep-able literal


def _with_locals() -> BaseException:
    def boom() -> None:
        api_key = _SECRET  # noqa: F841 — value is not a source literal
        visible = 42  # noqa: F841
        raise KeyError("missing")

    try:
        boom()
    except KeyError as exc:
        return exc


# --- Chains ------------------------------------------------------------------


def test_explicit_cause_connective() -> None:
    text = block_to_text(render_traceback(_chained(), Zoom.DETAILED, 80))
    assert "direct cause" in text
    assert "ValueError: root cause" in text
    assert "RuntimeError: higher level" in text


def test_implicit_context_connective() -> None:
    text = block_to_text(render_traceback(_context(), Zoom.DETAILED, 80))
    assert "During handling" in text
    assert "ValueError: first" in text
    assert "RuntimeError: during handling" in text


def test_suppress_context_hides_context() -> None:
    # `raise ... from ...` sets __suppress_context__, so the context chain
    # ("During handling") must NOT appear even though a __context__ exists.
    text = block_to_text(render_traceback(_chained(), Zoom.DETAILED, 80))
    assert "During handling" not in text


# --- Groups ------------------------------------------------------------------


def test_exception_group_tree() -> None:
    text = block_to_text(render_traceback(_grouped(), Zoom.DETAILED, 80))
    assert "ExceptionGroup" in text
    assert "ValueError: a" in text
    assert "TypeError: b" in text
    # Tree glyphs connect the members.
    assert "├─" in text or "└─" in text


# --- Cyclic chains -----------------------------------------------------------


def test_cyclic_cause_renders_marker() -> None:
    # A cyclic __cause__ chain (`a from b`, `b from a`) must stop at a muted marker
    # rather than recurse forever — the never-raise law under an adversarial chain.
    a, b = ValueError("a"), TypeError("b")
    a.__cause__, b.__cause__ = b, a
    text = block_to_text(render_traceback(b, Zoom.DETAILED, 80))
    assert "↻ <cycle>" in text


def test_cyclic_context_renders_marker() -> None:
    a, b = ValueError("a"), TypeError("b")
    a.__context__, b.__context__ = b, a
    a.__suppress_context__ = b.__suppress_context__ = False
    text = block_to_text(render_traceback(a, Zoom.DETAILED, 80))
    assert "↻ <cycle>" in text


# --- Suppress fold + honesty -------------------------------------------------


def test_suppress_folds_matching_frames() -> None:
    exc = _chained()
    off = block_to_text(render_traceback(exc, Zoom.SUMMARY, 80))
    on = block_to_text(render_traceback(exc, Zoom.SUMMARY, 80, suppress=["test_render_traceback"]))
    # Honesty: a declared capability changes output.
    assert on != off
    assert "frame" in on and "…" in on  # a fold line appeared


def test_suppress_no_match_is_inert() -> None:
    exc = _chained()
    off = block_to_text(render_traceback(exc, Zoom.SUMMARY, 80))
    on = block_to_text(render_traceback(exc, Zoom.SUMMARY, 80, suppress=["/no/such/path"]))
    assert on == off


# --- Redaction ---------------------------------------------------------------


def test_default_redact_masks_sensitive_names() -> None:
    assert default_redact("api_key")
    assert default_redact("PASSWORD")
    assert default_redact("access_token")
    assert not default_redact("count")


def test_locals_redacted_at_full() -> None:
    text = block_to_text(render_traceback(_with_locals(), Zoom.FULL, 100))
    assert "visible" in text and "42" in text
    assert "redacted" in text
    assert "sk-xyz" not in text  # the value never leaks


def test_redact_none_shows_everything() -> None:
    text = block_to_text(render_traceback(_with_locals(), Zoom.FULL, 100, redact=None))
    assert "sk-xyz" in text


# --- Zoom ladder honesty -----------------------------------------------------


def test_zoom_levels_differ() -> None:
    exc = _chained()
    rungs = [
        block_to_text(render_traceback(exc, z, 80))
        for z in (Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL)
    ]
    assert len(set(rungs)) == 4  # each rung is a distinct disclosure


def test_minimal_is_one_line() -> None:
    exc = _chained()
    text = block_to_text(render_traceback(exc, Zoom.MINIMAL, 80)).rstrip("\n")
    assert "\n" not in text
    assert "RuntimeError: higher level" in text


# --- TracebackException input path -------------------------------------------


def test_syntaxerror_head_parses_in_captured_path() -> None:
    # SyntaxError's exception-only rendering puts the source echo BEFORE the
    # head line — the captured path must still find `Type: message`, and both
    # input paths must agree (they collapse to the same tree).
    try:
        compile("def broken(:", "<fixture>", "exec")
    except SyntaxError as e:
        exc = e
    live = block_to_text(render_traceback(exc, Zoom.MINIMAL, None))
    te = traceback.TracebackException.from_exception(exc)
    captured = block_to_text(render_traceback(te, Zoom.MINIMAL, None))
    assert "SyntaxError" in captured
    assert "File" not in captured.split("\n")[0]  # the source echo is not the head
    assert captured.split("\n")[0] == live.split("\n")[0]


def test_captured_path_strips_module_qualified_type() -> None:
    # stdlib qualifies non-builtin exceptions as `module.Type`; the captured
    # path strips to the bare name the live path's type(exc).__name__ uses.
    class CustomBoom(Exception):
        pass

    try:
        raise CustomBoom("qualified")
    except CustomBoom as e:
        exc = e
    live = block_to_text(render_traceback(exc, Zoom.MINIMAL, None))
    te = traceback.TracebackException.from_exception(exc)
    captured = block_to_text(render_traceback(te, Zoom.MINIMAL, None))
    assert captured.split("\n")[0] == live.split("\n")[0]
    # Bare name, not the module-qualified `...<locals>.CustomBoom` stdlib prints.
    assert captured.startswith("CustomBoom: qualified")


def test_tracebackexception_input_renders() -> None:
    exc = _chained()
    te = traceback.TracebackException.from_exception(exc, capture_locals=True)
    text = block_to_text(render_traceback(te, Zoom.DETAILED, 80))
    assert "RuntimeError: higher level" in text
    assert "direct cause" in text


# --- Width contract ----------------------------------------------------------


@pytest.mark.parametrize("width", [20, 40, 80])
@pytest.mark.parametrize("zoom", [Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL])
def test_width_is_exact(width: int, zoom: Zoom) -> None:
    block = render_traceback(_with_locals(), zoom, width)
    assert block.width == width


def test_natural_width_when_none() -> None:
    # width=None → intrinsic sizing, no clip (piped output stays full-fidelity).
    block = render_traceback(_chained(), Zoom.SUMMARY, None)
    assert block.width > 0


# --- Caret geometry (display columns) ----------------------------------------


def test_byte_to_char_multibyte() -> None:
    # 'é' is 2 bytes in UTF-8; byte offset 3 lands after it → char index 2.
    assert _byte_to_char("héllo", 3) == 2


def test_caret_converts_wide_char_to_display_columns() -> None:
    # '世' is 3 UTF-8 bytes but 2 display columns. A caret at the char after it
    # must sit at column 2, not byte 3.
    line = "世x"
    colno = len("世".encode("utf-8"))  # byte offset of 'x'
    caret = _caret(line, colno, colno + 1)
    assert caret == "  ^"


def test_reraise_repr_failure_is_contained() -> None:
    # A local whose repr raises must degrade, not crash the error renderer.
    class Hostile:
        def __repr__(self) -> str:
            raise RuntimeError("no repr for you")

    def boom() -> None:
        trap = Hostile()  # noqa: F841
        raise ValueError("kaboom")

    try:
        boom()
    except ValueError as exc:
        block = render_traceback(exc, Zoom.FULL, 80)
    assert block.width == 80  # rendered without raising
