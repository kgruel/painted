"""painted's exception hierarchy (docs/ERRORS_DESIGN.md).

One root (``PaintedError``) and three leaves, each dual-inheriting the stdlib
type it replaces so every existing ``except ValueError``/``except
RuntimeError`` — ours and consumers' — keeps working unchanged (the
semver-MINOR argument, §3 of the design doc). These tests pin: the hierarchy
shape, the compat guarantee as an actual catch (not just an `issubclass`
check), the import surface across all three declared homes, and one
behavioral assertion per class at the representative site named in the
design doc's §5 site table.
"""

from __future__ import annotations

import argparse
import io

import pytest

from painted import Block, Style
from painted.core.cell import Cell
from painted.inplace import InPlaceRenderer


def _block(rows):
    return Block(rows, len(rows[0]) if rows else 0)


# =============================================================================
# Hierarchy shape
# =============================================================================


class TestHierarchyShape:
    def test_painted_error_is_an_exception(self):
        from painted.core.errors import PaintedError

        assert issubclass(PaintedError, Exception)

    def test_declaration_error_is_a_painted_error_and_a_value_error(self):
        from painted.core.errors import DeclarationError, PaintedError

        assert issubclass(DeclarationError, PaintedError)
        assert issubclass(DeclarationError, ValueError)

    def test_contract_error_is_a_painted_error_and_a_value_error(self):
        from painted.core.errors import ContractError, PaintedError

        assert issubclass(ContractError, PaintedError)
        assert issubclass(ContractError, ValueError)

    def test_lifecycle_error_is_a_painted_error_and_a_runtime_error(self):
        from painted.core.errors import LifecycleError, PaintedError

        assert issubclass(LifecycleError, PaintedError)
        assert issubclass(LifecycleError, RuntimeError)


# =============================================================================
# The compat guarantee — dual inheritance means the old catch still works
# =============================================================================


class TestCompatGuarantee:
    """§3: this is the semver-MINOR argument itself, not just a shape check —
    an existing `except ValueError`/`except RuntimeError` in a consumer's code
    must actually catch the new class, not merely be a supertype of it."""

    def test_declaration_error_caught_by_except_value_error(self):
        from painted.core.errors import DeclarationError

        try:
            raise DeclarationError("bad declaration")
        except ValueError as caught:
            assert isinstance(caught, DeclarationError)
        else:
            pytest.fail("DeclarationError was not caught by except ValueError")

    def test_contract_error_caught_by_except_value_error(self):
        from painted.core.errors import ContractError

        try:
            raise ContractError("bad value")
        except ValueError as caught:
            assert isinstance(caught, ContractError)
        else:
            pytest.fail("ContractError was not caught by except ValueError")

    def test_lifecycle_error_caught_by_except_runtime_error(self):
        from painted.core.errors import LifecycleError

        try:
            raise LifecycleError("bad state")
        except RuntimeError as caught:
            assert isinstance(caught, LifecycleError)
        else:
            pytest.fail("LifecycleError was not caught by except RuntimeError")


# =============================================================================
# Import surface — §2: home is core/errors.py, re-exported from painted and
# painted.core, part of the semver-stable surface.
# =============================================================================


class TestImportSurface:
    @pytest.mark.parametrize(
        "name", ["PaintedError", "DeclarationError", "ContractError", "LifecycleError"]
    )
    def test_importable_from_core_errors(self, name):
        import painted.core.errors as errors_module

        assert hasattr(errors_module, name)

    @pytest.mark.parametrize(
        "name", ["PaintedError", "DeclarationError", "ContractError", "LifecycleError"]
    )
    def test_importable_from_painted_core(self, name):
        import painted.core

        assert hasattr(painted.core, name)
        assert name in painted.core.__all__

    @pytest.mark.parametrize(
        "name", ["PaintedError", "DeclarationError", "ContractError", "LifecycleError"]
    )
    def test_importable_from_painted_root(self, name):
        import painted

        assert hasattr(painted, name)
        assert name in painted.__all__

    def test_root_and_core_resolve_to_the_same_classes(self):
        """Re-exported, not re-defined — `painted.DeclarationError is
        painted.core.DeclarationError`, one class with two import paths."""
        import painted
        import painted.core

        for name in ("PaintedError", "DeclarationError", "ContractError", "LifecycleError"):
            assert getattr(painted, name) is getattr(painted.core, name)


# =============================================================================
# Representative behavior — one per class, §5 site table
# =============================================================================


class TestDeclarationErrorSite:
    """A declared flag colliding with a framework flag (`cli/types.py:331`) —
    same construction call as TestCollisionChecks.test_tag_vs_framework_flag
    in test_tag_grammar.py, asserting the specific class instead of the bare
    stdlib parent."""

    def test_tag_vs_framework_flag_raises_declaration_error(self):
        from painted.cli import Tag, add_cli_args
        from painted.core.errors import DeclarationError

        parser = argparse.ArgumentParser()
        with pytest.raises(DeclarationError, match="framework flag"):
            add_cli_args(parser, tags=[Tag("json", "x")])


class TestContractErrorSite:
    """A malformed Cell (`core/cell.py:69`) and a Block row-width mismatch
    (`core/block.py:114`) — both call-time value faults on the render path."""

    def test_cell_multi_char_raises_contract_error(self):
        from painted.core.errors import ContractError

        with pytest.raises(ContractError, match="single character"):
            Cell("ab", Style())

    def test_block_row_width_mismatch_raises_contract_error(self):
        from painted.core.errors import ContractError

        with pytest.raises(ContractError, match="row 0 width 2 != block width 3"):
            Block([[Cell("a", Style()), Cell("b", Style())]], 3)


class TestLifecycleErrorSite:
    """`InPlaceRenderer.render()` outside its context manager
    (`inplace.py:87`) — the right call in the wrong state."""

    def test_render_outside_context_raises_lifecycle_error(self):
        from painted.core.errors import LifecycleError

        stream = io.StringIO()
        block = Block.text("hi", Style())
        renderer = InPlaceRenderer(stream)

        with pytest.raises(LifecycleError, match="outside of a context manager"):
            renderer.render(block)
