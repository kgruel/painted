"""Lens functions: stateless content-to-Block transformation at zoom levels.

Four built-in strategies:
  shape_lens  — auto-dispatches by data shape (generic Python values)
  tree_lens   — hierarchical data with branch characters
  chart_lens  — numeric data as sparklines/bars
  flame_lens  — hierarchical data as proportional horizontal segments

All share the same signature: (data, zoom, width) -> Block.
"""

from .chart import chart_lens
from .flame import flame_lens
from .shape import shape_lens
from .tree import NodeRenderer, tree_lens

__all__ = [
    "NodeRenderer",
    "chart_lens",
    "flame_lens",
    "shape_lens",
    "tree_lens",
]
