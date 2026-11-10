#!/usr/bin/env python3
"""Model-check the host adapter's ticket and frame-token protocol with TLC.

    python3 verification/host/check.py            # the checks + the mutants
    python3 verification/host/check.py --trace AnyCaller   # print one run in full

Needs Java 11+ (on PATH, or installed through mise). TLC itself is fetched once
into verification/.tools/ at a pinned version and verified by hash.

Exit status is 0 only when every run ends the way EXPECT says it should: the
shipped protocol passes, the recorded finding still reproduces, and each mutant
(the model with one guard broken) is caught by the property that guards it.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "HostAdapter.tla"
TOOLS = HERE.parent / ".tools"
TLC_VERSION = "1.7.4"
TLC_URL = f"https://github.com/tlaplus/tlaplus/releases/download/v{TLC_VERSION}/tla2tools.jar"
TLC_SHA256 = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"

# name -> (config, text to break, replacement, invariant expected to fail or None)
RUNS: dict[str, tuple[str, str | None, str | None, str | None]] = {
    # The checks.
    "Shipped": ("Shipped.cfg", None, None, None),
    # FINDING (open): one Plan published onto two forks with different Blocks
    # yields equal FrameTokens. Expected to fail until that is ruled on; if this
    # starts passing, the finding was fixed - move it to the checks above.
    "AnyCaller": ("AnyCaller.cfg", None, None, "StaleHitsDrop"),
    # The mutants: the model with one guard of host.py removed.
    "mutant: publish ignores the ticket base": (
        "Shipped.cfg",
        "    /\\ p.base = adapter[b].gid                                  \\* GUARD: ticket base\n",
        "    /\\ TRUE\n",
        "NoRegress",
    ),
    "mutant: generation identity is a per-lineage counter": (
        "Shipped.cfg",
        "[gid |-> p.gid, key |-> p.key,",
        "[gid |-> adapter[b].gid + 1, key |-> p.key,",
        "StaleHitsDrop",
    ),
    "mutant: frame token omits the offset": (
        "Shipped.cfg",
        "Token(a)   == <<a.gid, a.off, a.F>>",
        "Token(a)   == <<a.gid, a.F>>",
        "StaleHitsDrop",
    ),
}


def _java() -> str:
    found = shutil.which("java")
    if found:
        return found
    if shutil.which("mise"):
        where = subprocess.run(["mise", "where", "java"], capture_output=True, text=True)
        candidate = Path(where.stdout.strip()) / "bin" / "java"
        if where.returncode == 0 and candidate.exists():
            return str(candidate)
    sys.exit("no java found: install one (e.g. `mise use -g java@temurin-25`) and rerun")


def _tlc_jar() -> Path:
    jar = TOOLS / f"tla2tools-{TLC_VERSION}.jar"
    if not jar.exists():
        TOOLS.mkdir(exist_ok=True)
        print(f"fetching TLC {TLC_VERSION} ...", file=sys.stderr)
        with urllib.request.urlopen(TLC_URL) as response:  # noqa: S310 - pinned https URL
            jar.write_bytes(response.read())
    digest = hashlib.sha256(jar.read_bytes()).hexdigest()
    if digest != TLC_SHA256:
        jar.unlink()
        sys.exit(f"tla2tools.jar hash mismatch (got {digest}); deleted, not run")
    return jar


def _run(name: str, *, show: bool) -> bool:
    config, old, new, expected = RUNS[name]
    text = SPEC.read_text()
    if old is not None and new is not None:
        if text.count(old) != 1:
            print(f"DRIFT  {name}: the text this mutant breaks is no longer in the spec")
            return False
        text = text.replace(old, new)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / SPEC.name).write_text(text)
        shutil.copy(HERE / config, Path(tmp) / config)
        done = subprocess.run(
            [_java(), "-XX:+UseParallelGC", "-cp", str(_tlc_jar()), "tlc2.TLC",
             "-config", config, "-workers", "auto", "-deadlock", SPEC.name],
            cwd=tmp, capture_output=True, text=True,
        )  # fmt: skip
    out = done.stdout
    if show:
        print(out)
    violated = re.search(r"Invariant (\w+) is violated", out)
    passed = "Model checking completed. No error has been found." in out
    if not violated and not passed:
        print(f"ERROR  {name}: TLC did not finish\n{out}{done.stderr}")
        return False
    got = violated.group(1) if violated else None
    states = re.findall(r"(\d+) distinct states found", out)
    size = f"{states[-1]} states" if states else "?"
    if got == expected:
        verdict = "pass" if got is None else f"{got} violated, as expected"
        print(f"ok     {name}: {verdict} ({size})")
        return True
    want = "pass" if expected is None else f"violate {expected}"
    print(f"FAIL   {name}: expected to {want}, got {got or 'pass'} - rerun with --trace")
    return False


def main(argv: list[str]) -> int:
    if argv[:1] == ["--trace"]:
        matches = [n for n in RUNS if argv[1:] and argv[1].lower() in n.lower()]
        if len(matches) != 1:
            sys.exit("--trace needs text matching exactly one of:\n  " + "\n  ".join(RUNS))
        _run(matches[0], show=True)
        return 0
    return 0 if all([_run(name, show=False) for name in RUNS]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
