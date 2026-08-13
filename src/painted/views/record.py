"""Record rendering primitives — timestamped records as styled Blocks.

Three composable primitives for rendering timestamped records:

    record_line       — one record → one Block (zoom-aware)
    record_timeline   — records grouped by date (temporal)
    record_map        — records grouped by key hierarchy (topological)

Plus composable modifiers applied via record_line_composed:

    GutterFn    — colored left edge encoding one dimension
    AttentionFn — dim/highlight by information-gain score

Promoted from experiments/record_line_demo.py.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol

from ..core.block import Block, Wrap
from ..core.cell import Style
from ..core.errors import DeclarationError
from ..core.compose import fit_to_width, join_horizontal, join_vertical, pad, truncate
from ..core.zoom import Zoom
from ..icon_set import current_icons
from ..palette import CORE_ROLE_NAMES, current_palette
from ..core._text_width import display_width, truncate_ellipsis
from ..vocabulary import Thresholds, Vocabulary, vocab_style


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class PayloadLens(Protocol):
    """(kind, payload, zoom) → str | Block.

    Domain-specific rendering of a record's payload. Returns either a plain
    string (rendered with default style) or a pre-styled Block.
    """

    def __call__(self, kind: str, payload: dict, zoom: Zoom) -> str | Block: ...


class GutterFn(Protocol):
    """(kind, payload) → (gutter_char, style).

    Maps a record to its gutter appearance — a single character with a style.
    The gutter encodes exactly one orthogonal dimension (lifecycle, freshness,
    pass/fail, etc.). A view picks ONE gutter function.
    """

    def __call__(self, kind: str, payload: dict) -> tuple[str, Style]: ...


class AttentionFn(Protocol):
    """(kind, payload) → float 0.0–1.0.

    Scores a record's information-gain. High-attention records render fully,
    low-attention records collapse to a dimmed one-liner. Attention is not
    severity — it's how much a record changes your understanding.
    """

    def __call__(self, kind: str, payload: dict) -> float: ...


# ---------------------------------------------------------------------------
# Kind → color mapping
# ---------------------------------------------------------------------------


def _kind_style(kind: str) -> Style:
    """Map a record kind to a palette style.

    Semantic mapping. Follows the journalctl principle:
    most things are unstyled, color marks deviation.
    """
    p = current_palette()
    _map = {
        # Attention: errors and warnings
        "error": p.error,
        "alert": p.error,
        "critical": p.error,
        "warning": p.warning,
        "warn": p.warning,
        # Progress: things that happened
        "change": p.success,
        "deploy": p.success,
        "success": p.success,
        "completed": p.success,
        # Interest: things to notice
        "decision": p.accent,
        "thread": p.accent,
        "task": p.accent,
        "exchange": p.accent,
        "tick": p.accent,
    }
    return _map.get(kind, Style())  # unstyled baseline


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------


def _fmt_ts(ts: datetime, zoom: Zoom) -> str:
    """Format timestamp based on zoom level."""
    if zoom <= Zoom.MINIMAL:
        return ""
    if zoom <= Zoom.DETAILED:
        return ts.strftime("%H:%M")
    # FULL
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_width(zoom: Zoom) -> int:
    """Fixed width allocated to timestamp column."""
    if zoom <= Zoom.MINIMAL:
        return 0
    if zoom <= Zoom.DETAILED:
        return 6  # "14:23 "
    return 21  # "2025-01-15T14:23:00Z "


# ---------------------------------------------------------------------------
# Default payload rendering
# ---------------------------------------------------------------------------

_SUMMARY_KEYS = ("topic", "message", "name", "title", "summary", "description", "text")


def _oneline(text: str) -> str:
    """Collapse any embedded newlines so a summary stays a single line.

    The PayloadLens/summary contract is single-line ("No multiline"). A raw
    payload value (log/commit message, multi-line description) carrying a '\\n'
    would otherwise be emitted into a single Block row as a literal control
    character, breaking the gutter rail. Joining splitlines() with a space
    keeps the gist on one line.
    """
    return " ".join(text.splitlines())


def _default_payload_summary(kind: str, payload: dict) -> str:
    """Extract a one-line summary from payload using well-known keys."""
    return _oneline(_payload_summary_raw(kind, payload))


def _payload_summary_raw(kind: str, payload: dict) -> str:
    parts: list[str] = []

    # Kind-specific patterns
    if kind == "decision":
        topic = payload.get("topic", "")
        msg = payload.get("message", "")
        if topic and msg:
            return f"{topic}: {msg}"
        return topic or msg

    if kind in ("thread", "task"):
        name = payload.get("name", "")
        status = payload.get("status", "")
        summary = payload.get("summary", "")
        if name:
            parts.append(name)
        if status:
            parts.append(f"[{status}]")
        if summary:
            parts.append(summary)
        return " ".join(parts)

    if kind == "exchange":
        prompt = payload.get("prompt", "")
        response = payload.get("response", "")
        if prompt:
            return f"→ {prompt}" + (f" ← {response}" if response else "")

    if kind == "tick":
        name = payload.get("name", "")
        status = payload.get("status", "")
        fold = payload.get("fold", "")
        parts = [p for p in [name, status, fold] if p]
        return " ".join(parts)

    # Generic: try well-known keys
    for key in _SUMMARY_KEYS:
        if key in payload and payload[key]:
            return str(payload[key])

    # Fallback: k=v
    return " ".join(f"{k}={v}" for k, v in payload.items() if v)


# ---------------------------------------------------------------------------
# record_line — the core primitive
# ---------------------------------------------------------------------------


def _fit(block: Block, width: int | None) -> Block:
    """Fit to an exact width, or pass through untouched when width is None.

    ``width=None`` is the *natural-sizing* escape of painted's width contract
    (same as ``Block.text(text, style)`` with no width): the block keeps its
    intrinsic size, no padding and no truncation. ``record_line`` honors it so
    piped callers — whose output feeds other tools/prompts and must not be
    clipped — get full-fidelity records.
    """
    return block if width is None else fit_to_width(block, width)


def _fit_indented_row(width: int, indent: int, render: Callable[[int], Block]) -> Block | None:
    """Render an indented content row, degrading honestly when indent exhausts the budget.

    ``render(content_width)`` builds the row's content at the width remaining
    after ``indent``; the result is left-padded by ``indent``. At narrow
    widths ``width - indent`` can be <= 0 — passing that straight through
    silently collapses the row (RENDER_MODEL_AUDIT path 15). When indent alone
    leaves no cell for content, the row degrades to a single ambient ellipsis
    marker sized to ``width``; when not even one marker cell fits, returns
    ``None`` (the physical-space waiver) and the caller drops the row rather
    than emit a blank line stamped with false content.
    """
    content_width = width - indent
    if content_width >= 1:
        return pad(render(content_width), left=indent)
    marker = current_icons().ellipsis
    if width >= display_width(marker):
        return Block.text(marker, current_palette().muted, width=width)
    return None


def record_line(
    ts: datetime,
    kind: str,
    payload: dict,
    zoom: Zoom,
    width: int | None,
    *,
    payload_lens: PayloadLens | None = None,
) -> Block:
    """Render a single timestamped record as a Block.

    Zoom behavior:
      MINIMAL  — one-line gist, no timestamp, no label
      SUMMARY  — HH:MM [kind] one-line summary
      DETAILED — HH:MM [kind] summary + continuation lines for secondary fields
      FULL     — ISO timestamp [kind] all fields on individual lines
    """
    p = current_palette()

    # --- MINIMAL: just the gist ---
    if zoom <= Zoom.MINIMAL:
        summary = _default_payload_summary(kind, payload)
        if payload_lens:
            result = payload_lens(kind, payload, zoom)
            # MINIMAL is a single-line text summary; if a lens returns a Block,
            # we intentionally drop it and fall back to the default summary.
            summary = result if isinstance(result, str) else summary
        # Block.text's Wrap.NONE default clips silently; a cut summary is a
        # knowing drop at this caller's seam, so mark it with the ambient
        # ellipsis (byte-identical to the old clip when the summary fits).
        if width is not None and display_width(summary) > width:
            summary = truncate_ellipsis(summary, width)
        return Block.text(summary, Style(), width=width)

    # --- Build structured line ---

    # Timestamp
    ts_str = _fmt_ts(ts, zoom)
    ts_w = _ts_width(zoom)

    # Label
    label_text = kind
    kind_s = _kind_style(kind)

    # Content from lens or default
    if payload_lens:
        content = payload_lens(kind, payload, zoom)
    else:
        content = _default_payload_summary(kind, payload)

    # Calculate content width
    meta_width = ts_w + display_width(label_text) + 3  # 3 = "[] " around label + space after
    # Content budget = width remaining after meta. The assembled line is fitted to the
    # exact requested width below (fit_to_width), so this only needs a positive floor —
    # the old floor of 10 forced overflow when width < meta_width + 10.
    # width=None (natural sizing) → no budget, no truncation anywhere downstream.
    content_width = None if width is None else max(width - meta_width, 1)

    # --- SUMMARY: single line ---
    if zoom <= Zoom.SUMMARY:
        if isinstance(content, Block):
            content_str = ""  # Block content handled separately
        else:
            content_str = str(content)

        # Build segments with join_horizontal
        segments: list[Block] = []

        if ts_w > 0:
            ts_block = Block.text(f"{ts_str:<{ts_w}}", p.muted)
            segments.append(ts_block)

        # Label: [kind]
        bracket_l = Block.text("[", p.muted)
        label_block = Block.text(label_text, kind_s)
        bracket_r = Block.text("] ", p.muted)
        segments.extend([bracket_l, label_block, bracket_r])

        # Content (truncated to fit; untouched when natural-sizing)
        if isinstance(content, Block):
            segments.append(content if content_width is None else truncate(content, content_width))
        else:
            if content_width is not None and display_width(content_str) > content_width:
                content_str = truncate_ellipsis(content_str, content_width)
            segments.append(Block.text(content_str, Style()))

        # Fit to exact width: pads a short summary, clips a meta-overflow at tiny widths.
        return _fit(join_horizontal(*segments), width)

    # --- DETAILED: summary + secondary fields on continuation lines ---
    if zoom <= Zoom.DETAILED:
        # Primary line
        segments = []
        if ts_w > 0:
            segments.append(Block.text(f"{ts_str:<{ts_w}}", p.muted))

        segments.append(Block.text("[", p.muted))
        segments.append(Block.text(label_text, kind_s))
        segments.append(Block.text("] ", p.muted))

        # Use lens content directly — Block or str
        if isinstance(content, Block):
            segments.append(content if content_width is None else truncate(content, content_width))
        else:
            primary = str(content)
            if content_width is not None and display_width(primary) > content_width:
                primary = truncate_ellipsis(primary, content_width)
            segments.append(Block.text(primary, Style()))

        primary_line = join_horizontal(*segments)
        lines: list[Block] = [primary_line]

        # Secondary fields: long values or specific keys
        # Shallow indent — gutter rail provides visual continuity to parent
        indent = "  "
        for k, v in payload.items():
            if v is None or v == "":
                continue
            # DETAILED renders one truncated continuation line per field, so a
            # multiline value must be collapsed — otherwise the embedded '\n'
            # lands in a single row and breaks the gutter rail. (FULL splits
            # into real rows instead; see below.)
            sv = _oneline(str(v))
            if (
                k in ("description", "message", "body", "response", "output")
                or display_width(sv) > 40
            ):
                field_text = f"{indent}{k}: {sv}"
                if width is not None and display_width(field_text) > width:
                    field_text = truncate_ellipsis(field_text, width)
                lines.append(Block.text(field_text, p.muted))

        return _fit(join_vertical(*lines), width)

    # --- FULL: ISO timestamp + every field on own line ---
    segments = []
    if ts_w > 0:
        segments.append(Block.text(f"{ts_str:<{ts_w}}", p.muted))
    segments.append(Block.text("[", p.muted))
    segments.append(Block.text(label_text, kind_s))
    segments.append(Block.text("] ", p.muted))

    # Render lens content (Block or str) into the header, fitted (not grown) to the
    # requested width per the width-exact contract. For the default summary — and any
    # PayloadLens deriving its summary from payload keys — fitting loses nothing: every
    # value reappears verbatim in the per-field lines below. A custom PayloadLens that
    # returns a *computed/aggregated* summary absent from payload.items() has no such
    # field-line backstop, so its header can be clipped at narrow widths; aggregating
    # lenses that need full-width headers should emit the aggregate as a payload field.
    if isinstance(content, Block):
        segments.append(content)
    else:
        segments.append(Block.text(str(content), Style()))

    header_line = _fit(join_horizontal(*segments), width)
    lines = [header_line]

    # Shallow indent — gutter rail provides visual continuity to parent.
    # FULL shows complete values; long lines WRAP to the exact width (grow height)
    # rather than overflowing — data completeness AND width-exactness both hold.
    indent = "  "
    for k, v in payload.items():
        if v is None or v == "":
            continue
        # Each value line wraps to the exact width; Wrap.WORD hard-breaks over-long
        # tokens, so no data is lost. Block.text honors the value's newlines;
        # splitlines-then-join normalizes exotic breaks and drops a trailing one.
        sv = "\n".join(str(v).splitlines())
        # width=None → natural sizing, no wrap (nothing to reflow against).
        wrap = Wrap.WORD if width is not None else Wrap.NONE
        lines.append(Block.text(f"{indent}{k}: {sv}", p.muted, width=width, wrap=wrap))

    return _fit(join_vertical(*lines), width)


# ---------------------------------------------------------------------------
# record_timeline — temporal composition
# ---------------------------------------------------------------------------


def record_timeline(
    records: list[tuple[datetime, str, dict]],
    zoom: Zoom,
    width: int,
    *,
    payload_lens: PayloadLens | None = None,
) -> Block:
    """Render a chronological timeline of records, grouped by date.

    Zoom behavior:
      MINIMAL  — kind count summary
      SUMMARY+ — date-grouped record lines
    """
    if not records:
        # Honor the exact-width contract even when empty (pad/clip to width).
        return Block.text("(no records)", current_palette().muted, width=width)

    # --- MINIMAL: counts ---
    if zoom <= Zoom.MINIMAL:
        counts = Counter(kind for _, kind, _ in records)
        parts = [f"{n} {k}" for k, n in counts.most_common()]
        return Block.text(", ".join(parts), Style(), width=width)

    # --- Group by date ---
    p = current_palette()
    groups: dict[str, list[tuple[datetime, str, dict]]] = {}
    for ts, kind, payload in records:
        date_key = ts.strftime("%Y-%m-%d")
        groups.setdefault(date_key, []).append((ts, kind, payload))

    all_blocks: list[Block] = []
    for date_key, group_records in groups.items():
        # Date header. Fit to width now, individually — every row composed
        # below is already width-exact, so the trailing fit_to_width over the
        # whole stack has nothing left to clip. Deferring this fit (as the
        # natural-width header used to) meant the final call widened every
        # already-exact row back out via join_vertical's padding, then
        # re-marked it on the way back down: a second, spurious ellipsis
        # stacked onto a row that had already marked its own cut honestly.
        header = fit_to_width(Block.text(f"{date_key}:", p.muted.merge(Style(bold=True))), width)
        all_blocks.append(header)

        # Record lines, indented
        for ts, kind, payload in group_records:
            row = _fit_indented_row(
                width,
                2,
                lambda cw, ts=ts, kind=kind, payload=payload: record_line(
                    ts, kind, payload, zoom, cw, payload_lens=payload_lens
                ),
            )
            if row is not None:
                all_blocks.append(row)

    # Every block above is already exactly `width` wide; this join (and the
    # fit_to_width around it) is a defensive no-op, not a clipper.
    return fit_to_width(join_vertical(*all_blocks, gap=0), width)


# ---------------------------------------------------------------------------
# Modifier application
# ---------------------------------------------------------------------------

# Weight stepping: primary gutter char on first line, lighter on continuation.
# Error heaviest → pass lightest; the rail never breaks.
_GUTTER_STEP: dict[str, str] = {"█": "▐", "▐": "│", "│": "│", "·": "·"}


def apply_gutter(
    block: Block,
    kind: str,
    payload: dict,
    gutter_fn: GutterFn,
) -> Block:
    """Apply a gutter modifier to a rendered block.

    Builds a continuous gutter rail matching the block's height.
    First line uses the primary weight from gutter_fn; continuation
    lines step down one weight level (``█→▐→│``).
    """
    ch, style = gutter_fn(kind, payload)
    cont_ch = _GUTTER_STEP.get(ch, ch)

    rows = [(f"{ch} ", style)]
    if block.height > 1:
        rows += [(f"{cont_ch} ", style)] * (block.height - 1)

    gutter_block = Block.column(rows)
    return join_horizontal(gutter_block, block)


def apply_attention(
    block: Block,
    kind: str,
    payload: dict,
    attention_fn: AttentionFn,
    *,
    zoom: Zoom = Zoom.SUMMARY,
    width: int | None,
    ts: datetime | None = None,
    payload_lens: PayloadLens | None = None,
    score: float | None = None,
) -> Block:
    """Apply attention modifier: high-attention records render fully,
    low-attention records collapse to a dimmed one-liner.

    Args:
        width: Target width. Required because the low-attention collapse path
            creates a Block at this width.
        score: Pre-computed attention score. Pass it when the caller has already
            evaluated ``attention_fn`` (e.g. record_line_composed reserves marker
            width from it) so the callback runs exactly once — the AttentionFn
            protocol does not promise purity, so a second call could disagree.
    """
    if score is None:
        score = attention_fn(kind, payload)
    p = current_palette()
    icons = current_icons()

    if score >= 0.7:
        # Full rendering with the high-rank marker (ambient, so it degrades).
        marker = Block.text(f"{icons.rank_top} ", _kind_style(kind))
        return join_horizontal(marker, block)
    elif score >= 0.3:
        # Normal rendering, no marker
        return join_horizontal(Block.text("  ", Style()), block)
    else:
        # Collapse to dim one-liner regardless of zoom
        summary = _default_payload_summary(kind, payload)
        if width is not None and display_width(summary) > width - 10:
            summary = truncate_ellipsis(summary, width - 10)
        ts_str = ts.strftime("%H:%M") if ts else ""
        prefix = f"{ts_str} " if ts_str else ""
        return Block.text(f"{icons.rank_tail} {prefix}{kind}: {summary}", p.muted, width=width)


# ---------------------------------------------------------------------------
# record_line_composed — record with modifiers
# ---------------------------------------------------------------------------


def record_line_composed(
    ts: datetime,
    kind: str,
    payload: dict,
    zoom: Zoom,
    width: int | None,
    *,
    payload_lens: PayloadLens | None = None,
    gutter_fn: GutterFn | None = None,
    attention_fn: AttentionFn | None = None,
) -> Block:
    """record_line with composable modifiers applied.

    Composition order: record_line → attention → gutter (outside-in).
    Gutter is outermost because it's a visual frame.

    ``width=None`` (natural sizing) propagates to the inner record_line: no
    column reservation, no final fit. The gutter rail (height-based) still
    applies; the attention markers still prepend. Natural-width composed
    records simply keep their intrinsic width.
    """
    # Reserve width for every modifier that prepends columns, so the composed
    # block lands at exactly `width` and the final fit_to_width is a no-op rather
    # than a right-edge clipper that would silently drop content cells.
    # width=None: nothing to reserve against — keep inner_width None throughout.
    gutter_cols = 2 if gutter_fn else 0

    # Evaluate the attention score ONCE. The AttentionFn protocol does not promise
    # purity/idempotence, so a stateful/time/random callback could score differently
    # on a second call — and the marker-width reservation here MUST match what the
    # renderer draws. Thread the single score into apply_attention below.
    score = attention_fn(kind, payload) if attention_fn else None

    # The marker prepends 2 cols ("◆ " at score>=0.7, "  " at >=0.3). The <0.3
    # collapse path builds its own block at the passed width and prepends nothing,
    # so it needs no reservation.
    marker_cols = 2 if score is not None and score >= 0.3 else 0

    inner_width = None if width is None else width - gutter_cols - marker_cols

    # Base render
    block = record_line(ts, kind, payload, zoom, inner_width, payload_lens=payload_lens)

    # Apply attention (may collapse to one-liner)
    if attention_fn:
        block = apply_attention(
            block,
            kind,
            payload,
            attention_fn,
            zoom=zoom,
            width=inner_width,
            ts=ts,
            payload_lens=payload_lens,
            score=score,
        )

    # Apply gutter (outermost)
    if gutter_fn:
        block = apply_gutter(block, kind, payload, gutter_fn)

    # Modifiers prepend exactly the columns reserved above, so the composed block
    # is already `width` wide. This fit is a defensive no-op that guarantees the
    # composer honors its width arg — it must never clip content cells.
    return _fit(block, width)


# ---------------------------------------------------------------------------
# record_map — topological grouping
# ---------------------------------------------------------------------------


def record_map(
    records: list[tuple[datetime, str, dict]],
    zoom: Zoom,
    width: int,
    *,
    group_key: Callable[[str, dict], str] = lambda k, p: k,
    payload_lens: PayloadLens | None = None,
    gutter_fn: GutterFn | None = None,
    attention_fn: AttentionFn | None = None,
    sort_groups: str = "alpha",  # "alpha", "count", "recent"
) -> Block:
    """Render records grouped by a topological key, not by time.

    group_key: (kind, payload) → group name. Supports hierarchy via '/'.
    sort_groups: how to order groups — "alpha", "count", or "recent".

    Zoom behavior:
      MINIMAL  — group names + counts, one line
      SUMMARY  — group headers + latest record per group
      DETAILED — group headers + all records per group
      FULL     — group headers + all records fully expanded
    """
    if not records:
        # Honor the exact-width contract even when empty (pad/clip to width).
        return Block.text("(no records)", current_palette().muted, width=width)

    p = current_palette()

    # Group records
    groups: dict[str, list[tuple[datetime, str, dict]]] = {}
    for ts, kind, payload in records:
        key = group_key(kind, payload)
        groups.setdefault(key, []).append((ts, kind, payload))

    # Sort groups
    if sort_groups == "count":
        sorted_keys = sorted(groups.keys(), key=lambda k: len(groups[k]), reverse=True)
    elif sort_groups == "recent":
        sorted_keys = sorted(
            groups.keys(), key=lambda k: max(ts for ts, _, _ in groups[k]), reverse=True
        )
    else:
        sorted_keys = sorted(groups.keys())

    # --- MINIMAL: group names + counts ---
    if zoom <= Zoom.MINIMAL:
        parts = [f"{k} ({len(v)})" for k, v in [(k, groups[k]) for k in sorted_keys]]
        return Block.text("  ".join(parts), Style(), width=width)

    # --- Build tree structure ---
    # Parse hierarchy from '/' in keys
    tree: dict[str, dict[str, list[tuple[datetime, str, dict]]]] = {}
    for key in sorted_keys:
        key_parts = key.split("/", 1)
        if len(key_parts) == 2:
            tree.setdefault(key_parts[0], {})[key_parts[1]] = groups[key]
        else:
            tree.setdefault(key, {})[""] = groups[key]

    all_blocks: list[Block] = []

    for top_key in tree:
        subtree = tree[top_key]
        total_count = sum(len(v) for v in subtree.values())

        # Top-level group header. Fit to width now, individually — every row
        # composed below is already width-exact, so the trailing fit_to_width
        # over the whole stack has nothing left to clip. Deferring this fit
        # (as the natural-width header used to) meant the final call widened
        # every already-exact row back out via join_vertical's padding, then
        # re-marked it on the way back down: a second, spurious ellipsis
        # stacked onto a row that had already marked its own cut honestly.
        header_parts = [
            Block.text(f"  {top_key}", Style(bold=True)),
            Block.text(f" ({total_count})", p.muted),
        ]
        all_blocks.append(fit_to_width(join_horizontal(*header_parts), width))

        for sub_key, sub_records in subtree.items():
            # Sort by timestamp within group
            sub_records.sort(key=lambda r: r[0])

            if sub_key:
                # Sub-group header
                sub_header = Block.text(f"    {sub_key} ({len(sub_records)})", p.accent)
                all_blocks.append(fit_to_width(sub_header, width))
                indent = 6
            else:
                indent = 4

            if zoom <= Zoom.SUMMARY:
                # Show only the latest record per group
                latest_ts, latest_kind, latest_payload = sub_records[-1]
                row = _fit_indented_row(
                    width,
                    indent,
                    lambda cw: record_line_composed(
                        latest_ts,
                        latest_kind,
                        latest_payload,
                        Zoom.SUMMARY,
                        cw,
                        payload_lens=payload_lens,
                        gutter_fn=gutter_fn,
                        attention_fn=attention_fn,
                    ),
                )
                if row is not None:
                    all_blocks.append(row)
            else:
                # Show all records
                record_zoom = Zoom.DETAILED if zoom <= Zoom.DETAILED else Zoom.FULL
                for ts, kind, payload in sub_records:
                    row = _fit_indented_row(
                        width,
                        indent,
                        lambda cw, ts=ts, kind=kind, payload=payload: record_line_composed(
                            ts,
                            kind,
                            payload,
                            record_zoom,
                            cw,
                            payload_lens=payload_lens,
                            gutter_fn=gutter_fn,
                            attention_fn=attention_fn,
                        ),
                    )
                    if row is not None:
                        all_blocks.append(row)

        # Gap between top-level groups
        all_blocks.append(Block.text("", Style(), width=width))

    # Every block above is already exactly `width` wide; this join (and the
    # fit_to_width around it) is a defensive no-op, not a clipper.
    return fit_to_width(join_vertical(*all_blocks), width)


# ---------------------------------------------------------------------------
# Concrete gutter functions
# ---------------------------------------------------------------------------


def _glyph(vocabulary: Vocabulary, value: str, glyphs: tuple[str, ...]) -> str:
    """The rail glyph for ``value``: heaviest at the attention end, clamped.

    Distance is measured from the end ``attention`` names — the eye's end. An
    ``attention="last"`` vocabulary (severity, lifecycle) puts ``glyphs[0]`` on
    its final value and fades toward the first; ``attention="first"`` flips the
    direction. Past the ramp's length the last glyph repeats (a long vocabulary
    with a short ramp settles onto its lightest weight). Direction of
    distinction is the vocabulary's declared property, never a branch here.
    """
    index = vocabulary.index(value)
    if vocabulary.attention == "last":
        distance = (len(vocabulary.values) - 1) - index
    else:
        distance = index
    return glyphs[min(distance, len(glyphs) - 1)]


def record_gutter(
    vocabulary: Vocabulary,
    field: str,
    *,
    aliases: Mapping[str, str] | None = None,
    thresholds: Thresholds | None = None,
    glyphs: tuple[str, ...] = ("█", "▐", "│"),
    unknown: tuple[str, str] = ("│", "muted"),
    default: float = 0,
) -> GutterFn:
    """Build a :class:`GutterFn` from an ordered vocabulary.

    A gutter encodes one dimension as a colored rail; this factory derives that
    rail from a declaration instead of an ``if``-chain. It reads ``field`` from
    each payload and resolves it to a vocabulary value — directly, through
    ``aliases`` normalization (raw payload spellings → members), or through
    ``thresholds`` for a numeric field. The value colors the rail via the same
    value→role→palette resolution as ``mark_style`` (so a ``use_palette`` swap
    re-tints the rail live), and its distance from the ``attention`` end against
    ``glyphs`` picks the glyph weight.

    A payload value outside the vocabulary renders the declared ``unknown``
    fallback — ``(glyph, core-role name)``, resolved against the current palette
    at call time. A gutter renders arbitrary data, so unknown data is *tolerated*
    rather than raised; nothing is silent, because the fallback is itself
    declared. The honesty rules (design doc §1) govern the *declaration* — an
    unordered vocabulary, colliding ``aliases``/``thresholds``, an alias onto a
    non-member — not the data a rail is later asked to paint. Those declaration
    faults raise here, at construction:

    - ``vocabulary`` must be ordered — the glyph ramp needs index + attention.
    - ``aliases`` and ``thresholds`` are mutually exclusive (categorical vs
      numeric resolution).
    - a ``thresholds`` must resolve onto *this* vocabulary (same object).
    - ``glyphs`` must be non-empty.
    - every alias value must be a member (alias *keys* are raw data — not
      validated as names).
    """
    if not vocabulary.ordered:
        raise DeclarationError(
            "record_gutter needs an ordered vocabulary (the glyph ramp is "
            f"distance from the attention end); {vocabulary.name!r} is unordered"
        )
    if aliases is not None and thresholds is not None:
        raise DeclarationError(
            "record_gutter takes aliases OR thresholds, not both: aliases "
            "normalize categorical strings, thresholds bucket a numeric field"
        )
    if thresholds is not None and thresholds.vocabulary is not vocabulary:
        raise DeclarationError(
            "record_gutter thresholds must resolve onto the same vocabulary "
            f"({vocabulary.name!r}), not {thresholds.vocabulary.name!r}"
        )
    if not glyphs:
        raise DeclarationError("record_gutter needs at least one ramp glyph")
    unknown_glyph, unknown_role = unknown
    # The rail budget is exactly one display column per glyph — apply_gutter
    # reserves 2 (glyph + space), so a wide glyph would silently clip content
    # at the final fit. A declaration fault, caught here (width-is-exact).
    for ch in (*glyphs, unknown_glyph):
        if display_width(ch) != 1:
            raise DeclarationError(
                f"record_gutter glyph {ch!r} is {display_width(ch)} display "
                "columns wide; a rail glyph must be exactly 1"
            )
    if unknown_role not in CORE_ROLE_NAMES:
        raise DeclarationError(
            f"record_gutter unknown role {unknown_role!r} is not a core role "
            f"({sorted(CORE_ROLE_NAMES)!r})"
        )
    for alias, target in (aliases or {}).items():
        if target not in vocabulary.values:
            raise DeclarationError(
                f"record_gutter alias {alias!r} -> {target!r} is not a member "
                f"of vocabulary {vocabulary.name!r}"
            )

    alias_map = dict(aliases) if aliases else {}

    def _unknown_style() -> Style:
        # The same D5 rule mark_style honors: `text` may be None (no substrate
        # declared) and then means "unstyled" — never a bare None escaping the
        # GutterFn -> (str, Style) contract.
        style = getattr(current_palette(), unknown_role)
        return style if style is not None else Style()

    def gutter(kind: str, payload: dict) -> tuple[str, Style]:
        if thresholds is not None:
            # Numeric field: a resolvable number always yields a member, so the
            # unknown fallback fires only for data the ladder can't place — a
            # non-numeric value, None, or NaN (a rail never raises on data).
            try:
                value = thresholds.resolve(float(payload.get(field, default)))
            except (TypeError, ValueError):
                return unknown_glyph, _unknown_style()
        else:
            raw = payload.get(field)
            # Only strings can name a member; anything else (None, numbers,
            # unhashable structures) is out-of-vocabulary data by definition.
            value = alias_map.get(raw, raw) if isinstance(raw, str) else None
            if value is None or value not in vocabulary.values:
                # Missing field or out-of-vocabulary data: the declared fallback.
                return unknown_glyph, _unknown_style()
        return _glyph(vocabulary, value, glyphs), vocab_style(vocabulary, value)

    return gutter


# The three shipped gutters, now thin declarations over ``record_gutter``. Each
# is an ordered example vocabulary (module-level, deliberately NOT registered in
# _BUILTIN_VOCABULARIES — an app declares its own `freshness`/`lifecycle`, and a
# reserved painted name would collide) plus one factory call. The status dialects
# that were three private if-chains are now the vocabularies' declared members,
# with the raw payload spellings folded in as aliases.

# Task lifecycle: attention on the `blocked` end (heaviest rail), fading to
# `completed`. success/warning/error roles carry the color.
LIFECYCLE_VOCABULARY = Vocabulary(
    "lifecycle",
    values=("completed", "running", "stalled", "blocked"),
    ordered=True,
    roles={
        "completed": "success",
        "running": "success",
        "stalled": "warning",
        "blocked": "error",
    },
)

# Test/check outcome: `failed` pulls the eye, `passed` recedes.
PASS_FAIL_VOCABULARY = Vocabulary(
    "pass-fail",
    values=("passed", "warning", "failed"),
    ordered=True,
    roles={"passed": "success", "warning": "warning", "failed": "error"},
)

# Freshness: `old` pulls the eye as a faded dot. `recent` binds the `text`
# substrate role — a bare Style() under every shipped palette today (text=None),
# themeable tomorrow without touching this declaration.
FRESHNESS_VOCABULARY = Vocabulary(
    "freshness",
    values=("fresh", "recent", "stale", "old"),
    ordered=True,
    roles={"fresh": "accent", "recent": "text", "stale": "muted", "old": "muted"},
)
# Integer-day floors: `_age_days` is integer-day data, so a value resolves by the
# greatest floor it clears — 0..1 fresh, 2..7 recent, 8..30 stale, 31+ old.
FRESHNESS_AGE = Thresholds(FRESHNESS_VOCABULARY, {0: "fresh", 2: "recent", 8: "stale", 31: "old"})

# Gutter by task lifecycle: green=moving, yellow=stalled, red=blocked.
gutter_lifecycle = record_gutter(
    LIFECYCLE_VOCABULARY,
    "status",
    aliases={
        "errored": "blocked",
        "failed": "blocked",
        "waiting": "stalled",
        "pending": "stalled",
        "in-progress": "running",
        "active": "running",
        "done": "completed",
        "decided": "completed",
        "healthy": "completed",
    },
)

# Gutter by pass/fail for test/check results.
gutter_pass_fail = record_gutter(
    PASS_FAIL_VOCABULARY,
    "status",
    aliases={"success": "passed", "ok": "passed", "warn": "warning", "error": "failed"},
)

# Gutter by freshness: bright=recent, dim=stale. Reads `_age_days` (default 0).
gutter_freshness = record_gutter(
    FRESHNESS_VOCABULARY,
    "_age_days",
    thresholds=FRESHNESS_AGE,
    glyphs=("·", "│"),
)


# ---------------------------------------------------------------------------
# Concrete attention functions
# ---------------------------------------------------------------------------


def attention_staleness(kind: str, payload: dict) -> float:
    """Stale items dim, fresh items bright.

    Reads ``_age_days`` from payload (default 0).
    """
    age_days = payload.get("_age_days", 0)
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.7
    if age_days <= 30:
        return 0.3
    return 0.1


def attention_novelty(kind: str, payload: dict) -> float:
    """First occurrences highlight, repeated events dim.

    Reads ``occurrences`` or ``_count`` from payload (default 1).
    """
    occurrences = payload.get("occurrences", payload.get("_count", 1))
    if occurrences <= 1:
        return 1.0
    if occurrences <= 3:
        return 0.6
    return 0.2


def attention_blocked(kind: str, payload: dict) -> float:
    """Blocked tasks scream, completed tasks whisper."""
    status = payload.get("status", "")
    if status in ("blocked", "errored", "failed"):
        return 1.0
    if status in ("stalled", "waiting"):
        return 0.8
    if status in ("running", "in-progress", "active"):
        return 0.5
    if status in ("completed", "done"):
        return 0.2
    return 0.5


def attention_relevance(kind: str, payload: dict) -> float:
    """Score-based attention for search results.

    Reads ``_relevance`` from payload (default 0.5).
    """
    return payload.get("_relevance", 0.5)
