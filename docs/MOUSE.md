# Mouse Input in Terminal UIs

Terminal mouse protocol reference and painted implementation notes.

Mouse support is fully implemented. Types live in `tui/mouse.py`, keyboard
integration in `tui/keyboard.py`, Writer mouse control in `core/writer.py`,
and Surface exposes `on_mouse()`. All mouse types are re-exported from
`painted.tui`.

## Protocol Overview

Terminals support mouse input through escape sequences. The application enables
mouse tracking, the terminal reports events as escape sequences on stdin, and
the application parses them alongside keyboard input.

### Tracking Modes (What Gets Reported)

| Mode | DEC | Enable | Description |
|------|-----|--------|-------------|
| X10 | 9 | `\x1b[?9h` | Button press only |
| Normal | 1000 | `\x1b[?1000h` | Press and release |
| Button-event | 1002 | `\x1b[?1002h` | Press, release, and drag (motion while pressed) |
| Any-event | 1003 | `\x1b[?1003h` | All motion, regardless of button state |

Disable by replacing `h` with `l` (e.g., `\x1b[?1003l`).

### Encoding Modes (How Coordinates Are Formatted)

| Mode | DEC | Enable | Format |
|------|-----|--------|--------|
| Legacy | - | (default) | `CSI M Cb Cx Cy` — bytes, limited to 223 cols |
| UTF-8 | 1005 | `\x1b[?1005h` | Same, but UTF-8 encoded (up to 2015) |
| SGR | 1006 | `\x1b[?1006h` | `CSI < Cb ; Cx ; Cy M/m` — decimal, unlimited |
| URXVT | 1015 | `\x1b[?1015h` | `CSI Cb ; Cx ; Cy M` — decimal, no release info |

**SGR (1006) is the modern standard.** It has no coordinate limits and
distinguishes press (`M`) from release (`m`).

## SGR Mouse Protocol (1006)

### Response Format

```
\x1b[<Cb;Cx;CyM   (press)
\x1b[<Cb;Cx;Cym   (release)
```

- `Cb` — button code (decimal)
- `Cx` — column (1-indexed, decimal)
- `Cy` — row (1-indexed, decimal)
- `M` — press, `m` — release

### Button Encoding

The button code `Cb` is a bitmask:

| Bits | Meaning |
|------|---------|
| 0-1 | Button: 0=left, 1=middle, 2=right, 3=release (legacy only) |
| 2 | Shift modifier |
| 3 | Meta/Alt modifier |
| 4 | Control modifier |
| 5 | Motion event |
| 6-7 | Button high bits: 64=scroll up/button4, 65=scroll down/button5 |

**Button values:**

| Cb | Event |
|----|-------|
| 0 | Left press |
| 1 | Middle press |
| 2 | Right press |
| 32 | Left drag (motion with button) |
| 33 | Middle drag |
| 34 | Right drag |
| 35 | Motion (no button, requires mode 1003) |
| 64 | Scroll up |
| 65 | Scroll down |

Add 4/8/16 for Shift/Meta/Ctrl modifiers. Example: Ctrl+left click = 16.

### Scroll Wheel

Scroll events report as button 64 (up) and 65 (down). No release event is sent
for scroll — each scroll "tick" is a single press event. Trackpad scroll
gestures produce these same events, typically in rapid succession.

Horizontal scroll (where supported): button 66 (left) and 67 (right).

### Example Sequences

| Sequence | Meaning |
|----------|---------|
| `\x1b[<0;10;5M` | Left click at column 10, row 5 |
| `\x1b[<0;10;5m` | Left release at column 10, row 5 |
| `\x1b[<64;15;8M` | Scroll up at column 15, row 8 |
| `\x1b[<65;15;8M` | Scroll down at column 15, row 8 |
| `\x1b[<32;12;6M` | Left drag at column 12, row 6 |
| `\x1b[<16;5;3M` | Ctrl+left click at column 5, row 3 |

## Terminal Compatibility

SGR (1006) mouse mode is widely supported:

| Terminal | SGR (1006) | Any-event (1003) | Notes |
|----------|------------|------------------|-------|
| iTerm2 | Yes | Yes | Excellent support, configurable |
| macOS Terminal | Yes | Yes | |
| Windows Terminal | Yes | Yes | |
| Alacritty | Yes | Yes | |
| GNOME Terminal | Yes | Yes | |
| Konsole | Yes | Yes | |
| xterm | Yes | Yes | The reference implementation |
| kitty | Yes | Yes | |
| WezTerm | Yes | Yes | |
| tmux | Pass-through | Pass-through | Requires `set -g mouse on` |

**Legacy terminals without SGR support are rare today.** The main edge case is
tmux/screen multiplexers which pass through mouse sequences but may need
configuration.

## How Other Frameworks Handle This

### Textual (Python)

- Unified event model: `MouseDown`, `MouseUp`, `Click`, `MouseMove`, `MouseScrollUp/Down`
- Events contain: `x`, `y`, `button`, `shift`, `meta`, `ctrl`
- `Click` includes `chain` for double/triple click detection
- Mouse capture: `widget.capture_mouse()` routes all events to one widget
- Scroll events auto-handled by scrollable containers

### Blessed (Python)

- Events come through same `inkey()` as keyboard input
- Button names include modifiers: `"LEFT"`, `"CTRL_LEFT"`, `"LEFT_RELEASED"`
- Scroll: `"SCROLL_UP"`, `"SCROLL_DOWN"`
- Motion: `"MOTION"`, `"LEFT_MOTION"` (drag)
- `MouseEvent` class with `x`, `y`, `button_value`, `released`, `is_wheel`, `is_motion`

### Common Patterns

1. **Unified input stream** — mouse and keyboard events interleave on stdin
2. **Event types** — Click, Press, Release, Move, Scroll (not raw button codes)
3. **Modifiers as flags** — shift/meta/ctrl as booleans, not baked into button
4. **Coordinates** — 0-indexed for application use (protocol uses 1-indexed)
5. **Capture mode** — one widget can claim all mouse events temporarily
6. **Scroll → deltas** — scroll events become +1/-1 deltas for Viewport

## Implementation in painted

### Module Locations

| Concern | Module |
|---------|--------|
| Types and parsing | `tui/mouse.py` |
| Keyboard integration | `tui/keyboard.py` |
| Writer mouse control | `core/writer.py` |
| Surface callback | `tui/surface.py` |

All three mouse types are re-exported from `painted.tui`:

```python
from painted.tui import MouseEvent, MouseButton, MouseAction
```

### Types

`MouseEvent`, `MouseButton`, and `MouseAction` are implemented as described in the
Proposed Types section above. `MouseButton.NONE = 3` (motion without button).
`MouseEvent` adds a `scroll_delta` property: `-1` for scroll up, `+1` for scroll
down, `0` for non-scroll.

### Keyboard Integration

`KeyboardInput` detects the `CSI <` prefix in the stdin stream and delegates to
`parse_sgr_mouse()` (in `tui/mouse.py`). The `Input` union type (`str | MouseEvent`)
is exported from `painted.tui`.

### Writer Mouse Control

`Writer.enable_mouse(*, all_motion=False)` and `Writer.disable_mouse()` are
implemented in `core/writer.py`. They write SGR mode sequences (`?1002h`/`?1003h`
for tracking, `?1006h` for SGR encoding).

### Surface Integration

`Surface` accepts `enable_mouse=True` (and `mouse_all_motion=True` for mode 1003).
The main loop dispatches `MouseEvent` objects to `on_mouse()`. Override to handle:

```python
class MyApp(Surface):
    def on_mouse(self, event: MouseEvent) -> None:
        if event.is_scroll:
            self._viewport = self._viewport.scroll(event.scroll_delta)
```

### Viewport Scroll Integration

```python
from painted.tui import MouseEvent, MouseButton
from painted import Viewport

def on_mouse(self, event: MouseEvent) -> None:
    if event.is_scroll:
        self._viewport = self._viewport.scroll(event.scroll_delta)
```

See [VIEWPORT_DESIGN.md](VIEWPORT_DESIGN.md) for `Viewport` API.

## Remaining Open Questions

1. **Coordinate translation for layers** — Mouse events are screen-absolute.
   `Surface.hit_test(x, y)` returns a semantic id at a coordinate, but per-layer
   local coordinate translation is not automatic.

2. **Click chain detection** — Double-click requires state and timing logic.
   Not implemented; single press/release is the current granularity.

3. **Mouse capture mode** — A widget claiming all mouse events for drag
   operations is not implemented.

4. **Hover/motion in components** — Mode 1003 (all motion) is available via
   `mouse_all_motion=True` on Surface, but no built-in component uses it.

## References

- [XTerm Control Sequences](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html) — canonical protocol documentation
- [Textual Input Guide](https://textual.textualize.io/guide/input/) — Textual's mouse handling
- [Blessed Mouse Docs](https://blessed.readthedocs.io/en/latest/mouse.html) — Blessed's approach
- [ESPTerm Overview](https://espterm.github.io/docs/espterm-xterm.html) — clear mode summary
