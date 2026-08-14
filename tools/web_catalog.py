"""Deterministic website catalog derived from runtime demo discovery."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal, Mapping, Protocol, Sequence, TypedDict, cast

from painted._demo_discovery import DEMO_TIERS, DemoEntry

DemoTierId = Literal["primitives", "patterns", "apps", "examples", "showcase"]
RenderAs = Literal["block", "plain", "json"]


class PanelSpec(Protocol):
    demo_path: str
    render_as: RenderAs
    width: int


class DemoTierRecord(TypedDict):
    id: DemoTierId
    order: int


class DemoRecord(TypedDict):
    id: str
    tier: DemoTierId
    name: str
    slug: str
    title: str
    summary: str
    source: str
    command: str | None
    checkout_command: str
    invocations: list[str]
    has_main: bool


class SpecimenRecord(TypedDict):
    id: str
    fragment: str
    source: str
    render_as: RenderAs
    width: int


class CatalogV1(TypedDict):
    schema_version: Literal[1]
    demo_tiers: list[DemoTierRecord]
    demos: list[DemoRecord]
    specimens: list[SpecimenRecord]


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    """Return a checkout path in the catalog's repo-relative POSIX form."""
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"catalog source is outside the repository: {path}") from exc
    return relative.as_posix()


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def build_catalog(
    *,
    repo_root: Path,
    demos: Sequence[DemoEntry],
    panels: Mapping[str, PanelSpec],
) -> CatalogV1:
    """Build CatalogV1 without discovering demos or specimens independently."""
    tier_ids = cast(tuple[DemoTierId, ...], DEMO_TIERS)
    tier_order = {tier: order for order, tier in enumerate(tier_ids)}
    tiered_demos = [entry for entry in demos if entry.group]
    selector_counts = Counter(entry.name for entry in demos)

    unknown_tiers = sorted({entry.group for entry in tiered_demos} - set(tier_ids))
    if unknown_tiers:
        raise ValueError(f"unknown demo tiers: {', '.join(unknown_tiers)}")

    records: list[DemoRecord] = []
    seen_ids: set[str] = set()
    for entry in sorted(tiered_demos, key=lambda item: (tier_order[item.group], item.name)):
        tier = cast(DemoTierId, entry.group)
        identity = f"{tier}/{entry.name}"
        if identity in seen_ids:
            raise ValueError(f"duplicate demo identity: {identity}")
        seen_ids.add(identity)

        source = _repo_relative(entry.path, repo_root=repo_root)
        records.append(
            {
                "id": identity,
                "tier": tier,
                "name": entry.name,
                "slug": entry.name,
                "title": _title(entry.name),
                "summary": entry.description,
                "source": source,
                "command": (
                    f"painted demos {entry.name}" if selector_counts[entry.name] == 1 else None
                ),
                "checkout_command": f"uv run {source}",
                "invocations": list(entry.invocations),
                "has_main": entry.has_main,
            }
        )

    specimens: list[SpecimenRecord] = []
    for name, spec in sorted(panels.items()):
        source = _repo_relative(repo_root / spec.demo_path, repo_root=repo_root)
        specimens.append(
            {
                "id": name,
                "fragment": f"panels/{name}.html",
                "source": source,
                "render_as": spec.render_as,
                "width": spec.width,
            }
        )

    return {
        "schema_version": 1,
        "demo_tiers": [{"id": tier, "order": order} for order, tier in enumerate(tier_ids)],
        "demos": records,
        "specimens": specimens,
    }


def catalog_json(
    *,
    repo_root: Path,
    demos: Sequence[DemoEntry],
    panels: Mapping[str, PanelSpec],
) -> str:
    """Serialize CatalogV1 in its committed, reviewable representation."""
    return (
        json.dumps(
            build_catalog(repo_root=repo_root, demos=demos, panels=panels),
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
