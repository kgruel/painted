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

from painted import (
    PAINTED_PALETTE,
    Block,
    Palette,
    RefScheme,
    Zoom,
    render_html,
    use_palette,
    use_refs,
)

if __package__ is None:  # invoked as a script: python tools/outputgen.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from painted._doc_pages import DOCS as _DOC_PAGES_CATALOG

from tools.capture import capture_demo, import_module_by_path
from tools.disclosure_specimens import DISCLOSURE as _DISCLOSURE_CATALOG
from tools.doc_publish import to_html
from tools.landing_specimens import LANDING as _LANDING_CATALOG
from tools.reference_specimens import CATALOG as _REFERENCE_CATALOG


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
    # Ambient ref schemes, scoped around capture AND render_html — resolution
    # happens at render time, and a demo module must not set ambient state at
    # import (a module-scope use_refs would leak into every later panel).
    refs: tuple[RefScheme, ...] | None = None
    # Light format axis: "block" renders the demo's Block via render_html; "json"
    # serializes its data_attr; "plain" emits the Block's chars with no color (the
    # piped, no-ANSI stop). All three are format-dial stops on the site.
    render_as: Literal["block", "json", "plain"] = "block"


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
# The "no cliffs" walkthrough: ONE monitor dataset walked across the continuum.
# The site is always truecolor, so panels render under PAINTED_PALETTE by default
# (legible, on-brand, token-matched); `monitor_default_honest` is the DEFAULT
# (normal-ANSI) variant the walkthrough offers as a toggle — "what a 16-color
# terminal downsamples to".


def _module_panel(name: str, demo_path: str) -> OutputSpec:
    """A PANELS spec capturing one module-level Block constant via the "<module>" shape.

    Used for the registry-backed panel sets (the /reference catalog and the
    landing front door): each captures the matching upper-cased constant from its
    specimens module — the Block carries its own width and baked palette, so
    `width` here is inert (kept only for the dataclass).
    """
    return OutputSpec(
        name=name,
        demo_path=demo_path,
        function_or_zoom="<module>",
        format="html",
        width=64,
        data_attr=name.upper(),
    )


PANELS: dict[str, OutputSpec] = {
    # Stage 01's zero-config truth: paint(SAMPLE) transcribes the vitals dict to
    # its key/value pairs — NOT severity bars (those are monitor.py's render / a
    # lens). The walkthrough reveals the bars from here as the opt-in claim.
    "monitor_transcribe": OutputSpec(
        name="monitor_transcribe",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom="<paint>",
        format="html",
        width=48,
        data_attr="SAMPLE",
        palette=PAINTED_PALETTE,
    ),
    "monitor_q": OutputSpec(
        name="monitor_q",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.MINIMAL,
        format="html",
        width=64,
        data_attr="SAMPLE",
        palette=PAINTED_PALETTE,
    ),
    "monitor_default": OutputSpec(
        name="monitor_default",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.SUMMARY,
        format="html",
        width=48,
        data_attr="SAMPLE",
        palette=PAINTED_PALETTE,
    ),
    "monitor_default_honest": OutputSpec(
        name="monitor_default_honest",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.SUMMARY,
        format="html",
        width=48,
        data_attr="SAMPLE",
        # No palette → DEFAULT (normal ANSI): the "downsample preview" toggle.
    ),
    "monitor_vv": OutputSpec(
        name="monitor_vv",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.DETAILED,
        format="html",
        width=56,
        data_attr="SAMPLE",
        palette=PAINTED_PALETTE,
    ),
    # --live: a later tick (SAMPLE_LIVE) so the frame visibly differs from the static paint() panel.
    "monitor_live": OutputSpec(
        name="monitor_live",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.SUMMARY,
        format="html",
        width=48,
        data_attr="SAMPLE_LIVE",
        palette=PAINTED_PALETTE,
    ),
    # the format dial's plain stop: piped output, no ANSI/color.
    "monitor_plain": OutputSpec(
        name="monitor_plain",
        demo_path="demos/patterns/monitor.py",
        function_or_zoom=Zoom.SUMMARY,
        format="html",
        width=48,
        data_attr="SAMPLE",
        render_as="plain",
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
    # Refs: the denotation channel as HTML anchors. The demo declares a `fact`
    # RefScheme at module scope (setter form), so render_html picks it up
    # ambiently and wraps the refed cells in <a href> — the site's live proof
    # that a declared scheme turns denotation into links (REFS_DESIGN §6).
    "refs_anchors": OutputSpec(
        name="refs_anchors",
        demo_path="demos/primitives/refs.py",
        function_or_zoom="<module>",
        format="html",
        width=64,
        data_attr="OUTPUT",
        refs=(RefScheme("fact", lambda value: f"https://loops.dev/f/{value}"),),
    ),
    # --- Reference catalog ----------------------------------------------------
    # One real specimen per Design preview card. These are uniform (each captures a
    # module-level Block from tools/reference_specimens.py via the "<module>" shape),
    # so they dissolve into the CATALOG registry rather than 21 near-identical
    # literals — see _module_panel. Names mirror the Design card ids 1:1.
    **{name: _module_panel(name, "tools/reference_specimens.py") for name in _REFERENCE_CATALOG},
    # --- Landing front door ---------------------------------------------------
    # The hero wordmark + three routing cards for index.astro. Same <module> shape
    # as the reference catalog, sourced from tools/landing_specimens.py.
    **{name: _module_panel(name, "tools/landing_specimens.py") for name in _LANDING_CATALOG},
    # --- Disclosure ladder (walkthrough branch: /walkthrough/fidelity) ---------
    # The fidelity exemplar rendered under explicitly built Fidelity specs —
    # rungs 1–4 of the consumption ladder, sourced from tools/disclosure_specimens.py.
    **{name: _module_panel(name, "tools/disclosure_specimens.py") for name in _DISCLOSURE_CATALOG},
}


_BEGIN_RE = re.compile(r'<!--\s*outputgen:begin\s+name="(?P<name>[^"]+)"\s*-->')
_END_RE = re.compile(r"<!--\s*outputgen:end\s*-->")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# The site's committed panel fragments live in-repo (since the docs-site fold).
# `--emit-panels` writes here by default; `--check` verifies these match a fresh
# render, so a renderer change that forgets `./dev panels` fails the gate.
PANELS_DIR = Path("web/src/generated/panels")

# Committed doc-IR pages (tools/doc_publish.to_html over painted._doc_pages.DOCS):
# the SEMANTIC sink — chrome as <section>/<p>/<dl>, Figure islands via render_html.
# Same regen/check lifecycle as PANELS; the registry IS the `painted docs` registry,
# so the site cannot list a page the terminal doesn't have (or vice versa).
DOC_PAGES_DIR = Path("web/src/generated/docs")


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

    if spec.render_as == "plain":
        result = capture_demo(
            repo_root / spec.demo_path,
            spec.function_or_zoom,
            width=spec.width,
            data_attr=spec.data_attr,
        )
        if isinstance(result, Block):
            text = "\n".join("".join(c.char for c in result.row(y)) for y in range(result.height))
        else:
            text = result
        return _render_text_as_html(text)

    if spec.function_or_zoom == "<paint>":
        # paint()'s zero-config default: transcription of the *declared* shape.
        # Renders the real dataset through the same transcribe() paint() calls,
        # so the walkthrough's "zero config" panel is genuine paint output — a
        # dict as its key/value pairs, NOT the severity bars (those are the app's
        # render / an opt-in lens). transcribe is private (paint's default; you
        # never name it), so reach it directly here as tools already do.
        if spec.data_attr is None:
            raise ValueError(f"panel {spec.name!r} '<paint>' shape requires data_attr")
        from painted.views.lens.shape import transcribe

        mod = import_module_by_path(repo_root / spec.demo_path)
        data = getattr(mod, spec.data_attr)
        palette_cm = use_palette(spec.palette) if spec.palette is not None else nullcontext()
        with palette_cm:
            block = transcribe(data, int(Zoom.DETAILED), spec.width)
            return render_html(block)

    palette_cm = use_palette(spec.palette) if spec.palette is not None else nullcontext()
    refs_cm = use_refs(*spec.refs) if spec.refs is not None else nullcontext()
    with refs_cm:
        with palette_cm:
            result = capture_demo(
                repo_root / spec.demo_path,
                spec.function_or_zoom,
                width=spec.width,
                data_attr=spec.data_attr,
            )

        # render_html stays inside the refs scope: anchors resolve at render
        # time, not capture time.
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
    # Dedup by resolved inode so a symlinked CLAUDE.md -> README.md is visited
    # once (as the real file), not twice.
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        p = (repo_root / root).resolve()
        if p.is_file() and p.suffix.lower() == ".md":
            if p not in seen:
                seen.add(p)
                out.append(p)
            continue
        if p.is_dir():
            for md in sorted(p.rglob("*.md")):
                real = md.resolve()
                if real not in seen:
                    seen.add(real)
                    out.append(real)
    return out


def emit_panels(*, repo_root: Path, out_dir: Path | None = None) -> list[Path]:
    """Render every PANELS entry to ``out_dir/<name>.html`` as a standalone fragment.

    These are the site's real-output panels — committed artifacts the Astro build
    imports. ``out_dir`` defaults to the in-repo ``web/src/generated/panels``.
    """
    out_dir = out_dir or (repo_root / PANELS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, spec in PANELS.items():
        path = out_dir / f"{name}.html"
        _write_text(path, _generate_output(repo_root=repo_root, spec=spec))
        written.append(path)
    return written


def emit_doc_pages(*, repo_root: Path, out_dir: Path | None = None) -> list[Path]:
    """Publish every authored doc page to ``out_dir/<name>.html`` via ``to_html``.

    One fragment per ``painted._doc_pages.DOCS`` entry, at published (full)
    fidelity. ``out_dir`` defaults to the in-repo ``web/src/generated/docs``.
    """
    out_dir = out_dir or (repo_root / DOC_PAGES_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, entry in _DOC_PAGES_CATALOG.items():
        path = out_dir / f"{name}.html"
        _write_text(path, to_html(entry.build()))
        written.append(path)
    index = out_dir / "index.json"
    _write_text(index, _doc_pages_index())
    written.append(index)
    return written


def _doc_pages_index() -> str:
    """The page registry as JSON — the site lists pages from the same DOCS
    dict the terminal dispatches on, so neither side can list a page the
    other doesn't have."""
    entries = [
        {"name": name, "description": entry.description}
        for name, entry in _DOC_PAGES_CATALOG.items()
    ]
    return json.dumps(entries, indent=2) + "\n"


def check_doc_pages(*, repo_root: Path) -> list[str]:
    """Doc-page names whose committed fragment is missing or has drifted."""
    out_dir = repo_root / DOC_PAGES_DIR
    stale: list[str] = []
    for name, entry in _DOC_PAGES_CATALOG.items():
        want = to_html(entry.build())
        path = out_dir / f"{name}.html"
        if not path.exists() or _read_text(path) != want:
            stale.append(name)
    index = out_dir / "index.json"
    if not index.exists() or _read_text(index) != _doc_pages_index():
        stale.append("index.json")
    return stale


def check_panels(*, repo_root: Path) -> list[str]:
    """PANELS names whose committed fragment is missing or has drifted from a fresh render.

    The external counterpart to the doc-sentinel ``check_doc``: it lets the same
    ``--check`` gate one renderer change against both the internal docs and the
    external site, so neither silently lags the library.
    """
    out_dir = repo_root / PANELS_DIR
    stale: list[str] = []
    for name, spec in PANELS.items():
        want = _generate_output(repo_root=repo_root, spec=spec)
        path = out_dir / f"{name}.html"
        if not path.exists() or _read_text(path) != want:
            stale.append(name)
    return stale


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
        nargs="?",
        type=Path,
        const=Path(""),
        metavar="DIR",
        help="Render the PANELS set to HTML fragments (default: web/src/generated/panels).",
    )
    args = ap.parse_args(argv)

    repo_root: Path = args.repo_root

    if args.emit_panels is not None:
        # `--emit-panels` bare → const Path("") (== PosixPath(".")) → in-repo default;
        # an explicit DIR is used as-is. (str(Path("")) is "." — truthy — so compare paths.)
        out_dir = (repo_root / PANELS_DIR) if args.emit_panels == Path("") else args.emit_panels
        written = emit_panels(repo_root=repo_root, out_dir=out_dir)
        # Doc pages always land at the in-repo default — they are committed,
        # gated artifacts; the DIR override only redirects the panel set.
        written += emit_doc_pages(repo_root=repo_root)
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
        panel_stale = check_panels(repo_root=repo_root)
        doc_page_stale = check_doc_pages(repo_root=repo_root)
        if mismatched or panel_stale or doc_page_stale:
            if mismatched:
                print("outputgen doc blocks out of date:", file=sys.stderr)
                for path, names in mismatched:
                    rel = path.relative_to(repo_root)
                    print(f"  - {rel}: {', '.join(names)}", file=sys.stderr)
            if panel_stale:
                print("site panels out of date — run `./dev panels`:", file=sys.stderr)
                for name in panel_stale:
                    print(f"  - {name}", file=sys.stderr)
            if doc_page_stale:
                print("site doc pages out of date — run `./dev panels`:", file=sys.stderr)
                for name in doc_page_stale:
                    print(f"  - {name}", file=sys.stderr)
            return 1
        return 0

    if changed:
        print("Updated:")
        for path in changed:
            print(f"  - {path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
