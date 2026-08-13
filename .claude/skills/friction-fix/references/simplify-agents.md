# `/simplify` agent prompts (painted)

Read this when launching the four review agents. Copy the preamble verbatim
into each prompt and append that agent's angle. Launch all four in one message
with `isolation: "worktree"` so they run concurrently.

**Commit the branch first** (no push needed — worktrees share local refs).

## Shared preamble

Substitute `<ANGLE>`, `<angle-slug>`, `<branch>`, and a one-paragraph
`<context>` describing what the change does.

```
You are reviewing a diff in the painted repo (/Users/kaygee/Code/painted) for
**<ANGLE>** issues only. Quality review, NOT bug hunting.

FIRST, run these literally — your worktree may not start on the branch:
git checkout -B review-<angle-slug> <branch>
git diff main...HEAD
(local refs; do NOT fetch or push. The branch name must be unique to you —
sibling reviewers hold their own.)

TIME BUDGET: finish well under 10 minutes. Return partial findings rather
than nothing. Do NOT run ./dev check or the full suite; a targeted
`.venv/bin/python -m pytest <file> -q -n 0` in the main repo's venv is fine.

CONTEXT: <context>

YOUR ANGLE — <ANGLE>: <angle body, below>

<3-5 bullets of "specifically worth checking", named files and functions from
this diff. These separate a review that finds something from generalities.>

Report each finding as: file, line, one-line summary, and the concrete cost.
Return findings as text — do not fix anything. Your final message is data for
the orchestrator: always end with your findings (or "no findings"), never go
idle without reporting.
```

## The four angles

**Reuse** — Flag new code that re-implements something the codebase already
has; name the existing helper. Grep core/compose.py, views/, root modules,
and files adjacent to the change. Also ask: is this the Nth hand-rolled copy
of a pattern — where are the others?

**Simplification** — Flag unnecessary complexity the diff *adds*: redundant
or derivable state, copy-paste with slight variation, dead code, residue left
by something the change dissolved (stale docstrings, orphaned parameters,
comments describing the old behavior — grep for the old mechanism's words).
Name the simpler form.

**Efficiency** — Flag wasted work the diff introduces. Weigh by path
temperature and say so (an error path is cold by definition). painted's
function-local renderer imports are the mandated cli→renderer boundary
pattern, not a finding. Add: *"If you benchmark, say exactly what you
measured and how. Do NOT report a speedup you cannot reproduce twice, and
beware warm-cache contamination."*

**Altitude** — Is each change at the right depth, or a fragile bandaid? Give
it the repo's stated principles (the honesty rule, the dissolution test,
scope-the-claim, the three planes, semver-stable core vs evolving cli/tui)
and ask it to **argue both sides** of each placement question, then give a
verdict. Ask specifically: does any documented claim now overclaim what the
code does — is there an un-funneled path the new invariant's sentence
pretends to cover?

## What to expect back

- Findings are text; you apply them in the real tree. Anything an agent
  "fixed" in its worktree is discarded — which is what you want.
- Reproduce any measurement yourself before citing it.
- Two agents finding the same thing independently is the strongest signal in
  the pass (reuse + simplification both found the triplicated stderr gate on
  the first run).
- A finding can correct your *reasoning* rather than your code — a claim
  documented wider than it is true. Fix the claim, and hold the replacement
  wording to the same test.
