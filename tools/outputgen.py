from __future__ import annotations

import argparse
import html
import json
import re
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from painted import PAINTED_PALETTE, Block, Palette, Zoom, render_html, use_palette

if __package__ is None:  # invoked as a script: python tools/outputgen.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.capture import capture_demo, import_module_by_path


@dataclass(frozen=True, slots=True)
class OutputSpec:
    name: str
    demo_path: str
    function_or_zoom: str | Zoom
    format: Literal["html"]
    width: int
    data_attr: str | None = None
    # Ambient palette applied (in-process) during capture. None → DEFAULT.
    palette: Palette | None = None
    # Light format axis: "block" renders the demo's Block via render_html;
    # "json" serializes its data_attr — the format-dial stop on the site.
    render_as: Literal["block", "json"] = "block"


MANIFEST: dict[str, OutputSpec] = {
    "cell_demo": OutputSpec(
        name="cell_demo",
        demo_path="demos/primitives/cell.py",
        function_or_zoom="<module>",
        format="html",
        width=80,
        data_attr="output",
    ),
    "fidelity_minimal": OutputSpec(
        name="fidelity_minimal",
        demo_path="demos/patterns/fidelity.py",
        function_or_zoom=Zoom.MINIMAL,
        format="html",
        width=80,
        data_attr="SAMPLE_DISK",
    ),
    "fidelity_detailed": OutputSpec(
        name="fidelity_detailed",
        demo_path="demos/patterns/fidelity.py",
        function_or_zoom=Zoom.DETAILED,
        format="html",
        width=80,
        data_attr="SAMPLE_DISK",
    ),
}


# --- Site panels --------------------------------------------------------------
# A SEPARATE set from MANIFEST: these render to committed HTML fragments for the
# Astro site (via --emit-panels), NOT into doc sentinels. Keeping them outside
# the gated MANIFEST/docs `--check` lets the site pull real painted output
# without coupling the site to the docs-injection pipeline.
#
# The "no cliffs" walkthrough: ONE monitor dataset walked across the continuum,
# plus a vivid (PAINTED_PALETTE) variant of the default view for the live toggle.

PANELS: dict[str, OutputSpec] = {
    "monitor_q": OutputSpec(
        name="monitor_q",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.MINIMAL,
        format="html",
        width=64,
        data_attr="SAMPLE",
    ),
    "monitor_default": OutputSpec(
        name="monitor_default",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.SUMMARY,
        format="html",
        width=48,
        data_attr="SAMPLE",
    ),
    "monitor_default_vivid": OutputSpec(
        name="monitor_default_vivid",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.SUMMARY,
        format="html",
        width=48,
        data_attr="SAMPLE",
        palette=PAINTED_PALETTE,
    ),
    "monitor_vv": OutputSpec(
        name="monitor_vv",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.DETAILED,
        format="html",
        width=56,
        data_attr="SAMPLE",
    ),
    "monitor_json": OutputSpec(
        name="monitor_json",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom="<json>",
        format="html",
        width=48,
        data_attr="SAMPLE",
        render_as="json",
    ),
}


_BEGIN_RE = re.compile(r'<!--\s*outputgen:begin\s+name="(?P<name>[^"]+)"\s*-->')
_END_RE = re.compile(r"<!--\s*outputgen:end\s*-->")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8", newline="\n")


def _render_text_as_html(text: str) -> str:
    return f'<pre class="painted-output">{html.escape(text)}</pre>\n'


def _generate_output(*, repo_root: Path, spec: OutputSpec) -> str:
    if spec.render_as == "json":
        if spec.data_attr is None:
            raise ValueError(f"panel {spec.name!r} render_as='json' requires data_attr")
        mod = import_module_by_path(repo_root / spec.demo_path)
        data = getattr(mod, spec.data_attr)
        return _render_text_as_html(json.dumps(data, indent=2))

    palette_cm = use_palette(spec.palette) if spec.palette is not None else nullcontext()
    with palette_cm:
        result = capture_demo(
            repo_root / spec.demo_path,
            spec.function_or_zoom,
            width=spec.width,
            data_attr=spec.data_attr,
        )

    if isinstance(result, Block):
        return render_html(result)
    return _render_text_as_html(result)


def find_outputgen_names(html_doc: str) -> list[str]:
    return [m.group("name").strip() for m in _BEGIN_RE.finditer(html_doc)]


def update_doc(doc: str, *, repo_root: Path) -> tuple[str, list[str]]:
    out: list[str] = []
    updated: list[str] = []

    lines = doc.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _BEGIN_RE.search(line)
        if not m:
            out.append(line)
            i += 1
            continue

        name = m.group("name").strip()
        if name not in MANIFEST:
            raise KeyError(f"Missing manifest entry for output name {name!r}")

        out.append(line)
        i += 1

        while i < len(lines) and not _END_RE.search(lines[i]):
            i += 1

        if i >= len(lines):
            raise ValueError(f"Unclosed outputgen block for name {name!r}")

        out.append(_generate_output(repo_root=repo_root, spec=MANIFEST[name]))
        out.append(lines[i])
        i += 1
        updated.append(name)

    return "".join(out), updated


def check_doc(doc: str, *, repo_root: Path) -> list[str]:
    updated, touched = update_doc(doc, repo_root=repo_root)
    if updated == doc:
        return []
    return touched


def _iter_doc_files(repo_root: Path, roots: list[str]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        p = (repo_root / root).resolve()
        if p.is_file() and p.suffix.lower() == ".md":
            out.append(p)
            continue
        if p.is_dir():
            out.extend(sorted(p.rglob("*.md")))
    return out


def emit_panels(*, repo_root: Path, out_dir: Path) -> list[Path]:
    """Render every PANELS entry to ``out_dir/<name>.html`` as a standalone fragment.

    These are the site's real-output panels — committed artifacts the Astro build
    imports. Separate from the doc-sentinel injection path (and its `--check`).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, spec in PANELS.items():
        path = out_dir / f"{name}.html"
        _write_text(path, _generate_output(repo_root=repo_root, spec=spec))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="outputgen", description="Inject captured demo output into docs."
    )
    ap.add_argument("--repo-root", type=Path, default=_repo_root())
    ap.add_argument("--roots", nargs="+", default=["docs/guides"])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Verify output blocks are up to date.")
    mode.add_argument("--update", action="store_true", help="Regenerate and inject output blocks.")
    mode.add_argument(
        "--emit-panels",
        type=Path,
        metavar="DIR",
        help="Render the PANELS set to standalone HTML fragments in DIR (for the site).",
    )
    args = ap.parse_args(argv)

    repo_root: Path = args.repo_root

    if args.emit_panels is not None:
        written = emit_panels(repo_root=repo_root, out_dir=args.emit_panels)
        print("Wrote panels:")
        for p in written:
            shown = p.relative_to(repo_root) if p.is_relative_to(repo_root) else p
            print(f"  - {shown}")
        return 0

    files = _iter_doc_files(repo_root, args.roots)
    if not files:
        print("No doc files found under roots.", file=sys.stderr)
        return 2

    mismatched: list[tuple[Path, list[str]]] = []
    changed: list[Path] = []
    seen_names: set[str] = set()

    for path in files:
        src = _read_text(path)
        names = find_outputgen_names(src)
        if not names:
            continue
        seen_names.update(names)

        if args.check:
            bad = check_doc(src, repo_root=repo_root)
            if bad:
                mismatched.append((path, bad))
            continue

        updated, touched = update_doc(src, repo_root=repo_root)
        if touched and updated != src:
            _write_text(path, updated)
            changed.append(path)

    missing = sorted(set(MANIFEST) - seen_names)
    if missing:
        print("Missing outputgen sentinels for:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    if args.check:
        if mismatched:
            print("outputgen blocks out of date:", file=sys.stderr)
            for path, names in mismatched:
                rel = path.relative_to(repo_root)
                print(f"  - {rel}: {', '.join(names)}", file=sys.stderr)
            return 1
        return 0

    if changed:
        print("Updated:")
        for path in changed:
            print(f"  - {path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
