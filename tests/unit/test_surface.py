"""Tests for Surface emit mechanism."""

from painted.tui import Layer, Pop, Quit, Stay, Surface


class TestEmitWithCallback:
    def test_emit_calls_callback(self):
        captured = []

        def on_emit(kind: str, data: dict) -> None:
            captured.append((kind, data))

        surface = Surface(on_emit=on_emit)
        surface.emit("ui.key", key="j")

        assert captured == [("ui.key", {"key": "j"})]

    def test_emit_multiple(self):
        captured = []

        def on_emit(kind: str, data: dict) -> None:
            captured.append((kind, data))

        surface = Surface(on_emit=on_emit)
        surface.emit("ui.key", key="j")
        surface.emit("ui.resize", width=80, height=24)

        assert len(captured) == 2
        assert captured[0] == ("ui.key", {"key": "j"})
        assert captured[1] == ("ui.resize", {"width": 80, "height": 24})

    def test_emit_domain_action(self):
        captured = []

        def on_emit(kind: str, data: dict) -> None:
            captured.append((kind, data))

        surface = Surface(on_emit=on_emit)
        surface.emit("domain.action", item="foo")

        assert captured == [("domain.action", {"item": "foo"})]


class TestEmitWithoutCallback:
    def test_emit_no_callback_is_noop(self):
        surface = Surface()
        # Should not raise
        surface.emit("ui.key", key="j")

    def test_emit_none_callback_is_noop(self):
        surface = Surface(on_emit=None)
        surface.emit("ui.resize", width=80, height=24)


class TestAutoEmitKinds:
    def test_key_auto_emit_kind(self):
        """The run loop emits 'ui.key' after on_key — verify emit sends correct kind."""
        captured = []

        def on_emit(kind: str, data: dict) -> None:
            captured.append((kind, data))

        surface = Surface(on_emit=on_emit)
        # Simulate what the run loop does: on_key then emit
        surface.on_key("j")
        surface.emit("ui.key", key="j")

        assert captured == [("ui.key", {"key": "j"})]

    def test_resize_auto_emit_kind(self):
        """The _on_resize handler emits 'ui.resize' — verify emit sends correct kind."""
        captured = []

        def on_emit(kind: str, data: dict) -> None:
            captured.append((kind, data))

        surface = Surface(on_emit=on_emit)
        # Simulate what _on_resize does at the emit point
        surface.emit("ui.resize", width=120, height=40)

        assert captured == [("ui.resize", {"width": 120, "height": 40})]


# -- Helpers for action auto-emission tests ----------------------------------


def _make_layer(action_fn):
    """Create a Layer whose handle returns the action from action_fn(key)."""
    return Layer(
        name="test",
        state=None,
        handle=lambda key, ls, app: (ls, app, action_fn(key)),
        render=lambda ls, app, view: None,
    )


def _get_layers(state):
    return state["layers"]


def _set_layers(state, layers):
    return {**state, "layers": layers}


class TestActionAutoEmission:
    def test_handle_key_emits_stay(self):
        captured = []
        surface = Surface(on_emit=lambda k, d: captured.append((k, d)))
        layer = _make_layer(lambda key: Stay())
        state = {"layers": (layer,)}

        new_state, should_quit, pop_result = surface.handle_key(
            "j",
            state,
            _get_layers,
            _set_layers,
        )

        assert not should_quit
        assert pop_result is None
        assert captured == [("ui.action", {"action": "stay"})]

    def test_handle_key_emits_quit(self):
        captured = []
        surface = Surface(on_emit=lambda k, d: captured.append((k, d)))
        layer = _make_layer(lambda key: Quit())
        state = {"layers": (layer,)}

        new_state, should_quit, pop_result = surface.handle_key(
            "q",
            state,
            _get_layers,
            _set_layers,
        )

        assert should_quit
        assert captured == [("ui.action", {"action": "quit"})]

    def test_handle_key_emits_pop_with_result(self):
        captured = []
        surface = Surface(on_emit=lambda k, d: captured.append((k, d)))
        # Two layers — pop removes the top one
        base = _make_layer(lambda key: Stay())
        top = _make_layer(lambda key: Pop(result="selected"))
        state = {"layers": (base, top)}

        new_state, should_quit, pop_result = surface.handle_key(
            "enter",
            state,
            _get_layers,
            _set_layers,
        )

        assert not should_quit
        assert pop_result == "selected"
        assert captured == [("ui.action", {"action": "pop", "result": "selected"})]

    def test_handle_key_emits_pop_none_result_as_stay(self):
        """Pop with result=None means pop_result is None — emits stay."""
        captured = []
        surface = Surface(on_emit=lambda k, d: captured.append((k, d)))
        base = _make_layer(lambda key: Stay())
        top = _make_layer(lambda key: Pop(result=None))
        state = {"layers": (base, top)}

        new_state, should_quit, pop_result = surface.handle_key(
            "escape",
            state,
            _get_layers,
            _set_layers,
        )

        assert not should_quit
        assert pop_result is None
        assert captured == [("ui.action", {"action": "stay"})]

    def test_handle_key_no_emit_callback_is_noop(self):
        """handle_key works without on_emit — no crash."""
        surface = Surface()
        layer = _make_layer(lambda key: Quit())
        state = {"layers": (layer,)}

        new_state, should_quit, pop_result = surface.handle_key(
            "q",
            state,
            _get_layers,
            _set_layers,
        )

        assert should_quit


class TestRunSetupFailureRestoresTerminal:
    """Surface.run must restore the terminal even when setup fails.

    Regression: enter_alt_screen/hide_cursor ran before the try/finally,
    so a failure in sizing or user layout() wedged the terminal.
    """

    class _FailingSizeWriter:
        def __init__(self):
            self.calls = []

        def enter_alt_screen(self):
            self.calls.append("enter_alt_screen")

        def exit_alt_screen(self):
            self.calls.append("exit_alt_screen")

        def hide_cursor(self):
            self.calls.append("hide_cursor")

        def show_cursor(self):
            self.calls.append("show_cursor")

        def enable_mouse(self, *, all_motion=False):
            self.calls.append("enable_mouse")

        def disable_mouse(self):
            self.calls.append("disable_mouse")

        def size(self):
            raise OSError("not a tty")

    def test_setup_failure_exits_alt_screen(self):
        import asyncio

        import pytest

        surface = Surface()
        writer = self._FailingSizeWriter()
        surface._writer = writer

        with pytest.raises(OSError):
            asyncio.run(surface.run())

        assert "exit_alt_screen" in writer.calls
        assert "show_cursor" in writer.calls
        # Restore runs after the failed setup, not before
        assert writer.calls.index("exit_alt_screen") > writer.calls.index("enter_alt_screen")
