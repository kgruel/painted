# The host rung — interactive delivery under the dual allocation contract

**Status: PLANNED (drafted 2026-07-15, arc `thread/host-rung`)** — the 0.13
milestone (M6). Nothing in this document is shipped unless explicitly marked
as existing behavior; present-tense statements about the *design* describe
intent, and each section will be amended by deliberation rounds before
ratification.

Subordinate to `docs/RENDER_MODEL.md` (RATIFIED 2026-07-10): this document
realizes the model's §2 **dual allocation contract** at the interactive rung
and adds nothing to it. Companion to `docs/RENDERER_CONTRACT_DESIGN.md`
(IMPLEMENTED 0.11/0.12), whose `(data, fidelity, width) → Block` seam this
design extends without breaking; amends `docs/LIVE_DELIVERY_DESIGN.md` §10
at one point (§5 below). This document **absorbs** `docs/VIEWPORT_DESIGN.md`
(deleted in the same change; preserved in git): the `Viewport` primitive it
specified shipped long ago and its reference lives in §6; the wiring it
anticipated is this arc.

## 1. The thesis — one renderer, four deliveries

The semantic renderer is the unit that travels the ladder unchanged
(RENDER_MODEL law 7). Three rungs honor that today: `print_block` (STATIC),
`InPlaceRenderer` and `StreamSurface` (LIVE). The fourth — interactive
`Surface` — does not: a Surface app paints a `Buffer` directly, so reusing a
CLI command's renderer in a TUI means hand-rolling the glue every consumer
has hand-rolled (evidence, §8). The host rung is the Block-returning path
around `Surface`: a semantic renderer produces a content Block; a host-rung
adapter owns the frame — viewport, scroll state, evidence, chrome, input
routing, hit testing. Direct Buffer painting remains fully supported; the
adapter is an addition, not a replacement.

Exit criteria (roadmap ruling, 2026-07-11): one reference renderer works
through `print_block`, `InPlaceRenderer`, `StreamSurface`, and interactive
`Surface`; the renderer consumes no full `CliContext`; natural-height
overflow is scrollable and visibly evidenced; direct-Buffer Surface apps
remain supported.

## 2. The dual allocation contract — two arms, one ownership rule

Restated from RENDER_MODEL §2 (the normative source), because every section
below hangs off it:

```
height offered  (height=H)    → the renderer accepts vertical allocation,
                                returns a frame of exactly H rows, and owns
                                evidence for content it omits.
height omitted  (height=None) → the renderer returns natural-height content;
                                the host applies a viewport (vslice + offset)
                                and owns viewport state and evidence.
```

The arms are not rival architectures — a dashboard takes height and marks
its own semantic cut ("… 763 older entries"); an explorer omits it and gets
host scrolling over everything. Ownership of loss follows the offer (law 6):
whichever layer *decides* what is not shown marks it; mechanisms stay
silent. The omitted arm is the default and the backstop, not a failure mode:
STATIC delivery already lives on it with the terminal emulator's scrollback
as the viewport, and `InPlaceRenderer` already clips oversized frames with
evidence (LIVE_DELIVERY §10, shipped 0.10).

## 3. The declaration — acceptance is declared, the offer is decided

Ruling sought (round 0 lean, uncontested by the cross-family consult): the
arm is **view semantics, not delivery policy** — two real interactive
consumers want opposite arms in the same delivery mode (§8). So neither the
delivery defaults it nor the runtime negotiates it; the app declares it,
painted's construction-time grain (flags, tags, ref schemes, capability
brackets — declare at construction, derive thereafter).

Two facts the design keeps separate:

- **Acceptance** — declared at construction, on the renderer binding: this
  renderer honors a height offer (it has the height-aware callable shape,
  §4). Nothing declared means the three-argument contract and the omitted
  arm everywhere: today's behavior, unchanged.
- **The offer** — decided by the host per delivery invocation. Note the
  matrix has three rows, not two — an undeclared renderer has no `height`
  keyword to pass anything to:

  ```
  undeclared binding            → invoke (data, fidelity, width); the
                                  omitted arm semantically, no keyword
  declared binding, gated off   → invoke with height=None (off-TTY always;
                                  STATIC TTY — scrollback is a working
                                  viewport, and "known ≠ offered" is the
                                  ratified proviso: run_cli knowing the
                                  terminal is 60 rows is not permission to
                                  offer them)
  declared binding, gated on    → invoke with height=H (a hard vertical
                                  frame: alt-screen, interactive, bounded
                                  inline-live region on a TTY)
  ```

  Whether a *declared* renderer on a STATIC TTY can request a synthesized
  hard frame ("screenful semantics") is **unresolved** — §9 Q7. Until
  ruled, STATIC TTY sits in the gated-off row unconditionally. If it ships,
  it is a *separate* declaration from acceptance: "this callable can honor
  H" and "this delivery should manufacture a hard frame despite usable
  scrollback" are different propositions.

The honesty property is **conditional**, not unconditional: it is not
"declared acceptance must visibly change output" but *when passed integer
`H`, the returned Block has exactly `H` rows* (law 5, property-testable).
Natural content that coincidentally measures `H` satisfies it; byte
inequality is not required.

**Declaration grain** (round-0 P2, adopted): the declaration attaches
conceptually to the **renderer binding**, not the command. `run_cli`'s
one-binding-per-command form is the first surface, not the architectural
limit — a future command whose top-level view flips at runtime between a
budget-fit dashboard and a scrolling explorer selects among *pre-declared
bindings* (the host knows the arm before calling; the caching rule in §6
stays unambiguous), never inspects results. No prose in this document or
its successors may claim "the command owns vertical semantics."

Rejected alternatives, for the record:

- *Delivery-defaulted arms* (STATIC→None, INTERACTIVE→H): contradicted by
  the consumer evidence — a tasks dashboard and a store explorer are both
  INTERACTIVE and want opposite arms. A delivery-keyed default would key
  rendering decisions off destination rather than declared meaning — the
  framework contradicting the library's thesis.
- *Runtime result negotiation* (host offers, inspects what came back):
  breaks the resize matrix's caching rule (re-render vs re-slice becomes
  unknowable without asking), and reopens per-offer dynamism one milestone
  after ratifying that even capabilities are standing facts.

## 4. The signature — a distinct height-aware callable

The 0.11 contract stays untouched: `renderer=(data, fidelity, width) →
Block`, and every existing consumer remains source-compatible without
edits. Declared acceptors adopt the height-aware shape:

```python
def renderer(data, fidelity, width) -> Block: ...            # unchanged

def height_renderer(data, fidelity, width, *,
                    height: int | None) -> Block: ...        # declared acceptors
```

`height` is **keyword-only and has no default** in the height-aware
protocol. The host always passes it explicitly — including `height=None` on
gated-off deliveries (a pipe, an undeclared STATIC TTY) — so omission is an
observable decision in the call, never Python's accidental defaulting. This
is how "height omitted is deliberate" (RENDER_MODEL §2 proviso) becomes
mechanical rather than aspirational. A false declaration or wrong callable
shape fails loudly at first invocation; no arity inspection.

Height must reach the **semantic renderer**, not stop at a Surface-only
adapter (round-0 P1). Confining it to the adapter would fork the contract:
the same renderer would no longer travel the four rungs unchanged; direct
mechanism consumers (siftd drives `InPlaceRenderer` below the framework)
could not participate in semantic height; and offered-arm omission evidence
would have to be invented below the layer that understands the omitted
content — law 6 inverted.

Rejected: a public `Allocation(width, height)` parameter object. It either
replaces `width` (churning every renderer for no semantic gain) or coexists
with it (duplicate authority), and it recreates the silently-ignorable
carrier-field problem the renderer contract already rejected once — a field
appearing inside an object proves nothing about acceptance. Height is
precisely the input for which a *visible* contract amendment is the point.
(A private allocation value inside the adapter — as a cache key — is fine
and is not this rejection.)

## 5. Exactness and degenerate allocations

Two registers, kept separate so this subordinate document does not appear
to reopen ratified exactness (round-1 correction):

**Inherited — already normative in RENDER_MODEL §2, restated only:**

- `H` is the **content allocation after the host reserves its own chrome**
  (terminal 40 = 1 host indicator row + 39 offered). The host never crops
  the result further.
- A final renderer accepting integer `H` returns exactly `H` rows.
- Components keep their documented height semantics (exact / maximum /
  viewport — RENDER_MODEL §7 Q4): uniform exactness is wrong
  mid-composition; exactness is scoped to the **final** renderer.

**Proposed — new rulings this arc must ratify:**

- `block.height != H` is a **contract violation and fails loudly**
  (`ContractError` site); the host must not crop or pad the result into
  apparent compliance. Silent padding would mask the final-renderer
  exactness violation (law 5); silent cropping could additionally discard
  content unmarked (law 6).
- Short **fitted** content is padded *by the renderer* (exactness belongs
  to it); short **natural** content is padded *by the host adapter* when it
  constructs an exact delivery frame. Same operation, different owner,
  because ownership follows the offer.
- Degenerate heights: whether `H=0` is a valid offer depends on whether
  zero-height frames are representable at this boundary — if not, the host
  rejects the layout before invoking the renderer. At `H=1` the renderer
  decides whether the sole row is content or evidence; law-6 evidence is
  required only where the allocation physically permits it.
- **Amendment to LIVE_DELIVERY_DESIGN §10**: `finalize()`'s "deposits full
  height — no reason to lose content" holds only for natural-height input.
  Under the offered arm, finalize deposits the `H`-row Block the renderer
  returned; the content the renderer semantically omitted is not
  resurrected at deposit time. The amendment lands when this document
  ratifies.

## 6. The viewport adapter — the omitted arm, wired

*(This section absorbs `VIEWPORT_DESIGN.md`. The `Viewport` primitive is
shipped, public API; everything after "Wiring" is this arc's design.)*

**The primitive (shipped).** `Viewport` (`src/painted/viewport.py`, exported
from `painted`) is frozen scroll state — `offset` / `visible` / `content` —
with derived `max_offset`, `can_scroll`, `is_at_top`, `is_at_bottom`, and
pure transition ops: `scroll(delta)`, `scroll_to`, `page_up`/`page_down`,
`home`/`end`, `scroll_into_view(index)`, `with_content`/`with_visible`
(both clamp). It holds slice parameters and never slices; rendering is
`vslice(content, vp.offset, vp.visible)`. Clamping is a property of the
**transition ops**, which normalize their result to `[0, max_offset]` —
not a construction invariant: there is no validation on direct
construction, and callers building a `Viewport` by hand own its validity.
Content smaller than the viewport makes scrolling a no-op. It has no TUI
dependencies. The component migration the absorbed doc deferred as "a
future refactor" has since **shipped**: `ListState`, `TableState`, and
`DataExplorerState` all carry a `Viewport` and delegate scroll-into-view
to it. What components still lack is law-6 evidence for their own windows
(§9 Q6).

**Wiring (this arc).** The adapter is the host half of the omitted arm:

- **Caching**: the host holds the natural-height Block and the renderer
  inputs it was produced from. Cache publication is atomic with its input
  key — streaming data arriving concurrently with a resize must not install
  an old Block under a new generation.
- **Scroll evidence**: the adapter renders the affordance the render-model
  audit found missing — *movable* host viewporting and component-owned
  windows have no evidence today; `InPlaceRenderer`'s fixed head-clip
  (LIVE_DELIVERY §10) is the one shipped exception. The evidence row
  (`… ▼ 763 more rows`, ambient icon set, ASCII degradation) is
  host-authored because the host decided the window, and it counts **rows**,
  not entries — the adapter knows Block height and offset, never how rows
  map to semantic records; an entry count is the application's to supply.
  Exact form is a deliberation item (§9 Q2).
- **Intent, then geometry**: viewing intent — at-bottom/following,
  cursor-following, top-anchored — is captured *before* mutating `visible`
  or `content`, then reapplied. Testing `is_at_bottom` after the mutation is
  too late (the flag may have changed meaning). Note the directionality:
  terminal *shrink* grows `max_offset` and usually keeps offsets valid;
  it is viewport *growth* or content shrink that forces clamping.
- **The width-reflow anchor policy**: numeric row offsets are not stable
  across width changes — re-rendering at a new width can wrap one semantic
  record into a different number of rows, so clamping alone cannot preserve
  the user's place. The adapter needs a declared policy: reset-to-top,
  preserve-follow, **semantic anchor via refs where the content carries
  them** (the denotation channel doing viewport work), numeric offset as
  documented fallback. Which policies ship and which is default is a
  deliberation item.
- **Hit testing is a frame transform**, not `y + offset`: resolve which
  delivery-frame region contains the coordinate (host chrome and evidence
  rows handle their own events or resolve to no ref); only content-region
  coordinates translate — `(x − origin_x, y − origin_y + offset)` — and
  resolve against the exact cached Block generation that produced the
  displayed frame. Known event-order hazard to close: `Surface` swaps
  buffers on SIGWINCH and drains input before the next repaint; mouse
  events in that interval must target the last displayed frame or be
  dropped, never translated through new geometry against old content.

**The resize matrix** (with the round-0 qualifications):

| Change | Action | Qualification |
|---|---|---|
| width | re-render | always semantic — width transforms through composition; then reconcile the viewport via the anchor policy |
| both dimensions | re-render | a width change; reconcile viewport after |
| offered height | re-render | the budget the semantic cut was made against no longer exists |
| omitted height | **re-slice only** | valid only when *no other* renderer input changed (data, fidelity, component state, capabilities, presentation policy, width) |
| any height change | recompose chrome/evidence/padding | host-authored rows recompose every frame even when the renderer is not called |

**Chrome and the hybrid shape.** Host viewporting treats a monolithic
content Block uniformly (RENDER_MODEL §4, the interaction boundary) — sticky regions (fixed header,
scrolling body: the *default* TUI shape per the consumer evidence) are the
offered arm's job: the final renderer takes `H`, reserves its own
header/footer rows internally, gives the remainder to its body viewport,
owns that scroll state and evidence, and returns exactly `H`. Per-region
host negotiation is deferred — it becomes real only if painted itself ever
owns several independently scrolling regions, not when an application
composes them.

## 7. The inward host-event seam — designed here, deliberately last

The omitted arm gives the host scroll state the application may care about
("viewport at end" — a follow-mode toggle). The outward channel exists:
`Surface.emit` carries observations up (instrumentation, Facts). The inward
seam — host viewing-state reaching the application as *input* — is the
provisional edge RENDER_MODEL §4/§7 Q1 left unresolved, and repurposing an
observation channel for control would change `emit`'s semantics; that
remains refused. This arc designs the seam against the **streaming
consumers that already voted with their feet**: `strange-loops follow` and
`ticked runner` both bypass `run_cli` for long-running foreground work
(§8). If the seam plus `StreamSurface` cannot bring `follow` home through
the framework, the design missed its consumer. Shape intentionally open
until the viewport adapter's needs are concrete (deliberation item; the
arc's later rounds).

## 8. Consumer evidence — the recon this design is gated on

Gathered 2026-07-15 (design-arc rule 2: evidence before doc):

| Consumer | Shape | What it proves |
|---|---|---|
| `ticked` Dashboard (loops-tasks) | `Surface`; hand-rolls `body_height = height − 2`, `cursor.scroll_into_view`, `min(body.height, height)` crop at paint | the adapter's job description, hand-rolled in the newest consumer |
| `ticked` detail mode | natural-height detail Block silently cropped to buffer | a live law-6 violation shipping today — the hole the adapter fills |
| `StoreExplorerApp`, `AutoresearchApp` (loops) | `Surface` explorers over the store | omitted arm wanted at INTERACTIVE — kills delivery-defaulted arms |
| tasks dashboard (strange-loops) | `run_cli` display commands (legacy `render=`) | offered arm wanted at INTERACTIVE — same delivery, opposite arm |
| `strange-loops follow`, `ticked runner` | bypass `run_cli` entirely (direct poll + print / foreground daemon) | the streaming host gap; acceptance test for §7 |
| siftd `output/live.py` | wraps `InPlaceRenderer` directly, below the framework, own gate/throttle/lifecycle | declaration-surface decisions never reach mechanism consumers; the *mechanism* contract (clip-with-evidence) is their delivery-level protection — §5 exactness is a renderer-boundary contract enforced by whichever caller made the offer, which a direct consumer may adopt itself but `InPlaceRenderer` (receiving only a completed Block) cannot enforce for it |

## 9. Open questions — the deliberation queue

1. **The declaration spelling** on `run_cli` and the adapter: name, shape,
   and how binding-attachment reads in a one-binding world (§3).
2. **Evidence form** for host scroll affordances: row vs rail, glyph
   vocabulary, interaction with gutters (§6).
3. **Anchor policy set and default** for width reflow; how far refs go as
   semantic anchors (§6).
4. **Degenerate-height rulings**: is `H=0` offerable; the `H=1`
   content-vs-evidence rule (§5).
5. **The inward seam's shape** (§7) — after the adapter's needs are
   concrete.
6. **Component-window evidence**: `ListState`/`TableState`/
   `DataExplorerState` already scroll through `Viewport` (shipped), but
   their windows carry no law-6 evidence — does that remediation ride 0.13
   or 0.14 honesty-remediation? (§6; reworded round 1 — the original
   migration question was already answered in the codebase.)
7. **STATIC-TTY declared-screenful**: ship in 0.13 or fence for later — no
   consumer evidence yet, and it needs a declaration *separate from*
   acceptance (§3). Round-1 recommendation: fence — declared renderers on
   STATIC TTY receive `height=None` in 0.13; a future screenful
   declaration can synthesize the hard frame when demand shows up.

## Appendix — round record

- **Round 0 (2026-07-15, pre-draft)**: consumer recon (§8) + cross-family
  consult, codex gpt-5.6-sol, session `initially-bold-caribou` (11
  findings). Endorsed declaration-with-delivery-gate over delivery defaults
  and result negotiation; contributed the acceptance/offer split and the
  conditional honesty property (§3), the required-keyword-only signature and
  the Allocation rejection (§4), the exactness/degenerate rules and the
  `finalize()` amendment (§5), the cache-invalidation qualifications, intent
  capture, width-reflow anchor policy, and hit-test frame transform (§6),
  and the binding-attachment grain with its strongest counterargument
  (runtime *selection* among pre-declared bindings — kept open as the
  future path, §3). Store: `thread/host-rung`,
  `design/host-rung-round-0`.
- **Round 1 (2026-07-15, doc review)**: same sol session, three passes over
  the minted draft. Verdict: architecture sound, not ratification-ready.
  P1s applied: the undeclared-binding row added to §3's offer matrix (an
  undeclared renderer has no `height` keyword — the two-row matrix
  contradicted §4's distinct callable contracts); STATIC-TTY screenful
  removed from the operative gate and marked unresolved pending Q7 (§3 had
  ruled what §9 held open); the `Viewport` component migration corrected
  from planned to shipped (`ListState`/`TableState`/`DataExplorerState`
  verified in-code) and Q6 reworded to the surviving question
  (component-window evidence). Also applied: §5 split into
  inherited-normative vs proposed rulings; padding/cropping law attribution
  precision; transition-op clamping (not construction invariant); scroll
  evidence narrowed (InPlace head-clip is the shipped exception) and pinned
  to row counts; RENDER_MODEL citations §5→§4; siftd row's
  mechanism-vs-renderer-boundary protection split. Ruling recommendations
  on the §9 queue (Q1 `height_renderer=` binding spelling; Q2 reserved
  evidence row over a rail; Q3 anchor precedence follow → ref → numeric →
  top; Q4 `H≥0`, `H=0` valid/evidence-waived; Q7 fence) recorded for
  Kyle's round-2 rulings; Q5 (inward seam shape) confirmed as the one
  genuine deferral. Store: `design/host-rung-round-1`.
