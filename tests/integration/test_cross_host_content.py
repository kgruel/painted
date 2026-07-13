"""Cross-host content comparability (RENDER_MODEL.md law 1, Milestone 1).

One semantic renderer, delivered through the static and live paths, must
produce the same content Block for the same inputs — comparable *before*
serialization, which is exactly what ``capture_content_blocks``
(tests/helpers.py) exposes. The renderer here is law-7 clean by
construction (reads only fidelity + allocation), so any divergence these
tests catch is the *framework* leaking destination or lifecycle facts into
the content path, not the app misbehaving.

The pair under comparison is a streaming runner: ``--live`` exists only
when ``fetch_stream`` is declared (the honesty rule), so the honest
cross-host pair is ``--static`` (fetch → one Block) vs ``--live``
(fetch_stream → a Block per state, the last state shared with fetch).
"""

from __future__ import annotations

from painted import Block, Fidelity, Style

from tests.helpers import assert_blocks_equal, capture_content_blocks

_STATES = [
    {"name": "api-gateway", "state": "ok"},
    {"name": "billing", "state": "degraded"},
    {"name": "search", "state": "ok"},
]


def _render(service: dict, fidelity: Fidelity, width: int | None) -> Block:
    text = f"{service['name']}: {service['state']}"
    if fidelity.depth >= 2:
        text += " (detail)"
    w = 40 if width is None else min(width, 40)
    return Block.text(text, Style(), width=w)


async def _stream():
    for state in _STATES:
        yield state


def _fetch() -> dict:
    return _STATES[-1]


class TestCrossHostContent:
    def test_static_and_live_deliver_the_same_content_block(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        static_code, static_blocks = capture_content_blocks(
            ["--static"], renderer=_render, fetch=_fetch, fetch_stream=_stream
        )
        live_code, live_blocks = capture_content_blocks(
            ["--live"], renderer=_render, fetch=_fetch, fetch_stream=_stream
        )
        capsys.readouterr()

        assert static_code == 0 and live_code == 0
        assert len(static_blocks) == 1
        assert len(live_blocks) == len(_STATES)
        # the shared final state: one renderer, two hosts, one content Block
        assert_blocks_equal(static_blocks[0], live_blocks[-1])

    def test_live_path_renders_deterministically(self, monkeypatch, capsys):
        """Law 1 through the live host: same states, same Blocks, run to run."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        _, first = capture_content_blocks(
            ["--live"], renderer=_render, fetch=_fetch, fetch_stream=_stream
        )
        _, second = capture_content_blocks(
            ["--live"], renderer=_render, fetch=_fetch, fetch_stream=_stream
        )
        capsys.readouterr()

        assert len(first) == len(second) == len(_STATES)
        for a, b in zip(first, second):
            assert_blocks_equal(a, b)

    def test_fidelity_flags_reach_both_hosts_identically(self, monkeypatch, capsys):
        """The depth axis composes with delivery: -v changes the content Block
        the same way under both hosts (facet of law 1 the loops spike relies on)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        _, static_blocks = capture_content_blocks(
            ["-v", "--static"], renderer=_render, fetch=_fetch, fetch_stream=_stream
        )
        _, live_blocks = capture_content_blocks(
            ["-v", "--live"], renderer=_render, fetch=_fetch, fetch_stream=_stream
        )
        capsys.readouterr()

        assert_blocks_equal(static_blocks[0], live_blocks[-1])
