---
name: friction-fix
description: Take a store friction from triage to merged fix on main — verify against the current tree, rule the design question with Kyle, fix on a branch, /simplify with worktree agents, external codex review, merge, changelog line, resolution emits, file deferrals. Use when asked to fix, work, or resolve a friction from the loops store, or to run the friction-fix flow.
---

# painted Friction → Merged Fix

Ported from siftd's issue-fix skill after one validated run (the cli-errors-
stderr arc, 2026-08-13). The flow: **triage → rule → branch → fix →
`/simplify` → `codex review` → merge → changelog → resolve in the store →
file deferrals → name what's next.** Each stage catches something the previous
one missed; don't skip the external review because the internal one came back
clean — they find different classes of thing.

painted has no GitHub issues or PRs: frictions live in the loops store, the
four-heading body lives in the *resolution emit*, and the merge commit keeps
the repo's existing 2–4 line convention.

## 1. Triage — is it real, on the current tree?

```bash
sl read project --kind friction --plain
```

Then **reproduce it yourself** against the working tree, and read every file
and commit the friction names. Produce before writing any code:

- The failure, triggered locally (separate the streams: `>out.txt 2>err.txt`
  for routing claims).
- The **actual mechanism** — consumer-workaround frictions carry the
  consumer's diagnosis, which is often subtly wrong even when the symptom is
  real. On cli-error-multiline-flattening the loops commit blamed
  `Block.text`; the runner's own `replace("\n", " ")` was the primary
  flattener. A corrected mechanism changes the right fix — record the
  correction in the resolution emit.
- **Re-measure every count the friction states** — it was true the day it was
  written; arcs since are what stale it.

For a consumer-workaround friction, read the workaround commits in the
consumer's repo (`cd ~/Code/strange-loops && git show <hash>`) so "sweep the
residue" is concrete. Note: loops pins *published* painted, so the sweep can
only land when loops next bumps — record it as open residue in the resolution
emit, don't chase it now.

If invalid or already fixed, say so, fold the friction with the evidence, and
stop. Don't build.

## 2. Rule the design question first

A friction that poses a question ("should X, or Y?") gets Kyle's ruling
*before* the branch — and emit it:

```bash
sl emit project decision topic=practice/<slug> --strict --stdin message < msg.txt
```

`sl emit` takes positional `[vertex] <kind> KEY=VALUE ...` — **not**
`--kind/--topic` flags. Frictions fold by `name=`, decisions by `topic=`.
Write prose bodies to a file or quoted-delimiter heredoc and pipe via
`--stdin message`.

While implementing, watch for the case the ruling didn't see (the --json
error-object path wasn't in the stderr ruling). Surface it as one question —
recommended option first — rather than silently widening or narrowing the
ruling.

## 3. Branch and fix

```bash
git checkout -b fix/<short-slug>
```

Never commit on `main` (the changelog line in §7 is the one sanctioned
exception). Commit as work goes green; **push only on Kyle's explicit ask**.

- Check the seam for an existing precedent before inventing one — the refusal
  seam had already ruled errors-belong-on-stderr; the fix *extended* §8 rather
  than adding a second contract. Cite the design doc, don't restate it.
- Scope the claim: if a route legitimately stays outside the new invariant
  (the in-place live region), narrow the documented claim and name the
  exception at its sites — don't widen the fix to make the sentence true.
- **Write the test that would have caught it, then falsify it both ways** —
  mutate the fix (back the file up with `cp` to the scratchpad, never
  `git checkout <path>`, which restores HEAD and wipes uncommitted work),
  confirm red, restore, confirm green.
- Update the docs residue in the same change: folder-guide invariants live in
  `src/painted/*/README.md` (CLAUDE.md is a **symlink** — edit the README
  target, the Edit tool refuses the symlink path).

## 4. Green

```bash
./dev check     # the full 10-tier gate; must pass before any commit
```

No lanes to choose — the staircase is the whole gate. Pyright noise in the
IDE is not the gate; `ty` + `ruff` inside `./dev check` are.

## 5. `/simplify` — four worktree agents

Commit first. Launch all four (reuse / simplification / efficiency /
altitude) in one message with `isolation: "worktree"`, using
`references/simplify-agents.md` — copy the preamble verbatim. painted
specifics the preamble carries:

- **No push needed**: worktrees share local refs, so agents check out the
  local branch. Give each agent a **unique** review branch name
  (`review-<angle>`) — two agents collided on a shared `review-local` in the
  first run.
- End every prompt with the anti-idle line ("your final message is data for
  the orchestrator") — painted's spawns hit silent idle without it
  (friction:subagent-silent-idle).

Dedup findings across agents (two agents finding the same thing independently
is the strongest signal), apply what survives in the real tree, re-run
`./dev check`, commit. Skip findings needing changes well outside the diff
but **record them** — they become filed frictions in §8.

## 6. `codex review` (external)

```bash
codex review --base main -c model="gpt-5.6-sol" -c model_reasoning_effort="medium"
```

Verify each finding yourself before acting; disposition pre-existing
conditions with evidence, not assertion. Stop when a pass returns only
dispositioned items — deferred-with-reasoning is a valid terminal state.

## 7. Merge and changelog

```bash
git checkout main
git merge --no-ff fix/<short-slug> -m "Merge fix/<short-slug>: <what it does>

<2-4 lines: the defect, and anything the review pass changed.>"
./dev check                      # on main, before anything else
git branch -d fix/<short-slug>
```

Then the changelog line, **after** the merge so it can link the merge hash —
a small docs-only commit on main (the sanctioned exception; the tier-0
ratchet checks the shape). If `## [Unreleased]` doesn't exist (fresh after a
cut), create it above the newest version heading:

```markdown
- **What the user can now do (or stop hitting).** One clause of scope; state
  a behavior change plainly. ([<merge>](https://github.com/kgruel/painted/commit/<merge>))
```

Push only when Kyle says push.

## 8. Resolve in the store, file deferrals

The resolution emit is the durable four-heading body — Defect (mechanism as
verified, corrections called out) · Scope (what changed, the stated
exceptions, ruled decisions cited) · Evidence (repro, red-verified counts,
gate state, review outcome) · Residue (what stays open, and its trigger):

```bash
sl emit project friction name=<friction-name> status=resolved --strict --stdin message < msg.txt
```

File each deferral as its own friction (`status=open`), decomposed by
*cause* — one absence with N sites is one friction naming the absence. A
recurring pattern at its Nth site is a promotion signal; say what would
promote it and what that costs (core surface is semver-MAJOR — mint
deliberately).

## 9. Name what's next

Rank the remaining open frictions by **who is currently getting a wrong
answer** (silent wrong result → broken capability → vacuous safety net →
internal coherence), then apply the two overrides and say which you used:
recorded sequencing, and **context heat** — a friction adjacent to what you
just touched is cheapest now.
