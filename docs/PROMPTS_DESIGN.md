# Inline prompts — the parser's fourth reflection

**Status: PLANNED (0.9)** — design of record for the inline-prompt subsystem:
the new bottom interactive rung (scroll-flow interaction, no alt-screen)
between LIVE and the Surface. Contract spine ratified 2026-07-07 (store:
`decision/design/prompts-contract`, `decision/design/prompts-devtty-refusal`,
`decision/design/prompts-declared-foundation`); declaration grammar and the
`Prompt[T]` primitive ratified 2026-07-07 (Q1–Q4 resolved inline in §6).
Fresh-context review round 2026-07-08: §3.2 default-answer record line,
§8 stream discipline (prompts scope), and §9 danger tiers (Confirm-only
HARD, `challenge=`, value-carrying flag) ratified. Codex (GPT-5.5 xhigh)
fresh-eyes review, same day: 12 findings triaged and remediated in place —
danger×default construction rule, the HARD flag pair, single-door runtime
arity (`ctx.ask`, two arities), stream-state and error-routing rules (§8),
sequencing reorder (§12).

Companion to `docs/COMPLETION_DESIGN.md` (the parser's third reflection) and
`docs/FIDELITY_DESIGN.md` (the disclosure grammar prompts extend to the input
side). Provenance: this design is grounded in a six-tracer ecosystem trace
(2026-07-07) whose full evidence lives in the store under
`observation/peer/prompts-*` and `observation/peer/clig-dev`; §2 distills it.

## 1. The thesis — the missing tenet

clig.dev names nine tenets of good CLI design. painted has a named contract
for nearly all of them — *saying (just) enough* is the Fidelity grammar,
*ease of discovery* is declare→generate, *robustness* is the honesty rule —
except one: **conversation as the norm**. Trial-and-error, confirmation,
dialogue. That tenet is this subsystem.

A prompt is an **input**, and painted's CLI grammar already has an input
channel: declared flags. `--force` and `Are you sure? [y/N]` are the same
declaration at different fidelities — one resolves from argv, one resolves
interactively at a TTY. The parser is already read three ways (parse, help,
complete — COMPLETION_DESIGN §1); a declared prompt is the **fourth
reflection**. One declaration generates:

```
                     declared prompt
                           │
        ┌────────────┬─────┴──────┬─────────────────┐
        ▼            ▼            ▼                 ▼
      flag        prompt        error           completion
  (--overwrite)  (at a TTY,  (non-TTY, answer   (of the answer
   in argv,      flag absent) undeclared —       values, free —
   parsed,                    names the flag)    third reflection
   in -h)                                        composes)
```

The error in the third column is the load-bearing one, and it is the thing
**no standalone prompt library can produce** (§2): an honest refusal must
name the flag that answers the question, and the flag lives in the
application's parser. painted is a prompt library and a CLI framework in one
package — it holds both ends. This is completion's move again: the capability
exists *because* the declaration exists.

## 2. Provenance — the landscape, traced

Six tracers (2026-07-07), one probe: what does a bare confirm/select do when
stdin is not a TTY? Finding: **nowhere in the ecosystem is this a designed,
complete contract.** Five postures, each with a hole:

| Posture | Who | Behavior in a pipe | The hole |
|---------|-----|--------------------|----------|
| Pipe-as-answer | Rich, click, stdlib `input()` | reads the piped line as the response (`yes \|` works) | on EOF, Rich leaks a raw `EOFError`, click aborts; **`default=` never fires on EOF in either** — it is empty-line-only |
| Pipe-as-keystrokes | prompt_toolkit, questionary, InquirerPy; clack, prompts, enquirer | pipe bytes parsed as key sequences | works for text, fragile for selects (arrow keys are escape sequences); questionary leaks `EOFError` |
| Silent hang / exit 0 | all five major JS libraries on EOF | promise never settles → hang, or silent exit 0 | the worst behavior found; accidental in every case. Inquirer *built* the TTY check, then shipped it disabled while its README still documents it |
| Fail-loud, no hatch | Ink, dialoguer, inquire | clean error (`Raw mode is not supported`, `NotTTY`) | no answer channel — degradation is entirely the app's job; even official companion components don't guard. The seam where real apps' pipe crashes recur |
| Grab `/dev/tty` | bubbletea/gum, dialoguer-via-console, stdlib getpass | bypass the pipe, prompt the human anyway | defeats `echo y \|` scripting; fully headless still dies (`could not open a new TTY`) |

Three findings shape this design beyond the table:

- **clig.dev states the ideal; no library implements it.** Prompt only if
  *stdin* is a TTY; never require a prompt — always a flag alternative;
  needed-but-undeclared input in a non-interactive context fails *telling the
  user the flag*. The tools that do implement it are applications (terraform
  `-input=false`, pip `--no-input`, `GIT_TERMINAL_PROMPT=0`) — each
  re-deriving the behavior by hand, because the library layer can't see the
  parser.
- **The `default=` misconception is universal.** In Rich, click, dialoguer,
  and inquire, `default` means "the value when the user presses bare Enter" —
  it rescues nothing in CI. Callers read it as "the value when nobody
  answers" and ship hangs.
- **Three reusable gifts**, adopted below: gum's stream split (§8), huh's
  accessible mode as a fidelity downgrade (§5), and dialoguer's
  `report`/clack's answered-state — the prompt collapsing to a static record
  in the transcript (§7).

## 3. The contract

Ratified. For every prompt, declared or runtime (§6):

1. **The gate is stdin.** A prompt renders only when `sys.stdin.isatty()`.
   stdout's state is irrelevant to *whether* we ask — it governs how the
   program's *output* renders, as everywhere else; the prompt's own render
   follows the stream it draws on, stderr (§8). dialoguer guards the wrong
   stream (stderr)
   and gets a tool that prompts into a pipe; clig.dev is explicit: the
   question "is a human driving?" is a question about stdin.
2. **Non-TTY with a declared answer resolves without asking.** A passed
   flag resolves silently — the answer is already visible in the invocation
   itself. An applied `default` emits the §7 record line marked
   `(default)`, on stderr (§8): it is the one resolution path where the
   answer came from neither the user's argv nor the user's keystrokes, so
   the transcript must say so — "tell the user" applies most where nobody
   chose.
3. **Non-TTY without one raises `ContractError` naming the flag.**
   Error-with-remediation, terraform-shaped: *"stdin is not a terminal and
   no answer was provided — pass `--overwrite` / `--no-overwrite`."* The
   message can name the flag because the flag provably exists (§1). For a
   runtime declaration no flag exists, so the refusal names the channel
   that does: the prompt's name and the default its call site must supply
   (§6) — honest about the thinner channel.
4. **Never hang, never silently default, never exit unanswered.** The JS
   posture (unsettled promise → exit 0) is the named worst case; the apt
   posture (EOF silently means "no") is the subtle one — a default the user
   never declared is an invented answer, an honesty violation.
5. **`default=` fires on absence of a terminal, not on EOF.** A deliberate
   break from the ecosystem (§2). At a TTY, bare Enter accepting the default
   is *also* offered — but that is presentation of the same declared value,
   not a second meaning. Only `Danger.NONE` may carry a default — SOFT and
   HARD forbid `default=` at construction (§9), so the tiers that demand
   explicit intent cannot be silently absorbed by a script.
6. **`--no-input`.** One framework flag, clig-standard, disabling all
   interactivity: with it, every prompt behaves as if stdin were not a TTY
   (rules 2–3 apply). CI scripts declare their nature instead of relying on
   detection.

One timing consequence, named (2026-07-08): because `ctx.ask` resolves on
first read (§6), the rule-3 refusal fires when the question fires —
possibly mid-run, after work has been done. This diverges from terraform's
up-front `-input=false` refusal deliberately: painted's questions can be
data-dependent, and eager validation would refuse runs over questions never
asked — its own honesty violation. No mechanism compensates; the lever is
the app's, and it is the same lever Q3 grants: **ask before you act** — a
prompt read early fails early, and the call site chooses the failure point.

The adopted/refused ledger, for the record:

| Decision | Source |
|----------|--------|
| stdin-TTY gate, flag-naming error, `--no-input` | adopted from clig.dev |
| answered prompt → static record line | adopted from dialoguer `report` / clack |
| fidelity downgrade of the prompt itself | adopted from huh accessible mode |
| stderr-UI / stdout-result split | adopted from gum (§8, ratified for prompts 2026-07-08) |
| pipe-as-answer (`echo y \|`) | **refused** — the pipe is data-plane; answers ride the declared channel. `yes \|` scripting is replaced by the flag, which is typo-proof and completable |
| pipe-as-keystrokes | **refused** — fragile (escape sequences), and an accident everywhere it exists |
| EOF/empty-line as an answer | **refused** — invented answer |
| hang / silent exit | **refused** — the contract's raison d'être |

## 4. The `/dev/tty` refusal

Ratified: **painted never opens `/dev/tty`.** No prompt, no fallback, no
"just work" grab.

The Charm position ("stdin is data, the human is on `/dev/tty`") is the
strongest counter-argument, and it is genuinely attractive for painted —
apps do pipe data in and want to confirm something. The refusal holds
because the grab is a *compensation*: bubbletea reaches for the terminal
because it has no answer channel. painted has one — the declared flag — so
`cat data | tool` wanting confirmation says `cat data | tool --overwrite`,
which is scriptable, completable, and visible in the process table and shell
history where a hijacked terminal interaction is not. Grabbing the terminal
anyway is how CI hangs are born; clig.dev's stdin gate exists precisely to
prevent blocking a script on a human.

**The one legitimate `/dev/tty` case is secrets — deferred by name.**
clig.dev forbids secrets in flags *and* env vars (files or stdin only), so a
password prompt is the one prompt kind whose flag channel is forbidden by
design. That is exactly why sudo/ssh grab `/dev/tty` and ship an askpass
ladder (`SUDO_ASKPASS`, `SSH_ASKPASS`) as the declared no-tty escape. painted
does not ship a secret prompt in 0.9. When a consumer needs one (the
trigger), the shape is known in advance: `/dev/tty` becomes legitimate for
that prompt kind only, paired with an askpass-style declared escape so
automation is never dead-ended. Recorded so the future decision is a design
recall, not an improvisation.

## 5. The prompt's own fidelity ladder

A prompt is a render, and renders in painted degrade monotonically. The
ladder, top to bottom:

```
CELL     raw-mode keys + in-place repaint     select cursor, styled
         (InPlaceRenderer + KeyboardInput)    options
LINE     cooked-mode line input               numbered options, "Enter
         (huh-accessible / Rich-Prompt shape)  1-4", y/n — dumb terminals,
                                              screen readers, teleprinters
DECLARED no interaction                       flag / default / ContractError
```

Rung selection is capability-honest, same as mode resolution: stdin a TTY,
raw mode available, and stderr a TTY (§8 — CELL repaints in place on the
stream it draws; repainting into a log is not a render) → CELL; stdin a TTY
but raw mode unavailable, stderr piped, or plain requested → LINE; stdin
not a TTY or `--no-input` → DECLARED. The LINE
rung is not a degraded afterthought — it is the accessibility surface (huh
documents its equivalent as a screen-reader feature first) and must present
the same options and produce the same answer type as CELL. Same value → same
treatment, the vocabulary guarantee, applied to input.

This is the origin thesis pointed at input: adopting a prompt never forces
an environment rewrite, because every environment has a rung.

The CELL renderers are not new machinery: `views/components/` already ships
the frozen-state reducers the TUI side grew — `ListState` (selection,
scroll-into-view) and `TextInputState` (cursor editing: insert, delete,
movement, home/end, viewport scroll). A prompt at CELL is one of these
components delivered through `InPlaceRenderer` with the resolution contract
(§3) wrapped around it. The prompt subsystem and the Surface batteries
consume the *same* components — nothing is duplicated across the two
interactive rungs.

One placement consequence: `KeyboardInput` lives in `tui/keyboard.py`
today, and the module map sanctions no cli→tui edge. It hoists to the
renderer's delivery layer (beside `InPlaceRenderer`) as part of the CELL
rung — key reading is delivery machinery, not TUI machinery — and the
Surface consumes it from its new home. `cli/prompts.py` never imports
`tui/`. The hoist is a refactor, not a move (review finding, 2026-07-08):
today's object opens cbreak (not raw), binds `sys.stdin` at construction,
polls non-blocking, and learns availability only privately after mutating
terminal state. The delivery-layer form needs a public availability probe
that rung selection can read *before* any terminal mutation, a blocking
read for prompt use, and an injectable stream (§10).

## 6. The declaration — one primitive, three domain shapes (RATIFIED 2026-07-07)

The semantic primitive is **`Prompt[T]` — a declared question**:

```
Prompt[T]
  name          → the flag spelling, the record-line label
  question      → the rendered text
  domain        → what answers exist, and str → T
  default       → the declared non-TTY answer (optional)
  danger        → ceremony tier (§9, ordered vocabulary)
```

`default` is sentinel-guarded (`MISSING`), not `None`-guarded. Absent means
"no declared answer" — non-TTY falls through to `ContractError`.
`default=None` declares `None` *as the answer*, legal only where the domain
admits it (an optional select whose honest non-interactive resolution is
"none of them"); like every declared answer, the default is validated
against the domain at construction, so `Confirm(default=None)` is a
`DeclarationError`.

`Confirm`, `Select`, and `Input` are not three primitives — they are three
**domain shapes** over this one: `Confirm` is `Prompt[bool]` with the
two-element domain (and, alone among the shapes, the HARD tier's
`challenge=` — §9); `Select` is a Prompt over an *enumerable* domain (a
values tuple or a declared Vocabulary); `Input` is a Prompt over an *open*
domain with a parse/validate function. Everything on the primitive — the
resolution ladder, the stdin gate, the record-line collapse, the danger
tiers — is written once; a domain shape supplies only answer parsing and a
renderer binding.

**Domain enumerability is the single property the rest derives from:**

| domain | flag | completion | CELL renderer |
|--------|------|------------|---------------|
| enumerable | `choices`-validated | candidates for free (third reflection) | `ListState` cursor |
| open | typed value, validator runs | declared `completer=` riding the third reflection, else file/dir fallback (COMPLETION_DESIGN §5's classification) — `Input("reason")` must be able to refuse file completion | `TextInputState` editing |

All three shapes ship in 0.9, at all rungs — the earlier draft deferred
`Input`'s CELL rung on the belief that line editing was a subsystem to
build; `TextInputState` already exists (§5), so the deferral dissolved.

Two binding times, one contract. The resolution order is identical for both:
**argv flag (parse-time only) → prompt at a TTY → declared default →
`ContractError` naming the channel.**

**Parse-time** — declared to `run_cli` beside `tags`/`depth_aliases`, worked
example shaped on loops:

```python
run_cli(
    args, render, fetch,
    tags=[Tag("verify", "Signature verification detail")],
    prompts=[
        Confirm("reseal", "Re-seal the open window?", danger=Danger.SOFT),
        Select("scope", "Which store?", values=("local", "config", "all"),
               default="local"),
    ],
)
```

Each declaration generates its flag with the same collision rules as `Tag`
at parser construction — and those rules gain an explicit **reserved
registry** of the framework's own spellings (`-q`/`-v`/`--json`/`--plain`/
`--static`/`--live`/`-i`/`--no-input`, the budget flags), so a declaration
that would shadow a framework flag (`Confirm("input")` → `--no-input`) is a
`DeclarationError` at construction, not an argparse conflict at runtime.
`Confirm("reseal")` → `--reseal` / `--no-reseal`
(both spellings, BooleanOptionalAction-shaped — except at `danger=HARD`,
where the pair is `--reseal <challenge>` / bare `--no-reseal`, §9);
`Select("scope", values=…)`
→ `--scope {local,config,all}`, choices-validated by the parser, completed
by the third reflection with zero new machinery. The answer has **one
door** (ratified 2026-07-08): prompt-declared names are stripped from
`ctx.args` at compile time and parked as pre-resolved answers behind
`ctx.ask("scope")`, which triggers the interactive resolution on first
read — so the app controls *when* in its flow the question fires, and no
second attribute exists that looks like the answer but silently bypasses
the prompt (the `default=` misconception of §2, structurally prevented).
One sentence teaches it: a Tag's answer is in `ctx.args`; a Prompt's answer
is behind `ctx.ask`.

`run_app` mirrors the declaration: `AppCommand` gains `prompts=`, and the
app-level help/completion builders include them — without the mirror, a
multi-command consumer (loops, the first one) declares prompts that the
intercepted `-h` and `<TAB>` can never see.

**Runtime** — data-dependent questions ("3 conflicts — overwrite which?")
can't be parse-time flags. They remain declarations *made before asking*,
same object, handed to **the same door**: `ctx.ask` accepts a declaration
as well as a name — one method, two arities, so a runtime prompt sees
`--no-input`, the stream policy (§8), the memoization (keyed by name), and
the record ledger (§7) with no hidden global state. A runtime declaration
whose name collides with a parse-time declared prompt is a
`DeclarationError` pointing at `ctx.ask("name")` — otherwise a runtime ask
could consume a parked argv answer from outside its own domain (checkpoint
finding, 2026-07-09):

```python
choice = ctx.ask(Select("conflict", "Overwrite which?", values=conflict_ids))
```

A runtime declaration has no argv flag, so its declared channel is the
`default` (or the values' vocabulary collapsing to one — the gum
`--select-if-one` shape); absent both, non-TTY raises `ContractError`
naming... what it *can* name: the prompt's name and the fact that the
call site must supply a default for non-interactive use. The error text is
honest about the thinner channel rather than pretending a flag exists.

**Vocabulary tie-in.** `Select` accepts `values=` (an open tuple, the
series-shaped case) or `vocabulary=` (a declared Vocabulary): with a
vocabulary, the flag's legal values *are* the vocabulary, the parser
validates them, completion completes them, and the mark channel styles them
in the rendered prompt — one declaration feeding four generators plus the
render.

**The Q round (all resolved with Kyle, 2026-07-07):**

- **Q1 — the primitive set: the `Prompt[T]` analysis above.** All three
  domain shapes ship at all rungs. Multi-select remains deferred (trigger:
  first consumer) — a domain-shape addition, not a primitive change.
- **Q2 — placement: as proposed.** Components own the render
  (`views/components/` frozen-state pattern; the TUI batteries consume the
  same states). A new `cli/prompts.py` owns the domain shapes, `ask`, and
  the resolution contract — the evolving `painted.cli` surface, not the
  stable one, until 1.x hardens it.
- **Q3 — answer delivery: `ctx.ask("scope")`, the single memoized door**
  (extended 2026-07-08). Explicit, controls firing order, makes the
  prompt's position in the transcript deliberate — prompts are effects, and
  effects are visible at the call site. Prompt names never appear in
  `ctx.args`. `ask` is memoized: a prompt fires at most once per run, and a
  second read returns the recorded answer — the §7 record line is the
  visible proof of the single firing. `ctx.ask` of an undeclared name is a
  `DeclarationError`-family failure naming the declared prompts, never a
  bare `KeyError`.
- **Q4 — `--no-input` adopted verbatim** (clig-standard; it means no
  *interactivity*, orthogonal to `--plain`'s no *style*). The discussion
  surfaced a wider discomfort — framework flags are currently mandatory,
  with no way for an app to opt out — now tracked as
  `thread/framework-flags-optout`. Design constraint carried into 0.9:
  `--no-input` is wired like every other framework flag, so if that revisit
  makes them suppressible, it suppresses with the rest — no special casing.

## 7. Lifecycle — a live region that becomes a record

The prompt's delivery is InPlaceRenderer's exact lifecycle: a region that
repaints while open, then resolves. On answer, the interactive region is
replaced by a **single static record line** — question, chosen answer,
styled by the answer's mark where a vocabulary is declared:

```
? Overwrite 3 conflicts?  ▸ yes                 (while open: live region)
✓ overwrite: yes                                (after: one record line)
```

This is the dialoguer-`report`/clack precedent made structural: the
transcript is the render, and a session that asked three questions reads
afterward as three record lines — the same shape `record_line` gives log
events. A default-resolved prompt at DECLARED fidelity emits the same
record line marked `(default)`, so interactive and defaulted runs produce
comparable transcripts — clig's "if you change state, tell the user"
applied to answers. Flag-supplied answers are the one path that does not
echo: the answer is already visible in the invocation itself, and repeating
it fails "saying (just) enough". The rule in one line: **the record line
marks an answer the invocation doesn't show** — one asked at a TTY, or one
assumed from a declaration.

Ctrl-C during a prompt follows clig signals guidance: restore the terminal,
exit promptly — a prompt abort is a `KeyboardInterrupt`, never swallowed
into a `None` (the questionary sentinel is the named counterexample). EOF
(Ctrl-D) at a live prompt is the same abort path: at a TTY too, EOF is
never an answer and never falls through to the default — the §3 ledger's
EOF refusal applies everywhere, not just in pipes.

## 8. Stream discipline (RATIFIED for prompts 2026-07-08)

Prompts force a question painted has never taken a position on: the prompt
UI and the program's *output* cannot both own stdout. gum's split is the
proven shape — UI on stderr, result on stdout — and is what makes
`x | gum choose | y` composable. Ratified, scoped to prompts:

- **Prompt UI renders to stderr.** Both CELL and LINE rungs. stdout stays a
  pure data channel; `tool --json | jq` works even when the tool asked a
  question mid-run.
- The stdin gate (§3) is unaffected — stderr is where we *draw*, stdin is
  still what decides *whether*.
- **The rule-3 refusal renders to stderr too.** Today `run_cli`'s error
  block prints via `print_block`'s stdout default (`cli/runner.py`,
  `core/writer.py`), which would send the remediation text down the data
  pipe into `jq`; rerouting the prompt `ContractError` is part of
  sequencing step 1.
- **The prompt's render fidelity consults stderr's TTY-ness** — stderr
  piped → LINE rung, plain, no ANSI — while the gate stays stdin. Named
  edge, accepted: `tool 2>log` with stdin a TTY prompts into the log and
  waits on a human who sees nothing; redirecting stderr is a deliberate
  act, and the gate is clig's rule.
- **`CliContext` grows the stream dimensions this needs.** Today
  `is_tty`/`use_ansi` are stdout-derived (`cli/types.py`); the context
  gains explicit stdin (the gate) and stderr (prompt fidelity) state, so
  `echo y | tool` at a TTY-stdout never prompts and `tool | jq` at a
  TTY-stdin still can.

Taking this position for prompts creates pressure to reconcile
`PaintedHandler` (diagnostics) and `live_meter` with the same rule — clig is
blunt: messaging belongs on stderr. That reconciliation is scoped to its own
thread, not 0.9; the prompt decision should be made compatible with it, not
blocked by it.

## 9. Severity-tiered confirmation (RATIFIED 2026-07-08)

clig tiers dangerous-action ceremony: y/n → type-the-name → require an
explicit flag. Danger levels are an **ordered vocabulary** (0.6 mechanism):
ordered ⇒ comparative behaviors, exactly as severity drives gutter
escalation. The tiers answer two distinct failure modes: `SOFT` answers
*"did you mean to proceed?"* (accidental Enter, muscle memory); `HARD`
answers *"do you know what you're aiming at?"* (intended destruction,
wrong target).

| Danger | TTY ceremony | Non-TTY |
|--------|--------------|---------|
| `NONE` | y/N, Enter accepts default | default applies |
| `SOFT` | y/N, no Enter-default — an explicit key | flag or `ContractError` |
| `HARD` | type the declared `challenge` to proceed | flag **required and value-carrying** — `--reseal <challenge>`; the script restates the challenge |

A field survey (2026-07-08: gh/heroku/flyctl type-the-name, terraform's
literal `yes`, apt's `Yes, do as I say!`, rm's flag-only
`--no-preserve-root`) ratified three constraints:

- **HARD is `Confirm`-only.** The ecosystem has no dangerous select —
  battle-hardened CLIs decompose "dangerously choose" into choose
  (harmless) → confirm (ceremonial), with the confirm knowing the target's
  name. `danger=HARD` on `Select`/`Input` is a `DeclarationError`; revisit
  trigger: a first consumer arriving with a concrete ceremony in hand.
- **`challenge=` is a required free string on HARD.** Resource name
  (gh-shaped), literal token (terraform is `challenge="yes"`), or fixed
  phrase (apt) are all the same declaration — no fourth tier needed. HARD
  without `challenge`, and `challenge` on `NONE`/`SOFT`, are
  `DeclarationError`s: ceremony that can never fire is a dead declaration.
  So is an empty or whitespace-only challenge — `--destroy ""` satisfying
  HARD is the exact empty-shell-variable accident the value-carrying flag
  refuses (checkpoint finding, 2026-07-09).
- **HARD's flags are a pair, replacing the boolean pair (§6):**
  `--reseal <challenge>` is the yes — value-carrying, heroku's
  `--confirm <appname>` shape — and bare `--no-reseal` is the no, because
  declining needs no ceremony; only destroying does. Absence of both in
  non-TTY is the rule-3 `ContractError`. A challenge mismatch
  (`--reseal wrong`) is a `ContractError` at resolution, not an argparse
  choices error — a challenge may be data-dependent (loops' reseal
  challenge is plausibly the window id). The challenge value is never
  completed: typing it is the ceremony. It ports across rungs instead of
  evaporating in scripts: a TTY types the name, a script types the name
  into the flag, and an empty shell variable refuses instead of destroying
  the default. Corollary, the apt rule: `--no-input` and any generic
  affirmative never satisfy HARD — only the specific flag with the
  specific value does.
- **`danger >= SOFT` forbids `default=`** — a `DeclarationError` at
  construction. SOFT's guard is explicit intent; a default that silently
  resolves in a script evaporates the guard exactly where nobody is
  watching. Only `NONE` may carry a default, which keeps §3's rules 2 and
  5 coherent with the table's non-TTY column — a script can never trip
  over a SOFT or HARD action silently.

`Danger` is a painted builtin vocabulary (like severity) — the ceremony
behaviors are painted's, so the scale must be too.

## 10. Testing shape

The ecosystem's proven pattern is injection, not TTY emulation:
prompt_toolkit's `create_pipe_input`, ink-testing-library's fake stdin with
an `isTTY` override, `prompts.inject`. painted composes what it has:

- **CELL rung**: the component render fns are pure — golden-test
  `render(ListState(...))` / `render(TextInputState(...))` like any
  component; drive the reducer with a key list, TestSurface-style, no
  terminal.
- **Resolution contract**: parametrize the gate — a fake stdin whose
  `isatty()` returns False must yield the flag / default / `ContractError`
  ladder without rendering anything. The NO_COLOR conftest lesson (0.8)
  applies: the suite must scrub/parametrize ambient TTY-ness so
  `./dev check` passes identically piped and at a terminal — the contract's
  own audience is CI.
- **LINE rung**: cooked-mode reads take an injectable stream (the one place
  a stream parameter exists — for tests, not for pipe-driving; the public
  contract stays §3).

## 11. Refusals and deferrals

**Refused** (named in docs, with reasons):

- `/dev/tty` — §4.
- Pipe-driven answering (`yes |`, pipe-as-keystrokes) — §3 ledger. The
  migration path for `yes |` users is the flag.
- EOF-as-answer, hang, silent default — §3.
- A prompt *framework* (forms, multi-step wizards, validation chains) —
  already a named refusal in the TUI spine; a form is an app-side
  composition of prompts.
- A scripted answer to a *runtime* `HARD` prompt — a theorem, not a gap:
  the flag channel cannot exist (the domain didn't exist at parse time)
  and HARD forbids a default by definition. Scripts may do destructive
  things they committed to at invocation; they may not absorb destructive
  decisions that only materialize mid-run. The migration path is lifting
  the decision to parse time, where HARD gets its value-carrying flag
  (§9).

**Deferred** (with triggers):

- Secret/password prompts + the askpass ladder — trigger: first consumer
  (§4).
- Multi-select — trigger: first consumer; a domain-shape addition over the
  `Prompt[T]` primitive, not a primitive change (§6).
- Timeout-with-default (gum `--timeout`) — a liveness feature with a real
  CI story, but it reintroduces "an answer nobody gave"; wants its own
  argument. Trigger: a consumer that genuinely cannot use `--no-input`.
- Select filtering (type-to-filter over a large domain) — new interaction
  state, not a `ListState` reuse; trigger: first consumer whose domain
  outgrows a scrollable list.
- `PaintedHandler`/`live_meter` stderr reconciliation — own thread (§8).

## 12. Sequencing sketch (not yet sliced)

1. Contract core: the declarations (`Prompt[T]`, the three shapes, every
   construction-time rule — danger's construction and flag-pair rules
   included), parse-time `prompts=` flag generation, the
   gate, `--no-input`, `ctx.ask` + the memoized answer store, resolution
   order, `ContractError` messages routed to stderr — DECLARED rung only
   (no prompt rendering; the whole contract is testable headless, and the
   flags must exist before "passed flag resolves" is testable at all).
2. LINE rung: cooked-mode renderers for all three domain shapes — the
   accessibility floor, and the first visible prompt.
3. CELL rung: bind the existing `ListState`/`TextInputState` components to
   InPlaceRenderer delivery + the answered→record collapse.
4. The reflections beyond parse: the `run_app` mirror
   (`AppCommand.prompts`), help rendering, completion of answer values
   (third reflection, including `Input`'s `completer=`).
5. Danger ceremony rendering over the ordered-vocabulary mechanism — the
   TTY behaviors (Enter handling, type-the-challenge); danger's
   construction and flag rules landed in step 1.
6. Docs: this file's status flip, the doc-IR page, demos (a pattern-tier
   prompt demo; the walkthrough gains no stage — prompts are a rung, not a
   drive).

Rung order is deliberate: DECLARED before LINE before CELL means the honesty
contract exists before any pixel is drawn, and every later rung is pure
upgrade — monotonic enhancement, enforced by build order.
