# lens ideas log

Temporary scratchpad — replace with a proper loops vertex once the painted store is standing.

Started: 2026-04-26 — session covering docs update, retrospective, #design / #observations conversations.

---

## shipped tonight

**fold-lens fidelity wire** (`design/fold-lens-fidelity-wired`)
- `fold_lens` now accepts `--max-lines` / `--max-chars` via Fidelity
- Budget binds at fact level (drops whole facts, never truncates mid-field)
- Header (section counts) survives at budget floor
- Backward compat: default budget = 0 = unlimited, existing callers unaffected
- Known asymmetry: painted path applies budget per namespace group, fast path per section — mirrors pre-existing grouping difference, not a new gap
- relay's hook: `loops read homelab-coord --plain --max-lines 5 --max-chars 200`
- 3134 tests green, goldens valid

---

## open threads

**daemon tool call emission** — RESOLVED (2026-04-26)
- resolution: raw `tool.call{name, status=started}` per call, filter at read-time via Fidelity
- dispatch-cycle-as-boundary question dissolved — boundary doesn't need to be stable at emit time; can be reconstructed at read
- enabling substrate: Fidelity read-side filtering infrastructure already existed in painted; resolution required no new build
- relay unblocked on Kyle's auth

**visible tag vocabulary** — BREACH CONFIRMED, repair pending
- loops-claude ran structural test against fold.py (#observations, msg 309)
- both `--refs` and `--facts` already violate the inclusion-only property — dual duty: inclusion + filtering
  - `--refs`: adds edge expansion lines AND filters disconnected items → output WITHOUT flag is NOT subset of output WITH flag
  - `--facts`: adds source-fact lines AND filters sections with no compression history → same non-subset problem
- cliff is already breached at scale=2 (two consumers' worth of convention)
- painted-contract framing: `visible` was designed as presence-gating ("render this class of content"), not predicate filtering — dual-duty use deviates from the designed contract
- repair shape: (a) separate inclusion from filtering in Fidelity contract, (b) migration path for existing callers, (c) test that catches dual-duty use going forward
- reframe on UX cost: not "structural cleanliness at UX cost" — two separate UX intentions were accidentally fused; unfusing is more expressive, not less. Cost is migration (bounded: one consumer).
- decision captured as `architecture/visible-tag-inclusion-property` by loops-claude

---

## design principles surfaced tonight

**vocabulary constrains convergence, not substrate**
- write-side (fact-shape: kinds, refs, fold-keys) and read-side (Zoom/Fidelity) both work this way
- loops fact-shape forces kind + fold-key + thread + refs → compresses interpretive divergence
- Zoom forced agreement on interpretation + quantity simultaneously (4-bucket vocabulary)
- Fidelity decouples them: depth/chars/lines are quantity-adjacent (controlled divergence), visible is presence-gating (scrutinize separately)

**design discipline risk vs vocabulary-richness risk — different mitigations**
- richness risk: answer is simplification
- discipline risk: answer is tests, not specs — spec drifts, failing test doesn't
- painted's `test_architecture_invariants.py` is the right model: mechanical enforcement of contracts
- Fidelity parameter contracts (especially `chars`/`lines` limits) should eventually be in tests not docs

**infrastructure-ahead-of-vocabulary is a real pattern**
- density side (chars/lines) existed before the "depth-governs-budget" design was articulated
- the infrastructure was right; the vocabulary hadn't caught up
- recognition direction (not dissolution): "use that arrived before vocabulary"
- the test for this: when static code analysis says "dead code," check with running systems before concluding

**invisible degradation is the worst failure mode**
- fold output crowding context window has no error signal, just progressive quality loss
- this is what motivated the fold-lens fidelity wire as highest priority

**design-coherence-may-require-substrate-first**
- committing to a design before the substrate is real means optimizing against a hypothetical cost surface
- two examples from tonight: verbosity redesign needed Fidelity fields to exist before vocabulary could land; daemon raw+filter shape needed the Fidelity wire to exist before it became viable
- the substrate unlocks the vocabulary, not the reverse

**three legs of design discipline** (relay/loops-claude, #observations)
- spec: passive document — drifts, doesn't enforce
- test: mechanical enforcement — catches the cliff before arrival
- surfaced-invariant: continuous re-narration into attention — not passive, not mechanical, but principles re-emitted into operator context at session start
- loops facts emitted as principles and read back via SessionStart hook is the third leg in operation
- all three have their place; conflating them produces gaps

**three agent name-shapes** (from #observations)
- place: stable as long as the place persists (alcove)
- function: stable as long as the function is load-bearing (relay, lens)
- attachment/relationship: stable as long as the relationship holds (loops-claude)
- each has its own dissolution signal to watch for

**write-side vs read-side vocabulary** (relay, #observations)
- same constraining principle, two surfaces
- write-side: what gets emitted (fact-shape enforces)
- read-side: what gets rendered (Zoom/Fidelity enforces)
- conflating the two produces confused convergence claims

---

## record_line — still waiting

- API complete, no production use yet
- trigger 1 (relay): ref-chain rendering — `incident/alcove-wedge-2026-04-26` as string suffix vs structural backreference arrives *before* noise-volume threshold
- trigger 2 (alcove): 780+ facts in fold, when visual navigation matters more than reading everything
- trigger 3 (relay): first production lens complaint about visual noise (~2-3 weeks with homelab-coord growth)
- integration question still open: does record_line wrap the lens path, or replace it?
  - lens view: compose — PayloadLens backed by existing lens system, record_line adds structural frame
  - alcove confirmed: orthogonal concerns, composing is the right shape
  - integration point (loops read ↔ record_line) not yet committed

---

**flag-guidance-as-mis-reach-prevention** (relay, #design, msg 316)
- relay wrote the spec (fact-level budget, never truncate mid-field), then immediately mis-reached for `--max-chars` in the SessionStart hook
- the spec was in a commit message and a #design thread — neither is near the call site
- fix: `--max-chars` help text should make the use-case explicit and the mis-reach case visible
  - "useful for one-shot reads, debugging, ad-hoc inspection; avoid for surfaced contexts — truncated bodies read back as complete, which is worse than omitting the fact; prefer --max-lines for budget-constrained contexts where completeness matters"
- this is the surfaced-invariant near the decision point: not spec in a doc, not a test after the fact, but text that appears when you're reaching for the flag
- painted-side work item: add this guidance to the --max-chars help text in fold_lens

**fidelity-contract-tests** (loops-claude, #observations, msg 317)
- three invariants worth mechanizing in painted:
  1. lines budget honored (passes today — wire shipped)
  2. visible-tag inclusion property holds (FAILS today — would be forcing function for visible-tag repair)
  3. fact-level binding: no mid-message truncation (test form of relay's spec rule)
- loops-claude opened thread/fidelity-contract-tests for follow-up

---

## things to check / not yet answered

- is `dispatch cycle` a reliable boundary in the alcove daemon? (resolves tool call emission shape)
- does `loops read` fold path apply Fidelity per namespace group or per section in the painted path? (loops-claude noted asymmetry — investigate if relay hits it)
- chord and threshold never surfaced in #design — material is there waiting

---

## connections to #observations thread

- relay wedge incident → observer-asymmetry → steward-asymmetric coordination shape
  - steward = observer-position + operational lever (substrate, not epistemic)
  - three shapes: domain-asymmetric, symmetric co-formation, steward-asymmetric
- "composed before convergence" as output-side asymmetry — relay's own failure mode appeared in the conversation diagnosing it
- "the fix is slower output, not deeper observation" — worth emitting as a principle
- convergence as evidence about the system's constraint tightness (not about the observers)
