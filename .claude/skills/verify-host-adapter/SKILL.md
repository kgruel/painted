---
name: verify-host-adapter
description: Model-check the host viewport adapter's ticket and frame-token protocol with TLC. Use when a change touches `ViewportAdapter.plan`, `publish`, `resize`, the scroll ops, `_token`/`token`/`frame`, `resolve`, `_GenerationId`, `Plan`, or `FrameToken` in `src/painted/host.py`, or `HostViewport._install_generation`/`frame`/`route_click` — or when asked whether the host adapter model is still true to the code.
---

# Verify the host adapter protocol

`verification/host/HostAdapter.tla` is a TLA+ model of how a host drives
`ViewportAdapter` (`src/painted/host.py`, HOST_RUNG_DESIGN §6). TLC explores
every interleaving of the adapter's method calls, across two pure forks, up to
the bounds below. Tests check the orders someone wrote; this checks all of them.

## The two properties

| Property | In plain words | Harm if it breaks |
|---|---|---|
| `NoRegress` | A publish that lost the race never installs older renderer inputs over newer ones. | The screen settles on a stale render with nothing outstanding to replace it. |
| `StaleHitsDrop` | `resolve` returns a non-stale hit only against an adapter that maps coordinates exactly as the painted frame did, on any fork. | A click selects a row the user was not shown. |

## Run it

```bash
./dev verify
```

About four and a half minutes. Needs Java 11+ on PATH or installed through mise; TLC 1.7.4
is fetched once into `verification/.tools/` and verified by hash. It is not part
of `./dev check` — only the drift ratchet is (see the sync record below).

Four runs, and exit 0 means each ended as recorded:

- `AnyCaller` passes — the protocol under any caller its types allow, ticket
  reuse included (the shipped hosts are a subset of these runs).
- three mutants, each the model with one guard removed, each caught.

To read a run in full: `./dev verify --trace AnyCaller`.
If the pstack `/statechart` skill is installed, read any violation with it: it
tells the shortest path to the broken state in plain words.

## What the model covers

Each model action is one method call on the frozen adapter. The adapter is
pure, so one call is one indivisible step.

| Model | Code (`src/painted/host.py`) |
|---|---|
| `Plan(b)` — ticket `[key, base]`, `base` = current generation; mints nothing | `ViewportAdapter.plan` → `Plan(action, key, base)` |
| `plans` never shrinks — any ticket may be published any number of times | `Plan` is a frozen value; nothing consumes it |
| `Publish` guard `p.base = adapter[b].gid` | `publish`: `if plan.base is not current: return None` |
| `Publish` stamp `gid |-> nextGid, key |-> p.key`, then `nextGid + 1` | `publish`: `_Generation(key=plan.key, gid=_GenerationId(), …)` — a fresh identity per accepted publish |
| `Scroll(b, o)` — offset moves, generation does not | `scroll`, `page_up`, `page_down`, `home`, `end`, `scroll_to`, `scroll_into_view` |
| `Resize(b, h, o)` — height moves, generation does not | `resize` |
| `Token(a) == <<gid, off, F>>` | `_token` → `FrameToken(generation, offset, height)` |
| `Frame(b)` records the painted token | `ViewportAdapter.frame`; `HostViewport.frame` sets `last_token` |
| `StaleHitsDrop` compares tokens | `resolve`: `if token != self._token(): return Hit(…, stale=True)` |
| `Fork` — a second reference to a frozen value | frozen dataclass; no code |
| `AnyCaller.cfg` — the only config | any caller the types allow. `HostViewport._install_generation` (plan and publish in one step, each ticket once) is a subset of these runs, so it needs no config of its own |

**The sync record is `verification/host/sync.json`**: the covered symbols and a
hash of their ASTs (docstrings and comments excluded). Tier 0 of `./dev check`
fails when the covered code no longer matches it. Run `./dev verify --sync` to
move it forward — only after you have confirmed every row above still describes
the code. A new method that writes the same state belongs in `covered` too.

**Bounds:** 2 forks, 3 renderer-input versions, 4 distinct `Plan` tickets,
4 accepted publishes, 2 distinct Blocks, offsets {0,1}, heights {1,2} — about
22.5 million states.

**Left out, deliberately:**

- The anchor policy and all clamping. `Publish` and `Resize` may land on any
  offset, a superset of what the code picks, so the two properties hold for any
  anchor policy — but nothing here says the policy picks the *right* offset.
- Region resolution inside `resolve` (content / evidence / padding).
- The `HostEvent` seam (`observed` / `current` tokens).
- Liveness: nothing checks that a host re-plans after a rejected publish.
- `evidence_ref` is not in the token; changing it between paint and click is
  not modelled.

## When your change touches a row in the table

1. Change the model to describe the code as you are leaving it — from the code,
   not from what makes TLC pass. If one method now does two things a host could
   interleave, it becomes two actions.
2. Run the check.
3. If `AnyCaller` fails, run it with `--trace` and replay the steps against the
   real code. A step the code cannot take means the model is wrong: fix the
   model. If every step can happen, the code has a bug: report the steps in the
   code's words. Never weaken a property or a config to get a pass.
4. If a mutant reports `DRIFT`, the spec line it breaks has moved. Update the
   mutant's text in `check.py` and confirm it is still caught — a check that can
   no longer fail proves nothing.
5. Update the table in this file, then `./dev verify --sync`, in the same change.

## Closed finding: a ticket published twice

A `Plan` is a frozen value nothing consumes, so a caller can publish one plan
twice from the same base. TLC found, under `AnyCaller.cfg`:

1. `plan = a.plan(key)` on an empty adapter `a`.
2. `x = a.publish(block_one, plan)` and `y = a.publish(block_two, plan)` — both
   accepted, because `a` is frozen and still sits on the plan's base.
3. `x.token() == y.token()`, so a frame painted from `x` resolved non-stale
   against `y`, through different content.

The identity was minted in `plan()` and carried on the ticket (`Plan.proposed`),
so every publish of one plan stamped the same identity. Fixed by minting the
`_GenerationId` in `publish`, once per accepted publish; `Plan` no longer carries
an identity. Reuse is now harmless, so the model has one config (`AnyCaller`)
and the `TicketReuse` switch is gone. The unit regression is
`test_one_plan_published_twice_does_not_collide` in
`tests/unit/test_host_adapter.py`.
