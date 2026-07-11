"""Stable-surface guard — the semver-major tripwire for painted's public API.

painted is one package with two stability tiers (see CLAUDE.md "Stability
tiers"):

  * ``painted.core`` + ``painted.views`` + ``painted.display`` +
    ``painted.publish`` — the **semver-stable** library. A renderer is a thing
    you *call*; its surface should be maximally stable. ``painted.display`` is
    the entry-point module: ``paint()``'s closed kwarg surface is a public ABI,
    and ``show`` — though deprecated — carries a documented 1.0 removal
    horizon, so its presence is a commitment until then. loops imports from
    ``painted.display`` directly (the submodule path), so this surface is
    load-bearing for a real consumer. ``painted.publish`` is its
    foreign-semantics sibling (the doc-IR publisher, 0.10): loops' article
    publisher is the second world that made it library surface.
  * ``painted.cli`` + ``painted.tui`` — the **evolving** frameworks. They *call
    you*, and churn as apps' needs change.

This test pins the stable surface as a committed snapshot. Removing or renaming
any name below is a **semver-major break** for downstream consumers (loops,
siftd, fidelis), and this test is the tripwire that makes that break loud at
commit time rather than silent at some consumer's next upgrade. It is the
in-repo continuation of the contract precedent set by the width arc: *state the
contract → encode it as a law → guard it* — never let a published guarantee live
only in prose.

The guard is bidirectional: the snapshot must equal ``__all__`` exactly.
  * Removing/renaming a snapshotted name -> FAILS (semver-major break).
  * Publishing a name in ``__all__`` that is not in the snapshot -> FAILS too.

The second direction is deliberate. ``painted.core``/``painted.views``/
``painted.display`` are *wholly* the semver-stable surface: a name in their
``__all__`` is already a published stable name — there is no "stage it now,
commit to it later" state for these namespaces (that's what the evolving
``painted.cli``/``painted.tui`` are for). An earlier one-directional guard let an addition ship silently unsnapshotted
— ``callout`` and ``Overflow`` both reached ``views.__all__`` in the 0.4.0 batch
while the snapshot, and the green suite, said nothing. Requiring equality forces
every new stable export to be a conscious entry here, reviewed in the diff — it
catches the *omission*, not just the removal.

Resolution is checked too: every snapshotted name must actually resolve through
the module's lazy ``__getattr__``. The smoke tier checks this for the root
``painted.__all__`` facade only — the ``core``/``views`` namespaces are not
covered there, so a broken ``_LAZY_IMPORTS`` mapping on the stable surface would
otherwise slip through.
"""

from __future__ import annotations

import painted.core
import painted.display
import painted.views

# --- The committed stable surface ---------------------------------------------
# Edits here are API-contract decisions, reviewed in the diff. Do not regenerate
# mechanically: a removal that "fixes the test" is exactly the break it exists to
# catch.

STABLE_CORE_SURFACE = frozenset(
    {
        # Errors
        "PaintedError",
        "DeclarationError",
        "ContractError",
        "LifecycleError",
        # Primitives
        "Style",
        "Cell",
        "EMPTY_CELL",
        "Span",
        "Line",
        # Blocks
        "Block",
        "Wrap",
        # Composition
        "Align",
        "join_horizontal",
        "join_vertical",
        "join_responsive",
        "pad",
        "border",
        "rule",
        "truncate",
        "fit_to_width",
        "vslice",
        "budget_fields",
        "BudgetFit",
        # Measurement
        "display_width",
        # Borders
        "BorderChars",
        "ROUNDED",
        "HEAVY",
        "DOUBLE",
        "LIGHT",
        "ASCII",
        "current_borders",
        "use_borders",
        "reset_borders",
        # Buffer
        "Buffer",
        "BufferView",
        "CellWrite",
        # Rendering constraint
        "Zoom",
        # Doc-IR (node vocabulary + doc_lens, the one-way door opened at 0.10;
        # visible_body/capped deliberately unexported — see DOC_IR_DESIGN.md)
        "Doc",
        "Section",
        "Prose",
        "Def",
        "Defs",
        "Items",
        "Code",
        "Figure",
        "Link",
        "doc_lens",
        # Output
        "Writer",
        "ColorDepth",
        "print_block",
        "render_html",
    }
)

STABLE_VIEWS_SURFACE = frozenset(
    {
        # Aesthetic
        "Palette",
        "DEFAULT_PALETTE",
        "NORD_PALETTE",
        "MONO_PALETTE",
        "PAINTED_PALETTE",
        "current_palette",
        "use_palette",
        "reset_palette",
        "IconSet",
        "ASCII_ICONS",
        "current_icons",
        "use_icons",
        "reset_icons",
        # Borders (re-exported for view-layer ergonomics)
        "BorderChars",
        "ROUNDED",
        "HEAVY",
        "DOUBLE",
        "LIGHT",
        "ASCII",
        "current_borders",
        "use_borders",
        "reset_borders",
        # Theme
        "Theme",
        "DEFAULT_THEME",
        "NORD_THEME",
        "MONO_THEME",
        "PAINTED_THEME",
        "use_theme",
        "reset_theme",
        # Vocabularies (the mark channel)
        "Role",
        "Vocabulary",
        "Thresholds",
        "use_vocabularies",
        "current_vocabularies",
        "reset_vocabularies",
        "mark_style",
        # Ref schemes (the denotation channel's sibling declaration, 0.7)
        "RefScheme",
        "use_refs",
        "current_ref_schemes",
        "reset_refs",
        "resolve_ref",
        # Stateless views
        "NodeRenderer",
        "shape_lens",
        "tree_lens",
        "chart_lens",
        "flame_lens",
        "render_traceback",
        "sparkline",
        "sparkline_with_range",
        "cost_meter",
        # Callout (severity-tagged message)
        "callout",
        "Severity",
        "SpinnerState",
        "SpinnerFrames",
        "spinner",
        "DOTS",
        "LINE",
        "BRAILLE",
        "ProgressState",
        "progress_bar",
        "render_big",
        "BigTextFormat",
        "BIG_GLYPHS",
        # Stateful views
        "ListState",
        "list_view",
        "TableState",
        "Column",
        "AUTO",
        "Fill",
        "Overflow",
        "EllipsisSide",
        "table",
        "TextInputState",
        "text_input",
        "DataExplorerState",
        "DataNode",
        "data_explorer",
        "flatten",
        # Profile bridge
        "ProfileResult",
        "profile",
        "parse_collapsed",
        # Record rendering
        "PayloadLens",
        "GutterFn",
        "AttentionFn",
        "record_line",
        "record_timeline",
        "record_map",
        "record_line_composed",
        "apply_gutter",
        "apply_attention",
        "record_gutter",
        "gutter_lifecycle",
        "gutter_freshness",
        "gutter_pass_fail",
        "attention_staleness",
        "attention_novelty",
        "attention_blocked",
        "attention_relevance",
    }
)


STABLE_DISPLAY_SURFACE = frozenset(
    {
        # The single entry point (0.8+) and its deprecated warn-and-narrow alias.
        "paint",
        "show",
    }
)


STABLE_PUBLISH_SURFACE = frozenset(
    {
        # The doc-IR publisher (0.10): a root module beside display.py — the
        # terminal-side entry and the foreign-semantics side, siblings.
        # to_markdown joins here if it ever lands (DOC_IR_DESIGN.md).
        "to_html",
        "published_fidelity",
        # Section anchors (0.10.1): headed sections are addressable; the map is
        # public so a consumer's outline walk uses the SAME ids to_html stamps
        # (the loops article regexed painted's HTML to inject these — the
        # workaround this seam dissolves).
        "section_anchors",
    }
)


def _removed(snapshot: frozenset[str], current: list[str]) -> set[str]:
    return set(snapshot - set(current))


def _unsnapshotted(snapshot: frozenset[str], current: list[str]) -> set[str]:
    return set(current) - snapshot


class TestStableCoreSurface:
    def test_no_removals_or_renames(self) -> None:
        """Every snapshotted core name is still published in ``core.__all__``."""
        removed = _removed(STABLE_CORE_SURFACE, painted.core.__all__)
        assert not removed, (
            "semver-MAJOR break: painted.core dropped/renamed stable names "
            f"{sorted(removed)}. If intentional, this is a major-version change — "
            "update the snapshot in this test deliberately."
        )

    def test_no_unsnapshotted_additions(self) -> None:
        """Every name published in ``core.__all__`` is in the snapshot.

        ``painted.core`` is wholly semver-stable, so a published name is a
        committed name — it must be entered here deliberately, not slip in
        unguarded against a future rename/removal."""
        extra = _unsnapshotted(STABLE_CORE_SURFACE, painted.core.__all__)
        assert not extra, (
            "painted.core publishes stable names not in the snapshot: "
            f"{sorted(extra)}. Add them to STABLE_CORE_SURFACE — a name in the "
            "stable namespace's __all__ is a permanent public commitment and must "
            "be guarded against future rename/removal."
        )

    def test_every_stable_name_resolves(self) -> None:
        """Every snapshotted core name resolves through the lazy facade."""
        unresolved = []
        for name in sorted(STABLE_CORE_SURFACE):
            try:
                getattr(painted.core, name)
            except (AttributeError, ImportError) as exc:
                # AttributeError: wrong/missing attribute in the lazy mapping.
                # ImportError (incl. ModuleNotFoundError): wrong module path.
                # Either is a broken stable export — report it, don't let it
                # surface as an uncaught error.
                unresolved.append(f"{name}: {exc}")
        assert not unresolved, "painted.core stable names that do not resolve:\n" + "\n".join(
            unresolved
        )


class TestStableViewsSurface:
    def test_no_removals_or_renames(self) -> None:
        """Every snapshotted views name is still published in ``views.__all__``."""
        removed = _removed(STABLE_VIEWS_SURFACE, painted.views.__all__)
        assert not removed, (
            "semver-MAJOR break: painted.views dropped/renamed stable names "
            f"{sorted(removed)}. If intentional, this is a major-version change — "
            "update the snapshot in this test deliberately."
        )

    def test_no_unsnapshotted_additions(self) -> None:
        """Every name published in ``views.__all__`` is in the snapshot.

        ``painted.views`` is wholly semver-stable, so a published name is a
        committed name — it must be entered here deliberately, not slip in
        unguarded against a future rename/removal."""
        extra = _unsnapshotted(STABLE_VIEWS_SURFACE, painted.views.__all__)
        assert not extra, (
            "painted.views publishes stable names not in the snapshot: "
            f"{sorted(extra)}. Add them to STABLE_VIEWS_SURFACE — a name in the "
            "stable namespace's __all__ is a permanent public commitment and must "
            "be guarded against future rename/removal."
        )

    def test_every_stable_name_resolves(self) -> None:
        """Every snapshotted views name resolves through the lazy facade."""
        unresolved = []
        for name in sorted(STABLE_VIEWS_SURFACE):
            try:
                getattr(painted.views, name)
            except (AttributeError, ImportError) as exc:
                # AttributeError: wrong/missing attribute in the lazy mapping.
                # ImportError (incl. ModuleNotFoundError): wrong module path.
                # Either is a broken stable export — report it, don't let it
                # surface as an uncaught error.
                unresolved.append(f"{name}: {exc}")
        assert not unresolved, "painted.views stable names that do not resolve:\n" + "\n".join(
            unresolved
        )


class TestStableDisplaySurface:
    """``painted.display`` — the entry-point module — is semver-stable.

    Same bidirectional guard as core/views: ``paint``/``show`` may not be
    dropped, renamed, or joined by an unsnapshotted public name. paint()'s kwarg
    surface is a public ABI and show carries a documented 1.0 removal horizon, so
    a change here is a semver decision reviewed in the diff — not a quiet edit."""

    def test_no_removals_or_renames(self) -> None:
        """Every snapshotted display name is still published in ``display.__all__``."""
        removed = _removed(STABLE_DISPLAY_SURFACE, painted.display.__all__)
        assert not removed, (
            "semver-MAJOR break: painted.display dropped/renamed stable names "
            f"{sorted(removed)}. If intentional, this is a major-version change — "
            "update the snapshot in this test deliberately."
        )

    def test_no_unsnapshotted_additions(self) -> None:
        """Every name published in ``display.__all__`` is in the snapshot."""
        extra = _unsnapshotted(STABLE_DISPLAY_SURFACE, painted.display.__all__)
        assert not extra, (
            "painted.display publishes stable names not in the snapshot: "
            f"{sorted(extra)}. Add them to STABLE_DISPLAY_SURFACE — a name in the "
            "stable module's __all__ is a permanent public commitment and must be "
            "guarded against future rename/removal."
        )

    def test_every_stable_name_resolves(self) -> None:
        """Every snapshotted display name resolves on the module."""
        unresolved = []
        for name in sorted(STABLE_DISPLAY_SURFACE):
            try:
                getattr(painted.display, name)
            except (AttributeError, ImportError) as exc:
                unresolved.append(f"{name}: {exc}")
        assert not unresolved, "painted.display stable names that do not resolve:\n" + "\n".join(
            unresolved
        )


class TestStablePublishSurface:
    """``painted.publish`` — the doc-IR publisher module — is semver-stable.

    Same bidirectional guard as core/views/display: ``to_html``/
    ``published_fidelity`` may not be dropped, renamed, or joined by an
    unsnapshotted public name."""

    def test_no_removals_or_renames(self) -> None:
        """Every snapshotted publish name is still published in ``publish.__all__``."""
        import painted.publish

        removed = _removed(STABLE_PUBLISH_SURFACE, painted.publish.__all__)
        assert not removed, (
            "semver-MAJOR break: painted.publish dropped/renamed stable names "
            f"{sorted(removed)}. If intentional, this is a major-version change — "
            "update the snapshot in this test deliberately."
        )

    def test_no_unsnapshotted_additions(self) -> None:
        """Every name published in ``publish.__all__`` is in the snapshot."""
        import painted.publish

        extra = _unsnapshotted(STABLE_PUBLISH_SURFACE, painted.publish.__all__)
        assert not extra, (
            "painted.publish publishes stable names not in the snapshot: "
            f"{sorted(extra)}. Add them to STABLE_PUBLISH_SURFACE — a name in the "
            "stable module's __all__ is a permanent public commitment and must be "
            "guarded against future rename/removal."
        )

    def test_every_stable_name_resolves(self) -> None:
        """Every snapshotted publish name resolves on the module."""
        import painted.publish

        unresolved = []
        for name in sorted(STABLE_PUBLISH_SURFACE):
            try:
                getattr(painted.publish, name)
            except (AttributeError, ImportError) as exc:
                unresolved.append(f"{name}: {exc}")
        assert not unresolved, "painted.publish stable names that do not resolve:\n" + "\n".join(
            unresolved
        )


class TestRetiredNames:
    """Names deliberately removed pre-0.2.0 — pinned so they cannot quietly
    return (one spelling per concept; see docs/FIDELITY_DESIGN.md §4)."""

    def test_depth_alias_is_gone(self) -> None:
        """``Depth = Zoom`` died with the disclosure grammar: the ladder is
        the decision, ``Zoom`` is the one name for the rung-1 axis."""
        import painted.cli
        import painted.core.fidelity

        assert "Depth" not in painted.__all__
        assert "Depth" not in painted.cli.__all__
        assert not hasattr(painted.core.fidelity, "Depth")
        assert not hasattr(painted, "Depth")  # lazy facade must not resolve it
