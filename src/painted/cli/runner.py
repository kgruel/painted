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
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from .args import add_cli_args, parse_format, parse_mode, parse_zoom
from .context import detect_context, setup_defaults
from .help import HelpArg, build_help_data, render_help, scan_help_args
from .types import CliContext, Format, OutputMode, Zoom

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

    # Optional: description for help
    description: str | None = None

    # Optional: program name
    prog: str | None = None

    # Optional: callback to add custom args
    add_args: Callable[[argparse.ArgumentParser], None] | None = None

    # Optional: describe pre-parsed args for help rendering
    help_args: list[HelpArg] | None = None

    def run(self, args: list[str]) -> int:
        """Parse args, resolve context, dispatch."""
        # Intercept --help before argparse
        if "-h" in args or "--help" in args:
            return self._handle_help(args)

        parser = argparse.ArgumentParser(
            description=self.description,
            prog=self.prog,
            add_help=False,
        )
        # Re-add -h/--help so argparse still recognizes it for error messages
        parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)

        # Infer supported modes from config
        modes: set[OutputMode] = {OutputMode.STATIC}
        if self.fetch_stream is not None:
            modes.add(OutputMode.LIVE)
        if self.handlers and OutputMode.INTERACTIVE in self.handlers:
            modes.add(OutputMode.INTERACTIVE)

        add_cli_args(parser, modes=modes)

        if self.add_args is not None:
            self.add_args(parser)

        parsed = parser.parse_args(args)

        zoom = parse_zoom(parsed, self.default_zoom)
        mode = parse_mode(parsed)
        fmt = parse_format(parsed)

        # JSON short-circuits — it's data export, not rendering
        is_json = fmt == Format.JSON
        if is_json:
            return self._export_json()

        force_plain = fmt == Format.PLAIN

        # Plain text and minimal zoom imply static mode
        if mode == OutputMode.AUTO and (force_plain or zoom == Zoom.MINIMAL):
            mode = OutputMode.STATIC

        ctx = detect_context(zoom, mode, force_plain=force_plain, default_mode=self.default_mode)

        return self._dispatch(ctx)

    def _handle_help(self, args: list[str]) -> int:
        """Render zoom-aware help and return 0."""
        zoom, fmt = scan_help_args(args)
        help_data = build_help_data(self)

        if fmt == Format.JSON:
            print(json.dumps(asdict(help_data), default=str))
            return 0

        use_ansi = fmt != Format.PLAIN
        if fmt == Format.AUTO:
            use_ansi = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

        width = shutil.get_terminal_size().columns
        block = render_help(help_data, zoom, width, use_ansi)

        from ..core.writer import print_block

        print_block(block, use_ansi=use_ansi)
        return 0

    def _export_json(self) -> int:
        """Export data as JSON — bypasses render pipeline entirely."""
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

    def _dispatch(self, ctx: CliContext) -> int:
        """Dispatch to appropriate output mechanism."""
        setup_defaults(ctx)

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
            # Streaming mode: update as data arrives
            async def stream() -> int:
                with InPlaceRenderer() as renderer:
                    try:
                        async for state in self.fetch_stream():  # type: ignore[misc]
                            try:
                                block = self.render(ctx, state)
                            except Exception as exc:
                                renderer.render(self._render_error_block(ctx, exc))
                                renderer.finalize()
                                return 2
                            renderer.render(block)
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
    description: str | None = None,
    prog: str | None = None,
    add_args: Callable[[argparse.ArgumentParser], None] | None = None,
    help_args: list[HelpArg] | None = None,
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
        description: Help text description
        prog: Program name
        add_args: Callback to add custom arguments
        help_args: Describe pre-parsed args for help rendering

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
        description=description,
        prog=prog,
        add_args=add_args,
        help_args=help_args,
    ).run(args)
