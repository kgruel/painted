---
name: release
description: Cut and ship a painted release — merge the feature branch, tag, publish the GitHub release, verify PyPI. Use when asked to release, ship, cut a version, or merge-and-tag a finished branch.
---

# Release painted

The release path is: merge → gate → push → tag → GitHub release → PyPI (CI).
The PyPI publish is triggered by **publishing a GitHub release** (`.github/workflows/release.yml`),
not by the tag alone.

## Preconditions — verify before merging

1. **The branch is done**: `./dev check` green at head (10/10), and Kyle has read
   the branch diff. Merging is Kyle's call — never merge to main unprompted.
2. **Version + changelog already on the branch**: `pyproject.toml` version bumped,
   `CHANGELOG.md` has a `## [X.Y.Z] — YYYY-MM-DD` section with an intro paragraph
   (it becomes the release notes). These land as part of the branch's final
   "reconcile + cut" slice, not at release time. If missing, stop and add them
   on the branch first.
3. **Design doc status flipped** (PLANNED → IMPLEMENTED) and the store amended,
   if the release closes a design arc.
4. **Removing or renaming a public name?** Grep the consumers first:
   `~/Code/siftd` and `~/Code/loops`. Both pin painted **published** (not
   editable), so a removal breaks them at their next `painted>=` floor-bump, not
   instantly. If a live consumer imports the name, **harden in place** rather than
   remove (the 0.4.0 `callout` lesson — "not adopted yet" was wrong once already);
   if removal stands, sequence it: cut the painted release without the name, then
   the consumer bumps its floor in the same commit as its import switch (the
   0.5.0 completion-arc pattern). A rename is a remove + add — same caution.

## Steps

```bash
# 1. Merge — always --no-ff (the merge commit names the arc; history shows the seam)
git checkout main
git merge --no-ff <branch> -m "Merge <branch>: <one-line arc summary> (X.Y.Z)"

# 2. Re-run the gate ON MAIN post-merge — the merge itself must be green
./dev check

# 3. Push, tag, push the tag (both remotes go via origin's push URLs)
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z

# 4. Extract release notes = the changelog section body (between this version's
#    header and the previous version's header)
awk '/^## \[X.Y.Z\]/{f=1;next}/^## \[/{f=0}f' CHANGELOG.md > /tmp/relnotes.md

# 5. Publish the GitHub release — THIS triggers the PyPI workflow
gh release create vX.Y.Z --title "painted X.Y.Z — <arc name>" --notes-file /tmp/relnotes.md

# 6. Verify the publish went through
gh run list --workflow release.yml -L 1        # expect: completed success
curl -s https://pypi.org/pypi/painted/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"

# 7. Clean up
git branch -d <branch>
```

Title convention: `painted X.Y.Z — <arc name>` (e.g. "painted 0.7.0 — ref
deliveries", "painted 0.8.0 — paint(), the single entry").

## After shipping

- Emit the ship to the store: `sl emit project observation topic=session/<arc>-ship
  message="X.Y.Z SHIPPED <date>: ..."` with refs to the arc's decision/thread nodes,
  and update the arc's `roadmap`/`thread` nodes to their new status. The store is
  the operational record — session memory carries nothing painted needs.
- Consumers (loops, siftd) pin published versions and floor-bump on their own
  schedule — a release never requires same-day consumer coordination, but check
  the arc's design doc for any pre-declared consumer hazards before removing API.

## Failure notes

- PyPI workflow not firing → the release wasn't *published* (a tag alone does
  nothing; a draft release does nothing).
- Workflow uses PyPI trusted publishing (`id-token: write`, environment `pypi`) —
  no token to rotate locally; failures are on the PyPI/GitHub side.
- If the gate fails post-merge on main: fix forward on main immediately (main
  must stay green); do not tag until it passes.
- CI landmines (both hit once): `actions/setup-uv@v8` does not exist (no such
  major — check the action's actual latest); and the `release: published`
  workflow checks out the **tag's commit**, not HEAD — anything committed after
  tagging is not in the published artifact.
