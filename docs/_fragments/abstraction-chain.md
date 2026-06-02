```
atoms (data)  →  engine (runtime)  →  painted (surface)  →  apps (CLI)
Fact, Spec        Tick, Vertex         Block, Lens          loops/hlab/strange-loops
```

Below painted in the monorepo: `libs/atoms/` defines Facts and Specs; `libs/engine/` produces Ticks and stores. Above: `apps/loops/`, `apps/hlab/`, and `apps/strange-loops/` use painted's entry points and lenses for all display. painted renders whatever comes out — it doesn't know about loops concepts, just data shapes, zoom levels, and terminal cells.
