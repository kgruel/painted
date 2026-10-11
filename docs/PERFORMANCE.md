# Performance baselines

Roadmap Milestone 8 asks for a **recorded baseline and a repeatable comparison
process**, not optimization. RENDER_MODEL §6 defers performance budgets, so
nothing here sets a target. Two kinds of evidence exist:

- **Structural checks** are deterministic and gated. They pin properties that
  don't depend on machine speed.
- **Scenario baselines** are timings and counters from `./dev bench`. They are
  informational and never gated.

## Structural checks (gated)

| Property | Test |
|----------|------|
| Completion imports no renderer | `tests/unit/test_complete.py` (`*_is_render_free`) |
| A Surface frame that changes nothing writes no cells; a change writes exactly the changed cells | `tests/unit/test_diff_render.py` |
| An in-place live frame is one atomic write; an identical redraw writes no rows | `tests/unit/test_inplace_renderer.py` |
| A sustained stream keeps only the latest frame (no backlog of obsolete frames) | `tests/unit/test_stream_surface.py` (coalescing) |
| One-shot delivery (`print_block`) is one write at any height, plain or ANSI | `tests/unit/test_delivery_write_budget.py` |
| `import painted.tui` loads no `painted.views` | `tests/smoke/test_import_smoke.py` |
| Every bench scenario still runs | `tests/smoke/test_bench_harness.py` |

The roadmap's last structural item, "lower Fidelity avoids optional
computation", is the application's job, not something painted can gate. For
painted's own transcription default, the baseline below shows the cost rising
with zoom (about 4 µs at zoom 0 and about 380 µs at zoom 3 on the same value),
so lower detail does less work rather than rendering everything and discarding it.

## Scenario baselines (`./dev bench`)

```bash
./dev bench                                          # run and print the report
./dev bench --only host                              # one group, or a name substring
./dev bench --compare docs/baselines/baseline.json   # drift vs the recorded baseline
./dev bench --save docs/baselines/baseline.json      # re-record (commit the diff)
```

`tools/bench.py` holds the scenario list from the roadmap: cold imports, help,
completion, domain state → Block at each zoom, a dashboard composition tree,
plain / ANSI / HTML / JSON serialization, sparse and full Buffer diffs, host
viewport frames, key input → flushed frame, and a large table, tree and
traceback. Each scenario records:

- **median and p95 latency** (µs)
- **peak traced allocation** (KiB), from one `tracemalloc` run
- **frames over the live budget** (33 ms, one frame at 30 fps), for the live-frame scenarios
- **exact counters**: output bytes, `write` calls, changed cells, rows, modules loaded

The report renders through painted (`table_lens`).

### Comparison process

1. Before a change that might affect speed, run
   `./dev bench --compare docs/baselines/baseline.json` on the same machine that
   recorded the baseline (its `meta` names the machine).
2. A median more than 1.25× slower is flagged `SLOWER`, and any changed counter
   is flagged `COUNTERS`. Both are informational. A changed counter is
   machine-independent, so treat it as a real behavior change: the bytes,
   writes or cells delivered moved.
3. When a change intends to move a number, re-record with `--save` and commit
   the JSON. The diff is the review.
4. Re-record when the reference machine changes, too. Timings compare only
   against the same machine; counters compare everywhere.

### What the first baseline shows

Recorded 2026-10-11 at `7f005f7` (painted 0.15.0 plus unreleased work), Python
3.13, Linux x86_64, 200 iterations. Full data is in `docs/baselines/baseline.json`.

- **All live-frame scenarios fit the budget with room to spare.** A host
  viewport frame takes about 25 µs, and key → flushed frame on a 100×40
  `list_view` surface takes about 3 ms (42 changed cells, 1 write). No frame
  sample went over 33 ms.
- **`import painted.tui` costs about 60 ms**, against about 3 ms for `painted`,
  `painted.views` and `painted.cli`, which stay lazy. No single module
  dominates: tui loads core, host, the writer and buffer eagerly (29 modules).
- **ANSI serialization is about 10× plain** (about 18 ms against 1.9 ms for a
  200-row table), and HTML is about 27 ms. The per-span style resolution in
  `render_row_ansi` is where to look first.
- **A 2000-row `table_lens` takes about 220 ms and about 9 MiB.** This is the
  largest single render and scales with rows. Virtualization stays deferred past
  1.0 (ROADMAP "Explicitly deferred").
- **A Buffer diff costs the scan, not the changes:** about 0.76 ms for 120
  changed cells on 200×60, about 7 ms for all 12,000.

These are observations for whoever picks up performance work, not commitments.
Per the roadmap, no representation rewrite is undertaken for speculative
performance.
