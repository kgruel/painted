---
name: build-slice
description: Dispatch an implementation slice through subtask with the ratified model tiers and standing sol review. Use when implementing a planned slice or stage of a design arc, dispatching implementation work to workers, or asked to build S<N> of a plan.
---

# Build a slice via subtask

Standing process, ratified by Kyle 2026-07-12 (store: `decision
design/renderer-contract-ratified`; refinements:
`observation workflow/subtask-slice-lessons`). Implementation goes through
**subtask** workers in isolated worktrees — not inline edits — with fixed model
roles per stage. Field-validated on the 0.11 S1–S5 walk (5 slices, 5/5 initial
review HOLDs caught real defects, all merged same-day).

## Model roles (fixed)

| Stage | Adapter/model | Fit |
|-------|---------------|-----|
| Plan + implement complex slices | claude **Opus / high** | design-sensitive stages, cross-module seams — and anything touching **lifecycle or scope semantics**, even when it looks spec-complete (Sonnet took 3 rounds on exactly that class: kept caching where the spec meant per-event evaluation) |
| Generate/fixed mechanical tasks | claude **Sonnet / medium** | well-specified, spec-in-hand, no judgment calls |
| Standing review on **every** task | codex **gpt-5.6-sol / medium** | cross-model-family review catches bug classes same-family review misses — 3+ arcs of evidence (store: `observation practice/cross-model-review`) |

## Mechanics

- From Claude Code, always dispatch with the env var unset:
  `CLAUDECODE= subtask send <task> "..."` (so the nested session doesn't detect a
  parent).
- `subtask ask --follow-up <session>` does **not** inherit adapter/model — respell
  `--adapter codex --model gpt-5.6-sol --reasoning medium` on every re-review.
- Review loop that works: sol reviews **in the worker's worktree** (cd to the
  workspace, `subtask ask`); findings go back to the worker via `subtask send`
  with concrete fix directions; re-review via `--follow-up` in the *same* sol
  session so it verifies its own findings.
- Before `subtask merge`: confirm the worker **committed** — sol reporting "HEAD
  equals base, reviewed the working diff" is the tell. Send
  `subtask send <task> "Commit your changes."` first.
- After each merge: `./dev check` on the branch before dispatching the next slice.

## Authorization and wording

- **Standing merge authorization** (Kyle, 0.11 S3): a slice that finishes to spec
  and passes review with no judgment questions merges and the pipeline keeps
  walking — no per-merge sign-off. Judgment questions still stop for Kyle.
- **Dispatch wording is load-bearing**: state the *intended behavior*, not the
  defensive gesture. "Guard width=None at each entry point" got built as
  `width or 80` — the exact fabricated fallback the contract deletes. Say "pass
  None through; natural sizing".
- Workers routinely idle without sending a final report — instruct "report before
  going idle" and nudge on idle; an idle notification is not a deliverable.
