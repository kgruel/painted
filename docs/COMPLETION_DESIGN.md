# Shell completion — the third reflection of the parser

**Status: IMPLEMENTED 2026-06-30** (umbrella branch `autocomplete`, slices
S1–S7). Native, zero-dependency, *dynamic* shell completion delivered as a
painted capability rather than a generated static script. This document is the
design of record — the tying narrative the per-file docstrings
(`cli/complete.py`, `cli/_argwalk.py`, `cli/completion_shell.py`) don't hold on
their own. The consumer-facing guide is the doc-IR page (`painted docs
completion`); this file is for *contributors*.

Companion to `docs/FIDELITY_DESIGN.md` (disclosure) and
`docs/LIVE_DELIVERY_DESIGN.md` (delivery): those give two of `run_cli`'s axes
their contract; this gives the parser its *third projection*.

## 1. The thesis — one parser, three reflections

An argparse parser is built once (`cli/types.py:build_parser`) and read three
ways:

```
                build_parser ─→ walk_args ─→ [ArgSpec]
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                             ▼
     parse                         help                        complete
  → Namespace                    → Def                       → Candidate
  (runs the command)          (renders -h)              (answers TAB)
```

`cli/_argwalk.py:walk_args` is the **single walk** over `parser._actions`,
yielding a neutral `ArgSpec` per action. Help projects each spec to a `Def`
(`cli/help.py`); completion projects it to a `Candidate` (`cli/complete.py`).
There is **no second source of truth** — the flag you see under `-h` is exactly
the flag that completes, because both are the same `ArgSpec`. Adding a structural
fact to completion (see §6, mutex membership) means adding a field to `ArgSpec`,
not a second introspection of the parser.

## 2. The honesty rule

A completion candidate exists **only** because the parser, or a declared
`.completer`, produced it. painted never invents a candidate, and it
**under-lists rather than suggest a flag the parser would reject**. A candidate
you can't act on is worse than one that's missing. This rule is load-bearing in
concrete decisions:

- `complete_app` builds each subcommand parser with `modes={STATIC}`
  (`cli/complete.py:_command_parser`): an `AppCommand` can't declare its delivery
  capability, so completion omits `-i`/`--live`/`--static` rather than offer a
  flag the command might reject.
- File/dir fallback (§5) is *classified* by painted but *walked* by the shell —
  painted never fabricates paths it hasn't read.
- Mutex-exclusions (§6) suppress a group sibling once one member is on the line,
  because argparse would reject the pair.

## 3. The render-free guarantee — no renderer on TAB

Pressing TAB imports **none** of `core.block` / `core.doc`. This is not a
promise; it is enforced by construction and verified end-to-end
(subprocess-probed in `tests/unit`):

- `complete.py`, `_argwalk.py`, and `completion_shell.py` import only stdlib,
  each other, and the renderer-free `ArgsView` (`cli/types.py`).
- An `AppCommand` is read **by attribute only** (`cmd.name`, `cmd.add_args`,
  `cmd.tags`) — never constructed and never round-tripped through the framework.
- The `_PAINTED_COMPLETE` gate intercepts at the **top** of `AppRunner.run` /
  `CliRunner.run`, before any routing or render machinery loads.
- `cli/__init__.py` is a PEP 562 lazy facade; `app_runner`/`runner` defer
  `core.doc` and `.help` imports into the functions that need them.

Why a rendering library specifically needs this: TAB must be instant no matter
how expensive the program is to *run*, and typing TAB must never trigger the
work the command would do. For painted — where the alternative is importing the
whole surface — the guarantee is the thesis, not a micro-optimization.

## 4. The transport — buffer to candidates and back

The shell glue (`completion zsh`/`bash`) re-invokes the program with
`_PAINTED_COMPLETE=<shell>` set and the edit buffer in `COMP_LINE`/`COMP_POINT`.
`cli/completion_shell.py` parses that buffer into the producer's
`preceding`/`prefix` and prints candidates back in the shell's dialect:

- **Cursor boundary** — only the left of `COMP_POINT` is parsed; the partial
  token under the cursor is the `prefix`.
- **Tolerant quoting** — a half-typed `--kind "lo` makes `shlex` raise;
  `_tolerant_split` closes the quote, then falls back to a naive split, rather
  than dropping the request.
- **`--opt=val` splitting** — the value is completed in the option's value
  context, then re-prefixed so the shell replaces the whole word.
- **Dialect** — zsh gets `value:description` for `_describe` (colon-escaped);
  bash and the fallback get bare values.
- **File directive** — an open slot emits a `\x1f`-prefixed line (Unit
  Separator, collision-proof, survives `read -r`) telling the glue to add
  `_files` / `compopt -o default`. See §5.

## 5. File and directory completion — classify here, walk there

An argument with no `choices` and no `.completer` is an **open slot**. painted's
producer *classifies* it (`wants_file_completion`); the **shell** does the
filesystem walk (zsh `_files`, bash `compopt -o default`). painted never reads
the disk — so `~` expansion, hidden-file rules, and the user's own `zstyle` all
keep working, and completion stays render-free and side-effect-free. The explicit
opt-out for a free-text value with no path fallback is a completer returning
`[]`.

## 6. Mutex-exclusions

argparse builds mutually-exclusive groups (painted's own CLI has two: the zoom
group `-q`/`-v`/depth-aliases and the mode group `--static`/`--live`). argparse
*rejects* two members of one group on the same line, so offering `--live` after
`--static` — or `-q` after `-v` — violates the honesty rule.

The fix carries the one structural fact through the **single walk**:
`ArgSpec.mutex_group` is the action's group index (`None` when ungrouped),
computed in `walk_args` from `parser._mutually_exclusive_groups`. The
*suppression policy* lives in the producer (`complete.py`), where the honesty
rule is enforced: `_mutex_blocked` drops a candidate whose group already has a
*different* member present. A member is never blocked by its **own** spelling —
argparse accepts `-v -v` (=`-vv`) and `-q --quiet`, so those keep completing;
only a genuine sibling blocks.

Presence detection (`_present_option_strings`) handles the three ways an option
appears: exact (`--static`), `--opt=val` (the head), and short-flag **clusters**
(`-vv`/`-qv` decompose to their nargs-0 members — argparse-valid, so they count
as present). A value-taking option's value is skipped, mirroring
`_count_consumed_positionals`.

**Scoped limitation (honest, not a claim of completeness):** abbreviations
(argparse's `allow_abbrev`, on by default) are matched by exact spelling, not
resolved — a typed `--stat` does not register `--static`, so its sibling isn't
suppressed. This mirrors the rest of the producer's exact-match handling; the
pre-mutex behavior over-listed the same case, so suppression is a strict
improvement even where it under-fires. Resolving abbreviations would mean
re-implementing argparse's prefix matching across the whole producer — a separate
concern, deferred.

## 7. Cache

*(S10 — see §"Roadmap" until landed.)*

## 8. Install

*(S11 — see §"Roadmap" until landed.)*

## 9. Ecosystem placement

The design twin is **argcomplete**: painted reuses the same `action.completer`
attribute convention, so a completer written for painted is portable to
argcomplete and back. The difference is philosophical — argcomplete's model is
"re-run the program under a completion monkeypatch," importing and partially
executing the app on every TAB; painted's gate intercepts *before* any render
machinery loads (§3). **shtab** was mined narrowly (the zsh `_describe`
colon-escape) but rejected as an engine — it generates a *static* script with no
dynamic callback. Compiled-language leaders (clap_complete, Cobra, carapace) beat
painted on breadth (shell count, install lifecycle, argument-group logic); those
are roadmap items, not design gaps. What painted adds that nothing else in the
Python ecosystem makes explicit: the render-free promise, structurally enforced,
because nothing else in the ecosystem is a rendering library that would pay for
it.

## 10. Slice topology (S1–S7, shipped)

The v1 arc, per-slice branches off umbrella `autocomplete`, merged `--no-ff`:

| Slice | Delivered |
|-------|-----------|
| S1 | Enablers: `build_parser` extracted render/fetch-free; `ArgsView`; `fetch` arity shim |
| S2 | `AppCommand.add_args` — one callback serves parse, `-h`, and completion |
| S3 | The producer: `complete_args` / `complete_app` / `complete_line`; the `.completer` seam; C-LAZY render-free TAB path |
| S4 | Shell integration: the gate, the transport, the zsh emitter; auto-injected `completion` command |
| S5 | Dogfood: `painted demos <TAB>` (render-free discovery) and `painted docs <TAB>` (honest renderer-loading contrast) |
| S6 | bash emitter (`completion bash`) |
| S7 | File/dir fallback (open-slot classification + `\x1f` directive) |

## 11. Roadmap

- **mutex-exclusions** (S9, this arc) — see §6.
- **cache** (S10, this arc) — see §7.
- **install-polish** (S11, this arc) — see §8.
- **fish / pwsh emitters** — deferred; `_EMITTERS` and the dialect-aware `_emit`
  make adding them cheap, but the shells aren't there yet.
- **`complete_via` sugar** — a declarative shorthand for attaching a completer,
  deferred until the `.completer` attribute proves ergonomically insufficient.
- **`help_args` → `add_args` cross-repo sweep** — loops uses `help_args` heavily
  but depends on *published* painted with no editable pin, so the migration is a
  coordinated, version-gated, cross-repo change. Deferred.
