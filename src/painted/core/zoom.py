"""Zoom: detail level for rendering.

The other axis of rendering constraint alongside width.
Width says how much space, Zoom says how much detail.

Used by lenses, record_line, components, and show() — shared
vocabulary that flows from CLI parsing through to rendering.
"""

from enum import IntEnum


class Zoom(IntEnum):
    """Detail level for rendering."""

    MINIMAL = 0  # One-liner, counts only
    SUMMARY = 1  # Key information, tree structure
    DETAILED = 2  # Everything visible, nested expansion
    FULL = 3  # All fields, full depth
