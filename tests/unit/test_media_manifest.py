from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tools.media_manifest import build_media_manifest, media_manifest_json
from tools.outputgen import MEDIA_MANIFEST_PATH, _media_manifest_json
from tools.record_media import frame_input_args, poster_command, validate_frame_inventory
from tools.recording_recipes import Publication, RecordingRecipe, Viewport
from tools.web_catalog import CatalogV1

REPO_ROOT = Path(__file__).resolve().parents[2]


def _catalog() -> CatalogV1:
    return {
        "schema_version": 1,
        "demo_tiers": [{"id": "patterns", "order": 0}],
        "demos": [
            {
                "id": "patterns/responsive",
                "tier": "patterns",
                "name": "responsive",
                "slug": "responsive",
                "title": "Responsive",
                "summary": "Responsive layout",
                "source": "demos/patterns/responsive.py",
                "command": "painted demos responsive",
                "checkout_command": "uv run demos/patterns/responsive.py",
                "invocations": [],
                "has_main": True,
            }
        ],
        "specimens": [],
    }


def _write_recipe(root: Path, body: str) -> None:
    path = root / "recordings/responsive.tape"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")


def _recipe(*, publication: Publication | None) -> RecordingRecipe:
    return RecordingRecipe(
        id="patterns/responsive",
        target_kind="demo",
        source="recordings/responsive.tape",
        command="uv run python -m tools.record_media patterns/responsive",
        viewport=Viewport(width=800, height=450),
        frame_rate=30,
        trim_start_frame=0,
        fallback_specimen_id="monitor_live",
        accessibility_description=(
            "The same status data reflows from two columns to one as the terminal narrows."
        ),
        publication=publication,
    )


def _publication() -> Publication:
    return Publication(
        video="/media/responsive.webm",
        gif="/media/responsive.gif",
        poster="/media/responsive-poster.png",
        poster_frame=24,
        duration_seconds=6.0,
        frame_count=180,
    )


def _published_tree(root: Path) -> None:
    _write_recipe(
        root,
        "\n".join(
            (
                "Output frames/",
                "Set Width 800",
                "Set Height 450",
                "Set Framerate 30",
                "",
            )
        ),
    )
    media = root / "web/public/media"
    media.mkdir(parents=True)
    for name in ("responsive.webm", "responsive.gif", "responsive-poster.png"):
        (media / name).touch()


def test_published_recipe_emits_complete_deterministic_record(tmp_path: Path) -> None:
    _published_tree(tmp_path)
    recipe = _recipe(publication=_publication())

    manifest = build_media_manifest(
        repo_root=tmp_path,
        recipes=[recipe],
        catalog=_catalog(),
        panels={"monitor_live": object()},
    )

    assert manifest == {
        "schema_version": 1,
        "recordings": [
            {
                "id": "patterns/responsive",
                "target_kind": "demo",
                "recipe": "recordings/responsive.tape",
                "command": "uv run python -m tools.record_media patterns/responsive",
                "viewport": {"width": 800, "height": 450},
                "duration_seconds": 6.0,
                "frame_count": 180,
                "video": "/media/responsive.webm",
                "gif": "/media/responsive.gif",
                "poster": {"path": "/media/responsive-poster.png", "frame": 24},
                "fallback_specimen_id": "monitor_live",
                "accessibility_description": recipe.accessibility_description,
            }
        ],
    }
    first = media_manifest_json(
        repo_root=tmp_path,
        recipes=[recipe],
        catalog=_catalog(),
        panels={"monitor_live": object()},
    )
    second = media_manifest_json(
        repo_root=tmp_path,
        recipes=[recipe],
        catalog=_catalog(),
        panels={"monitor_live": object()},
    )
    assert first == second
    assert json.loads(first) == manifest
    assert first.endswith("\n")


def test_draft_is_validated_but_not_published(tmp_path: Path) -> None:
    _write_recipe(
        tmp_path,
        "Output frames/\nSet Width 800\nSet Height 450\nSet Framerate 30\n",
    )

    manifest = build_media_manifest(
        repo_root=tmp_path,
        recipes=[_recipe(publication=None)],
        catalog=_catalog(),
        panels={"monitor_live": object()},
    )

    assert manifest == {"schema_version": 1, "recordings": []}


def test_homepage_recipe_uses_explicit_identity_without_catalog_inference(tmp_path: Path) -> None:
    _write_recipe(
        tmp_path,
        "Output frames/\nSet Width 800\nSet Height 450\nSet Framerate 30\n",
    )
    recipe = replace(
        _recipe(publication=None),
        id="homepage/continuum",
        target_kind="homepage",
        command="uv run python -m tools.record_media homepage/continuum",
    )

    manifest = build_media_manifest(
        repo_root=tmp_path,
        recipes=[recipe],
        catalog=_catalog(),
        panels={"monitor_live": object()},
    )

    assert manifest["recordings"] == []


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"id": "responsive"}, "unknown CatalogV1 demo id"),
        ({"fallback_specimen_id": "responsive"}, "unknown PANELS fallback"),
        ({"command": "vhs recordings/responsive.tape"}, "repo-owned media builder"),
        ({"viewport": Viewport(801, 450)}, "VHS viewport does not match"),
        ({"frame_rate": 60}, "VHS framerate does not match"),
        ({"trim_start_frame": -1}, "trim_start_frame must be zero or positive"),
    ],
)
def test_recipe_relationships_and_vhs_contract_are_explicit(
    tmp_path: Path, change: dict[str, object], match: str
) -> None:
    _write_recipe(
        tmp_path,
        "Output frames/\nSet Width 800\nSet Height 450\nSet Framerate 30\n",
    )
    recipe = replace(_recipe(publication=None), **change)

    with pytest.raises(ValueError, match=match):
        build_media_manifest(
            repo_root=tmp_path,
            recipes=[recipe],
            catalog=_catalog(),
            panels={"monitor_live": object()},
        )


def test_published_assets_must_exist_and_match_vhs_outputs(tmp_path: Path) -> None:
    _published_tree(tmp_path)
    recipe = _recipe(publication=_publication())
    (tmp_path / "web/public/media/responsive.webm").unlink()

    with pytest.raises(ValueError, match="published video asset does not exist"):
        build_media_manifest(
            repo_root=tmp_path,
            recipes=[recipe],
            catalog=_catalog(),
            panels={"monitor_live": object()},
        )


def test_vhs_must_emit_frames_instead_of_direct_video(tmp_path: Path) -> None:
    _write_recipe(
        tmp_path,
        (
            "Output web/public/media/responsive.webm\n"
            "Set Width 800\nSet Height 450\nSet Framerate 30\n"
        ),
    )

    with pytest.raises(ValueError, match="must output frames/"):
        build_media_manifest(
            repo_root=tmp_path,
            recipes=[_recipe(publication=None)],
            catalog=_catalog(),
            panels={"monitor_live": object()},
        )


def test_fallback_specimen_is_optional_and_emits_null(tmp_path: Path) -> None:
    _published_tree(tmp_path)
    recipe = replace(_recipe(publication=_publication()), fallback_specimen_id=None)

    manifest = build_media_manifest(
        repo_root=tmp_path,
        recipes=[recipe],
        catalog=_catalog(),
        panels={},
    )

    assert manifest["recordings"][0]["fallback_specimen_id"] is None


def test_poster_command_selects_declared_encoded_frame() -> None:
    command = poster_command(
        source=Path("recording.webm"),
        destination=Path("poster.png"),
        frame=24,
    )

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        "recording.webm",
        "-vf",
        "select=eq(n\\,24)",
        "-frames:v",
        "1",
        "poster.png",
    ]


def test_ffmpeg_starts_at_declared_raw_frame_and_caps_post_trim_count() -> None:
    args = frame_input_args(
        frame_rate=30,
        frames=Path("frames"),
        trim_start_frame=20,
        frame_count=180,
    )

    assert args == [
        "-framerate",
        "30",
        "-start_number",
        "20",
        "-i",
        "frames/frame-text-%05d.png",
        "-frames:v",
        "180",
    ]


def test_raw_inventory_includes_trim_before_published_frame_count(tmp_path: Path) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    for number in range(199):
        (frames / f"frame-text-{number:05d}.png").touch()

    with pytest.raises(ValueError, match=r"trim 20 \+ published 180 needs 200"):
        validate_frame_inventory(frames, trim_start_frame=20, frame_count=180)

    (frames / "frame-text-00199.png").touch()
    validate_frame_inventory(frames, trim_start_frame=20, frame_count=180)


def test_poster_frame_must_select_an_encoded_frame(tmp_path: Path) -> None:
    _published_tree(tmp_path)
    publication = replace(_publication(), poster_frame=180)

    with pytest.raises(ValueError, match="poster_frame"):
        build_media_manifest(
            repo_root=tmp_path,
            recipes=[_recipe(publication=publication)],
            catalog=_catalog(),
            panels={"monitor_live": object()},
        )


def test_duration_and_frame_count_must_match_recipe_rate(tmp_path: Path) -> None:
    _published_tree(tmp_path)
    publication = replace(_publication(), duration_seconds=5.0)

    with pytest.raises(ValueError, match="duration_seconds must match frame_count"):
        build_media_manifest(
            repo_root=tmp_path,
            recipes=[_recipe(publication=publication)],
            catalog=_catalog(),
            panels={"monitor_live": object()},
        )


def test_recording_ids_are_unique_across_drafts_and_publications(tmp_path: Path) -> None:
    _write_recipe(
        tmp_path,
        "Output frames/\nSet Width 800\nSet Height 450\nSet Framerate 30\n",
    )
    recipe = _recipe(publication=None)

    with pytest.raises(ValueError, match="duplicate recording id"):
        build_media_manifest(
            repo_root=tmp_path,
            recipes=[recipe, recipe],
            catalog=_catalog(),
            panels={"monitor_live": object()},
        )


def test_committed_media_manifest_matches_generator() -> None:
    assert (REPO_ROOT / MEDIA_MANIFEST_PATH).read_text(encoding="utf-8") == _media_manifest_json(
        repo_root=REPO_ROOT
    )
