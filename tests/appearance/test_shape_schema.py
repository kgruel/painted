"""Dataclass rendering ladder — pins the declared-schema branch of shape_lens.

Slice 1 routes a dataclass instance through the dict machinery: fields become a
key-value table, `repr=False` fields are dropped (declared suppression), and each
value renders through the budgeted recursive path. This fixture snapshots that
ladder across zooms so a regression in the field projection — a leaked `secret`,
a lost bold key, a nested value that stops recursing — shows up as a precise diff.

The dataclass is defined at module scope with pinned field values so the snapshot
is deterministic (no interpreter drift).
"""

from __future__ import annotations

import dataclasses

from painted import join_vertical
from painted.views import shape_lens

_WIDTH = 32


@dataclasses.dataclass
class _Account:
    user: str
    roles: list
    secret: str = dataclasses.field(repr=False)  # declared suppression
    active: bool = True


_FIXTURE = _Account(user="alice", roles=["admin", "ops"], secret="hunter2", active=True)


def test_dataclass_ladder(appearance) -> None:
    # One rendering per zoom rung — the same declared schema, disclosed further at
    # each step. `secret` must never appear in any rung.
    blocks = [shape_lens(_FIXTURE, zoom=z, width=_WIDTH) for z in (0, 1, 2, 3)]
    appearance.assert_block(join_vertical(*blocks), "ladder")
