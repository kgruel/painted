---
name: design-arc
description: Run a painted design arc — mint or amend a design doc, deliberate through the store, ratify with Kyle, flip status at ship. Use when designing a new contract or feature, amending a design doc, running design review rounds, or closing a design arc at release.
---

# Design arc discipline

Ratified practice (store: `decision practice/design-doc-discipline` +
`practice/docs-authoritative-store-operational`, Kyle 2026-07-10). The rule in one
line: **no build without a ratified design doc** — and the doc, the store, and the
evidence each carry a different register.

## The register split (template: the render-model arc)

| Register | Home | Carries |
|----------|------|---------|
| Contract | `docs/*_DESIGN.md` | the normative design — describes the library, tight |
| Deliberation | the loops store (`project` vertex) | decisions, rulings, history (fold upserts preserve lineage) |
| Evidence | an audit doc or appendix (e.g. `RENDER_MODEL_AUDIT.md`) | commit-pinned, reproducible verification |

## Rules

1. **Amend before mint.** If a lane already has a design doc, amend it — and sweep
   the residue (stale prose, superseded claims, dead pointers) in the same change.
   A new document only for a genuinely new contract (renderer contract, host rung
   were; most things aren't).
2. **Evidence-gated timing.** Write the design doc *after* its evidence gate — a
   spike, a trace, a consumer audit (the renderer-contract doc came after the
   loops-adoption spike). Never speculatively upfront; that's the speculative
   design the render model itself warns against.
3. **Status vocabulary**: `PLANNED → RATIFIED (Kyle, dated) → IMPLEMENTED` (flipped
   at ship — a release-skill precondition). Ratification is Kyle's call, explicit
   and dated, recorded in the doc header and the store.
4. **Honesty in prose**: never state unshipped behavior in present tense — the doc
   describes what is, the store describes what's intended.

## Cadence

- **Open the arc**: a store `thread` (`name=<arc> status=open`). Open investigations
  are `trace` kind, iterating deliberations `design` kind
  (store: `design:practice/work-pipeline-kinds`) — link with generic `ref=`, not
  typed edges.
- **Deliberate**: review rounds before ratification. Include a **cross-model-family
  pass** (codex/sol) — it repeatedly catches bug classes same-family review misses
  (store: `observation practice/cross-model-review`). Big contracts have used
  adversarial multi-agent passes; every ruling lands as a
  `decision topic=design/<thing>` with rationale.
- **Ratify**: Kyle rules; record the ruling + date in doc and store.
- **Build**: dispatch via the `build-slice` skill.
- **Ship**: flip the doc status, amend the store's `roadmap`/`decision` nodes —
  then the `release` skill takes over.
