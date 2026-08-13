"""CliRunner: the main CLI dispatch engine.

Connects argument parsing, context detection, and rendering into
a single entry point for CLI tools.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, overload

from contextlib import AbstractContextManager, ExitStack, nullcontext

from ..core.errors import ContractError, DeclarationError
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
    from ..core.cell import Style
    from ..core.renderer import HeightRenderer, Renderer
    from ..host import HostEventSink
    from ..refs import RefScheme
    from .help import HelpArg
    from .prompts import Prompt

# .help is imported lazily inside _handle_help, never at module top: it pulls
# core.doc (the renderer), and importing the runner must not — the no-renderer-
# on-TAB rule. The help-render path pays the import only when -h actually fires.

T = TypeVar("T")  # State type
R = TypeVar("R")  # Return type


def _legacy_render_stacklevel() -> int:
    """Stacklevel for the ``render=`` warning, attributed to the caller's own
    line regardless of entry point: direct ``CliRunner(render=...)``
    construction, or ``run_cli(...)``'s pass-through construction one frame
    deeper. Walks past this module's frames and the dataclass-generated
    ``__init__`` (``co_filename == "<string>"``) rather than hardcoding a
    depth that only one of the two entry points would get right.
    """
    frame = sys._getframe(1)  # the caller of this helper (__post_init__)
    level = 1
    while frame is not None and frame.f_code.co_filename in (__file__, "<string>"):
        frame = frame.f_back
        level += 1
    return level


@dataclass(frozen=True)
class _RendererBinding(Generic[T]):
    """The normalized renderer declaration (docs/HOST_RUNG_DESIGN.md §3–4).

    All four authored forms — legacy ``render=``, ``renderer=``,
    ``height_renderer=``, and the transcription default — collapse to one record
    at construction, and dispatch consults *this*, never the callable's arity.
    The design rationale (§3): a future runtime view-selection picks between
    pre-declared bindings, and the acceptance flag it selects on must be a
    standing fact recorded here, not re-derived by inspecting results.

    Fields carry the two orthogonal axes the offer matrix reads:

      * ``accepts_height`` — the **acceptance** declaration (§3). ``True`` only
        for ``height_renderer=``: this callable has the keyword-only ``height``
        parameter and honors the offered arm. The host passes ``height=`` only
        when this is set; an undeclared binding is never handed the keyword
        (it has none), which is the top row of the §3 matrix.
      * ``legacy`` — the ``(ctx, data)`` call shape of the deprecated ``render=``
        form. Mutually exclusive with ``accepts_height``.

    Neither flag set is the ``(data, fidelity, width)`` contract (``renderer=``
    or the transcription default).
    """

    # Widened to Callable[..., Block] deliberately: the record's whole point is
    # that the *flags* below carry the call shape, not the callable's static
    # type — dispatch reads `accepts_height`/`legacy` to pick the arguments, and
    # a single union type here would force every call site to re-narrow it. The
    # three authored shapes (Renderer[T], HeightRenderer[T], the legacy
    # (ctx, data)) all satisfy this.
    call: Callable[..., Block]
    accepts_height: bool
    legacy: bool


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

    # The height-aware acceptance declaration (docs/HOST_RUNG_DESIGN.md §4): a
    # renderer with the keyword-only `height` parameter that honors the offered
    # arm of the dual allocation contract. Keyword-only, beside `renderer=`, and
    # mutually exclusive with *all* authored-renderer forms — declaring it with
    # `renderer=` or legacy `render=` is a construction-time DeclarationError
    # (the same collision contract). `height_renderer=` alone is a complete
    # declaration; no `renderer=` is needed. The parameter name *is* the
    # acceptance flag, so no boolean can drift from the callable's real shape —
    # both forms normalize into `_binding` (§3).
    height_renderer: HeightRenderer[T] | None = field(default=None, kw_only=True, repr=False)

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

    # Ref schemes declaration (docs/RENDERER_CONTRACT_DESIGN.md §7): the
    # runner-owned bracket around render + serialization, replacing whatever
    # ambient `use_refs` state was active for that cycle. A static sequence
    # validates now, at construction (DeclarationError — starts-clean-never-
    # fires); a callable of state cannot start clean, so it evaluates after a
    # successful fetch and before the renderer is invoked — a raising
    # callable enters the render-error path unchanged (app fault, not
    # painted's), an invalid *result* faults ContractError before any
    # use_refs call. Absent (None, the default): the framework installs
    # nothing — ambient schemes an app set through `use_refs` itself flow
    # through unchanged. `ref_schemes=[]` is a valid explicit empty
    # declaration: disable ambient resolution for the runner-owned cycle.
    # Not evaluated on handler-dispatched modes (only a static sequence
    # installs there — a handler has no fetched state to evaluate a callable
    # against) or on the `--json` fork (data export never renders, never
    # serializes a Block).
    ref_schemes: Sequence[RefScheme] | Callable[[T], Sequence[RefScheme]] | None = field(
        default=None, kw_only=True
    )

    # The inward host-event sink (docs/HOST_RUNG_DESIGN.md §7): host viewing-state
    # reaching the application as *input*, delivered synchronously and exactly once
    # per event through a construction-time push callback. Keyword-only, on the
    # HOST constructor (never on the renderer binding / _RendererBinding — accepting
    # host input is application/session behavior, and the semantic renderer stays
    # unchanged across the four rungs). Wired into the two rungs where painted owns
    # a viewport: the interactive host rung (HostSurface, _run_host) and the
    # alt-screen streaming tier (StreamSurface, _run_live_surface — the follow
    # path). On every other route (STATIC, pipe, in-place LIVE, the offered arm)
    # declaring it is legal and it simply never fires — honest event-source silence,
    # never a manufactured tokenless / synthetic-mount event.
    on_host_event: HostEventSink | None = field(default=None, kw_only=True)

    # The static form's validated, FROZEN copy — set once in __post_init__,
    # never re-derived from `self.ref_schemes` afterward. `self.ref_schemes`
    # is a caller-owned sequence (a list the app can still mutate after
    # construction); every bracket reads this tuple instead, so a
    # post-construction mutation (e.g. appending a duplicate name) can never
    # reopen a declaration that already started clean (§3's defensive-copy
    # ruling). ``None`` here means "not the static form" — absent, or a
    # callable, which evaluates fresh per fetch and has nothing to freeze.
    _ref_schemes_static: tuple[RefScheme, ...] | None = field(default=None, init=False, repr=False)

    # Internal parser cache for repeated invocations
    _parser_cache: argparse.ArgumentParser | None = field(default=None, init=False, repr=False)

    # The normalized renderer declaration (§3–4), set once in __post_init__ from
    # whichever of the four authored forms was declared. Dispatch reads this —
    # never `render`/`renderer`/`height_renderer` directly, never the callable's
    # arity — so the acceptance arm is a standing fact, not a per-call inspection.
    _binding: _RendererBinding[T] = field(init=False, repr=False)

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
        # `height_renderer=` (HOST_RUNG_DESIGN §4) is the acceptance declaration
        # and is mutually exclusive with *every* authored-renderer form — the
        # same collision contract as render=/renderer= above, one callable of
        # record per command. Checked before fetch so the misconfiguration a
        # caller sees is the declaration collision, not a missing fetch masking it.
        if self.height_renderer is not None and self.renderer is not None:
            raise DeclarationError(
                "declare either renderer= (the (data, fidelity, width) contract) or "
                "height_renderer= (the height-aware (data, fidelity, width, *, "
                "height) contract), not both"
            )
        if self.height_renderer is not None and self.render is not None:
            raise DeclarationError(
                "declare either render= (legacy (ctx, data)) or height_renderer= "
                "(the height-aware (data, fidelity, width, *, height) contract), "
                "not both"
            )
        if self.fetch is None:
            raise DeclarationError("run_cli requires fetch= (how to fetch state)")
        if self.render is not None:
            # The 0.11 sequencing promise (§3): render= was silent while raymarch/
            # starmap were blocked on the capability vocabulary; both migrated in
            # M5-c, so the gate opens here, once, at the declaration seam — never
            # per frame.
            warnings.warn(
                "render=(ctx, data) is deprecated; use renderer=(data, fidelity, "
                "width) instead (removed at 1.0, docs/RENDERER_CONTRACT_DESIGN.md §3)",
                DeprecationWarning,
                stacklevel=_legacy_render_stacklevel(),
            )
        if self.render is None and self.renderer is None and self.height_renderer is None:
            # Nothing declared: render by transcription (§4). The *neither* form
            # is a real call form now — install painted's default renderer so
            # dispatch has always exactly one renderer, no special no-render branch.
            #
            # The fence: transcription cannot consume fidelity.visible (no way to
            # map app-domain facet names onto arbitrary data), yet every declared
            # Tag mints a --{name} flag — so tags= under the default renderer
            # would be a dead public flag, the honesty violation FIDELITY_DESIGN §1
            # calls structurally impossible. tags= with no renderer therefore
            # faults here, taking the old *neither* fault's place (§4). A declared
            # renderer= or height_renderer= *can* consume facets, so the fence is
            # scoped to this transcription branch only.
            if self.tags:
                raise DeclarationError(
                    "tags= requires render=, renderer=, or height_renderer=: the "
                    "transcription default cannot consume declared facets "
                    "(fidelity.visible), so each --{tag} flag would be dead "
                    "(docs/RENDERER_CONTRACT_DESIGN.md §4)"
                )
            # The default renderer lives at the root, not here: cli may not import
            # views (the layer tripwire), so the bridge to the transcription lens
            # is a root module the runner references (docs/…§4). Import is lazy —
            # `import painted.cli` stays views-free until a bare tool actually runs.
            from .._transcription import transcription_renderer

            self.renderer = transcription_renderer

        # Normalize the four forms into the one record dispatch consults (§3–4).
        # Order mirrors the declaration precedence: an explicit height_renderer=
        # first (the only accepting arm), then the (data, fidelity, width) forms
        # (an authored renderer= or the transcription default installed just
        # above), then the legacy (ctx, data) render=. Dispatch never inspects
        # the callable's arity — the arm is this standing fact.
        if self.height_renderer is not None:
            self._binding = _RendererBinding(
                self.height_renderer, accepts_height=True, legacy=False
            )
        elif self.renderer is not None:
            self._binding = _RendererBinding(self.renderer, accepts_height=False, legacy=False)
        else:
            assert self.render is not None  # transcription filled renderer otherwise
            self._binding = _RendererBinding(self.render, accepts_height=False, legacy=True)

        if self.live_delivery not in ("inplace", "surface"):
            raise DeclarationError(
                f"live_delivery must be 'inplace' or 'surface', got {self.live_delivery!r}"
            )

        # ref_schemes=: the static sequence form validates now, at
        # construction (§7) — frozen into `_ref_schemes_static` so every
        # bracket reads that copy, never the caller-owned sequence again
        # (starts-clean-never-fires; a post-construction mutation must not
        # be able to reopen it). The callable form can't start clean; it
        # evaluates per fetch, at dispatch. Anything that is neither a
        # Sequence nor callable — a set, an iterator, a bare RefScheme —
        # is a malformed declaration, faulted here too, not left to crash
        # with an unrelated "not callable" TypeError at render time.
        if self.ref_schemes is not None:
            if isinstance(self.ref_schemes, Sequence):
                self._ref_schemes_static = self._validate_ref_schemes(
                    self.ref_schemes, error_type=DeclarationError, context="ref_schemes="
                )
            elif not callable(self.ref_schemes):
                raise DeclarationError(
                    "ref_schemes= must be a Sequence of RefScheme or a callable "
                    f"of state, got {self.ref_schemes!r}"
                )

        # The delivery's single NO_COLOR read (§9.1), set for the duration of one
        # dispatch by ``_host_scope`` and reset on its exit. ``None`` outside a
        # dispatch means "resolve ambiently" — the behavior a direct ``_run_static``
        # test call still sees.
        self._delivery_no_color: bool | None = None

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
            return self._emit_refusal(ctx, exc)

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
        # -i is honest for every command now (HOST_RUNG_DESIGN §1): the host rung
        # mounts *any* renderer binding into an interactive Surface, so INTERACTIVE
        # always does something on a TTY — the mode-filtering rationale
        # (docs/MODE_RESOLUTION.md: hide -i when it is a no-op) is satisfied by the
        # capability existing, not by gating. A custom INTERACTIVE handler still
        # wins the dispatch (the escape), and a surface stream still converges -i
        # onto StreamSurface; off a TTY, -i falls back to LIVE.
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
    def _validate_ref_schemes(
        schemes: object, *, error_type: type[Exception], context: str
    ) -> tuple[RefScheme, ...]:
        """Validate a ref_schemes collection, raising ``error_type`` on any
        registry-shape violation: not a sequence, a non-``RefScheme``
        element, or a duplicate name (§7). One check, two fault classes —
        the static declaration (``error_type=DeclarationError``) and a
        callable's returned result (``error_type=ContractError``) share the
        same shape rules but fire at different times for different parties.
        """
        from ..refs import RefScheme

        # A shape check, not a duck-typed `tuple(...)` — a set, a generator,
        # or any other one-shot/unordered iterable is not the declared
        # Sequence[RefScheme] shape and must fault here, on both routes
        # (static and callable-result), rather than being silently accepted
        # and misbehaving later (§7).
        if not isinstance(schemes, Sequence):
            raise error_type(f"{context} must be a Sequence of RefScheme, got {schemes!r}")
        seen: set[str] = set()
        validated: list[RefScheme] = []
        for scheme in schemes:
            if not isinstance(scheme, RefScheme):
                raise error_type(f"{context} element {scheme!r} is not a RefScheme")
            if scheme.name in seen:
                raise error_type(f"RefScheme {scheme.name!r} is declared twice")
            seen.add(scheme.name)
            validated.append(scheme)
        return tuple(validated)

    def _resolve_ref_schemes(self, state: T) -> tuple[RefScheme, ...] | None:
        """Resolve the declared ``ref_schemes=`` against ``state`` for one
        render+serialize bracket (§7). ``None`` means nothing was declared —
        the caller installs no bracket, so ambient ``use_refs`` state an app
        set itself keeps flowing. A static sequence, already validated at
        construction, returns unchanged (including empty). A callable
        evaluates now, against this fetch's state — a raising callable
        propagates unchanged (the caller's render-error path handles it); an
        invalid result faults ``ContractError``, before any ``use_refs`` call.
        """
        ref_schemes = self.ref_schemes
        if ref_schemes is None:
            return None
        if isinstance(ref_schemes, Sequence):
            # The static form: return the tuple frozen at construction, never
            # re-read or re-validate the caller-owned sequence — a
            # post-construction mutation must not reopen what already
            # started clean (§3's defensive-copy ruling).
            assert (
                self._ref_schemes_static is not None
            )  # set alongside this branch, in __post_init__
            return self._ref_schemes_static

        from ..core.errors import ContractError

        schemes = ref_schemes(state)  # app code — raises unchanged
        return self._validate_ref_schemes(
            schemes, error_type=ContractError, context="ref_schemes= callable result"
        )

    @staticmethod
    def _ref_scope(schemes: tuple[RefScheme, ...] | None) -> AbstractContextManager[None]:
        """The runner-owned bracket for a resolved scheme set (§7).

        ``None`` (nothing declared) installs no bracket at all — a no-op
        context manager, so ambient state flows through untouched. A
        (possibly empty) tuple REPLACEs the registry for the scope's
        duration via ``use_refs``, restoring prior ambient state on exit.
        """
        if schemes is None:
            return nullcontext()
        from ..refs import use_refs

        return use_refs(*schemes)

    def _handler_ref_scope(self) -> AbstractContextManager[None]:
        """The bracket around a custom mode handler (§7).

        Handler paths are excluded from callable evaluation — the framework
        neither fetches nor renders there, so a callable has no state
        boundary to evaluate against. A static sequence needs no state and
        installs around the handler invocation like any other declared
        scope; the handler owns its own ``use_refs`` scope beyond that, like
        any direct library user.
        """
        if self._ref_schemes_static is None:
            return nullcontext()
        return self._ref_scope(self._ref_schemes_static)

    @staticmethod
    def _current_columns() -> int:
        """The terminal's current column count, re-read per live frame.

        The width sibling of ``InPlaceRenderer._viewport_rows``: both re-read
        ambient geometry (``shutil.get_terminal_size``) each frame so a
        mid-run resize re-enters the renderer as changed input (§6). Gated by
        the offer rule — on a non-TTY the read is discarded for ``None``.
        """
        return shutil.get_terminal_size().columns

    def _render(
        self, ctx: CliContext, state: T, offered: int | None, *, height: int | None = None
    ) -> Block:
        """Produce the content Block, dispatching the declared render contract.

        The one seam every delivery-path render funnels through — it reads the
        binding record (§3–4), never the callable's arity. The three call shapes
        differ in exactly one place:

          * the ``(data, fidelity, width)`` contract (``renderer=`` or the
            transcription default, §1) — state, the compiled Fidelity intact, and
            the ``offered`` width the caller resolved through ``_offered_width``;
          * the height-aware contract (``height_renderer=``, §4) — the same three
            plus a keyword-only ``height`` *offer*, always passed explicitly so
            omission (``height=None``) is an observable decision, never Python's
            default. This seam is the **offer site**: after a height-aware call it
            enforces §5 exactness on the result, and a negative offer is a host
            bug faulted *before* the call, never handed to the renderer;
          * legacy ``render=`` — the whole context, reading ``ctx.width`` itself.

        The offer matrix's three rows (§3) fall out of the binding: an undeclared
        renderer is never handed the ``height`` keyword (it has none); a declared
        renderer always is. ``height`` defaults to ``None`` because every S1
        delivery is gated-off (the Q7 STATIC-TTY fence, off-TTY always) — a
        gated-on delivery slice passes an integer ``H`` here instead.

        The width offer is computed *per offer* at the caller, not here: static
        and non-streaming callers pass ``_offered_width(ctx)``; the in-place live
        loop re-reads geometry each frame; the alt-screen adapter passes the
        surface buffer's current width (§6). This seam only forwards it.
        """
        binding = self._binding
        if binding.accepts_height:
            # §5: a negative offer is a host bug — fail loudly *before* the
            # renderer runs (never hand a bogus allocation to app code).
            if height is not None and height < 0:
                raise ContractError(
                    f"height offer must be a non-negative integer, got {height!r} "
                    "(a negative allocation is a host bug — HOST_RUNG_DESIGN §5)"
                )
            block = binding.call(state, ctx.fidelity, offered, height=height)
            self._verify_height(block, height)  # §5 exactness at the offer site
            return block
        if binding.legacy:
            return binding.call(ctx, state)
        return binding.call(state, ctx.fidelity, offered)

    @staticmethod
    def _verify_height(block: Block, height: int | None) -> None:
        """Enforce the offered-arm exactness contract at the offer site (§5).

        The conditional honesty property: when the host offers an integer ``H``,
        the height-aware renderer's Block must have exactly ``H`` rows. This is
        the offer-site helper the gated-on delivery slices (bounded LIVE,
        interactive) call after their own ``_render``; in S1 no shipped path
        offers ``H``, so it is exercised only by tests.

          * ``height is None`` — the omitted arm (natural sizing); no check.
          * ``H == 0`` — a valid offer (``Block.empty(w, 0)``); requires an exact
            zero-height Block, evidence waived (§5).
          * ``H < 0`` — a host bug; faults even here (the offer should have been
            rejected pre-call, but the helper is complete on its own).
          * ``block.height != H`` — a contract violation: the host **never** crops
            or pads the result into apparent compliance (silent padding would mask
            the final-renderer exactness violation of law 5; silent cropping could
            discard content unmarked, law 6). It faults loudly instead.

        Reads ``block.height`` only — no renderer-type import needed, so ``cli``
        import discipline stays intact.
        """
        if height is None:
            return
        if height < 0:
            raise ContractError(
                f"height offer must be a non-negative integer, got {height!r} "
                "(a negative allocation is a host bug — HOST_RUNG_DESIGN §5)"
            )
        if block.height != height:
            raise ContractError(
                f"height-aware renderer returned {block.height} rows for an offer of "
                f"{height} (the offered arm must return exactly H rows; the host does "
                "not crop or pad into compliance — HOST_RUNG_DESIGN §5)"
            )

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
            # The error object keeps its machine-readable shape but rides
            # stderr like every other error — stdout stays a clean data
            # channel on failure, so `tool --json > file` never writes an
            # error that looks like data (ruled 2026-08-13, unconditional).
            message = self._exception_message(exc)
            print(json.dumps({"error": message}), file=sys.stderr)
            return 1
        try:
            data = asdict(state)  # type: ignore[arg-type]  # T may be dataclass
        except TypeError:
            data = state
        print(json.dumps(data, default=str))
        return 0

    def _host_scope(self, ctx: CliContext) -> ExitStack:
        """Install the host capability bracket for the framework render paths (§9.2–9.4).

        Capabilities are *standing* facts for the run — a single snapshot resolved
        from ``stdout`` (§9.3) — so one bracket spans STATIC and every LIVE
        sub-path: an in-place loop, a plain-cadence stream, the alt-screen surface,
        and its scrollback deposit all render inside it (a ContextVar set here is
        inherited by the asyncio tasks the live hosts spawn, per §9.2). The paired
        ASCII-safe ``IconSet`` honors §9.4: a host narrowing ``glyph=False`` must
        also install an ASCII-safe glyph vocabulary, so the two never disagree.
        Custom handlers own their own bracket (§9.3) and never reach here.

        The one-snapshot rule (§9.1): NO_COLOR is read **once** here and stored for
        the delivery, so the ``color`` facet and every serializer this dispatch
        opens (STATIC ``print_block``, the in-place LIVE writer, the alt-screen
        deposit) share the exact same value — a mid-run env change cannot split
        content choice from serialization.
        """
        from ..capabilities import (
            resolve_host_capabilities,
            resolve_no_color,
            use_capabilities,
        )

        no_color = resolve_no_color()
        caps = resolve_host_capabilities(sys.stdout, use_ansi=ctx.use_ansi, no_color=no_color)
        stack = ExitStack()
        self._delivery_no_color = no_color
        stack.callback(setattr, self, "_delivery_no_color", None)
        stack.enter_context(use_capabilities(caps))
        if not caps.glyph:
            from ..icon_set import ASCII_ICONS, use_icons

            stack.enter_context(use_icons(ASCII_ICONS))
        return stack

    def _dispatch(self, ctx: CliContext) -> int:
        """Dispatch to appropriate output mechanism."""
        # A custom handler replaces the framework render path, so it owns its own
        # capability bracket (§9.3, mirroring refs ownership §7) — the framework
        # installs nothing on its behalf. Its static ref scope still applies.
        if self.handlers and ctx.mode in self.handlers:
            with self._handler_ref_scope():
                result = self.handlers[ctx.mode](ctx)
            return result if isinstance(result, int) else 0

        # Framework render paths (STATIC, LIVE, INTERACTIVE-fallback): the host
        # capability bracket wraps every offer these paths make to the renderer.
        with self._host_scope(ctx):
            if ctx.mode == OutputMode.STATIC:
                return self._run_static(ctx)

            elif ctx.mode == OutputMode.LIVE:
                return self._run_live(ctx)

            elif ctx.mode == OutputMode.INTERACTIVE:
                # No custom handler (that was intercepted above): the host rung.
                return self._run_interactive(ctx)

            return 0

    def _render_and_deliver(self, ctx: CliContext, state: T) -> int:
        """Resolve ref_schemes, render, and print — shared by the static
        dispatch and the non-streaming live path (both fetch once, render
        once). Ref-scheme resolution shares the render-error path (§7): a
        resolution fault — a raising callable, or an invalid result faulting
        ``ContractError`` — reports through the same exit code as a renderer
        fault, never the fetch path. The resolved bracket spans render
        through the ``print_block`` serialization that resolves refs.
        """
        from ..core.writer import print_block

        try:
            schemes = self._resolve_ref_schemes(state)
        except Exception as exc:
            self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
            return 2

        with self._ref_scope(schemes):
            try:
                block = self._render(ctx, state, self._offered_width(ctx))
            except Exception as exc:
                self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
                return 2
            print_block(block, use_ansi=ctx.use_ansi, no_color=self._delivery_no_color)
        return 0

    def _run_static(self, ctx: CliContext) -> int:
        """Run with static output (print_block)."""
        try:
            state = self._do_fetch(ctx)
        except Exception as exc:
            self._emit_error(ctx, self._fetch_error_block(ctx, exc), exc)
            return 1

        return self._render_and_deliver(ctx, state)

    def _run_live(self, ctx: CliContext) -> int:
        """Run with InPlaceRenderer."""
        import asyncio

        from ..inplace import InPlaceRenderer
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
                    last_schemes: tuple[RefScheme, ...] | None = None
                    try:
                        async for state in self._stream_iter(ctx):
                            try:
                                # Non-ANSI cadence: this branch retains only
                                # the last Block and prints it once at the
                                # end — a cadence choice, not a per-frame
                                # viewport. The offer is still per-frame (§6):
                                # on a pipe it is None; on a forced-plain TTY
                                # it is the *current* columns, re-read each
                                # state like every other live offer — --plain
                                # drops ANSI, not the viewport, so a mid-run
                                # resize re-enters here too, never a stale
                                # detection-time ctx.width.
                                # ref_schemes evaluates per fetched state (§7)
                                # even though only the last one is ever
                                # serialized — the state that actually renders
                                # is the one whose schemes travel to the print
                                # below.
                                schemes = self._resolve_ref_schemes(state)
                                with self._ref_scope(schemes):
                                    last_block = self._render(
                                        ctx,
                                        state,
                                        self._offered_width(ctx, self._current_columns()),
                                    )
                                last_schemes = schemes
                            except Exception as exc:
                                self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
                                return 2
                    except PromptAbort:
                        # A prompt abort is not a graceful stop — propagate it
                        # out of run_cli like a static-mode abort (§7).
                        raise
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        return 0
                    except Exception as exc:
                        self._emit_error(ctx, self._fetch_error_block(ctx, exc), exc)
                        return 1
                    if last_block is not None:
                        with self._ref_scope(last_schemes):
                            print_block(last_block, use_ansi=False)
                    return 0

                meter = None
                if self.live_meter:
                    from .live_meter import LiveMeter

                    meter = LiveMeter()
                from .prompts import PromptContractError

                # The in-place writer serializes under the delivery's one NO_COLOR
                # snapshot (§9.1) — the same value the capability bracket used.
                with InPlaceRenderer(no_color=self._delivery_no_color) as renderer:
                    try:
                        async for state in self._stream_iter(ctx):
                            if meter is not None:
                                meter.start()
                            try:
                                schemes = self._resolve_ref_schemes(state)
                            except Exception as exc:
                                # The stated exception to errors-ride-stderr:
                                # inside an in-place live region (styled TTY
                                # only), the error renders as the final frame —
                                # the region is the display the user is
                                # watching, and finalize() keeps it visible.
                                renderer.render(self._render_error_block(ctx, exc))
                                renderer.finalize()
                                return 2
                            # The bracket spans render through the write
                            # below — InPlaceRenderer.render() writes
                            # synchronously (its own "flush"), no separate
                            # callback the way the alt-screen Surface has (§7).
                            with self._ref_scope(schemes):
                                try:
                                    # Re-offer current geometry each frame: the
                                    # in-place host owns a live viewport, so a
                                    # mid-run resize re-enters the renderer as
                                    # changed input (§6).
                                    block = self._render(
                                        ctx,
                                        state,
                                        self._offered_width(ctx, self._current_columns()),
                                    )
                                except PromptContractError:
                                    # A refusal never renders into the live region —
                                    # propagate to the outer finalize + the seam.
                                    raise
                                except Exception as exc:
                                    # Same stated stderr exception as the
                                    # resolution fault above: the error is the
                                    # live region's final frame.
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

        return self._render_and_deliver(ctx, state)

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

        # The frame bracket (§7): StreamSurface calls this once per
        # successful fetch event, eagerly, in its own consumer task — never
        # here at the ContextVar-install seam. The ContextVar itself is
        # installed later, in the Surface's render task, from the resolved
        # result this closure returns; the resolver call never happens
        # there. None when nothing was declared, so StreamSurface installs
        # no bracket at all.
        def resolve_ref_schemes(state: T) -> tuple[RefScheme, ...]:
            schemes = self._resolve_ref_schemes(state)
            assert schemes is not None  # ref_schemes is declared — guarded below
            return schemes

        resolve_fn: Callable[[T], tuple[RefScheme, ...]] | None = (
            resolve_ref_schemes if self.ref_schemes is not None else None
        )

        surface = StreamSurface(
            render=offer_frame,
            fetch_stream=lambda: self._stream_iter(ctx),
            live_meter=self.live_meter,
            resolve_ref_schemes=resolve_fn,
            # A fresh content identity per run: the stream is "the same document"
            # growing across yields, so a resize never resets scroll and only a new
            # run starts fresh (§6 fallback 5). The inward seam (§7) reports the
            # viewport as content grows / the user scrolls — the follow path.
            content_id=object(),
            on_host_event=self.on_host_event,
            # The one-snapshot rule (§9.1): the surface's writer is CONSTRUCTED
            # from the delivery's already-resolved NO_COLOR policy, not a fresh
            # env read. _host_scope resolved it once (self._delivery_no_color);
            # threading it here makes _frame_scope's writer-derived capability
            # bracket equal the outer host bracket by construction — a mid-run
            # NO_COLOR flip after resolution can no longer split the frame's
            # content choice or its serialization from the delivery snapshot.
            no_color=self._delivery_no_color,
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
            # Funnel through _emit_error like every other mode: stderr, at
            # stderr's own fidelity, under the delivery's one NO_COLOR
            # snapshot (§9.1).
            if surface.error_kind == "render":
                self._emit_error(ctx, self._render_error_block(ctx, surface.error), surface.error)
                return 2
            self._emit_error(ctx, self._fetch_error_block(ctx, surface.error), surface.error)
            return 1

        # Gate on frame *presence*, not the state payload: renderer data is
        # unconstrained, so a final fetched state of None is a legitimate
        # frame that still gets its promised scrollback deposit (and its
        # ref bracket). Only a run where nothing was ever fetched skips it.
        final_frame = surface.last_frame
        if final_frame is not None:
            last_state, last_schemes = final_frame
            # The deposit is itself a separate serialization event, but it
            # reuses the schemes already resolved for the last fetched
            # state — never re-evaluates the callable (§7: "the final
            # deposit serializes under the last state's schemes", not a
            # fresh evaluation). The pair is carried atomically
            # (StreamSurface), so state and schemes can never desync. A
            # resolution fault would already have surfaced as
            # surface.error above; by construction there is nothing left
            # to fail here.
            with self._ref_scope(last_schemes):
                try:
                    # The deposit is itself an offer — the runner's final print
                    # to the normal screen (a TTY; the surface path was gated
                    # on it). It re-reads *current* columns like every other
                    # offer (§§5–6): a resize during the alt-screen session
                    # moved the geometry, so detection-time ctx.width would
                    # deposit at a stale width.
                    block = self._render(
                        ctx,
                        last_state,
                        self._offered_width(ctx, self._current_columns()),
                    )
                except PromptContractError:
                    raise
                except Exception as exc:
                    self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
                    return 2
                if self.live_meter:
                    # The deposit carries the run's final gauge — what this show cost.
                    block = surface.meter.dress(block)
                # The scrollback deposit is the alt-screen path's STATIC print —
                # serialized under the delivery's one NO_COLOR snapshot (§9.1).
                print_block(block, use_ansi=ctx.use_ansi, no_color=self._delivery_no_color)
        return 0

    def _run_interactive(self, ctx: CliContext) -> int:
        """Resolve the INTERACTIVE mode to a delivery (HOST_RUNG_DESIGN §1).

        A custom ``handlers[INTERACTIVE]`` was already intercepted in
        ``_dispatch`` (the escape), so this is the framework path. Three
        resolutions, gated the way the surrounding live paths already gate:

          * **not a usable TTY** (piped, forced-plain) — no alt screen is
            possible, so fall back to LIVE, exactly as INTERACTIVE did before the
            host rung existed (preserves the run-and-exit / one-shot behavior a
            non-TTY ``-i`` had).
          * **a declared stream** — streaming delivery is the live tier's job
            (surface or in-place); ``-i`` keeps converging onto it. The single
            *fetch* host rung would drop the stream, and bringing ``follow`` home
            through the framework is the inward-seam's future work (§7), not this.
          * **otherwise** — the host rung: mount the binding into ``HostSurface``.
        """
        if not (ctx.is_tty and ctx.use_ansi):
            return self._run_live(ctx)
        if self.fetch_stream is not None:
            return self._run_live(ctx)
        return self._run_host(ctx)

    def _run_host(self, ctx: CliContext) -> int:
        """Mount the renderer binding into the interactive host rung (§6).

        One fetch, then an alt-screen ``HostSurface`` scrolls / re-renders over it
        (the omitted arm's viewport, or the offered arm's per-frame ``height=H``
        offer). The offer, exactness (§5), and the offer matrix all stay in
        ``_render`` — the surface is handed a ``(width, height) → Block`` closure
        over it, the same shape the alt-screen stream path hands ``StreamSurface``,
        so the renderer itself stays pure and signature-identical.

        Fetch and ref-scheme resolution route errors the same way the one-shot
        paths do (fetch fault → exit 1, resolution fault → exit 2, a prompt
        refusal / abort through the single seam). ``ref_schemes=`` installs once
        around the whole session — a single fetched state has one scheme set, so
        there is no per-frame resolution the way a stream needs (§7).
        """
        from .prompts import PromptAbort

        try:
            state = self._do_fetch(ctx)
        except PromptAbort:
            raise  # propagates out of run_cli, like every other mode
        except Exception as exc:
            self._emit_error(ctx, self._fetch_error_block(ctx, exc), exc)
            return 1

        try:
            schemes = self._resolve_ref_schemes(state)
        except Exception as exc:
            self._emit_error(ctx, self._render_error_block(ctx, exc), exc)
            return 2

        binding = self._binding

        def render_frame(width: int, height: int | None) -> Block:
            # The offer site: `_render` reads the binding (§3 matrix), applies the
            # width-offer rule, and — on the offered arm — verifies §5 exactness.
            # The omitted arm passes height=None (an undeclared binding never even
            # sees the keyword). Width is the frame's current geometry each call.
            return self._render(ctx, state, self._offered_width(ctx, width), height=height)

        # A fresh identity per session: "the same document" across resizes (so a
        # resize never resets scroll), a new one only for a new run (§6 fallback 5).
        content_id = object()

        from .stream_surface import run_host_surface

        with self._ref_scope(schemes):
            return run_host_surface(
                render=render_frame,
                accepts_height=binding.accepts_height,
                content_id=content_id,
                inputs=ctx.fidelity,
                no_color=self._delivery_no_color,
                # The inward seam (§7). On the offered arm HostSurface builds no
                # viewport controller, so a declared sink there simply never fires.
                on_host_event=self.on_host_event,
            )

    def _emit_error(self, ctx: CliContext, block: Block, exc: Exception) -> None:
        """Render a fetch/render error to stderr — errors never ride stdout.

        The one funnel every mode's error rendering goes through: stdout stays
        a clean data channel on failure in every format (the same contract the
        refusal seam established for prompts, design §8), so ``tool | jq`` and
        ``output=$(tool)`` never parse an error as data. ANSI follows stderr's
        own plane — ``stderr_is_tty`` overridden by the ``--plain`` request —
        never the resolved stdout format, exactly like ``_emit_refusal``.

        A prompt refusal is *not* ordinary: it re-raises here so the single
        refusal seam in ``run()`` routes it (with its exit-1 contract) instead.

        The error writer serializes under the delivery's one NO_COLOR snapshot
        (§9.1) — never a second env read that a mid-run env change (a renderer
        that flips NO_COLOR and then raises) could desync from the delivery's
        own policy.
        """
        from .prompts import PromptContractError

        if isinstance(exc, PromptContractError):
            raise exc
        from ..core.writer import print_block

        print_block(
            block,
            sys.stderr,
            use_ansi=ctx.stderr_use_ansi,
            no_color=self._delivery_no_color,
        )

    def _emit_refusal(self, ctx: CliContext, exc: Exception) -> int:
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

        print_block(self._fetch_error_block(ctx, exc), sys.stderr, use_ansi=ctx.stderr_use_ansi)
        return 1

    @staticmethod
    def _exception_message(exc: Exception) -> str:
        message = str(exc).strip()
        return message or type(exc).__name__

    @staticmethod
    def _fetch_error_block(ctx: CliContext, exc: Exception) -> Block:
        from ..core.cell import Style

        try:
            from ..palette import current_palette

            style = current_palette().error
        except Exception:
            style = Style(fg="red")

        message = CliRunner._exception_message(exc)
        return CliRunner._multiline_error_block(message, style, ctx.width)

    @staticmethod
    def _render_error_block(ctx: CliContext, exc: Exception) -> Block:
        from ..core.cell import Style

        message = str(exc).strip()
        if message:
            text = f"{type(exc).__name__}: {message}"
        else:
            text = type(exc).__name__

        return CliRunner._multiline_error_block(text, Style(), ctx.width)

    @staticmethod
    def _multiline_error_block(message: str, style: Style, width: int) -> Block:
        """An error message as a Block, newlines preserved.

        A consumer's error message owns its line structure (a did-you-mean
        block is three lines by design) — flattening it is the framework
        rewriting declared meaning. Each line word-wraps within the width;
        ``Block.text`` is single-line by design, so multi-line is composed.
        """
        from ..core.block import Block, Wrap
        from ..core.compose import join_vertical

        width = max(1, width)
        lines = message.split("\n")
        return join_vertical(
            *(Block.text(line, style, width=width, wrap=Wrap.WORD) for line in lines)
        )


# Four published call forms — the truth type checkers carry, so no caller ever
# sees `fetch` as optional even though the runtime signature says None (the
# requiredness lives in construction). One overload per call form: the three
# authored-renderer contracts (legacy positional `render`; keyword `renderer=`;
# keyword `height_renderer=`, HOST_RUNG_DESIGN §4) and the *neither* form (the
# transcription default, §4). Each requires `fetch`, and no overload lists more
# than one renderer keyword — so declaring two at once matches none, the type
# analog of the construction-time mutual-exclusion DeclarationError. See
# RENDERER_CONTRACT_DESIGN.md §§3, 12.
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
    ref_schemes: Sequence[RefScheme] | Callable[[T], Sequence[RefScheme]] | None = ...,
    on_host_event: HostEventSink | None = ...,
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
    ref_schemes: Sequence[RefScheme] | Callable[[T], Sequence[RefScheme]] | None = ...,
    on_host_event: HostEventSink | None = ...,
) -> int: ...


# The height-aware form — keyword `height_renderer=` (HOST_RUNG_DESIGN §4). A
# complete declaration on its own (no `renderer=` needed); it lists no other
# renderer keyword, so pairing it with render=/renderer= matches no overload.
@overload
def run_cli(
    args: list[str],
    *,
    height_renderer: HeightRenderer[T],
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
    ref_schemes: Sequence[RefScheme] | Callable[[T], Sequence[RefScheme]] | None = ...,
    on_host_event: HostEventSink | None = ...,
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
    ref_schemes: Sequence[RefScheme] | Callable[[T], Sequence[RefScheme]] | None = ...,
    on_host_event: HostEventSink | None = ...,
) -> int: ...


def run_cli(
    args: list[str],
    render: Callable[[CliContext, T], Block] | None = None,
    fetch: Callable[..., T] | None = None,
    *,
    renderer: Renderer[T] | None = None,
    height_renderer: HeightRenderer[T] | None = None,
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
    ref_schemes: Sequence[RefScheme] | Callable[[T], Sequence[RefScheme]] | None = None,
    on_host_event: HostEventSink | None = None,
) -> int:
    """Run a CLI tool with zoom/mode/format handling.

    Declare at most one renderer contract:

      * ``renderer=`` — the contract (§1): ``(data, fidelity, width) → Block``,
        the semantic renderer given only its three inputs. Keyword-only.
      * ``height_renderer=`` — the height-aware contract (HOST_RUNG_DESIGN §4):
        ``(data, fidelity, width, *, height) → Block``, the offered arm of the
        dual allocation contract. Keyword-only, mutually exclusive with *all*
        authored-renderer forms.
      * ``render=`` — legacy ``(ctx, data) → Block``, optional-positional so
        existing ``run_cli(args, render, fetch)`` call sites keep working. Kept
        through a deprecation window; no runtime warning until 0.12 (§3).
      * *neither* — the framework renders by **transcription** (§4): the fetched
        data is transcribed through the same contract. ``tags=`` is unavailable
        on this form (transcription cannot consume declared facets), and
        declaring it raises ``DeclarationError``.

    Passing more than one renderer form raises ``DeclarationError`` at
    construction — as does a missing ``fetch``.

    Args:
        args: Command-line arguments (sys.argv[1:])
        render: Legacy render callback ``(ctx, data) → Block`` (deprecation window)
        renderer: The renderer contract ``(data, fidelity, width) → Block`` (§1)
        height_renderer: The height-aware renderer contract
            ``(data, fidelity, width, *, height) → Block`` (HOST_RUNG_DESIGN §4)
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
        ref_schemes: Declared ref schemes (docs/RENDERER_CONTRACT_DESIGN.md §7)
            — a static sequence of RefScheme, or a callable of state evaluated
            per fetch. Installs as the runner-owned bracket around render and
            serialization, replacing whatever ambient use_refs state was
            active; absent, the framework installs nothing
        on_host_event: The inward host-event sink (docs/HOST_RUNG_DESIGN.md §7)
            — a ``HostEvent -> None`` callback invoked synchronously, exactly
            once per event, when painted owns a viewport (the interactive host
            rung and the alt-screen streaming tier). On every other route
            (STATIC, pipe, in-place LIVE, the offered arm) declaring it is legal
            and it never fires. A handler exception fails the active host
            delivery loudly (never swallowed, never rerouted to Surface.emit)

    Returns:
        Exit code (0 for success)
    """
    return CliRunner(
        render=render,
        renderer=renderer,
        height_renderer=height_renderer,
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
        ref_schemes=ref_schemes,
        on_host_event=on_host_event,
    ).run(args)
