# Invariant Audit Remediation Plan

Source: a multi-agent invariant audit (7 finder dimensions × adversarial verification)
run against documented invariants that `tests/unit/test_architecture_invariants.py`
does **not** already cover. 9 violations confirmed; 1 more (`ProfileResult.flame_dict`)
surfaced while enumerating blast radius for the generalized static checks.

Two dimensions came back clean — **lazy-imports** (cli/fidelity has no module-level
renderer imports) and **render-purity** (component/lens render fns are pure). Those
invariants hold today.

## Governing idea

This is the *fan-out form* of `test_architecture_invariants.py`. That file asserts
invariants a static AST pass can check; the audit found the invariants that need
*reading and judgment*. The remediation loop is: **demote each judgment-level finding
into a mechanical check** where possible (Tier 1), and pin the rest with behavioral
regression tests (Tier 2). What becomes mechanizable moves into the arch test; what
can't is locked by a targeted test.

Property-vs-golden split (from the test-suite design discussion): Tier 1 = static
contract checks (Tier 0 of the fail-fast staircase). Tier 2 = behavioral/property
tests — a `len(`/`[:width]` grep is all false positives, which is *why* these belong
in the property tier, not a static scan.

## Sequencing

1. This plan doc (durable staging artifact). ✅
2. Red → green per finding, fix landing **with** its guard test.
3. `./dev check` last (arch → lint → unit → golden → outputgen).

---

## Tier 1 — Generalized static guards (catch the whole class)

Decision: **general form, not scoped.** Inventory confirms it ships green-after-fix:
- Non-frozen dataclasses in all of `src/painted`: exactly 3 — `CellWrite` (fix),
  `FrameRecord` + `CliRunner` (allowlist as intentionally mutable).
- Frozen dataclasses with unguarded mutable-collection fields: exactly 3 —
  `AppCommand.help_args`, `IconSet.spinner` (fix via tuple coercion),
  `ProfileResult.flame_dict` (allowlist — see below).

A *scoped* check (core/ + views/ only) would have **hidden** `ProfileResult`. The
general form catching the sampled-missed case is the pattern-over-point-solution win.

### Test A — runtime imports must be stdlib or explicitly allowlisted
**Covers #3, #4 (wcwidth in `_text_width.py`, `writer.py`, `buffer.py`, `span.py`).**

The finding is a **docs defect, not a code defect.** `core/__init__.py` documents the
real contract as "no runtime dependencies beyond wcwidth"; wcwidth is the single
deliberate exception. The top-level CLAUDE.md overstates it as "standard library."

- New test `test_runtime_imports_are_stdlib_or_allowlisted`: rglob `src/painted`,
  collect **module-level** imports (walk `tree.body`, descend into non-`TYPE_CHECKING`
  `If` nodes only — type-only imports are exempt), assert top package ∈
  `sys.stdlib_module_names` ∨ `startswith("painted")` ∨ `_ALLOWED_RUNTIME_DEPS = {"wcwidth"}`.
- Companion docs fix: reword `CLAUDE.md` and `src/painted/CLAUDE.md` "zero runtime deps
  beyond standard library" → "beyond wcwidth (the single vetted exception)".
- **Red demo**: confirm it flags wcwidth *before* adding it to the allowlist (proves it
  catches a future unsanctioned `import requests`), then allowlist + reword.

### Test B — dataclasses frozen unless explicitly allowlisted as mutable
**Covers #7 (`CellWrite`).** Inverts the blind spot that let CellWrite slip the current
name-suffix test (it doesn't end in `State`).

- New test `test_dataclasses_frozen_unless_allowlisted`: AST-walk every `@dataclass`;
  for any with `frozen is not True`, assert its name ∈ `_MUTABLE_DATACLASSES`.
- `_MUTABLE_DATACLASSES = {"FrameRecord", "CliRunner"}` with inline rationale
  (timing accumulator; runtime parser-cache + callable holder).
- Fix: `core/buffer.py` `CellWrite` → `@dataclass(frozen=True, slots=True)`. Its union
  sibling `ScrollOp` is already frozen — restores consistency.

### Test C — frozen dataclasses must coerce/allowlist mutable-collection fields
**Covers #8 (`AppCommand.help_args`), #9 (`IconSet.spinner`).**

- New test `test_frozen_dataclasses_guard_mutable_collection_fields`: AST-walk
  `@dataclass(frozen=True)` classes; flag a field whose annotation top-level name ∈
  {list, dict, set, List, Dict, Set, Sequence, Mapping, MutableSequence, MutableMapping}
  unless the class defines `__post_init__` **or** `(Class, field)` ∈ allowlist.
- `_DICT_FIELD_ALLOWLIST = {("ProfileResult", "flame_dict")}` — nested arbitrary `Any`;
  internally produced by `profile()`; deep-freeze impractical; shallow `MappingProxyType`
  would fake immutability (rejected, explicit-over-implicit).
- Fixes (tuple coercion via `__post_init__` + `object.__setattr__`, matching the
  `Block`/`test_block_defensively_freezes_rows` convention):
  - `AppCommand.help_args`: annotation → `Sequence[HelpArg] | None`, coerce to tuple.
  - `IconSet.spinner`: annotation stays `Sequence[str]`, coerce to tuple.
- Runtime companion mirroring `test_block_defensively_freezes_rows`: construct each with
  a caller-owned list, mutate the list, assert the field is a tuple and unaffected.

---

## Tier 2 — Behavioral regression tests (no clean static check exists)

### Test D — table() stays column-aligned with a wide/multi-codepoint separator
**Covers #1.** `views/components/table.py:148` `sep_width = len(separator)` desyncs columns
when a caller passes a wide-glyph border separator (every shipped preset is width-1, so
latent). Fix: `display_width(separator)` (add `from ...core._text_width import display_width`).

### Test E — chart_lens preserves the value column for emoji/combining labels
**Covers #2.** `views/lens/chart.py:202` `row_text[:width]` is a codepoint slice that drops
the trailing value text when `len > display_width` (emoji/combining marks). Verifier
reproduced active corruption. Fix: drop `[:width]`; rely on width-aware
`Block.text(row_text, Style(), width=width)`.

### Test F — record_line emits no embedded-newline rows at any zoom (default lens)
**Covers #5, #6.** `views/record.py`: at MINIMAL/SUMMARY/DETAILED a payload value with `\n`
produces a row claiming `height=1` that renders 2+ terminal rows and **breaks the gutter
rail**. Only FULL calls `splitlines()`. Fix: collapse newlines at source via
`" ".join(s.splitlines())` — in `_default_payload_summary` (MINIMAL/SUMMARY) and the
DETAILED continuation-field loop. FULL unchanged.

**Boundary (do not overclaim):** this fix + Test F close the **default-lens** path only. A
custom `payload_lens` returning multiline still breaks the rail — a lens-side contract
violation Test F does not cover. A single assertion in record_line's row assembly would
catch *any* multiline leak regardless of lens; deferred as a named design choice, not
silently added.

---

## Summary

| Test | Covers | Type | Fix |
|------|--------|------|-----|
| A | #3, #4 | Static + `sys.stdlib_module_names` | docs reword + wcwidth allowlist |
| B | #7 | Static AST | CellWrite → frozen |
| C | #8, #9 | Static AST + runtime companion | tuple coercion; ProfileResult allowlisted |
| D | #1 | Behavioral | `display_width(separator)` |
| E | #2 | Behavioral | drop `[:width]` |
| F | #5, #6 | Behavioral | collapse newlines at source |

10 violations → 6 tests + 3 code fixes + 2 coercions + 1 docs reword + 1 ripple
(`help_args_to_flags` parameter widened `list` → `Sequence` for the tuple coercion).
Watch for golden fallout on the record_line change (others are output-preserving for
inputs in current goldens).
