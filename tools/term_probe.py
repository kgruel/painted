#!/usr/bin/env python3
"""Terminal probe: is DEC 2026 synchronized output actually honored?

Painted's InPlaceRenderer wraps every frame in CSI ?2026h/l so the terminal
composites it atomically. This probe isolates that assumption from painted
entirely (no painted imports — pure escape bytes):

1. DECRQM  — query the terminal: "do you recognize mode 2026?" (definitive)
2. SYNCED  — rewrite a region with a deliberate mid-frame stall + flush,
             wrapped in 2026. Honored sync => rock solid. Tearing => the
             wrap is being ignored in this window state.
3. CONTROL — the same hostile rewrite with no sync wrap. This SHOULD
             visibly tear/band; if it doesn't, the test isn't probing.

Run it focused, then run it again and immediately click to another window:

    uv run tools/term_probe.py            # watch focused
    uv run tools/term_probe.py --delay 3  # 3s to background it, then watch

Compare: if SYNCED is solid focused but tears backgrounded, the terminal
drops synchronized output for unfocused windows — renderer granularity is
the only remaining lever and the bug report belongs upstream.
"""

from __future__ import annotations

import argparse
import select
import sys
import termios
import time
import tty

ROWS = 10
WIDTH = 60
FPS = 10
SECONDS = 5
STALL = 0.04  # mid-frame stall: a wide-open window for an unsynced compositor


def decrqm_2026() -> str:
    """Ask via DECRQM whether mode 2026 is recognized. Returns a verdict."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?2026$p")
        sys.stdout.flush()
        resp = ""
        while select.select([fd], [], [], 0.3)[0]:
            resp += sys.stdin.read(1)
            if resp.endswith("y"):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # Reply shape: CSI ? 2026 ; Ps $ y — Ps: 0 unrecognized, 1 set, 2 reset,
    # 3 permanently set, 4 permanently reset.
    if "$y" not in resp:
        return "no DECRQM reply — terminal doesn't answer mode queries"
    ps = resp.split(";")[-1].split("$")[0]
    return {
        "0": "mode 2026 NOT recognized",
        "1": "mode 2026 recognized (currently set)",
        "2": "mode 2026 recognized (currently reset)",
        "3": "mode 2026 permanently set",
        "4": "mode 2026 permanently reset",
    }.get(ps, f"unexpected reply: {resp!r}")


def torture(label: str, synced: bool) -> None:
    """Alternate two high-contrast frames with a hostile mid-frame stall."""
    out = sys.stdout
    out.write(f"{label}\n" + "\n" * ROWS)
    out.flush()
    for i in range(FPS * SECONDS):
        glyph = "█" if i % 2 == 0 else "·"
        line = glyph * WIDTH
        if synced:
            out.write("\x1b[?2026h")
        out.write(f"\x1b[{ROWS}A")
        for r in range(ROWS):
            out.write(line[: WIDTH - 8] + f"  row {r}\x1b[0K\n")
            if r == ROWS // 2:
                out.flush()
                time.sleep(STALL)  # half the frame is on screen right now
        if synced:
            out.write("\x1b[?2026l")
        out.flush()
        time.sleep(max(0.0, 1 / FPS - STALL))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=int, default=0, help="seconds to background the window first")
    args = parser.parse_args()

    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print("term_probe needs a real TTY (run it directly in the terminal).")
        return 1

    print(f"DECRQM: {decrqm_2026()}")
    if args.delay:
        print(f"backgrounding window in {args.delay}s — click away now...")
        time.sleep(args.delay)

    sys.stdout.write("\x1b[?25l")
    try:
        torture("SYNCED  (2026-wrapped, mid-frame stall) — should be rock solid:", synced=True)
        torture("CONTROL (no sync wrap, same stall) — SHOULD tear/band:", synced=False)
    finally:
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()
    print("done. verdict: solid SYNCED + tearing CONTROL = sync honored here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
