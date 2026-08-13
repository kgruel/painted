#!/usr/bin/env python3
"""Refs — the denotation channel becomes a link.

A ref is an opaque per-cell annotation: "what does this cell refer to?" A
``RefScheme`` declared through ``use_refs`` turns a ref's ``scheme:value`` into a
URI, and link deliveries read it — HTML wraps the cells in an ``<a href>``, a
terminal emits an OSC 8 hyperlink. A scheme-less or undeclared ref stays inert:
the text still renders, painted just never invents a URI.

Run: uv run demos/primitives/refs.py
"""

from painted import Block, RefScheme, Style, join_horizontal, join_vertical, print_block, use_refs

# The resolver seam is ambient state, scoped with `with use_refs(...)` around
# the render — never set at module scope, where importing the demo would leak
# the scheme into every later render in the same process (the docs-site panel
# run imports many demo modules). The refs_anchors panel spec declares the same
# scheme for its own scoped capture.
FACT_SCHEME = RefScheme("fact", lambda value: f"https://loops.dev/f/{value}")


def spacer() -> Block:
    return Block.text("", Style())


def link(label: str, ref: str) -> Block:
    """A labelled, refed row — the ref carries the denotation, the style the look."""
    return join_horizontal(
        Block.text("  ", Style()),
        Block.text(f"{label:<18}", Style(fg="cyan"), ref=ref),
        Block.text(ref, Style(dim=True)),
    )


def build_output() -> Block:
    return join_vertical(
        spacer(),
        Block.text("  denotation → link", Style(dim=True)),
        spacer(),
        link("deploy succeeded", "fact:01JQ8F"),
        link("cache warmed", "fact:01JQ8G"),
        link("healthcheck ok", "fact:01JQ8H"),
        spacer(),
        Block.text("  inert (no declared scheme)", Style(dim=True)),
        spacer(),
        link("local target", "sidebar"),
        spacer(),
    )


OUTPUT = build_output()


def demo() -> None:
    with use_refs(FACT_SCHEME):
        print_block(OUTPUT)


if __name__ == "__main__":
    demo()
