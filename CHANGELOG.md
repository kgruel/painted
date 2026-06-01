# Changelog

All notable changes to painted are documented here. This project adheres to
[Semantic Versioning](https://semver.org/); pre-1.0, minor versions may carry
breaking changes.

## [0.2.0] — 2026-06-01

### Removed (breaking)

- **Deep submodule import paths.** Backing submodules were made private to close a
  latent import-order shadowing bug. `painted.views.profile` and
  `painted.views.components.{spinner,table,list_view,text_input,data_explorer,sparkline}`
  no longer resolve. **The public names are unchanged** — import them through the
  `painted.views` facade (e.g. `from painted.views import table, spinner, profile`),
  which has always been the supported path.

### Changed

- **`width` is now an exact contract.** Passing `width` makes `block.width == width`
  exactly: too-wide content is clipped (padded if short) by default; pass
  `wrap=Wrap.CHAR`/`Wrap.WORD` to reflow into more rows instead. Omit `width` for
  natural content sizing. Threaded through lenses, records, and composers so a width
  budget can be subdivided and the pieces tile.
- **Test architecture overhauled.** The demo-text golden tier is retired in favor of
  smoke + Hypothesis property + structured char/style appearance + integration
  tiers. `./dev check` is now a 9-tier gate, including a single-process Cohesion tier
  that catches cross-test state leaks the per-tier runs can't see.

### Fixed

- `record_line_composed` no longer drops content cells — the attention marker's
  columns are budgeted so the final width-fit is a no-op, not a right-edge clipper.
- `record_line_composed` evaluates `attention_fn` exactly once (was twice), so
  stateful or non-pure scorers reserve and render with the same score.
- `record_timeline([])` and `record_map([])` honor the exact-width contract (their
  empty "(no records)" branch was natural-width).

### Added

- Architecture guard `test_public_names_do_not_shadow_submodules` — fails if any
  package re-exports a public name that collides with one of its own submodule files.
