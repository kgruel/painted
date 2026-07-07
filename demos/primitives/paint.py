#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""paint() — the single entry point.

paint(subject) transcribes what a value *declares*: scalars print directly,
a dict its key/value pairs, a list its items, a dataclass/Enum its declared
shape — recursively. It never *invents* a shape the subject didn't declare
(a bare list is items, not a chart; that claim needs lens=chart_lens).

This is the top of the ladder — the recurring verb the whole stack renders
through. Everything below it (Block, compose, print_block) is done for you.

Run: uv run demos/primitives/paint.py
"""

from dataclasses import dataclass

from painted import paint


def demo_scalars() -> None:
    paint("deploy complete")
    paint(42)
    paint(True)
    paint()


def demo_dict() -> None:
    paint({"host": "prod-1", "status": "healthy", "uptime": "14d 3h", "cpu": 0.45})
    paint()


def demo_list() -> None:
    paint(["api", "worker", "scheduler", "cache"])
    paint()


def demo_nested() -> None:
    # Recursive transcription: the nested dict stays key/value, never a tree.
    paint(
        {
            "cluster": {
                "prod-1": {"status": "healthy", "cpu": 0.45},
                "prod-2": {"status": "degraded", "cpu": 0.91},
            },
            "version": "2.4.1",
        }
    )
    paint()


def demo_declared() -> None:
    # A declared schema transcribes its fields — the "wide" base case.
    @dataclass
    class Server:
        name: str
        port: int
        healthy: bool

    paint(Server("api", 8080, True))
    paint()


def demo_items_not_chart() -> None:
    # A bare numeric list is *items*, not a chart — paint never invents "a series".
    paint([3, 7, 2, 9, 5, 8, 1, 6, 4, 10, 3, 7])


def demo() -> None:
    demo_scalars()
    demo_dict()
    demo_list()
    demo_nested()
    demo_declared()
    demo_items_not_chart()


if __name__ == "__main__":
    demo()
