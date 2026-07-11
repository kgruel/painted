# painted 1.0.0 roadmap

## Release definition

painted 1.0.0 proves and stabilizes this promise:

> Author one semantic renderer returning a `Block`; reuse it unchanged as
> delivery progresses from static output through live to interactive hosts.

This is the expanded 1.0, ratified deliberately: the interactive host rung is
*inside* the promise, so 1.0 cannot ship until that rung is real. What stays
outside is the TUI application spine — keymap grammar, gesture maps,
composition batteries — which rides 1.x. The boundary: 1.0 proves a renderer
*survives* every delivery level; 1.x makes interactive *applications*
pleasant to build.

The release does not require every component, host feature, or performance
optimization to be finished. It does require the renderer/host boundary to be
real, reusable, documented, and supported by consumer evidence.

## Guiding model

`docs/RENDER_MODEL.md` (RATIFIED 2026-07-10) is the design of record; this
roadmap implements it and does not restate it. The load-bearing sentence:

> The semantic renderer owns meaning and accepted allocation. The host owns
> lifecycle, unaccepted allocation, representation-level viewing state, and
> content it authors about that state.

Four policy axes stay separate throughout: **Fidelity** (compiled disclosure
intent), **Allocation** (offered width, optionally offered height), **Format**
(how the result serializes), **Mode** (delivery lifecycle). Changes to the
model along the way are explicit amendments against its eight laws, recorded
in the document — never silent drift.

## How to read this roadmap

- **Milestones are contract deltas; versions are checkpoints.** Each milestone
  ships as one or more concise minor releases. The version numbers below are
  targets, not promises — we take as many minors as the work needs, and the
  numbering stretches rather than the releases swelling.
- **Consumers force the pace.** loops iterates in parallel the whole way, and
  new apps are started early as consumers — evidence generators during the
  work, not validators after it.
- **This document will change.** When adoption evidence contradicts a
  milestone, the milestone moves. The critical path ordering is the stable
  part.
- **Docs are authoritative; the store is operational.** This file and the
  design docs are the prose of record — they *describe the library*. The
  project store's `roadmap/` nodes carry live status, deliberation, and
  provenance. (The end-state ideal — store-authoritative with generated
  artifacts, the `semantic_article` pattern plus `to_markdown` — is named
  and deferred until loops' emit-vs-edit friction resolves.)
- **No build without a ratified design doc, with two qualifiers.**
  *Amend before minting*: where a lane already has a doc, it is amended —
  the semantic tree amends `DOC_IR_DESIGN.md`; the host rung absorbs
  `VIEWPORT_DESIGN.md` and sweeps its residue. New docs only for genuinely
  new contracts (renderer contract, host rung). *Evidence-gated timing*: a
  design doc is written after its evidence gate (the renderer-contract doc
  after the loops spike), never speculatively upfront. Register split, per
  the render-model template: the doc carries the contract, the store carries
  the deliberation, an audit or appendix carries the evidence.

## Consumer lanes (parallel, continuous)

These run alongside the milestones and feed them evidence:

- **loops / sl** — the rich-Fidelity forcing consumer. Deletes its duplicate
  flag-compilation machinery, adopts prompts (re-seal Confirm, store-scope
  Select), migrates renderers through the canonical boundary as it lands.
  The `semantic_article` lens (fold → Doc → terminal + HTML siblings) is
  already the first external doc-IR consumer, currently on a path hack that
  M2 removes.
- **A conventional static CLI** migrating incrementally from `print()` — the
  Rung-0-upward consumer shape. Start during M3–M4, not at validation time.
- **A sustained streaming or interactive app** — the host-rung consumer
  shape. Start alongside M5 so the viewport adapter and host-event seam are
  designed against a real event loop.

## Milestone 0: Ratify the render model — *mostly complete*

`RENDER_MODEL.md` + `RENDER_MODEL_AUDIT.md` are ratified and committed on the
`render-model` branch (41d7849, gate 10/10). Remaining residue:

- Merge the branch to main.
- Align `docs/ARCHITECTURE.md` with the content-Block/delivery-frame split and
  the model's glossary (one term per decision boundary).
- Merge the positioning flip (`semantic-renderer-positioning`, rebased onto
  the ratified vocabulary) — README/site copy claims re-verified against the
  model's glossary.

No release; docs and positioning only.

## Milestone 1: Make the laws executable — *rides 0.10*

Add inexpensive structural and behavioral guards before changing public APIs,
so every later milestone is measured against pinned law rather than
discipline.

Work:

- Assert identical declarations + argv compile to identical `Fidelity` under
  different TTY, `COLUMNS`, and `LINES` conditions (law 4).
- Prevent core composition and delivery modules from importing disclosure
  policy, with `core/doc.py` retained as the named exception (law 8).
- Pin existing marked truncation behavior with evidence-focused tests (law 6
  — today no test asserts a marker on width clipping).
- Add a cross-host harness that captures the content Block before delivery
  (law 1: static and live paths comparable before serialization).
- Preserve the audit's render and geometry-loss inventories as regression
  references.

Do not attempt universal tests for semantic depth monotonicity or facet
independence — those laws require application-specific assertions about
meaning, and facet independence is semantic (layout may reflow; a
byte-equality test would be wrong).

Exit criteria:

- Destination-dependent Fidelity resolution fails a test.
- Downstream disclosure-policy imports fail an architecture test.
- Existing omission evidence cannot disappear silently.

## Milestone 2: Ship the semantic tree — **0.10**

Promote the doc-IR realizations the trifecta evidence just earned: two worlds
(painted's docs site, loops' inquiry article) now realize one `Doc` tree as
sibling outputs, and the second world reaches the publisher via an
`importlib` path hack. This is the Format axis *confirmed*, not amended:
`render_html` stays the Block sink ("the browser as another terminal"); the
publisher is the sanctioned pre-Block semantic layer, which is also why
`core/doc.py` is law 8's allowlisted exception.

Work:

- Move `to_html` from `tools/doc_publish.py` into the packaged library, in a
  stable namespace beside `painted.display` (a publisher is not core — it
  emits foreign semantics — but "not core" never meant "not shipped").
- Settle the Inline union with `Link` as its first rich member, driven by the
  refs-as-plain-text friction in the article lens; wire it through both
  projectors (OSC 8 terminal-side, `<a href>` HTML-side) via the existing
  `RefScheme` channel.
- Export the `Doc` vocabulary through the one-way door under the semver
  guard.
- **`InPlaceRenderer` declares its oversized-frame behavior** — fit /
  clip-with-evidence / refuse / upgrade to `StreamSurface`. Front-loaded from
  honesty remediation because silent tearing is the one behavior the model
  forbids outright, and the fix is self-contained.
- Rider: the tags-only `AppCommand -h` interception asymmetry (small,
  pre-existing, one seam over from the 0.9 fix).
- Design doc: amend `docs/DOC_IR_DESIGN.md` (publisher home, Inline union,
  export) — no new document.

Exit criteria:

- The article publisher runs against installed painted — no repo checkout,
  no `PAINTED_REPO`.
- Both realizations of one `Doc` disclose identically (the shared
  `visible_body` walk, now pinned).
- Silent in-place tearing is impossible.

## Milestone 3: Run the loops adoption spike — *evidence, no release*

Use loops as the forcing consumer before designing a new renderer signature
or context type. The model deliberately deferred the signature to this
evidence; the spike collects it.

Work:

- Delete loops' duplicate Fidelity and flag-compilation machinery where the
  painted declaration grammar covers it.
- Record every adapter required to reuse a loops renderer through `run_cli`.
- Determine whether `(data, fidelity, width)` is sufficient in practice —
  the article lens's `fold_view(data, zoom, width, *, …) -> Block` is the
  first vote, for decomposed kwargs over a context object.
- Record where height is *offered* versus merely *known*.
- Identify content decisions that genuinely require render capabilities.
- Test whether optional rendering removes consumer code rather than moving
  it.
- Keep app-specific valued facets and acquisition policy outside painted
  unless another consumer demonstrates a general contract.

Exit criteria:

- loops no longer owns duplicate general-purpose Fidelity parsing.
- Its semantic renderers require no fabricated mode, TTY, or stream facts.
- The evidence needed to choose the canonical renderer signature is recorded.

## Milestone 4: Settle the semantic renderer contract — **0.11**

Choose the smallest canonical renderer boundary the adoption evidence
supports. It must be able to express: domain state, Fidelity, offered
allocation, render capabilities, ambient presentation policy. It must not
expose mode, TTY status, input streams, handlers, or delivery lifecycle.

Work:

- `run_cli` render becomes optional, defaulting to transcription — the
  no-lens graduate, ratified 2026-07-07 as the resolution of the
  transcribe-export question.
- Make the canonical renderer usable by static, in-place, and alt-screen
  live delivery.
- Provide an explicit compatibility path for legacy `render(ctx, data)`
  callables, with a documented migration story.
- Introduce a public `RenderContext` only if it removes repeated adaptation
  in more than one real consumer (the concept filter from RENDER_MODEL §6).
- Design doc: new renderer-contract document, written against the M3
  evidence; the capability vocabulary (M5) folds into the same document —
  capabilities are a renderer input, not a subsystem.

Exit criteria:

- In-repo and loops renderers use the canonical boundary.
- No semantic renderer dispatches on lifecycle or mode.
- Legacy behavior has a documented migration and compatibility story.

## Milestone 5: The capability vocabulary — **0.12**

Replace semantic-renderer reads of the `ctx.use_ansi` proxy with a narrow
capability vocabulary for content-carrier selection (color / glyph / link
facets). This decides RENDER_MODEL §7 Q3 by roadmap rather than by a third
consumer — accepted deliberately, and fenced: the vocabulary covers only what
raymarch and starmap demand, and it must not swallow the two existing
capability mechanisms (ambient `IconSet` glyph fallback, `ColorDepth`
serialization downsampling).

Work:

- Define the vocabulary; convert raymarch and starmap.
- Dissolve `ResponsiveSurface`'s fabricated `CliContext` — the live friction
  evidence the audit named.

Exit criteria:

- Capability-dependent content does not depend on the `use_ansi` proxy.
- No in-repo renderer fabricates context values.
- The vocabulary has not grown past its two consumers' demands.

## Milestone 6: Complete the interactive host rung — **0.13**

Add a Block-returning path around `Surface` while preserving direct Buffer
painting for applications that need the lower-level API.

Build the frame viewport adapter from existing primitives:

```text
Viewport state
+ vslice
+ short-content padding
+ host-authored scroll evidence
+ ref-aware coordinate translation
+ input routing
```

Implement the dual allocation contract:

- `height=None`: renderer returns natural-height content; the host owns the
  frame viewport and its evidence.
- `height=H`: the final renderer returns exactly `H`; the host does not crop
  it further.

Verify resize behavior:

- Width changes re-render.
- Omitted-height changes re-slice without requiring a semantic re-render.
- Offered-height changes re-render.
- Viewport offsets clamp when content shrinks.
- Hit testing translates delivery-frame coordinates back through the
  viewport.

The inward host-event seam is designed here, against the streaming/
interactive consumer app — and stays separate from `Surface.emit()`, which
remains an outward observation channel.

Design doc: new host-rung document absorbing `docs/VIEWPORT_DESIGN.md`,
residue swept in the same change.

Exit criteria:

- One reference renderer works through `print_block`, `InPlaceRenderer`,
  `StreamSurface`, and interactive `Surface` delivery.
- The renderer does not consume a full `CliContext`.
- Natural-height overflow is scrollable and visibly evidenced.
- Existing direct Buffer-painting Surface applications remain supported.

## Milestone 7: Close the honesty gaps — **0.14**

Remediate semantic decision points, not low-level clipping mechanisms. The
ownership rule governs: evidence is owed by the layer that knowingly chose to
discard, never by the mechanism that executed the cut. `Buffer.put()` and
`Block.paint()` remain silent mechanisms with explicit clipping contracts.

Work:

- Give the Surface frame viewport position and overflow evidence
  (`Viewport.can_scroll` is computed today, never drawn).
- Give `list_view` and `table` visible scrolling evidence.
- Mark or expose table column loss.
- Audit tree and flame semantic drops; preserve appropriate evidence.
- Decide whether default `Wrap.NONE` is sufficiently explicit to permit
  silent clipping.
- Every remediation lands with an evidence-focused test (extending the M1
  pins).

Exit criteria:

- No host or view knowingly discards requested semantic content without
  appropriate evidence.
- Primitive clipping behavior remains small, predictable, and policy-free.

## Milestone 8: Baselines and boundaries — **0.15**

Measure the stable pipeline and enforce the package structure that adoption
revealed — before the teaching pass describes either.

Performance (baseline, not optimization — the model's §6 defers budgets):

- Scenario baselines: cold imports, help, completion; domain state → content
  Block at multiple Fidelity levels; realistic composition trees; plain /
  ANSI / HTML / structured serialization; sparse and full Buffer diffs; host
  viewport composition; key input → flushed frame; representative large
  table, tree, traceback, dashboard.
- Record median and p95 latency, peak allocations, output bytes and write
  counts, changed-cell counts, frames over the live budget.
- Deterministic structural gates where timing gates would be unstable:
  completion imports no renderer or TUI modules (already built — pin it);
  unchanged frames emit no cell writes; one-shot delivery uses a bounded
  write count; live delivery does not accumulate obsolete frames; lower
  Fidelity avoids optional computation where the application permits.

Boundaries (coupling observed during adoption, not a speculative layout):

- Classify every package-root module by architectural responsibility.
- Replace the unrestricted root-layer exemption with explicit dependency
  rules.
- Extract a delivery subsystem only if host work created another sanctioned
  cross-layer seam.
- Preserve public facades; update the architecture module map and validate
  it against the filesystem.

If schedule pressure forces a cut, the scenario-baseline half trails to the
RC; the structural gates and dependency rules do not.

Exit criteria:

- 1.0 has a recorded scenario baseline and a repeatable comparison process.
- Inappropriate dependencies cannot hide in package-root modules.
- No representation rewrite is undertaken for speculative performance.

## Milestone 9: Validate and teach the progression — **0.16**

The docs edition: validate the model with the consumer lanes (now mature) and
rewrite the teaching materials around it. This absorbs the docs-unification
and marketing pass.

Work:

- Rewrite the README around the two monotonic axes (semantic authoring ×
  host capability).
- One progressive guide keeping the same renderer through:
  `paint value → define view → compose Block → choose host → add interaction`.
- Teach semantic renderer, content Block, host, and delivery frame before
  subsystem vocabulary.
- Single-source or generate the glossary (RENDER_MODEL §7 Q6) to prevent
  drift between the model, the consumer guide, and the site.
- Document the structured-format fork from the Block path, the doc-IR
  sibling-realization path, and the dual allocation contract with static,
  dashboard, and scrolling examples.
- Component height semantics declared per component by docstring convention
  (§7 Q4, the cheap resolution — a typed vocabulary stays deferred).
- Revisit every existing design doc with the same thoroughness that produced
  it — FIDELITY, COMPLETION, DIAGNOSTICS, ERRORS, VOCABULARIES, REFS, PAINT,
  PROMPTS, LIVE_DELIVERY, MOUSE, and the pattern docs — reconciled to the
  ratified model's vocabulary. The docs' job is prose that describes the
  library; provenance lives in the store.

Exit criteria:

- A fresh reader identifies the progressive renderer model without
  prompting.
- Both external-style consumers reuse renderers across delivery levels.
- Consumer feedback no longer exposes an unmodeled host or renderer input.

## Milestone 10: Freeze the 1.0 public contract — **0.17 → 1.0.0rc**

Audit every exported and documented name before the release candidate.

Decide and document:

- Stable public names and canonical import paths; whether any CLI or TUI
  APIs remain experimental, and whether unstable APIs move under an explicit
  experimental namespace.
- Removal of deprecated `show()` at the pre-declared 1.0 boundary.
- Removal of the pre-declared **id→ref deprecation aliases** from 0.7.
- Exception, exit-code, stream-discipline (stdout/stderr, closing the open
  thread), and terminal-restoration contracts.
- Typing guarantees and `py.typed` coverage.
- Supported Python versions, wheel contents, installation behavior.
- Compatibility policy for documented CLI and TUI APIs — a conventional 1.0
  does not remove or rename documented public APIs in a minor; any namespace
  retaining weaker compatibility is narrow and explicit.

Exit criteria:

- Every documented public name has an owner and stability classification.
- Both pre-declared removals are complete; grep loops/siftd/hlab first
  (consumers pin published painted).
- Public signatures match the progressive renderer model.
- No alpha-era compatibility language contradicts the 1.0 policy.

## Milestone 11: Release candidate and release — **1.0.0**

Ship at least one release candidate and exercise it in painted, loops, and
the external-style reference applications.

Release gates:

- The complete `./dev check` gate passes; built-wheel installation and
  import tests pass in clean environments; supported Python versions pass
  CI.
- Cross-host renderer equivalence tests pass.
- Terminal restoration, resize, and viewport tests pass.
- No silent in-place tearing remains.
- Performance baselines reviewed and recorded.
- README, guides, API reference, compatibility policy, and changelog agree.
- No unresolved 1.0-blocking deprecations remain.

After the RC has been exercised by the reference consumers, publish 1.0.0.
From then on, changes to the render model are explicit amendments to its
laws.

## Explicitly deferred beyond 1.0

The following do not block 1.0 without additional consumer evidence:

- The TUI application spine: keymap-as-data grammar, gesture maps,
  composition batteries (sectioned lists, suspend/resume).
- A public `RenderContext` type.
- Programmatic achieved-Fidelity reporting or a `RenderResult` type.
- A typed universal component-height vocabulary.
- General virtualization for unbounded subjects.
- A bidirectional replacement for `Surface.emit()`.
- Mark-persistence (marks surviving into artifacts as refs do — pressure
  toward one general cell-annotation channel; dissolution-test when it
  lands).
- `to_markdown` and further doc-IR publishers; fish/pwsh completion
  emitters.
- Comprehensive namespace or package reorganization beyond enforced
  boundaries.
- Native acceleration, packed Cell storage, or other speculative
  representation changes; a universal 60 fps guarantee.

## Critical path

```text
ratify render model            (done — merge residue)
    -> gate the laws                    ┐ (done)
    -> ship the semantic tree           ┴ 0.10 (built, on branch)
    -> loops adoption spike             (evidence)
    -> semantic renderer contract       0.11
    -> capability vocabulary            0.12
    -> interactive host rung            0.13
    -> honesty remediation              0.14
    -> baselines + boundaries           0.15
    -> teach the progression            0.16
    -> public API freeze                0.17 → rc
    -> 1.0.0
```

Consumer lanes run beside the path throughout and are allowed to reorder it:
that is what forcing functions are for. Work that does not strengthen this
path should be evaluated carefully before it is added to the 1.0 scope.
