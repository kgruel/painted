#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Denotation — refed record lines: one ref channel, two readers.

A store activity feed rendered with ``record_line``: the payload lens stamps
each summary with a ref (``fact:01JQ8F…``) — *what the line refers to*, never
how it looks. The same refs then serve every reader the delivery has: a
declared ``RefScheme`` resolves them to URIs (OSC 8 links on a TTY), and
``Buffer.hit(x, y)`` resolves mouse coordinates back to them. The lens declares
meaning once; each delivery reads what it can. Undeclared schemes stay inert —
the line still renders, painted never invents a URI.

    uv run demos/patterns/denotation.py -q     # census: records, refs, resolvable
    uv run demos/patterns/denotation.py        # the refed feed (links on a TTY)
    uv run demos/patterns/denotation.py -v     # + resolution table (the link reader)
    uv run demos/patterns/denotation.py -vv    # + hit probes (the mouse reader)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime

from painted import (
    Block,
    CliContext,
    RefScheme,
    Style,
    Zoom,
    join_horizontal,
    join_vertical,
    resolve_ref,
    run_cli,
    truncate,
    use_refs,
)
from painted.palette import current_palette
from painted.tui import Buffer
from painted.views import record_line

# --- Schemes: declared in main() around the delivery, never at module scope
# (a module-scope use_refs would leak into every later render in this process).
# The render itself never requires them — an undeclared ref is inert, not an error.

SCHEMES = (
    RefScheme("fact", lambda value: f"https://loops.dev/f/{value}"),
    RefScheme("run", lambda value: f"https://ci.example.dev/run/{value}"),
)


# --- Data: a morning of store activity, each record carrying its denotation ---


@dataclass(frozen=True)
class FeedData:
    records: tuple[tuple[datetime, str, dict], ...]


_D = datetime  # fixed timestamps — the feed is frozen data, not wall-clock


FEED: tuple[tuple[datetime, str, dict], ...] = (
    (
        _D(2026, 7, 5, 9, 41, 3),
        "deploy",
        {
            "ref": "fact:01JQ8FZQ4R",
            "service": "api-gateway",
            "revision": "v2.4.1",
            "status": "succeeded",
        },
    ),
    (
        _D(2026, 7, 5, 9, 42, 17),
        "scale",
        {"ref": "fact:01JQ8G2M9K", "service": "worker", "replicas": "3 -> 5"},
    ),
    (
        _D(2026, 7, 5, 9, 44, 52),
        "alert",
        {
            "ref": "run:8841",
            "service": "auth-service",
            "p95_ms": 2100,
            "threshold_ms": 500,
        },
    ),
    (
        _D(2026, 7, 5, 9, 45, 30),
        "rollback",
        {
            "ref": "fact:01JQ8G8T2W",
            "service": "auth-service",
            "revision": "v1.9.0",
            "status": "succeeded",
        },
    ),
    (
        _D(2026, 7, 5, 9, 47, 11),
        "note",
        {"ref": "trace:span-19", "text": "auth-service latency under investigation"},
    ),
)


# --- The lens: interprets payloads AND stamps the denotation ---


def _summary_text(kind: str, payload: dict) -> str:
    if kind == "deploy":
        return f"{payload['service']} {payload['revision']} {payload['status']}"
    if kind == "scale":
        return f"{payload['service']} replicas {payload['replicas']}"
    if kind == "alert":
        return f"{payload['service']} p95 {payload['p95_ms']}ms (threshold {payload['threshold_ms']}ms)"
    if kind == "rollback":
        return f"{payload['service']} rolled back to {payload['revision']}"
    return str(payload.get("text", ""))


def _summary_style(kind: str) -> Style:
    p = current_palette()
    return {
        "deploy": p.success,
        "scale": p.accent,
        "alert": p.warning,
        "rollback": p.error,
    }.get(kind, p.muted)


def _feed_lens(kind: str, payload: dict, zoom: Zoom) -> str | Block:
    """Summary as a styled Block with the record's ref stamped on it.

    The ref rides the summary cells through record_line's composition — no
    record_line support needed, refs survive every join.
    """
    text = _summary_text(kind, payload)
    if zoom <= Zoom.MINIMAL:
        return text
    return Block.text(text, _summary_style(kind), ref=payload["ref"])


# --- Blocks ---


def _header(text: str) -> Block:
    return Block.text(f"  {text}", Style(dim=True))


def _spacer() -> Block:
    return Block.text("", Style())


def _feed_block(data: FeedData, zoom: Zoom) -> Block:
    """The feed itself discloses with zoom: SUMMARY is one line per record,
    DETAILED adds continuation fields, FULL shows everything."""
    rows = [
        record_line(ts, kind, payload, zoom, None, payload_lens=_feed_lens)
        for ts, kind, payload in data.records
    ]
    return join_vertical(*rows)


def _inert_reason(ref: str) -> str:
    scheme, sep, _ = ref.partition(":")
    if not sep:
        return "inert — scheme-less (hit-testing idiom)"
    return f"inert — no RefScheme declares {scheme!r}"


def _resolution_table(data: FeedData) -> Block:
    """Each ref through resolve_ref — the link deliveries' choke point."""
    p = current_palette()
    rows: list[Block] = []
    for _ts, _kind, payload in data.records:
        ref = payload["ref"]
        uri = resolve_ref(ref)
        target = Block.text(uri, p.accent) if uri else Block.text(_inert_reason(ref), p.muted)
        rows.append(
            join_horizontal(
                Block.text(f"  {ref:<18}", Style(dim=True)),
                Block.text("-> ", p.muted),
                target,
            )
        )
    return join_vertical(*rows)


def _hit_probes(data: FeedData) -> Block:
    """Paint the summary feed into a Buffer, then ask coordinates what they mean."""
    p = current_palette()
    feed = _feed_block(data, Zoom.SUMMARY)
    buf = Buffer(feed.width, feed.height)
    feed.paint(buf, 0, 0)

    probes: list[tuple[int, int, str]] = [(2, 0, "timestamp column")]
    probes += [(18, y, "summary text") for y in range(feed.height)]

    rows: list[Block] = []
    for x, y, label in probes:
        ref = buf.hit(x, y)
        rows.append(
            join_horizontal(
                Block.text(f"  hit({x:>2},{y})", Style(dim=True)),
                Block.text(f"  {ref if ref is not None else '(no ref)':<18}", p.accent if ref else p.muted),
                Block.text(f" {label}", Style(dim=True)),
            )
        )
    return join_vertical(*rows)


# --- Zoom renderers ---


def _render_minimal(data: FeedData, width: int) -> Block:
    p = current_palette()
    refs = [payload["ref"] for _ts, _kind, payload in data.records]
    resolvable = sum(1 for r in refs if resolve_ref(r) is not None)
    return truncate(
        Block.text(
            f"{len(data.records)} records  {len(refs)} refed  {resolvable} resolvable",
            p.accent,
        ),
        width,
    )


def _render_summary(data: FeedData, width: int, zoom: Zoom = Zoom.SUMMARY) -> Block:
    return truncate(
        join_vertical(
            _spacer(),
            _header("store activity (each summary carries its ref)"),
            _spacer(),
            _feed_block(data, zoom),
        ),
        width,
    )


def _render_detailed(data: FeedData, width: int, zoom: Zoom = Zoom.DETAILED) -> Block:
    return truncate(
        join_vertical(
            _render_summary(data, width, zoom),
            _spacer(),
            _header("the link reader: resolve_ref(ref) -> URI | inert"),
            _spacer(),
            _resolution_table(data),
        ),
        width,
    )


def _render_full(data: FeedData, width: int) -> Block:
    return truncate(
        join_vertical(
            _render_detailed(data, width, Zoom.FULL),
            _spacer(),
            _header("the mouse reader: Buffer.hit(x, y) -> ref"),
            _spacer(),
            _hit_probes(data),
            _spacer(),
        ),
        width,
    )


def _render(ctx: CliContext, data: FeedData) -> Block:
    if ctx.zoom >= Zoom.FULL:
        return _render_full(data, ctx.width)
    if ctx.zoom >= Zoom.DETAILED:
        return _render_detailed(data, ctx.width)
    if ctx.zoom >= Zoom.SUMMARY:
        return _render_summary(data, ctx.width)
    return _render_minimal(data, ctx.width)


def _fetch() -> FeedData:
    return FeedData(records=FEED)


def main() -> int:
    with use_refs(*SCHEMES):
        return run_cli(
            sys.argv[1:],
            render=_render,
            fetch=_fetch,
            description=__doc__,
            prog="denotation.py",
        )


if __name__ == "__main__":
    sys.exit(main())
