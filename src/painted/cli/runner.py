"""CliRunner: the main CLI dispatch engine.

Connects argument parsing, context detection, and rendering into
a single entry point for CLI tools.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar

from contextlib import nullcontext

from .types import (
    CliContext,
    Fidelity,
    Format,
    OutputMode,
    Tag,
    Zoom,
    add_cli_args,
    detect_context,
    parse_fidelity,
    parse_format,
    parse_mode,
    parse_zoom,
)
from .help import HelpArg, help_doc, scan_help_args

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ..core.block import Block

T = TypeVar("T")  # State type
R = TypeVar("R")  # Return type


@dataclass
class CliRunner(Generic[T]):
    """CLI runner with sensible defaults and explicit overrides."""

    # Required: how to render state to Block
    render: Callable[[CliContext, T], Block]

    # Required: how to fetch state (sync)
    fetch: Callable[[], T]

    # Optional: streaming fetch for live mode
    fetch_stream: Callable[[], AsyncIterator[T]] | None = None

    # Optional: custom handlers for specific modes
    handlers: dict[OutputMode, Callable[[CliContext], R]] | None = None

    # Defaults
    default_zoom: Zoom = Zoom.SUMMARY
    default_mode: OutputMode = OutputMode.LIVE

    # Live delivery tier: "inplace" (scrollback liveness) or "surface"
    # (alt-screen sustained animation). See docs/LIVE_DELIVERY_DESIGN.md.
    live_delivery: str = "inplace"

    # Opt-in delivery gauge: dress live frames with a cost_meter row
    # (render+write vs the measured frame period). An author choice, like
    # live_delivery — it changes the output, so it is never implied.
    # Meters streaming frames only: without fetch_stream there is no frame
    # period to measure, so the flag has no effect.
    live_meter: bool = False

    # Optional: description for help
    description: str | None = None

    # Optional: program name
    prog: str | None = None

    # Optional: callback to add custom args
    add_args: Callable[[argparse.ArgumentParser], None] | None = None

    # Optional: describe pre-parsed args for help rendering
    help_args: list[HelpArg] | None = None

    # Disclosure declarations — each Tag generates a --{name} flag compiled
    # into fidelity.visible; depth_aliases are app-local depth spellings
    # ({"brief": 0} generates --brief). See docs/FIDELITY_DESIGN.md.
    tags: list[Tag] | None = None
    depth_aliases: dict[str, int] | None = None

    # Whether this app honors --max-chars/--max-lines. Opt-in: a flag exists
    # only because a capability was declared.
    budgets: bool = False

    # Optional: transform Fidelity after parsing — the escape hatch for
    # app-specific residue the grammar doesn't express. Runs last, after tag
    # compilation.
    build_fidelity: Callable[[argparse.Namespace, Fidelity], Fidelity] | None = None

    # Internal parser cache for repeated invocations
    _parser_cache: argparse.ArgumentParser | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        # Same promise as the declaration collision checks: misconfiguration
        # raises at construction, never degrades silently at dispatch.
        if self.live_delivery not in ("inplace", "surface"):
            raise ValueError(
                f"live_delivery must be 'inplace' or 'surface', got {self.live_delivery!r}"
            )

    def run(self, args: list[str]) -> int:
        """Parse args, resolve context, dispatch."""
        # Intercept --help before argparse
        if "-h" in args or "--help" in args:
            return self._handle_help(args)

        has_declarations = bool(self.tags) or bool(self.depth_aliases)
        if (
            not args
            and self.add_args is None
            and self.build_fidelity is None
            and not has_declarations
        ):
            zoom = self.default_zoom
            mode = OutputMode.AUTO
            fmt = Format.AUTO
            fidelity = Fidelity(depth=int(zoom))
        else:
            parser = self._get_parser()
            parsed = parser.parse_args(args)

            zoom = parse_zoom(parsed, self.default_zoom)
            mode = parse_mode(parsed)
            fmt = parse_format(parsed)
            fidelity = parse_fidelity(
                parsed, zoom, tags=self.tags, depth_aliases=self.depth_aliases
            )
            if self.build_fidelity is not None:
                fidelity = self.build_fidelity(parsed, fidelity)

        # JSON short-circuits — it's data export, not rendering
        is_json = fmt == Format.JSON
        if is_json:
            return self._export_json()

        force_plain = fmt == Format.PLAIN

        # Plain text and minimal depth imply static mode. Checked on the
        # compiled fidelity, not the -q flag, so a depth alias to 0 behaves
        # like -q (<= because a build_fidelity hook can hand back any int).
        if mode == OutputMode.AUTO and (force_plain or fidelity.depth <= int(Zoom.MINIMAL)):
            mode = OutputMode.STATIC

        ctx = detect_context(
            fidelity, mode, force_plain=force_plain, default_mode=self.default_mode
        )

        return self._dispatch(ctx)

    def _get_parser(self) -> argparse.ArgumentParser:
        """Build and cache the parser for repeated invocations."""
        if self._parser_cache is not None:
            return self._parser_cache

        parser = argparse.ArgumentParser(
            description=self.description,
            prog=self.prog,
            add_help=False,
        )
        # Re-add -h/--help so argparse still recognizes it for error messages
        parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)

        modes: set[OutputMode] = {OutputMode.STATIC}
        if self.fetch_stream is not None:
            modes.add(OutputMode.LIVE)
        # -i is available with a custom handler, or when surface delivery is
        # opted in — then INTERACTIVE falls through to the alt-screen live path,
        # converging -i and --live onto the same StreamSurface.
        if (self.handlers and OutputMode.INTERACTIVE in self.handlers) or (
            self.live_delivery == "surface" and self.fetch_stream is not None
        ):
            modes.add(OutputMode.INTERACTIVE)

        add_cli_args(
            parser,
            modes=modes,
            tags=self.tags,
            depth_aliases=self.depth_aliases,
            budgets=self.budgets,
        )

        if self.add_args is not None:
            framework_actions = len(parser._actions)
            self.add_args(parser)
            self._check_add_args_dests(parser._actions[framework_actions:])

        self._parser_cache = parser
        return parser

    def _check_add_args_dests(self, added: list[argparse.Action]) -> None:
        """Custom args must not land on a declared tag/alias dest.

        argparse raises only on duplicate option strings, not duplicate
        dests — a custom arg (or positional) whose dest matches a declared
        name would silently turn the tag on or override depth at compile
        time. Same promise as the name collision check, extended to the
        escape hatch.
        """
        from .types import declared_dests

        declared = declared_dests(self.tags, self.depth_aliases)
        if not declared:
            return
        for action in added:
            if action.dest in declared:
                raise ValueError(
                    f"add_args registers dest {action.dest!r}, which collides "
                    "with a declared tag or depth alias"
                )

    def _handle_help(self, args: list[str]) -> int:
        """Render zoom-aware help and return 0."""
        # Build the parser for its validation side effects — a broken
        # declaration must raise on the help path too, not render the
        # contradiction it would refuse to parse.
        self._get_parser()
        zoom, fmt = scan_help_args(args, depth_aliases=self.depth_aliases)
        doc = help_doc(self)

        if fmt == Format.JSON:
            print(json.dumps(asdict(doc), default=str))
            return 0

        use_ansi = fmt != Format.PLAIN
        if fmt == Format.AUTO:
            use_ansi = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

        from ..core.fidelity import Fidelity
        from ..core.writer import print_block
        from ..core.doc import doc_lens

        width = shutil.get_terminal_size().columns
        block = doc_lens(doc, fidelity=Fidelity(depth=int(zoom)), width=width)
        print_block(block, use_ansi=use_ansi)
        return 0

    def _export_json(self) -> int:
        """Export data as JSON — bypasses render pipeline entirely.

        Dataclass state is exported via ``asdict``; anything else is handed
        to ``json.dumps`` directly. Values JSON can't encode are coerced with
        ``str()`` (``default=str``) rather than erroring — export is
        best-effort by contract, so a non-JSON-clean field yields its repr,
        not a failure.
        """
        try:
            state = self.fetch()
        except Exception as exc:
            message = self._exception_message(exc)
            print(json.dumps({"error": message}))
            return 1
        try:
            data = asdict(state)  # type: ignore[arg-type]  # T may be dataclass
        except TypeError:
            data = state
        print(json.dumps(data, default=str))
        return 0

    @staticmethod
    def _icon_scope(ctx: CliContext):
        """Scoped ASCII icon override for plain output — restored on exit."""
        if not ctx.use_ansi:
            from ..icon_set import ASCII_ICONS, use_icons

            return use_icons(ASCII_ICONS)
        return nullcontext()

    def _dispatch(self, ctx: CliContext) -> int:
        """Dispatch to appropriate output mechanism."""
        with self._icon_scope(ctx):
            # Check for custom handler
            if self.handlers and ctx.mode in self.handlers:
                result = self.handlers[ctx.mode](ctx)
                return result if isinstance(result, int) else 0

            # Dispatch by mode
            if ctx.mode == OutputMode.STATIC:
                return self._run_static(ctx)

            elif ctx.mode == OutputMode.LIVE:
                return self._run_live(ctx)

            elif ctx.mode == OutputMode.INTERACTIVE:
                # Falls back to LIVE if no custom handler
                return self._run_live(ctx)

            return 0

    def _run_static(self, ctx: CliContext) -> int:
        """Run with static output (print_block)."""
        from ..core.writer import print_block

        try:
            state = self.fetch()
        except Exception as exc:
            block = self._fetch_error_block(ctx, exc)
            print_block(block, use_ansi=ctx.use_ansi)
            return 1

        try:
            block = self.render(ctx, state)
        except Exception as exc:
            block = self._render_error_block(ctx, exc)
            print_block(block, use_ansi=ctx.use_ansi)
            return 2

        print_block(block, use_ansi=ctx.use_ansi)
        return 0

    def _run_live(self, ctx: CliContext) -> int:
        """Run with InPlaceRenderer."""
        import asyncio

        from ..inplace import InPlaceRenderer
        from ..core.writer import print_block

        if self.fetch_stream is not None:
            # Alt-screen delivery for sustained streams — only on a real TTY
            # (it takes the terminal over). Pipes / forced-plain fall through
            # to the in-place path's non-TTY branch below.
            if self.live_delivery == "surface" and ctx.is_tty and ctx.use_ansi:
                return self._run_live_surface(ctx)

            # Streaming mode: update as data arrives
            async def stream() -> int:
                if not ctx.use_ansi:
                    from ..core.writer import print_block

                    last_block = None
                    try:
                        async for state in self.fetch_stream():  # type: ignore[misc]
                            try:
                                last_block = self.render(ctx, state)
                            except Exception as exc:
                                print_block(self._render_error_block(ctx, exc), use_ansi=False)
                                return 2
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        return 0
                    except Exception as exc:
                        print_block(self._fetch_error_block(ctx, exc), use_ansi=False)
                        return 1
                    if last_block is not None:
                        print_block(last_block, use_ansi=False)
                    return 0

                meter = None
                if self.live_meter:
                    from .live_meter import LiveMeter

                    meter = LiveMeter()
                with InPlaceRenderer() as renderer:
                    try:
                        async for state in self.fetch_stream():  # type: ignore[misc]
                            if meter is not None:
                                meter.start()
                            try:
                                block = self.render(ctx, state)
                            except Exception as exc:
                                renderer.render(self._render_error_block(ctx, exc))
                                renderer.finalize()
                                return 2
                            if meter is not None:
                                block = meter.dress(block)
                            renderer.render(block)
                            if meter is not None:
                                meter.stop()
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        renderer.finalize()
                        return 0
                    except Exception as exc:
                        renderer.render(self._fetch_error_block(ctx, exc))
                        renderer.finalize()
                        return 1
                    # Keep final output visible
                    renderer.finalize()
                    return 0

            try:
                return asyncio.run(stream())
            except KeyboardInterrupt:
                return 0

        # No streaming: just fetch and render
        try:
            state = self.fetch()
        except Exception as exc:
            block = self._fetch_error_block(ctx, exc)
            print_block(block, use_ansi=ctx.use_ansi)
            return 1

        try:
            block = self.render(ctx, state)
        except Exception as exc:
            block = self._render_error_block(ctx, exc)
            print_block(block, use_ansi=ctx.use_ansi)
            return 2

        print_block(block, use_ansi=ctx.use_ansi)
        return 0

    def _run_live_surface(self, ctx: CliContext) -> int:
        """Stream onto an alt screen, then deposit the final frame.

        The StreamSurface owns the alt-screen render loop; once it tears the
        alt screen down, we deposit the last frame (or the failure) to the
        normal screen at the current zoom and width — the scrollback half of
        the two-tier contract.
        """
        import asyncio

        from ..core.writer import print_block
        from .stream_surface import StreamSurface

        assert self.fetch_stream is not None  # guarded by the caller
        surface = StreamSurface(
            ctx=ctx,
            render=self.render,
            fetch_stream=self.fetch_stream,
            live_meter=self.live_meter,
        )
        try:
            asyncio.run(surface.run())
        except KeyboardInterrupt:
            pass  # final frame still deposited below
        except Exception as exc:
            # User fetch/render failures are captured in surface.error; what
            # reaches here is a delivery failure (terminal setup, sizing).
            # Surface.run has already restored the terminal — translate to the
            # documented exit-code contract instead of leaking a traceback.
            print(self._exception_message(exc), file=sys.stderr)
            return 1

        if surface.error is not None:
            if surface.error_kind == "render":
                print_block(self._render_error_block(ctx, surface.error), use_ansi=ctx.use_ansi)
                return 2
            print_block(self._fetch_error_block(ctx, surface.error), use_ansi=ctx.use_ansi)
            return 1

        if surface.last_state is not None:
            try:
                block = self.render(ctx, surface.last_state)
            except Exception as exc:
                print_block(self._render_error_block(ctx, exc), use_ansi=ctx.use_ansi)
                return 2
            if self.live_meter:
                # The deposit carries the run's final gauge — what this show cost.
                block = surface.meter.dress(block)
            print_block(block, use_ansi=ctx.use_ansi)
        return 0

    @staticmethod
    def _exception_message(exc: Exception) -> str:
        message = str(exc).strip()
        return message or type(exc).__name__

    @staticmethod
    def _fetch_error_block(ctx: CliContext, exc: Exception) -> Block:
        from ..core.block import Block, Wrap
        from ..core.cell import Style

        try:
            from ..palette import current_palette

            style = current_palette().error
        except Exception:
            style = Style(fg="red")

        message = CliRunner._exception_message(exc)
        width = max(1, ctx.width)
        return Block.text(message.replace("\n", " "), style, width=width, wrap=Wrap.WORD)

    @staticmethod
    def _render_error_block(ctx: CliContext, exc: Exception) -> Block:
        from ..core.block import Block, Wrap
        from ..core.cell import Style

        message = str(exc).strip()
        if message:
            text = f"{type(exc).__name__}: {message}"
        else:
            text = type(exc).__name__

        width = max(1, ctx.width)
        return Block.text(text.replace("\n", " "), Style(), width=width, wrap=Wrap.WORD)


def run_cli(
    args: list[str],
    render: Callable[[CliContext, T], Block],
    fetch: Callable[[], T],
    *,
    fetch_stream: Callable[[], AsyncIterator[T]] | None = None,
    handlers: dict[OutputMode, Callable[[CliContext], R]] | None = None,
    default_zoom: Zoom = Zoom.SUMMARY,
    default_mode: OutputMode = OutputMode.LIVE,
    live_delivery: str = "inplace",
    live_meter: bool = False,
    description: str | None = None,
    prog: str | None = None,
    add_args: Callable[[argparse.ArgumentParser], None] | None = None,
    help_args: list[HelpArg] | None = None,
    tags: list[Tag] | None = None,
    depth_aliases: dict[str, int] | None = None,
    budgets: bool = False,
    build_fidelity: Callable[[argparse.Namespace, Fidelity], Fidelity] | None = None,
) -> int:
    """Run a CLI tool with zoom/mode/format handling.

    Args:
        args: Command-line arguments (sys.argv[1:])
        render: Function to render state to Block
        fetch: Function to fetch state (sync)
        fetch_stream: Optional async iterator for streaming updates
        handlers: Custom handlers for specific output modes
        default_zoom: Default zoom level (SUMMARY)
        default_mode: Default mode for TTY when AUTO (LIVE)
        live_delivery: Live tier — "inplace" (scrollback) or "surface" (alt screen)
        live_meter: Dress live frames with a delivery-cost gauge (opt-in)
        description: Help text description
        prog: Program name
        add_args: Callback to add custom arguments
        help_args: Describe pre-parsed args for help rendering
        tags: Declared disclosure layers — each generates a --{name} flag
            compiled into fidelity.visible
        depth_aliases: App-local depth spellings ({"brief": 0} → --brief)
        budgets: Whether the app honors --max-chars/--max-lines
        build_fidelity: Transform Fidelity after tag compilation — the escape
            hatch for app-specific residue

    Returns:
        Exit code (0 for success)
    """
    return CliRunner(
        render=render,
        fetch=fetch,
        fetch_stream=fetch_stream,
        handlers=handlers,  # type: ignore[arg-type]
        default_zoom=default_zoom,
        default_mode=default_mode,
        live_delivery=live_delivery,
        live_meter=live_meter,
        description=description,
        prog=prog,
        add_args=add_args,
        help_args=help_args,
        tags=tags,
        depth_aliases=depth_aliases,
        budgets=budgets,
        build_fidelity=build_fidelity,
    ).run(args)
