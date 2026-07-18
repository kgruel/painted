"""The inward host-event seam's causality invariant (HOST_RUNG_DESIGN §7, S5).

Driven in the **production drain shape**: ``Surface.run`` drains several inputs
before a repaint, so transitions accumulate against a *fixed* displayed frame
between repaints. The strategy interleaves ``repaint`` markers (a ``frame()``
call) with transition ops; between two repaints the ops form one drain batch. For
*any* such sequence, every delivered ``HostEvent`` obeys:

  * ``observed`` == the token of the **last displayed frame** — it stays fixed
    across the batch (its causality job), so later events in a batch legitimately
    carry ``observed != current``;
  * ``current`` == the mapping the transition **installed** (``adapter.token()``
    right after it), never copied from ``observed``;
  * **no event fires before the first display** — no observed mapping exists yet.

Driven over the shared ``HostViewport`` controller (both host surfaces route
through it), so the law is proven once for the machinery both consume.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.core.block import Block
from painted.core.cell import Style
from painted.core.compose import join_vertical
from painted.host import HostViewport, ResizeChange
from painted.mouse import MouseButton

_KEYS = ("up", "down", "page_up", "page_down", "home", "end")
_OPS = st.sampled_from(
    (*_KEYS, "wheel_up", "wheel_down", "grow", "reslice", "cursor", "quit", "repaint")
)


def _rows(n: int, width: int = 20) -> Block:
    return join_vertical(*[Block.text(f"row{i}", Style(), width=width) for i in range(n)])


@given(ops=st.lists(_OPS, min_size=1, max_size=64))
def test_observed_is_the_last_displayed_frame_and_current_is_the_installed_state(
    ops: list[str],
) -> None:
    events: list[object] = []
    vp = HostViewport(content_id="doc", on_event=events.append, follow_start=True)
    vp.set_geometry(20, 5)
    vp.install(_rows(30), reason=None)  # mount (silent) — NO frame() yet

    displayed = None  # the last DISPLAYED frame token; None until the first repaint
    for i, op in enumerate(ops):
        if op == "repaint":
            vp.frame()
            displayed = vp.last_token  # a new displayed frame the next batch lands on
            continue

        prev = len(events)
        if op in _KEYS:
            vp.route_key(op)
        elif op == "wheel_up":
            vp.route_wheel(MouseButton.SCROLL_UP)
        elif op == "wheel_down":
            vp.route_wheel(MouseButton.SCROLL_DOWN)
        elif op == "grow":
            vp.publish_stream(_rows(30 + i))  # a new generation; emits iff following
        elif op == "reslice":
            vp.set_geometry(20, 3 + (i % 6))
            vp.reslice(reason=ResizeChange())
        elif op == "cursor":
            vp.cursor_to(i % 30)
        else:  # quit
            vp.route_quit()

        installed = vp.adapter.token()  # the mapping this transition installed
        for ev in events[prev:]:
            if displayed is None:
                raise AssertionError("an event was delivered before the first display")
            # observed pins to the last DISPLAYED frame — fixed across the batch.
            assert ev.observed == displayed  # type: ignore[attr-defined]
            # current is exactly the live installed mapping, never copied.
            assert ev.current == installed  # type: ignore[attr-defined]

    # If the run never repainted, the seam stayed silent throughout.
    if "repaint" not in ops:
        assert events == []
