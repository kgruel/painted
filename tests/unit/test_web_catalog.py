from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from painted._demo_discovery import DEMO_TIERS, discover_demos
from tools.outputgen import CATALOG_PATH, PANELS, _catalog_json
from tools.web_catalog import build_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_KEYS = {
    "id",
    "tier",
    "name",
    "slug",
    "title",
    "summary",
    "source",
    "command",
    "checkout_command",
    "invocations",
    "has_main",
}
SPECIMEN_KEYS = {"id", "fragment", "source", "render_as", "width"}


def _catalog():
    return build_catalog(repo_root=REPO_ROOT, demos=discover_demos(), panels=PANELS)


def test_catalog_has_exact_discovery_and_panel_coverage() -> None:
    catalog = _catalog()
    discovered = [entry for entry in discover_demos() if entry.group]

    assert [record["id"] for record in catalog["demos"]] == [
        f"{entry.group}/{entry.name}" for entry in discovered
    ]
    assert len({record["id"] for record in catalog["demos"]}) == len(discovered)
    assert {record["id"] for record in catalog["specimens"]} == set(PANELS)


def test_catalog_v1_shape_and_serialization_are_deterministic() -> None:
    catalog = _catalog()

    assert set(catalog) == {"schema_version", "demo_tiers", "demos", "specimens"}
    assert catalog["schema_version"] == 1
    assert catalog["demo_tiers"] == [
        {"id": tier, "order": order} for order, tier in enumerate(DEMO_TIERS)
    ]
    assert all(set(record) == DEMO_KEYS for record in catalog["demos"])
    assert all(set(record) == SPECIMEN_KEYS for record in catalog["specimens"])

    first = _catalog_json(repo_root=REPO_ROOT)
    second = _catalog_json(repo_root=REPO_ROOT)
    assert first == second
    assert json.loads(first) == catalog
    assert first.endswith("\n")


def test_catalog_sources_and_specimens_are_traceable() -> None:
    catalog = _catalog()

    for record in catalog["demos"]:
        assert not Path(record["source"]).is_absolute()
        assert "\\" not in record["source"]
        assert (REPO_ROOT / record["source"]).is_file()
        assert record["checkout_command"] == f"uv run {record['source']}"

    for record in catalog["specimens"]:
        spec = PANELS[record["id"]]
        assert record == {
            "id": record["id"],
            "fragment": f"panels/{record['id']}.html",
            "source": Path(spec.demo_path).as_posix(),
            "render_as": spec.render_as,
            "width": spec.width,
        }
        assert (REPO_ROOT / record["source"]).is_file()
        assert (REPO_ROOT / "web/src/generated" / record["fragment"]).is_file()


def test_ambiguous_installed_selectors_are_not_published() -> None:
    catalog = _catalog()
    by_id = {record["id"]: record for record in catalog["demos"]}
    selector_counts = Counter(entry.name for entry in discover_demos())

    assert by_id["patterns/layers"]["command"] is None
    assert by_id["apps/layers"]["command"] is None
    for record in catalog["demos"]:
        expected = (
            f"painted demos {record['name']}" if selector_counts[record["name"]] == 1 else None
        )
        assert record["command"] == expected


def test_committed_catalog_matches_generator() -> None:
    assert (REPO_ROOT / CATALOG_PATH).read_text(encoding="utf-8") == _catalog_json(
        repo_root=REPO_ROOT
    )
