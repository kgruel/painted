# Doc-IR — a document intermediate representation

**Status**: design draft (2026-06-03). Provisional — node types stay out of
`painted.views.__all__` until validated against *both* help and a real guide.

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

### Disclosure predicate (shared by every projector)

A node appears iff:

```
fidelity.depth >= node.min_depth
  AND (node.tag is None or fidelity.shows(node.tag))
```

`min_depth` = the coarse `-v`/`-vv` ladder (generalizes help's `eff = zoom - min_zoom`).
`tag` = a cross-cutting semantic layer, opt-in via `--show <name>` — `rationale`,
`example`, `aside`. Both default to "always show". **Disclosure never rewrites prose;
it reveals or hides whole nodes.** No paragraph is authored twice.

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
# views/lens/doc.py — LIBRARY (the terminal lens, peer to shape_lens/tree_lens)
def to_block(doc: Doc, *, fidelity: Fidelity = Fidelity(), width: int | None = None) -> Block

# tools/ — SITE GENERATION (not in the wheel; consumes the same tree)
def to_html(doc: Doc, *, fidelity: Fidelity = Fidelity()) -> str        # SEMANTIC html
def to_markdown(doc: Doc, *, fidelity: Fidelity = Fidelity()) -> str    # deferred
```

All pure functions of `(tree, fidelity)` (render-is-a-pure-function invariant).

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
| **Lens** | `tree → Block` | `shape_lens`, `tree_lens`, `to_block` | library |
| **Publisher** | `tree → foreign semantics` | `to_html(doc)`, `to_markdown(doc)` | tools |

`to_block` lands in the renderer's own type (`Block`) → it's a lens → library, with the
other lenses. `to_html` emits web semantics the renderer has no type for → it leaves the
renderer's world → publisher → tooling (beside `build_site`/`outputgen`).

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

1. Node vocabulary + `to_block` + the shared disclosure predicate (`views/lens/doc.py`).
2. Rewrite `cli/help.py` onto it (breaking; `painted.cli` is the evolving surface).
   Rewrite its tests to pin the *new* output.
3. `to_html` in `tools/`; point one `web/` page at it to prove the semantic sink.
4. *Later/maybe*: Inline union, `Code(ref)` docgen resolution, `to_markdown`,
   `painted docs` consumer, whether prose guides migrate off hand-markdown at all.
