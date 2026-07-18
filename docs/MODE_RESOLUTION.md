# Mode Resolution Rules

How `CliRunner` resolves the output mode when the user doesn't explicitly choose one.

Types live in `cli/types.py`. `CliRunner` and `run_cli` live in `cli/runner.py`.

## The Three Axes

```
ZOOM / FIDELITY (what to show)   OUTPUT MODE (how to deliver)
├─ 0: MINIMAL (-q/--quiet)       ├─ STATIC: print and scroll
├─ 1: SUMMARY (default)          ├─ LIVE: cursor-controlled updates
├─ 2: DETAILED (-v)              └─ INTERACTIVE: alt screen + keyboard
└─ 3: FULL (-vv)

FORMAT (serialization)
├─ ANSI: styled terminal (TTY default)
├─ PLAIN: no styles (pipe default)
└─ JSON: machine-readable (--json)
```

`Zoom` is a flat integer (0–3). `Fidelity` is a richer alternative that bundles
depth (same int as Zoom), a `visible` tag set for semantic layers, and `chars`/`lines`
density budgets. `CliContext` carries `Fidelity` as its canonical field; `ctx.zoom`
is a backward-compat property returning `Zoom(fidelity.depth)`.

Zoom/fidelity, mode, and format are orthogonal in principle. Mode resolution is where
they interact — certain zoom/format choices constrain which modes make sense.

## Mode Resolution

When the user passes `--static`, `--live`, or `-i`, that's final. Resolution
only applies to AUTO (no explicit flag).

### Rule: Capability Filtering

`CliRunner` infers which modes the CLI actually supports:

| Config present | Modes registered |
|----------------|-----------------|
| (always) | STATIC, INTERACTIVE |
| `fetch_stream` | + LIVE |

INTERACTIVE is always registered since 0.13 (the host rung mounts any binding);
`handlers[INTERACTIVE]` still overrides the framework host rung when present.

Only supported modes get argparse flags. A CLI without `fetch_stream` never
shows `--live` in `--help`.

### Rule: AUTO Collapse

When mode is AUTO, certain conditions force STATIC:

| Condition | Why |
|-----------|-----|
| `--json` | Machine-readable output; cursor control would corrupt JSON |
| `--plain` | No ANSI codes; cursor control requires ANSI escape sequences |
| `-q` (MINIMAL) | One-liner output; animation overhead is wasteful |
| Pipe (not TTY) | No terminal to animate; print and exit |

Otherwise AUTO resolves to the highest supported mode:
- TTY with LIVE available → LIVE
- TTY without LIVE → STATIC

### Resolution Order

```
User passes explicit mode flag?
  yes → use it (--static, --live, -i)
  no  → AUTO
         │
         ├─ --json?   → STATIC
         ├─ --plain?  → STATIC
         ├─ -q?       → STATIC
         ├─ pipe?     → STATIC
         └─ TTY?      → LIVE (if supported) or STATIC
```

### Rule: Flag Visibility

`--help` only shows flags for modes the CLI supports. This prevents user
confusion ("why does `-i` do nothing?").

Since 0.13 (the host rung, `docs/HOST_RUNG_DESIGN.md`) **INTERACTIVE is always
supported**: `-i` mounts *any* renderer binding into an alt-screen `HostSurface`
on a usable TTY (falling back to LIVE off a TTY), so it is never a no-op and
`run_cli` offers it unconditionally. `--live` still follows the honesty rule —
it exists only when `fetch_stream` is declared.

**ANSI stays context-derived, never mode-granted.** Requesting `-i` does not
manufacture ANSI the destination can't render: `use_ansi` follows the *TTY*, so
`-i` into a pipe resolves `use_ansi=False` and the degraded LIVE route emits the
same clean, non-ANSI output the pipe would otherwise get — no alt-screen escapes,
no cursor control. On a real TTY the interactive path gets ANSI via `is_tty` like
every other delivery; there is no INTERACTIVE special case in `detect_context`.

| CLI capabilities | Flags shown |
|-----------------|-------------|
| Static only (no stream) | `-i`, `--static` |
| Static + Live (a stream) | `-i`, `--static`, `--live` |

`--static` is the "force no animation" escape hatch; `-i` forces the interactive
host rung; `--live` (when present) forces in-place/surface live.

## Design Rationale

### Why MINIMAL implies STATIC

`-q` produces a one-liner (e.g., `4/6 healthy  1 degraded  1 down`). Firing
up `InPlaceRenderer` for a single line that never changes is pure overhead.
The output is already minimal — animation adds nothing.

### Why PLAIN implies STATIC

`--plain` strips ANSI codes. Cursor-controlled rendering (`InPlaceRenderer`)
works by writing ANSI escape sequences to move the cursor and overwrite
previous output. Without ANSI, the cursor stays put and each "frame" appends
below the last — producing garbage. PLAIN and LIVE are mechanically
incompatible.

### Why capability filtering exists

Without filtering, every CLI shows `-i`, `--live`, and `--static` regardless
of whether those modes do anything. The rule is the honesty rule applied to
modes: offer a flag only when it delivers. `--live` still obeys this (no
`fetch_stream`, no `--live`). `-i` no longer needs it: the host rung
(`docs/HOST_RUNG_DESIGN.md`) makes INTERACTIVE deliver for *any* binding, so
`-i` is honest everywhere and is offered unconditionally — the capability
existing is what satisfies the rule, not the gating. A custom
`handlers[INTERACTIVE]` still overrides the framework host rung; a declared
surface stream still converges `-i` onto `StreamSurface`.

## Non-Rule: Format Never Implies Mode (Except for Collapse)

`--plain` collapses AUTO to STATIC, but it doesn't prevent `--plain --live`
if the user explicitly asks. Explicit flags are respected even when the
combination is unusual. The collapse rules only govern AUTO resolution.
