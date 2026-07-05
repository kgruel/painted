# Errors — the exception hierarchy

**Status: RATIFIED 2026-07-05, implementation in flight** (branch
`exception-hierarchy`, PR off `main`). painted has raised bare stdlib
exceptions since its first commit — 19 `ValueError` and 3 `RuntimeError`
sites on `main` today, zero classes of its own. This document declares the
hierarchy, the classification rule that assigns every raise site to a class,
and the compatibility argument that makes the change semver-MINOR. Companion
to the vocabularies work (branch `declared-vocabularies`): the principle
ratified there — *validate every declaration, tolerate all data* — is the
axis this taxonomy is built on.

## 1. The evidence — why bare stdlib types stopped being enough

Three consumers pay for the missing hierarchy today:

1. **Apps can't discriminate painted faults from their own.** siftd's sync
   seam reads `except Exception:  # a rendering fault must not fail the
   push` — bare `Exception` because there is nothing narrower to name. A
   root class turns that into `except PaintedError` and lets non-painted
   bugs surface instead of being swallowed.
2. **Our own tests discriminate by message regex.** 70×
   `pytest.raises(ValueError)` in the suite, distinguished only by `match=`
   strings. Message text is not a contract; a class is.
3. **The vocabularies arc made the raise taxonomy load-bearing.** *Validate
   every declaration* means declaration faults must be loud, immediate, and
   never caught in production code. That behavioral contract deserves a name
   the type system can see, not a comment convention.

## 2. The hierarchy

```
PaintedError (Exception)
├── DeclarationError (PaintedError, ValueError)
├── ContractError   (PaintedError, ValueError)
└── LifecycleError  (PaintedError, RuntimeError)
```

Home: `src/painted/core/errors.py`. The classes are part of the
**semver-stable** surface — exported from `painted.core.__all__` and
re-exported from `painted.__all__`, guarded by `test_public_api.py`. They
live in `core` (not a top-level `errors.py`) because `cli` may import from
`core` but never the reverse; the renderer and the framework both raise
them, so they belong at the bottom of the import graph.

**`PaintedError`** — the root. Never raised directly; exists so a consumer
can write `except PaintedError` and mean "any fault painted itself
detected". Carries no fields in v1 — structure can be added additively
later if a consumer demonstrates the need.

**`DeclarationError`** — a malformed declaration, raised at
construction/registration time. Behavioral contract: *fix your code*. It
fires before any rendering happens (parser construction, runner
`__post_init__`, command registration), so an app that starts cleanly will
never see one at runtime. Production code must not catch it; tests assert
it.

**`ContractError`** — an API contract violated at call time: a value passed
to a render-path function that the contract rules out (a two-character
`Cell.char`, a `Block` row wider than its declared width, an unknown wrap
mode). Behavioral contract: *usually fix your code*, but an app feeding
semi-trusted data into a render path may legitimately catch it and fall
back.

**`LifecycleError`** — the right call in the wrong state
(`InPlaceRenderer.render()` outside its context manager). Behavioral
contract: fix the call *sequence*, not the value.

## 3. Dual inheritance — the compatibility argument

Each subclass also inherits the stdlib type it replaces
(`ValueError`/`RuntimeError`), the same pattern as
`json.JSONDecodeError(ValueError)`. Consequences:

- Every existing `except ValueError` and `pytest.raises(ValueError)` —
  ours and consumers' — keeps working unchanged. siftd and loops pin
  *published* painted; this ships without a coordinated floor-bump.
- The compatibility claim is **catch-compatibility**, precisely: `except`
  clauses and `str(exc)` are unchanged. The *type name* is visible wherever
  the class is displayed — `repr()`, interpreter traceback headers, and
  painted's own CLI error blocks now read `ContractError: …` instead of
  `ValueError: …`. That visible change is the feature, not a leak: the
  displayed name now tells the reader which behavioral contract was broken.
- The change is **semver-MINOR**: additive names, catch behavior preserved.
  Dropping the stdlib parents later would be semver-MAJOR; there is no
  plan to.

## 4. The classification rule

Assign by *when* the fault fires and *what the fix is*:

| Fires at | Fix is | Class |
|----------|--------|-------|
| construction / registration of a declared surface | the declaration | `DeclarationError` |
| call time, bad value | the value (or callsite) | `ContractError` |
| call time, bad state | the call sequence | `LifecycleError` |

Tie-breaker precedent: `CliRunner.__post_init__` validates `live_delivery`
at construction and its comment already reads "same promise as the
declaration collision checks" — construction-time misconfiguration of a
declared surface is `DeclarationError` even when the surface is a runner,
not a `Tag`. `Block.__init__` geometry checks are `ContractError`, not
`DeclarationError`: a `Block` is data built at render time, not a declared
surface — it has no registration moment.

## 5. Site table (normative, `main` scope)

**`DeclarationError`** (11 sites):

| Site | Fault |
|------|-------|
| `cli/types.py:326` | declared flag name not kebab-case |
| `cli/types.py:331` | declared flag collides with framework flag |
| `cli/types.py:333` | declared flag collides with another declaration |
| `cli/types.py:337` | depth alias maps to negative depth |
| `cli/types.py:415` | `add_args` dest collides with a declaration |
| `cli/app_runner.py:154` | command name declared twice |
| `cli/app_runner.py:161` | command aliases itself |
| `cli/app_runner.py:167` | alias listed twice on one command |
| `cli/app_runner.py:169,173` | alias collides with a name/alias |
| `cli/runner.py:117` | `live_delivery` not a known delivery |

**`ContractError`** (8 sites):

| Site | Fault |
|------|-------|
| `core/cell.py:69` | `Cell.char` not a single character |
| `core/block.py:114,117,122` | `Block` row/ids geometry mismatch |
| `core/block.py:218,697` | unknown wrap mode |
| `_sparkline_core.py:63` | unknown sampling strategy |
| `views/components/_callout.py:92` | unknown severity |

**`LifecycleError`** (2 sites): `inplace.py:87,121` — renderer used outside
its context manager.

**Untouched, by design:**

- `AttributeError` sites (module `__getattr__`, frozen-dataclass
  immutability) — the attribute protocol *requires* `AttributeError`;
  wrapping it would break `hasattr` and lazy-import machinery.
- `_CompletionArgError` — private argparse control flow inside the
  completion protocol, never crosses the public surface.
- `_doc_pages.py:435` `RuntimeError` — dev-only docs server; environmental
  failure, not a painted contract, and not in the wheel's supported surface.
- **The never-raise law is unaffected.** Delivery seams (diagnostics
  handler, traceback rendering) continue to catch bare `Exception` — the
  law is about *painted never crashing the host app*, which is broader than
  painted's own fault taxonomy.

## 6. Adoption

- **This PR**: the classes, the 21 reclassified sites above, targeted test
  tightening (`pytest.raises(DeclarationError)` etc. at representative
  sites), this doc, changelog.
- **0.6 fast-follow** (branch `declared-vocabularies`, before it merges):
  migrate its new raise sites — `vocabulary.py` validation (~20 sites,
  all `DeclarationError` except the two call-time ordered-op/membership
  checks, which are `ContractError`), `record_gutter` construction
  (`DeclarationError`), `PaintedHandler` empty-thresholds
  (`DeclarationError`).
- **Future arcs**: new raise sites must name a class from this doc. This is
  enforced, not prose: `test_raise_sites_use_painted_exception_classes`
  (architecture invariants) rejects a bare `raise ValueError`/`RuntimeError`
  in `src/painted` outside a rationale-carrying exemption list.

## 7. Non-goals and deferrals

- **Error codes / structured fields** — deferred until a consumer needs to
  branch on more than the class. Additive when it comes.
- **A warnings taxonomy** — painted currently emits no `warnings.warn`;
  out of scope until it does (the `paint()`/`show()` deprecation at 0.8 is
  the likely trigger — decide then).
- **Wrapping third-party/OS errors** (terminal I/O, `wcwidth`) — painted
  propagates environment failures as-is; the hierarchy names *painted's*
  faults only.
