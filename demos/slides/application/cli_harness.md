---
id: cli_harness
title: CLI Harness
group: application
order: 5
align: center
---

# CLI Harness

[spacer]

[zoom:0]

`run_cli()` is the “one call” entry point for CLI tools

[spacer]

you provide `fetch` and `renderer(data, fidelity, width) -> Block` — painted chooses delivery

[spacer]

delivery axes: `OutputMode` (STATIC / LIVE / INTERACTIVE) and `Format` (ANSI / PLAIN / JSON)

[spacer]

zoom is a first-class input: `Zoom.MINIMAL → Zoom.FULL`

[spacer]

↓ for more detail

[zoom:1]

*the contract (shape only)*

[spacer]

```python
def renderer(data: T, fidelity: Fidelity, width: int | None) -> Block: ...
def fetch() -> T: ...

run_cli(args, renderer=renderer, fetch=fetch)
```

[spacer]

optionally:

```python
run_cli(
    args,
    renderer=renderer,
    fetch=fetch,
    handlers={OutputMode.INTERACTIVE: lambda ctx: MySurface().run()},
)
```

[zoom:2]

*where to look next*

[spacer]

`src/painted/fidelity.py` defines `run_cli`, `CliContext`, `Zoom`, `OutputMode`, and `Format`.

