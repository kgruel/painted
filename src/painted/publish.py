"""The doc-IR publisher: ``to_html`` — a doc node tree to SEMANTIC html.

The web counterpart of ``doc_lens`` (``core/doc.py``), per the taxonomy in
``docs/DOC_IR_DESIGN.md``: a *publisher* emits foreign semantics the renderer
has no type for (``<section>``/``<h2>``/``<dl>``). It lives at the package
root beside ``display.py`` — the terminal-side entry and the foreign-semantics
side, siblings — because a second world (a consumer publishing its own ``Doc``
trees) makes the publisher library surface, not site tooling (the 0.10
amendment; previously ``tools/doc_publish.py``). It reads the node tree
DIRECTLY — rendering chrome to a Block and then Block → HTML would flatten an
``<h1>`` into a bold span (the OCR trap). The one node that legitimately
routes through ``Block → HTML`` (``core/html.py``) is ``Figure``: a
terminal-faithful island inside a semantic page.

Disclosure is the SAME walk the lens uses — ``visible_body`` / ``capped`` from
``core/doc.py`` — so the two sinks cannot disclose differently. ``to_markdown``
is sketched in the design doc, not built; it joins this module if it lands.
"""

from __future__ import annotations

import html as _html

from .core.doc import (
    Code,
    Defs,
    Doc,
    Figure,
    Inline,
    Items,
    Link,
    Node,
    Prose,
    Section,
    capped,
    inline_spans,
    visible_body,
)
from .core.fidelity import Fidelity
from .core.html import render_html
from .core.zoom import Zoom
from .refs import resolve_ref

__all__ = ["to_html", "published_fidelity"]

_MAX_HEADING = 6


def published_fidelity(doc: Doc) -> Fidelity:
    """The fidelity a *published* page renders at: full depth, every tag on.

    The fidelity dials are a terminal affordance (``-v``, a declared tag flag); a
    published page IS the full document. Deriving the tag set from the tree
    (rather than configuring it per page) keeps the site registry equal to the
    ``painted docs`` registry with nothing to drift.
    """
    return Fidelity(depth=Zoom.FULL, visible=_all_tags(doc.body))


def _all_tags(nodes: tuple[Node, ...]) -> frozenset[str]:
    tags: set[str] = set()
    for node in nodes:
        if node.tag is not None:
            tags.add(node.tag)
        if isinstance(node, Section):
            tags |= _all_tags(node.body)
    return frozenset(tags)


def to_html(doc: Doc, *, fidelity: Fidelity | None = None) -> str:
    """Project a ``Doc`` to a semantic HTML fragment (the ``to_html`` publisher).

    ``fidelity`` defaults to ``published_fidelity(doc)`` — the full document.
    Pass one explicitly to publish a disclosed view (same semantics as the lens).
    """
    fid = published_fidelity(doc) if fidelity is None else fidelity
    out: list[str] = ['<article class="painted-doc">\n']
    if doc.title:
        out.append(f"<h1>{_esc(doc.title)}</h1>\n")
    _emit_body(out, doc.body, depth=fid.depth, fidelity=fid, level=2)
    out.append("</article>\n")
    return "".join(out)


def _emit_body(
    out: list[str], nodes: tuple[Node, ...], *, depth: int, fidelity: Fidelity, level: int
) -> None:
    for node, eff in visible_body(nodes, depth, fidelity):
        _emit_node(out, node, eff, fidelity, level)


def _emit_node(out: list[str], node: Node, eff: int, fidelity: Fidelity, level: int) -> None:
    match node:
        case Section():
            _emit_section(out, node, eff, fidelity, level)
        case Prose():
            out.append(f"<p>{_emit_inline(node.content)}</p>\n")
        case Defs():
            _emit_defs(out, node, eff, fidelity)
        case Items():
            _emit_items(out, node, fidelity)
        case Code():
            _emit_code(out, node)
        case Figure():
            _emit_figure(out, node)


def _emit_section(
    out: list[str], section: Section, eff: int, fidelity: Fidelity, level: int
) -> None:
    out.append("<section>\n")
    heading = _esc(section.heading or "")
    if section.hint and eff >= 1:  # the subhead is a tier-1 reveal, like the lens
        hint = f'<span class="hint">{_esc(section.hint)}</span>'
        heading = f"{heading} {hint}" if heading else hint
    if heading:
        h = min(level, _MAX_HEADING)
        out.append(f"<h{h}>{heading}</h{h}>\n")
    # Cascade: the section's own eff becomes its body's local depth (same as the lens).
    _emit_body(out, section.body, depth=eff, fidelity=fidelity, level=level + 1)
    out.append("</section>\n")


def _emit_defs(out: list[str], defs: Defs, eff: int, fidelity: Fidelity) -> None:
    items = capped(defs.items, fidelity)
    if not items:
        return
    if eff == 0:
        # Compact tier: terms only — same disclosure as the lens's terse line.
        out.append('<p class="defs-compact">' + "  ".join(_esc(d.term) for d in items) + "</p>\n")
        return
    out.append("<dl>\n")
    for d in items:
        out.append(f"<dt>{_esc(d.term)}</dt>\n")
        out.append(f"<dd>{_emit_inline(d.summary)}</dd>\n")
        if eff >= 2 and d.detail:
            out.append(f'<dd class="detail">{_emit_inline(d.detail)}</dd>\n')
    out.append("</dl>\n")


def _emit_items(out: list[str], items: Items, fidelity: Fidelity) -> None:
    entries = capped(items.entries, fidelity)
    if not entries:
        return
    tag = "ol" if items.ordered else "ul"
    out.append(f"<{tag}>\n")
    for entry in entries:
        out.append(f"<li>{_emit_inline(entry)}</li>\n")
    out.append(f"</{tag}>\n")


def _emit_code(out: list[str], code: Code) -> None:
    if code.text is None:
        # Deferred docgen resolution — the same placeholder the lens shows.
        label = f"[code: {code.src}]" if code.src else "[code]"
        out.append(f'<p class="code-placeholder">{_esc(label)}</p>\n')
        return
    out.append(f'<pre><code class="language-{_esc(code.lang)}">{_esc(code.text)}</code></pre>\n')


def _emit_figure(out: list[str], fig: Figure) -> None:
    out.append("<figure>\n")
    out.append(render_html(fig.block))
    if fig.caption:
        out.append(f"<figcaption>{_esc(fig.caption)}</figcaption>\n")
    out.append("</figure>\n")


def _emit_inline(content: Inline) -> str:
    """Inline content as escaped HTML — the publisher half of the shared walk.

    Every span comes through ``inline_spans`` (``core/doc.py``), the same
    normalization ``doc_lens`` renders from, so the two sinks cannot render a
    span differently. A ``Link`` resolves its target through the SAME
    ``resolve_ref`` choke point the cell deliveries use: a declared scheme
    yields ``<a href>``, an undeclared one renders the text as plain content —
    identical inertness in both worlds (painted never invents URIs).
    """
    parts: list[str] = []
    for span in inline_spans(content):
        if isinstance(span, Link):
            uri = resolve_ref(span.target)
            if uri:
                parts.append(f'<a href="{_esc(uri)}">{_esc(span.text)}</a>')
            else:
                parts.append(_esc(span.text))
        else:
            parts.append(_esc(span))
    return "".join(parts)


def _esc(text: str) -> str:
    return _html.escape(text)
