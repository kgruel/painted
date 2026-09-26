"""Behavior at the investigation boundary: evidence, navigation, and delivery."""

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from painted import Fidelity
from painted.tui import TestSurface
from tools.capture import import_module_by_path

ROOT = Path(__file__).resolve().parents[2]
F = import_module_by_path(ROOT / "demos/examples/fieldwork.py", module_name="_fieldwork_tests")


def text(block):
    return "\n".join("".join(c.char for c in block.row(y)) for y in range(block.height))


def run(keys, *, width=110, height=30, location=None):
    app = F.Fieldwork(location=location)
    frames = TestSurface(app, width=width, height=height, input_queue=keys).run_to_completion()
    return app, frames


def test_incident_practice_rollout_chain_and_missing_evidence():
    archive = F.load_archive()
    incident = F.project(archive, F.Location())
    assert incident.selected.id == F._START
    missing = next(r for r in incident.relations if not r.available)
    assert missing.target == "practice/jellyfin-cache-nvme-move"
    practice = next(r for r in incident.relations if r.name == "journald-size-cap-provisioning")
    assert practice.direction == "in"
    view = F.project(archive, F.Location(selected=practice.target))
    assert "only media so far" in view.selected.message
    rollout = next(r for r in view.relations if "fleet-cap-rollout" in r.name)
    later = F.project(archive, F.Location(selected=rollout.target))
    assert "13/14" in later.selected.message and "NOT applied" in later.selected.message
    assert later.selected.recorded > view.selected.recorded


def test_search_follow_and_back_restore_the_reading():
    app, frames = run(
        ["/", *"journald", "enter", "j", "v", "p", "tab", "j", "enter", "backspace", "q"]
    )
    assert app.location.query == "journald"
    assert app.view.selected.name == "journald-size-cap-provisioning"
    assert app.location.fidelity.depth == 2
    assert app.location.fidelity.shows("provenance")
    assert app.location.focus == "links" and app.location.link_index == 1
    assert any("journald-fleet-cap-rollout" in frame.text for frame in frames)
    assert "Provenance" in frames[-1].text


def test_missing_link_stays_in_place_with_an_explanation():
    app, frames = run(["tab", "enter", "q"])
    assert app.view.selected.id == F._START
    assert not app.history
    assert any("unavailable in this snapshot" in frame.text for frame in frames)


def test_search_capture_keeps_command_keys_as_text_and_escape_cancels():
    app, _ = run(["/", *"qpc", "escape", "q"])
    assert app.location == F.Location()
    assert not app.history


def test_no_matches_is_not_a_health_verdict():
    app, frames = run(["/", *"no-such-evidence", "enter", "tab", "enter", "q"])
    assert not app.view.matches and app.view.selected is None
    assert any("No matching records" in f.text for f in frames)
    assert any("current health" in f.text for f in frames)


def test_scroll_reaches_the_end_and_back_restores_position():
    location = F.Location(fidelity=Fidelity(depth=3, visible=frozenset({"checks"})))
    app, _ = run(
        ["page_down"] * 15 + ["tab", "j", "enter", "backspace", "q"],
        width=80,
        height=18,
        location=location,
    )
    assert app.location.scroll > 0
    assert app.location.scroll == app.max_scroll
    assert app.view.selected.id == F._START


@pytest.mark.parametrize("width,height", [(1, 1), (20, 8), (80, 24), (110, 30)])
def test_small_and_large_screens_preserve_selection(width, height):
    app, frames = run(
        ["j", "tab", "v", "page_down", "?", "escape", "q"], width=width, height=height
    )
    assert frames
    assert all(f.buffer.width == width and f.buffer.height == height for f in frames)
    assert app.view.selected is not None


def test_tui_paints_the_same_evidence_as_cli_renderer():
    app, frames = run(["q"], width=80, height=50)
    block = F._render(app.view, app.location.fidelity, 80)
    assert frames[0].lines[3 : 3 + block.height] == text(block).splitlines()


@pytest.mark.parametrize("depth", range(4))
def test_each_named_facet_is_visible_even_at_quiet_depth(depth):
    view = F._fetch()
    base = text(F._render(view, Fidelity(depth=depth), 88))
    for tag, expected in (
        ("checks", "How much disk space"),
        ("provenance", "Recorded at:"),
        ("fields", "Recorded fields"),
        ("matches", "Matching records"),
    ):
        rendered = text(F._render(view, Fidelity(depth=depth, visible=frozenset({tag})), 88))
        assert expected in rendered
        if not F._shown(Fidelity(depth=depth), tag):
            assert expected not in base


def test_recording_time_does_not_replace_reported_event_date():
    archive = F.load_archive()
    record = next(r for r in archive.records if r.name == "gitlab-oom-ssh-banner-2026-04-20")
    assert record.event_date == "2026-04-20"
    assert record.recorded.startswith("2026-07-03")


def test_store_reader_is_read_only_and_preserves_revisions_in_arrival_order(tmp_path):
    path = tmp_path / "facts.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE facts (id, kind, ts, observer, payload, arrival_ordinal, arrival_seq)"
    )
    for ordinal, (id, kind, ts) in enumerate(
        (("a", "incident", 100), ("b", "incident", 50), ("c", "credential", 110))
    ):
        payload = json.dumps({"name": "same-name", "message": id})
        connection.execute(
            "INSERT INTO facts VALUES (?,?,?,?,?,?,?)",
            (id, kind, ts, "operator", payload, ordinal, 0),
        )
    connection.commit()
    connection.close()
    before = path.read_bytes()
    archive = F.load_archive(path)
    assert [r.id for r in archive.records] == ["a", "b"]
    assert len({r.name for r in archive.records}) == 1
    assert path.read_bytes() == before
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        F.load_archive(missing)
    assert not missing.exists()


def test_renderer_exact_width_at_every_depth():
    for width in (0, 1, 8, 28, 80, 120):
        for depth in range(4):
            assert F._render(F._fetch(), Fidelity(depth=depth), width).width == width


def test_cli_flags_and_json_reach_the_same_selection():
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "demos/examples/fieldwork.py"),
            "--match",
            "banner",
            "--kind",
            "incident",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(proc.stdout)
    assert value["query"] == "banner"
    assert value["selected"]["name"] == "gitlab-oom-ssh-banner-2026-04-20"
    assert len(value["matches"]) == 1


def synthetic_archive():
    records = tuple(
        F._record(
            {
                "id": str(i),
                "kind": "incident",
                "ts": i,
                "observer": "synthetic test",
                "payload": {
                    "name": "long linked label " * 20 if i else "subject",
                    "message": "A long recorded account. " * 80,
                    "next_ref": str((i + 1) % 8),
                    "extra": "synthetic field",
                },
            }
        )
        for i in range(8)
    )
    return F.Archive("synthetic archive", records)


@pytest.mark.parametrize("width,height", [(80, 18), (20, 8), (110, 6)])
@pytest.mark.parametrize("focus", ["records", "links"])
@pytest.mark.parametrize("notice", ["", "A long notice " * 30], ids=["no-notice", "long-notice"])
def test_viewport_evidence_survives_labels_facets_and_notices(width, height, focus, notice):
    app = F.Fieldwork(
        synthetic_archive(),
        F.Location(
            selected="0",
            focus=focus,
            fidelity=Fidelity(depth=3, visible=frozenset(t.name for t in F._TAGS)),
        ),
    )
    app.notice = notice
    frames = TestSurface(app, width=width, height=height).run_to_completion()
    detail_width = width - 34 if width >= 88 else width
    total = F._render(app.view, app.location.fidelity, detail_width).height
    assert total > app.body_height
    assert f"lines 1-{app.body_height}/{total}" in frames[0].text
    if width >= 88:
        # With one sidebar row, omission counts take precedence over its heading.
        count = len(app.view.relations if focus == "links" else app.view.matches)
        assert f"{count} below" in frames[0].lines[3][:32]


@pytest.mark.parametrize("width,height", [(1, 1), (8, 2), (20, 4)])
def test_tiny_frames_prioritize_evidence_over_chrome(width, height):
    app = F.Fieldwork(synthetic_archive(), F.Location(selected="0"))
    frames = TestSurface(app, width=width, height=height).run_to_completion()
    assert "+" in frames[0].text or "lines 0-0/" in frames[0].text


@pytest.mark.parametrize("width,height", [(80, 12), (20, 8)])
def test_help_scrolls_to_final_explanation_without_moving_investigation(width, height):
    location = F.Location(selected="0", focus="links", scroll=2, link_index=1)
    app = F.Fieldwork(synthetic_archive(), location)
    keys = ["?", "page_down", "page_up"] + ["page_down"] * 100
    frames = TestSurface(app, width=width, height=height, input_queue=keys).run_to_completion()
    assert "lines 1-" in frames[1].text
    assert frames[2].text != frames[1].text
    assert frames[3].text == frames[1].text
    body = " ".join(line.strip() for line in frames[-1].lines[3 : height - 2])
    assert "verdict is inferred." in body
    assert app.help_scroll == app.help_max_scroll > 0
    assert app.location == location
    for key in ("home", "down", "up", "end"):
        app.on_key(key)
    assert app.help_scroll == app.help_max_scroll
    app.on_key("escape")
    assert not app.help and app.location == location


@pytest.mark.parametrize("width,height", [(0, 8), (20, 0), (0, 0)])
def test_zero_space_is_the_physical_evidence_waiver(width, height):
    app = F.Fieldwork(synthetic_archive(), F.Location(selected="0"))
    frames = TestSurface(app, width=width, height=height, input_queue=["?"]).run_to_completion()
    assert all(f.buffer.width == width and f.buffer.height == height for f in frames)
    assert not any(f.text.strip() for f in frames)


def test_natural_width_does_not_wrap_long_text_or_pad_short_text():
    archive = synthetic_archive()
    view = F.project(archive, F.Location(selected="0"))
    block = F._render(view, Fidelity(depth=2), None)
    assert view.selected.message in text(block).splitlines()[4]
    assert block.width == len(view.selected.message)
    summary = F._render(view, Fidelity(depth=0), None)
    assert summary.width == len(text(summary).rstrip()) < 88
    empty = replace(view, selected=None, query="long query " * 50)
    assert empty.query in text(F._render(empty, Fidelity(), None))
    for width in (0, 1, 8, 28, 80, 120):
        for depth in range(4):
            assert F._render(view, Fidelity(depth=depth), width).width == width


def test_cli_help_does_not_open_the_store():
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "demos/examples/fieldwork.py"),
            "--store",
            "/no/such/store.db",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--record" in proc.stdout and "--checks" in proc.stdout
