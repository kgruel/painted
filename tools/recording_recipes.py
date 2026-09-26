"""Curated VHS recording recipes for website media.

This module is the declaration boundary, not a second demo catalog. Demo targets
use the tier-qualified identity already published by CatalogV1; homepage targets
use an explicit ``homepage/<slug>`` identity. Relationships are always declared.

The initial curated set contains the homepage continuum and focus-form demo.
Draft recipes can be added before assets exist; ``tools.media_manifest`` validates
those drafts but publishes only recipes with a ``publication`` declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TargetKind = Literal["demo", "homepage"]


@dataclass(frozen=True, slots=True)
class Viewport:
    """VHS pixel viewport, consumed by ``Set Width`` and ``Set Height``."""

    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Publication:
    """Published outputs and deterministic poster selection for one recording.

    Paths are public URLs rooted at ``web/public``. ``poster_frame`` is zero-based
    and identifies the selected frame in the encoded recording.
    """

    video: str | None
    gif: str | None
    poster: str
    poster_frame: int
    duration_seconds: float
    frame_count: int


@dataclass(frozen=True, slots=True)
class RecordingRecipe:
    """One explicitly related VHS-to-frames recipe and its website fallback."""

    id: str
    target_kind: TargetKind
    source: str
    command: str
    viewport: Viewport
    frame_rate: int
    trim_start_frame: int
    fallback_specimen_id: str | None
    accessibility_description: str
    publication: Publication | None = None


RECORDING_RECIPES: tuple[RecordingRecipe, ...] = (
    RecordingRecipe(
        id="homepage/continuum",
        target_kind="homepage",
        source="demos/recordings/homepage-continuum.tape",
        command="uv run python -m tools.record_media homepage/continuum",
        viewport=Viewport(width=760, height=520),
        frame_rate=60,
        trim_start_frame=20,
        fallback_specimen_id=None,
        accessibility_description=(
            "Health checks progress from pending to four healthy, one degraded, and one down; "
            "the expanded view names each service, latency, and result."
        ),
        publication=Publication(
            video="/media/homepage-continuum.mp4",
            gif=None,
            poster="/media/homepage-continuum-poster.png",
            poster_frame=420,
            duration_seconds=7.866667,
            frame_count=472,
        ),
    ),
    RecordingRecipe(
        id="apps/focus_form",
        target_kind="demo",
        source="demos/recordings/apps-focus-form.tape",
        command="uv run python -m tools.record_media apps/focus_form",
        viewport=Viewport(width=820, height=500),
        frame_rate=60,
        trim_start_frame=20,
        fallback_specimen_id=None,
        accessibility_description=(
            "A keyboard-operated form moves focus through hostname, port, username, and submit; "
            "entered values appear in the submitted confirmation."
        ),
        publication=Publication(
            video="/media/apps-focus-form.mp4",
            gif=None,
            poster="/media/apps-focus-form-poster.png",
            poster_frame=230,
            duration_seconds=4.633333,
            frame_count=278,
        ),
    ),
)
