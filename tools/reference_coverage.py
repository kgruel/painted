"""Validate and serialize the curated public reference coverage declaration.

The declaration lives beside the existing reference specimen authority in
``tools.reference_specimens``. This module does not discover capabilities or
maintain a second specimen registry: it validates the declared specimen IDs
against ``tools.outputgen.PANELS`` supplied by the caller, then emits the small
reference-specific artifact consumed by Astro.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from tools.reference_specimens import FROZEN_CAPABILITY_FAMILIES, REFERENCE_FAMILIES


_MODES = {"specimen", "link", "omission"}


def build_reference_coverage(*, panels: Mapping[str, Any]) -> dict[str, object]:
    """Build validated, deterministic reference coverage metadata."""
    expected_family_ids = tuple(FROZEN_CAPABILITY_FAMILIES)
    declared_family_ids = tuple(str(family["id"]) for family in REFERENCE_FAMILIES)
    if declared_family_ids != expected_family_ids:
        raise ValueError(
            "reference family order/identity must match FROZEN_CAPABILITY_FAMILIES: "
            f"expected {expected_family_ids!r}, got {declared_family_ids!r}"
        )

    families: list[dict[str, object]] = []
    all_capabilities: list[str] = []
    all_entry_ids: set[str] = set()
    declared_specimens: set[str] = set()
    mode_counts: Counter[str] = Counter()

    for index, declaration in enumerate(REFERENCE_FAMILIES, start=1):
        family_id = str(declaration["id"])
        expected_capabilities = FROZEN_CAPABILITY_FAMILIES[family_id]
        entries = declaration["entries"]
        if not isinstance(entries, tuple) or not entries:
            raise ValueError(f"reference family {family_id!r} must declare entries")

        seen_in_family: list[str] = []
        serialized_entries: list[dict[str, object]] = []
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                raise TypeError(f"reference entry in {family_id!r} must be a dict")
            entry_id = str(raw_entry["id"])
            if entry_id in all_entry_ids:
                raise ValueError(f"duplicate reference entry id {entry_id!r}")
            all_entry_ids.add(entry_id)

            mode = str(raw_entry["mode"])
            if mode not in _MODES:
                raise ValueError(f"reference entry {entry_id!r} has invalid mode {mode!r}")
            mode_counts[mode] += 1

            covers = tuple(str(item) for item in raw_entry["covers"])
            if not covers:
                raise ValueError(f"reference entry {entry_id!r} covers no capabilities")
            unexpected = sorted(set(covers) - set(expected_capabilities))
            if unexpected:
                raise ValueError(
                    f"reference entry {entry_id!r} declares capabilities outside "
                    f"{family_id!r}: {unexpected!r}"
                )
            seen_in_family.extend(covers)

            specimen_ids = tuple(str(item) for item in raw_entry.get("specimen_ids", ()))
            href = raw_entry.get("href")
            link_label = raw_entry.get("link_label")
            omission_reason = raw_entry.get("omission_reason")
            if mode == "specimen":
                if not specimen_ids:
                    raise ValueError(f"specimen entry {entry_id!r} declares no specimen IDs")
                if href is not None or link_label is not None or omission_reason is not None:
                    raise ValueError(
                        f"specimen entry {entry_id!r} cannot declare link/omission fields"
                    )
                missing = sorted(set(specimen_ids) - set(panels))
                if missing:
                    raise ValueError(
                        f"specimen entry {entry_id!r} references IDs absent from PANELS: {missing!r}"
                    )
                declared_specimens.update(specimen_ids)
            elif mode == "link":
                if specimen_ids or not isinstance(href, str) or not href or not link_label:
                    raise ValueError(
                        f"link entry {entry_id!r} requires href/link_label and no specimens"
                    )
                if omission_reason is not None:
                    raise ValueError(f"link entry {entry_id!r} cannot declare omission_reason")
            else:
                if specimen_ids or href is not None or link_label is not None:
                    raise ValueError(
                        f"omission entry {entry_id!r} cannot declare specimens or a link"
                    )
                if not isinstance(omission_reason, str) or not omission_reason:
                    raise ValueError(f"omission entry {entry_id!r} requires a reason")

            serialized_entries.append(
                {
                    "id": entry_id,
                    "title": str(raw_entry["title"]),
                    "summary": str(raw_entry["summary"]),
                    "covers": list(covers),
                    "mode": mode,
                    "specimen_ids": list(specimen_ids),
                    "href": href,
                    "link_label": link_label,
                    "omission_reason": omission_reason,
                }
            )

        counts = Counter(seen_in_family)
        duplicate_capabilities = sorted(name for name, count in counts.items() if count != 1)
        missing_capabilities = sorted(set(expected_capabilities) - set(seen_in_family))
        if duplicate_capabilities or missing_capabilities:
            raise ValueError(
                f"reference family {family_id!r} must cover every capability exactly once; "
                f"duplicates={duplicate_capabilities!r}, missing={missing_capabilities!r}"
            )

        all_capabilities.extend(expected_capabilities)
        families.append(
            {
                "id": family_id,
                "index": index,
                "title": str(declaration["title"]),
                "summary": str(declaration["summary"]),
                "capabilities": list(expected_capabilities),
                "entries": serialized_entries,
            }
        )

    specimens = []
    for specimen_id in sorted(declared_specimens):
        spec = panels[specimen_id]
        specimens.append(
            {
                "id": specimen_id,
                "fragment": f"panels/{specimen_id}.html",
                "source": str(spec.demo_path),
            }
        )

    return {
        "schema_version": 1,
        "summary": {
            "family_count": len(families),
            "capability_count": len(all_capabilities),
            "entry_count": len(all_entry_ids),
            "mode_counts": {mode: mode_counts[mode] for mode in sorted(_MODES)},
            "specimen_count": len(specimens),
        },
        "families": families,
        "specimens": specimens,
    }


def reference_coverage_json(*, panels: Mapping[str, Any]) -> str:
    """Serialize coverage with stable ordering and a trailing newline."""
    return json.dumps(build_reference_coverage(panels=panels), indent=2) + "\n"
