"""Writer: terminal output via ANSI escape sequences."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, TextIO
from urllib.parse import quote

from wcwidth import wcwidth

from ..palette import current_palette
from ..refs import resolve_ref
from .buffer import CellWrite
from .cell import NAMED_COLORS, Style
from ._color import _nearest_basic, _rgb_to_256, _rgb_to_basic
from ._row_ops import iter_trimmed_row_spans, row_visible_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .block import Block


# Bytes left untouched when percent-encoding a resolver-returned URI for OSC 8:
# RFC 3986 reserved + unreserved, plus "%" so already-encoded URIs pass through.
_URI_SAFE = ":/?#[]@!$&'()*+,;=%~-._"


class ColorDepth(Enum):
    NONE = 0
    BASIC = 16
    EIGHT_BIT = 256
    TRUECOLOR = 16_777_216


class Writer:
    """Converts cell writes to ANSI escape sequences and outputs to terminal.

    Automatically downgrades colors when terminal color depth is limited.
    Capabilities resolve at this boundary — views express intent (Style),
    Writer resolves against detected terminal capability.
    """

    def __init__(
        self,
        stream: TextIO = sys.stdout,
        *,
        color_depth: ColorDepth | None = None,
        hyperlinks: bool = True,
        no_color: bool | None = None,
    ):
        self._stream = stream
        # When provided, forces color capability resolution (useful for tests and
        # non-interactive environments where isatty() is false).
        self._color_depth: ColorDepth | None = color_depth
        # OSC 8 is progressive enhancement (design §5): a plain opt-out switch,
        # not a detection — unsupporting terminals ignore the wrapper. Mirrors
        # the color_depth override, without a detect_ counterpart.
        self._hyperlinks: bool = hyperlinks
        # NO_COLOR (no-color.org): ambient colour-off — suppresses fg/bg while
        # keeping bold/underline/etc. Resolved once. An explicit no_color= wins
        # (True or False); otherwise read the env (present and non-empty). This
        # is orthogonal to color_depth: a forced depth does NOT bypass NO_COLOR —
        # PaintedHandler snapshots a *detected* depth and passes it as a forced
        # depth, and that must still honour the user's NO_COLOR. Callers that need
        # colour regardless of the environment pass no_color=False explicitly.
        if no_color is not None:
            self._no_color: bool = no_color
        else:
            self._no_color = bool(os.environ.get("NO_COLOR"))

    @property
    def no_color(self) -> bool:
        """The resolved NO_COLOR policy — read once at construction (§9.1).

        A host that derives capability facets from a delivery's writer reads this
        so the facet snapshot and the serializer share one resolution, never two
        env reads that only usually agree.
        """
        return self._no_color

    @property
    def hyperlinks(self) -> bool:
        """Whether this writer emits OSC 8 link carriers — the link facet's signal."""
        return self._hyperlinks

    @property
    def stream(self) -> TextIO:
        """The destination stream — its encoding is the glyph facet's signal."""
        return self._stream

    def size(self) -> tuple[int, int]:
        """Terminal dimensions (columns, rows)."""
        sz = shutil.get_terminal_size()
        return (sz.columns, sz.lines)

    def detect_color_depth(self) -> ColorDepth:
        """Check terminal capabilities for color support."""
        if self._color_depth is not None:
            return self._color_depth

        if not hasattr(self._stream, "isatty") or not self._stream.isatty():
            self._color_depth = ColorDepth.NONE
            return self._color_depth

        colorterm = os.environ.get("COLORTERM", "").lower()
        if colorterm in ("truecolor", "24bit"):
            self._color_depth = ColorDepth.TRUECOLOR
            return self._color_depth

        term = os.environ.get("TERM", "").lower()
        if "256color" in term:
            self._color_depth = ColorDepth.EIGHT_BIT
            return self._color_depth

        if term:
            self._color_depth = ColorDepth.BASIC
            return self._color_depth

        self._color_depth = ColorDepth.BASIC
        return self._color_depth

    def apply_style(self, style: Style) -> str:
        """Convert Style to ANSI SGR escape sequence."""
        codes: list[str] = []

        if style.bold:
            codes.append("1")
        if style.dim:
            codes.append("2")
        if style.italic:
            codes.append("3")
        if style.underline:
            codes.append("4")
        if style.reverse:
            codes.append("7")

        # Two suppressions share the NO_COLOR shape — fg/bg dropped, bold/underline
        # kept: an explicit NO_COLOR, and a colorless destination (ColorDepth.NONE,
        # resolved or forced). NONE is a colorless destination, not a downsampling
        # target — the depth is meaningful only after color is chosen (§9.4), so the
        # writer never emits color for it. Positive depths downsample as usual.
        if not self._no_color:
            depth = self.detect_color_depth()
            if depth is not ColorDepth.NONE:
                if style.fg is not None:
                    codes.extend(self._color_codes(style.fg, foreground=True, depth=depth))
                if style.bg is not None:
                    codes.extend(self._color_codes(style.bg, foreground=False, depth=depth))

        if not codes:
            return ""
        return f"\x1b[{';'.join(codes)}m"

    def _color_codes(
        self,
        color: str | int,
        foreground: bool,
        *,
        depth: ColorDepth | None = None,
    ) -> list[str]:
        """Convert a color value to SGR parameter strings.

        Automatically downgrades colors when terminal color depth is limited:
        - Hex RGB -> truecolor / 256-color / 16-color, as needed
        - 256-color index -> 16-color, as needed
        - Named colors always emit as basic SGR (already safe)

        ``depth`` is optional so direct callers can continue using the helper
        without duplicating capability detection.
        """
        if depth is None:
            depth = self.detect_color_depth()
        base = 30 if foreground else 40

        if isinstance(color, int):
            if depth.value >= ColorDepth.EIGHT_BIT.value:
                prefix = "38" if foreground else "48"
                return [prefix, "5", str(color)]
            return [str(base + _nearest_basic(color))]

        if isinstance(color, str):
            if color.startswith("#") and len(color) == 7:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
                if depth == ColorDepth.TRUECOLOR:
                    prefix = "38" if foreground else "48"
                    return [prefix, "2", str(r), str(g), str(b)]
                if depth == ColorDepth.EIGHT_BIT:
                    prefix = "38" if foreground else "48"
                    return [prefix, "5", str(_rgb_to_256(r, g, b))]
                return [str(base + _rgb_to_basic(r, g, b))]

            idx = NAMED_COLORS.get(color.lower())
            if idx is not None:
                return [str(base + idx)]

        return []

    def reset_style(self) -> str:
        """SGR reset sequence."""
        return "\x1b[0m"

    def open_hyperlink(self, uri: str) -> str:
        """OSC 8 open sequence for a hyperlink target (ST terminator)."""
        return f"\x1b]8;;{uri}\x1b\\"

    def close_hyperlink(self) -> str:
        """OSC 8 close sequence (ST terminator)."""
        return "\x1b]8;;\x1b\\"

    def _link_target(
        self, ref: str | None, resolved: dict[str, str | None]
    ) -> tuple[str | None, str | None]:
        """Resolve a cell's ref to ``(open-link key, uri)``, honoring the gate.

        Returns ``(None, None)`` when no link should wrap the cell — hyperlinks
        off, no ref, or the ref resolves to no URI (inert, design §5). Otherwise
        ``(ref, uri)``: the ref keys the open link, so a ref change re-anchors
        even when two refs resolve to the same URI. ``resolved`` memoizes so each
        distinct ref hits the (app-owned) resolver once per emission call.
        """
        if not self._hyperlinks or ref is None:
            return (None, None)
        try:
            uri = resolved[ref]
        except KeyError:
            uri = resolve_ref(ref)
            if uri:
                # Resolver output is app data entering a raw escape sequence:
                # percent-encode anything outside printable ASCII so a stray
                # control byte (ESC, BEL, ST) can't terminate the OSC 8 early or
                # inject a second sequence into the terminal stream. Reserved
                # URI characters and "%" stay untouched — already-encoded URIs
                # pass through unchanged.
                uri = quote(uri, safe=_URI_SAFE)
            resolved[ref] = uri
        # An empty-string URI is "no URI": OSC 8 with an empty target is the
        # close sequence, which would desync the open/close state machine.
        if not uri:
            return (None, None)
        return (ref, uri)

    def move_cursor(self, x: int, y: int) -> str:
        """CSI escape for cursor positioning (1-based)."""
        return f"\x1b[{y + 1};{x + 1}H"

    def set_scroll_region(self, top: int, bottom: int) -> str:
        """Set scroll region via DECSTBM (top/bottom margins, 0-based inclusive)."""
        return f"\x1b[{top + 1};{bottom + 1}r"

    def reset_scroll_region(self) -> str:
        """Reset scroll region to full screen (DECSTBM with no params)."""
        return "\x1b[r"

    def scroll_up(self, n: int) -> str:
        """Scroll up (content moves up) by n lines: CSI n S."""
        return f"\x1b[{n}S"

    def scroll_down(self, n: int) -> str:
        """Scroll down (content moves down) by n lines: CSI n T."""
        return f"\x1b[{n}T"

    def write_ops(self, ops: list[RenderOp], *, clear_first: bool = False) -> None:
        """Render a mixed stream of operations (scroll + cell writes)."""
        if not ops and not clear_first:
            return

        parts: list[str] = []
        parts.append("\x1b[?2026h")  # synchronized output begin
        if clear_first:
            parts.append("\x1b[2J")  # erase display

        last_style: Style | None = None
        # OSC 8 link state, an independent state machine from last_style: a
        # ref-only transition must emit even when style is unchanged. last_ref
        # is the ref of the currently open link (None ⇒ no link open).
        last_ref: str | None = None
        resolved: dict[str, str | None] = {}  # memo: resolve each distinct ref once
        covered: set[tuple[int, int]] = set()  # trailing cells of wide chars written this frame
        cursor_x: int = -1
        cursor_y: int = -1

        for op in ops:
            if isinstance(op, ScrollOp):
                if op.top > op.bottom or op.n == 0:
                    continue

                top = max(0, op.top)
                bottom = max(top, op.bottom)
                n = op.n

                if last_ref is not None:
                    parts.append(self.close_hyperlink())
                    last_ref = None
                parts.append(self.reset_style())
                last_style = None

                parts.append(self.set_scroll_region(top, bottom))
                if n > 0:
                    parts.append(self.move_cursor(0, bottom))
                    parts.append(self.scroll_up(n))
                else:
                    parts.append(self.move_cursor(0, top))
                    parts.append(self.scroll_down(-n))
                parts.append(self.reset_scroll_region())
                cursor_x = -1
                cursor_y = -1
                continue

            # CellWrite
            w = op

            if (w.x, w.y) in covered:
                continue

            if w.x != cursor_x or w.y != cursor_y:
                # A cursor jump breaks link adjacency: an open link must not
                # bleed across cells the frame didn't write.
                if last_ref is not None:
                    parts.append(self.close_hyperlink())
                    last_ref = None
                parts.append(self.move_cursor(w.x, w.y))

            if w.cell.style != last_style:
                parts.append(self.reset_style())
                sgr = self.apply_style(current_palette().resolve_style(w.cell.style))
                if sgr:
                    parts.append(sgr)
                last_style = w.cell.style

            target_ref, uri = self._link_target(w.ref, resolved)
            if target_ref != last_ref:
                if last_ref is not None:
                    parts.append(self.close_hyperlink())
                if uri is not None:  # uri and target_ref are set together
                    parts.append(self.open_hyperlink(uri))
                last_ref = target_ref

            parts.append(w.cell.char)

            char_width = wcwidth(w.cell.char)
            if char_width and char_width > 1:
                for dx in range(1, char_width):
                    covered.add((w.x + dx, w.y))
                cursor_x = w.x + char_width
            else:
                cursor_x = w.x + 1
            cursor_y = w.y

        if last_ref is not None:
            parts.append(self.close_hyperlink())
        parts.append(self.reset_style())
        parts.append("\x1b[?2026l")  # synchronized output end

        self._stream.write("".join(parts))
        self._stream.flush()

    def write_frame(self, writes: list[CellWrite], *, clear_first: bool = False) -> None:
        """Render cell writes to terminal. Batches into a single write call."""
        self.write_ops(writes, clear_first=clear_first)  # type: ignore[arg-type]  # CellWrite is a RenderOp

    def clear_screen(self) -> None:
        """Erase entire display (ED2)."""
        self._stream.write("\x1b[2J")
        self._stream.flush()

    def enter_alt_screen(self) -> None:
        self._stream.write("\x1b[?1049h")
        self._stream.flush()

    def exit_alt_screen(self) -> None:
        self._stream.write("\x1b[?1049l")
        self._stream.flush()

    def hide_cursor(self) -> None:
        self._stream.write("\x1b[?25l")
        self._stream.flush()

    def show_cursor(self) -> None:
        self._stream.write("\x1b[?25h")
        self._stream.flush()

    def enable_mouse(self, *, all_motion: bool = False) -> None:
        """Enable SGR mouse tracking.

        Args:
            all_motion: If True, report all mouse motion (mode 1003).
                        If False, only report button events and drags (mode 1002).
        """
        # Mode 1002 = button-event tracking (press, release, drag)
        # Mode 1003 = any-event tracking (all motion, high volume)
        tracking_mode = 1003 if all_motion else 1002
        self._stream.write(f"\x1b[?{tracking_mode}h")  # Enable tracking
        self._stream.write("\x1b[?1006h")  # Enable SGR encoding
        self._stream.flush()

    def disable_mouse(self) -> None:
        """Disable mouse tracking."""
        self._stream.write("\x1b[?1002l")  # Disable button-event
        self._stream.write("\x1b[?1003l")  # Disable any-event
        self._stream.write("\x1b[?1006l")  # Disable SGR encoding
        self._stream.flush()


def print_block(
    block: Block,
    stream: TextIO | None = None,
    *,
    use_ansi: bool | None = None,
    no_color: bool | None = None,
) -> None:
    """Print a Block to a stream, optionally with ANSI styling.

    Renders the block line-by-line. When use_ansi is True, includes ANSI
    escape codes for styling. When False, outputs plain text only.
    When None (default), auto-detects from stream.isatty().

    Args:
        block: The Block to print.
        stream: Output stream (defaults to sys.stdout, resolved at call time).
        use_ansi: Whether to include ANSI escape codes (default: auto-detect).
        no_color: The NO_COLOR policy for the serializing Writer. ``None``
            (default) lets the Writer resolve it ambiently from the environment;
            a host that has already resolved the delivery's color snapshot passes
            that exact value so the serializer and its capability bracket cannot
            split (§9.1).
    """
    if stream is None:
        stream = sys.stdout
    if use_ansi is None:
        use_ansi = hasattr(stream, "isatty") and stream.isatty()
    if use_ansi:
        writer = Writer(stream, no_color=no_color)
        write_block_ansi(block, writer, stream)
    else:
        # Plain text: just characters, no styling.
        # rstrip trailing spaces — join_vertical pads to widest block,
        # which creates noise when piped to files/other tools.
        for row_idx in range(block.height):
            line = row_visible_text(block.row(row_idx))
            stream.write(line.rstrip())
            stream.write("\n")

    stream.flush()


def _block_ref_row(block: Block, row_idx: int) -> Sequence[str | None] | None:
    """The ref row for a block row: per-cell grid, uniform block ref, or None.

    Mirrors compose.py's ref-row idiom — a per-cell ``_refs`` override wins, else
    the uniform whole-block ``ref``, else no refs — so the ANSI reader threads
    denotation through ``iter_trimmed_row_spans`` without reaching into Block for
    a bespoke accessor. Returns None on the common (ref-less) path so the span
    walk stays on its fast branch.
    """
    refs = block._refs
    if refs is not None:
        return refs[row_idx]
    if block.ref is not None:
        return (block.ref,) * block.width
    return None


def render_row_ansi(block: Block, row_idx: int, writer: Writer, *, clear_eol: bool = False) -> str:
    """Render one row of a Block to an ANSI string (no trailing newline).

    With clear_eol, the row ends in erase-to-end-of-line (CSI 0K) so it
    cleanly overwrites a longer previous line — the in-place overwrite
    discipline, where a region is never blanked ahead of its redraw.
    """
    out: list[str] = []
    last_style: Style | None = None
    last_ref: str | None = None  # ref of the open OSC 8 link (None ⇒ none open)
    resolved: dict[str, str | None] = {}  # memo: resolve each distinct ref once

    for span in iter_trimmed_row_spans(block.row(row_idx), _block_ref_row(block, row_idx)):
        cell = span.cells[0]
        if cell.style != last_style:
            out.append(writer.reset_style())
            sgr = writer.apply_style(current_palette().resolve_style(cell.style))
            if sgr:
                out.append(sgr)
            last_style = cell.style

        ref = span.refs[0] if span.refs is not None else None
        target_ref, uri = writer._link_target(ref, resolved)
        if target_ref != last_ref:
            if last_ref is not None:
                out.append(writer.close_hyperlink())
            if uri is not None:  # uri and target_ref are set together
                out.append(writer.open_hyperlink(uri))
            last_ref = target_ref

        out.append(cell.char)

    # Close any open link BEFORE reset_style — an OSC 8 must never leak across
    # the newline the caller appends after this row.
    if last_ref is not None:
        out.append(writer.close_hyperlink())
    out.append(writer.reset_style())
    if clear_eol:
        out.append("\x1b[0K")
    return "".join(out)


def render_block_ansi(block: Block, writer: Writer, *, clear_eol: bool = False) -> str:
    """Render a Block to one ANSI string."""
    return "".join(
        render_row_ansi(block, row_idx, writer, clear_eol=clear_eol) + "\n"
        for row_idx in range(block.height)
    )


def write_block_ansi(block: Block, writer: Writer, stream: TextIO) -> None:
    """Write a Block to a stream with ANSI styling.

    Shared by `print_block` and `InPlaceRenderer`.
    """
    stream.write(render_block_ansi(block, writer))


@dataclass(frozen=True)
class ScrollOp:
    """Scroll a region vertically by n lines.

    Coordinates are 0-based, inclusive. Positive n scrolls up (content moves up).
    """

    top: int
    bottom: int
    n: int


RenderOp = CellWrite | ScrollOp
