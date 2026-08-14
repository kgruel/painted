# Painted web redesign plan

Status: Wave 0 complete; Wave 1 ready
Scope: `web/`, its generated inputs, and the documentation/demo metadata needed to publish it  
Execution model: root agent owns judgment and integration; Sol and Terra agents implement bounded work packages

## Outcome

Rebuild the public site around Painted's strongest proof: one semantic rendering
model can produce static terminal output, progressive CLI disclosure, live output,
interactive applications, semantic web documentation, and recorded motion without
rewriting the underlying meaning.

The finished site should be useful in four distinct ways:

1. A new visitor understands Painted's purpose and sees genuine output quickly.
2. A learner can follow a progressive path from `paint()` through `Surface`.
3. An experienced user can enter through an orthogonal, task-shaped guide.
4. A prospective adopter can browse the full capability and demo catalog.

The site itself remains evidence. It should use Painted output wherever Painted
owns the representation, semantic HTML where the document tree owns the content,
and real recordings where time or interaction is the claim.

## Decisions held for the redesign

These are defaults for implementation. The root agent may amend them after seeing
working prototypes.

### Public information architecture

The primary navigation becomes:

- **Learn** — progressive paths through the library.
- **Guides** — orthogonal, task-shaped explanations.
- **Demos** — runnable curriculum, examples, and recorded showcase pieces.
- **Reference** — capability and API lookup.

`/walkthrough` becomes the conceptual foundation of `/learn`; it should not remain
a competing top-level content type. Existing `/docs/{slug}` pages are incorporated
into Learn or Guides rather than remaining orphan routes.

### Two progressive paths

Learn exposes two related spines:

1. The user-facing altitude path:

   `paint → compose → lens → CLI → live → Surface`

2. The implementation mental model:

   `Cell → Style → Span → Line → Block → Buffer → Lens → Surface`

The altitude path is the default. The implementation path explains the machinery
and cross-links to the matching altitude. Neither should be expanded into one
undifferentiated mega-tutorial.

### Orthogonal guide families

Initial guide taxonomy:

- Fidelity and disclosure
- Responsive width and composition
- Themes, palettes, icons, marks, and vocabularies
- Refs, denotation, mouse, and hit testing
- Live delivery and host behavior
- Focus, layers, cursor, and search
- Diagnostics and logging
- Prompts, help, and completion
- Testing, replay, and profiling
- Extending components, lenses, publishers, and hosts

Each guide declares which altitude rungs it applies to. Each Learn page links
sideways to relevant guides; each guide links back to the minimal prerequisite
point on a learning spine.

### Honest media lanes

The website uses four presentation lanes with explicit ownership:

| Claim being shown | Published form | Source of truth |
|---|---|---|
| Terminal cells and styling | `render_html` fragment | Painted `Block` |
| Document structure and prose | semantic HTML | Painted `Doc` tree |
| Time, animation, terminal delivery | MP4/WebM or GIF with poster | real demo recording |
| Navigation and browser behavior | Astro/HTML/CSS, minimal islands | website shell |

The cosmetic `PaintedSurface.jsx` recreation is removed from the public product
story once a real recording replaces it. Recordings complement generated HTML;
they never replace it as the drift-gated representation of static output.

Recording recipes should be reproducible. Generated media may be treated as
deploy artifacts or curated website assets, but the recipe, demo command, viewport,
duration, and poster-frame selection must be recorded in metadata.

### Provenance language

"Real output" remains a site-wide promise, but individual pages should not repeat
"real, not mock" on every card. Provenance belongs in a concise methodology note,
an unobtrusive specimen badge or tooltip, and the build/drift gates. User-facing
copy should lead with what a capability does.

## Target routes

The exact slugs may change during root review, but the first implementation should
target this shape:

```text
/
/learn/
/learn/altitude/
/learn/internals/
/learn/<step>/
/guides/
/guides/<slug>/
/demos/
/demos/<slug>/
/reference/
/reference/<capability-or-module>/   (optional in the first release)
/about/rendered-by-painted/
```

Legacy `/walkthrough` and useful `/docs/{slug}` URLs should redirect or remain as
compatible aliases when the deployment platform permits it.

## Homepage narrative

The homepage should fit the following sequence, with the first three sections
carrying the initial redesign:

1. A concise promise, install command, and Learn/GitHub actions.
2. A genuine short recording that moves one dataset through disclosure and
   delivery modes.
3. A compact monotonic-enhancement continuum made from real HTML specimens.
4. A capability map grouped by user problem rather than design-system category.
5. Selected demo films: a pattern, an interactive app, and showcase pieces.
6. Entry cards for Learn, Guides, Demos, and Reference.

The Painted wordmark remains part of the identity but no longer consumes most of
the first viewport. Motion or the monotonic continuum should supply the primary
visual payoff.

## Generated content model

The redesign should reduce hand-maintained imports and duplicate catalogs.

Create one website-facing manifest or generated index that can describe:

- stable slug and title
- content kind: primitive, pattern, app, example, showcase, guide, doc, specimen
- summary and capability tags
- progression/altitude position, when applicable
- related guide, API, demo, and source links
- runnable command
- static specimen identifier
- recording recipe and published media paths, when applicable
- provenance/source module

The manifest may be authored in Python beside demo/specimen discovery and emitted
as JSON for Astro. Do not make Astro parse Python source or infer pedagogy from
directory names alone. Existing demo discovery and `tools/outputgen.py` should be
extended or adapted rather than replaced by an unrelated registry.

The first implementation need not model every possible relationship. It must,
however, establish one authoritative route for demo/catalog metadata so the web
catalog and `painted demos` cannot silently become separate inventories.

## Capability coverage target

The reference redesign should account for at least these families, whether through
a specimen card, guide link, API entry, or explicitly documented omission:

- core cells, spans, lines, blocks, buffers, composition, borders, width, wrapping
- lenses and views
- tables, records, progress, meters, spinners, callouts, inputs, and lists
- palette, theme, icons, semantic marks, and vocabularies
- fidelity, budgets, formats, help, completion, and prompts
- refs, links, hit testing, mouse, cursor, focus, search, and layers
- static, live, stream-surface, and interactive delivery
- diagnostics, logging, traceback rendering, profiling, and testing
- document IR and HTML publishing

This is a coverage audit, not a requirement to produce a large bespoke panel for
every public name in the first pass.

## Wave 0 contract

Frozen by root review on 2026-08-13. Additive optional fields may be proposed by
an implementation package, but agents must not change these identities, ownership
boundaries, or route decisions without root review.

### Baseline evidence

- `npm run build` succeeds under Astro 6.4.3 and emits eight static pages:
  `/`, `/reference/`, `/walkthrough/`, `/walkthrough/fidelity/`, and four
  `/docs/{slug}/` pages (`completion`, `diagnostics`, `primitives`, `prompts`).
- `uv run python -m tools.outputgen --check` succeeds with the committed panels
  and Doc-IR fragments unchanged.
- Demo discovery finds 49 entries: 48 tiered demos (8 primitives, 16 patterns,
  8 apps, 5 examples, 11 showcase pieces) plus the root `tour`.
- The current reference registry contains 21 genuine Painted specimens; the
  Doc-IR registry contains four published documents.
- Desktop (1440×1000) and mobile (390×844) screenshots of the homepage,
  walkthrough, reference, and `/docs/primitives/` are captured under
  `/tmp/painted-web-wave0-baseline/`. They are local review evidence, not
  repository or release artifacts.

The visual baseline confirms the redesign targets: the homepage wordmark dominates
the first viewport; provenance copy is repeated; the reference is organized as an
old design-system gallery; and narrow layouts squeeze the global navigation and
clip wide code/specimen content. The existing semantic Doc-IR output remains a
strong foundation and should be restyled rather than flattened or rewritten.

### First-release routes

The new information architecture is canonical, but the first release uses rendered
compatibility pages rather than deployment-specific redirects:

```text
/
/learn/
/learn/altitude/
/learn/internals/
/learn/{step}/                 step = paint | compose | lens | cli | live | surface
/guides/
/guides/{slug}/
/demos/
/demos/{tier}/{name}/          tier = primitives | patterns | apps | examples | showcase
/reference/
/about/rendered-by-painted/
```

`/reference/{capability}/` remains optional and is not a Wave 1 dependency.
`/walkthrough/`, `/walkthrough/fidelity/`, and `/docs/{slug}/` remain buildable
compatibility routes in the first release. The new shell should point primary
navigation and progression links at the canonical routes. Host redirects can
replace compatibility pages only after the deployment platform is known; until
then, preserving useful URLs is more reliable than assuming redirect support.

Demo identity is always tier-qualified. The stable public identity is
`{tier}/{name}`, and the public route mirrors it. This avoids route instability
when two tiers contain the same filename. It also exposes an existing CLI defect:
`patterns/layers.py` and `apps/layers.py` both discover as `layers`, while the
current unqualified runner selects the first. The manifest must not claim an
installed command uniquely runs the app entry until discovery/dispatch provides a
unique selector; its checkout command remains publishable meanwhile.

### Website catalog schema v1

The generated website catalog lives at `web/src/generated/catalog.json`. It is a
deterministic build artifact: no timestamp, machine-specific absolute path, or
hand-authored HTML belongs in it.

```text
CatalogV1
  schema_version: 1
  demo_tiers: DemoTier[]
  demos: DemoRecord[]
  specimens: SpecimenRecord[]

DemoTier
  id: "primitives" | "patterns" | "apps" | "examples" | "showcase"
  order: integer

DemoRecord
  id: "{tier}/{name}"                 # stable identity
  tier: DemoTier.id
  name: string                        # runner/source name
  slug: string                        # initially equal to name
  title: string                       # human-facing, deterministic
  summary: string                     # current first docstring line
  source: repo-relative POSIX path
  command: string | null              # only if it uniquely selects this demo
  checkout_command: string
  invocations: string[]               # declared docstring examples
  has_main: boolean

SpecimenRecord
  id: string                          # current PANELS key
  fragment: "panels/{id}.html"
  source: repo-relative POSIX path
  render_as: "block" | "plain" | "json"
  width: integer
```

`painted._demo_discovery` remains the authority for demo membership and tier
ordering. The catalog generator consumes `discover_demos()`; it does not rescan
the tree independently. `tools.outputgen.PANELS` and its focused specimen
registries remain the authority for specimen membership. The current
`generated/docs/index.json` remains the Doc-IR registry and is not duplicated in
`catalog.json`.

The v1 catalog deliberately omits guide relationships, capability tags,
progression rungs, and media recipes. Those fields require curated declarations,
not filename inference, and may be added as optional fields only when a page or
recording workflow consumes them. Breaking field or identity changes require a
schema version bump. The outputgen check must cover the catalog and reject stale,
missing, or extra generated records.

### Acceptance checklist for delegated packages

- Generated truth: every tiered discovery entry appears exactly once; every
  published specimen traces to `PANELS`; generation is deterministic and
  drift-gated.
- Honest commands: a non-null installed command uniquely selects its record;
  checkout commands point at existing source files.
- Route integrity: the canonical routes build, compatibility routes remain, and
  primary navigation contains no placeholder or orphan destination.
- Honest lanes: terminal claims use generated fragments, document prose remains
  semantic Doc-IR HTML, and motion claims use recordings with a static fallback.
- Responsive fidelity: review at 390px and 1440px; the document must not acquire
  horizontal overflow, while intentionally wide cell grids scroll within their
  own specimen container.
- Accessibility: landmarks and heading order are coherent, keyboard focus is
  visible, navigation is operable, and motion respects reduced-motion settings.
- Low-runtime shell: Astro/HTML/CSS is the default; client JavaScript requires a
  concrete behavior that cannot be expressed by the static shell.
- Verification: relevant focused Python tests, the outputgen drift check, and
  `npm run build` pass; visual packages hand back desktop and mobile screenshots.

## Implementation waves

Only the root agent merges judgment-heavy decisions. Agents should not concurrently
edit the same files. Each work package ends in a clean handoff with changed files,
commands run, unresolved choices, and screenshots or generated artifacts where
visual review is required.

### Wave 0 — baseline and contracts

Owner: root agent

- Re-read this plan after compaction and inspect current git status.
- Capture desktop and mobile screenshots of the existing homepage, walkthrough,
  reference, and one doc-IR page.
- Record baseline build output and route list.
- Decide whether route migration uses redirects, compatibility pages, or preserves
  old slugs for the first release.
- Establish a short acceptance checklist and freeze shared types/JSON fields before
  delegating implementation.

Gate: no implementation begins until the manifest boundary and first-release route
set are explicit.

### Wave 1 — parallel foundations

#### Sol package A: catalog and generation architecture

Likely files: `src/painted/_demo_discovery.py`, `tools/outputgen.py`, new focused
tooling modules, generated JSON under `web/src/generated/`, relevant tests/docs.

Deliver:

- A proposed and implemented website manifest schema.
- Generation from existing first-party demo/specimen declarations.
- Stable relationships for tier, command, description, source, and available
  specimen/media fields.
- Drift checking integrated into the existing outputgen tier.
- Unit or cohesion tests that prevent demo inventory divergence.

Constraints:

- Do not redesign page markup or global CSS.
- Do not create a second demo-discovery authority.
- Keep generated files deterministic and reviewable.

Root review: schema semantics, ownership boundary, compatibility with future guides,
and whether every field is earned by a current consumer.

#### Terra package A: site shell and design prototype

Likely files: `web/src/layouts/`, `web/src/styles/`, new reusable Astro components,
and a prototype route that does not replace the live homepage yet.

Deliver:

- Responsive shell with Learn / Guides / Demos / Reference navigation.
- Shared page-header, specimen, media, card, and cross-link primitives.
- A homepage prototype using existing generated specimens and a media placeholder.
- Desktop and mobile screenshots.

Constraints:

- Do not edit generator or discovery code.
- Keep JavaScript optional; use Astro and CSS unless behavior requires an island.
- Preserve JetBrains Mono glyph coverage and exact cell-grid rendering.
- Do not permanently remove the current homepage before root visual review.

Root review: hierarchy, density, visual tone, mobile overflow, and whether the design
feels like a website made with Painted rather than a terminal-themed template.

### Wave 2 — navigation and primary experiences

Starts only after root accepts the Wave 1 schema and shell.

#### Sol package B: Learn and guide publishing

Deliver:

- `/learn` landing and the two progressive spine representations.
- A guide index driven by declared metadata.
- A reusable guide layout with prerequisites, applicable altitude, related demos,
  and next/previous progression.
- Migration of existing guide content without duplicating its source of truth.
- Incorporation or routing of the existing generated doc-IR pages.

Constraints:

- Preserve semantic HTML for prose.
- Figures that claim Painted output must use generated fragments.
- Avoid rewriting all guide prose during the structural pass; flag stale content
  for root editorial judgment.

Root review: pedagogy, naming, sequencing, cross-links, and conceptual accuracy.

#### Terra package B: homepage implementation

Deliver:

- Final homepage using the accepted shell.
- Smaller wordmark and concise first-screen product statement.
- Real-media component with poster, motion preference, accessible fallback, and
  no autoplay behavior that harms usability.
- Monotonic continuum from actual generated fragments.
- Capability preview and four destination entries.
- Removal of the cosmetic React surface from homepage usage after the recording
  path is functional.

Constraints:

- Reuse shared components accepted in Wave 1.
- Do not hand-copy generated terminal markup.
- Keep the page useful when video is unavailable or reduced motion is requested.

Root review: final copy, choice of hero recording, viewport composition, and removal
of any repeated provenance/apology language.

### Wave 3 — demos and reference

#### Terra package C: demo gallery and detail pages

Deliver:

- `/demos` grouped by learning role: primitives, patterns, apps, examples, showcase.
- Filters or compact navigation only if the catalog size demonstrates a need.
- Detail pages with command, source, related concepts, static output, recording,
  and controls where metadata exists.
- Responsive media presentation and poster loading.

Root review: which demos deserve recordings, editorial ordering, and whether the
gallery teaches the tier distinctions without exposing test-infrastructure jargon.

#### Sol package C: reference coverage and generation

Deliver:

- Capability-oriented reference taxonomy replacing Components/Colors/Spacing/Type/
  Brand as the primary grouping.
- Coverage report against the families listed above.
- Generated data feeding reference cards and links.
- Static specimens for high-value missing capabilities where the existing tooling
  can produce them honestly.
- Explicit omissions for capabilities that require motion, events, or prose rather
  than fabricated static output.

Root review: public API boundaries, completeness claims, grouping, and which missing
specimens are worth maintaining.

### Wave 4 — recording set and integration

Owner: root agent with bounded Terra/Sol follow-ups as needed.

- Choose a small initial recording set; do not record every demo.
- Produce the homepage continuum recording first, then selected pattern/app/showcase
  recordings.
- Inspect representative frames for color, clipping, dimensions, and meaningful
  motion.
- Wire actual media metadata into the manifest.
- Remove dead React/CSS assets once nothing imports them.
- Resolve legacy routes and internal links.
- Run full visual, accessibility, generated-output, and build review.

Suggested initial media set:

1. Homepage: one dataset across quiet/default/verbose/live/interactive modes.
2. Pattern: responsive or fidelity.
3. App: focus form, layers, or widgets.
4. Showcase: harmonograph plus one of starmap/raymarch/mandelbrot.

Gate: recordings must show a capability that static HTML cannot. Decorative motion
alone does not justify an asset.

### Wave 5 — polish and release readiness

Owner: root agent

- Editorial pass for terminology shared with README and public API.
- Verify install commands, demo commands, source links, and API names.
- Audit keyboard navigation, landmarks, focus visibility, captions, reduced motion,
  and contrast.
- Test at representative narrow, tablet, and desktop widths.
- Confirm no fixed cell specimen silently overflows its intended container.
- Check route metadata, titles, descriptions, favicon, social preview, and 404.
- Run the repository's relevant Python gates plus `npm run build` in `web/`.
- Review generated diffs and ensure no hand-edited generated artifact exists.

Deployment is a separate user-approved action and is not implied by this plan.

## Orchestration protocol

After compaction, the root agent should use agents in waves rather than opening all
work at once.

1. Root restores context from this file, inspects the worktree, and completes Wave 0.
2. Spawn Sol A and Terra A concurrently with narrow file ownership.
3. Review both outputs locally; root makes or requests corrections before integration.
4. Spawn Sol B and Terra B concurrently only after shared contracts are stable.
5. Continue through Waves 3–5, reusing an existing agent for follow-up when its
   context is valuable and its file ownership remains coherent.

Agent prompts must include:

- the exact work package and non-goals
- files or directories the agent owns
- files it must not edit
- required verification commands
- expected handoff format
- instruction to preserve unrelated user changes

The root agent retains:

- information architecture and naming decisions
- public product claims and editorial voice
- visual acceptance and choice among prototypes
- schema approval and source-of-truth boundaries
- cross-package integration
- final tests, cleanup, and completion judgment

Sol should preferentially receive work involving Python architecture, generation,
schema invariants, drift gates, and cross-layer integration. Terra should
preferentially receive Astro components, layouts, responsive styling, page assembly,
and bounded content presentation. Either model may receive a corrective task when
the work is concrete and the root supplies the judgment already made.

## Verification matrix

| Area | Required evidence |
|---|---|
| Generated truth | `outputgen --check` or the repository command that contains it |
| Python changes | focused tests plus the relevant `./dev check` tiers |
| Web compilation | `npm run build` from `web/` |
| Routes | generated route list and internal-link check |
| Desktop visuals | screenshots of home, Learn, Guides, Demos, Reference |
| Mobile visuals | the same key routes at a narrow viewport |
| Cell fidelity | box drawing, wide glyphs, fills, wrapping, and horizontal overflow inspected |
| Media | poster, fallback, reduced motion, dimensions, color, and meaningful frame progression inspected |
| Accessibility | landmarks, heading order, keyboard operation, visible focus, captions/labels |
| Content integrity | commands and API names verified against current code |

## Completion criteria

The redesign is complete when:

- The first viewport communicates the product and shows genuine Painted behavior.
- No public page relies on the cosmetic PaintedSurface recreation.
- Learn, Guides, Demos, and Reference are all reachable and meaningfully populated.
- The two learning spines and orthogonal guides cross-link coherently.
- Demo and reference catalogs consume generated authoritative metadata.
- Static output, semantic docs, and recordings use their appropriate honest lanes.
- The capability audit has no silent omissions; deferred items are recorded.
- Desktop/mobile visual review and relevant build/test gates pass.
- The root agent has completed a final editorial and architectural review.

## Deliberate non-goals for the first release

- Running a true interactive terminal emulator in the browser.
- Recording every demo.
- Building a bespoke API page for every exported symbol.
- Rewriting all existing documentation before the new structure is proven.
- Adding search before route structure and content metadata stabilize.
- Deploying the site without an explicit deployment request.
