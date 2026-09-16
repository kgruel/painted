"""Container-field normalization for frozen primitives.

A frozen dataclass that declares ``tuple[X, ...]`` gets no enforcement from
Python: pass a list and the attribute stays a list. The value then behaves
correctly almost everywhere and fails somewhere far away — the first place it
meets a tuple concatenation or is mutated through a caller's retained
reference. The annotation is the contract; this makes it true.

The rule predates this module — ``IconSet.spinner`` and ``Vocabulary.values``
already coerced, each for its own stated reason — but it was applied field by
field, so siblings drifted apart (``IconSet.sparkline`` did not coerce while
``IconSet.spinner`` did). ``tests/unit/test_frozen_containers.py`` is the
ratchet that keeps the family together; this is the one implementation it
holds every member to.
"""

from __future__ import annotations

from typing import Any


def freeze_fields(obj: Any, *names: str) -> None:
    """Normalize the named sequence fields of a frozen dataclass to tuples.

    Called from ``__post_init__``. Only the field itself is normalized — a
    nested sequence *inside* it is a separate declaration and is left alone
    (``Items.entries`` holds inline runs that may themselves be tuples).
    """
    for name in names:
        value = getattr(obj, name)
        if type(value) is not tuple:
            object.__setattr__(obj, name, tuple(value))
