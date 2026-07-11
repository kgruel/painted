# Doc-IR — a document intermediate representation

**Status**: validated (2026-06-05); **amended 2026-07-11 for 0.10** (roadmap
Milestone 2 — ratified by Kyle 2026-07-11, **built same day** on
`semantic-tree-0.10`). The node vocabulary lives in
`core/doc.py` (a document compositor — see the boundary section) and has been
proven against *both* help and a real guide. The 0.10 amendment promotes what
the trifecta evidence earned — two worlds (painted's docs site, loops' inquiry
article) realize one `Doc` tree as sibling outputs, the second reaching the
publisher via an `importlib` path hack today: the publisher ships in the
packaged library (`painted.publish`), the Inline union settles with `Link` as
its first rich member, and the node vocabulary exports through the one-way
door. `Code(src)` docgen resolution and `to_markdown` remain deferred.

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
    src: str | None = None    # docgen snippet id, e.g. "py:painted.cell:Style#definition"
    lang: str = "python"      # projector resolves `src` via docgen (deferred seam)
    min_depth: int = 0        # (Code(ref=) is a deprecated alias for src, removed at 1.0)
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

### Inline — settled at 0.10, `Link` first

Help descriptions are plain strings; guide prose has `**bold**`, `` `code` ``,
`[links]`. The union was specified early but shipped `str`-only; the evidence
that settles it is the refs-as-plain-text friction in the article lens — a
`fact:01J…` ref authored into prose reaches both projectors as inert text.
The settled shape:

```python
Inline = str | tuple[str | Link, ...]

@dataclass(frozen=True)
class Link:
    text: str        # what the reader sees
    target: str      # a ref — "scheme:value", resolved via the declared RefScheme
```

- The plain-`str` arm stays: it is a single text span (help exercises only
  this arm, unchanged). Inside the tuple, `str` *is* the text span — the
  sketched `Text(str)` wrapper dissolved into `str` itself.
- **`Link` rides the existing denotation channel** (REFS_DESIGN), not a new
  one. `doc_lens` renders `Link.text` with `ref=target` stamped on its cells —
  the writer's OSC 8 emission and `render_html`'s `<a href>` wrapping already
  honor it. `to_html` resolves `target` through the same `resolve_ref` for its
  chrome anchors. One resolver seam, two projectors, identical inertness: an
  undeclared scheme renders `text` as plain content in *both* worlds — painted
  never invents URIs. (An absolute web URL is just a ref whose scheme the page
  declares; no special case until a consumer demonstrates the need.)
- `Emphasis` / `CodeSpan` remain unminted future members — added when a
  consumer demonstrates need, never speculatively. Adding a union member is
  additive; this is why `Link` alone can settle the door.

`Inline` positions: `Prose.content`, `Def.summary`/`detail`, `Items.entries`.
Both projectors walk spans through one shared helper (the `visible_body`
pattern applied to inline content) so the two sinks cannot render a span
differently.

## Projector contracts

```python
# core/doc.py — LIBRARY (the document compositor, peer of compose.py); exported as doc_lens
def doc_lens(doc: Doc, *, fidelity: Fidelity = Fidelity(), width: int | None = None) -> Block

# painted/publish.py — LIBRARY (the publisher namespace, root module beside display.py;
# 0.10 — previously tools/doc_publish.py, which dissolves)
def to_html(doc: Doc, *, fidelity: Fidelity | None = None) -> str        # SEMANTIC html
def published_fidelity(doc: Doc) -> Fidelity                             # full depth + every authored tag
def section_anchors(doc: Doc) -> dict[int, str]                          # anchor id per headed Section, by node identity (0.10.1)
def to_markdown(doc: Doc, *, fidelity: Fidelity = Fidelity()) -> str     # still deferred; joins publish.py if it lands
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
| **Publisher** | `tree → foreign semantics` | `to_html(doc)`, `to_markdown(doc)` | library (`publish.py`, 0.10 — was tools) |

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
world → publisher. **Home (amended 0.10):** the category boundary is the *codomain*,
and that is unchanged — a publisher is not core; it emits foreign semantics. What the
original filing conflated was "not core" with "not shipped": the taxonomy placed
publishers in `tools/` when the only consumer was painted's own site build. The
trifecta evidence broke that assumption — loops' inquiry article realizes the same
`Doc` tree and could reach `to_html` only via an `importlib` path hack against a repo
checkout. A second *world* consuming the publisher makes it library surface:
`painted/publish.py`, a root module beside `display.py` (the terminal-side entry and
the foreign-semantics side, siblings), part of the semver-stable set. `tools/
doc_publish.py` dissolves, its residue swept in the same change (`build_site`/
`outputgen`/`./dev panels` import `painted.publish`). Law 8's allowlisted exception is
untouched: the disclosure walk stays in `core/doc.py`; `publish.py` consumes it from
above, exactly as `doc_lens` does.

`core/html.py` is **not** a counterexample to the codomain rule: it's a *Block
sink*, peer to the ANSI writer — `Block → HTML` renders cells faithfully ("the browser
as another terminal"), it does not publish documents. The publisher `to_html` *calls*
it for `Figure` islands.

**Export (amended 0.10 — the one-way door opens):** the authoring seam that held the
vocabulary back (the Inline union) settles above, so the node vocabulary — `Doc`,
`Section`, `Prose`, `Def`, `Defs`, `Items`, `Code`, `Figure`, `Link` — and `doc_lens`
graduate into `painted.core.__all__` under the semver guard
(`tests/unit/test_public_api.py`); `to_html` + `published_fidelity` export via
`painted.publish`. The disclosure walk (`visible_body`/`capped`) stays *unexported*:
it is the mechanism that guarantees the sinks disclose identically, and painted's two
projectors are its only sanctioned readers — a second out-of-package publisher is the
evidence that would export it, not this amendment. `Code(ref=)`'s deprecated alias
keeps its 1.0 removal clock; exporting `Code` does not reset it.

**Section anchors (amended 0.10.1):** a headed `Section` is *addressable* —
`to_html` stamps `<section id="…">` so published pages can be deep-linked and
consumers can build outlines. The id derives from the **declared tree only**:
the heading text (lowercased, non-alphanumeric runs collapsed to hyphens — the
familiar heading-slug convention), deduplicated in document order by suffixing
`-2`, `-3`, …. Neither the hint (a tier-1 *reveal*, so disclosure-dependent)
nor fidelity participates — an anchor is identical at every fidelity its
section is visible at, and a hidden duplicate still reserves its number, so a
deep link survives the reader turning detail up or down. Unnamed sections
declare no identity and get no id (the honesty rule: an addressable surface
element exists only because a heading was declared). `section_anchors(doc)` is
the public half of the seam — a consumer's outline walk reads the SAME map
`to_html` stamps from, so the ids cannot drift between the page and a table of
contents built beside it. Evidence: the loops inquiry article regexed painted's
emitted HTML to inject exactly these ids (`_anchor_sections`), coupling itself
to the serialization's whitespace — the loops-adoption-spike finding this
amendment dissolves. A *declared* anchor (an explicit per-section override)
stays unbuilt: the derived id serves the one consumer, and the field would ride
the renderer-contract discussion (0.11) if a second world demands authored
identity.

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
6. ✅ **0.10** (this amendment, roadmap Milestone 2 — built 2026-07-11):
   `to_html` + `published_fidelity` moved into `painted/publish.py`
   (`tools/doc_publish.py` dissolved, residue swept); the Inline union settled
   with `Link` riding the ref channel through both projectors (`Span.ref`
   underneath, so a wrapped link keeps its denotation on every fragment); the
   node vocabulary + `doc_lens` graduated into `core.__all__` under the
   semver guard (`painted.publish` pinned by its own snapshot). Exit criteria
   (from the roadmap): the article publisher runs against *installed*
   painted — no repo checkout, no `PAINTED_REPO`; both realizations of one
   `Doc` disclose identically (the shared `visible_body` walk, pinned in
   `TestDisclosureParity` + the link-parity test).
7. *Later/maybe*: `Emphasis`/`CodeSpan` Inline members (evidence-gated),
   `Code(src)` docgen resolution, `to_markdown`, whether prose guides migrate
   off hand-markdown at all, promoting `/docs/primitives` into the site's
   "guides" lane.
