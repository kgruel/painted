# Diagnostics — logging and tracebacks as renders

**Status: IMPLEMENTED 2026-07-04** (branch `semantic-logging-tracebacks`,
slices S1–S4 — S1 hardened `shape_lens`, S2 built `render_traceback`, S3 the
delivery glue, S4 this doc + demo + changelog). painted renders the two
diagnostic surfaces every program already produces — log records and uncaught
tracebacks — as structured Blocks disclosed by zoom, not format strings. This
document is the design of record. Companion to `docs/FIDELITY_DESIGN.md`
(disclosure) and `docs/COMPLETION_DESIGN.md` (the parser's reflections): those
gave two axes their contract; this applies the same *declared-meaning* thesis to
diagnostics.

## 1. The thesis — three declarations

Every diagnostic painted renders is a projection of a declaration already in the
data. Nothing is invented; the rendering derives.

1. **A log level is a declared severity.** `levelno` thresholds collapse onto the
   closed 4-level `Severity` vocabulary. The threshold mapping *is* the
   declaration — a record renders in the role of the greatest floor it clears.
2. **A traceback is a record tree.** Frames are records (`file:line in func` rows
   on a continuous gutter rail); cause/context chains and `ExceptionGroup`s are
   the tree that connects them. **Capture is the declaration** —
   `TracebackException.from_exception` freezes a live exception into frame-free
   plain data, so a rendered traceback is a projection of declared meaning, not a
   snapshot of live interpreter state.
3. **A dataclass is a declared schema.** `fields()` derive the rendering on the
   spine (S1's `shape_lens` hardening); dict/list duck-typing stays exploration
   mode. `repr=False` is declared suppression and is honored — a field the schema
   hides is not rendered.

## 2. The substrate-sharing argument — why one arc, not three features

The three surfaces are not independent. `render_traceback`'s FULL-zoom locals
route each value back through the *same* `shape_lens` that `show()` uses — so a
cyclic or unrepresentable local can't crash the error renderer only because S1
first made `shape_lens` cycle-safe, depth-capped, and schema-aware. That was a
real latent bug (a self-referential container raised `RecursionError` in
`show()` before this arc), fixed as the substrate the traceback renderer stands
on. And `PaintedHandler.emit` composes `render_traceback` for `exc_info` — the
handler doesn't re-derive traceback structure, it mounts the S2 renderer. One
hardening (S1) is consumed by two deliverers (S2, S3); the arc is the shared
substrate, which is why it ships as one branch rather than three.

## 3. The seam resolution — why root, why not cli

`PaintedHandler` and `install` are delivery glue: they connect an external
runtime surface (the `logging` machinery, `sys.excepthook`) to the renderer.
That is the same shape as `run_cli` connecting argv to the renderer — so the
instinct is to put it under `cli/`. **It does not go there.**

`painted/cli/` is held to a frozen tripwire: `_CLI_SEAMS` is fixed at two, and
nothing in `cli/` may import `views` (`docs/LIVE_DELIVERY_DESIGN.md` §9 ratified
"re-layer, never relax" — a third seam triggers extracting a named delivery
layer, never a third entry in the allowlist). Diagnostics glue *must* import
`views` (it renders `render_traceback`), so putting it in `cli/` would either
break the tripwire or force a premature delivery-layer extraction for a surface
that is not a CLI at all — a log handler and an excepthook are not argv-driven.

The resolution: the glue lives at the package **root** (`painted/diagnostics.py`),
which may import `views` and `core` freely — the standing precedent is
`inplace.py` and the root `__init__.py` facade itself. `PaintedHandler` /
`install` / `DEFAULT_THRESHOLDS` export through the root `painted.__init__`
facade (`__all__` + `_LAZY_IMPORTS`), **not** the `views` snapshot, so they are
part of the evolving surface, not the semver-stable `core`/`views` contract. The
smoke tier auto-verifies the facade resolves. No CLI involvement, `_CLI_SEAMS`
untouched.

## 4. `render_traceback` — the zoom ladder

`render_traceback(exc, zoom, width, *, suppress=(), redact=default_redact)`.
Accepts a live `BaseException` (captured internally — `capture_locals` only at
FULL) or a pre-captured `TracebackException` (rendered as-is; this is the
serializable / Fact-friendly boundary). Each rung is additive — climbing never
rewrites the rung below:

| Rung | Adds |
|------|------|
| MINIMAL  | type + message + innermost app frame, one line |
| SUMMARY  | + the frame stack (one line/frame), suppressed frames folded, chains summarized |
| DETAILED | + source ±1 with a caret, chains fully rendered |
| FULL     | + source ±3, redacted + budgeted locals, groups fully expanded |

Load-bearing contracts:

- **The gutter encodes exactly ONE dimension — frame origin.** App frame keeps
  the default weight; a suppressed / library frame is muted. The rail is
  continuous and never breaks (the `record_line` gutter law).
- **`suppress` is declared and output-changing.** Frames whose module path
  contains a `suppress` substring fold to one muted `… N frames in <module> …`
  line. Same exception with suppress on/off *must* differ (honesty test).
- **Carets are display-column-correct.** `colno`/`end_colno` are byte offsets;
  they are converted to display columns (tabs expanded as the rendered line
  expands them, prefix measured with `display_width`) so wide / zero-width source
  characters never misalign the `^^^` run.
- **Locals are redacted then budgeted.** `default_redact` masks names matching
  `password|secret|token|key|api` (case-insensitive) to `∙∙∙ redacted` — the
  value never reaches a `repr`. Surviving values route through the hardened,
  cycle-safe `shape_lens` path with tight budgets.
- **Chains and groups are the tree.** `__cause__` ("The above exception was the
  direct cause…", error role), `__context__` when not suppressed ("During
  handling… another exception occurred", warning role), and `ExceptionGroup`
  `.exceptions` as a tree of recursive bodies.

`render_traceback` is exported from `views.__all__` (semver-stable) and pinned in
`STABLE_VIEWS_SURFACE`. `default_redact` stays module-importable but **unlisted**
— it is the default argument of `render_traceback`, not a standalone view.

## 5. `PaintedHandler` and `install` — the delivery glue

`PaintedHandler(logging.Handler)` is a **renderer, not a formatter**: it
overrides `emit`, builds a Block (timestamp + severity-styled level + logger name
+ message + `extra` fields as payload continuation per zoom + any `exc_info`
traceback), and writes it atomically (one `.write` + flush) under the handler
lock. `setFormatter` still works — but only for the **message string**; the
structure (rows, gutter, traceback) stays painted's.

- **`DEFAULT_THRESHOLDS`** (the declaration point): `DEBUG→INFO` (the journalctl
  principle — routine noise stays muted), `INFO→INFO`, `WARNING→WARNING`,
  `ERROR→ERROR`, `CRITICAL→ERROR` (the palette has no louder role than error;
  Severity stays the closed 4-level set). A custom mapping must change output
  (honesty test).
- **Construction snapshot.** `current_palette()` and the stream's color depth are
  captured in `__init__`. A `ContextVar` palette does not cross threads, so a
  worker-thread log must render with the aesthetic the main thread declared —
  `emit` wraps build + write in a single `use_palette(snapshot)` so both the
  header styling and `render_block_ansi`'s late palette resolution see it. A
  piped stream detects `ColorDepth.NONE` → plain text.
- **`exc_info` → `render_traceback`, capped at `traceback_zoom`.** The composition
  point: `min(handler_zoom, traceback_zoom)` — a ceiling, so a FULL handler with
  the default DETAILED ceiling won't dump locals into a log line.
- **Failure discipline.** Any render error → `self.handleError(record)` (respects
  `logging.raiseExceptions`). A log emitted *during* our own render is caught by a
  thread-local reentrancy guard → a plain `record.getMessage()` one-liner rather
  than an infinite recursion.

`install(*, zoom=Zoom.DETAILED, width=None, suppress=(), threads=False)` routes
`sys.excepthook` through `render_traceback` + `print_block(stderr)`.
`KeyboardInterrupt` passes through to the default hook. `threads=True` is an
opt-in declared capability that additionally sets `threading.excepthook`. The
tested invariant: the installed hook's output is **byte-identical** to the
explicit `print_block(render_traceback(...))` path for the same exception and
params — the hook is glue, not a second renderer.

## 6. Scope cuts, with revisit triggers

- **attrs / pydantic schema detection — DEFERRED.** S1's schema branch handles
  stdlib `@dataclass`, `NamedTuple`, and `Enum` only. `attrs` is not imported and
  not duck-detected. *Trigger:* a second consumer whose values are predominantly
  attrs/pydantic instances, at which point the branch takes a small registry of
  `(detect, to_dict)` pairs rather than a hard `import attr`.
- **`inspect_lens` / a reflection register — NOT BUILT.** Rendering a live object
  by reflecting its methods/signature (as opposed to its declared fields) is
  exploration mode by another name; it belongs with `show()`'s duck-typing, not
  on the diagnostics spine. *Trigger:* a concrete debugging workflow that the
  schema branch can't serve.
- **Syntax highlighting (pygments) — REJECTED, chosen non-goal.** Zero runtime
  deps beyond wcwidth is a hard constraint, and the design bet is that
  *structure and severity* emphasis (the gutter, the caret, the accent on the
  failing line) reads better in a terminal diagnostic than token coloring. Not a
  gap; a decision.
- **Markup / rich-text log messages — NEVER.** A log message is a string; the
  Cell substrate neutralizes control characters. Structure comes from the record
  (level, logger, `extra`, `exc_info`), never from parsing the message body.
- **fish / pwsh-style future surfaces — none.** Diagnostics has no shell-emitter
  axis; the completion doc's fish/pwsh roadmap has no analogue here.

## 7. Slice topology (S1–S4, shipped)

| Slice | Delivered |
|-------|-----------|
| S1 | `shape_lens` hardened: cycle detection (real `RecursionError` fix), depth cap, declared-schema branch (dataclass / NamedTuple / Enum, `repr=False` honored) — the substrate |
| S2 | `render_traceback` (`views/_traceback.py`, stable export): the record tree, zoom ladder, suppress fold, display-correct carets, chains + groups, redacted + budgeted locals |
| S3 | Delivery glue (`painted/diagnostics.py`, root): `PaintedHandler` (severity thresholds, construction snapshot, `exc_info` composition, reentrancy guard), `install` (byte-identical excepthook, opt-in `threads`) |
| S4 | This design-of-record + the doc-IR `diagnostics` page + the primitive demos (`diagnostics` for render_traceback, `logging_handler` for the delivery glue) + CHANGELOG |
