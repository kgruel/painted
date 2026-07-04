"""Diagnostics delivery — PaintedHandler + install.

The handler is a renderer, not a formatter: emit builds a Block and writes it.
These tests pin the declared behaviors — threshold honesty, extra→payload, the
exc_info composition point, the reentrancy guard, the handleError discipline —
and the excepthook invariants (byte-identical to the explicit render path,
KeyboardInterrupt passthrough, threads=True opt-in).
"""

from __future__ import annotations

import io
import logging
import sys

import pytest

from painted import DEFAULT_THRESHOLDS, PaintedHandler, Zoom, install, print_block
from painted.core.writer import ColorDepth
from painted.diagnostics import _resolve_severity
from painted.views import Severity, render_traceback


def _record(
    name: str = "test",
    level: int = logging.INFO,
    msg: str = "hello",
    *,
    args=(),
    exc_info=None,
    extra: dict | None = None,
) -> logging.LogRecord:
    rec = logging.LogRecord(name, level, __file__, 1, msg, args, exc_info)
    if extra:
        for k, v in extra.items():
            setattr(rec, k, v)
    return rec


def _emit(handler: PaintedHandler, record: logging.LogRecord) -> str:
    handler.emit(record)
    return handler._stream.getvalue()  # type: ignore[union-attr]


def _handler(**kw) -> PaintedHandler:
    kw.setdefault("color_depth", ColorDepth.NONE)
    return PaintedHandler(io.StringIO(), **kw)


# --- Thresholds -------------------------------------------------------------


def test_resolve_severity_picks_greatest_floor_cleared() -> None:
    assert _resolve_severity(logging.DEBUG, DEFAULT_THRESHOLDS) is Severity.INFO
    assert _resolve_severity(logging.INFO, DEFAULT_THRESHOLDS) is Severity.INFO
    assert _resolve_severity(logging.WARNING, DEFAULT_THRESHOLDS) is Severity.WARNING
    assert _resolve_severity(logging.ERROR, DEFAULT_THRESHOLDS) is Severity.ERROR
    assert _resolve_severity(logging.CRITICAL, DEFAULT_THRESHOLDS) is Severity.ERROR
    # Between floors resolves to the lower floor's severity.
    assert _resolve_severity(45, DEFAULT_THRESHOLDS) is Severity.ERROR
    # Below every floor degrades to INFO.
    assert _resolve_severity(1, DEFAULT_THRESHOLDS) is Severity.INFO


def test_custom_thresholds_change_output_honesty() -> None:
    """A custom mapping is the declaration point — it MUST change output."""
    rec = _record(level=logging.WARNING, msg="watch out")
    default = _emit(_handler(color_depth=ColorDepth.TRUECOLOR), _record(level=logging.WARNING))
    # Re-route WARNING onto the ERROR severity → a different role color in the ANSI.
    custom = _emit(
        _handler(
            color_depth=ColorDepth.TRUECOLOR,
            thresholds={logging.WARNING: Severity.ERROR},
        ),
        rec,
    )
    assert default != custom


# --- Extra → payload / message ---------------------------------------------


def test_extra_fields_render_as_payload_at_detailed() -> None:
    rec = _record(level=logging.INFO, msg="done", extra={"user": "kyle", "count": 3})
    out = _emit(_handler(zoom=Zoom.DETAILED), rec)
    assert "user = kyle" in out
    assert "count = 3" in out


def test_extra_fields_absent_below_detailed() -> None:
    rec = _record(level=logging.INFO, msg="done", extra={"user": "kyle"})
    out = _emit(_handler(zoom=Zoom.SUMMARY), rec)
    assert "user = kyle" not in out


def test_message_uses_getmessage_with_args() -> None:
    rec = _record(msg="hello %s", args=("world",))
    out = _emit(_handler(), rec)
    assert "hello world" in out


def test_zoom_changes_output() -> None:
    rec = _record(level=logging.INFO, msg="hi")
    minimal = _emit(_handler(zoom=Zoom.MINIMAL), _record(level=logging.INFO, msg="hi"))
    summary = _emit(_handler(zoom=Zoom.SUMMARY), rec)
    # SUMMARY adds the timestamp + logger name; MINIMAL does not.
    assert "test" in summary
    assert "test" not in minimal


# --- exc_info composition ---------------------------------------------------


def _exc_info():
    try:
        raise ValueError("boom")
    except ValueError:
        return sys.exc_info()


def test_exc_info_renders_traceback() -> None:
    rec = _record(level=logging.ERROR, msg="failed", exc_info=_exc_info())
    out = _emit(_handler(zoom=Zoom.DETAILED), rec)
    assert "ValueError: boom" in out


def test_traceback_zoom_is_a_ceiling() -> None:
    """A FULL handler with a DETAILED traceback_zoom must not dump locals."""
    exc = _exc_info()
    secret_local = "sentinel_value_xyz"  # noqa: F841 — captured by the frame below

    def _raise():
        marker = secret_local  # noqa: F841
        raise KeyError("k")

    try:
        _raise()
    except KeyError:
        exc = sys.exc_info()
    rec = _record(level=logging.ERROR, msg="failed", exc_info=exc)
    out = _emit(_handler(zoom=Zoom.FULL, traceback_zoom=Zoom.DETAILED), rec)
    assert "sentinel_value_xyz" not in out


# --- Reentrancy / handleError ----------------------------------------------


def test_reentrancy_guard_falls_back_to_plain_line() -> None:
    handler = _handler(zoom=Zoom.DETAILED)
    handler._local.in_emit = True  # simulate being mid-render
    out = _emit(handler, _record(msg="reentrant"))
    assert out.strip() == "reentrant"


def test_render_failure_routes_to_handle_error(monkeypatch) -> None:
    handler = _handler()
    seen: list[logging.LogRecord] = []
    monkeypatch.setattr(handler, "handleError", seen.append)
    monkeypatch.setattr(handler, "_build", lambda rec: (_ for _ in ()).throw(RuntimeError("x")))
    handler.emit(_record())
    assert len(seen) == 1


def test_pipe_stream_renders_plain() -> None:
    """A non-tty stream (color_depth NONE) emits no escape codes."""
    out = _emit(_handler(color_depth=ColorDepth.NONE), _record(level=logging.ERROR))
    assert "\x1b[" not in out


# --- install / excepthook ---------------------------------------------------


@pytest.fixture
def _restore_hooks():
    saved_sys = sys.excepthook
    import threading

    saved_thread = threading.excepthook
    yield
    sys.excepthook = saved_sys
    threading.excepthook = saved_thread


def test_install_hook_is_byte_identical_to_explicit_path(_restore_hooks, capsys) -> None:
    try:
        raise ValueError("identical")
    except ValueError as e:
        exc = e

    install(zoom=Zoom.DETAILED, width=60)
    sys.excepthook(type(exc), exc, exc.__traceback__)
    hook_out = capsys.readouterr().err

    print_block(render_traceback(exc, Zoom.DETAILED, 60, suppress=()), sys.stderr)
    explicit_out = capsys.readouterr().err

    assert hook_out == explicit_out
    assert hook_out.strip()


def test_install_passes_through_keyboard_interrupt(_restore_hooks, capsys) -> None:
    install()
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt as e:
        sys.excepthook(type(e), e, e.__traceback__)
    err = capsys.readouterr().err
    # The default hook prints the bare "KeyboardInterrupt", not a rendered gutter rail.
    assert "│" not in err
    assert "KeyboardInterrupt" in err


def test_install_threads_opt_in(_restore_hooks) -> None:
    import threading

    before = threading.excepthook
    install(threads=False)
    assert threading.excepthook is before  # untouched without opt-in

    install(threads=True)
    assert threading.excepthook is not before


def test_install_thread_hook_renders(_restore_hooks, capsys) -> None:
    import threading

    install(threads=True, zoom=Zoom.SUMMARY)

    def target():
        raise ValueError("in a thread")

    t = threading.Thread(target=target)
    t.start()
    t.join()
    err = capsys.readouterr().err
    assert "ValueError: in a thread" in err
