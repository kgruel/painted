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
from typing import TYPE_CHECKING, Generic, TypeVar, overload

from contextlib import nullcontext

from ..core.errors import DeclarationError
from .types import (
    ArgsView,
    CliContext,
    Fidelity,
    Format,
    OutputMode,
    Tag,
    Zoom,
    build_parser,
    consumer_args,
    detect_context,
    parse_fidelity,
    parse_format,
    parse_mode,
    parse_zoom,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ..core.block import Block
    from ..core.renderer import Renderer
    from .help import HelpArg
    from .prompts import Prompt

# .help is imported lazily inside _handle_help, never at module top: it pulls
# core.doc (the renderer), and importing the runner must not — the no-renderer-
# on-TAB rule. The help-render path pays the import only when -h actually fires.

T = TypeVar("T")  # State type
R = TypeVar("R")  # Return type


@dataclass
class CliRunner(Generic[T]):
    """CLI runner with sensible defaults and explicit overrides."""

    # How to render state to a Block — two contracts, exactly one declared.
    #
    #   render=    legacy (ctx, data) → Block; the host hands the whole context.
    #   renderer=  the contract (data, fidelity, width) → Block (§1): the semantic
    #              renderer, given only its three inputs. Keyword-only at the
    #              run_cli surface, the RENDER_MODEL glossary's exact term.
    #
    # Both default None at the signature so `render` can move from required- to
    # optional-positional (existing `run_cli(args, render, fetch)` call sites keep
    # working) and `renderer` can be keyword-only. Requiredness moves to
    # construction (__post_init__): at most one — declaring both faults; declaring
    # neither installs the transcription default (§4), so there is always exactly
    # one renderer at dispatch. `render=` is documented legacy through a
    # deprecation window — no runtime warning yet, that gate opens at 0.12
    # (docs/RENDERER_CONTRACT_DESIGN.md §3).
    render: Callable[[CliContext, T], Block] | None = None
    # kw_only so the legacy positional layout is byte-for-byte preserved:
    # `CliRunner(render, fetch)` still binds render then fetch, and `renderer`
    # is keyword-only at the dataclass exactly as it is at the run_cli surface.
    # repr=False so the transcription default the *neither* form self-installs
    # (§4) never leaks through the generated repr — the default renderer stays
    # private; its callable identity is not API.
    renderer: Renderer[T] | None = field(default=None, kw_only=True, repr=False)

    # How to fetch state (sync). Arity-polymorphic via the run() shim: declared
    # nullary it's called fetch(), declared with a parameter it receives ctx —
    # hence Callable[..., T] rather than a fixed arity. Optional at the signature
    # (see above); a missing fetch is a DeclarationError at construction.
    fetch: Callable[..., T] | None = None

    # Optional: streaming fetch for live mode (same arity shim as fetch)
    fetch_stream: Callable[..., AsyncIterator[T]] | None = None

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

    # Declared inline prompts (docs/PROMPTS_DESIGN.md). Each generates its
    # flag(s) and is resolvable through ctx.ask; a prompt's answer never appears
    # in ctx.args — one door for the answer (design Q3).
    prompts: list[Prompt] | None = None

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
        #
        # Construction is the render-path validation seam, not parser
        # construction: the runner's empty-argv fast path never builds a parser,
        # and neither render/renderer/fetch mints a flag, so a parser-time check
        # would provably never fire on bare `tool` — the most common invocation
        # (docs/RENDERER_CONTRACT_DESIGN.md §3). These checks therefore live here,
        # asserted on empty argv by the tests.
        if self.render is not None and self.renderer is not None:
            raise DeclarationError(
                "declare either render= (legacy (ctx, data)) or renderer= (the "
                "(data, fidelity, width) contract), not both"
            )
        if self.fetch is None:
            raise DeclarationError("run_cli requires fetch= (how to fetch state)")
        if self.render is None and self.renderer is None:
            # Neither declared: render by transcription (§4). The *neither* form
            # is a real call form now — install painted's default renderer so
            # dispatch has always exactly one renderer, no special no-render branch.
            #
            # The fence: transcription cannot consume fidelity.visible (no way to
            # map app-domain facet names onto arbitrary data), yet every declared
            # Tag mints a --{name} flag — so tags= under the default renderer
            # would be a dead public flag, the honesty violation FIDELITY_DESIGN §1
            # calls structurally impossible. tags= with neither renderer therefore
            # faults here, taking the old *neither* fault's place (§4).
            if self.tags:
                raise DeclarationError(
                    "tags= requires render= or renderer=: the transcription default "
                    "cannot consume declared facets (fidelity.visible), so each "
                    "--{tag} flag would be dead "
                    "(docs/RENDERER_CONTRACT_DESIGN.md §4)"
                )
            # The default renderer lives at the root, not here: cli may not import
            # views (the layer tripwire), so the bridge to the transcription lens
            # is a root module the runner references (docs/…§4). Import is lazy —
            # `import painted.cli` stays views-free until a bare tool actually runs.
            from .._transcription import transcription_renderer

            self.renderer = transcription_renderer

        if self.live_delivery not in ("inplace", "surface"):
            raise DeclarationError(
                f"live_delivery must be 'inplace' or 'surface', got {self.live_delivery!r}"
            )

    def run(self, args: list[str]) -> int:
        """Parse args, resolve context, dispatch."""
        # Completion gate first — before -h, before parsing. When the shell glue
        # calls back (the _PAINTED_COMPLETE env var), complete this command's own
        # parser and exit, never touching the renderer. Lazy import keeps the
        # transport off the no-completion path.
        from .completion_shell import completion_active, run_single_completion

        shell = completion_active()
        if shell is not None:
            return run_single_completion(self._get_parser(), shell=shell)

        # Intercept --help before argparse
        if "-h" in args or "--help" in args:
            return self._handle_help(args)

        has_declarations = bool(self.tags) or bool(self.depth_aliases) or bool(self.prompts)
        parked: dict[str, object] = {}
        no_input = False
        plain_requested = False
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
            args_view = ArgsView()
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
            args_view = consumer_args(parsed, self.tags, self.depth_aliases, self.prompts)
            # Park each prompt's argv answer, keyed by its dest(s); stripped from
            # ctx.args above, resolved lazily behind ctx.ask (design Q3).
            no_input = bool(getattr(parsed, "no_input", False))
            # The prompt session's plainness derives from the --plain *request*,
            # not the resolved output format: --json --plain resolves fmt=JSON
            # (stdout is data), but the user still asked for a plain prompt UI on
            # stderr — a different plane (§8). stdout's ANSI stays fmt-derived
            # below; the stderr prompt UI reads the flag itself.
            plain_requested = bool(getattr(parsed, "plain", False))
            for prompt in self.prompts or ():
                for dest in prompt.dests():
                    # Each prompt dest carries argparse default=_UNSET (the
                    # absent-flag sentinel), so an absent flag parks as _UNSET —
                    # kept distinct from a flag that legally parsed to None
                    # (design §6, the flag_supplied seam). The dest is always on
                    # the namespace (the parser registered it), so the getattr
                    # fallback is unreachable.
                    parked[dest] = getattr(parsed, dest, None)

        is_json = fmt == Format.JSON
        force_plain = fmt == Format.PLAIN

        # Plain text and minimal depth imply static mode. Checked on the
        # compiled fidelity, not the -q flag, so a depth alias to 0 behaves
        # like -q (<= because a build_fidelity hook can hand back any int).
        if mode == OutputMode.AUTO and (force_plain or fidelity.depth <= int(Zoom.MINIMAL)):
            mode = OutputMode.STATIC

        ctx = detect_context(
            fidelity,
            mode,
            force_plain=force_plain,
            default_mode=self.default_mode,
            args=args_view,
            prompts=self.prompts,
            parked=parked,
            no_input=no_input,
            plain_requested=plain_requested,
        )

        # The single refusal seam (design §8): a prompt ContractError raised
        # anywhere under fetch/render/handler — in any mode, JSON included —
        # propagates here and routes to stderr with a clean stdout, rather than
        # each mode path re-implementing the routing. The per-mode handlers let
        # PromptContractError pass through (they never render it as an ordinary
        # error block).
        from .prompts import PromptContractError

        try:
            # JSON short-circuits — it's data export, not rendering — but still
            # carries ctx so an arity-1 fetch reads the same resolved invocation.
            if is_json:
                return self._export_json(ctx)
            return self._dispatch(ctx)
        except PromptContractError as exc:
            return self._emit_refusal(ctx, exc, plain=plain_requested)

    def _get_parser(self) -> argparse.ArgumentParser:
        """Build and cache the parser for repeated invocations.

        Delegates to the standalone ``build_parser`` — the same parser
        completion and help walk. The runner's only job here is to compute the
        supported mode set (which depends on fetch_stream/handlers/delivery,
        things build_parser deliberately doesn't know).
        """
        if self._parser_cache is not None:
            return self._parser_cache

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

        self._parser_cache = build_parser(
            add_args=self.add_args,
            tags=self.tags,
            depth_aliases=self.depth_aliases,
            budgets=self.budgets,
            prompts=self.prompts,
            modes=modes,
            prog=self.prog,
            description=self.description,
        )
        return self._parser_cache

    def _handle_help(self, args: list[str]) -> int:
        """Render zoom-aware help and return 0."""
        from .help import help_doc, scan_help_args

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

    @staticmethod
    def _wants_ctx(fn: Callable[..., object]) -> bool:
        """Arity shim: a 0-param fetch is called nullary (the existing
        contract, untouched), a fetch that declares a positional parameter
        receives ``ctx``. Lets a fetch read ``ctx.args`` without breaking every
        nullary fetch already in the wild. Callables whose signature can't be
        introspected fall back to nullary — the conservative, back-compatible
        default."""
        import inspect

        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        return any(
            p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
            for p in sig.parameters.values()
        )

    def _do_fetch(self, ctx: CliContext) -> T:
        """Call fetch through the arity shim."""
        assert self.fetch is not None  # construction guarantees fetch is present
        return self.fetch(ctx) if self._wants_ctx(self.fetch) else self.fetch()

    @staticmethod
    def _offered_width(ctx: CliContext, geometry: int | None = None) -> int | None:
        """The offered allocation (§5) — the single place the offer rule lives.

        The rule is one line, and gates on the *viewport*, not on ANSI-ness:
        stdout is a real viewport (a TTY) → offer its geometry; a viewportless
        destination (a pipe, a file redirect) → offer ``None``, so blocks
        render at natural width (the 0.10.1 half of the invariant). Format is
        orthogonal — ``--plain`` at a real TTY still offers geometry (the
        terminal's columns are real; the user only asked to drop ANSI); only
        losing the viewport yields ``None``. No renderer ever consults TTY
        state — the pipe case arrives as ``width=None``, not a fabricated
        fallback.

        ``geometry`` is *which* width is current at the moment of the offer,
        never *whether* a TTY gets one: it defaults to ``ctx.width`` (the
        known geometry at one-shot dispatch) and the live paths pass the
        frame's current width instead — the freshly-read terminal columns
        in-place, the surface buffer's width on the alt screen. A mid-run
        resize therefore changes the next offer without re-implementing the
        rule per delivery path (§6).
        """
        known = ctx.width if geometry is None else geometry
        return known if ctx.is_tty else None

    @staticmethod
    def _current_columns() -> int:
        """The terminal's current column count, re-read per live frame.

        The width sibling of ``InPlaceRenderer._viewport_rows``: both re-read
        ambient geometry (``shutil.get_terminal_size``) each frame so a
        mid-run resize re-enters the renderer as changed input (§6). Gated by
        the offer rule — on a non-TTY the read is discarded for ``None``.
        """
        return shutil.get_terminal_size().columns

    def _render(self, ctx: CliContext, state: T, offered: int | None) -> Block:
        """Produce the content Block, dispatching the declared render contract.

        The one seam both delivery-path renders funnel through, so the two
        contracts differ in exactly one place. ``renderer=`` gets the three
        inputs (§1) — state, the compiled Fidelity intact, and the ``offered``
        width the caller resolved through ``_offered_width``; ``render=`` gets
        the legacy whole context and reads ``ctx.width`` itself (the known
        geometry stays ``int`` through the migration window, §5). Construction
        guarantees a renderer is present — the app's, or the transcription
        default installed when neither was declared (§4), which travels the
        ``renderer`` branch like any other.

        The offer is computed *per offer* at the caller, not here: static and
        non-streaming callers pass ``_offered_width(ctx)``; the in-place live
        loop re-reads geometry each frame; the alt-screen adapter passes the
        surface buffer's current width (§6). This seam only forwards it.
        """
        if self.renderer is not None:
            return self.renderer(state, ctx.fidelity, offered)
        assert self.render is not None  # exactly one of render/renderer, per construction
        return self.render(ctx, state)

    def _stream_iter(self, ctx: CliContext) -> AsyncIterator[T]:
        """Open the fetch_stream async iterator through the arity shim."""
        assert self.fetch_stream is not None
        if self._wants_ctx(self.fetch_stream):
            return self.fetch_stream(ctx)
        return self.fetch_stream()

    def _export_json(self, ctx: CliContext) -> int:
        """Export data as JSON — bypasses render pipeline entirely.

        Dataclass state is exported via ``asdict``; anything else is handed
        to ``json.dumps`` directly. Values JSON can't encode are coerced with
        ``str()`` (``default=str``) rather than erroring — export is
        best-effort by contract, so a non-JSON-clean field yields its repr,
        not a failure.
        """
        from .prompts import PromptContractError

        try:
            state = self._do_fetch(ctx)
        except PromptContractError:
            # A refusal is not export data — let the single seam route it to
            # stderr with nothing on stdout, so `tool --json | jq` stays clean.
            raise
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
            state = self._do_fetch(ctx)
        except Exception as exc:
            self._emit_error(ctx, self._fetch_error_block(ctx, exc), exc)
            return 1

        try:
            block = self._render(ctx, state, self._offered_width(ctx))
        except Exception as exc:
            self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
            return 2

        print_block(block, use_ansi=ctx.use_ansi)
        return 0

    def _run_live(self, ctx: CliContext) -> int:
        """Run with InPlaceRenderer."""
        import asyncio

        from ..inplace import InPlaceRenderer
        from ..core.writer import print_block
        from .prompts import PromptAbort

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
                        async for state in self._stream_iter(ctx):
                            try:
                                # Viewportless: this branch retains only the
                                # last Block and prints it once at the end — a
                                # cadence choice, not a per-frame viewport. On a
                                # pipe the offer is None; on a forced-plain TTY
                                # it is the known geometry, like static (§5).
                                last_block = self._render(ctx, state, self._offered_width(ctx))
                            except Exception as exc:
                                self._emit_error(
                                    ctx, self._render_error_block(ctx, exc), exc, use_ansi=False
                                )
                                return 2
                    except PromptAbort:
                        # A prompt abort is not a graceful stop — propagate it
                        # out of run_cli like a static-mode abort (§7).
                        raise
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        return 0
                    except Exception as exc:
                        self._emit_error(
                            ctx, self._fetch_error_block(ctx, exc), exc, use_ansi=False
                        )
                        return 1
                    if last_block is not None:
                        print_block(last_block, use_ansi=False)
                    return 0

                meter = None
                if self.live_meter:
                    from .live_meter import LiveMeter

                    meter = LiveMeter()
                from .prompts import PromptContractError

                with InPlaceRenderer() as renderer:
                    try:
                        async for state in self._stream_iter(ctx):
                            if meter is not None:
                                meter.start()
                            try:
                                # Re-offer current geometry each frame: the
                                # in-place host owns a live viewport, so a
                                # mid-run resize re-enters the renderer as
                                # changed input (§6).
                                block = self._render(
                                    ctx, state, self._offered_width(ctx, self._current_columns())
                                )
                            except PromptContractError:
                                # A refusal never renders into the live region —
                                # propagate to the outer finalize + the seam.
                                raise
                            except Exception as exc:
                                renderer.render(self._render_error_block(ctx, exc))
                                renderer.finalize()
                                return 2
                            if meter is not None:
                                block = meter.dress(block)
                            renderer.render(block)
                            if meter is not None:
                                meter.stop()
                    except PromptAbort:
                        # Settle the live region, then propagate — a prompt abort
                        # exits like static mode, never as a graceful stop (§7).
                        renderer.finalize()
                        raise
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        renderer.finalize()
                        return 0
                    except PromptContractError:
                        renderer.finalize()
                        raise
                    except Exception as exc:
                        renderer.render(self._fetch_error_block(ctx, exc))
                        renderer.finalize()
                        return 1
                    # Keep final output visible
                    renderer.finalize()
                    return 0

            try:
                return asyncio.run(stream())
            except PromptAbort:
                raise  # a prompt abort propagates out of run_cli, not exit-0
            except KeyboardInterrupt:
                return 0

        # No streaming: just fetch and render
        try:
            state = self._do_fetch(ctx)
        except Exception as exc:
            self._emit_error(ctx, self._fetch_error_block(ctx, exc), exc)
            return 1

        try:
            block = self._render(ctx, state, self._offered_width(ctx))
        except Exception as exc:
            self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
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
        from .prompts import PromptAbort, PromptContractError
        from .stream_surface import StreamSurface

        assert self.fetch_stream is not None  # guarded by the caller

        # The surface's per-frame width lives in its buffer, not ``ctx`` —
        # ``detect_context`` ran once, the alt screen resizes. The adapter is
        # runner-internal plumbing (§6): it applies the one offer rule to the
        # buffer's *current* geometry each frame, so the renderer itself stays
        # pure and signature-identical. Stale ``ctx.width`` would let
        # ``Block.paint`` clip silently after a resize.
        def offer_frame(state: T, geometry: int) -> Block:
            return self._render(ctx, state, self._offered_width(ctx, geometry))

        surface = StreamSurface(
            render=offer_frame,
            fetch_stream=lambda: self._stream_iter(ctx),
            live_meter=self.live_meter,
        )
        try:
            asyncio.run(surface.run())
        except PromptAbort:
            raise  # a prompt abort propagates out of run_cli, not a silent deposit
        except KeyboardInterrupt:
            pass  # final frame still deposited below
        except PromptContractError:
            raise  # route through the seam, not the delivery-failure path below
        except Exception as exc:
            # User fetch/render failures are captured in surface.error; what
            # reaches here is a delivery failure (terminal setup, sizing).
            # Surface.run has already restored the terminal — translate to the
            # documented exit-code contract instead of leaking a traceback.
            print(self._exception_message(exc), file=sys.stderr)
            return 1

        if surface.error is not None:
            # A refusal captured inside the surface routes through the seam too.
            if isinstance(surface.error, PromptContractError):
                raise surface.error
            if surface.error_kind == "render":
                print_block(self._render_error_block(ctx, surface.error), use_ansi=ctx.use_ansi)
                return 2
            print_block(self._fetch_error_block(ctx, surface.error), use_ansi=ctx.use_ansi)
            return 1

        if surface.last_state is not None:
            try:
                # The deposit is itself an offer — the runner's final print to
                # the normal screen (a TTY; the surface path was gated on it).
                # It re-reads *current* columns like every other offer (§§5–6):
                # a resize during the alt-screen session moved the geometry, so
                # detection-time ctx.width would deposit at a stale width.
                block = self._render(
                    ctx, surface.last_state, self._offered_width(ctx, self._current_columns())
                )
            except PromptContractError:
                raise
            except Exception as exc:
                print_block(self._render_error_block(ctx, exc), use_ansi=ctx.use_ansi)
                return 2
            if self.live_meter:
                # The deposit carries the run's final gauge — what this show cost.
                block = surface.meter.dress(block)
            print_block(block, use_ansi=ctx.use_ansi)
        return 0

    @staticmethod
    def _emit_error(
        ctx: CliContext, block: Block, exc: Exception, *, use_ansi: bool | None = None
    ) -> None:
        """Print an ordinary fetch/render error block to stdout.

        A prompt refusal is *not* ordinary: it re-raises here so the single
        refusal seam in ``run()`` routes it to stderr with a clean stdout
        (design §8). Every other error keeps the existing stdout path unchanged,
        so this is the one place mode handlers funnel error rendering through.
        """
        from .prompts import PromptContractError

        if isinstance(exc, PromptContractError):
            raise exc
        from ..core.writer import print_block

        print_block(block, use_ansi=ctx.use_ansi if use_ansi is None else use_ansi)

    def _emit_refusal(self, ctx: CliContext, exc: Exception, *, plain: bool) -> int:
        """Route a prompt refusal to stderr, leaving stdout a clean data channel.

        The single seam every mode funnels a ``PromptContractError`` through
        (design §8): the remediation text renders to stderr at stderr's own
        fidelity, stdout emits nothing (``tool --json | jq`` stays parseable even
        when the tool refused mid-run), and the exit is nonzero — a refusal is a
        run that produced no answer. A refusal is prompt UI, so its plainness
        follows the same gate as the prompts it speaks for: stderr's TTY-ness
        overridden by the ``--plain`` *request* (cf. ``PromptSession._use_ansi``),
        never the resolved stdout format.
        """
        from ..core.writer import print_block

        use_ansi = ctx.stderr_is_tty and not plain
        print_block(self._fetch_error_block(ctx, exc), sys.stderr, use_ansi=use_ansi)
        return 1

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


# Three published call forms — the truth type checkers carry, so no caller ever
# sees `fetch` as optional even though the runtime signature says None (the
# requiredness lives in construction). One overload per call form: the two
# authored-renderer contracts (legacy positional `render`; keyword `renderer=`)
# and the *neither* form (the transcription default, §4) — published now that its
# behavior lands in S3, the call form spelled the moment it behaves. Each requires
# `fetch`. See RENDERER_CONTRACT_DESIGN.md §§3, 12.
@overload
def run_cli(
    args: list[str],
    render: Callable[[CliContext, T], Block],
    fetch: Callable[..., T],
    *,
    fetch_stream: Callable[..., AsyncIterator[T]] | None = ...,
    handlers: dict[OutputMode, Callable[[CliContext], R]] | None = ...,
    default_zoom: Zoom = ...,
    default_mode: OutputMode = ...,
    live_delivery: str = ...,
    live_meter: bool = ...,
    description: str | None = ...,
    prog: str | None = ...,
    add_args: Callable[[argparse.ArgumentParser], None] | None = ...,
    help_args: list[HelpArg] | None = ...,
    tags: list[Tag] | None = ...,
    depth_aliases: dict[str, int] | None = ...,
    prompts: list[Prompt] | None = ...,
    budgets: bool = ...,
    build_fidelity: Callable[[argparse.Namespace, Fidelity], Fidelity] | None = ...,
) -> int: ...


@overload
def run_cli(
    args: list[str],
    *,
    renderer: Renderer[T],
    fetch: Callable[..., T],
    fetch_stream: Callable[..., AsyncIterator[T]] | None = ...,
    handlers: dict[OutputMode, Callable[[CliContext], R]] | None = ...,
    default_zoom: Zoom = ...,
    default_mode: OutputMode = ...,
    live_delivery: str = ...,
    live_meter: bool = ...,
    description: str | None = ...,
    prog: str | None = ...,
    add_args: Callable[[argparse.ArgumentParser], None] | None = ...,
    help_args: list[HelpArg] | None = ...,
    tags: list[Tag] | None = ...,
    depth_aliases: dict[str, int] | None = ...,
    prompts: list[Prompt] | None = ...,
    budgets: bool = ...,
    build_fidelity: Callable[[argparse.Namespace, Fidelity], Fidelity] | None = ...,
) -> int: ...


# The *neither* form — no render=, no renderer=: the framework transcribes the
# fetched data through the (data, fidelity, width) contract (§4). `fetch` stays
# required, keyword-only like every other input on this form.
@overload
def run_cli(
    args: list[str],
    *,
    fetch: Callable[..., T],
    fetch_stream: Callable[..., AsyncIterator[T]] | None = ...,
    handlers: dict[OutputMode, Callable[[CliContext], R]] | None = ...,
    default_zoom: Zoom = ...,
    default_mode: OutputMode = ...,
    live_delivery: str = ...,
    live_meter: bool = ...,
    description: str | None = ...,
    prog: str | None = ...,
    add_args: Callable[[argparse.ArgumentParser], None] | None = ...,
    help_args: list[HelpArg] | None = ...,
    tags: list[Tag] | None = ...,
    depth_aliases: dict[str, int] | None = ...,
    prompts: list[Prompt] | None = ...,
    budgets: bool = ...,
    build_fidelity: Callable[[argparse.Namespace, Fidelity], Fidelity] | None = ...,
) -> int: ...


def run_cli(
    args: list[str],
    render: Callable[[CliContext, T], Block] | None = None,
    fetch: Callable[..., T] | None = None,
    *,
    renderer: Renderer[T] | None = None,
    fetch_stream: Callable[..., AsyncIterator[T]] | None = None,
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
    prompts: list[Prompt] | None = None,
    budgets: bool = False,
    build_fidelity: Callable[[argparse.Namespace, Fidelity], Fidelity] | None = None,
) -> int:
    """Run a CLI tool with zoom/mode/format handling.

    Declare at most one renderer contract:

      * ``renderer=`` — the contract (§1): ``(data, fidelity, width) → Block``,
        the semantic renderer given only its three inputs. Keyword-only.
      * ``render=`` — legacy ``(ctx, data) → Block``, optional-positional so
        existing ``run_cli(args, render, fetch)`` call sites keep working. Kept
        through a deprecation window; no runtime warning until 0.12 (§3).
      * *neither* — the framework renders by **transcription** (§4): the fetched
        data is transcribed through the same contract. ``tags=`` is unavailable
        on this form (transcription cannot consume declared facets), and
        declaring it raises ``DeclarationError``.

    Passing both renderers raises ``DeclarationError`` at construction — as does
    a missing ``fetch``.

    Args:
        args: Command-line arguments (sys.argv[1:])
        render: Legacy render callback ``(ctx, data) → Block`` (deprecation window)
        renderer: The renderer contract ``(data, fidelity, width) → Block`` (§1)
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
        prompts: Declared inline prompts — each generates its flag(s) and is
            resolvable through ctx.ask (docs/PROMPTS_DESIGN.md)
        budgets: Whether the app honors --max-chars/--max-lines
        build_fidelity: Transform Fidelity after tag compilation — the escape
            hatch for app-specific residue

    Returns:
        Exit code (0 for success)
    """
    return CliRunner(
        render=render,
        renderer=renderer,
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
        prompts=prompts,
        budgets=budgets,
        build_fidelity=build_fidelity,
    ).run(args)
