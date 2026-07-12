# The renderer contract — one boundary, every delivery

**Status: DRAFT 2026-07-12, proposed** — the 0.11 milestone (M4), the first
design produced through the full trace → design pipeline
(`practice/work-pipeline-kinds`). Five sub-decisions were ratified in
deliberation 2026-07-11/12 (store: `design/rendering/renderer-contract`,
five refinements); this document is the contract of record for them,
pending ratification. Evidence base: the loops adoption spike
(`trace/loops-adoption-spike`, concluded 2026-07-11 — two rounds against
a real consumer, 9 loops-side audit facts, one round-trip migration).
Design review 2026-07-12 (codex gpt-5.6-sol, medium): HOLD with 10
findings, all triaged and amended in place — headline: the offer rule
collapsed to TTY-or-`None` once the runner's real LIVE-on-pipe behavior
was checked; the `run_cli` signature mechanics (`fetch=None` +
`DeclarationError` + `@overload`s) and the capability-fence honesty
clause (§9) ratified by Kyle in the same round. Review round 2, same
day: 2 P1 + 1 P2 plus a challenge to the signature itself
(`renderer(data, RenderRequest)`) — the challenge was argued down on the
concept filter, the accretion dynamic, and declared-acceptance grounds
(the reviewer conceded and moved HOLD → APPROVE; the rejection is
recorded in §3); the findings resolved as: callable `refs=` evaluation
after fetch / before render, faulting `ContractError` on the render path
(§7); `transcribe` helpers adopt `width: int | None` (§4); the Surface
frame loop owns one ref scope spanning render through flush (§7).
Review round 3, 2026-07-12 (multi-agent adversarial pass — six
dimensions, three-lens verification per finding, 27 confirmed): HOLD →
amended in place, Kyle's rulings. Headline: the declaration is spelled
**`ref_schemes=`** (the `refs=` spelling collided with `Block(refs=)` —
§7); all render-path declaration validation moves to **runner
construction** (the empty-argv fast path never builds a parser — §3);
`tags=` without a renderer faults at construction (transcription cannot
consume `visible` — §4); the offer is computed **per offer** — live
hosts re-offer current geometry each frame (§§5–6); round 2's
`ContractError` ruling splits in two (§7: a raising callable propagates
unwrapped down the render-error path; an invalid result faults
`ContractError` *before* `use_refs`); the `render=` `DeprecationWarning`
is deferred to 0.12 (§3); `Renderer` lands in `painted.core` (§3);
`shape_lens` widens with the shared core (§4); tests-and-gates and
compatibility close-outs join the document (§§11–12); and a
citation-precision pass realigned every RENDER_MODEL pointer with the
ratified text.

Subordinate to `docs/RENDER_MODEL.md` (RATIFIED 2026-07-10), the design of
record for the render model: this document realizes the model's §2
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
- **`width`** — the **offered allocation** (RENDER_MODEL §2): the columns
  the host actually gives the renderer, `None` when the destination has no
  real geometry to offer. Exact when offered, per the width contract;
  natural sizing when `None`.
- **returns a content `Block`** — never writes, never exits, never
  consults delivery.

What the renderer **never sees**: mode, TTY-ness, streams, argv, handlers,
lifecycle. Those are host-selection material, never renderer inputs —
law 7 bars a semantic renderer from consuming lifecycle or mode, and the
§2 provenance rule keeps TTY-ness outside fidelity; a renderer that
consults them is coupling to a rung instead of traveling the ladder. The
remaining renderer inputs from the model's inventory — render capabilities
and ambient presentation policy — arrive ambiently, not positionally: the
signature is closed at three (§9's fence, scoped to those non-positional
inputs; offered *height*'s separate arrival constraints are recorded in
§10).

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
`_spans_block` dodge outright, byte-identical output. Provenance, for
remote auditors: the `_spans_block` deletion is commit-pinned on loops
main (`afe82c5`, "the width contract dissolves two lens workarounds",
goldens byte-stable); the `_anchor_sections` deletion lives in loops'
untracked `.loops/` workspace, recorded in the loops store observation
of 2026-07-11. The recorded hazard:
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
  and were rejected (`lens=` additionally belongs to `paint()`'s closed
  kwarg surface, PAINT_DESIGN, and would front-run the roadmap's
  unshipped lens-selection lane).
- **`render=`** keeps the legacy `(ctx, data)` shape unchanged through a
  deprecation window. It moves from required-positional to
  optional-positional (`render=None`), so existing positional call sites —
  `run_cli(args, render, fetch)` — keep working verbatim. In 0.11
  `render=` is documented as legacy but emits **no runtime warning**: §9
  holds the capability consumers (`raymarch`, `starmap`) on `render=`
  until 0.12 ships the vocabulary, and a deprecation that scolds the
  sanctioned path weakens the warning channel. The `DeprecationWarning`
  gate opens at 0.12, when the last blocked consumer class has a
  migration path; `render=` joins the pre-declared 1.0 removals
  (`show()`, the 0.7 id→ref aliases), executed in the 0.17 → 1.0.0rc
  freeze window and landing as of 1.0 (the removal-train mechanics and
  the precise semver framing are recorded in §10).
- **Signature mechanics.** An optional positional cannot precede a
  required one, so making `render` optional forces `fetch` to
  `fetch=None` *at the signature*, with the requiredness moved to
  construction time: a missing `fetch` raises `DeclarationError`, the
  established boundary for declaration faults. Published `@overload`s
  carry the truth for type checkers — one overload per call form
  (legacy positional `render`; keyword `renderer=`; neither), each with
  `fetch` required — so no caller sees `fetch` as optional in their
  IDE even though the runtime signature says `None`.
- **Runner construction is the validation seam** —
  `CliRunner.__post_init__`, the seam the `live_delivery` check already
  uses — not parser construction: the runner's empty-argv fast path
  never builds a parser, and the existing parser-time collision checks
  (Tag, prompt-flag) are safe only because those declarations mint
  grammar and force the parser into existence. `renderer=`, `render=`,
  and `ref_schemes=` mint no flags, so a parser-time check would
  provably never fire on bare `tool` — the most common invocation.
  Construction-time faults, all `DeclarationError`: missing `fetch`;
  **both `render=` and `renderer=`**; `tags=` with neither (§4); an
  invalid static `ref_schemes=` sequence (§7). The static sequence is
  defensively copied at construction, so later caller mutation cannot
  bypass validation.
- **No signature inspection for contract selection.** run_cli never
  guesses which *contract* a callable implements from its arity —
  inspection fails silent on partials, closures, and `*args`, the exact
  silent-on-upgrade failure mode the spike recorded as a hazard (§2).
  The parameter name is the cheapest explicit marker there is. Passing
  the wrong shape to either parameter fails loud with an arity
  `TypeError` at first invocation. One pre-existing exception is
  recorded rather than silently grandfathered: the fetch arity shim
  (`_wants_ctx`) inspects a single declared parameter to choose between
  `fetch()` and `fetch(ctx)` — a calling convenience on one declared
  callable, never a choice between contracts; its conservative nullary
  fallback stays within that scope.

The mnemonic is verb vs noun: `render=` was "call me back to do the
rendering, here's the context"; `renderer=` is "here is the semantic
renderer, host it." One naming consequence is recorded rather than acted
on: the glossary classifies `InPlaceRenderer` as a *host*, so its
`-Renderer` suffix is pre-model residue that this parameter sharpens.
Rename (candidate `InPlaceHost`, alias-then-remove) is on the 0.17 removal
list; the name is decided at rename time, likely with the 0.16 docs
edition.

Typing: the contract is a callable shape, published as a type alias
(`Renderer`) in **`painted.core`** — shared rendering vocabulary beside
the `Fidelity` spec it references, following the established split (the
spec in core, the grammar that compiles into it in cli) — re-exported by
`painted.cli` for convenience. Core placement is deliberate: the 0.13
host rung runs the same renderer through `Surface`, and `tui` imports
nothing from `cli`; landing the model's central unit on the one surface
that path cannot reach would force a tui→cli import, a duplicate name,
or a relocation one milestone after minting. The alias joins
`core.__all__` under the `test_public_api` guard — a semver-stable
commitment, which is what the contract of record deserves. There is
**no public `RenderContext`** — the model's §6 concept filter asks
whether a type *eliminates host-specific adaptation for consumers, or
merely packages several arguments under another name*, and the spike's
evidence answers: the adapters *dissolve* under the three-parameter
contract; there is nothing left for a context object to carry.

**Rejected: `renderer(data, RenderRequest)`** — recorded with its
strongest case, because it is the alternative every future reader will
reach for. A narrow frozen request object (`fidelity` + `allocation` +
`capabilities`) would give future renderer inputs an additive home, spare
the contract a signature transition when height or capabilities arrive,
and make renderer inputs explicit to construct in tests. It is rejected
on three grounds. *The concept filter*: the spike found no
request-object adaptation a public type would eliminate — existing
adapters dissolve into the three explicit inputs; admitting the type now
would be speculative packaging, exactly what the filter screens out.
(The model *deferred* the RenderContext question to adoption evidence;
that evidence is now in, and it answers no.) *The accretion
dynamic*: a carrier object at a boundary is where renderer inputs widen
through silently ignorable field additions — `CliContext` is this
document's own cautionary tale. At this boundary, new inputs require
visible amendment, and offered dimensions require **declared
acceptance** — the model's offered≠known proviso, written specifically
about context objects: presence in a context object is not allocation
ownership, and the contract must make "height omitted" deliberate
(RENDER_MODEL §2; law 6's ownership rule puts the evidence debt on the
knowing decider). A renderer that silently ignores
`request.allocation.height` while the host believes it accepted H is
exactly that proviso violated, so the request object's extensibility is
specifically the dishonest kind. *The lifecycle misdiagnosis*: the
ambient-state risk cited against capabilities belongs to refs
(serialization-time, crossing a boundary the renderer cannot bracket —
§7), not to render-time ambient inputs, which are the shipped,
law-1-pinned pattern (palette, icons, borders, vocabularies). If
adoption evidence later meets the concept filter — host-specific
adaptation that only a public type would eliminate — a request type may
be admitted through the normal deprecation process; the option is gated,
not foreclosed.

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
for the facets transcription consumes: `-q`/`-v` and declared budgets
visibly change transcription output because they arrive through
`fidelity` exactly as they would for any renderer. It does **not** hold
for `tags=` — transcription cannot consume `fidelity.visible` (it has no
way to map app-domain facet names onto arbitrary data), and every
declared `Tag` mints a `--{name}` flag, so `tags=` under the default
renderer would be a dead public flag: the violation FIDELITY_DESIGN §1
declares structurally impossible, owned by painted's own renderer where
"testable per app" cannot reach. The fence follows the honesty rule's
own logic: **declaring `tags=` with neither `render=` nor `renderer=`
raises `DeclarationError` at runner construction** (§3) — the dead flag
is unconstructible. `depth_aliases` and `budgets=True` stay valid with
the default: transcription consumes depth and the budget facets.

Consequences:

- **A contract-shaped wrapper is mandatory — and it is not sufficient.**
  `transcribe` today is `(content, zoom, width, *, fidelity=None)` with
  an *integer* width compared numerically throughout its recursive
  helpers (`views/lens/shape.py`) — the compiled spec is already
  accepted whole through the `fidelity=` keyword (the machinery consumes
  `fidelity.chars`/`fidelity.lines` from it), but no wrapper can
  synthesize natural sizing around an implementation that requires a
  number. Two changes, with distinct owners: **the implementation
  change** — `transcribe` and its recursive helpers adopt
  `width: int | None`, propagating `None` as unconstrained natural
  sizing (not new contract: the 0.10.1 width-`None`-natural contract
  extended to one more implementation). `transcribe` and `shape_lens`
  are one-line wrappers over the same recursive core, so the widening
  reaches both: **`shape_lens`'s public signature widens to
  `width: int | None` in the same change** — the exploration entry
  adopting the library-wide width law, a compatible widening noted in
  the CHANGELOG. **The wrapper** — performs fidelity adaptation only:
  maps `fidelity.depth` to the zoom argument and passes the compiled
  spec through the existing `fidelity=` keyword *intact* — never
  decomposed into loose facet kwargs (§1's rule applies to painted's
  own default renderer first). Together they make the most basic
  promised call, `run_cli(args, fetch=fetch)` under a pipe, produce
  natural-width transcription rather than an error or a fabricated
  width.
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
geometry it merely knows*." The model's §2 goes further: the width a
renderer receives under a pipe today is "a resolved *fallback*
(`COLUMNS`/`get_terminal_size`), not a destination-imposed measure." A
fallback is not an offer.

So normalization lives **at the offer, not at detection**:

- **`CliContext.width` stays `int`** — geometry the host knows. It serves
  legacy `render(ctx, data)` unchanged through the migration window and
  the runner's own furniture (error blocks, the help path). The
  furniture exemption is deliberate and recorded: the offer rule governs
  what the host tells *renderers*; furniture is the host's own output,
  rendered at geometry it knows — no offer is involved. (At 1.0, when
  `render=` is removed, furniture becomes the field's only runner-side
  consumer; its `int`-ness rests on this exemption.) Stamping `None` in
  `detect_context` would conflate knowing with offering and change a
  frozen public field's type under every legacy consumer at once.
- **The offer is computed at the single host-to-renderer offer seam,
  each time an offer is made** — one private `_offered_width(...)`, the
  only place the rule lives, never re-implemented per delivery path.
  Static and non-streaming delivery offer once; live delivery offers per
  rendered frame, from current geometry (§6). The rule is **one line**:

  > stdout is a TTY → offer current geometry (`ctx.width` at one-shot
  > dispatch; the frame's width on live paths); otherwise → offer `None`.
  > (INTERACTIVE is host-managed — outside the static contract; height
  > joins at the 0.13 host rung.)

  The rule is mode-independent because the *delivery reality* is
  TTY-determined, not mode-determined. STATIC piped prints once, natural.
  And LIVE forced onto a pipe is **already** a no-viewport path in the
  runner: the non-ANSI live branch retains only the last Block and prints
  it once at the end — a cadence choice, not a width allocation. Offering
  the fallback width there would be exactly the "resolved fallback
  masquerading as an offer" the model warns against; it offers `None`
  like every other viewportless delivery. Only a real viewport — a TTY —
  offers geometry.

This is what "run_cli owns the invariant" cashes out to: no renderer ever
consults TTY state. The pipe case arrives as `width=None`, blocks render
natural (the 0.10.1 half of the invariant), and loops' `piped` parameter
and Spine-1 closure glue delete outright
(`thread/cli-context-piped-width-none`, resolved 2026-07-12).

One edge, decided without new machinery: **`COLUMNS` on a pipe is not an
offer.** Width's provenance today is environmental or caller-provided,
never user-declared (the model's provenance rule sorts declared intent
into Fidelity; its glossary allows caller-provided width) — so an env
var on a pipe is a resolved fallback, not an offer, and doesn't smuggle
one through. Real demand for fixed-width piped output would be a new,
user-declared allocation channel — a `--width` flag, a separate future
design — not `COLUMNS`.

## 6. The contract across delivery paths

The same renderer, uninvoked differently:

- **STATIC** — `block = renderer(state, ctx.fidelity, _offered_width(ctx))`,
  delivered via `print_block`.
- **LIVE, in-place** — the same call per tick, with the offer re-derived
  from current terminal geometry at each frame (the §5 seam applied per
  offer: `detect_context` runs once, the terminal resizes — the same
  argument as the alt screen below, and the delivery half already
  re-reads ambient rows per frame). `InPlaceRenderer` receives completed
  Blocks and owns the viewport (clip-with-evidence per
  LIVE_DELIVERY §10).
- **LIVE, alt-screen** — `StreamSurface` receives an internally adapted
  closure; the renderer itself stays pure and signature-identical. The
  adaptation is runner-internal plumbing, never consumer-visible — with
  one obligation the current code does not yet meet: the adapter offers
  the surface's **current buffer width at each frame**, not the
  once-captured `ctx.width`. `detect_context` runs once; the alt screen
  resizes. Passing stale width would let `Block.paint` clip silently —
  the model's resize rule is that a width change re-enters the renderer
  as changed input, so the offer must track the live geometry.
- **INTERACTIVE** — handlers own the mode, as today: they receive only
  `CliContext`, are dispatched before any fetch, and bypass the render
  path entirely. This document **does not deliver renderer reuse on the
  interactive rung** — an app that wants its renderer inside a Surface
  today still captures renderer and fetch itself. That is deliberate
  deferral, not oversight: "one reference renderer works through
  `print_block`, `InPlaceRenderer`, `StreamSurface`, *and interactive
  `Surface`*" is the 0.13 host rung's exit criterion
  (`roadmap/host-rung`), designed against the streaming consumer app.
  Offered *height* — the dual allocation contract's second half — is
  absent from this document for the same reason.
- **`--json`** — unchanged: the structured fork serializes domain data and
  never invokes the semantic renderer (the Format exception,
  RENDER_MODEL §2). The renderer contract does not touch it, and neither
  does the ref declaration: no schemes are evaluated or installed there
  (§7).

## 7. Ref schemes — declaration over ambient timing

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
        ref_schemes=[FactScheme(...), TickScheme(...)])  # static schemes
run_cli(args, fetch=fetch, renderer=view,
        ref_schemes=lambda state: schemes_for(state))    # schemes built from state
```

- **`ref_schemes=`** takes a sequence of `RefScheme` — the
  plural-of-element-type pattern beside `prompts=` (the elements are
  `RefScheme`s, so the parameter says so; loops' own builder is already
  named `ref_schemes(state, base_uri=)`) — **or a callable of state**,
  evaluated per fetch. The `refs=` spelling was rejected: **ref** is the
  ratified word for the per-cell annotation and a live public kwarg —
  `Block(refs=)` is the annotation grid — and REFS_DESIGN §3 D2 was
  ratified to sweep exactly this two-concepts-one-word collision; this
  document does not re-mint it. The callable form is evidence-demanded,
  not speculative: the vertex path rides the fetched data, and LIVE
  refreshes state per tick. It is the same dual shape `render` has
  always had with respect to state.
- The framework installs the declared schemes around render *and*
  serialization. The timing bug becomes unwritable.
- **Replace semantics, three cases.** Absent `ref_schemes=`, the
  framework installs nothing — ambient schemes an app set through
  `use_refs` flow through unchanged (the library seam keeps working
  under the framework). A declaration REPLACES the registry inside the
  runner-owned bracket, per `use_refs` semantics, with the prior ambient
  state restored at bracket exit. And `ref_schemes=[]` is a *valid,
  explicit empty declaration*: disable ambient ref resolution within the
  runner-owned cycle — ordinary replace semantics, making omission and
  explicit emptiness observably different.
- **Lifecycle, precisely** — because "around render and serialization" is
  a per-frame bracket, not a per-process one, and ContextVars do not flow
  backward between tasks: the framework evaluates the callable against
  each fetched state and installs the resulting schemes **in the task
  that renders and serializes**, bracketing that frame's render through
  its flush. `StreamSurface` fetches in a consumer task and renders in
  the Surface task; setting the ContextVar at fetch time would never
  reach the render task, so the schemes travel *with the state* to the
  rendering side and are installed there. And because render and flush
  are *separate callbacks* on the Surface, a `with use_refs(...)` inside
  the render callback closes too early — **the frame loop owns one scope
  per frame**, entered before render, exited after flush, with guaranteed
  release on success, exception, cancellation, resize, and quit. Each new
  state's schemes replace the previous frame's at its bracket; the final
  deposit (the scrollback frame a live run leaves behind) serializes
  under the last state's schemes. States that arrive faster than frames
  are coalesced exactly as the frames themselves are — schemes belong to
  the state that actually renders.
- **Evaluation timing and fault classification.** The static sequence
  form is validated at runner construction (§3) and faults as
  `DeclarationError` — the starts-clean-never-fires contract
  (ERRORS_DESIGN). The callable form *cannot* start clean: it is
  evaluated **after a successful fetch and before the renderer is
  invoked**, and that evaluation stage **belongs to the render phase**.
  Two distinct fault rules, because two different parties fault. If
  **the callable itself raises**, the application exception propagates
  *unwrapped*, classified through the render-error path — wrapping
  would misattribute an app fault as painted's (REFS_DESIGN's
  misattribution principle for the resolver seam, applied to its
  sibling). If the callable **returns an invalid collection** — a
  non-`RefScheme` element, duplicate names, any registry-shape
  violation — **the framework validates the result itself, before any
  `use_refs` call, and raises `ContractError`**: `use_refs`'s internal
  `DeclarationError` must never escape mid-cycle (an app that started
  clean would see the wrong class, violating ERRORS_DESIGN's contract).
  Both routes follow the render-error path: rendered error block, render
  exit code. Never the fetch path — an implementation that evaluates
  schemes inside `_do_fetch` and reports a fetch failure has
  misclassified an app-declaration fault as a data fault. This is the
  same rule that pulled `resolve(NaN)` and undeclared-vocabulary lookups
  to `ContractError`: faults that fire mid-cycle are contract-time, not
  declaration-time.
- **Handler paths and the structured fork are excluded, explicitly.** A
  custom mode handler owns its lifecycle; the framework neither fetches
  nor renders there, so a callable `ref_schemes=` has no state boundary
  to evaluate against and is **not evaluated** on handler-dispatched
  modes — the handler owns its own `use_refs` scope, like any direct
  library user. Static scheme sequences, which need no state, are
  installed around the handler invocation. `--json` is excluded
  absolutely, static and callable alike: the structured fork serializes
  domain data, never Blocks — there is no render to evaluate before and
  no serialization that resolves refs, and a fault surfacing there would
  corrupt the machine-parseable stdout the JSON path guarantees (the
  Format exception, §6). The declaration covers the fetch → render →
  deliver cycle *where the framework owns it* — every path except the
  one a handler explicitly took over and the fork that never renders.
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
`fidelity.depth`, `visible`/`chars`/`lines` kwargs → the corresponding
`Fidelity` fields, `piped` → `width is None`, TTY consultation → delete.
And the row every consumer hits, first-class: **`ctx.width` (always
`int`) → `width: int | None`** — the renderer and its helpers adopt the
None-is-natural posture, exactly as `transcribe` does (§4): integer
arithmetic on width becomes conditional or natural-sizing-aware, because
the dominant legacy shape feeds `ctx.width` straight into int-only
helpers and would `TypeError` on the first piped invocation. The
behavioral delta is the contract's point, not a regression: migrated
renderers render piped output *natural* instead of at the fallback
width. "Mechanical" holds once that posture is adopted — the mapping is
still line-for-line; the `None` arm is the one new obligation.
One ownership rule rides the depth mapping: `Fidelity.depth` is an open
int (a `build_fidelity` hook can hand back any value), while `Zoom` is
bounded — so **the migrating consumer clamps** when feeding a
bounded-`Zoom` view, using the same two-sided clamp `ctx.zoom` applies
today (`Zoom(min(max(fidelity.depth, 0), 3))`). The framework passes
`fidelity` through untouched; no silent clamping happens at the boundary.

**Declaration grammar over shared parsing** — recorded as a position: the
spike found `cli/fidelity.py`'s claimed siftd mirror drifted on every axis
(depth flags, visible derivation, budgets). The drift is evidence *for*
per-consumer declaration grammars compiled by `parse_fidelity` and
*against* a shared flag-parsing function: the flag-to-facet vocabulary is
genuinely per-consumer; a shared function cannot absorb two consumers
without freezing both. painted's export is the compile seam
(`parse_fidelity`, the Tag/depth-alias/budgets grammar), never a canned
argv layout. The surviving half of the drifted pair is named
deliberately: siftd's `cli/_common.py:fidelity_from_args` still
hand-builds painted's `Fidelity` without `parse_fidelity`. siftd
consumes painted as a renderer library only — it sits outside the
`run_cli` seam and carries no migration obligation from this contract;
grammar adoption is on siftd's schedule, and until then its hand-rolled
parser retains the documented drift hazard by design, not by omission.

**The app tier, explicitly.** Neither `renderer=` nor `ref_schemes=`
gets an `AppCommand` mirror: the mirror pattern exists for flag-minting
declarations that must survive `run_app`'s interception (`-h`,
completion) — `tags`, `prompts`, `add_args` — and neither new parameter
surfaces anything on the parser's reflections. Multi-command apps adopt
the contract through each handler's own `run_cli` call, unchanged at the
`run_app` tier.

Consumer follow-ups this contract unblocks (loops' schedule, not this
milestone): delete dead `fidelity_from_args`, dissolve `piped` across ~11
lenses, collapse the Spine-1 closures — flipping the spike's exit
criteria 1–2 from evidenced to satisfied.

## 9. The capability slot — fenced for 0.12

The model's renderer-input inventory (§2, provisional r4) names a third
input beside fidelity and allocation: **render capabilities** — which
visual carriers the destination supports (color, glyph repertoire, link
delivery). The 0.12 milestone replaces semantic-renderer reads of the
`use_ansi` proxy with a narrow capability vocabulary, and that work grows
*inside this document* — capabilities are a renderer input, not a
subsystem.

What this document commits to now, so 0.12 composes instead of amending:

- **The signature stays closed at three positionals — a fence scoped to
  capabilities and ambient policy.** Capabilities arrive
  non-positionally — by a mechanism 0.12 decides; every existing
  presentation channel (palette, icons, borders, vocabularies) is
  ambient, so ambient is the natural landing — never as a fourth
  parameter. The spike found zero lenses consuming capability facts
  positionally. Offered *height* is not governed by this fence — a
  dimension is offered, never ambient; its arrival constraints are
  recorded with the deferral (§10).
- **The sequencing consequence, stated plainly:** the two real capability
  consumers (`raymarch`, `starmap`) read `ctx.use_ansi` — legacy-context
  state that today's ambient mechanisms cannot express (color carrier,
  link delivery). They therefore **cannot migrate to the three-parameter
  contract in 0.11 and stay on legacy `render=` until 0.12 ships the
  vocabulary** — which is why the `render=` `DeprecationWarning` gate
  opens at 0.12, not 0.11 (§3): the deprecation clock starts when the
  last blocked consumer class has a path. This is deliberate: migrating
  them through a closure over
  host context would re-create the adapter glue this contract exists to
  dissolve. If 0.12's design finds a non-positional mechanism
  insufficient, that is an **explicit amendment against this section** —
  not silent drift.
- **The fences hold** (per `roadmap/capability-vocabulary`): the
  vocabulary covers only what the two existing consumers demand, and it
  must not swallow the two existing capability *mechanisms* — ambient
  `IconSet` glyph fallback and `ColorDepth` serialization downsampling.

## 10. Refusals and deferrals

Each deferral carries three things — the §9 valve pattern applied as a
standard: the constraints already set, what remains genuinely open, and
what future outcome would require amendment.

- **No public `RenderContext`** — §3; the concept filter is not met and
  the evidence points at dissolution, not consolidation. Open: adoption
  evidence of host-specific adaptation only a public type would
  eliminate; admitting one then is the normal deprecation process, not
  an amendment.
- **Transcription renderer stays private** — §4; a public name waits for
  a composing consumer — one that wraps it or delegates to it.
- **No `--width` flag** — §5; deferred until real demand for fixed-width
  piped output appears. Already set: it would be a user-declared
  allocation channel, distinct in kind from `COLUMNS`.
- **No offered height** — §6; the dual allocation contract's second half
  is the 0.13 host rung's opening question, designed against the
  streaming consumer app. Constraints already set by this document and
  the model, recorded so 0.13 inherits them knowingly: height, when
  offered, must arrive through **declared acceptance** — never ambient
  (a dimension is offered, not ambient — RENDER_MODEL §2), never a
  silently ignorable carrier field (§3), never arity inspection (§3).
  Genuinely open: the *form* of the declaration — a separate renderer
  protocol, an explicit declaration at the `run_cli` surface, a wrapper,
  a host-level registration; this document deliberately does not pick.
  A height-accepting contract is the *anticipated* path, not an
  amendment against §9, whose fence is scoped to capabilities and
  ambient policy.
- **`InPlaceRenderer` rename** — §3; recorded on the 0.17 removal list,
  name decided at rename time.
- **`render=` removal** — pre-declared here; executed in the 0.17 → rc
  freeze window alongside `show()` and the id→ref aliases, landing as of
  1.0. The framing is precise: for `show()` the 1.0 landing is
  semver-required — `painted.display` is the stable tier. For `render=`
  — a parameter of `run_cli` on the evolving `painted.cli` surface — the
  window is **policy, not semver obligation**: consumers on `render=`
  keep the whole 0.x line as a courtesy the tier doesn't owe them.
  Whether `painted.cli` itself graduates to semver stability at 1.0 is
  an upstream `roadmap/api-freeze` question this document deliberately
  does not decide — it must be answered there before the 0.17 freeze,
  not invented here by implication.

## 11. Tests and gates

The contract's subtlest mechanisms are cross-task lifecycle invariants —
prose alone will not secure them. The 0.11 cut lands with:

- **Call forms and overloads** — every accepted `run_cli` form (legacy
  positional; keyword `render=`; keyword `renderer=`; neither)
  dispatches correctly, and the published `@overload`s type-check each
  form with `fetch` required — no form sees it as optional.
- **Construction validation** — missing `fetch`, `render=`+`renderer=`,
  `tags=` without a renderer, and an invalid static `ref_schemes=`
  sequence each raise `DeclarationError` at `CliRunner` construction —
  asserted **on empty argv** specifically, the fast path that skips the
  parser (§3).
- **Static-sequence freezing** — mutating the caller's list after
  construction cannot bypass validation.
- **The transcription default** — TTY (offered width) and pipe
  (`None` → natural) outputs pinned through the appearance tier; natural
  sizing exercised across the recursive shapes (nested dicts, lists,
  dataclasses); `-q`/`-v` and budgets visibly change default output —
  the honesty half that holds (§4).
- **The offer rule** — `_offered_width`: STATIC+TTY → `ctx.width`; any
  non-TTY → `None`; both live hosts re-offer current geometry per frame,
  and a mid-run width change re-enters the renderer as changed input.
- **Ref schemes** — static and callable forms; ambient preservation when
  undeclared; `ref_schemes=[]` disables ambient resolution within the
  cycle; the prior ambient state restored at bracket exit.
- **Fault classification** — a raising callable propagates the app
  exception unwrapped down the render-error path; an invalid result
  raises `ContractError`, with no `use_refs` `DeclarationError` escaping
  mid-cycle.
- **Delivery paths** — static, in-place live, alt-screen live (the final
  deposit serializes under the last state's schemes), handler-dispatched
  (static schemes installed, callable not evaluated), and `--json`
  (nothing evaluated or installed).
- **Scope hygiene** — the per-frame ref scope releases on success,
  renderer error, flush error, cancellation, and quit (`TestSurface`
  frame capture is the harness).
- **Deprecation timing** — 0.11 asserts `render=` emits *no* warning;
  the 0.12 warning lands with a correct `stacklevel` when the gate
  opens.
- **Public surface** — `Renderer` joins `core.__all__` under the
  `test_public_api` guard; `shape_lens`'s widened signature is covered
  by the width-contract property tests.

## 12. Compatibility and sequencing

**CHANGELOG posture.** `renderer=` and `ref_schemes=` are additive
(minor). The `transcribe`/`shape_lens` widening to `width: int | None`
is compatible — every existing `int` call is unchanged — and noted as
the 0.10.1 width law reaching the exploration entry. `render=` is
documented legacy at 0.11, warns at 0.12, and is removed at 1.0 (§10).

**Residue schedule, same cut** (the REFS_DESIGN D1 alias law: flip all
internal docs, demos, and tests in the change that lands the new word):

- Demos and tests migrate to `renderer=` — except `raymarch` and
  `starmap`, which stay on `render=` per §9 until 0.12 and are the
  documented reason the warning gate waits.
- The consumer guide (`src/painted/CLAUDE.md` Level 2) and the root
  CLAUDE.md `run_cli` flow teach the contract shape.
- PAINT_DESIGN's "run_cli's `render=` becomes optional" gains an
  amendment note: the no-lens graduate landed as `renderer=`'s
  transcription default, not as an optional `render=`.
- REFS_DESIGN §4 gains a pointer to the framework-tier `ref_schemes=`
  declaration (this document, §7).

**Build sequence.** S1 — signature, overloads, construction validation
(the seam alone, no behavior change). S2 — the offer seam
(`_offered_width`, per-frame offers in both live hosts). S3 — the
transcription default (the `width: int | None` widening through the
shared core, the wrapper, the `tags=` fence). S4 — `ref_schemes=`
(replace semantics, fault classification, the frame bracket). S5 — the
internal flip and docs residue. Each slice lands green through the full
gate; S3 verifies the appearance and outputgen panels stay byte-stable
(the widening adds an arm; existing `int` calls are untouched).
