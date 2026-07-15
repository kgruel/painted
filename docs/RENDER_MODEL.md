# The render model — one renderer, progressively capable hosts

**Status: RATIFIED 2026-07-10; amended 2026-07-14** (RENDERER_CONTRACT_DESIGN
§9.5 residue sweep — §7 Q3 resolved, §2's capability-input qualifier
decided, the §8 law-1/law-7 audit rows dated-annotated in place; the
2026-07-10 audit text is preserved as historical evidence, not rewritten).
Design of record, together with its
evidence companion `docs/RENDER_MODEL_AUDIT.md`. Subsequent changes are
amendments against the laws in §4, not revisions of the foundational model.
The §7 questions are implementation and API-expression questions; none
undermines the ownership boundaries, and ratification does not prejudge
their answers — the model is falsifiable there (loops adoption can reject
the renderer boundary; oversized in-place delivery can expose the host
contract; the capability vocabulary can prove too broad).

Provenance: the 2026-07-09/10 conceptual review (GPT-5.6 architecture pass +
follow-up dialogue), seven revision rounds — r2: nine-finding review of r1
(pipeline ownership, two axes, Format exception); r3: four-tracer code
audit of the law-status claims (§8); r4: cross-review of the audit
(corrected law-7 classification, five ambient channels, render capabilities
as a renderer input, the ownership refinement of law 6); r5: the **dual
allocation contract** (§2), content Block / delivery frame split (§1), the
interaction boundary (§4), the honesty umbrella; r6: representation-level
host boundary, provisional inward seam (Emit is outward-only),
`InPlaceRenderer` contract named; r7 (final): ratification wording — host
row drops input resolution (that's the caller/orchestrator), law 1 speaks
in offered allocation. This is the *umbrella* page — position:

```
RENDER_MODEL.md    normative conceptual model (this page)
ARCHITECTURE.md    implementation structure and data flow (subordinate)
*_DESIGN.md        subsystem decisions and history
```

The per-subsystem designs (`FIDELITY_DESIGN.md`, `LIVE_DELIVERY_DESIGN.md`,
`PAINT_DESIGN.md`) each ratified one axis of this model; this document states
the spine they share, so a fresh reader sees the ladder before the
subsystems. It coins no new types and proposes no renames — every fix here
is definitional.

## 1. The thesis

> Author one semantic renderer returning a `Block`; reuse it unchanged as
> delivery progresses from static output through live to interactive hosts.

```
domain state + fidelity + offered allocation + capabilities
              │
              ▼
      semantic renderer
      (project + compose)
              │
              ▼
        content Block
              │
              ▼
   host frame composition
   (representation-level: viewport,
    chrome, decoration — only for
    dimensions and facilities the
    renderer did not accept, §2)
              │
              ▼
      delivery frame ──▶ Writer
```

The semantic renderer owns both projection *and* composition: it selects
views, arranges them, and returns the complete **content Block**. What
travels the ladder unchanged is the whole function, not a pre-composition
fragment. The host owns the **delivery frame**: for dimensions and
facilities the renderer did not accept, the host applies
representation-level transforms (a viewport is `vslice` plus an offset of
viewing state) and composes content derived solely from host/viewing state
(chrome, highlights). It never consults the domain subject. This makes
"frame is a role played by a Block" precise: the delivery frame *is* the
content Block unless the host transformed it. (`vslice` closes the
primitive gap; the host *adapter* — viewport state + slice + padding +
evidence + input routing — remains to be designed, §7 Q1.)

There are two monotonic axes, not one ladder:

```
Semantic authoring:  transcription → explicit projection → composition
Host capability:     one-shot → live → interactive
```

The invariant is **monotonic enhancement**: progress on the host axis never
requires rewriting work on the semantic axis. This is already ratified
per-axis — delivery ("climbing a rung never rewrites the rung below",
LIVE_DELIVERY_DESIGN) and disclosure (the consumption ladder,
FIDELITY_DESIGN §1) — but has never been stated whole. The acceptance test
for any painted API decision:

> Does it slot into an existing render function, or force a rewrite?

The two axes can still be taught sequentially. The product ladder, with the
axis each rung grows:

| Rung | Axis | You need | You write |
|------|------|----------|-----------|
| 1 | (defaults) | decent defaults | `paint(value)` |
| 2 | semantic | representation control | a renderer: `def view(data, ...) -> Block` |
| 3 | semantic | layout control | composition: `border(pad(join(...)))` |
| 4 | host | lifecycle control | pick a delivery host (`print_block`, `InPlaceRenderer`) — or declare modes and let `run_cli` orchestrate the selection |
| 5 | host | interaction | `Surface` — state + input around the same renderer |

The rungs are not successive versions of one abstraction — `paint()`,
`run_cli()`, and `Surface` operate at different conceptual levels. The
continuous thread is the render function returning `Block`.

## 2. The four cross-host control axes

Four controls recur across the host axis — some resolved implicitly, some
unsupported by particular entry points — and every control belongs to
exactly one of them:

```
Fidelity     what information — compiled user disclosure intent
Allocation   what space       — offered width, optionally offered height
Format       what encoding    — ANSI / plain / HTML / structured serialization
Mode         what cadence     — static / live / interactive lifecycle
```

These four are the *host-selection and policy* axes — they are not an
inventory of renderer inputs. Domain state and ambient presentation policy
(palette, icons, borders, vocabulary registry, role overrides — §4 law 1)
are also renderer inputs, but they don't select hosts and no host
reinterprets them.

The sorting axis between Fidelity and Allocation is **provenance, not
kind**.
Everything the user declared (`-v`, `--thinking`, `--max-lines`) compiles
into `Fidelity`; everything the environment imposes (terminal geometry,
TTY-ness) stays outside it. The budgets (`chars`/`lines`) are quantitative
but they are *intent* — "give me the terse version" — not capacity:

```
tool --max-lines 10 > report.txt
```

means *preserve my density limit independent of the destination*. A narrow
terminal means *arrange the requested representation within available
geometry*. These are observably different: the user budget survives piping
as stated intent; the width a renderer receives under a pipe is a resolved
*fallback* (`COLUMNS`/`get_terminal_size`), not a destination-imposed
measure. Merging them under one "constraints" object would obscure agency
and persistence.

> **Fidelity is the resolved, destination-independent statement of how much
> and which information the user asked to see.**

**The Format exception.** Format is the one axis with a sanctioned fork off
the Block path. Visual formats (ANSI, plain, HTML) serialize the Block;
structured formats serialize *domain data* through a parallel boundary —
`--json` hands the fetched data to `json.dumps` directly
(`cli/runner.py:_export_json`) and never invokes the semantic renderer.
This is deliberate: a machine consumer wants the subject, not a picture of
it. The exception is explicit here so nothing else claims it as precedent.

**Render capabilities.** *(Dated amendment 2026-07-14: the "provisional,
r4" qualifier is removed — capabilities are a decided input, shipped as
`capabilities.py` and transported through the sixth ContextVar channel,
RENDERER_CONTRACT_DESIGN §9.)* The audit surfaced a third
legitimate renderer input beside fidelity and allocation: **which visual
carriers the destination supports** — color, glyph repertoire, link
delivery. `raymarch` chooses between a truecolor half-block portrait and a
luminance glyph ramp; `starmap` advertises links only where link delivery
works. These are honest adaptations to the destination, not lifecycle
coupling. The renderer-input set is therefore:

```
semantic renderer inputs
├── domain state
├── fidelity              (user intent)
├── offered allocation    (width; optionally height — the dual contract)
├── render capabilities   (color / glyph / link support)
└── ambient presentation policy
```

Mode and host *lifecycle* stay out of this set — that remains law 7's
prohibition. Two fences keep "capabilities" from swallowing existing
mechanisms: glyph *fallback* stays ambient (`IconSet`'s ASCII degradation),
and color *downsampling* stays serialization-side (`ColorDepth` in
`Writer`). A capability input is only for **content-structure choices** —
selecting the carrier, not substituting glyphs or quantizing colors.
`ctx.use_ansi` was the coarse proxy; the shipped vocabulary is
`capabilities.py`'s `Capabilities` (color/glyph/link — RENDERER_CONTRACT_DESIGN
§9, dated amendment 2026-07-14, §7 Q3 resolved).

**The allocation contract (r5).** A dimension is *offered*, not ambient —
and the old Option A / Option B question ("who owns vertical adaptation?")
dissolves into the width contract, generalized to height and decided per
render call:

```
height offered  → the renderer accepts vertical allocation, returns a
                  fitted frame (exact at this final boundary), and owns
                  evidence for content it omits.
height omitted  → the renderer returns natural-height content; the host
                  applies a viewport (vslice + offset) and owns viewport
                  state and evidence.
```

The two arms are not rival architectures — a dashboard takes height and
marks its own truncation; a record stream omits it and gets host
scrolling. Monotonic enhancement is preserved: static delivery already
lives on the omitted arm with the terminal emulator as its viewport
(scrollback, scrollbar); an alt-screen host must explicitly provide the
viewport behavior that entering the alt screen removed. The rule recurses
to component viewports unchanged.

Two provisos:

- **Offered ≠ known.** A host can know `height=40` and offer
  `height=None`. Presence in a context object is not allocation
  ownership — the renderer contract must make "height omitted"
  deliberate. (Today's `CliContext` exposes `width` and `height`
  indiscriminately — further evidence it is too broad for the eventual
  renderer boundary, though still not proof a public `RenderContext` type
  is needed, §6.)
- **Exactness is scoped to the final renderer.** A final renderer
  accepting `height=H` returns exactly H — which lets a host reserve its
  own chrome rows first (terminal 40 = 1 indicator + 39 offered) and
  never crop the result further. Reusable *components* instead document
  whether an accepted height is exact, a maximum, or a viewport height:
  vertical stacking makes uniform exactness wrong mid-composition — a
  deliberate, named asymmetry with the width contract.

## 3. Glossary — one term per decision boundary

The rule, enforceable editorially without any API migration:

> A term identifies a **decision boundary**, not another name for an
> existing operation. Neighboring terms must not compete for the same role.

| Term | The boundary it names |
|------|----------------------|
| **Semantic renderer** | the application-authored function: domain state + fidelity + offered allocation + capabilities → **content Block**. Selects views, composes them, owns meaning and accepted allocation. The unit that travels the ladder unchanged. |
| **View** | a reusable library projection — lenses and components; what a semantic renderer selects and arranges. `painted.views` keeps the name as the namespace. |
| **Lens** | a data-shaped view (`tree_lens`, `chart_lens`, `shape_lens`) |
| **Transcription** | the conservative built-in projection `paint()` applies — declared-not-invented |
| **Block** | the immutable visual interchange format; already resolved, carries no policy |
| **Composition** | `Block → Block` transforms; no domain or disclosure knowledge |
| **Host** | owns delivery lifecycle and any viewing state, representation transforms, or host-authored content for allocation and facilities the renderer did not accept. Never consults the domain subject. (A caller or host orchestrator — `run_cli` — resolves renderer inputs; `print_block` and `InPlaceRenderer` receive completed Blocks.) |
| **Surface** | painted's *interactive host* — adds lifecycle and input to the same rendering model. Never a drawing target. |
| **Buffer** | the mutable paint target a Surface owns |
| **Fidelity** | the compiled disclosure intent (`depth`, `visible`, `chars`, `lines`) |
| **Zoom** | the rung-1 porthole onto fidelity's depth axis (blessed permanently, FIDELITY_DESIGN §1) |
| **Tag / facet** | a named orthogonal information dimension — set semantics, not ordered |
| **Budget** | a user-declared density ceiling (`--max-chars`/`--max-lines`) — intent, not capacity |
| **Width** | environment- or caller-provided layout allocation; exact when passed (the width contract) |
| **Offered allocation** | the dimensions the host actually gave the renderer, as distinct from geometry it merely knows; ownership of loss follows the offer (§2) |
| **Frame** | a *role*, not a type: the Block a host delivers at one instant — the content Block itself, or the host's geometry-transformed slice of it |
| **Delivery** | presenting a frame. Rendering creates content Blocks; host frame composition produces the frame; delivery presents it. |

Terms that stay documentation-tier and never become types: *frame*,
*projector* (the general word for anything-→-Block when teaching), the host
taxonomy itself. They earn public API surface only if a consumer needs to
hold one.

The delivery taxonomy — hosts, and the one orchestrator:

| Name | Role |
|------|------|
| `print_block` | one-shot host |
| `InPlaceRenderer` | in-place live host (scrollback, no alt screen) |
| `StreamSurface` | alt-screen live host for streamed data (a `Surface` underneath) |
| `Surface` | interactive host |
| `paint()` | default transcription + one-shot delivery, in one convenience call |
| `run_cli()` | **not a host** — the grammar compiler and host *selector*; resolves policy, then dispatches to one of the above. `--live` is likewise a selection flag, not a host. |

## 4. The laws

The laws share one umbrella, stated plainly rather than coined:

> **Painted does not silently claim behavior it did not provide.** Declared
> capabilities affect output (the honesty rule, FIDELITY_DESIGN §1);
> discarded requested content leaves appropriate evidence (law 6); and
> crossings between host and application remain observable (refs outward;
> host events inward, provisional — §4's interaction boundary).

| # | Law | Status |
|---|-----|--------|
| 1 | **Determinism** — given the same domain and component state, Fidelity, offered allocation, render capabilities, and ambient presentation policy (palette, icons, borders, vocabulary registry, role overrides), a semantic renderer produces the same content Block. | Held by design (frozen state, pure render fns); pinned per-component by property tests. Five content-affecting ambient channels verified 2026-07-10, corrected r4: `Theme` atomically sets **four** of them (palette, icons, borders, role overrides — `theme.py`); the vocabulary registry is a separate ContextVar. `refs` resolve at serialization in the core path (`writer.py:209`); `starmap`'s render-time `resolve_ref` probe is a capability read (§2), not a sixth ambient channel. |
| 2 | **Depth monotonicity** — raising depth elaborates; it never contradicts or removes a lower-depth conclusion. | Editorial law; meaning-preservation is domain-specific. Testable per app. |
| 3 | **Facet independence** — enabling a facet does not change the *selection or meaning* of unrelated information; layout may reflow to accommodate it. | Sibling of the honesty rule (FIDELITY_DESIGN §1); testable per app — semantically, not byte-literally: a literal unchanged-output assertion would fail on legitimate reflow. |
| 4 | **Destination independence** — no destination capability or terminal geometry participates in fidelity resolution. | **Verified 2026-07-10** (§8): every `Fidelity` construction site in `src/` is argv/declaration-pure; `detect_context` computes TTY/geometry into separate `CliContext` fields and never writes into the fidelity it's handed. Two gaps: ungated (a regression reading terminal size in `parse_fidelity` would pass today's suite), and FIDELITY_DESIGN documents `build_fidelity`'s *position* but not the keep-geometry-out obligation on its *content*. The hatch stays app territory. |
| 5 | **Allocation safety** — a passed width is exact, never exceeded; a height accepted by a *final* renderer is likewise exact (§2). | Width: ratified contract, property-tested. Height: r5 extension, not yet implemented — components document their height semantics (exact / maximum / viewport, §7 Q4). |
| 6 | **Omission evidence** — the layer that *knowingly* discards requested semantic content must preserve evidence of that loss where the format permits; allocation-driven loss never silently masquerades as user intent. | **Audited 2026-07-10 (§8): target invariant, not current fact.** The marked/silent split tracks the *layer*, not the axis: width loss in the lens/compose layer is mostly marked; primitive width loss and **all height loss are silent** — no height-overflow evidence primitive, no rendered scroll affordance in the package. The r4 ownership form (below) shrinks the remediation surface: mechanisms may clip silently; *deciders* must mark. |
| 7 | **Host independence** — equivalent semantic inputs, allocation, presentation policy, and render capabilities produce equivalent Blocks regardless of host *lifecycle*; a semantic renderer never consumes lifecycle or mode. | **Target invariant, not current fact — but closer than r3 reported (corrected r4).** 23 of 25 in-repo `CliContext` renderers read only fidelity + allocation; 2 (`raymarch`, `starmap`) additionally consume output *capabilities* via the `use_ansi` proxy — legitimate under this law's r4 form, pending the capability vocabulary (§7 Q3); **0** dispatch on lifecycle inside a semantic renderer (r3 miscounted: `responsive.py`/`table.py` read `is_tty` in `_handle_interactive`, which is host territory). `views/` is clean and arch-enforced. The friction evidence stands: `ResponsiveSurface` fabricates a fake `CliContext` (`is_tty=True, mode=INTERACTIVE`) to reuse its renderer. Loops adoption + `run_cli` optional-render is the acceptance test. *(Dated annotation 2026-07-14: the fabricated-`CliContext` friction was swept in 0.11 — `run_cli`'s `renderer=` seam, RENDERER_CONTRACT_DESIGN §9 — and the two `use_ansi` capability readers (`raymarch`, `starmap`) converted to `current_capabilities()` in 0.12 (§9.5), resolving §7 Q3. The status text above is preserved as the 2026-07-10 finding, not rewritten.)* |
| 8 | **No downstream policy** — `Block`, composition, `Buffer`, `Writer` carry no disclosure policy. Composition never asks *why* a row exists. | **Verified 2026-07-10** (§8) for the named modules — but held by *discipline*, not construction: no gate forbids `compose.py` importing fidelity, and the arch tests only check cross-layer direction. One sanctioned exception one file over: `core/doc.py` hosts the shared disclosure walk (deliberate, documented in its docstring, kept out of `core.__all__`) — any future gate must name it, `_CLI_SEAMS`-style. |

**Determinism fine print (law 1).** Time is not an exception. The component
pattern externalizes it into frozen state — a spinner's frame index lives in
its state, and render is pure per-state. Animation is a sequence of
deterministic renders, not a time-dependent one.

**Facet resolution (law 3's fine print).** Implication resolves at compile
time — explicit (`--rationale` passed) ∪ implied (`implied_at ≤ depth`) →
effective, and renderers see only the effective set. A tag that must never
be depth-implied simply omits `implied_at`; explicit-only is the grammar's
default by omission, not a feature to add.

**Omission's three faces (law 6).** Not all omission is equal:

- **Intentional omission** — requested through Fidelity (`--max-lines 10`,
  low depth). The user asked for less; silence may be honest, a marker
  optional.
- **Allocation-driven loss** — requested information could not fit the
  offered space. Evidence is preferred wherever the format permits ("12 more
  records", a truncation mark, an expand affordance).
- **Visual clipping** — exact-width behavior at the cell level; ellipsis or
  another mark follows the width contract.

The law binds the middle case only — and the **ownership rule** resolves
its tension with law 8 (a `Buffer` cannot invent a "12 more records"
marker): the layer that *knowingly chooses* to discard requested semantic
content owes evidence; a lower-level mechanism that merely executes an
explicit clipping contract does not. Consequences:

- `Block.paint()` and `Buffer.put()` may remain silent clipping mechanisms.
- A host viewporting natural-height content owes viewport evidence. Host
  chrome (a scroll indicator) is host-authored content *about viewing
  state*, composed around the content Block — never derived from the
  subject, so law 8 survives it.
- A renderer that accepted height owns all loss inside it; the host,
  having offered exactly (§2), has no reason to crop further.
- A table dropping semantic columns owes a mark or an exposed count.
- Explicit `Wrap.NONE` may stay silent — clipping is its declared contract
  (whether the *default* counts as "declared" is §7 Q2).
- Fidelity-requested omission may stay silent.

**The interaction boundary (r5).** The dynamic form of laws 6–8:

> Host-side interaction transforms an existing semantic-renderer result
> without changing renderer inputs. App-side interaction changes renderer
> inputs and invokes the renderer again.

The stress-tested sorting:

| Interaction | Side | Why |
|---|---|---|
| frame scroll; follow/tail | host | viewing state over the existing content Block |
| height resize (omitted arm) | host | re-slice; no re-render needed |
| width resize; height resize (offered arm) | app path | allocation is a renderer input |
| expand/collapse; focus move; runtime fidelity | app | renderer inputs changed |
| component scroll | app | component state is a renderer input |
| hit-testing | crossing | host translates coordinates through the viewport, reads the cell's **ref** (`Surface.hit()` exists today), hands meaning outward |
| infinite loading | crossing | host signals "viewport at end" through the provisional host-event seam; app fetches and re-renders — the loading boundary stays visible |
| view-search | host | searches and decorates the *representation*; must disclose its scope — it cannot find what fidelity did not disclose |
| data-search | app | searches the *subject*; a semantic selection change |

Crossings travel two seams — one real, one provisional. **Refs** outward
(representation → meaning) exists today: `Buffer.hit`/`Surface.hit` resolve
a coordinate to a cell's ref. The inward seam — host viewing-state events
reaching the application ("viewport at end") — is **provisional**:
`Surface.emit()` is an *outward observation* callback (instrumentation,
Facts upstream), and repurposing an observational channel for control
would change its semantics substantially. The host-event seam's API is
deliberately unresolved (§7 Q1). Host viewporting treats a monolithic content Block
*uniformly* — sticky content (fixed header, scrolling body) is the shape
it refuses: the app must take the offered-height arm and compose the split
itself, or use a purpose-built interactive structure. (Layers are one
implementation, not the architectural requirement.)

Three legitimate scales for large content, none prohibited, each honest:
finite → natural Block + host viewport; large-but-bounded → component/app
viewport with windowed rendering (scrolling becomes renderer-input state
and re-renders); unbounded → acquisition-aware app state with visible
loading boundaries. A host never guarantees cheap scrolling over an
arbitrarily large subject.

## 5. Requested vs achieved fidelity

Three stages, only the middle one a type:

```
declared intent ──▶ compiled Fidelity ──▶ rendered representation under an allocation
```

A user may request FULL and receive eight columns of width; the result may
not achieve the request. That distinction matters when omission must be
visible — which is law 6's middle case — but it does not automatically
warrant a `RenderResult` type. Programmatic achieved-fidelity reporting
waits for a concrete consumer.

## 6. What this document deliberately does not decide

- **A shared `RenderContext`.** Deferred to loops-adoption evidence. The
  test, per the concept filter: *does it eliminate host-specific adaptation
  for consumers, or merely package several arguments under another name?*
  `render(data, fidelity=…, width=…) -> Block` may already be the protocol.
  The offered-vs-known distinction (§2) adds evidence that `CliContext` is
  too broad for the renderer boundary — it exposes `height` whether or not
  the host offered it — without yet proving a public type is the fix.
- **Package boundaries / the root-layer exemption.** Real coupling observed
  during adoption drives extraction, not the neatness of a proposed layer
  diagram.
- **Performance budgets.** A separate lane: scenario baselines along the
  pipeline stages (project → compose → serialize → diff → deliver), plus the
  fidelity question *does lower detail do less work, or render-then-discard?*
- **Renaming `Surface`.** Declined. The ambiguity is resolved by definition
  (§3): Surface is the interactive host, Buffer is the paint target, and
  "surface" is never used for the latter.

## 7. Open questions

*(r5 resolved the former Q1 — vertical allocation ownership — into the
dual allocation contract, §2. Its residue is Q1 below, which absorbs the
former optional-render question: they turned out to be the same question.)*

1. **Expressing the allocation contract in APIs.** How do `run_cli` and
   `Surface` express "height known but not offered" without handing
   semantic renderers the full `CliContext`? This is now the same question
   as optional-render's signature — `render(data, fidelity=…, width=…,
   height=…?) -> Block`, with a `Surface` Block-returning render path
   alongside buffer painting. It carries two sub-designs: the **host
   viewport adapter** (Viewport state + `vslice` + short-content padding +
   host-authored evidence + input routing — the primitives exist, the
   adapter doesn't), and the **host-event seam** (how viewing-state events
   reach the app without repurposing the observational `emit()`). Loops
   adoption decides the signature; the adapter is painted-side work.
   (`ResponsiveSurface`'s fake-`CliContext` is the test case to dissolve.)
2. **Law 6 remediation shape** — narrowed by the ownership rule (§4): the
   owners are hosts viewporting natural-height content (viewport
   evidence — `Viewport.can_scroll` is computed today, never drawn),
   `list_view`/`table` scroll windows, `table` column drops, and
   `tree`/`flame` semantic drops. Primitives stay silent by contract.
   Two residuals: (a) is `Block.text`'s *default* `Wrap.NONE` a "declared"
   contract, or does defaulting make the silence undeclared? (b)
   **`InPlaceRenderer` must declare its oversized-frame behavior** — it
   cannot provide a movable viewport over rows already released to
   scrollback (the audit's tearing finding), so it picks one: frame must
   fit / clip with evidence / refuse / upgrade delivery to
   `StreamSurface`. Today's answer — tear silently — is the only one the
   model forbids. *(b resolved 0.10, ratified 2026-07-11: clip with
   evidence — LIVE_DELIVERY_DESIGN §10; pinned with the law-6 evidence
   gates.)*
3. **The capability vocabulary** — what replaces the `use_ansi` proxy:
   color / glyph / link facets? And where exactly the fence sits against
   the two existing capability mechanisms (ambient `IconSet` fallback,
   `ColorDepth` downsampling) so "capabilities" doesn't swallow them.
   *(resolved by RENDERER_CONTRACT_DESIGN §9, dated amendment 2026-07-14:
   `capabilities.py`'s three-facet `Capabilities` — color/glyph/link —
   ships as the sixth ambient ContextVar channel, resolved after fidelity
   and never participating in it; the fence holds as designed.)*
4. **Component height semantics** — the exact / maximum / viewport-height
   trichotomy (§2): declared per component by docstring convention, or
   worth a typed vocabulary? Which existing components (`table`,
   `list_view` take `visible_height`) mean which?
5. **Which gates graduate?** — three are specified (§8): the
   `parse_fidelity` purity test (law 4), the intra-core no-fidelity-import
   test with `core/doc.py` allowlisted (law 8), and evidence pins for the
   marked truncation paths (law 6 — today *no test anywhere* asserts a
   marker on width clipping in the primitive/Line layers).
6. **Where the glossary lives long-term** — this page, the consumer guide
   (`src/painted/CLAUDE.md`), or both with one generated from the other.

## 8. Verification record (2026-07-10)

Four parallel tracers (one Opus, three Sonnet) audited the law-status
claims against the code at commit `10d7fef`. Compressed here in the
FIDELITY_DESIGN §2 style; full tables in `docs/RENDER_MODEL_AUDIT.md`.
Counting method: "25 renderers" = files declaring
`def _render(ctx: CliContext, …)` under `demos/` + `src/painted/_demo_cli.py`.
Cross-review of the audit caught one classification error in r3 (the
`responsive.py`/`table.py` `is_tty` reads sit in `_handle_interactive`,
not in the renderers) — corrected below; the catch is itself the argument
for keeping the full reproducible inventory in-repo.

**Verdicts:**

| Law | Claimed (r2) | Found |
|-----|--------------|-------|
| 1 Determinism | ambient list "(palette, theme, icons, refs)" | List corrected (r4): **palette, icons, borders, vocabulary registry, role overrides** — five content-affecting ContextVar channels. `Theme` atomically sets four (not the vocabulary registry). Core-path `refs` resolve only in `Writer` ANSI emission (`core/writer.py:209`) — serialization-side, like `NO_COLOR`; `starmap`'s render-time probe is a capability read. *(Dated annotation 2026-07-14: six channels as of RENDERER_CONTRACT_DESIGN §9 — `capabilities.py`'s `Capabilities` ships as the sixth, distinguished from the other five as a logical renderer **input** that happens to travel ambiently, not a content-affecting presentation policy channel. The five-channel finding above is unchanged as of 2026-07-10; this note doesn't rewrite it.)* |
| 4 Destination independence | holds by construction | **Confirmed by reading**, all `Fidelity(...)` sites. Ungated; hatch obligation undocumented in FIDELITY_DESIGN. |
| 6 Omission evidence | needs audit | **Does not hold.** See below. |
| 7 Host independence | target invariant | Confirmed target; gap quantified (corrected r4): 23/25 renderers use fidelity + allocation only, 2/25 add capability reads, 0/25 lifecycle-dispatch inside a renderer — plus the taught signature + `Surface.render()` convention. *(Dated annotation 2026-07-14: the fabricated-`CliContext` friction evidence below (`ResponsiveSurface`) was swept in 0.11 — `run_cli`'s `renderer=` seam, RENDERER_CONTRACT_DESIGN §9 — and the two capability-reading renderers (`raymarch`, `starmap`) converted from the `use_ansi` proxy to `current_capabilities()` in 0.12 (§9.5). The "target invariant, not current fact" caveat narrows accordingly; the 2026-07-10 gap count above is the historical baseline, not current status.)* |
| 8 No downstream policy | holds by construction | **Confirmed for the named modules** (the "depth" in `writer.py` is `ColorDepth` — unrelated). Held by discipline: ungated. `core/doc.py` is the one deliberate exception (the shared disclosure walk lives there for import-order reasons; unexported). |

**Law 6, the layer-not-axis finding.** 25 geometry-loss paths inventoried.
The pattern:

| Layer | Width loss | Height loss |
|-------|-----------|-------------|
| lenses / compose (`truncate`, `fit_to_width`, `chart`, `tree` labels) | mostly **marked** (ambient ellipsis) | — |
| primitives (`Block.text` `Wrap.NONE` default, `Line.truncate`, `Line.to_block`) | **silent** | — |
| paint targets (`Block.paint`, `Buffer.put`, `Surface`) | **silent** | **silent** |
| scroll windows (`list_view`, `table` visible-height) | — | **silent** (no affordance) |

Ranked silent paths: (1) `Block.paint`/`Surface` clipping whole rows with
nothing emitted — the same renderer that marks under `print_block` loses
content invisibly under `Surface`, tying law 6's worst gap directly to
law 7; (2) `list_view`/`table` scroll windows — `Viewport.can_scroll`
computed, never rendered; (3) `Block.text`'s default `Wrap.NONE`; (4)
`Line.truncate` backing table cells (default `ellipsis=False`) and list
rows; (5) `tree_lens` dropping whole subtrees at `content_width <= 0`;
(6) `flame_lens` vanishing sub-minimum segments; (7) `border` titles and
`record_map` negative-width collapse.

Boundary blur worth designing away: `_render_scalar` can fire the
fidelity-chars marker (`"... [N chars]"`) *and* the width ellipsis on the
same string — two residues, no signal for which constraint bound; `table`'s
default `Overflow.CLIP` hides whole trailing columns behind one right-edge
ellipsis while `Overflow.FIT` answers honestly but is opt-in;
`budget_fields` returns a `dropped` count but marking is caller-owned.

**Law 7 baseline detail (corrected r4).** Taught signature
`render(ctx: CliContext, data)` (README + consumer guide) though the doc
examples read only `ctx.zoom`/`ctx.width`. In-repo: 23/25 renderers use
fidelity + allocation only (mechanically migratable); `raymarch.py:470+`
and `starmap.py:421+` additionally consume output capabilities via the
`use_ansi` proxy (legitimate under the r4 law; vocabulary is §7 Q3); zero
renderers dispatch on lifecycle — `responsive.py:576` and `table.py:399`
read `is_tty` inside `_handle_interactive`, which is host territory.
`views/` imports no cli — enforced. *(Dated pointer 2026-07-14: both
readers converted to `current_capabilities()` in 0.12 — RENDERER_CONTRACT_DESIGN
§9.5; §7 Q3 is resolved. This baseline detail is the 2026-07-10 finding,
left as historical evidence.)*

**Gates specified by the audit:**

- *Law 4*: call `parse_fidelity` twice with identical Namespaces under
  different `isatty`/`COLUMNS`/`LINES`, assert equal `Fidelity`; optional
  static check that `core/fidelity.py` + `parse_fidelity` never reference
  `os.environ`/`isatty`/`get_terminal_size`.
- *Law 8*: `_assert_no_imports` (the existing helper) over
  `{block, compose, cell, span, writer, buffer}.py` + `inplace.py` +
  `tui/{surface,layer}.py`, forbidding `core.fidelity` and `cli.types`,
  with `core/doc.py` explicitly allowlisted and commented.
- *Law 6*: today the "+N more" footer is the **only** geometry-adjacent
  evidence behavior with test coverage, and it's fidelity-driven. Any
  remediation should land with evidence pins, or the marks will rot.
