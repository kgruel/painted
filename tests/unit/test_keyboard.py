"""Tests for keyboard input handling."""

import io
from unittest.mock import patch

from painted.keyboard import KeyboardInput, cbreak_supported

# The public name survives the hoist: tui re-exports it from the new root home.
from painted.tui import KeyboardInput as _KeyboardInputViaTui

assert _KeyboardInputViaTui is KeyboardInput


class TestGetKey:
    """Test KeyboardInput.get_key() byte handling."""

    def test_cr_returns_enter(self):
        """CR (0x0D) returns 'enter'."""
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b"\x0d"):
            assert kb.get_key() == "enter"

    def test_lf_returns_enter(self):
        """LF (0x0A) returns 'enter' — some terminals send this instead of CR."""
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b"\x0a"):
            assert kb.get_key() == "enter"

    def test_backspace_returns_backspace(self):
        """DEL (0x7F) returns 'backspace'."""
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b"\x7f"):
            assert kb.get_key() == "backspace"

    def test_tab_returns_tab(self):
        """TAB (0x09) returns 'tab'."""
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b"\x09"):
            assert kb.get_key() == "tab"

    def test_none_when_no_input(self):
        """Returns None when no input available."""
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=None):
            assert kb.get_key() is None

    def test_none_when_unavailable(self):
        """Returns None when keyboard not available."""
        kb = KeyboardInput()
        kb._available = False
        assert kb.get_key() is None


class TestReadKeyBlocking:
    """KeyboardInput.read_key() — the prompt-side blocking reader (§5)."""

    def test_returns_char(self):
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b"a"):
            assert kb.read_key() == "a"

    def test_enter(self):
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b"\x0d"):
            assert kb.read_key() == "enter"

    def test_eof_returns_none(self):
        # An actual stream EOF: os.read → b"" → read_key returns None (abort).
        kb = KeyboardInput()
        kb._available = True
        with patch.object(kb, "_read_byte", return_value=b""):
            assert kb.read_key() is None

    def test_none_when_unavailable(self):
        kb = KeyboardInput()
        kb._available = False
        assert kb.read_key() is None


class TestCbreakSupported:
    """The public availability probe read before any terminal mutation (§5)."""

    def test_false_for_non_tty_stream(self):
        # A StringIO has no real fd — the probe must answer False without raising.
        assert cbreak_supported(io.StringIO()) is False

    def test_false_for_stream_without_fileno(self):
        class _NoFileno:
            pass

        assert cbreak_supported(_NoFileno()) is False  # type: ignore[arg-type]

    def test_probe_does_not_enter_cbreak(self):
        # It must be read-only: tcgetattr is consulted, setcbreak never called.
        with patch("painted.keyboard.tty.setcbreak") as setcbreak:
            cbreak_supported(io.StringIO())
        setcbreak.assert_not_called()
