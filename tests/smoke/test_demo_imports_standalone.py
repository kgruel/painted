"""Every demo imports in a fresh interpreter, with only what a real run gives it.

The blind spot this closes: `tests/conftest.py` puts `demos/showcase` on
sys.path for the whole pytest session, so any in-process test — including the
liveness smoke — resolves a demo's private-sibling imports whether or not the
demo's *own* loader would have. A demo can therefore be import-broken on every
real run path while all ten gate tiers stay green. That is not hypothetical: it
happened the moment harmonograph gained `from _plaque import NOTE_TAG` while
harmonograph_lab still exec'd it with no path setup of its own.

So this runs in a subprocess, and gives each demo exactly one thing: its own
directory on sys.path. That is the contract every real loader implements —
`uv run` by putting the script's directory there, and `painted demos <name>` /
`tools/capture.py` / the lab's own `_load_showcase` by appending it around the
exec. A demo that needs more than that is a demo that will not run.

Tier 1 by design (`tests/CLAUDE.md`): the cheapest thing that can fail, in a
fresh subprocess, asserting only that importing does not raise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent
_DEMOS = _PROJECT / "demos"

# One subprocess for all of them: the isolation that matters is from the test
# session's sys.path, not from each other. Each demo is exec'd under a private
# module name so `if __name__ == "__main__"` guards stay inert, with sys.path
# saved and restored around it so one demo's siblings never leak to the next.
_PROBE = r"""
import importlib.util, sys, traceback
from pathlib import Path

demos = Path(sys.argv[1])
failures = []
for path in sorted(demos.rglob("*.py")):
    if path.name.startswith("_") or "__pycache__" in path.parts:
        continue
    name = "_standalone_" + "_".join(path.relative_to(demos).with_suffix("").parts)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    saved = sys.path[:]
    sys.path.append(str(path.parent))
    try:
        spec.loader.exec_module(module)
    except BaseException:
        failures.append(
            str(path.relative_to(demos)) + "\n" + traceback.format_exc(limit=3)
        )
    finally:
        sys.path[:] = saved
        sys.modules.pop(name, None)

if failures:
    print("\n\n".join(failures))
    sys.exit(1)
"""


def test_every_demo_imports_with_only_its_own_directory_on_the_path() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(_DEMOS)],
        capture_output=True,
        text=True,
        cwd=_PROJECT,
        timeout=180,
    )
    assert result.returncode == 0, (
        "demo(s) that cannot import on a real run path:\n\n" + result.stdout + result.stderr
    )
