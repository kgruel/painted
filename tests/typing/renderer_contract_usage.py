"""Static-typing enforcement for the renderer contract's published surface.

This file is **type-checked by ty, never executed** — pytest does not collect it
(no ``test_`` name), and all usage lives inside an uncalled function so importing
it has no side effects (the calls below would otherwise *run* ``run_cli``). It
lives in the curated ``tests/typing/`` tree the gate points ty at, alongside
``src/``. Its job is to pin two guarantees the runtime tests cannot see:

  1. The `@overload`s reach consumers through **every public facade** — the root
     ``from painted import run_cli`` that CLAUDE.md Level 2 teaches, plus
     ``from painted.cli import run_cli`` and ``from painted.core import Renderer``.
     If any facade regressed to exposing ``run_cli`` as ``Any`` (dropping its
     ``TYPE_CHECKING`` re-export), the ``assert_type(..., int)`` below would fail
     ``type-assertion-failure`` and break the gate (`int` and `Any` are not
     equivalent).
  2. Every authored-renderer form (``render=``, ``renderer=``,
     ``height_renderer=``) **requires ``fetch``**, and no overload lists two
     renderer keywords at once. Omitting ``fetch`` or pairing two forms matches
     no overload; the negative cases carry a load-bearing
     ``type: ignore[no-matching-overload]`` — remove the requiredness (or the
     mutual exclusion) and the suppressed error vanishes, surfacing the ignore
     as unused.

See docs/RENDERER_CONTRACT_DESIGN.md §§3, 11.
"""

from __future__ import annotations

from typing import assert_type

from painted import Block, CliContext, Fidelity, RefScheme, Style
from painted import HeightRenderer as RootHeightRenderer  # the taught root facade
from painted import Renderer as RootRenderer  # the taught root facade
from painted import run_cli as root_run_cli
from painted.cli import HeightRenderer as CliHeightRenderer, run_cli
from painted.core import HeightRenderer, Renderer


def _renderer(data: object, fidelity: Fidelity, width: int | None) -> Block:
    return Block.text("x", Style())


def _height_renderer(
    data: object, fidelity: Fidelity, width: int | None, *, height: int | None
) -> Block:
    return Block.text("x", Style())


def _legacy(ctx: CliContext, data: object) -> Block:
    return Block.text("x", Style())


def _fetch() -> str:
    return "x"


def _schemes_for(state: str) -> list[RefScheme]:
    return [RefScheme("fact", lambda v: v)]


def _typecheck() -> None:
    """Never called — type checkers analyze the body, nothing runs it."""
    # Renderer is a usable alias for the contract shape.
    typed_renderer: Renderer[str] = _renderer
    # HeightRenderer is a usable Protocol for the height-aware shape (HOST_RUNG §4),
    # reached through every facade (root / painted.cli / painted.core).
    typed_height: HeightRenderer[str] = _height_renderer
    cli_typed_height: CliHeightRenderer[str] = _height_renderer
    root_typed_height: RootHeightRenderer[str] = _height_renderer

    # positive: all published forms type-check and return int
    assert_type(run_cli([], renderer=_renderer, fetch=_fetch), int)  # keyword renderer=
    assert_type(run_cli([], _legacy, _fetch), int)  # legacy positional
    assert_type(run_cli([], render=_legacy, fetch=_fetch), int)  # legacy keyword
    assert_type(run_cli([], renderer=typed_renderer, fetch=_fetch), int)  # via Renderer alias
    assert_type(run_cli([], fetch=_fetch), int)  # neither → transcription default (§4)
    # height_renderer= is its own published form (HOST_RUNG §4), fetch required.
    assert_type(run_cli([], height_renderer=_height_renderer, fetch=_fetch), int)
    assert_type(run_cli([], height_renderer=typed_height, fetch=_fetch), int)  # via the Protocol
    _ = (cli_typed_height, root_typed_height)  # the facades carry the same shape

    # ref_schemes= (§7) reaches every published call form: a static sequence
    # and a callable of state, both keyword-only, alongside any renderer form.
    assert_type(
        run_cli([], renderer=_renderer, fetch=_fetch, ref_schemes=[RefScheme("fact", str)]), int
    )
    assert_type(run_cli([], _legacy, _fetch, ref_schemes=_schemes_for), int)
    assert_type(run_cli([], fetch=_fetch, ref_schemes=[]), int)

    # negative: fetch is required; omitting it matches no overload. The ignore is
    # load-bearing — it suppresses a real no-matching-overload error.
    run_cli([], renderer=_renderer)  # type: ignore[no-matching-overload]
    run_cli([], _legacy)  # type: ignore[no-matching-overload]
    # ... and there is no overload for passing two renderer forms at once —
    # the type analog of the construction-time mutual-exclusion DeclarationError.
    run_cli([], _legacy, _fetch, renderer=_renderer)  # type: ignore[no-matching-overload]
    run_cli(  # type: ignore[no-matching-overload]
        [], renderer=_renderer, height_renderer=_height_renderer, fetch=_fetch
    )
    run_cli([], height_renderer=_height_renderer)  # type: ignore[no-matching-overload]

    # The taught root facade (`from painted import run_cli`) carries the same
    # overload/alias truth — not just the painted.cli/painted.core paths.
    root_typed: RootRenderer[str] = _renderer
    assert_type(root_run_cli([], renderer=root_typed, fetch=_fetch), int)
    assert_type(root_run_cli([], _legacy, _fetch), int)
    root_run_cli([], renderer=_renderer)  # type: ignore[no-matching-overload]
