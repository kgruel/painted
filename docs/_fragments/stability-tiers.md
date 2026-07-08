<!-- region:summary -->
`painted.core` + `painted.views` + `painted.display` are the **semver-stable** library surface (removing or renaming an `__all__` name is semver-MAJOR, guarded by `tests/unit/test_public_api.py`); `painted.cli` + `painted.tui` are the **evolving** framework surface that may change across minor versions.
<!-- /region -->

<!-- region:full -->
painted is one package with two stability tiers, so a single install gives you differential guarantees. `painted.core`, `painted.views`, and `painted.display` are the **semver-stable** library surface — a renderer is a thing you *call*, so its surface is held maximally stable. Depend on them freely: removing or renaming any name in their `__all__` is a **semver-MAJOR** break, guarded by `tests/unit/test_public_api.py`, which pins the surface as a committed snapshot and fails loudly on any removal or rename. Additions are fine — they are semver-minor and freely allowed; extend the snapshot once you intend to commit to a new name's stability. `painted.display`'s `show()` is the one pre-declared exception: its removal at 1.0 is a scheduled semver-MAJOR event riding the deprecation horizon `docs/PAINT_DESIGN.md` documents, not a surprise break.

`painted.cli` and `painted.tui` are the **evolving** framework surface — they *call you*, and churn as apps' needs change, so they may change across minor versions. Together this resolves the library-vs-framework version tension without splitting the package.
<!-- /region -->
