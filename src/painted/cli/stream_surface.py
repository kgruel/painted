"""StreamSurface — alt-screen delivery for sustained live streams.

The 'surface' tier of the two-tier live contract (see
``docs/LIVE_DELIVERY_DESIGN.md``). Where ``InPlaceRenderer`` delivers
ephemeral liveness into the scrollback via relative cursor walks,
``StreamSurface`` delivers sustained animation onto its own alt screen via
absolute per-cell diffs — structurally immune to the scroll-tearing that
relative addressing suffers when the viewport moves.

It hosts the app's ``fetch_stream()`` as a task alongside the ``Surface``
render loop: each yielded state is stored and triggers a repaint of
``render(ctx, state)`` at (0, 0). The *stream* paces state (it already
sleeps); ``fps_cap`` only bounds repaint. The final frame is deposited to
the normal screen by the caller (``CliRunner._run_live``) after the alt
screen is torn down — smoothness of the alt screen, scrollback persistence
of in-place.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Generic, TypeVar

from ..core.cell import Style
from ..tui.surface import Surface
from .live_meter import LiveMeter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from ..core.block import Block
    from .types import CliContext

T = TypeVar("T")

# Poll interval while paused — how fast resume is noticed. Cheap; not a frame rate.
_PAUSE_POLL = 0.05


class StreamSurface(Surface, Generic[T]):
    """Generic stream-consuming Surface. Private to the cli package.

    Keys: ``q`` / ctrl-c quit; ``space`` pauses (stops consuming the
    iterator — nearly free). On exit (stream exhausted, quit, or error) the
    last state is left in ``last_state`` / any failure in ``error`` for the
    caller to deposit and translate to an exit code.
    """

    def __init__(
        self,
        *,
        ctx: CliContext,
        render: Callable[[CliContext, T], Block],
        fetch_stream: Callable[[], AsyncIterator[T]],
        fps_cap: int = 60,
    ) -> None:
        super().__init__(fps_cap=fps_cap, on_start=self._spawn, on_stop=self._stop)
        self._ctx = ctx
        self._render = render
        self._fetch_stream = fetch_stream
        self._state: T | None = None
        self._paused = False
        self._consumer: asyncio.Task[None] | None = None
        self._agen: AsyncIterator[T] | None = None

        # Outcome, read by the caller after the alt screen is torn down.
        self.last_state: T | None = None
        self.error: Exception | None = None
        self.error_kind: str | None = None  # "fetch" | "render"

        # Delivery gauge: only this side of the decoupling can measure
        # render+write cost — the stream's yield boundary reads ~0 here.
        self.meter = LiveMeter()

    # --- Stream hosting (lifecycle hooks fire inside Surface.run) ---

    async def _spawn(self) -> None:
        """Spawn the consumer once the loop is live (_running is True)."""
        self._consumer = asyncio.get_running_loop().create_task(self._consume())

    async def _stop(self) -> None:
        """Cancel the consumer and close the generator from the main task.

        Closing the async generator here (not inside the cancelled consumer)
        sidesteps await-during-cancellation hazards: this runs in the
        uncancelled main task.
        """
        if self._consumer is not None and not self._consumer.done():
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer
        aclose = getattr(self._agen, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()

    async def _consume(self) -> None:
        self._agen = self._fetch_stream()
        try:
            while self._running:
                if self._paused:
                    await asyncio.sleep(_PAUSE_POLL)
                    continue
                try:
                    state = await self._agen.__anext__()
                except StopAsyncIteration:
                    break
                self._state = state
                self.last_state = state
                self.mark_dirty()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the stream raised
            self.error = exc
            self.error_kind = "fetch"
        finally:
            # Stream exhausted or failed → leave the loop so the deposit runs.
            self.quit()

    # --- Surface overrides ---

    def render(self) -> None:
        if self._buf is None:
            return
        self._buf.fill(0, 0, self._buf.width, self._buf.height, " ", Style())
        if self._state is None:
            return
        self.meter.start()
        try:
            block = self._render(self._ctx, self._state)
        except Exception as exc:
            self.error = exc
            self.error_kind = "render"
            self.quit()
            return
        self.meter.dress(block).paint(self._buf, 0, 0)

    def _flush(self) -> None:
        # The loop runs render() then _flush(); stopping here closes the
        # start() opened in render(), so the sample spans paint+diff+write.
        super()._flush()
        self.meter.stop()

    def on_key(self, key: str) -> None:
        if key in ("q", "\x03"):
            self.quit()
        elif key == " ":
            self._paused = not self._paused
