"""Extended tests for painted.fidelity: resolve_mode edge cases, exception messages.

The CliRunner dispatch classes that used to live here moved to
tests/integration/test_run_cli_dispatch.py (the integration tier owns
end-to-end run_cli dispatch)."""

from __future__ import annotations

from painted.cli import (
    CliRunner,
    OutputMode,
    resolve_mode,
)


# =============================================================================
# resolve_mode edge cases
# =============================================================================


class TestResolveModeEdgeCases:
    def test_auto_neither_tty_nor_pipe(self):
        # Both False => falls through to final STATIC return.
        assert resolve_mode(OutputMode.AUTO, is_tty=False, is_pipe=False) == OutputMode.STATIC


# =============================================================================
# CliRunner._exception_message
# =============================================================================


class TestExceptionMessage:
    def test_normal_message(self):
        assert CliRunner._exception_message(ValueError("boom")) == "boom"

    def test_empty_message_falls_back_to_class_name(self):
        assert CliRunner._exception_message(RuntimeError("")) == "RuntimeError"

    def test_whitespace_only_message(self):
        assert CliRunner._exception_message(TypeError("   ")) == "TypeError"
