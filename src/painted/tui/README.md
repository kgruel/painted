# painted.tui — Interactive App Subsystem

Full-screen terminal applications with keyboard input, modal dialogs, and diff rendering.

## Surface

The app base class. Manages alt screen, keyboard loop, and diff-based rendering.

```python
import asyncio
from painted.tui import Surface

class MyApp(Surface):
    def __init__(self):
        super().__init__()
        self.count = 0

    def render(self) -> None:
        buf = self._buf
        block = Block.text(f"Count: {self.count}", Style())
        block.paint(buf, 0, 0)

    def on_key(self, key: str) -> None:
        if key == "q":
            self.quit()
        elif key == " ":
            self.count += 1

asyncio.run(MyApp().run())
```

`run()` is async: it enters alt screen, starts the keyboard + render loop, and diff-flushes only changed cells. `render()` takes no arguments — paint into `self._buf`.

## HostSurface — the host rung (a renderer's Block, interactively)

A `Surface` subclass that mounts a **semantic renderer** into the interactive
delivery, so a renderer that already travels `print_block` / `InPlaceRenderer` /
`StreamSurface` also drives a TUI with no hand-rolled viewport/scroll/evidence
glue (`docs/HOST_RUNG_DESIGN.md` §6). It sits *beside* direct-`Buffer` `Surface`
apps — an addition, not a replacement. `run_cli` mounts it for you on `-i` (the
host rung is the framework's INTERACTIVE path); reach for it directly only when
you drive the loop yourself.

```python
from painted.tui import HostSurface

# Omitted arm: the host owns the viewport. The renderer returns natural-height
# content; HostSurface slices it, routes scroll keys, and marks omission.
HostSurface(render=lambda width, height: my_block(data, width), accepts_height=False)

# Offered arm: the renderer owns the frame. HostSurface offers height=H (the full
# frame — it draws no chrome) and verifies exactly H rows (ContractError if not).
HostSurface(render=lambda width, height: my_dashboard(data, width, height),
            accepts_height=True)
```

`render` is `(width, height) -> Block` — `height` is `None` on the omitted arm,
the integer `H` on the offered arm. Two arms, one class, chosen by
`accepts_height` (the binding's standing acceptance fact, never inspected per
frame):

- **Omitted arm** — mounts a root `ViewportAdapter` (`from painted import
  ViewportAdapter`). Scroll keys (arrows / `j`/`k`, page up/down, home/end / `g`/`G`)
  and the scroll wheel route through the adapter; follow / at-bottom intent is
  tracked; the reserved evidence row appears on overflow. A **height-only resize
  re-slices with no renderer call** (the §6 matrix); a width change re-renders and
  reconciles the anchor.
- **Offered arm** — the renderer takes `height=H` and owns its own internal
  chrome/body-scroll (the hybrid shape, §6). HostSurface treats the returned Block
  as opaque, verifies exactness, and paints it.

**Hit testing follows the event-order discipline** (§6): the token of the last
*displayed* frame is retained and every mouse event resolves against exactly that
token, so an event that arrives after a SIGWINCH swaps geometry resolves *stale*
(dropped) rather than translating through the new geometry. Resolved hits land in
`.hits` and emit `host.hit` observations.

**The inward host-event seam** (`on_host_event=`, §7) is the counterpart of the
outward-only `Surface.emit`: host viewing-state reaching the app as *input*. Pass
`on_host_event=sink` (a `HostEvent -> None` callback, from `painted`) and the
omitted arm delivers a `HostViewportEvent` (scroll / follow-track / cursor /
resize — a typed `ViewportChange` reason beside the resulting `offset` /
`following` / `is_at_bottom` / `cursor_row`), a `HostHitEvent` (the resolved
`Hit`), or a `HostQuitEvent` — each carrying two frame tokens: `observed` (the
displayed mapping the input landed on) and `current` (the live post-transition
mapping, equal to `observed` exactly when the transition installed no change
relative to the displayed frame — mid-batch a later event may differ). Delivery is synchronous, exactly once per
event, after the pure adapter transition installs; a handler exception fails the
host delivery loud (never swallowed, never rerouted to `emit`). The **offered
arm** owns no viewport, so a declared sink there fires zero times — honest
silence, never a synthetic mount event. The **omitted arm** routes through the
shared `HostViewport` controller (root `painted.host`) — which `StreamSurface`
composes too, so the machinery is extracted, not forked; the offered arm creates
no controller (its renderer owns the frame).

## Layer Pattern

Modal stack on top of Surface. Top layer handles keys, all render bottom-to-top.

```python
from painted.tui import Layer, Stay, Pop, Push, Quit, Action

class ConfirmLayer(Layer):
    def handle(self, key, layer_state, app_state):
        if key == "y":
            return layer_state, app_state, Pop(result=True)
        if key == "n":
            return layer_state, app_state, Pop(result=False)
        return layer_state, app_state, Stay()

    def render(self, layer_state, app_state, buf):
        Block.text("Confirm? [y/n]", Style()).paint(buf, 0, 0)
```

Actions: `Stay` | `Pop(result)` | `Push(layer)` | `Quit`. Base layer never pops.

## Focus

Two-tier model: navigation vs widget capture.

```python
from painted.tui import Focus, ring_next, ring_prev

focus = Focus(id="sidebar")
focus = ring_next(focus, ["sidebar", "main", "footer"])  # cycle forward
focus.captured  # True when a widget owns all input (e.g., text input)
```

## Search

Query + selected index, with filter functions.

```python
from painted.tui import Search, filter_fuzzy, filter_prefix, filter_contains

search = Search(query="hel")
matches = filter_fuzzy(search, items, key=lambda x: x.name)
```

## Buffer / BufferView

Direct cell painting. BufferView clips and translates coordinates.

```python
from painted.tui import Buffer, BufferView, Region

buf = Buffer(80, 24)
view = Region(x=5, y=2, width=40, height=10).view(buf)
block.paint(view, 0, 0)  # paints at (5, 2) in buffer coordinates
```

## Testing

```python
from painted.tui import TestSurface, CapturedFrame

harness = TestSurface(MyApp(), width=20, height=5, input_queue=["j", "j", "enter", "q"])
frames: list[CapturedFrame] = harness.run_to_completion()
assert "expected text" in frames[-1].text
```

`TestSurface` replays the `input_queue` (keys and `MouseEvent`s) against a fixed
`width`×`height` buffer, captures frames and emissions, and exposes each frame's
diff in `frame.writes`. No real terminal needed.

## Exports

```python
from painted.tui import (
    Buffer, BufferView, CellWrite, KeyboardInput, Input,
    Surface, HostSurface, HostRender, Emit, LifecycleHook,
    Layer, Stay, Pop, Push, Quit, Action, process_key, render_layers,
    Focus, ring_next, ring_prev, linear_next, linear_prev,
    Search, filter_fuzzy, filter_prefix, filter_contains,
    TestSurface, CapturedFrame,
    Region, Cursor, CursorMode,
    MouseEvent, MouseButton, MouseAction,
)
```
