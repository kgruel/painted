"""Repo-owned VHS frames -> ffmpeg media builder.

The builder deliberately keeps VHS away from final video encoding: VHS writes
``frames/`` at the declared rate, then ffmpeg encodes those text frames. This
preserves cadence that VHS's direct MP4/WebM output can otherwise cap at 25fps.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.media_manifest import _public_file, _repo_path
from tools.recording_recipes import RECORDING_RECIPES, Publication, RecordingRecipe


def poster_command(*, source: Path, destination: Path, frame: int) -> list[str]:
    """Return ffmpeg argv selecting one exact zero-based encoded frame."""
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"select=eq(n\\,{frame})",
        "-frames:v",
        "1",
        str(destination),
    ]


def frame_input_args(
    *,
    frame_rate: int,
    frames: Path,
    trim_start_frame: int,
    frame_count: int,
) -> list[str]:
    """Return ffmpeg input argv for the declared post-setup frame window."""
    return [
        "-framerate",
        str(frame_rate),
        "-start_number",
        str(trim_start_frame),
        "-i",
        str(frames / "frame-text-%05d.png"),
        "-frames:v",
        str(frame_count),
    ]


def validate_frame_inventory(frames: Path, *, trim_start_frame: int, frame_count: int) -> None:
    """Require enough contiguous raw text frames for the encoded frame window."""
    text_frames = sorted(frames.glob("frame-text-*.png"))
    required_raw_count = trim_start_frame + frame_count
    if len(text_frames) < required_raw_count:
        raise ValueError(
            f"VHS produced {len(text_frames)} raw text frames; "
            f"trim {trim_start_frame} + published {frame_count} needs {required_raw_count}"
        )
    for number in range(trim_start_frame, required_raw_count):
        frame = frames / f"frame-text-{number:05d}.png"
        if not frame.is_file():
            raise ValueError(f"VHS frame window is not contiguous: missing {frame.name}")


def _video_command(
    *,
    frame_rate: int,
    frames: Path,
    trim_start_frame: int,
    frame_count: int,
    destination: Path,
    suffix: str,
) -> list[str]:
    common = (
        ["ffmpeg", "-y"]
        + frame_input_args(
            frame_rate=frame_rate,
            frames=frames,
            trim_start_frame=trim_start_frame,
            frame_count=frame_count,
        )
        + [
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        ]
    )
    if suffix == ".mp4":
        return common + [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    return common + [
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "32",
        "-b:v",
        "0",
        str(destination),
    ]


def _gif_command(
    *,
    frame_rate: int,
    frames: Path,
    trim_start_frame: int,
    frame_count: int,
    destination: Path,
) -> list[str]:
    return (
        ["ffmpeg", "-y"]
        + frame_input_args(
            frame_rate=frame_rate,
            frames=frames,
            trim_start_frame=trim_start_frame,
            frame_count=frame_count,
        )
        + [
            "-vf",
            (f"fps={frame_rate},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"),
            "-loop",
            "0",
            str(destination),
        ]
    )


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(argv, cwd=cwd, env=env, check=True)


def _publication_paths(
    publication: Publication, *, repo_root: Path
) -> tuple[Path | None, Path | None, Path]:
    video = (
        _public_file(publication.video, field="video", repo_root=repo_root)[0]
        if publication.video is not None
        else None
    )
    gif = (
        _public_file(publication.gif, field="gif", repo_root=repo_root)[0]
        if publication.gif is not None
        else None
    )
    poster = _public_file(publication.poster, field="poster", repo_root=repo_root)[0]
    return video, gif, poster


def build_recording(recipe: RecordingRecipe, *, repo_root: Path) -> None:
    """Build one declared publication through VHS frames and ffmpeg."""
    publication = recipe.publication
    if publication is None:
        raise ValueError(f"recording {recipe.id!r} is still a draft")
    source = _repo_path(recipe.source, field="recipe source", repo_root=repo_root)
    video_path, gif_path, poster_path = _publication_paths(publication, repo_root=repo_root)

    with tempfile.TemporaryDirectory(prefix="painted-recording-") as temp:
        work = Path(temp)
        env = os.environ.copy()
        env["PAINTED_RECORDING_REPO"] = str(repo_root.resolve())
        _run(["vhs", str(source)], cwd=work, env=env)

        frames = work / "frames"
        validate_frame_inventory(
            frames,
            trim_start_frame=recipe.trim_start_frame,
            frame_count=publication.frame_count,
        )

        built_video: Path | None = None
        built_gif: Path | None = None
        if video_path is not None:
            built_video = work / video_path.name
            _run(
                _video_command(
                    frame_rate=recipe.frame_rate,
                    frames=frames,
                    trim_start_frame=recipe.trim_start_frame,
                    frame_count=publication.frame_count,
                    destination=built_video,
                    suffix=video_path.suffix.lower(),
                ),
                cwd=work,
            )
        if gif_path is not None:
            built_gif = work / gif_path.name
            _run(
                _gif_command(
                    frame_rate=recipe.frame_rate,
                    frames=frames,
                    trim_start_frame=recipe.trim_start_frame,
                    frame_count=publication.frame_count,
                    destination=built_gif,
                ),
                cwd=work,
            )

        poster_source = built_video or built_gif
        if poster_source is None:
            raise ValueError(f"recording {recipe.id!r} has no encoded poster source")
        built_poster = work / poster_path.name
        _run(
            poster_command(
                source=poster_source,
                destination=built_poster,
                frame=publication.poster_frame,
            ),
            cwd=work,
        )

        for built, destination in (
            (built_video, video_path),
            (built_gif, gif_path),
            (built_poster, poster_path),
        ):
            if built is None or destination is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built, destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build one curated Painted recording.")
    parser.add_argument("recording_id")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    matches = [recipe for recipe in RECORDING_RECIPES if recipe.id == args.recording_id]
    if len(matches) != 1:
        parser.error(f"unknown or duplicate recording id: {args.recording_id!r}")
    build_recording(matches[0], repo_root=args.repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
