# The renderer contract — one boundary, every delivery

**Status: DRAFT 2026-07-12, proposed** — the 0.11 milestone (M4), the first
design produced through the full trace → design pipeline
(`practice/work-pipeline-kinds`). Five sub-decisions were ratified in
deliberation 2026-07-11/12 (store: `design/rendering/renderer-contract`,
five refinements); this document is the contract of record for them,
pending ratification. Evidence base: the loops adoption spike
(`trace/loops-adoption-spike`, concluded 2026-07-11 — two rounds against
a real consumer, 9 loops-side audit facts, one round-trip migration).

Subordinate to `docs/RENDER_MODEL.md` (RATIFIED 2026-07-10), the design of
record for the render model: this document realizes the model's §3
renderer-input set at the framework seam and adds nothing to it. The
capability-vocabulary work (0.12, M5) will grow inside this document —
capabilities are a renderer input, not a subsystem (§9). Companion to
`docs/FIDELITY_DESIGN.md` (what compiles into the second parameter) and
`docs/REFS_DESIGN.md` (whose declaration surface §7 extends).

## 1. The thesis — one renderer, one boundary

The render model's promise is one semantic renderer reused unchanged across
progressively capable hosts. Until now that promise had no *spelled*
boundary on the framework tier: `run_cli` hands renderers a full
`CliContext`, and every real consumer immediately re-derives from it the
three things it actually wanted — the data, the compiled Fidelity, and a
width. The spike measured what that costs (§2). This document closes the
gap: the canonical renderer is

```python
def renderer(data, fidelity: Fidelity, width: int | None) -> Block: ...
```

- **`data`** — domain state, whatever `fetch` produced. painted never
  interprets it.
- **`fidelity`** — the compiled disclosure spec, intact. Never decomposed
  into loose kwargs by the framework; a renderer that only wants the depth
  axis reads `fidelity.depth` and ignores the rest.
- **`width`** — the **offered allocation** (RENDER_MODEL §5): the columns
  the host actually gives the renderer, `None` when the destination has no
  real geometry to offer. Exact when offered, per the width contract;
  natural sizing when `None`.
- **returns a content `Block`** — never writes, never exits, never
  consults delivery.

What the renderer **never sees**: mode, TTY-ness, streams, argv, handlers,
lifecycle. Those are host-selection axes (RENDER_MODEL §3); a renderer that
consults them is coupling to a rung instead of traveling the ladder. The
remaining renderer inputs from the model's inventory — render capabilities
and ambient presentation policy — arrive ambiently, not positionally: the
signature is closed at three (§9).

## 2. Evidence — why exactly these three

The spike ran the proposed signature against loops, painted's first real
consumer (25+ lenses, two deliveries, one document pipeline). Findings, by
input:

**The teardown adapter (for `fidelity`).** loops' dispatch builds a proper
`Fidelity` via `parse_fidelity`, then immediately decomposes it — zoom,
visible, chars, lines spread as kwargs, with per-lens signature inspection
to decide which each lens accepts — because the lenses predate `Fidelity`.
The strongest single lens (`fold_view`) *recomposes* the object as its
first act. The whole build-up-then-tear-down round trip is adapter shim
that passing `fidelity` intact dissolves
(`rendering/call-lens-fidelity-teardown-adapter`, loops store). All 25+
lenses fall into three signature tiers the compiled object subsumes
(`rendering/lens-signature-tiers`).

**The fabricated TTY fact (for `width: int | None`).** `piped`, computed
as not-TTY and threaded through ~11 loops lenses, is fully redundant with
width's `None` sentinel — the same TTY bit encoded twice at every call
site; every consumer branch reduces to `width is None`
(`rendering/piped-is-fabricated-tty-fact`, recurrence count 4). The
recurring `run_cli` closure glue is exactly
`w = ctx.width if ctx.is_tty else None; lens(..., piped=not ctx.is_tty)` —
a consumer re-reading state painted resolved one frame earlier
(`rendering/run-cli-adapter-inventory`).

**Height stays out.** The static path never *offers* height (it merely
knows it); only the Surface tier offers it, via `layout(width, height)`.
Nowhere in loops' document path is height offered, known, or needed — the
terminal scrolls, HTML has no height
(`rendering/height-offered-only-in-tui`). A height-free static signature
matches real usage exactly; offered height joins at the 0.13 host rung
under the dual allocation contract (RENDER_MODEL §2).

**Domain identity stays out.** `vertex_name`/`vertex_path` and their kin
are app-side state, bound via closure over `data` — the signature does not
widen for them (`rendering/fold-view-maximal-signature`).

**The delete test.** The 0.10.1 seams (width-`None` natural sizing,
section anchors) deleted consumer workarounds rather than relocating them —
the round-2 migration removed loops' `_anchor_sections` regex and
`_spans_block` dodge outright, byte-identical output. The recorded hazard:
the old regex had *silently* stopped matching on upgrade — output-coupled
consumer glue fails silent; owned seams fail loud. That asymmetry is this
document's recurring argument for explicit seams over inspection and
post-processing.

## 3. The seam — `renderer=` beside `render=`

The new contract arrives as a **new parameter**, not a reinterpretation of
the old one:

```python
run_cli(args, fetch=fetch, renderer=my_renderer)   # the contract (§1)
run_cli(args, legacy_render, fetch)                # legacy, deprecation window
run_cli(args, fetch=fetch)                         # neither → transcription (§4)
```

- **`renderer=`** is keyword-only and takes the `(data, fidelity, width)`
  callable. The name is the RENDER_MODEL glossary's exact term for the
  app-authored unit; `view` and `lens` are library-projection vocabulary
  and were rejected (`lens=` additionally belongs to `paint()` and would
  front-run the model's §7 lens lane).
- **`render=`** keeps the legacy `(ctx, data)` shape unchanged through a
  deprecation window. It moves from required-positional to
  optional-positional (`render=None`), so existing positional call sites —
  `run_cli(args, render, fetch)` — keep working verbatim. Passing a legacy
  renderer emits `DeprecationWarning`; `render=` joins `show()` and the
  0.7 id→ref aliases on the 0.17 pre-declared removal list
  (`roadmap/api-freeze`).
- **Passing both raises `DeclarationError`** at parser construction, the
  established collision behavior (Tag collisions, prompt-flag collisions).
- **No signature inspection.** run_cli never guesses which contract a
  callable implements from its arity — inspection fails silent on
  partials, closures, and `*args`, the exact silent-on-upgrade failure
  mode the spike recorded as a hazard (§2). The parameter name is the
  cheapest explicit marker there is. Passing the wrong shape to either
  parameter fails loud with an arity `TypeError` at first invocation.

The mnemonic is verb vs noun: `render=` was "call me back to do the
rendering, here's the context"; `renderer=` is "here is the semantic
renderer, host it." One naming consequence is recorded rather than acted
on: the glossary classifies `InPlaceRenderer` as a *host*, so its
`-Renderer` suffix is pre-model residue that this parameter sharpens.
Rename (candidate `InPlaceHost`, alias-then-remove) is on the 0.17 removal
list; the name is decided at rename time, likely with the 0.16 docs
edition.

Typing: the contract is a callable shape, published as a type alias
(`Renderer`) beside `run_cli` for annotation. There is **no public
`RenderContext`** — the model's §6 concept filter admits a public type only
when it removes repeated adaptation in more than one real consumer, and
the spike's evidence points the other way: the adapters *dissolve* under
the three-parameter contract; there is nothing left for a context object
to carry.

## 4. The default — transcription is a renderer

With neither `render=` nor `renderer=`, run_cli renders by
**transcription** — the no-lens graduate, ratified 2026-07-07. The
mechanics matter: the default is **a default renderer, not a `paint()`
call**.

`paint()` performs its own context detection — ANSI from the destination
stream, width from ambient `shutil.get_terminal_size`. Routing the
framework's default through it would discard the compiled Fidelity and the
normalized width and re-derive both: a piped invocation would transcribe
at the *terminal's* width and `-v` would change nothing — painted
fabricating facts against itself, the `piped` disease wearing a different
coat.

Instead, the no-renderer case is `renderer=` defaulting to painted's
transcription function, invoked through the same three-parameter contract
as any app-authored renderer. "Optional renderer" dissolves: there is no
special no-render branch in dispatch — **there is always a renderer; the
default one is transcription.** One code path, and the honesty rule holds
for free: `-q`/`-v` and declared budgets visibly change transcription
output because they arrive through `fidelity` exactly as they would for
any renderer.

Consequences:

- `transcribe` (today `(subject, zoom, width)`, `views/lens/shape.py`)
  grows fidelity awareness — the budget facets must be honored, not just
  depth. `shape_lens` already took this step (`fidelity=` kwarg);
  whether `transcribe` grows the same kwarg or a thin contract-shaped
  wrapper adapts it is implementation detail.
- The transcription renderer stays **private**. A named public "reference
  renderer" is teachable, but the §6 concept filter applies: it earns a
  public name when a real consumer wants to compose with it — wrap it,
  delegate to it — not before. Default use requires no name.
- `paint()` is untouched, including its ambient-width posture
  (`thread/paint-width-destination` stays open on its own terms). The two
  entries are siblings: `paint` owns casual delivery with its own
  detection; `run_cli` owns harness delivery with compiled context. Neither
  routes through the other.

## 5. The offer — width normalization at the dispatch seam

`ctx.width` and the contract's `width` are different concepts that share a
word, and the glossary already separates them: **offered allocation** is
"the dimensions the host actually gave the renderer, *as distinct from
geometry it merely knows*." The model's §3 goes further: the width a
renderer receives under a pipe today is "a resolved *fallback*
(`COLUMNS`/`get_terminal_size`), not a destination-imposed measure." A
fallback is not an offer.

So normalization lives **at the offer, not at detection**:

- **`CliContext.width` stays `int`** — geometry the host knows. It serves
  legacy `render(ctx, data)` unchanged through the migration window and
  the runner's own furniture (error blocks). Stamping `None` in
  `detect_context` would conflate knowing with offering and change a
  frozen public field's type under every legacy consumer at once.
- **The offer is computed once at the dispatch seam** — a single private
  `_offered_width(ctx)` (or equivalent computed once in `_dispatch`),
  never re-derived per delivery path:

| Mode | Offer |
|------|-------|
| STATIC, stdout is a TTY | `ctx.width` — the geometry is real |
| STATIC, piped / file | `None` — natural width; a fallback is not an offer |
| LIVE (in-place or alt-screen) | `ctx.width` — a live viewport is real by construction |
| INTERACTIVE | host-managed — outside the static contract; height joins at the 0.13 host rung |

This is what "run_cli owns the invariant" cashes out to: no renderer ever
consults TTY state. The pipe case arrives as `width=None`, blocks render
natural (the 0.10.1 half of the invariant), and loops' `piped` parameter
and Spine-1 closure glue delete outright
(`thread/cli-context-piped-width-none`, resolved 2026-07-12).

Edges, decided without new machinery:

- **`COLUMNS` on a pipe is not an offer.** By the model's provenance rule
  width is environment-imposed capacity, never intent — env vars don't
  smuggle a width through a pipe. Real demand for fixed-width piped output
  would be a declared `--width` flag (user-imposed allocation, a separate
  future design), not `COLUMNS`.
- **`--live` forced onto a pipe** is degenerate today (cursor codes into a
  pipe) and stays out of scope: LIVE offers `ctx.width` unconditionally
  because the mode's contract *is* "there is a viewport"; forcing it
  somewhere viewportless is the user's explicit call, and the fallback
  width is the best available answer.

## 6. The contract across delivery paths

The same renderer, uninvoked differently:

- **STATIC** — `block = renderer(state, ctx.fidelity, _offered_width(ctx))`,
  delivered via `print_block`.
- **LIVE, in-place** — the same call per tick; `InPlaceRenderer` receives
  completed Blocks and owns the viewport (clip-with-evidence per
  LIVE_DELIVERY §10).
- **LIVE, alt-screen** — `StreamSurface` receives an internally adapted
  closure; the renderer itself stays pure and signature-identical. The
  adaptation is runner-internal plumbing, never consumer-visible.
- **INTERACTIVE** — handlers own the mode, as today. A handler may call
  the renderer directly; the framework does not. Offered *height* — the
  dual allocation contract's second half — is deliberately absent from
  this document and joins at the 0.13 host rung.
- **`--json`** — unchanged: the structured fork serializes domain data and
  never invokes the semantic renderer (the Format exception,
  RENDER_MODEL §3). The renderer contract does not touch it.

## 7. Refs — declaration over ambient timing

Refs resolve at **serialization** (`writer.py:209`), after the renderer
returns. The spike's round-1 finding: a renderer that scopes
`with use_refs(...)` around its own body has torn the declarations down
before the host serializes — loops' lens needed setter semantics plus a
comment explaining that declarations must outlive the render and survive
until delivery resolves the ref grid. A consumer forced to understand
delivery timing to use an ambient API correctly is structural friction,
not a documentation gap: the renderer cannot bracket a resolution point it
does not own.

`run_cli` owns the whole fetch → render → deliver cycle, so it is the one
place an ambient scope can bracket all of it. Ref schemes therefore join
the **declaration surface**:

```python
run_cli(args, fetch=fetch, renderer=view,
        refs=[FactScheme(...), TickScheme(...)])      # static schemes
run_cli(args, fetch=fetch, renderer=view,
        refs=lambda state: ref_schemes(state))        # schemes built from state
```

- **`refs=`** takes a sequence of `RefScheme` — the plural-of-element-type
  pattern beside `prompts=` — **or a callable of state**, evaluated per
  fetch. The callable form is evidence-demanded, not speculative: loops'
  declaration is `ref_schemes(state, base_uri=)` — the vertex path rides
  the fetched data, and LIVE refreshes state per tick. It is the same dual
  shape `render` has always had with respect to state.
- The framework installs the declared schemes (via `use_refs`) around
  render *and* serialization. The timing bug becomes unwritable.
- **`use_refs` survives unchanged** as the library seam. Direct users
  (`paint`, `print_block`) own their delivery timing, so context-manager
  scope already works for them. The declaration is sugar-plus-correctness
  for the framework tier, not a second mechanism.

Rejected alternatives: **riding the Block** — a scheme is a resolver,
delivery policy rather than content; composed Blocks carrying different
schemes have no principled winner, and the model classifies ref resolution
as serialization-time, not a renderer input. **Pure-ambient status quo** —
the mechanism is fine; the ownership is wrong for framework users, per the
timing evidence above.

## 8. Migration

The legacy shape keeps working through the window; migrating a renderer is
mechanical:

```python
# before — legacy (ctx, data)
def render(ctx: CliContext, state: State) -> Block:
    w = ctx.width if ctx.is_tty else None
    return my_view(state, int(ctx.zoom), w, piped=not ctx.is_tty)

# after — the contract
def renderer(state: State, fidelity: Fidelity, width: int | None) -> Block:
    return my_view(state, fidelity, width)
```

The mapping for renderers that consumed decomposed facets: `ctx.zoom` →
`fidelity.depth` (via the same clamp `ctx.zoom` applies today, if the enum
is wanted), `visible`/`chars`/`lines` kwargs → the corresponding
`Fidelity` fields, `piped` → `width is None`, TTY consultation → delete.

**Declaration grammar over shared parsing** — recorded as a position: the
spike found `cli/fidelity.py`'s claimed siftd mirror drifted on every axis
(depth flags, visible derivation, budgets). The drift is evidence *for*
per-consumer declaration grammars compiled by `parse_fidelity` and
*against* a shared flag-parsing function: the flag-to-facet vocabulary is
genuinely per-consumer; a shared function cannot absorb two consumers
without freezing both. painted's export is the compile seam
(`parse_fidelity`, the Tag/depth-alias/budgets grammar), never a canned
argv layout.

Consumer follow-ups this contract unblocks (loops' schedule, not this
milestone): delete dead `fidelity_from_args`, dissolve `piped` across ~11
lenses, collapse the Spine-1 closures — flipping the spike's exit
criteria 1–2 from evidenced to satisfied.

## 9. The capability slot — fenced for 0.12

The model's renderer-input inventory (§3, provisional r4) names a third
input beside fidelity and allocation: **render capabilities** — which
visual carriers the destination supports (color, glyph repertoire, link
delivery). The 0.12 milestone replaces semantic-renderer reads of the
`use_ansi` proxy with a narrow capability vocabulary, and that work grows
*inside this document* — capabilities are a renderer input, not a
subsystem.

What this document commits to now, so 0.12 composes instead of amending:

- **The signature stays closed at three positionals.** Capabilities arrive
  non-positionally — ambiently, or by a mechanism 0.12 decides — never as
  a fourth parameter. The spike found zero lenses consuming capability
  facts positionally; the two real consumers (`raymarch`, `starmap`) read
  ambient state.
- **The fences hold** (per `roadmap/capability-vocabulary`): the
  vocabulary covers only what the two existing consumers demand, and it
  must not swallow the two existing capability *mechanisms* — ambient
  `IconSet` glyph fallback and `ColorDepth` serialization downsampling.

## 10. Refusals and deferrals

- **No public `RenderContext`** — §3; the concept filter is not met and
  the evidence points at dissolution, not consolidation.
- **Transcription renderer stays private** — §4; a public name waits for a
  composing consumer.
- **No `--width` flag** — §5; deferred until real demand for fixed-width
  piped output appears.
- **No offered height** — §6; the dual allocation contract's second half
  is the 0.13 host rung's opening question, designed against the streaming
  consumer app.
- **`InPlaceRenderer` rename** — §3; recorded on the 0.17 removal list,
  name decided at rename time.
- **`render=` removal** — 0.17, alongside `show()` and the id→ref aliases;
  pre-declared here.
