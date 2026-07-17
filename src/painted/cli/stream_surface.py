"""StreamSurface — alt-screen delivery for sustained live streams.

The 'surface' tier of the two-tier live contract (see
``docs/LIVE_DELIVERY_DESIGN.md``). Where ``InPlaceRenderer`` delivers
ephemeral liveness into the scrollback via relative cursor walks,
``StreamSurface`` delivers sustained animation onto its own alt screen via
absolute per-cell diffs — structurally immune to the scroll-tearing that
relative addressing suffers when the viewport moves.

It hosts the app's ``fetch_stream()`` as a task alongside the ``Surface``
render loop: each yielded state is stored and triggers a repaint of
``render(state, buffer_width)`` at (0, 0) — the render callback is a
runner-internal adapted closure that offers the buffer's *current* width
each frame (the renderer contract's per-frame offer, RENDERER_CONTRACT
§6), never a once-captured context width. The *stream* paces state (it already
sleeps); ``fps_cap`` only bounds repaint. The final frame is deposited to
the normal screen by the caller (``CliRunner._run_live``) after the alt
screen is torn down — smoothness of the alt screen, scrollback persistence
of in-place.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import AbstractContextManager, ExitStack
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from ..core.cell import Style
from ..tui.surface import HostSurface, Surface
from .live_meter import LiveMeter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from ..core.block import Block
    from ..refs import RefScheme
    from ..tui.surface import HostRender

T = TypeVar("T")

# Poll interval while paused — how fast resume is noticed. Cheap; not a frame rate.
_PAUSE_POLL = 0.05


class StreamSurface(Surface, Generic[T]):
    """Generic stream-consuming Surface. Private to the cli package.

    Keys: ``q`` / ctrl-c quit; ``space`` pauses (stops consuming the
    iterator — nearly free). On exit (stream exhausted, quit, or error) the
    last state is left in ``last_state`` / any failure in ``error`` for the
    caller to deposit and translate to an exit code.

    ``ref_schemes=`` evaluation (docs/RENDERER_CONTRACT_DESIGN.md §7): the
    resolver runs once per successful **fetch event**, eagerly, inside
    ``_consume()`` — never lazily at render time, and never keyed by state
    identity. A state that arrives twice (even the same mutated object) is
    evaluated on every fetch; a state that gets coalesced away before a frame
    ever renders was still evaluated, at its own fetch, so its callable's
    fault still surfaces instead of silently disappearing. The resolved
    ``(state, schemes)`` pair is carried as one atomic tuple into
    ``self._frame`` (the pair about to render) and ``self._last_frame`` (the
    pair for the caller's deposit) — the ContextVar itself is installed later,
    in ``_frame_scope()``, in the rendering task, since ContextVars set in the
    consumer task would never be visible there.
    """

    def __init__(
        self,
        *,
        render: Callable[[T, int], Block],
        fetch_stream: Callable[[], AsyncIterator[T]],
        fps_cap: int = 60,
        live_meter: bool = False,
        resolve_ref_schemes: Callable[[T], tuple[RefScheme, ...]] | None = None,
        no_color: bool | None = None,
    ) -> None:
        # ``no_color`` is the delivery's single resolved NO_COLOR snapshot,
        # threaded down to the Surface writer so this alt-screen frame's
        # capability bracket (``_frame_scope`` → ``resolve_surface_capabilities``,
        # which reads ``self._writer.no_color``) equals the host's outer bracket
        # by construction, never a second env read (§9.1). ``CliRunner`` passes
        # ``self._delivery_no_color`` here; a direct construction leaves it
        # ``None`` and the writer resolves NO_COLOR ambiently, like any Surface.
        super().__init__(
            fps_cap=fps_cap, on_start=self._spawn, on_stop=self._stop, no_color=no_color
        )
        # The render callback is a runner-adapted closure taking the frame's
        # current width (§6), not (ctx, state): the offer rule and the app
        # renderer both live behind it, so the surface only supplies geometry.
        self._render = render
        self._fetch_stream = fetch_stream
        # The runner-owned ref_schemes= resolver — (state) -> schemes, called
        # once per fetch event in _consume() (see class docstring). None when
        # the app declared no ref_schemes=.
        self._resolve_ref_schemes = resolve_ref_schemes
        # The current (state, schemes) pair, set together in _consume() —
        # None before the first fetch. render()/_frame_scope() both read this
        # single attribute, never a standalone `self._state`.
        self._frame: tuple[T, tuple[RefScheme, ...] | None] | None = None
        self._paused = False
        self._consumer: asyncio.Task[None] | None = None
        self._agen: AsyncIterator[T] | None = None

        # The pair for the most recently fetched state — read by the caller
        # (the deposit) after the alt screen is torn down, via the
        # `last_state`/`last_ref_schemes` properties below. Same atomicity
        # guarantee as `_frame`: one tuple, one write, never two attributes
        # that could advance independently.
        self._last_frame: tuple[T, tuple[RefScheme, ...] | None] | None = None
        self.error: Exception | None = None
        self.error_kind: str | None = None  # "fetch" | "render"

        # Delivery gauge (opt-in): only this side of the decoupling can
        # measure render+write cost — the stream's yield boundary reads ~0
        # here. The attribute always exists; the flag gates measurement and
        # dressing, so an opted-out run pays nothing.
        self.meter = LiveMeter()
        self._live_meter = live_meter

    @property
    def last_frame(self) -> tuple[T, tuple[RefScheme, ...] | None] | None:
        """The most recently fetched (state, schemes) pair — None only when
        nothing was ever fetched. This is the deposit's read: frame *presence*
        is this property being non-None, distinct from the state payload,
        which is unconstrained domain data and may itself legitimately be
        ``None`` (the transcription default renders it). The two views below
        conflate those cases and exist for convenience reads only.
        """
        return self._last_frame

    @property
    def last_state(self) -> T | None:
        """The most recently fetched state — None before the first fetch
        (and also when the fetched state itself was None; the deposit
        distinguishes via ``last_frame``)."""
        return None if self._last_frame is None else self._last_frame[0]

    @property
    def last_ref_schemes(self) -> tuple[RefScheme, ...] | None:
        """The ref_schemes= resolved for ``last_state``, at its own fetch
        (§7) — never re-evaluated at deposit. A read of the same atomic pair
        ``last_state`` reads, so the two can never desync. None when nothing
        was declared, or nothing has been fetched yet.
        """
        return None if self._last_frame is None else self._last_frame[1]

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
                # ref_schemes= evaluation (§7): eager, once per successful
                # fetch event — never lazily at render time, never keyed by
                # state identity. A state that gets coalesced away before a
                # frame ever renders was still evaluated here, at its own
                # fetch, so its callable's fault still surfaces instead of
                # silently disappearing; a repeated-identity fetch (the same
                # mutated object yielded twice) is evaluated on every fetch.
                # The ContextVar itself is NOT installed here — it belongs to
                # the rendering task (_frame_scope()); this only resolves and
                # validates the app's declaration, an app-code call that
                # needs no ambient state of its own.
                if self._resolve_ref_schemes is None:
                    schemes = None
                else:
                    try:
                        schemes = self._resolve_ref_schemes(state)
                    except Exception as exc:
                        # A declaration-time fault (§7), classified as a
                        # render-phase fault regardless of which task
                        # detected it — never this method's own "the stream
                        # raised" classification below.
                        self.error = exc
                        self.error_kind = "render"
                        self.quit()
                        return
                # One write, one atomic pair: state and its schemes can never
                # be observed independently — a reader sees both together or
                # neither (the `_frame`/`_last_frame` reads below).
                frame = (state, schemes)
                self._frame = frame
                self._last_frame = frame
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

    def _frame_scope(self) -> AbstractContextManager[Any]:
        """Compose the base capability bracket with this frame's ref_schemes= (§7, §9.3).

        ``super()._frame_scope()`` installs the Surface capability bracket (§9.3
        Surface row) for ``render()``/``_flush()``. On top of it, this installs the
        current frame's already-resolved ref schemes: evaluation happened once,
        eagerly, at the fetch event that produced ``self._frame`` (``_consume()``,
        above) — this method never calls the resolver, only installs the *result*
        as ambient state, in this task (the Surface's own render task). The
        ContextVar set here would never be visible from the consumer task that
        fetched the state, which is exactly why evaluation happens elsewhere and
        only the result travels.
        """
        stack = ExitStack()
        stack.enter_context(super()._frame_scope())
        if self._frame is not None:
            _, schemes = self._frame
            if schemes is not None:  # something declared
                from ..refs import use_refs

                stack.enter_context(use_refs(*schemes))
        return stack

    def render(self) -> None:
        if self._buf is None:
            return
        self._buf.fill(0, 0, self._buf.width, self._buf.height, " ", Style())
        if self.error is not None:
            return
        if self._frame is None:
            return
        state, _schemes = self._frame
        if self._live_meter:
            self.meter.start()
        try:
            # Offer the buffer's current width — a resize re-created _buf at the
            # new geometry, so this frame's offer tracks it (§6).
            block = self._render(state, self._buf.width)
        except Exception as exc:
            self.error = exc
            self.error_kind = "render"
            self.quit()
            return
        if self._live_meter:
            block = self.meter.dress(block)
        block.paint(self._buf, 0, 0)

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


def run_host_surface(
    *,
    render: HostRender,
    accepts_height: bool,
    content_id: object,
    inputs: object,
    evidence_label: str | None = None,
    no_color: bool | None = None,
    on_emit: Callable[[str, dict[str, object]], None] | None = None,
) -> int:
    """Mount a renderer binding into the interactive host rung and run it
    (HOST_RUNG_DESIGN §6 — the fourth delivery).

    The cli→tui seam for the host rung lives *here*, in the same file that already
    crosses to ``painted.tui.surface`` for ``StreamSurface`` — the architecture
    tripwire caps that crossing at the two existing seam files, so the runner
    reaches ``HostSurface`` through this cli-internal launcher rather than a third
    ``cli → tui`` import (``runner`` stays tui-free). The launcher is thin: it
    constructs the ``HostSurface`` from the runner's already-built render closure
    and runs the alt-screen loop, translating ``KeyboardInterrupt`` to a clean
    exit like every other delivery path. Exactness, the offer rule, and error
    routing all live behind ``render`` (the runner's ``_render``) and inside
    ``HostSurface``; nothing about them is re-implemented here.
    """
    import asyncio

    surface = HostSurface(
        render=render,
        accepts_height=accepts_height,
        content_id=content_id,
        inputs=inputs,
        evidence_label=evidence_label,
        no_color=no_color,
        on_emit=on_emit,
    )
    try:
        asyncio.run(surface.run())
    except KeyboardInterrupt:
        pass  # Ctrl-C is a clean interactive exit, like the live paths
    return 0
