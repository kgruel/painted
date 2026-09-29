from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import tools.reference_coverage as coverage_module
from tools.outputgen import PANELS, REFERENCE_COVERAGE_PATH, _reference_coverage_json
from tools.reference_coverage import build_reference_coverage, reference_coverage_json
from tools.reference_specimens import FROZEN_CAPABILITY_FAMILIES, REFERENCE_FAMILIES


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_reference_coverage_accounts_for_every_individual_capability_once() -> None:
    report = build_reference_coverage(panels=PANELS)

    assert [family["id"] for family in report["families"]] == list(FROZEN_CAPABILITY_FAMILIES)
    declared: list[str] = []
    expected: list[str] = []
    for family in report["families"]:
        assert family["capabilities"] == list(FROZEN_CAPABILITY_FAMILIES[family["id"]])
        expected.extend(FROZEN_CAPABILITY_FAMILIES[family["id"]])
        for entry in family["entries"]:
            declared.extend(entry["covers"])

    assert set(declared) == set(expected)
    assert len(declared) == len(set(declared)) == 49
    assert report["summary"]["family_count"] == 9
    assert report["summary"]["capability_count"] == 49


def test_reference_modes_are_honest_and_specimens_trace_to_panels() -> None:
    report = build_reference_coverage(panels=PANELS)
    specimen_records = {record["id"]: record for record in report["specimens"]}

    for family in report["families"]:
        for entry in family["entries"]:
            if entry["mode"] == "specimen":
                assert entry["specimen_ids"]
                assert entry["href"] is None
                for specimen_id in entry["specimen_ids"]:
                    assert specimen_id in PANELS
                    assert specimen_records[specimen_id] == {
                        "id": specimen_id,
                        "fragment": f"panels/{specimen_id}.html",
                        "source": PANELS[specimen_id].demo_path,
                    }
            elif entry["mode"] == "link":
                assert entry["href"] and entry["link_label"]
                assert entry["specimen_ids"] == []
            else:
                assert entry["mode"] == "omission"
                assert entry["omission_reason"]
                assert entry["specimen_ids"] == []

    delivery = next(family for family in report["families"] if family["id"] == "delivery")
    delivery_modes = {
        capability: entry["mode"] for entry in delivery["entries"] for capability in entry["covers"]
    }
    assert delivery_modes == {
        "static": "specimen",
        "live": "link",
        "stream-surface": "link",
        "interactive": "link",
    }


def test_reference_coverage_rejects_unknown_panel_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    families = copy.deepcopy(REFERENCE_FAMILIES)
    families[0]["entries"][2]["specimen_ids"] = ("not_a_panel",)
    monkeypatch.setattr(coverage_module, "REFERENCE_FAMILIES", families)

    with pytest.raises(ValueError, match="absent from PANELS"):
        build_reference_coverage(panels=PANELS)


def test_reference_coverage_rejects_duplicate_individual_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    families = copy.deepcopy(REFERENCE_FAMILIES)
    families[0]["entries"][2]["covers"] = ("composition", "composition", "borders")
    monkeypatch.setattr(coverage_module, "REFERENCE_FAMILIES", families)

    with pytest.raises(ValueError, match="every capability exactly once"):
        build_reference_coverage(panels=PANELS)


def test_reference_coverage_serialization_and_committed_artifact_are_deterministic() -> None:
    first = reference_coverage_json(panels=PANELS)
    second = _reference_coverage_json()

    assert first == second
    assert first.endswith("\n")
    assert json.loads(first)["schema_version"] == 1
    assert (REPO_ROOT / REFERENCE_COVERAGE_PATH).read_text(encoding="utf-8") == first
