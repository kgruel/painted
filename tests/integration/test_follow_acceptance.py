"""The follow acceptance shape — the painted-side proof the inward seam brings
``strange-loops follow`` home through the framework (HOST_RUNG_DESIGN §7/§8, S5).

``follow`` is the forcing consumer §8 names: a long-running foreground stream that
bypassed ``run_cli`` because a plain direct-paint Surface plus callback could not
tail growing content with evidence. This drives it **through the real path**:
``run_cli`` with a declared stream and ``live_delivery="surface"`` → dispatch →
``_run_live_surface`` → a genuine ``StreamSurface`` whose real async ``_consume``
task pulls the declared ``fetch_stream``. Only the alt-screen ``run()`` shell —
which needs a real terminal — is replaced by a deterministic driver that runs the
*production* consumer + ``render()`` + ``on_key`` and steps them explicitly; no
private ``_frame`` / ``_pending`` poking, the coalescing and draining are real.

The scenario:
  1. content grows while following — the viewport tails the bottom and a
     ``FollowChange`` fires each yield once a frame has been displayed (the first
     yield IS the first display, so it tails silently — §7 delivers no event
     before an observed frame exists);
  2. the user scrolls up — follow disengages, the ``HostViewportEvent`` carries
     it, and the evidence row's below-count starts counting the tail;
  3. content keeps growing while scrolled up — the viewer holds their place
     (offset fixed) and the evidence below-count GROWS, with no viewport event;
  4. ``end`` re-engages follow at the new bottom.

And through all of it: every event's ``observed`` equals the frame the input
landed on. The in-repo ticked exercise (one binding across the four rungs)
happens after this slice merges (§8).
"""

from __future__ import annotations

import asyncio
import contextlib
import io

from painted import FollowChange, HostViewportEvent
from painted.cli.runner import run_cli
from painted.cli.stream_surface import StreamSurface
from painted.core.block import Block
from painted.core.buffer import Buffer
from painted.core.cell import Style
from painted.core.compose import join_vertical
from painted.core.writer import Writer

WIDTH, HEIGHT = 20, 5  # a 5-row frame: 4 content rows + 1 evidence row on overflow


def _rows(n: int, width: int) -> Block:
    return join_vertical(*[Block.text(f"line {i}", Style(), width=width) for i in range(n)])


def _below_count(surf: StreamSurface) -> int:
    """Rows the window omits BELOW the frame — what the evidence row counts as
    the tail accrues. Read from the live adapter (offset + shown vs content)."""
    a = surf._vp.adapter
    assert a.content is not None
    ch = a.content.height
    frame_h = a.frame_height
    shown = (frame_h - 1) if ch > frame_h else frame_h  # overflow reserves one evidence row
    return max(0, ch - (a.viewport.offset + shown))


def test_follow_comes_home_through_run_cli(monkeypatch) -> None:
    events: list[object] = []
    steps: list[tuple[str, object, list[object]]] = []  # (label, landed, events_this_step)
    result: dict[str, object] = {}
    box: dict[str, asyncio.Queue] = {}

    async def app_stream():
        """The declared stream: pulls row-counts from a queue the driver fills,
        so yields pace deterministically against the render steps. A ``None``
        sentinel exhausts it."""
        q = box["feed"]
        while True:
            n = await q.get()
            if n is None:
                return
            yield n

    async def fake_run(self: StreamSurface) -> None:
        # Headless terminal (the only substitution — no tty/alt-screen), then the
        # REAL production consumer + render + input routing, stepped explicitly.
        self._writer = Writer(io.StringIO())
        self._buf = Buffer(WIDTH, HEIGHT)
        self._prev = Buffer(WIDTH, HEIGHT)
        self.layout(WIDTH, HEIGHT)  # production mount
        box["feed"] = asyncio.Queue()
        self._running = True
        consumer = asyncio.create_task(self._consume())

        async def wait_pending() -> None:
            for _ in range(10_000):
                if self._pending or not self._running:
                    return
                await asyncio.sleep(0)
            raise AssertionError("the production consumer never delivered a state")

        def render_once() -> None:
            self._dirty = True
            with self._frame_scope():
                self.render()  # production render → publish (coalesced) → frame

        async def deliver(n: int) -> None:
            landed = self._vp.last_token
            prev = len(events)
            await box["feed"].put(n)  # a real stream yield through _consume
            await wait_pending()
            render_once()
            steps.append((f"deliver({n})", landed, events[prev:]))

        def press(key: str) -> None:
            landed = self._vp.last_token
            prev = len(events)
            self.on_key(key)  # production routing → events
            render_once()
            steps.append((f"press({key})", landed, events[prev:]))

        # --- the scenario -----------------------------------------------------
        await deliver(8)  # first display: tails the bottom silently (no observed frame yet)
        await deliver(12)  # grows while following → FollowChange, tracks the bottom
        await deliver(16)  # grows again → FollowChange
        press("up")  # scroll up → follow disengages; the event carries it
        result["offset_scrolled"] = self._vp.adapter.viewport.offset
        result["below_after_up"] = _below_count(self)
        await deliver(40)  # grows while scrolled up → hold place, below-count grows
        result["offset_after_grow"] = self._vp.adapter.viewport.offset
        result["below_after_grow"] = _below_count(self)
        press("end")  # re-engage follow at the new bottom

        # teardown: exhaust the stream and let the consumer unwind
        self._running = False
        await box["feed"].put(None)
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)  # take the alt-screen surface tier

    rc = run_cli(
        ["--live"],
        renderer=lambda data, fidelity, width: _rows(int(data), width or WIDTH),
        fetch=lambda: 0,
        fetch_stream=app_stream,
        live_delivery="surface",
        on_host_event=events.append,
    )
    assert rc == 0  # a scenario failure inside fake_run would surface as a nonzero code

    by_label = {label: (landed, evs) for label, landed, evs in steps}

    def only_follow(evs: list[object]) -> HostViewportEvent:
        assert len(evs) == 1, f"expected exactly one event, got {evs}"
        ev = evs[0]
        assert isinstance(ev, HostViewportEvent) and isinstance(ev.reason, FollowChange)
        return ev

    # 1. The first yield is the first display → no event (nothing observed yet),
    #    but subsequent growth while following fires FollowChange tracking bottom.
    assert by_label["deliver(8)"][1] == []  # first display: silent tail
    ev = only_follow(by_label["deliver(12)"][1])
    assert ev.following is True and ev.is_at_bottom is True
    ev = only_follow(by_label["deliver(16)"][1])
    assert ev.following is True and ev.is_at_bottom is True

    # 2. Scroll up disengages follow — the event carries the disengagement.
    ev = only_follow(by_label["press(up)"][1])
    assert ev.following is False and ev.is_at_bottom is False

    # 3. Growth while scrolled up: hold place (offset fixed), below-count grows,
    #    and NO viewport event fires (not following → nothing viewport-relevant moved).
    assert by_label["deliver(40)"][1] == []  # held place → no event
    assert result["offset_after_grow"] == result["offset_scrolled"]  # place held
    assert result["below_after_grow"] > result["below_after_up"]  # the tail accrued below

    # 4. `end` re-engages follow at the new bottom.
    ev = only_follow(by_label["press(end)"][1])
    assert ev.following is True and ev.is_at_bottom is True

    # Through all of it: every event's observed == the frame the input landed on.
    for label, landed, evs in steps:
        for ev in evs:
            assert ev.observed == landed, f"{label}: observed drifted from the displayed frame"


def test_g_re_engages_follow_like_end(monkeypatch) -> None:
    """`G` is the tail key alongside `end` — same re-engage semantics, driven the
    same way through run_cli's stream path."""
    events: list[object] = []
    steps: list[tuple[str, list[object]]] = []
    box: dict[str, asyncio.Queue] = {}

    async def app_stream():
        q = box["feed"]
        while True:
            n = await q.get()
            if n is None:
                return
            yield n

    async def fake_run(self: StreamSurface) -> None:
        self._writer = Writer(io.StringIO())
        self._buf = Buffer(WIDTH, HEIGHT)
        self._prev = Buffer(WIDTH, HEIGHT)
        self.layout(WIDTH, HEIGHT)
        box["feed"] = asyncio.Queue()
        self._running = True
        consumer = asyncio.create_task(self._consume())

        async def wait_pending() -> None:
            for _ in range(10_000):
                if self._pending or not self._running:
                    return
                await asyncio.sleep(0)
            raise AssertionError("no delivery")

        def render_once() -> None:
            self._dirty = True
            with self._frame_scope():
                self.render()

        async def deliver(n: int) -> None:
            await box["feed"].put(n)
            await wait_pending()
            render_once()

        def press(key: str) -> None:
            prev = len(events)
            self.on_key(key)
            render_once()
            steps.append((f"press({key})", events[prev:]))

        await deliver(8)  # first display
        await deliver(20)  # a FollowChange (tracks bottom)
        press("home")  # jump to top, follow off
        press("G")  # re-engage the tail

        self._running = False
        await box["feed"].put(None)
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    rc = run_cli(
        ["--live"],
        renderer=lambda data, fidelity, width: _rows(int(data), width or WIDTH),
        fetch=lambda: 0,
        fetch_stream=app_stream,
        live_delivery="surface",
        on_host_event=events.append,
    )
    assert rc == 0

    by_label = {label: evs for label, evs in steps}
    home_evs = by_label["press(home)"]
    assert len(home_evs) == 1 and home_evs[0].following is False  # disengaged at the top
    g_evs = by_label["press(G)"]
    assert len(g_evs) == 1
    ev = g_evs[0]
    assert isinstance(ev, HostViewportEvent) and isinstance(ev.reason, FollowChange)
    assert ev.following is True and ev.is_at_bottom is True
