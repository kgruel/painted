# painted.cli — the CLI framework

Argument parsing, context detection, mode dispatch, help, completion, prompts,
and lifecycle. The framework that turns user intent (`-v`, `--json`, a pipe, a
TAB press) into a call on the renderer. Start at Level 0; escalate on a trigger.

**You are here** — on top of the renderer, one contract away from it:

```
Cell / Block / compose / lenses     ← the renderer (core/, views/): data → cells
        │  Block  (the one contract between the two concerns)
        ▼
run_cli / CliRunner / detect_context ← this folder: intent → a delivered Block
```

The renderer turns data into cells and knows nothing about argv, modes, or
TTYs. This folder connects the two. See root `CLAUDE.md` Level 1 ("Two concerns,
one contract") for the split, and `src/painted/CLAUDE.md` Level 2 for the
consumer's-eye view of `run_cli`.

<!-- docgen:begin frag:stability-tiers#summary -->
`painted.core` + `painted.views` + `painted.display` + `painted.publish` are the **semver-stable** library surface (removing or renaming an `__all__` name is semver-MAJOR, guarded by `tests/unit/test_public_api.py`); `painted.cli` + `painted.tui` are the **evolving** framework surface that may change across minor versions.
<!-- docgen:end -->

**This half evolves.** Unlike `core`/`views`/`display`/`publish`, `painted.cli`
may change across minor versions. It *calls you* (renderer, fetch, handlers), so
its surface churns as apps' needs change. Don't pin app code to internals here
the way you would to `Block`.

---

## Level 0 — The boundary rule (read before touching anything)

**Trigger**: I'm about to add an import or a module to `cli/`.

Two hard rules govern this folder. Both are gate-enforced, and breaking either
is the fastest way to fail `./dev check`.

1. **`cli/` must not import `views/` (or anything that pulls the renderer) at
   module top.** The framework reaches the renderer only through **lazy imports
   inside functions**. This is why two modules that *look* like they belong here
   live at the package root instead:
   - `_transcription.py` — `run_cli`'s default renderer. It imports `views`, so
     it can't live in `cli/`; `runner.py` imports it lazily at dispatch.
   - `_prompt_cell.py` — the raw-mode (CELL rung) prompt renderer. Same reason:
     it imports `views`, so it sits at root and `prompts.py` reaches it lazily.

2. **The no-renderer-on-TAB guarantee.** Completion must disclose nothing and
   deliver nothing, so the completion path imports *none* of `core.block` /
   `core.doc`. `cli/__init__.py` is lazy (PEP 562) precisely so
   `import painted.cli.complete` doesn't drag the renderer onto the TAB path.
   `complete.py`, `completion_shell.py`, and `_argwalk.py` are **render-free by
   construction** — keep them that way. `help.py` and `runner.py` *do* pull
   `core.doc`, so they are imported lazily, never at package top.

If you add a module here, ask first: does it need the renderer? If yes, it
either belongs at root (like `_transcription.py`) or must be pulled lazily.

**Don't reach for yet**: the dispatch internals, the prompt rungs.

---

## Level 1 — The three reflections of one parser

**Trigger**: I need to change how flags, help, or completion behave.

The load-bearing local idea: **painted builds one genuine `argparse` parser
(`build_parser` in `types.py`), and three subsystems read the same actions.**
There is no second source of truth for "what flags exist."

```
build_parser(...)  →  one argparse.ArgumentParser
        │
        ├─ PARSE     runner.py       parser.parse_args → Fidelity + ctx
        ├─ HELP      help.py         actions → doc-IR Doc (help_doc)
        └─ COMPLETE  complete.py     actions → Candidates (via _argwalk)
```

`_argwalk.py` is that single read: it yields a neutral `ArgSpec` per action, and
help projects it to a `Def` while completion projects it to a `Candidate`. Add a
flag once (in `add_cli_args` or a declaration), and parse, help, and completion
all see it — that's the invariant to preserve. A fourth reflection is
completion's *shell transport* (`completion_shell.py`): it emits the shell glue
and parses the `COMP_LINE`/`COMP_POINT` edit buffer back into the producer's
prefix.

**Local module map**:

| Module | Responsibility |
|--------|----------------|
| `types.py` | `Tag`, `OutputMode`, `Format`, `CliContext`, `ArgsView`; `detect_context`, `build_parser`, `add_cli_args`, `parse_fidelity` — the grammar + context detection |
| `runner.py` | `CliRunner`, `run_cli` — compile flags → `Fidelity`, dispatch by mode, deliver |
| `help.py` | `help_doc`, `HelpArg` — help as a doc-IR `Doc` (not a print) |
| `app_runner.py` | `AppCommand`, `run_app` — multi-command routing through `run_cli` |
| `prompts.py` | `Prompt[T]`/`Confirm`/`Select`/`Input`, `PromptSession` — the declared-question grammar behind `ctx.ask` |
| `_prompt_line.py` | LINE rung: cooked-mode prompt rendering (private sibling of `prompts.py`) |
| `complete.py` | the completion *producer* — parser actions → `Candidate`s (render-free) |
| `completion_shell.py` | the completion *transport* — shell glue emit + edit-buffer parse (render-free) |
| `_argwalk.py` | the single walk over parser actions (render-free) |
| `stream_surface.py` | alt-screen LIVE delivery (`live_delivery="surface"`) |
| `live_meter.py` | the opt-in per-frame `cost_meter` dressing |

The `run_cli` dispatch flow (parse → intercept `-h` → compile `Fidelity` →
`detect_context` → dispatch by mode) is owned by root `CLAUDE.md` Level 2 — read
it there, don't re-derive it here. What's local: the completion gate is checked
*first* in `CliRunner.run` (before `-h`, before parsing), and the empty-argv fast
path skips building a parser entirely.

**Don't reach for yet**: the renderer seam, prompts, completion internals.

---

## Level 2 — The renderer contract seam

**Trigger**: I'm working on how a rendered `Block` gets produced and delivered.

`run_cli` accepts one of four renderer forms, resolved at **construction**
(`CliRunner.__post_init__`), never degrading silently at dispatch. All four
normalize into one private `_RendererBinding` record carrying the declared arm;
dispatch (`_render`) reads that record, never the callable's arity:

- `renderer=` — the contract `(data, fidelity, width) → Block` (keyword-only).
  The semantic renderer, given only its three inputs. Reach for this first.
- `height_renderer=` — the height-aware contract
  `(data, fidelity, width, *, height) → Block` (keyword-only, `HeightRenderer`).
  The **acceptance** declaration for the offered arm of the dual allocation
  contract (`docs/HOST_RUNG_DESIGN.md` §4): the host offers a per-delivery
  `height`, and when it offers an integer `H` the returned Block must have
  exactly `H` rows (`_verify_height` enforces this at the offer site, §5).
  Mutually exclusive with *all* other renderer forms — pairing it with
  `renderer=` or `render=` is a construction-time `DeclarationError`.
- `render=` — legacy `(ctx, data) → Block`, optional-positional so existing
  `run_cli(args, render, fetch)` call sites keep working. Deprecation window; no
  runtime warning until 0.12.
- *neither* — the framework installs the transcription default (`_transcription.py`).
  `tags=` is unavailable on this form (transcription can't map facet names onto
  arbitrary data) and declaring it raises `DeclarationError`; a declared
  `renderer=` or `height_renderer=` lifts that fence.

The **offer matrix** (§3, three rows) lives in `_render`: an undeclared binding
is never handed the `height` keyword (it has none); a declared binding gated-off
is offered `height=None`; a declared binding gated-on is offered `height=H`. The
gated-off routes (STATIC, in-place/streaming LIVE — off-TTY always, and STATIC-TTY
unconditionally per the Q7 fence: a known terminal height is not permission to
offer it) pass `height=None`. The **interactive path is the gated-on route that
ships in 0.13/S4** (`_run_interactive` → `_run_host`): on a usable TTY it mounts
the binding into the host rung (`HostSurface`, below) and the *offered arm*
receives `height=H` from real Surface geometry. The bounded inline-LIVE row of the
matrix stays fenced (a later decision — see `docs/HOST_RUNG_DESIGN.md` §3). Route-
level pinning of every row is `tests/integration/test_host_rung_dispatch.py`.

**INTERACTIVE dispatch** (`_run_interactive`): a custom `handlers[INTERACTIVE]`
still wins first (the escape). Otherwise the framework resolves it: **not a usable
TTY** → fall back to LIVE (the pre-host-rung behavior); **a declared stream** →
stay on the live tier (`-i` keeps converging onto `StreamSurface`; the single-
fetch host rung would drop the stream, and the inward seam that would bring
`follow` home is §7's future work); **otherwise** → the host rung. Because the
host rung mounts *any* binding, `-i` is now honest on every command and
`_get_parser` offers it unconditionally — the `docs/MODE_RESOLUTION.md` filtering
rationale (hide `-i` when it is a no-op) is satisfied by the capability existing,
not by gating. The runner reaches the tui `HostSurface` through the *existing*
`stream_surface.py` cli→tui seam (a thin `run_host_surface` launcher) — the arch
tripwire caps that crossing at two seam files, so `runner.py` itself stays tui-
free.

Two local seams worth knowing before you touch delivery:

- **`_offered_width` is the single home of the width offer** (`docs/RENDERER_CONTRACT_DESIGN.md`
  §5). The rule gates on the *viewport*, not on ANSI-ness: a real TTY gets its
  geometry, a pipe/redirect gets `None` (natural sizing). `--plain` at a TTY
  still offers geometry. Width is re-offered per frame under LIVE — never a
  once-captured context width. No renderer ever consults TTY state; the pipe
  case arrives as `width=None`.
- **`ref_schemes=`** declares the denotation channel's resolver for the run — a
  runner-owned `use_refs` bracket around render + serialization. A static
  sequence validates at construction; a callable of state evaluates after fetch.
  See `docs/RENDERER_CONTRACT_DESIGN.md` §7.
- **`on_host_event=`** declares the inward host-event sink (`docs/HOST_RUNG_DESIGN.md`
  §7) — a keyword-only `HostEvent -> None` callback on the HOST constructor, never
  on the renderer binding (`_RendererBinding` carries the acceptance arm, not host
  input). The runner threads it into the two rungs where painted owns a viewport:
  `_run_host` (the interactive host rung — the offered arm builds no controller,
  so it fires nothing there) and `_run_live_surface` (the alt-screen streaming
  tier — the `follow` path). STATIC, in-place LIVE, the piped fallback, and the
  offered arm receive zero calls. A handler exception fails the active host
  delivery loud (never swallowed, never rerouted to `Surface.emit`). Both
  `HostSurface` and `StreamSurface` drive the shared `HostViewport` controller
  (root `painted.host`) that mints the events.

The full contract, its rationale, and the width-at-the-offer invariant are in
`docs/RENDERER_CONTRACT_DESIGN.md` (ratified 2026-07-12). Cite it; don't restate.

---

## Level 3 — Declarations: the grammar that mints the flag surface

**Trigger**: I'm adding or changing a `Tag`, depth alias, budget, or prompt.

Every user-facing flag exists because a capability was **declared** — the
honesty rule (`docs/FIDELITY_DESIGN.md`): a flag exists only because a capability
was declared, and a declared capability must change output. The grammar lives in
`types.py` beside the parsing it configures (the `Fidelity` *spec* stays in
`core/fidelity.py` — spec in core, grammar in cli).

| Declaration | Buys | Compiles into |
|-------------|------|---------------|
| `Tag(name, help, implied_at=…)` | `--{name}` flag + help entry + depth implication | `fidelity.visible` (read via `fidelity.shows(name)`) |
| `depth_aliases={"brief": 0}` | `--brief` (a depth *spelling*, joins `-q`/`-v`) | `fidelity.depth` |
| `budgets=True` | `--max-chars`/`--max-lines` | `fidelity.chars`/`fidelity.lines` |
| `prompts=[Confirm(…), …]` | the prompt's flag(s) + help + answer completion | resolved through `ctx.ask`, never `ctx.args` |

**Declarations are promises validated at construction.** `check_declarations`
raises `DeclarationError` for a malformed name, a collision (tag↔framework,
alias↔framework, tag↔tag, tag↔alias, prompt-spelling↔anything), or an
out-of-domain alias depth — at parser build, not at dispatch. `parse_fidelity`
resolves tag implications at compile time so the spec stays dumb and consumers
just call `shows()`. `build_fidelity=` is the escape-hatch, run last.

Grammar rationale is `docs/FIDELITY_DESIGN.md`. Don't restate the ladder here.

---

## Level 4 — Prompts and completion

**Trigger**: I'm modifying the inline-prompt subsystem or shell completion.

**Prompts** (`prompts.py`, `_prompt_line.py`, root `_prompt_cell.py`) — a
declared prompt is a CLI flag and an interactive question at two fidelities of
the same declaration. `Confirm`/`Select`/`Input` are three domain shapes over
one `Prompt[T]`; `ctx.ask(name)` is the single, memoized door an answer comes
through. Resolution never hangs and never invents an answer (flag → interactive
at a TTY → declared `default=` → `ContractError` naming the flag). The prompt
*render* has a two-rung split: LINE (cooked mode, `_prompt_line.py`, here) and
CELL (raw mode, `_prompt_cell.py`, at root because it imports `views`). Stdin's
TTY-ness is the gate; stderr's is the render fidelity. Full design:
`docs/PROMPTS_DESIGN.md`.

**Completion** (`complete.py`, `completion_shell.py`, `_argwalk.py`) — the
parser's third reflection, render-free (see Level 0). A candidate exists only
because the parser (or a declared `.completer`) produces it — the honesty-rule
analog. `CompletionContext` carries the parsed `ArgsView` so far plus the prefix,
so a domain completer scopes candidates to what's already typed. Full design:
`docs/COMPLETION_DESIGN.md`.

---

## Local invariants

- **`CliContext` is frozen.** `fidelity` is the canonical disclosure field;
  `ctx.zoom` is its rung-1 porthole (`Zoom(min(depth, 3))`), blessed permanently,
  not a compat shim. `ctx.args` (an `ArgsView`) is read-only; a prompt's answer
  never appears there — it rides `ctx.ask`.
- **Validation at construction, not dispatch.** Every misdeclaration
  (`render=` + `renderer=`, missing `fetch`, colliding flag names, bad
  `ref_schemes` shape) raises `DeclarationError` in `__post_init__` /
  `check_declarations` — asserted on empty argv.
- **`is_tty`/`use_ansi` are stdout-derived** (how *output* renders);
  `stdin_is_tty` gates prompts; `stderr_is_tty` sets prompt render fidelity.
  Three planes, kept separate.
- **Errors** follow `docs/ERRORS_DESIGN.md`: `DeclarationError` (author fault, at
  construction), `ContractError` (runtime contract breach), and
  `PromptContractError`, whose refusal routes through the single seam in
  `CliRunner.run`.
- **Errors never ride stdout.** Every mode's error emission — rendered blocks
  through `_emit_error`, the `--json` `{"error": …}` object, the refusal seam —
  targets stderr, leaving stdout a clean data channel on failure in every
  format. ANSI on that emission follows the stderr plane
  (`ctx.stderr_use_ansi`: `stderr_is_tty` overridden by the `--plain` request),
  never the resolved stdout format. Error messages keep their newlines: a
  consumer's multi-line message is declared structure, not whitespace. One
  stated exception: the in-place LIVE branch renders the error as the live
  region's final frame (a styled-TTY-only route — the region *is* the display,
  and a piped LIVE run takes the non-ANSI branch, which funnels to stderr).

## Design docs (cite, don't copy)

| Doc | Owns |
|-----|------|
| `docs/RENDERER_CONTRACT_DESIGN.md` | the `(data, fidelity, width)` seam, `renderer=`, transcription default, width-at-the-offer, `ref_schemes=` |
| `docs/FIDELITY_DESIGN.md` | the disclosure grammar: `Tag`, depth aliases, budgets, the honesty rule, the consumption ladder |
| `docs/PROMPTS_DESIGN.md` | inline prompts: stdin-TTY gate, prompt fidelity rungs, declared answers |
| `docs/COMPLETION_DESIGN.md` | shell completion: the third reflection, honesty rule, render-free guarantee |
| `docs/MODE_RESOLUTION.md` | AUTO mode collapse, capability filtering |
| `docs/ERRORS_DESIGN.md` | the exception hierarchy and its site table |
