# Doc-IR — a document intermediate representation

**Status**: validated (2026-06-05). The node vocabulary lives in `core/doc.py`
(a document compositor — see the boundary section) and has been proven against
*both* help and a real guide. Node types stay out of `painted.core.__all__` until
the remaining authoring seams (Inline union, `Code(ref)` resolution) settle.

## Thesis

painted already dogfoods itself for *specimens* — every panel on the site is real
`render_html` output. It does **not** dogfood itself for *document chrome* (headings,
prose, definition lists): that goes through separate machinery (`docgen` markdown
assembly, the Astro page). The doc-IR closes that gap.

A document is a **node tree**. Three things read it — a *lens* `to_block` (terminal +
help) and two *publishers* `to_html` / `to_markdown` (see the taxonomy below; they are
**not** peers). What unites them: each reads the tree *directly*. Rendering chrome to a
`Block` and then `Block → HTML` would flatten an `<h1>` into a bold `<span>` and a
paragraph into fixed-width cell-rows. That's the OCR trap. The tree holds the
structure; no consumer recovers it from a `Block`.

This is not a new sink — it formalizes what `web/` already is: a semantic page with
real-render panel **islands**. And `cli/help.py`'s `render_help` is the existence
proof of the terminal projector — it's a hand-rolled doc renderer hardcoded to one
genre (the help screen).

## Three orthogonal axes

```
doc node tree   ×   Fidelity   ×   projector
(what)              (how much)      (what medium)
```

- **node tree** — the content/structure (this document).
- **Fidelity** (`core/fidelity.py`, already shipped) — `depth` (0–3 progressive
  tiers), `visible` (consumer-defined semantic-layer tags, via `shows(tag)`),
  `chars`/`lines` (prose density budgets). The doc-IR *consumes* this; it invents no
  disclosure primitive of its own.
- **projector** — `to_block` / `to_html` / `to_markdown`. Distinct from Format
  (ANSI/PLAIN/JSON) and Mode (static/live/interactive), which compose underneath
  `to_block`.

### Disclosure tier (shared by every projector)

Disclosure is not binary — it is a **per-node tier** keyed on the *effective depth*:

```
eff = depth - node.min_depth        # hidden when eff < 0, or node.tag is off
                                     # (tag checked against fidelity.visible)
```

`min_depth` is the `-v`/`-vv` ladder; `tag` is a cross-cutting semantic layer,
opt-in via the page's declared flag (`--rationale`, `--example`, `--aside` —
the docs CLI enumerates each page's node tags into `Tag` declarations; the
generic `--show <name>` spelling retired with FIDELITY_DESIGN.md §7d). `eff`
is **relative**:
a `Section` consumes its `min_depth` and passes the remaining budget (its own `eff`)
down to its body as the local depth. So a flag list nested under a group heading is
one tier compacter than the same list at the top level, *without re-authoring
`min_depth` on every child* — this cascade is what lets help's framework groups
collapse to a terse line at the default view while the command's own args stay
expanded on the same screen. (Help's old `eff = zoom - min_zoom`, computed per flat
group, was the special case; the cascade generalizes it to a nested tree.)

`eff` drives **density, not re-authoring**: a `Defs` shows terms-only at `eff == 0`,
term+summary columns at `eff >= 1`, and adds `Def.detail` at `eff >= 2` — the same
content, never written twice. Prose, items, code, figures, and `Section` headings are
binary (shown whenever `eff >= 0`); only list density and the `Section.hint` subhead
are tiered. **The original "reveals or hides whole nodes, never rewrites" axiom was
too strong** — the help existence-proof showed a group genuinely renders *denser* as
depth climbs. The invariant that survives: disclosure never re-*authors* content (no
paragraph written twice); it may reveal, hide, or compress a node.

## Node vocabulary

Frozen dataclasses (project invariant). Derived from two exemplars: `cli/help.py`
(thin) and `docs/guides/01-primitives-and-blocks.md` (rich). The repeated
`min_depth` / `tag` pair *is* the Fidelity disclosure contract applied uniformly — it
is the spine, not boilerplate.

```python
@dataclass(frozen=True)
class Doc:
    title: str | None
    body: tuple[Node, ...]

@dataclass(frozen=True)
class Section:                 # nests; heading level = tree depth, not stored
    heading: str | None       # help groups can be unnamed ("")
    body: tuple[Node, ...]
    hint: str | None = None   # help's "(what to show)" subhead
    min_depth: int = 0
    tag: str | None = None

@dataclass(frozen=True)
class Prose:
    content: Inline           # plain `str` accepted as sugar (see Inline, deferred)
    min_depth: int = 0
    tag: str | None = None

@dataclass(frozen=True)
class Def:                     # subsumes HelpFlag — term intact, no lossy downcast
    term: str                 # "-v, --verbose"
    summary: Inline
    detail: Inline | None = None    # revealed at depth >= DETAILED

@dataclass(frozen=True)
class Defs:
    items: tuple[Def, ...]
    min_depth: int = 0
    tag: str | None = None

@dataclass(frozen=True)
class Items:                   # flat bullet/number list (Defs is term+desc)
    entries: tuple[Inline, ...]
    ordered: bool = False
    min_depth: int = 0
    tag: str | None = None

@dataclass(frozen=True)
class Code:
    text: str | None = None
    ref: str | None = None    # docgen snippet id, e.g. "py:painted.cell:Style#definition"
    lang: str = "python"      # projector resolves `ref` via docgen (deferred seam)
    min_depth: int = 0
    tag: str | None = None

@dataclass(frozen=True)
class Figure:                 # embed a live-rendered Block — this is what makes doc == demo
    block: Block             # (renamed from "Specimen": that name is taken in tools/)
    caption: str | None = None
    min_depth: int = 0
    tag: str | None = None

Node = Section | Prose | Defs | Items | Code | Figure
```

`Rule` (horizontal rule) is intentionally omitted — it dissolves into `Section`
boundaries.

### Inline (deferred)

Help descriptions are plain strings; guide prose has `**bold**`, `` `code` ``,
`[links]`. To keep the contract guide-complete without over-building, `Inline` is
specified now but the first implementation accepts only plain `str`:

```python
Inline = str | tuple[InlineSpan, ...]
# InlineSpan = Text(str) | Emphasis(Inline, kind) | CodeSpan(str) | Link(Inline, target)
```

Help exercises only the `str` arm. The union lands when guides come into scope.

## Projector contracts

```python
# core/doc.py — LIBRARY (the document compositor, peer of compose.py); exported as doc_lens
def doc_lens(doc: Doc, *, fidelity: Fidelity = Fidelity(), width: int | None = None) -> Block

# tools/doc_publish.py — SITE GENERATION (not in the wheel; consumes the same tree)
def to_html(doc: Doc, *, fidelity: Fidelity | None = None) -> str       # SEMANTIC html
def to_markdown(doc: Doc, *, fidelity: Fidelity = Fidelity()) -> str    # deferred
```

All pure functions of `(tree, fidelity)` (render-is-a-pure-function invariant).
Disclosure is single-sourced: both projectors iterate bodies through
`visible_body` / `capped` (`core/doc.py`), so two sinks cannot disclose
differently. `to_html`'s fidelity defaults to `published_fidelity(doc)` — full
depth plus every tag authored in the tree — because the fidelity dials are a
terminal affordance; a published page is the full document.

- **`to_block`** — the `doc_lens`. Honors `width` exactly (width contract). Uses
  `fidelity.chars`/`lines` for budgets, `depth` + `visible` for disclosure.
- **`to_html`** — *semantic*: `Section → <section>` + `<h1..h6>` (level from tree
  depth), `Prose → <p>`, `Defs → <dl><dt><dd>`, `Items → <ul>/<ol>`,
  `Code → <pre><code>`, and **`Figure → <figure>` delegating to the existing
  `Block → HTML` (`core/html.py`)** for a terminal-faithful island. Chrome is never
  routed through `Block → HTML`.
- **`to_markdown`** — sketched, not built. If it ever lands it reads the same tree;
  it is never `Block → markdown`.

### Library boundary — three categories, discriminated by codomain

`to_block` and `to_html` are **not** peers. The discriminator is *whether the output
is a `Block`*:

| category | maps | examples | home |
|---|---|---|---|
| **Block sink** (Format) | `Block → substrate` | ANSI writer, `core/html.py` | library |
| **Compositor** | `tree → Block` | `compose`, **`doc_lens`** (`core/doc.py`) | library (core) |
| **Lens** | `data → Block` | `shape_lens`, `tree_lens` | library (views) |
| **Publisher** | `tree → foreign semantics` | `to_html(doc)`, `to_markdown(doc)` | tools |

`to_block`/`doc_lens` lands in the renderer's own type (`Block`). **It was first filed
as a "lens" beside `shape_lens`/`tree_lens` — but those interpret *arbitrary domain
data* (dicts, lists, unknown trees), while `doc_lens` interprets a *fixed vocabulary
painted defines* (`Doc`/`Section`/`Def`/…).** That makes it a *document compositor* —
a peer of `compose.py` (which lays out raw Blocks) — and it lives in `core`, not
`views`. The forcing function was the dissolution: help (`cli/`) must consume it, and
the gated `cli ↛ views` peer boundary forbids importing a views lens; `core` is below
both. `doc.py` imports only `core` and nothing under `views` imported it, so the move
was edge-free and the "it's a lens" identity was conceptual, not structural.

`to_html` emits web semantics the renderer has no type for → it leaves the renderer's
world → publisher → tooling (beside `build_site`/`outputgen`).

`core/html.py` is **not** a counterexample to "HTML-gen is tooling": it's a *Block
sink*, peer to the ANSI writer — `Block → HTML` renders cells faithfully ("the browser
as another terminal"), it does not publish documents. The publisher `to_html` *calls*
it for `Figure` islands. Tools depends on library, never the reverse. The node types
stay out of `views.__all__` until validated.

## How help dissolves (the proof of (a))

`build_help_data(runner) -> HelpData` becomes `help_doc(runner) -> Doc`:

| `cli/help.py` today | doc-IR |
|---|---|
| `HelpData(prog, description, groups)` | `Doc(title=prog, body=[Prose(description), *sections])` |
| `HelpGroup(name, hint, detail, flags, min_zoom)` | `Section(heading=name, hint=hint, min_depth=min_zoom, body=[Prose(detail, min_depth=DETAILED), Defs(...)])` |
| `HelpFlag(short, long, description, detail)` | `Def(term="-v, --verbose", summary=description, detail=detail)` |
| `help_args_to_flags` (drops `short`, jams `default` into a string) | **deleted** — adapter emits `Def`s with the term intact |
| `_extract_add_args_flags` (argparse introspection) | adapter → `Def`s |
| `render_help(data, zoom, width, use_ansi)` | `to_block(help_doc(runner), fidelity=…, width=…)`; the `use_ansi` bool was a degenerate plain projection — now a Format concern, off the signature |

Net deletion: `HelpData`, `HelpGroup`, `HelpFlag`, `HelpArg`, and the
`help_args_to_flags` lossy bridge all collapse. `help.py` becomes a thin
config → `Doc` adapter plus the argparse → `Defs` introspection. The three pieces of
help debt — the lossy `HelpFlag`/`HelpArg` bridge, the `min_zoom` single-int shadow of
three-axis `Fidelity`, and the `use_ansi` bool jammed into the render signature — all
dissolve into primitives that already ship.

## Build sequence

1. ✅ Node vocabulary + `to_block` + the shared disclosure predicate (`core/doc.py`).
2. ✅ `painted docs` consumer (terminal front door) — proved `doc == demo` on a real guide.
3. ✅ Disclosure grows binary → tier (`eff = depth - min_depth`, cascading); absorbs
   help's compact/expanded/detail keyings into one predicate.
4. ✅ Rewrite `cli/help.py` (and `app_runner.py`) onto it. `HelpData`/`HelpGroup`/
   `HelpFlag`/`help_args_to_flags`/`build_help_data`/`render_help` deleted; tests pin
   the new output. The dissolution forced the `views → core` reclassification above.
5. ✅ `to_html` in `tools/doc_publish.py`; `web/src/pages/docs/primitives.astro`
   consumes the committed fragment (emitted by `./dev panels`, drift-gated by
   `outputgen --check`) — the semantic sink, proven. Authored pages moved to
   `painted/_doc_pages.py` (neutral module: the CLI front door and the publisher
   are two consumers of one registry).
6. *Later/maybe*: Inline union, `Code(ref)` docgen resolution, `to_markdown`,
   whether prose guides migrate off hand-markdown at all, graduating the node
   vocabulary into `core.__all__` (rides whichever branch settles Inline —
   export is a one-way door), promoting `/docs/primitives` into the site's
   "guides" lane.
