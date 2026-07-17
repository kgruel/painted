"""Surface — base class for buffer-rendered terminal applications."""

from __future__ import annotations

import os
import signal
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, ExitStack
from typing import TYPE_CHECKING, Any

from ..mouse import MouseEvent
from ..core.buffer import Buffer, CellWrite
from ..host import HostViewport
from ..keyboard import KeyboardInput
from .layer import Layer
from .layer import process_key as _process_key
from ..core.writer import ScrollOp, Writer

if TYPE_CHECKING:
    from ..core.block import Block
    from ..host import Hit

Emit = Callable[[str, dict[str, Any]], None]
LifecycleHook = Callable[[], Awaitable[None]]

# The content renderer the host rung drives: given the frame's current width and
# the height offer (``None`` on the omitted arm, the integer ``H`` on the offered
# arm — HOST_RUNG_DESIGN §2), return a content Block. The offer rule and the app
# renderer both live behind it; the Surface only supplies geometry.
HostRender = Callable[[int, "int | None"], "Block"]

# Minimum sleep: yields the event loop without measurably delaying the frame.
MIN_YIELD = 0.001


def frame_sleep(elapsed: float, fps_cap: int, *, active: bool) -> float:
    """Seconds to sleep after a frame, compensating for frame work already done.

    ``active`` (input flowing or a re-render already queued) yields minimally so
    the loop drains input at full speed. Otherwise sleep only the remainder of
    the frame period — the frame's own render time counts toward its period, so
    a slow render shortens the sleep instead of stretching the frame.
    """
    if active:
        return MIN_YIELD
    return max(MIN_YIELD, 1.0 / fps_cap - elapsed)


class Surface:
    """Base class for buffer-rendered applications.

    Subclasses override layout(), render(), and on_key() to build interactive
    terminal UIs using the cell-buffer rendering system.
    """

    def __init__(
        self,
        *,
        fps_cap: int = 60,
        enable_mouse: bool = False,
        mouse_all_motion: bool = False,
        scroll_optimization: bool | None = None,
        scroll_optimization_emit: bool = False,
        on_emit: Emit | None = None,
        on_start: LifecycleHook | None = None,
        on_stop: LifecycleHook | None = None,
        no_color: bool | None = None,
    ):
        # ``no_color`` threads a host's *already-resolved* NO_COLOR snapshot into
        # this Surface's writer (RENDERER_CONTRACT_DESIGN.md §9.1). A framework
        # host (``run_cli``) resolves the delivery's color policy once in
        # ``_host_scope`` and passes it here so ``_frame_scope``'s writer-derived
        # capability bracket *equals* that snapshot by construction — the frame
        # can never re-read the environment and split content choice from
        # serialization. ``None`` (a standalone Surface with no owning host) keeps
        # the writer resolving NO_COLOR from its own environment, unchanged.
        self._writer = Writer(no_color=no_color)
        self._fps_cap = fps_cap
        self._buf: Buffer | None = None
        self._prev: Buffer | None = None
        self._keyboard = KeyboardInput()
        self._running = False
        self._dirty = True
        self._needs_clear = False
        self._enable_mouse = enable_mouse
        self._mouse_all_motion = mouse_all_motion
        if scroll_optimization is None:
            env = os.environ.get("PAINTED_SCROLL_OPTIM", "").strip().lower()
            scroll_optimization = env in {"1", "true", "yes", "on"}
        self._scroll_optimization = bool(scroll_optimization)
        self._scroll_optimization_emit = scroll_optimization_emit
        self._on_emit = on_emit
        self._on_start = on_start
        self._on_stop = on_stop

    async def run(self) -> None:
        """Enter alt screen, run main loop, restore terminal on exit."""
        # Deferred: asyncio is ~55% of this module's import cost, and only the
        # running loop needs it — importing Surface (e.g. via painted.tui or
        # TestSurface) shouldn't pay for it.
        import asyncio

        self._running = True
        # Everything from enter_alt_screen on is inside the try: sizing, user
        # layout(), and signal-handler setup can all raise, and the terminal
        # must be restored even when setup fails.
        sigwinch_installed = False
        loop = None
        try:
            self._writer.enter_alt_screen()
            self._writer.hide_cursor()
            if self._enable_mouse:
                self._writer.enable_mouse(all_motion=self._mouse_all_motion)

            # Initial sizing
            width, height = self._writer.size()
            self._buf = Buffer(width, height)
            self._prev = Buffer(width, height)
            self.layout(width, height)

            # Handle terminal resize
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGWINCH, self._on_resize)
            sigwinch_installed = True

            with self._keyboard:
                if self._on_start is not None:
                    await self._on_start()

                while self._running:
                    frame_start = loop.time()
                    # Drain all available input before rendering
                    had_input = False
                    while True:
                        inp = self._keyboard.get_input()
                        if inp is None:
                            break
                        if isinstance(inp, MouseEvent):
                            self.on_mouse(inp)
                            self.emit(
                                "ui.mouse",
                                action=inp.action.name,
                                button=inp.button.name,
                                x=inp.x,
                                y=inp.y,
                                shift=inp.shift,
                                meta=inp.meta,
                                ctrl=inp.ctrl,
                            )
                        else:
                            self.on_key(inp)
                            self.emit("ui.key", key=inp)
                        self._dirty = True
                        had_input = True

                    # Advance state (animations, timers)
                    self.update()

                    # Render if dirty
                    if self._dirty:
                        self._dirty = False
                        with self._frame_scope():
                            self.render()
                            self._flush()

                    # Adaptive sleep: short yield when input is flowing, else the
                    # REMAINDER of the frame period — sleeping the full period after
                    # a blocking render compounds to render_time + period per frame
                    # (a 30fps cap delivered ~23fps before compensation).
                    elapsed = loop.time() - frame_start
                    await asyncio.sleep(
                        frame_sleep(elapsed, self._fps_cap, active=had_input or self._dirty)
                    )
        finally:
            if self._on_stop is not None:
                await self._on_stop()
            if sigwinch_installed and loop is not None:
                loop.remove_signal_handler(signal.SIGWINCH)
            if self._enable_mouse:
                self._writer.disable_mouse()
            self._writer.show_cursor()
            self._writer.exit_alt_screen()

    def layout(self, width: int, height: int) -> None:
        """Called on resize. Override to recalculate regions."""

    def update(self) -> None:
        """Called every iteration. Override to advance animations/timers.

        Call mark_dirty() if state changed and a re-render is needed.
        """

    def render(self) -> None:
        """Called each frame when dirty. Override to paint into self._buf."""

    def _frame_scope(self) -> AbstractContextManager[Any]:
        """Context manager entered before ``render()``, exited after
        ``_flush()`` — one bracket per dirty frame.

        The framework Surface owns the terminal, so it resolves and installs the
        **capability bracket** here (docs/RENDERER_CONTRACT_DESIGN.md §9.3 Surface
        row): the scope spans ``render()`` through the ``_flush()`` serialization,
        in the task that owns the loop, with guaranteed release on success,
        exception, cancellation, resize, and quit — ordinary ``with`` semantics.
        The facets come from the Surface's *own writer* (the single snapshot the
        facets and that writer's serialization share, §9.1): the alt screen
        establishes ANSI *control* only, so ``color`` still consults NO_COLOR +
        depth, ``glyph`` the encoding, ``link`` the writer's hyperlink config —
        alt-screen operation alone implies none of them. The §9.4 pairing folds in:
        a ``glyph=False`` frame also installs an ASCII-safe ``IconSet``.

        Subclasses that override this **must compose** it — ``StreamSurface`` adds
        the declared ``ref_schemes=`` for the frame's state (§7) on top of the
        capability bracket via ``super()._frame_scope()``.
        """
        from ..capabilities import resolve_surface_capabilities, use_capabilities
        from ..core.writer import ColorDepth

        w = self._writer
        caps = resolve_surface_capabilities(
            w.stream,
            no_color=w.no_color,
            depth_is_none=w.detect_color_depth() is ColorDepth.NONE,
            hyperlinks=w.hyperlinks,
        )
        stack = ExitStack()
        stack.enter_context(use_capabilities(caps))
        if not caps.glyph:
            from ..icon_set import ASCII_ICONS, use_icons

            stack.enter_context(use_icons(ASCII_ICONS))
        return stack

    def on_key(self, key: str) -> None:
        """Called on keypress. Override to dispatch to focused component."""

    def on_mouse(self, event: MouseEvent) -> None:
        """Called on mouse event. Override to handle clicks, drags, scrolls."""

    def hit(self, x: int, y: int) -> str | None:
        """Return the semantic ref at a screen coordinate, if any.

        Useful for mapping MouseEvent coordinates to rendered regions.
        """
        if self._buf is None:
            return None
        return self._buf.hit(x, y)

    def emit(self, kind: str, **data: Any) -> None:
        """Emit an observation. No-op if no callback registered."""
        if self._on_emit is not None:
            self._on_emit(kind, data)

    def handle_key(
        self,
        key: str,
        state: Any,
        get_layers: Callable[[Any], tuple[Layer, ...]],
        set_layers: Callable[[Any, tuple[Layer, ...]], Any],
    ) -> tuple[Any, bool, Any]:
        """Delegate to process_key() and auto-emit an action fact.

        Returns the same (new_state, should_quit, pop_result) tuple as
        process_key().  After processing, emits one of:
          - ui.action action="quit"   when should_quit is True
          - ui.action action="pop"    when pop_result is not None
          - ui.action action="stay"   otherwise
        """
        new_state, should_quit, pop_result = _process_key(
            key,
            state,
            get_layers,
            set_layers,
        )
        if should_quit:
            self.emit("ui.action", action="quit")
        elif pop_result is not None:
            self.emit("ui.action", action="pop", result=str(pop_result))
        else:
            self.emit("ui.action", action="stay")
        return new_state, should_quit, pop_result

    def mark_dirty(self) -> None:
        """Mark the display as needing a re-render."""
        self._dirty = True

    def quit(self) -> None:
        """Signal the run loop to exit."""
        self._running = False

    def _on_resize(self) -> None:
        """Handle SIGWINCH: resize buffers and recalculate layout."""
        width, height = self._writer.size()
        self._resize(width, height)

    def _resize(self, width: int, height: int) -> None:
        """Apply a resize event (buffer + layout + clear-on-next-flush)."""
        self._needs_clear = True
        self._buf = Buffer(width, height)
        self._prev = Buffer(width, height)
        self.layout(width, height)
        self._dirty = True
        self.emit("ui.resize", width=width, height=height)

    def _flush(self) -> None:
        """Diff current vs previous buffer and write changes to terminal."""
        if self._buf is None or self._prev is None:
            return

        needs_clear = self._needs_clear
        self._needs_clear = False

        if not needs_clear and self._scroll_optimization and self._try_flush_scroll_optimized():
            self._prev = self._buf.clone()
            return

        writes = self._buf.diff(self._prev)
        if writes or needs_clear:
            self._writer.write_frame(writes, clear_first=needs_clear)
        # Swap: current becomes previous for next frame
        self._prev = self._buf.clone()

    def _try_flush_scroll_optimized(self) -> bool:
        if self._buf is None or self._prev is None:
            return False

        cur = self._buf
        prev = self._prev
        if cur.width != prev.width or cur.height != prev.height:
            return False

        width, height = cur.width, cur.height
        if height < 3 or width < 1:
            return False

        max_n = min(3, height - 1)
        if max_n <= 0:
            return False

        old_content = prev.line_hashes(include_style=False)
        new_content = cur.line_hashes(include_style=False)
        old_full = prev.line_hashes(include_style=True)
        new_full = cur.line_hashes(include_style=True)

        cand = self._detect_vertical_scroll(old_content, new_content, max_n=max_n)
        if cand is None:
            return False
        top, bottom, n, overlap_start, overlap_end, match_ratio = cand

        region_height = bottom - top + 1
        if region_height < 6:
            return False

        repaint_lines: set[int] = set()

        # Inserted lines created by the scroll.
        if n > 0:
            for y in range(bottom - n + 1, bottom + 1):
                repaint_lines.add(y)
        else:
            m = -n
            for y in range(top, top + m):
                repaint_lines.add(y)

        # Overlap region: if the scrolled-in line differs (including style), repaint.
        for y in range(overlap_start, overlap_end + 1):
            if new_full[y] != old_full[y + n]:
                repaint_lines.add(y)

        # Outside region: repaint changed lines.
        for y in range(0, top):
            if new_full[y] != old_full[y]:
                repaint_lines.add(y)
        for y in range(bottom + 1, height):
            if new_full[y] != old_full[y]:
                repaint_lines.add(y)

        repaint_in_region = sum(1 for y in repaint_lines if top <= y <= bottom)
        if repaint_in_region >= int(region_height * 0.7):
            return False

        cell_ops: list[ScrollOp | CellWrite] = [ScrollOp(top=top, bottom=bottom, n=n)]
        cells = cur._cells
        refs = cur._refs
        for y in sorted(repaint_lines):
            row_start = y * width
            for x in range(width):
                idx = row_start + x
                cell_ops.append(
                    CellWrite(x, y, cells[idx], refs[idx] if refs is not None else None)
                )

        self._writer.write_ops(cell_ops)

        if self._scroll_optimization_emit:
            self.emit(
                "ui.scroll_optim",
                top=top,
                bottom=bottom,
                n=n,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                match_ratio=match_ratio,
                repainted_lines=len(repaint_lines),
            )

        return True

    @staticmethod
    def _detect_vertical_scroll(
        old_hashes: list[int],
        new_hashes: list[int],
        *,
        max_n: int,
        min_overlap: int = 6,
        min_match_ratio: float = 0.8,
    ) -> tuple[int, int, int, int, int, float] | None:
        """Detect a vertical scroll region.

        Returns (top, bottom, n, overlap_start, overlap_end, match_ratio) where
        n>0 scrolls up and overlap_start..overlap_end are the new-buffer lines
        that are expected to match old[y+n].
        """
        height = len(new_hashes)
        if height != len(old_hashes):
            return None

        best: tuple[int, float, int, int, int, int, int, int] | None = None
        # tuple: (match_count, match_ratio, -mismatch_count, overlap_len, -abs(n), top, bottom, n)

        for step in range(1, max_n + 1):
            for n in (step, -step):
                y0 = max(0, -n)
                y1 = min(height - 1, height - 1 - n)
                if y1 - y0 + 1 < min_overlap:
                    continue

                for a in range(y0, y1 + 1):
                    matches = 0
                    distinct: set[int] = set()
                    for b in range(a, y1 + 1):
                        if new_hashes[b] == old_hashes[b + n]:
                            matches += 1
                        distinct.add(new_hashes[b])

                        overlap_len = b - a + 1
                        if overlap_len < min_overlap:
                            continue

                        ratio = matches / overlap_len
                        if ratio < min_match_ratio:
                            continue

                        if len(distinct) < max(3, overlap_len // 3):
                            continue

                        if n > 0:
                            top = a
                            bottom = b + n
                            overlap_start = a
                            overlap_end = b
                        else:
                            top = a + n
                            bottom = b
                            overlap_start = a
                            overlap_end = b

                        if top < 0 or bottom >= height or top >= bottom:
                            continue

                        mismatches = overlap_len - matches
                        key = (matches, ratio, -mismatches, overlap_len, -abs(n), top, bottom, n)
                        if best is None or key > best:
                            best = key

        if best is None:
            return None

        _, ratio, _, overlap_len, _, top, bottom, n = best
        abs_n = abs(n)
        overlap_start = top if n > 0 else top + abs_n
        overlap_end = bottom - abs_n if n > 0 else bottom
        if overlap_end - overlap_start + 1 != overlap_len:
            overlap_start = max(0, overlap_start)
            overlap_end = min(height - 1, overlap_end)
        return (top, bottom, n, overlap_start, overlap_end, ratio)


class HostSurface(Surface):
    """The host rung wired to a ``Surface`` — a semantic renderer's Block
    delivered interactively (HOST_RUNG_DESIGN §6).

    The fourth delivery of the dual allocation contract, beside ``print_block``
    (STATIC), ``InPlaceRenderer`` / ``StreamSurface`` (LIVE): a renderer that
    travels the other three rungs unchanged now also drives an alt-screen TUI,
    with no hand-rolled viewport/scroll/evidence glue (RENDER_MODEL law 7). It is
    an *addition* — direct-``Buffer`` ``Surface`` apps remain fully supported (§1).

    Two arms, chosen by ``accepts_height`` — the binding's standing **acceptance**
    fact (§3), never inspected per frame:

      * **omitted arm** (``accepts_height=False`` — ``renderer=`` / ``render=`` /
        the transcription default): the *host* owns the viewport. The renderer is
        offered natural sizing (``render(width, None)``) once per width, and a
        ``ViewportAdapter`` (root ``painted.host``) slices that natural-height
        Block into the frame, routes scroll keys, tracks follow / at-bottom
        intent, and marks omitted rows with the reserved evidence row. A
        **height-only resize re-slices with no renderer call** (§6 matrix); a
        width change re-renders and reconciles the anchor.
      * **offered arm** (``accepts_height=True`` — ``height_renderer=``): the
        *renderer* owns the frame. The host offers ``height=H`` — the full frame
        height, since it draws no chrome and so subtracts none (§5) — verifies the
        returned Block is exactly ``H`` rows (a loud ``ContractError`` otherwise,
        never a crop or pad), and paints it. Internal chrome and body scroll are
        the renderer's business (the hybrid shape, §6); the host treats the Block
        as opaque and routes it no scroll keys.

    ``render`` is ``(width, height) -> Block``. ``run_cli`` passes a closure over
    its binding and the width-offer rule; a direct consumer passes any such
    callable. ``content_id`` / ``inputs`` are the adapter's ``RenderKey`` identity
    (§6): ``content_id`` is "the same document" (a constant across a single-fetch
    session, so a resize never resets scroll), ``inputs`` the opaque
    renderer-input token (fidelity, capabilities…) — width is tracked separately
    because it is the re-render-and-reconcile trigger.

    Both arms delegate the omitted-arm machinery to the shared ``HostViewport``
    controller (``_vp``), which ``StreamSurface`` composes too (S5): scroll/wheel
    routing, frame production, the event-order discipline, and the inward
    ``on_host_event=`` seam (§7) all live there rather than being forked. The
    offered arm builds no controller — the renderer owns the frame, so the host
    holds no viewport and the sink fires zero times.

    The **event-order discipline** (§6): the controller retains the last
    *displayed* frame's token (set only when a frame is produced, never in
    ``layout()``), and an incoming mouse event resolves against exactly that
    token. A resize between paint and a queued event mints new geometry while the
    retained token still names the displayed frame, so the event resolves stale
    and is dropped — never translated through the new geometry.
    """

    def __init__(
        self,
        *,
        render: HostRender,
        accepts_height: bool = False,
        content_id: Any = None,
        inputs: Any = None,
        evidence_label: str | None = None,
        quit_keys: tuple[str, ...] = ("q", "escape"),
        fps_cap: int = 60,
        on_emit: Emit | None = None,
        on_host_event: Any = None,  # HostEventSink | None (§7)
        no_color: bool | None = None,
    ) -> None:
        # Mouse is enabled only for the omitted arm — it is the only arm the host
        # hit-tests (the offered arm's renderer owns its own regions). ``no_color``
        # threads the delivery's resolved snapshot to the writer (RENDERER_CONTRACT
        # §9.1), exactly as StreamSurface does.
        super().__init__(
            fps_cap=fps_cap,
            enable_mouse=not accepts_height,
            on_emit=on_emit,
            no_color=no_color,
        )
        self._render_frame = render
        self._accepts_height = accepts_height
        self._content_id = content_id
        self._inputs = inputs
        self._evidence_label = evidence_label
        self._quit_keys = frozenset(quit_keys)
        # The inward host-event sink (§7): host viewing-state reaching the app as
        # input. On the *host* constructor, never on the renderer binding — the
        # semantic renderer stays unchanged across the four rungs. On the offered
        # arm (accepts_height) the host owns no viewport, so no controller is
        # built and the sink receives zero calls (honest event-source silence).
        self._on_host_event = on_host_event

        # Omitted arm: the shared viewport controller (adapter + last token +
        # routing + event minting). ``None`` on the offered arm and until the
        # first ``layout`` mounts it.
        self._vp: HostViewport | None = None
        # Current geometry, set on every layout() — read by the offered arm.
        self._width = 0
        self._height = 0
        # Resolved hits, newest last — the *outward* observability seam a host
        # consumer / test reads (``host.hit`` emissions). The inward
        # ``HostHitEvent`` rides ``on_host_event`` alongside it; ``emit`` stays
        # outward-only (§7).
        self.hits: list[Hit] = []

    # --- Geometry: the resize matrix, decided by the adapter (§6) --------------

    def layout(self, width: int, height: int) -> None:
        """Mount on init, re-plan on every resize (SIGWINCH lands here via
        ``_resize``).

        Offered arm: nothing to plan — ``render()`` re-invokes the renderer with
        the new ``H`` each dirty frame. Omitted arm: the first ``layout`` **mounts**
        the controller (installs content, no event — no synthetic mount event, §7);
        every later ``layout`` is a resize (``layout`` re-runs only via ``_resize``),
        so it applies the §6 matrix and mints one ``ResizeChange`` — a width change
        re-renders and reconciles the anchor, a height-only change **re-slices with
        no renderer call**.
        """
        self._width = width
        self._height = height
        if self._accepts_height:
            return

        from ..host import ResizeChange

        # The natural render runs *here*, in layout() — outside the run loop's
        # per-frame bracket — so it must install the Surface's capability / icon
        # bracket itself (RENDERER_CONTRACT §9.3). The offered arm needs no
        # equivalent: its render is in render(), already inside _frame_scope.
        with self._frame_scope():
            if self._vp is None:
                self._vp = HostViewport(
                    content_id=self._content_id,
                    on_event=self._on_host_event,
                    evidence_label=self._evidence_label,
                )
                self._vp.set_geometry(width, height)
                self._vp.install(self._render_frame(width, None), reason=None)
                return
            width_changed = self._vp.set_geometry(width, height)
            if width_changed:
                self._vp.install(self._render_frame(width, None), reason=ResizeChange())
            else:  # height-only: re-slice, no renderer call
                self._vp.reslice(reason=ResizeChange())

    # --- Frame production ------------------------------------------------------

    def render(self) -> None:
        buf = self._buf
        if buf is None:
            return
        if self._accepts_height:
            self._render_offered(buf)
        else:
            self._render_omitted(buf)

    def _render_offered(self, buf: Buffer) -> None:
        """Offer ``height=H`` (the full frame — no host chrome), verify exactness,
        paint. The renderer owns the frame; the host holds no viewport token."""
        h = self._height
        block = self._render_frame(self._width, h)
        if block.height != h:
            from ..core.errors import ContractError

            raise ContractError(
                f"height-aware renderer returned {block.height} rows for an offer of "
                f"{h} (the offered arm must return exactly H rows; the host does not "
                "crop or pad into compliance — HOST_RUNG_DESIGN §5)"
            )
        block.paint(buf, 0, 0)

    def _render_omitted(self, buf: Buffer) -> None:
        """Assemble the controller's frame and paint it. The controller retains
        its token as the hit-test anchor for the *displayed* frame (§6)."""
        if self._vp is None:
            return
        self._vp.frame().block.paint(buf, 0, 0)

    # --- Input routing (through the shared controller) -------------------------

    def on_key(self, key: str) -> None:
        if key in self._quit_keys:
            if self._vp is not None:  # omitted arm only — offered arm fires nothing
                self._vp.route_quit()
            self.quit()
            return
        if self._accepts_height or self._vp is None:
            return  # the renderer owns internal scroll on the offered arm (§6)
        if self._vp.route_key(key):
            self.mark_dirty()

    def on_mouse(self, event: MouseEvent) -> None:
        if self._accepts_height or self._vp is None:
            return
        if event.is_scroll:
            # The controller maps the wheel button to a vertical delta (a
            # horizontal wheel is not the vertical viewport's) and mints the event.
            if self._vp.route_wheel(event.button):
                self.mark_dirty()
            return
        # A click resolves against the LAST DISPLAYED frame's token (§6): the
        # controller drops a stale event (a resize mutated geometry after paint)
        # rather than translating it through the new geometry. It mints the inward
        # ``HostHitEvent``; here we also record the outward ``host.hit``.
        hit = self._vp.route_click(event.x, event.y)
        if hit is None:
            return
        self.hits.append(hit)
        self.emit(
            "host.hit",
            region=hit.region.name,
            ref=hit.ref,
            content_xy=hit.content_xy,
            stale=hit.stale,
        )
