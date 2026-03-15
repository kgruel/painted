# Autoresearch Ideas — painted import surface

## Initial hypotheses

- `import painted.core` should be close to the floor after the lazy top-level
  import refactor. If it is still expensive, the cost is likely inside
  `painted.core` itself rather than the root package.
- `from painted import run_cli` may still overpay because `painted.cli.__init__`
  eagerly imports help, app runner, and the main runner.
- `from painted import show` should stay lighter than `run_cli`, but it still
  imports display + CLI context/types + icon-set support up front.

## Likely optimization paths

- **Lazy `painted.cli` facade:** make `painted.cli.__init__` mirror the root
  package and defer `help`, `app_runner`, and `runner` until needed.
- **Split help path from run path:** if `run_cli_import_ms` is high, move help
  rendering imports out of the base runner import surface.
- **Keep `show` on a narrower dependency diet:** if `show_import_ms` is high,
  revisit whether display needs the full CLI vocabulary at import time.
- **Track module creep:** if `core_import_modules` grows over time, add a hard
  regression test around the allowed import set.
- **Memory over latency tradeoffs:** if a faster import path increases peak KiB
  substantially, keep both metrics visible rather than chasing raw ms only.

## Nice-to-have follow-ups

- Add a `__dir__` implementation for lazy root exports so REPL discoverability
  stays good without forcing eager imports.
- Add a dedicated smoke test for `from painted import *` if the root facade
  becomes more dynamic over time.
