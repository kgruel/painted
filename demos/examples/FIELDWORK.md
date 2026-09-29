# Fieldwork

An investigation desk for recorded operational evidence. It starts with eight
historical facts from gruel.network; it can also open a local loops store.

```bash
uv run painted demos fieldwork -i
```

Start on the media disk incident. Press `v` to read the complete account, then
`Tab` to select connected evidence. The first reference is unavailable in this
snapshot; that missing evidence stays visible. Move down twice to the journald
practice and press `Enter`. In the practice's links, move down to the fleet
rollout and press `Enter` again.

The practice says the fix has reached only media. The later rollout records
13 of 14 guest VMs reached, with an unreachable host still outstanding. Neither
record is a current health check. `Backspace` returns to the previous reading,
including its search, depth, facets, selected link, and scroll position.

| Key | Question or action |
|---|---|
| `/`, then Enter | Search words across the recorded evidence; Escape cancels |
| `j` / `k`, arrows | Select a record or connected fact |
| `Tab` | Switch between records and links |
| `Enter` | Follow the selected explicit reference |
| `Backspace` / left | Return to the previous reading |
| `v` / `V` | Read more / less detail |
| `p` | Who recorded this, and when? |
| `c` | What check could inform a new investigation? |
| `f` | Which additional fields were recorded? |
| `m` | List the matching fact names and IDs |
| Page Up / Page Down | Scroll the evidence, or help while it is open |
| `?` | Open / close help; Escape also closes it |
| `q` | Quit |

At depth 3, provenance and fields are implied, as they are with `-vv` in the
CLI. Lowering depth hides only implied facets: explicit CLI requests and key
toggles persist. Facet keys toggle the explicit request, so removing one at
depth 3 still leaves the depth implication visible until you press `V`.

At widths below 88 columns, the sidebar disappears; selection still works and
the status above the reading identifies the selected link (ellipsized if needed).
The line-range row is reserved independently of labels, facets, and notices.
When the range cannot fit, `+N rows` counts undisplayed rows; at still narrower
widths, `+` marks overflow. Even a one-row screen prioritizes this evidence.
Only zero width or zero height prevents a visible marker. A one-row sidebar
likewise prioritizes omission counts over its heading. Below six terminal rows,
there is no reading area: enlarge the terminal to read the evidence.

Help has its own scroll position: Page Up / Page Down, arrows or `j` / `k`, and
Home / End scroll it without changing the investigation. Closing help restores
the same subject, selected link, facets, and evidence scroll position.

## The same questions from a pipe

```bash
# Find fact names and IDs without reading every account.
uv run painted demos fieldwork --match journald -q --matches

# Read one practice, its provenance, and suggested checks.
uv run painted demos fieldwork \
  --record journald-size-cap-provisioning -v --provenance --checks

# Read the original incident behind the SSH-banner practice.
uv run painted demos fieldwork --match banner --kind incident -v

# A structured selection, its matches, and its explicit relationships.
uv run painted demos fieldwork --match journald --json
```

The renderer takes `View, Fidelity, width` in both the CLI and TUI. Selecting a
record changes the subject; the depth and named facets keep their meanings.
JSON serializes the selected data instead of the rendered text. Omitted width
(for example, a pipe) preserves natural line widths; an integer width is exact.

## Open the grounding store

```bash
uv run painted demos fieldwork \
  --store ~/Code/gruel.network/.loops/data/homelab-coord.db \
  --match journald -i
```

The SQLite adapter opens an existing store with `mode=ro` and reads operational
kinds from its `facts` table in arrival order. It does not use loops' entity fold:
repeated names remain separate facts, and `--record` requires an exact ID when a
name is ambiguous. Search is case-insensitive, all-words matching. It includes
names, messages, IDs, kinds, observers, and additional field values.

Links come from explicit `*_ref` fields, with incoming links derived from those
same references. Unresolved addresses are retained without guessing a target.
The reader does not verify store signatures. It takes one snapshot at launch;
reopen it to read new facts.

The bundled JSON contains eight unmodified operational facts selected on
2026-09-04, with original IDs and provenance. Its suggested checks were added
for this example from gruel.network's tool definitions. They are displayed for
manual use, with their scope and limitations; nothing executes stored commands.
The excerpt and store reader are historical evidence, not a diagnosis of the
current homelab.
