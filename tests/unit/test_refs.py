"""Unit tier — the RefScheme declaration and the resolver seam (REFS_DESIGN §4).

Pins: ``RefScheme`` construction validation (bad name shape, non-callable
resolver — both ``DeclarationError``, the *validate every declaration* mandate
applying from day one just as it does for ``Vocabulary``/``Role``);
``use_refs``'s dual setter/context-manager shape with REPLACE-not-accumulate
semantics and a duplicate-name collision raising at the call; the
``resolve_ref`` inertness table (no colon / undeclared scheme / resolver
declines / resolves); and the one deliberate asymmetry with ``mark_style`` — an
undeclared scheme degrades to inert rather than raising. A resolver that itself
raises is app code faulting, not painted detecting a fault, so that exception
must propagate unwrapped — never re-boxed as a ``PaintedError``.
"""

from __future__ import annotations

import pytest

from painted.core.errors import ContractError, DeclarationError, PaintedError
from painted.refs import (
    RefScheme,
    current_ref_schemes,
    reset_refs,
    resolve_ref,
    use_refs,
)


def _fact_scheme(resolve=None) -> RefScheme:
    """The design doc's example scheme: resolves a fact id to a loops.dev URL."""
    return RefScheme("fact", resolve or (lambda value: f"https://loops.dev/f/{value}"))


# --- Construction validation --------------------------------------------------


class TestConstructionValidation:
    def test_non_kebab_name_raises(self) -> None:
        with pytest.raises(DeclarationError, match="kebab-case"):
            RefScheme("Bad_Name", lambda value: value)

    def test_uppercase_name_raises(self) -> None:
        with pytest.raises(DeclarationError, match="kebab-case"):
            RefScheme("FACT", lambda value: value)

    def test_non_callable_resolver_raises(self) -> None:
        with pytest.raises(DeclarationError, match="callable"):
            RefScheme("fact", "not-a-function")  # type: ignore[arg-type]

    def test_none_resolver_raises(self) -> None:
        with pytest.raises(DeclarationError, match="callable"):
            RefScheme("fact", None)  # type: ignore[arg-type]


# --- use_refs: duplicate-name collision ---------------------------------------


class TestDuplicateNameCollision:
    def test_duplicate_names_across_passed_schemes_raises(self) -> None:
        a = RefScheme("dup", lambda value: value)
        b = RefScheme("dup", lambda value: value.upper())
        with pytest.raises(DeclarationError, match="declared twice"):
            use_refs(a, b)

    def test_no_partial_registration_on_collision(self) -> None:
        # A failed use_refs() call must not leave a half-applied registry behind.
        reset_refs()
        a = RefScheme("dup", lambda value: value)
        b = RefScheme("dup", lambda value: value.upper())
        with pytest.raises(DeclarationError, match="declared twice"):
            use_refs(a, b)
        assert current_ref_schemes() == {}


# --- use_refs: dual-mode ambient seam ------------------------------------------


class TestDualModeSeam:
    def test_setter_persists(self) -> None:
        use_refs(_fact_scheme())
        assert "fact" in current_ref_schemes()

    def test_context_manager_restores(self) -> None:
        reset_refs()
        with use_refs(_fact_scheme()):
            assert "fact" in current_ref_schemes()
        assert "fact" not in current_ref_schemes()

    def test_context_manager_restores_prior_not_empty(self) -> None:
        # A scoped override restores whatever was active BEFORE the block — a
        # ContextVar reset, not a blind clear-to-empty.
        outer = RefScheme("outer", lambda value: value)
        inner = RefScheme("inner", lambda value: value)
        use_refs(outer)  # setter — the prior registry
        with use_refs(inner):
            active = current_ref_schemes()
            assert "inner" in active and "outer" not in active
        restored = current_ref_schemes()
        assert "outer" in restored and "inner" not in restored

    def test_replace_semantics_not_accumulation(self) -> None:
        use_refs(_fact_scheme())
        other = RefScheme("other", lambda value: value)
        use_refs(other)  # replaces, does not accumulate
        active = current_ref_schemes()
        assert "other" in active and "fact" not in active

    def test_reset_refs_clears_to_empty(self) -> None:
        use_refs(_fact_scheme())
        reset_refs()
        assert current_ref_schemes() == {}


# --- resolve_ref: the inertness table ------------------------------------------


class TestResolveRefInertness:
    def test_no_colon_is_inert(self) -> None:
        # Scheme-less refs are the hit-testing idiom — inert in link deliveries,
        # not an error.
        reset_refs()
        assert resolve_ref("sidebar") is None

    def test_empty_string_is_inert(self) -> None:
        reset_refs()
        assert resolve_ref("") is None

    def test_undeclared_scheme_is_inert(self) -> None:
        reset_refs()
        assert resolve_ref("fact:01JQ8F") is None

    def test_undeclared_scheme_is_inert_even_with_other_schemes_active(self) -> None:
        use_refs(RefScheme("other", lambda value: f"https://x/{value}"))
        assert resolve_ref("fact:01JQ8F") is None

    def test_declared_resolver_returning_none_is_inert(self) -> None:
        use_refs(_fact_scheme(resolve=lambda value: None))
        assert resolve_ref("fact:01JQ8F") is None

    def test_resolves_to_uri(self) -> None:
        use_refs(_fact_scheme())
        assert resolve_ref("fact:01JQ8F") == "https://loops.dev/f/01JQ8F"

    def test_value_is_everything_after_first_colon(self) -> None:
        # partition on the FIRST colon only — a value may itself carry colons.
        seen = {}

        def capture(value: str) -> str:
            seen["value"] = value
            return "resolved"

        use_refs(RefScheme("fact", capture))
        resolve_ref("fact:2026-07-05:01JQ8F")
        assert seen["value"] == "2026-07-05:01JQ8F"


# --- The deliberate asymmetry with mark_style ----------------------------------


class TestHonestyAsymmetry:
    def test_undeclared_scheme_is_inert_not_a_contract_error(self) -> None:
        # mark_style raises ContractError on an undeclared vocabulary; resolve_ref
        # deliberately does NOT raise on an undeclared scheme — the honesty rule
        # here is "inert", not "raise". A ref without a URI still renders its
        # content perfectly; painted never invents one.
        reset_refs()
        try:
            result = resolve_ref("fact:01JQ8F")
        except ContractError:
            pytest.fail("resolve_ref must not raise on an undeclared scheme")
        assert result is None


# --- Resolver faults are the app's, not painted's ------------------------------


class TestResolverExceptionPropagatesUnwrapped:
    def test_resolver_exception_propagates_unwrapped(self) -> None:
        def boom(value: str) -> str:
            raise RuntimeError("app-side failure")

        use_refs(RefScheme("fact", boom))
        with pytest.raises(RuntimeError, match="app-side failure") as excinfo:
            resolve_ref("fact:01JQ8F")
        assert not isinstance(excinfo.value, PaintedError)

    def test_resolver_exception_is_not_wrapped_as_declaration_error(self) -> None:
        def boom(value: str) -> str:
            raise KeyError("missing")

        use_refs(RefScheme("fact", boom))
        with pytest.raises(KeyError):
            resolve_ref("fact:01JQ8F")


class TestNonStringName:
    def test_non_string_name_is_a_declaration_error(self) -> None:
        # A None/int name must fault as a painted declaration, not leak the
        # regex engine's TypeError.
        for bad in (None, 3, b"fact"):
            with pytest.raises(DeclarationError, match="kebab-case"):
                RefScheme(bad, lambda v: v)  # type: ignore[arg-type]
