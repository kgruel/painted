"""CELL — raw-in-place interactive prompt rendering, the top rung.

Delivery-layer machinery, beside ``inplace.py`` and ``keyboard.py``. A CELL
prompt is one of the frozen-state view components the TUI side already grew —
``ListState`` (selection, scroll-into-view) for a choice, ``TextInputState``
(cursor editing) for free text — delivered through ``InPlaceRenderer`` on stderr
and driven by ``KeyboardInput``'s blocking read (docs/PROMPTS_DESIGN.md §5). The
prompt subsystem and the ``Surface`` batteries consume the *same* components;
nothing is duplicated across the two interactive rungs.

**Why this lives at the package root, not ``cli/``.** The CELL rung composes the
``painted.views`` components, and ``cli`` may not import ``views`` (the two
sanctioned ``cli`` seams are full). §5's own prescription for a delivery seam is
to extract it *below* the cli boundary — so the loop lives here, at the delivery
layer (root → views is the same edge ``painted``/``display``/``diagnostics``
already take), and ``cli/prompts.py`` reaches it lazily through
``resolve_cell``. This module never imports ``tui/``.

Lifecycle (§7): the live region repaints while open and, on answer, is cleared
so the caller's one static record line lands where it was — the interactive
region *becomes* the record. On abort (Ctrl-C at the read, or an EOF/Ctrl-D key)
the terminal is restored (cbreak exit) *first*, the region is settled, and the
``KeyboardInterrupt`` propagates — never an answer, never the default.
"""

from __future__ import annotations

from typing import Any, Callable, TextIO

from .core.block import Block
from .core.cell import Style
from .core.compose import join_horizontal, join_vertical
from .core.span import Line, Span
from .icon_set import current_icons
from .inplace import InPlaceRenderer
from .keyboard import KeyboardInput
from .palette import current_palette
from .vocabulary import vocab_style
from .views import ListState, TextInputState, list_view, text_input
from .cli.prompts import MISSING, Confirm, Danger, Input, Prompt, Select

__all__ = ["resolve_cell"]

# Ctrl-C is delivered as SIGINT in cbreak (ISIG stays on) and raises at the read;
# these are the byte-level escape hatches that reach us as keys instead — Ctrl-D
# (0x04, not an EOF in cbreak) and a defensive Ctrl-C byte. read_key() returning
# None (a real stream EOF) is the third abort signal, handled in _next_key.
_ABORT_KEYS = ("\x03", "\x04")

_FIELD_WIDTH = 40  # visible columns for an Input field's text_input
_MAX_VISIBLE = 10  # option rows shown before a Select list scrolls


def resolve_cell(
    prompt: Prompt[Any],
    *,
    stdin: TextIO,
    stderr: TextIO,
    key_source: Callable[[], str | None] | None = None,
) -> Any:
    """Render ``prompt`` at the CELL rung on stderr and return its answer.

    ``key_source`` is an injectable blocking key reader (``() -> str | None``,
    ``None`` at EOF) for tests — no real terminal needed. In production it is
    ``KeyboardInput(stream=stdin).read_key``; the renderer is an
    ``InPlaceRenderer`` bound explicitly to ``stderr`` (never the module's
    import-time stdout default — prompt UI draws on stderr, §8).
    """
    renderer = InPlaceRenderer(stream=stderr)
    keyboard = KeyboardInput(stream=stdin) if key_source is None else None
    renderer.__enter__()
    if keyboard is not None:
        keyboard.__enter__()
        read: Callable[[], str | None] = keyboard.read_key
    else:
        assert key_source is not None
        read = key_source

    try:
        answer = _run(prompt, renderer, read)
    except BaseException:
        # Abort ordering (§7): restore the terminal (cbreak exit) FIRST, then
        # settle the region, then let the exception propagate.
        if keyboard is not None:
            keyboard.__exit__()
        renderer.clear()
        renderer.__exit__()
        raise

    # Answer: clear the live region and exit, so the caller's record line lands
    # where the region was — the interactive region becomes the record (§7).
    renderer.clear()
    if keyboard is not None:
        keyboard.__exit__()
    renderer.__exit__()
    return answer


def _next_key(read: Callable[[], str | None]) -> str:
    """Block for the next key; a ``None`` (EOF) or an abort key raises.

    EOF and Ctrl-D are the same abort path as Ctrl-C (which raises at the read
    on its own): never an answer, never a silent fall-through to the default
    (§7). The ``KeyboardInterrupt`` is the shared abort signal the loops let
    propagate to ``resolve_cell``'s restore-then-raise handler.
    """
    key = read()
    if key is None or key in _ABORT_KEYS:
        raise KeyboardInterrupt
    return key


def _run(prompt: Prompt[Any], renderer: InPlaceRenderer, read: Callable[[], str | None]) -> Any:
    if isinstance(prompt, Select):
        return _run_select(prompt, renderer, read)
    if isinstance(prompt, Input):
        return _run_input(prompt, renderer, read)
    if isinstance(prompt, Confirm):
        if prompt.danger is Danger.HARD:
            return _run_hard_confirm(prompt, renderer, read)
        return _run_confirm(prompt, renderer, read)
    raise TypeError(  # pragma: no cover — exhaustive over the three shipped shapes
        f"no CELL renderer for prompt shape {type(prompt).__name__}"
    )


# =============================================================================
# Select — a ListState cursor over the options
# =============================================================================


def _run_select(prompt: Select, renderer: InPlaceRenderer, read: Callable[[], str | None]) -> str:
    choices = prompt.choices
    has_default = prompt.default is not MISSING
    # NONE with a default starts the cursor on it (Enter accepts the default,
    # and it is *visible* under the cursor — no bare-Enter surprise). SOFT has
    # no default; the cursor starts at the top and Enter selects what's shown.
    start = choices.index(str(prompt.default)) if has_default else 0
    visible = min(len(choices), _MAX_VISIBLE)
    state = ListState().with_count(len(choices)).move_to(start).scroll_into_view(visible)

    while True:
        renderer.render(_select_block(prompt, state, visible))
        key = _next_key(read)
        if key in ("up", "k"):
            state = state.move_up().scroll_into_view(visible)
        elif key in ("down", "j"):
            state = state.move_down().scroll_into_view(visible)
        elif key == "home":
            state = state.move_to(0).scroll_into_view(visible)
        elif key == "end":
            state = state.move_to(len(choices) - 1).scroll_into_view(visible)
        elif key == "enter":
            return choices[state.selected]
        # Any other key is ignored — the cursor holds its position.


def _select_block(prompt: Select, state: ListState, visible: int) -> Block:
    palette = current_palette()
    choices = prompt.choices
    default_idx = choices.index(str(prompt.default)) if prompt.default is not MISSING else None

    header = Line((Span("? ", palette.accent), Span(prompt.question, Style())))
    option_lines: list[Line] = []
    for i, choice in enumerate(choices):
        # Same value → same treatment (§5): a declared vocabulary marks its
        # values at CELL exactly as at LINE and in the record line. A values=
        # tuple Select has no vocabulary, so its options stay unstyled.
        value_style = (
            vocab_style(prompt.vocabulary, choice) if prompt.vocabulary is not None else Style()
        )
        spans = [Span(choice, value_style)]
        if i == default_idx:
            spans.append(Span(" (default)", palette.muted))
        option_lines.append(Line(tuple(spans)))

    body = list_view(state, option_lines, visible)
    return join_vertical(header.to_block(header.width), body)


# =============================================================================
# Input — a TextInputState field, parse on submit
# =============================================================================


def _run_input(prompt: Input, renderer: InPlaceRenderer, read: Callable[[], str | None]) -> Any:
    has_default = prompt.default is not MISSING
    state = TextInputState()
    hint: str | None = None

    while True:
        renderer.render(_input_block(prompt, state, hint))
        key = _next_key(read)
        if key == "enter":
            text = state.text
            if text == "" and has_default:
                return prompt.resolve_default()
            if prompt.parse is None:
                return text
            try:
                return prompt.parse(text)
            except Exception as exc:
                # Reject → hint and keep editing (never errors out, §5/§7).
                hint = f"Invalid input: {str(exc).strip() or type(exc).__name__}"
        elif key == "backspace":
            state, hint = state.delete_back(), None
        elif key == "delete":
            state = state.delete_forward()
        elif key == "left":
            state = state.move_left()
        elif key == "right":
            state = state.move_right()
        elif key == "home":
            state = state.move_home()
        elif key == "end":
            state = state.move_end()
        elif len(key) == 1 and key.isprintable():
            state, hint = state.insert(key), None
        # Unknown keys are ignored — the field holds.


def _input_block(prompt: Input, state: TextInputState, hint: str | None) -> Block:
    palette = current_palette()
    has_default = prompt.default is not MISSING
    suffix = f" [{prompt.default}]" if has_default else ""
    header = Line((Span("? ", palette.accent), Span(f"{prompt.question}{suffix}: ", Style())))
    field = text_input(state, _FIELD_WIDTH)
    row = join_horizontal(header.to_block(header.width), field)
    if hint is None:
        return row
    hint_line = Line((Span(hint, palette.warning),))
    return join_vertical(row, hint_line.to_block(hint_line.width))


# =============================================================================
# Confirm — single-key y/n (danger tiers govern the Enter key)
# =============================================================================


def _run_confirm(
    prompt: Confirm, renderer: InPlaceRenderer, read: Callable[[], str | None]
) -> bool:
    has_default = prompt.default is not MISSING  # only NONE may carry one (§9)
    hint: str | None = None

    while True:
        renderer.render(_confirm_block(prompt, hint))
        key = _next_key(read)
        low = key.lower() if len(key) == 1 else key
        if low == "y":
            return True
        if low == "n":
            return False
        if key == "enter" and has_default:
            # NONE tier: bare Enter accepts the declared default.
            return bool(prompt.default)
        # SOFT (no default) demands an explicit key — Enter is not enough (§9);
        # any other key, likewise, re-prompts with a hint.
        hint = "Press y or n."


def _confirm_block(prompt: Confirm, hint: str | None) -> Block:
    palette = current_palette()
    has_default = prompt.default is not MISSING
    if has_default:
        cue = "[Y/n]" if prompt.default else "[y/N]"
    else:
        cue = "[y/n]"
    line = Line(
        (
            Span("? ", palette.accent),
            Span(f"{prompt.question} ", Style()),
            Span(cue, palette.muted),
        )
    )
    if hint is None:
        return line.to_block(line.width)
    hint_line = Line((Span(hint, palette.warning),))
    return join_vertical(line.to_block(line.width), hint_line.to_block(hint_line.width))


# =============================================================================
# Confirm, danger=HARD — type the challenge (a TextInputState field)
# =============================================================================


def _run_hard_confirm(
    prompt: Confirm, renderer: InPlaceRenderer, read: Callable[[], str | None]
) -> bool:
    """HARD's type-the-challenge ceremony at CELL (design §9).

    Typing the challenge *is* the ceremony, so the field is a ``TextInputState``
    — the same free-text component ``Input`` binds, reused whole. The challenge
    is shown (proof of aim, not a secret); Enter resolves exactly once: the
    exact challenge → ``True``, anything else (a mismatch, an empty field) →
    ``False``, fail-closed. No re-prompt loop — a typo destroys nothing and the
    region collapses to ``✓ name: no``. Abort keys raise through ``_next_key``
    as everywhere, never a ``False``.
    """
    state = TextInputState()
    while True:
        renderer.render(_hard_confirm_block(prompt, state))
        key = _next_key(read)
        if key == "enter":
            return state.text == prompt.challenge
        elif key == "backspace":
            state = state.delete_back()
        elif key == "delete":
            state = state.delete_forward()
        elif key == "left":
            state = state.move_left()
        elif key == "right":
            state = state.move_right()
        elif key == "home":
            state = state.move_home()
        elif key == "end":
            state = state.move_end()
        elif len(key) == 1 and key.isprintable():
            state = state.insert(key)
        # Unknown keys are ignored — the field holds.


def _hard_confirm_block(prompt: Confirm, state: TextInputState) -> Block:
    palette = current_palette()
    icons = current_icons()
    header = Line((Span("? ", palette.accent), Span(prompt.question, Style())))
    cue = Line(
        (
            Span(f"{icons.warn} type ", palette.error),
            Span(f"{prompt.challenge}", palette.error),
            Span(" to proceed: ", palette.error),
        )
    )
    field = text_input(state, _FIELD_WIDTH)
    cue_row = join_horizontal(cue.to_block(cue.width), field)
    return join_vertical(header.to_block(header.width), cue_row)
