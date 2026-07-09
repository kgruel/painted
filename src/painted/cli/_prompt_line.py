"""LINE — cooked-mode prompt rendering, the interactive rung's accessibility
floor (docs/PROMPTS_DESIGN.md §5, §7, §12 step 2).

No raw terminal, no repaint: a LINE prompt is scroll-flow Q&A — the question
(and, for ``Select``, its numbered options) prints once, an invalid answer
gets a brief hint and a re-read, and the whole exchange scrolls into the
transcript like every other stderr line (§8 — prompt UI always draws on
stderr). This is the rung every environment has (dumb terminals, screen
readers, teleprinters — huh documents its equivalent as an accessibility
feature first, §5), so it offers the same options and produces the same
answer type CELL will (slice 3) — same value, same treatment, applied to
input.

Private sibling of ``cli/prompts.py``, imported lazily from there (the
framework→renderer boundary: this module pulls ``core``/``palette`` at
import, so nothing above pays for it until an interactive prompt actually
fires — the same lazy-import discipline ``prompts.py``'s own default-record
line follows). ``cli/prompts.py`` never imports ``tui/`` — LINE needs no raw
mode, so it has no reason to.
"""

from __future__ import annotations

from typing import Any, TextIO

from ..core.cell import Style
from ..core.span import Span
from ..core.writer import Writer
from ..icon_set import current_icons
from ..palette import current_palette
from .prompts import MISSING, Confirm, Input, Prompt, Select

__all__ = ["resolve_line"]


def resolve_line(prompt: Prompt[Any], *, stdin: TextIO, stderr: TextIO, use_ansi: bool) -> Any:
    """Render ``prompt`` at the LINE rung and return its answer.

    Dispatches by domain shape — each shares the read/re-prompt/abort
    skeleton (``_read_line``) and differs only in its cue and answer parsing.
    ``danger=HARD`` never reaches here: the caller (``PromptSession``) stubs
    it before this module is even imported — HARD's type-the-challenge
    ceremony is CELL-only (slice 5).
    """
    if isinstance(prompt, Confirm):
        return _confirm_line(prompt, stdin, stderr, use_ansi)
    if isinstance(prompt, Select):
        return _select_line(prompt, stdin, stderr, use_ansi)
    if isinstance(prompt, Input):
        return _input_line(prompt, stdin, stderr, use_ansi)
    raise TypeError(  # pragma: no cover — exhaustive over the three shipped shapes
        f"no LINE renderer for prompt shape {type(prompt).__name__}"
    )


# =============================================================================
# The shared read primitive — EOF and Ctrl-C both abort, never an answer
# =============================================================================


def _read_line(stdin: TextIO, stderr: TextIO) -> str:
    """Block for one line of cooked input; return it without its newline.

    The distinguishing case (design §7): bare Enter reads as ``"\\n"`` (a
    NONE-tier default-accept, handled by each caller), while EOF (Ctrl-D)
    reads as ``""``. Both EOF and a ``KeyboardInterrupt`` raised out of the
    blocking read (a real terminal delivers it here on Ctrl-C) take the
    *same* abort path: a restoring newline to stderr, then the exception
    propagates — never an answer, never a silent fall-through to the
    default.
    """
    try:
        raw = stdin.readline()
    except KeyboardInterrupt:
        stderr.write("\n")
        stderr.flush()
        raise
    if raw == "":
        stderr.write("\n")
        stderr.flush()
        raise KeyboardInterrupt
    return raw[:-1] if raw.endswith("\n") else raw


# =============================================================================
# Rendering — plain or SGR-styled spans, styled only when stderr is a TTY
# =============================================================================


def _render(spans: tuple[Span, ...], *, stderr: TextIO, use_ansi: bool) -> str:
    """Spans to a plain or SGR-styled string, no trailing newline."""
    if not use_ansi:
        return "".join(s.text for s in spans)
    writer = Writer(stderr)
    palette = current_palette()
    out: list[str] = []
    for span in spans:
        sgr = writer.apply_style(palette.resolve_style(span.style))
        if sgr:
            out.append(sgr)
        out.append(span.text)
        if sgr:
            out.append(writer.reset_style())
    return "".join(out)


def _write_lines(stderr: TextIO, use_ansi: bool, *lines: tuple[Span, ...]) -> None:
    """Write complete, newline-terminated lines to stderr."""
    for spans in lines:
        stderr.write(_render(spans, stderr=stderr, use_ansi=use_ansi))
        stderr.write("\n")
    stderr.flush()


def _write_cue(stderr: TextIO, use_ansi: bool, spans: tuple[Span, ...]) -> None:
    """Write the trailing input cue — no newline; the cursor stays on the line."""
    stderr.write(_render(spans, stderr=stderr, use_ansi=use_ansi))
    stderr.flush()


def _hint(stderr: TextIO, use_ansi: bool, message: str) -> None:
    """A brief styled re-prompt hint (design: invalid input never errors out)."""
    icons = current_icons()
    _write_lines(stderr, use_ansi, (Span(f"{icons.warn} {message}", current_palette().warning),))


# =============================================================================
# Confirm — y/n
# =============================================================================


def _confirm_line(prompt: Confirm, stdin: TextIO, stderr: TextIO, use_ansi: bool) -> bool:
    palette = current_palette()
    has_default = prompt.default is not MISSING
    if has_default:
        cue_text = "[Y/n]" if prompt.default else "[y/N]"
    else:
        cue_text = "[y/n]"
    cue = (Span(f"{cue_text} ", palette.muted),)

    _write_cue(
        stderr,
        use_ansi,
        (
            Span("? ", palette.accent),
            Span(f"{prompt.question} ", Style()),
            *cue,
        ),
    )
    while True:
        raw = _read_line(stdin, stderr)
        text = raw.strip().lower()
        if text == "" and has_default:
            return bool(prompt.default)
        if text in ("y", "yes"):
            return True
        if text in ("n", "no"):
            return False
        _hint(stderr, use_ansi, f"Please answer y or n {cue_text}.")
        _write_cue(stderr, use_ansi, cue)


# =============================================================================
# Select — numbered options
# =============================================================================


def _select_line(prompt: Select, stdin: TextIO, stderr: TextIO, use_ansi: bool) -> str:
    palette = current_palette()
    choices = prompt.choices
    has_default = prompt.default is not MISSING
    default_idx = choices.index(prompt.default) + 1 if has_default else None

    lines: list[tuple[Span, ...]] = [(Span("? ", palette.accent), Span(prompt.question, Style()))]
    for i, choice in enumerate(choices, start=1):
        marker = " (default)" if i == default_idx else ""
        lines.append((Span(f"  {i}) ", palette.muted), Span(f"{choice}{marker}", Style())))
    _write_lines(stderr, use_ansi, *lines)

    suffix = f" [{default_idx}]" if has_default else ""
    cue = (Span(f"Enter 1-{len(choices)}{suffix}: ", palette.muted),)
    _write_cue(stderr, use_ansi, cue)

    while True:
        raw = _read_line(stdin, stderr)
        text = raw.strip()
        if text == "" and has_default:
            return str(prompt.default)
        if text.isdigit():
            n = int(text)
            if 1 <= n <= len(choices):
                return choices[n - 1]
        _hint(stderr, use_ansi, f"Please enter a number between 1 and {len(choices)}.")
        _write_cue(stderr, use_ansi, cue)


# =============================================================================
# Input — free text through parse
# =============================================================================


def _input_line(prompt: Input, stdin: TextIO, stderr: TextIO, use_ansi: bool) -> Any:
    palette = current_palette()
    has_default = prompt.default is not MISSING
    suffix = f" [{prompt.default}]" if has_default else ""
    cue = (
        Span("? ", palette.accent),
        Span(f"{prompt.question}{suffix}: ", Style()),
    )
    _write_cue(stderr, use_ansi, cue)

    while True:
        raw = _read_line(stdin, stderr)
        if raw == "" and has_default:
            return prompt.resolve_default()
        if prompt.parse is None:
            return raw
        try:
            return prompt.parse(raw)
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            _hint(stderr, use_ansi, f"Invalid input: {message}")
            _write_cue(stderr, use_ansi, cue)
