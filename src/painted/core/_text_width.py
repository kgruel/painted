"""Utilities for display-width-aware text measurement and truncation.

Terminal UIs need to measure strings in display columns (wcwidth/wcswidth),
not code points (len()).
"""

from __future__ import annotations

from wcwidth import wcswidth, wcwidth

from ..icon_set import current_icons


_display_width_cache: dict[str, int] = {}


def display_width(text: str) -> int:
    """Return the display width (columns) of a string — the cell count its
    materialization produces (zero-width chars contribute nothing, wide chars
    two columns, non-printables one: they scrub to a space cell).

    When wcswidth reports non-printable characters the width is summed
    per-char instead — never a ``len()`` fallback, which would miscount any
    wide or zero-width char sharing the string with the non-printable.
    """
    if text.isascii():
        return len(text)
    cached = _display_width_cache.get(text)
    if cached is not None:
        return cached
    w = wcswidth(text)
    if w < 0:
        w = sum(cw for cw in map(char_width, text) if cw > 0)
    if len(_display_width_cache) < 4096:
        _display_width_cache[text] = w
    return w


_char_width_cache: dict[str, int] = {}


def char_width(ch: str) -> int:
    """Return the display width (columns) of a single character."""
    if ch.isascii():
        return 1
    cached = _char_width_cache.get(ch)
    if cached is not None:
        return cached
    w = wcwidth(ch)
    if w < 0:
        w = 1
    _char_width_cache[ch] = w
    return w


def take_prefix(text: str, max_width: int) -> tuple[str, int]:
    """Take a prefix that fits within max_width display columns.

    Returns (prefix, consumed_codepoints).
    """
    if max_width <= 0 or not text:
        return ("", 0)

    used = 0
    chars: list[str] = []
    consumed = 0

    for i, ch in enumerate(text):
        w = char_width(ch)
        if w == 0:
            # Combining marks / zero-width characters: keep them in the prefix.
            chars.append(ch)
            consumed = i + 1
            continue

        if used + w > max_width:
            break

        chars.append(ch)
        used += w
        consumed = i + 1

        if used == max_width:
            break

    return ("".join(chars), consumed)


def truncate(text: str, max_width: int) -> str:
    """Truncate text to max_width display columns."""
    prefix, _ = take_prefix(text, max_width)
    return prefix


def truncate_ellipsis(text: str, max_width: int, *, ellipsis: str | None = None) -> str:
    """Truncate text with an ellipsis if it exceeds max_width columns.

    ``ellipsis=None`` (the default) reads the ambient ``IconSet.ellipsis`` so the
    marker degrades to ASCII under ``use_icons(ASCII_ICONS)``; pass an explicit
    string to override.
    """
    if ellipsis is None:
        ellipsis = current_icons().ellipsis
    if max_width <= 0:
        return ""

    if display_width(text) <= max_width:
        return text

    ell_w = display_width(ellipsis)
    if ell_w <= 0 or ell_w >= max_width:
        return truncate(text, max_width)

    return truncate(text, max_width - ell_w) + ellipsis


def index_for_col(text: str, col: int) -> int:
    """Return the largest string index whose prefix width is <= col."""
    if col <= 0 or not text:
        return 0

    used = 0
    for i, ch in enumerate(text):
        w = char_width(ch)
        if w == 0:
            continue
        if used + w > col:
            return i
        used += w

    return len(text)
