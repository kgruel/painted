"""Traceback rendering — an exception as a record tree, disclosed by zoom.

A traceback is a *record tree*: frames are records (``file:line in func`` rows on
a continuous gutter rail), and chains/groups are the tree that connects them.
Capture is the declaration — ``TracebackException.from_exception`` freezes a live
exception into frame-free plain data, so a rendered traceback is a projection of
declared meaning, not of live interpreter state.

    render_traceback(exc, Zoom.DETAILED, 80)         # a live exception
    render_traceback(te, Zoom.SUMMARY, 80)           # a captured TracebackException

The zoom ladder (each rung additive, never rewriting the rung below):

    MINIMAL   type + message + innermost app frame, one line
    SUMMARY   + frame stack (one line/frame, suppressed folded, chains summarized)
    DETAILED  + source ±1 with a caret, chains fully rendered
    FULL      + source ±3, redacted+budgeted locals, groups fully expanded

The gutter rail encodes exactly ONE dimension — frame origin: an app frame keeps
the default weight, a suppressed/library frame is muted. Source carets are derived
from ``colno``/``end_colno`` (byte offsets) and converted to DISPLAY columns so
wide/zero-width source characters never misalign them.
"""

from __future__ import annotations

import linecache
import os
import re
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from traceback import TracebackException

from ..core._text_width import display_width, truncate_ellipsis
from ..core.block import Block
from ..core.cell import Style
from ..core.compose import fit_to_width, join_horizontal, join_vertical
from ..core.span import Line, Span
from ..core.zoom import Zoom
from ..icon_set import current_icons
from ..palette import current_palette

# --- Redaction ---------------------------------------------------------------

# Local NAMES a default install should never echo. Substring, case-insensitive:
# a `db_password` or `API_KEY` is masked, the value never reaching a repr.
_REDACT_PAT = re.compile(r"password|secret|token|key|api", re.IGNORECASE)

_REDACTED = "∙∙∙ redacted"
_UNREPRESENTABLE = "<unrepresentable>"


def default_redact(name: str) -> bool:
    """True if a local NAME declares itself sensitive (masked, not rendered).

    Kept module-importable but *unlisted* in ``views.__all__``: it is the default
    argument of ``render_traceback``, not a standalone view.
    """
    return bool(_REDACT_PAT.search(name))


# --- Normalized model --------------------------------------------------------
# Both input paths (a live BaseException, a captured TracebackException) collapse
# to this frozen tree before any rendering. The only divergence is locals: the
# live path carries real objects (rendered through the hardened shape_lens at
# FULL); the captured path carries stdlib's pre-repr'd strings (the Fact-friendly
# boundary — capture already happened, so we render the frozen text as-is).


@dataclass(frozen=True)
class _Frame:
    filename: str  # real path — linecache reads source through it
    lineno: int | None
    name: str
    colno: int | None
    end_colno: int | None
    # Locals as an immutable sorted tuple of (name, value) pairs (frozen-dataclass
    # contract). `locals_are_repr` distinguishes the two capture modes: live
    # objects (BaseException, FULL) rendered through shape_lens, vs stdlib's
    # pre-repr'd strings (TracebackException — capture already happened).
    locals_pairs: tuple[tuple[str, object], ...] | None
    locals_are_repr: bool


@dataclass(frozen=True)
class _Node:
    type_name: str
    message: str
    frames: tuple[_Frame, ...]
    cause: _Node | None  # __cause__ — "direct cause of"
    context: _Node | None  # __context__ (unsuppressed) — "during handling of"
    children: tuple[_Node, ...]  # ExceptionGroup members
    is_group: bool
    is_cycle: bool = False  # a revisited exception — a muted ↻ marker, not a re-walk


# A chain/group link back to an already-normalized exception. Cause/context are
# assignable (`a.__cause__ = b; b.__cause__ = a`) and `raise e from e` is legal, so
# the exception graph can be cyclic; a marker node stops the walk the way stdlib's
# `TracebackException` threads a `_seen` id-set. Without it a cycle recurses until
# RecursionError — which would defeat the whole point of an error renderer.
_CYCLE = "↻ <cycle>"


def _cycle_node() -> _Node:
    """A sentinel for a revisited exception in a cyclic chain (rendered muted)."""
    return _Node(_CYCLE, "", (), None, None, (), False, is_cycle=True)


def _safe_str(exc: BaseException) -> str:
    """``str(exc)`` that cannot itself raise — a broken ``__str__`` degrades."""
    try:
        return str(exc)
    except Exception:
        return f"<unprintable {type(exc).__name__}>"


def _from_exception(exc: BaseException, capture: bool, seen: frozenset[int] = frozenset()) -> _Node:
    """Normalize a live exception. ``capture`` grabs live frame locals (FULL).

    Colno and the frame list come from a capture-free ``TracebackException`` (no
    eager repr, so nothing in it can raise); live locals are read separately from
    the traceback frames, which walk in the same order — so the two align by index.

    ``seen`` carries the ids of exceptions already on the current walk so a cyclic
    cause/context/group chain stops at a muted marker instead of recursing forever.
    """
    if id(exc) in seen:
        return _cycle_node()
    seen = seen | {id(exc)}
    te = TracebackException.from_exception(exc, capture_locals=False)
    walked = list(traceback.walk_tb(exc.__traceback__)) if capture else []
    frames: list[_Frame] = []
    for i, fs in enumerate(te.stack):
        live = walked[i][0].f_locals if capture and i < len(walked) else None
        pairs = tuple(sorted(live.items())) if live is not None else None
        frames.append(
            _Frame(
                fs.filename,
                fs.lineno,
                fs.name,
                getattr(fs, "colno", None),
                getattr(fs, "end_colno", None),
                pairs,
                False,
            )
        )

    cause = _from_exception(exc.__cause__, capture, seen) if exc.__cause__ is not None else None
    # __context__ is shown only when not suppressed; `raise X from Y` (and
    # `from None`) both set __suppress_context__, so a set __cause__ naturally
    # wins here without a separate precedence check.
    context = (
        _from_exception(exc.__context__, capture, seen)
        if exc.__context__ is not None and not exc.__suppress_context__
        else None
    )
    is_group = isinstance(exc, BaseExceptionGroup)
    children = tuple(_from_exception(e, capture, seen) for e in exc.exceptions) if is_group else ()

    return _Node(
        type(exc).__name__,
        _safe_str(exc),
        tuple(frames),
        cause,
        context,
        children,
        is_group,
    )


def _from_te(te: TracebackException, seen: frozenset[int] = frozenset()) -> _Node:
    """Normalize a captured TracebackException (locals are frozen repr strings).

    stdlib collapses live cycles when it builds the tree, so a captured chain is
    normally acyclic; the ``seen`` guard still holds against a hand-assembled
    cyclic ``TracebackException`` — the never-raise law applies to both inputs.
    """
    if id(te) in seen:
        return _cycle_node()
    seen = seen | {id(te)}
    frames = tuple(
        _Frame(
            fs.filename,
            fs.lineno,
            fs.name,
            getattr(fs, "colno", None),
            getattr(fs, "end_colno", None),
            tuple(sorted(loc.items()))
            if (loc := getattr(fs, "locals", None)) is not None
            else None,
            True,
        )
        for fs in te.stack
    )
    cause = _from_te(te.__cause__, seen) if te.__cause__ is not None else None
    context = (
        _from_te(te.__context__, seen)
        if te.__context__ is not None and not te.__suppress_context__
        else None
    )
    sub = getattr(te, "exceptions", None)
    is_group = sub is not None
    children = tuple(_from_te(t, seen) for t in sub) if sub is not None else ()

    type_name, message = _split_head(te)
    return _Node(type_name, message, frames, cause, context, children, is_group)


def _split_head(te: TracebackException) -> tuple[str, str]:
    """`(type, message)` from a TracebackException's exception-only header line."""
    lines = list(te.format_exception_only())
    head = lines[0].rstrip("\n") if lines else ""
    type_name, sep, message = head.partition(": ")
    return (type_name, message) if sep else (head, "")


# --- Caret geometry ----------------------------------------------------------


def _byte_to_char(line: str, byte_off: int) -> int:
    """A UTF-8 byte offset (as ``colno`` reports) → a character index into ``line``."""
    if byte_off <= 0:
        return 0
    return len(line.encode("utf-8")[:byte_off].decode("utf-8", "replace"))


def _caret(line: str, colno: int, end_colno: int | None) -> str | None:
    """Build a ``   ^^^`` caret for ``line``, in DISPLAY columns.

    ``colno``/``end_colno`` are byte offsets; the offset AND the span are measured
    with ``display_width`` over the real characters, so a wide or zero-width glyph
    before/under the marker shifts it exactly as the rendered source row shifts.
    """
    start = _byte_to_char(line, colno)
    offset = display_width(line[:start])
    span = 1
    if end_colno is not None and end_colno > colno:
        end = _byte_to_char(line, end_colno)
        span = max(1, display_width(line[start:end]))
    return " " * offset + "^" * span


# --- Rail --------------------------------------------------------------------

_RAIL = "│ "


def _rail(block: Block, style: Style) -> Block:
    """Prepend a continuous ``│`` gutter column, in one origin color, to a block."""
    rows = [(_RAIL, style)] * max(1, block.height)
    return join_horizontal(Block.column(rows), block)


def _fit(block: Block, width: int | None) -> Block:
    """Exact width, or natural sizing when ``width`` is None (the width contract)."""
    return block if width is None else fit_to_width(block, width)


def _text(text: str, style: Style, width: int | None) -> Block:
    """A single-row block, truncated to an int ``width`` (natural when None)."""
    if width is not None and display_width(text) > width:
        text = truncate_ellipsis(text, width)
    return Block.text(text, style, width=width)


# --- Suppression -------------------------------------------------------------


def _match_sub(frame: _Frame, suppress: Sequence[str]) -> str | None:
    """The first ``suppress`` substring matching this frame's file, else None."""
    for sub in suppress:
        if sub in frame.filename:
            return sub
    return None


# --- Frame rendering ---------------------------------------------------------

_SRC_INDENT = "  "


def _source_block(frame: _Frame, zoom: Zoom, width: int | None) -> Block | None:
    """Source context around the failing line, with an accented line + caret."""
    if frame.lineno is None:
        return None
    ctx = 3 if zoom >= Zoom.FULL else 1
    p = current_palette()
    rows: list[Block] = []
    for n in range(frame.lineno - ctx, frame.lineno + ctx + 1):
        raw = linecache.getline(frame.filename, n)
        if not raw:
            continue
        src = raw.rstrip("\n")
        if n == frame.lineno:
            rows.append(_text(f"{_SRC_INDENT}{src}", p.accent, width))
            if frame.colno is not None:
                caret = _caret(src, frame.colno, frame.end_colno)
                if caret and caret.strip():
                    rows.append(_text(f"{_SRC_INDENT}{caret}", p.error, width))
        else:
            rows.append(_text(f"{_SRC_INDENT}{src}", p.muted, width))
    return join_vertical(*rows) if rows else None


def _render_value(value: object, width: int | None) -> Block:
    """A local's value through the HARDENED shape_lens — cycle-safe, contained.

    A raising ``__repr__``/``__str__`` inside the built-in path degrades to a muted
    placeholder rather than crashing the error renderer (the whole point of
    rendering an error).
    """
    from .lens.shape import shape_lens

    try:
        return shape_lens(value, int(Zoom.SUMMARY), width if width is not None else 40)
    except Exception:
        return Block.text(_UNREPRESENTABLE, current_palette().muted)


def _locals_block(
    frame: _Frame,
    width: int | None,
    redact: Callable[[str], bool] | None,
) -> Block | None:
    """Per-frame locals (FULL): redacted by name, values budgeted + cycle-safe."""
    if not frame.locals_pairs:
        return None

    p = current_palette()
    inner = None if width is None else max(1, width - len(_SRC_INDENT))
    rows: list[Block] = []
    for name, value in frame.locals_pairs:
        head = Block.text(f"{_SRC_INDENT}{name} = ", p.muted)
        if redact is not None and redact(name):
            rows.append(join_horizontal(head, Block.text(_REDACTED, p.muted)))
            continue
        val_budget = None if inner is None else max(1, inner - display_width(f"{name} = "))
        if frame.locals_are_repr:
            val_block = _text(str(value), p.muted, val_budget)
        else:
            val_block = _render_value(value, val_budget)
        if val_block.height == 1:
            rows.append(join_horizontal(head, val_block))
        else:
            rows.append(join_vertical(head, val_block))
    return join_vertical(*rows) if rows else None


def _render_frame(frame: _Frame, zoom: Zoom, width: int | None, redact) -> Block:
    """One frame: a ``file:line in func`` row + (per zoom) source and locals."""
    base = os.path.basename(frame.filename) or frame.filename
    loc = f"{base}:{frame.lineno}" if frame.lineno is not None else base
    rows: list[Block] = [_text(f"{loc} in {frame.name}", Style(), width)]

    if zoom >= Zoom.DETAILED:
        src = _source_block(frame, zoom, width)
        if src is not None:
            rows.append(src)
    if zoom >= Zoom.FULL:
        locals_block = _locals_block(frame, width, redact)
        if locals_block is not None:
            rows.append(locals_block)

    return join_vertical(*rows)


def _frames_block(node: _Node, zoom: Zoom, width: int | None, suppress, redact) -> Block | None:
    """The frame stack: a continuous rail, consecutive suppressed frames folded."""
    frames = node.frames
    if not frames:
        return None
    inner = None if width is None else max(1, width - len(_RAIL))
    muted = current_palette().muted
    rows: list[Block] = []
    i = 0
    while i < len(frames):
        sub = _match_sub(frames[i], suppress)
        if sub is not None:
            j = i
            while j < len(frames) and _match_sub(frames[j], suppress) is not None:
                j += 1
            n = j - i
            label = f"… {n} frame{'s' if n > 1 else ''} in {sub} …"
            rows.append(_rail(_text(label, muted, inner), muted))
            i = j
            continue
        rows.append(_rail(_render_frame(frames[i], zoom, inner, redact), Style()))
        i += 1
    return join_vertical(*rows)


# --- Chain / group / node ----------------------------------------------------

_CAUSE = "The above exception was the direct cause of the following exception:"
_CONTEXT = "During handling of the above exception, another exception occurred:"


def _header(node: _Node, width: int | None) -> Block:
    """The ``Type: message`` header — type in the error role, message split into rows."""
    p = current_palette()
    msg_lines = node.message.splitlines() or [""]
    first = Line((Span(f"{node.type_name}: ", p.error), Span(msg_lines[0])))
    if width is None:
        w = max([first.width, *(display_width(m) for m in msg_lines[1:])], default=0)
    else:
        w = width
    rows: list[Block] = [first.to_block(w)]
    for extra in msg_lines[1:]:
        rows.append(_text(extra, Style(), w))
    return join_vertical(*rows)


def _connective(text: str, style: Style, width: int | None) -> Block:
    """A blank-flanked chain connective line (cause = error, context = warning)."""
    blank = Block.text("", Style(), width=width)
    return join_vertical(blank, _text(text, style, width), blank)


def _minimal_line(node: _Node, width: int | None, suppress) -> Block:
    """MINIMAL: ``Type: message at file.py:42`` — innermost app frame, one line."""
    if node.is_cycle:
        return _fit(_text(_CYCLE, current_palette().muted, width), width)
    p = current_palette()
    frame = _innermost_app_frame(node, suppress)
    at = ""
    if frame is not None and frame.lineno is not None:
        base = os.path.basename(frame.filename) or frame.filename
        at = f" at {base}:{frame.lineno}"
    line = Line(
        (
            Span(f"{node.type_name}: ", p.error),
            Span(node.message),
            Span(at, p.muted),
        )
    )
    w = line.width if width is None else width
    block = line.to_block(w)
    return _fit(block, width)


def _innermost_app_frame(node: _Node, suppress) -> _Frame | None:
    """The deepest non-suppressed frame (fallback: the deepest frame)."""
    for frame in reversed(node.frames):
        if _match_sub(frame, suppress) is None:
            return frame
    return node.frames[-1] if node.frames else None


def _render_group(node: _Node, zoom: Zoom, width: int | None, suppress, redact) -> Block:
    """An ExceptionGroup as a tree: header + each member on a tree branch."""
    icons = current_icons()
    parts: list[Block] = [_header(node, width)]
    frames = _frames_block(node, zoom, width, suppress, redact)
    if frames is not None:
        parts.append(frames)

    n = len(node.children)
    if zoom <= Zoom.SUMMARY:
        # Summarize members one line each — the group's shape without its depth.
        for k, child in enumerate(node.children):
            glyph = icons.tree_last if k == n - 1 else icons.tree_branch
            child_w = None if width is None else max(1, width - display_width(glyph))
            body = _minimal_line(child, child_w, suppress)
            parts.append(_prefix_tree(body, glyph, icons.tree_space, icons.tree_indent, k == n - 1))
        return _fit(join_vertical(*parts), width)

    # DETAILED/FULL: each member fully expanded under a tree branch.
    for k, child in enumerate(node.children):
        glyph = icons.tree_branch if k < n - 1 else icons.tree_last
        child_w = None if width is None else max(1, width - display_width(glyph))
        body = _render_node(child, zoom, child_w, suppress, redact)
        parts.append(_prefix_tree(body, glyph, icons.tree_space, icons.tree_indent, k == n - 1))
    return _fit(join_vertical(*parts), width)


def _prefix_tree(body: Block, glyph: str, space: str, indent: str, last: bool) -> Block:
    """Prefix ``body``'s first row with a tree glyph, continuation rows with the rail."""
    cont = space if last else indent
    rows = [(glyph, Style())] + [(cont, Style())] * (max(1, body.height) - 1)
    return join_horizontal(Block.column(rows), body)


def _render_body(node: _Node, zoom: Zoom, width: int | None, suppress, redact) -> Block:
    """One exception's own body — header, frame stack, (groups: member tree)."""
    if node.is_group:
        return _render_group(node, zoom, width, suppress, redact)
    parts: list[Block] = [_header(node, width)]
    frames = _frames_block(node, zoom, width, suppress, redact)
    if frames is not None:
        parts.append(frames)
    return join_vertical(*parts)


def _render_node(node: _Node, zoom: Zoom, width: int | None, suppress, redact) -> Block:
    """A full exception including its chain (the earlier exception renders first)."""
    if node.is_cycle:
        return _fit(_text(_CYCLE, current_palette().muted, width), width)
    if zoom <= Zoom.MINIMAL:
        return _minimal_line(node, width, suppress)

    p = current_palette()
    parts: list[Block] = []
    prior = node.cause or node.context
    if prior is not None:
        if zoom <= Zoom.SUMMARY:
            # Chains summarized: the prior collapses to its one-line MINIMAL form.
            parts.append(_minimal_line(prior, width, suppress))
        else:
            parts.append(_render_node(prior, zoom, width, suppress, redact))
        connective = _CAUSE if node.cause is not None else _CONTEXT
        role = p.error if node.cause is not None else p.warning
        parts.append(_connective(connective, role, width))

    parts.append(_render_body(node, zoom, width, suppress, redact))
    return _fit(join_vertical(*parts), width)


def render_traceback(
    exc: BaseException | TracebackException,
    zoom: Zoom,
    width: int | None,
    *,
    suppress: Sequence[str] = (),
    redact: Callable[[str], bool] | None = default_redact,
) -> Block:
    """Render an exception (or a captured TracebackException) as a Block.

    A live ``BaseException`` is captured on the spot — ``capture_locals`` is on
    only at ``Zoom.FULL``, and the capture is repr-free so nothing in it can raise.
    A ``TracebackException`` is rendered as-is: capture already happened, so this is
    the serializable / Fact-friendly boundary.

    ``suppress`` names module-path substrings declared "not my code"; matching
    frames FOLD to a single muted ``… N frames in <module> …`` line — a declared,
    output-changing choice. ``redact`` masks locals by NAME (FULL only); the default
    hides ``password``/``secret``/``token``/``key``/``api``. Pass ``redact=None`` to
    show every local. Caret positions convert byte offsets to display columns, so
    wide/zero-width source characters never misalign the marker; multi-line messages
    split into rows before hitting the cell substrate.
    """
    if isinstance(exc, TracebackException):
        node = _from_te(exc)
    else:
        node = _from_exception(exc, capture=zoom >= Zoom.FULL)
    return _render_node(node, zoom, width, suppress, redact)
