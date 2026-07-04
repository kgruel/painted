"""Pinned exception fixtures for deterministic traceback snapshots.

Every exception here is raised and caught *entirely within this module*, so the
captured traceback holds only this file's frames — its basename (``_tb_fixture.py``)
and line numbers are stable across machines, and ``linecache`` reads real source
from this real file. Locals at the innermost frame are deliberately simple scalars
(no object reprs, no addresses) so the FULL-zoom rendering stays deterministic.

Do NOT reformat this file casually: the committed appearance snapshots pin the
line numbers below. A deliberate edit regenerates them via ``--update-appearance``.
"""

from __future__ import annotations


def divide(a: int, b: int) -> float:
    numerator = a
    return numerator / b  # ZeroDivisionError raises here


def _wrap() -> None:
    try:
        divide(10, 0)
    except ZeroDivisionError as err:
        raise ValueError("could not divide") from err


def make_chained() -> BaseException:
    """A ``raise ... from ...`` explicit-cause chain."""
    try:
        _wrap()
    except ValueError as exc:
        return exc
    raise AssertionError("unreachable")


def make_context() -> BaseException:
    """An implicit ``__context__`` chain (error during error handling)."""
    try:
        divide(1, 0)
    except ZeroDivisionError:
        try:
            raise RuntimeError("cleanup failed")
        except RuntimeError as exc:
            return exc
    raise AssertionError("unreachable")


def make_group() -> BaseException:
    """An ExceptionGroup with two heterogeneous leaves."""
    try:
        raise ExceptionGroup("multiple failures", [ValueError("first"), TypeError("second")])
    except ExceptionGroup as exc:
        return exc


# Assembled at import (not a source literal) so no source line reveals it — the
# only carrier is the redacted `password` local below.
_SECRET = "".join(["hunt", "er2"])


def _raise_simple() -> None:
    password = _SECRET  # noqa: F841 — redaction target
    count = 3  # noqa: F841 — plain local, rendered at FULL
    note = "deterministic"  # noqa: F841
    raise KeyError("missing")


def make_simple() -> BaseException:
    """A single-frame error carrying redactable + plain locals for FULL zoom."""
    try:
        _raise_simple()
    except KeyError as exc:
        return exc
    raise AssertionError("unreachable")
