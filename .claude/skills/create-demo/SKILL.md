---
name: create-demo
description: Add a demo to painted — pick the right tier, follow that tier's shape, wire it into the liveness list and the ladder. Use when asked to write, add, or port a demo, showcase, example, or pattern under demos/.
---

# Add a demo

Demos are the curriculum. The tier decides everything else, so pick it first
and let the rest follow.

## 1. Pick the tier — by test shape, not by subject

`demos/CLAUDE.md` has the table; the question it answers is *where does state
live and how do you test the lesson*:

| If the lesson is… | Tier | You write |
|---|---|---|
| one type or composition | `primitives/` | `demo()`, printed. No `main()`, no flags |
| a workflow, where the invocation IS the lesson | `patterns/` | `_fetch()` + `_render(data, fidelity, width)` + your own `run_cli` call |
| interaction — keys, selection, modal layers | `apps/` | a Surface app, tested via `TestSurface` |
| a miniature real application | `examples/` | same as apps |
| spectacle — full-screen, animated | `showcase/` | `_fetch()` + `_render` + `showcase_main` |

The line that matters most: **a pattern writes its own `run_cli` call because
that call is what it teaches. A showcase does not, because a showcase teaches
its output.** Don't harness a pattern's entry point, and don't hand-roll a
showcase's.

## 2. Follow that tier's shape

For **showcase**, read the two module docstrings rather than copying a
neighbour — they are the contract and they explain the *why*:

- `demos/showcase/_harness.py` — `showcase_main`, `ShowcaseArg`, `plate`.
  Declare each argument once; the harness spends it on both the parser and
  `--help`. Pass `doc=__doc__, file=__file__` explicitly.
- `demos/showcase/_plaque.py` — `Plaque`, `render_plaque`, `NOTE_TAG`, if the
  demo carries a maker's note. A note is named-only, capped, and signed; take
  `NOTE_TAG` itself, never a lookalike.

For every tier, the rules in `demos/CLAUDE.md` still apply — visual not
explanatory, own layer only, real-ish sample text.

## 3. Facets

Declare a `Tag` only for something that changes output at every depth it
claims. Two conventions the tests hold:

- a `stats` facet is `implied_at=3` (`-vv`)
- a maker's note is `NOTE_TAG` — named-only, implied at no depth

## 4. Wire it in

- add the name to the right list in `tests/smoke/test_demo_liveness.py`
  (`PRIMITIVES` / `PATTERNS` / `SHOWCASE`, or `APPS` with a key sequence)
- add a line to the ladder in `demos/CLAUDE.md`
- law tests go in `tests/unit/test_<name>_demo.py` — pin what the demo
  *claims*, never a decorative pose. `tests/CLAUDE.md` says which tier a given
  test shape belongs to.

No PEP 723 header. Demos run via `painted demos <name>` or `uv run
demos/<tier>/<name>.py` from a checkout; every loader puts the demo's own
directory on `sys.path`, so private siblings import cleanly.

## 5. Before committing

`./dev check` — all ten tiers. The liveness smoke will render your demo at
every zoom; `outputgen` will catch it if you changed a committed panel.

If you refactored an existing demo, prove it output-neutral rather than
asserting it: render every demo × depth × width × tag combination to a hash
before and after and diff. `tests/unit/test_showcase_harness.py` is the
precedent for what that buys.
