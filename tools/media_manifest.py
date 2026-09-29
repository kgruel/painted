"""Validate VHS recipes and emit deterministic website media metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal, Mapping, Sequence, TypedDict

from tools.recording_recipes import Publication, RecordingRecipe
from tools.web_catalog import CatalogV1

_HOMEPAGE_ID = re.compile(r"homepage/[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SET_WIDTH = re.compile(r"^\s*Set\s+Width\s+(\d+)\s*$", re.MULTILINE)
_SET_HEIGHT = re.compile(r"^\s*Set\s+Height\s+(\d+)\s*$", re.MULTILINE)
_SET_FRAMERATE = re.compile(r"^\s*Set\s+Framerate\s+(\d+)\s*$", re.MULTILINE)
_OUTPUT = re.compile(r'^\s*Output\s+"?([^"\n]+?)"?\s*$', re.MULTILINE)


class ViewportRecord(TypedDict):
    width: int
    height: int


class PosterRecord(TypedDict):
    path: str
    frame: int


class MediaRecord(TypedDict):
    id: str
    target_kind: Literal["demo", "homepage"]
    recipe: str
    command: str
    viewport: ViewportRecord
    duration_seconds: float
    frame_count: int
    video: str | None
    gif: str | None
    poster: PosterRecord
    fallback_specimen_id: str | None
    accessibility_description: str


class MediaManifestV1(TypedDict):
    schema_version: Literal[1]
    recordings: list[MediaRecord]


def _repo_path(value: str, *, field: str, repo_root: Path) -> Path:
    """Resolve a declaration's repo-relative POSIX path without allowing escape."""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"{field} must be a repo-relative POSIX path: {value!r}")
    resolved = (repo_root / Path(*path.parts)).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{field} is outside the repository: {value!r}") from exc
    return resolved


def _public_file(value: str, *, field: str, repo_root: Path) -> tuple[Path, str]:
    """Map a public URL to its required file and VHS repo-relative output path."""
    if not value.startswith("/") or value.startswith("//"):
        raise ValueError(f"{field} must be a root-relative public URL: {value!r}")
    relative = value.removeprefix("/")
    if not relative or "?" in relative or "#" in relative:
        raise ValueError(f"{field} must name one published asset: {value!r}")
    file_path = _repo_path(f"web/public/{relative}", field=field, repo_root=repo_root)
    return file_path, f"web/public/{PurePosixPath(relative).as_posix()}"


def _single_setting(pattern: re.Pattern[str], tape: str, *, field: str) -> int:
    matches = pattern.findall(tape)
    if len(matches) != 1:
        raise ValueError(f"VHS recipe must declare exactly one {field}")
    return int(matches[0])


def _validate_identity(recipe: RecordingRecipe, *, demo_ids: set[str]) -> None:
    if recipe.target_kind == "demo":
        if recipe.id not in demo_ids:
            raise ValueError(f"unknown CatalogV1 demo id: {recipe.id!r}")
        return
    if recipe.target_kind == "homepage":
        if not _HOMEPAGE_ID.fullmatch(recipe.id):
            raise ValueError(f"homepage recipe id must be explicit homepage/<slug>: {recipe.id!r}")
        return
    raise ValueError(f"unknown recording target kind: {recipe.target_kind!r}")


def _validate_publication(
    publication: Publication,
    *,
    repo_root: Path,
    frame_rate: int,
) -> None:
    if publication.video is None and publication.gif is None:
        raise ValueError("published recording needs a video or GIF output")
    if publication.duration_seconds <= 0:
        raise ValueError("published recording duration_seconds must be positive")
    if publication.frame_count <= 0:
        raise ValueError("published recording frame_count must be positive")
    if not 0 <= publication.poster_frame < publication.frame_count:
        raise ValueError("poster_frame must select a zero-based encoded frame")
    encoded_duration = publication.frame_count / frame_rate
    if abs(publication.duration_seconds - encoded_duration) > 1 / frame_rate:
        raise ValueError(
            "duration_seconds must match frame_count at the declared frame_rate: "
            f"expected approximately {encoded_duration:g}"
        )

    for field, value, suffixes in (
        ("video", publication.video, (".webm", ".mp4")),
        ("gif", publication.gif, (".gif",)),
    ):
        if value is None:
            continue
        asset, _ = _public_file(value, field=field, repo_root=repo_root)
        if asset.suffix.lower() not in suffixes:
            raise ValueError(f"{field} has unsupported extension: {value!r}")
        if not asset.is_file():
            raise ValueError(f"published {field} asset does not exist: {value!r}")

    poster, _ = _public_file(publication.poster, field="poster", repo_root=repo_root)
    if poster.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"poster has unsupported extension: {publication.poster!r}")
    if not poster.is_file():
        raise ValueError(f"published poster asset does not exist: {publication.poster!r}")


def build_media_manifest(
    *,
    repo_root: Path,
    recipes: Sequence[RecordingRecipe],
    catalog: CatalogV1,
    panels: Mapping[str, object],
) -> MediaManifestV1:
    """Build MediaManifestV1 from explicit declarations.

    Drafts (``publication is None``) are validated but not exposed to Astro.
    Published records cannot exist until every referenced asset exists.
    """
    demo_ids = {record["id"] for record in catalog["demos"]}
    seen: set[str] = set()
    records: list[MediaRecord] = []

    for recipe in sorted(recipes, key=lambda item: item.id):
        if recipe.id in seen:
            raise ValueError(f"duplicate recording id: {recipe.id!r}")
        seen.add(recipe.id)
        _validate_identity(recipe, demo_ids=demo_ids)

        source = _repo_path(recipe.source, field="recipe source", repo_root=repo_root)
        if source.suffix != ".tape" or not source.is_file():
            raise ValueError(f"VHS recipe source does not exist: {recipe.source!r}")
        if recipe.command != f"uv run python -m tools.record_media {recipe.id}":
            raise ValueError(
                f"recording command must use the repo-owned media builder: {recipe.command!r}"
            )
        if recipe.viewport.width <= 0 or recipe.viewport.height <= 0:
            raise ValueError("recording viewport dimensions must be positive")
        if recipe.frame_rate <= 0:
            raise ValueError("recording frame_rate must be positive")
        if recipe.trim_start_frame < 0:
            raise ValueError("recording trim_start_frame must be zero or positive")
        if recipe.fallback_specimen_id is not None and recipe.fallback_specimen_id not in panels:
            raise ValueError(f"unknown PANELS fallback: {recipe.fallback_specimen_id!r}")
        if not recipe.accessibility_description.strip():
            raise ValueError("recording accessibility_description must not be empty")

        tape = source.read_text(encoding="utf-8")
        tape_width = _single_setting(_SET_WIDTH, tape, field="Set Width")
        tape_height = _single_setting(_SET_HEIGHT, tape, field="Set Height")
        tape_frame_rate = _single_setting(_SET_FRAMERATE, tape, field="Set Framerate")
        if (tape_width, tape_height) != (recipe.viewport.width, recipe.viewport.height):
            raise ValueError(
                "VHS viewport does not match recording metadata: "
                f"tape={(tape_width, tape_height)!r}, "
                f"declared={(recipe.viewport.width, recipe.viewport.height)!r}"
            )
        if tape_frame_rate != recipe.frame_rate:
            raise ValueError(
                "VHS framerate does not match recording metadata: "
                f"tape={tape_frame_rate!r}, declared={recipe.frame_rate!r}"
            )
        outputs = {value.strip() for value in _OUTPUT.findall(tape)}
        if outputs != {"frames/"}:
            raise ValueError(
                "VHS recipe must output frames/ for repo-owned ffmpeg encoding; "
                f"got {sorted(outputs)!r}"
            )

        publication = recipe.publication
        if publication is None:
            continue
        _validate_publication(
            publication,
            repo_root=repo_root,
            frame_rate=recipe.frame_rate,
        )
        records.append(
            {
                "id": recipe.id,
                "target_kind": recipe.target_kind,
                "recipe": recipe.source,
                "command": recipe.command,
                "viewport": {
                    "width": recipe.viewport.width,
                    "height": recipe.viewport.height,
                },
                "duration_seconds": publication.duration_seconds,
                "frame_count": publication.frame_count,
                "video": publication.video,
                "gif": publication.gif,
                "poster": {
                    "path": publication.poster,
                    "frame": publication.poster_frame,
                },
                "fallback_specimen_id": recipe.fallback_specimen_id,
                "accessibility_description": recipe.accessibility_description,
            }
        )

    return {"schema_version": 1, "recordings": records}


def media_manifest_json(
    *,
    repo_root: Path,
    recipes: Sequence[RecordingRecipe],
    catalog: CatalogV1,
    panels: Mapping[str, object],
) -> str:
    """Serialize MediaManifestV1 deterministically for the Astro build."""
    return (
        json.dumps(
            build_media_manifest(
                repo_root=repo_root,
                recipes=recipes,
                catalog=catalog,
                panels=panels,
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
