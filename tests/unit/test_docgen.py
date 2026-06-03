"""Tests for tools/docgen.py — the fragment/region extraction engine and the
markdown --update/--check round-trip that the Docs gate tier (`./dev docs`)
depends on. This engine had zero direct coverage before this file, so its
region-selector edges (empty / missing-end / id-matching) were unguarded.
"""

from pathlib import Path

import pytest

from tools import docgen


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_frag(root: Path, frag_id: str, text: str) -> None:
    _write(root, f"docs/_fragments/{frag_id}.md", text)


# ---- extract_region (Python-source `# doc:region` spans) --------------------


def test_extract_region_returns_body_between_markers(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write(root, "sample.py", "before\n# doc:region demo\nINSIDE\n# doc:endregion demo\nafter\n")
    source, origin = docgen.extract_region(repo_root=root, rel_path="sample.py", region_id="demo")
    assert source == "INSIDE\n"
    assert (origin.start_line, origin.end_line) == (3, 3)


def test_extract_region_missing_region_raises_keyerror(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write(root, "sample.py", "x = 1\n")
    with pytest.raises(KeyError):
        docgen.extract_region(repo_root=root, rel_path="sample.py", region_id="nope")


def test_extract_region_missing_end_marker_raises_valueerror(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write(root, "sample.py", "# doc:region demo\nINSIDE\nno end here\n")
    with pytest.raises(ValueError, match="missing end marker"):
        docgen.extract_region(repo_root=root, rel_path="sample.py", region_id="demo")


def test_extract_region_empty_region_is_valid(tmp_path: Path) -> None:
    # Adjacent begin/end markers are a valid *empty* region. Before the C1 fix
    # this raised a misleading "missing end marker" even though it was found.
    root = tmp_path.resolve()
    _write(root, "sample.py", "# doc:region demo\n# doc:endregion demo\n")
    source, _ = docgen.extract_region(repo_root=root, rel_path="sample.py", region_id="demo")
    assert source == "\n"


def test_extract_region_only_matching_id_closes(tmp_path: Path) -> None:
    # An endregion for a *different* id must not close the region early.
    root = tmp_path.resolve()
    _write(
        root,
        "sample.py",
        "# doc:region outer\nA\n# doc:endregion other\nB\n# doc:endregion outer\n",
    )
    source, _ = docgen.extract_region(repo_root=root, rel_path="sample.py", region_id="outer")
    assert source == "A\n# doc:endregion other\nB\n"


def test_extract_region_rejects_path_escape(tmp_path: Path) -> None:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    with pytest.raises(ValueError, match="escapes repo root"):
        docgen.extract_region(repo_root=root, rel_path="../outside.py", region_id="x")


# ---- extract_fragment (markdown `<!-- region: -->` spans) -------------------

_FRAG = "Full intro.\n<!-- region:summary -->\nTerse summary.\n<!-- /region -->\nFull outro.\n"


def test_extract_fragment_whole_file_strips_region_markers(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_frag(root, "demo", _FRAG)
    source, _ = docgen.extract_fragment(repo_root=root, frag_id="demo")
    assert source == "Full intro.\nTerse summary.\nFull outro.\n"


def test_extract_fragment_region_returns_just_that_span(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_frag(root, "demo", _FRAG)
    source, _ = docgen.extract_fragment(repo_root=root, frag_id="demo", region="summary")
    assert source == "Terse summary.\n"


def test_extract_fragment_unknown_region_raises_keyerror(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_frag(root, "demo", _FRAG)
    with pytest.raises(KeyError):
        docgen.extract_fragment(repo_root=root, frag_id="demo", region="nope")


def test_extract_fragment_region_missing_end_raises_valueerror(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_frag(root, "demo", "Intro.\n<!-- region:summary -->\nbody with no close\n")
    with pytest.raises(ValueError, match="missing"):
        docgen.extract_fragment(repo_root=root, frag_id="demo", region="summary")


def test_extract_fragment_empty_region_matches_extract_region(tmp_path: Path) -> None:
    # Parity with extract_region's empty-region result (review finding C1):
    # the two extractors must agree that an empty region yields an empty body.
    root = tmp_path.resolve()
    _write_frag(root, "demo", "Intro.\n<!-- region:summary -->\n<!-- /region -->\nOutro.\n")
    source, _ = docgen.extract_fragment(repo_root=root, frag_id="demo", region="summary")
    assert source == "\n"


def test_extract_fragment_bad_id_raises_valueerror(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    with pytest.raises(ValueError, match="Bad fragment id"):
        docgen.extract_fragment(repo_root=root, frag_id="bad id!", region=None)


# ---- build_snippet_store + update/check round-trip --------------------------


def test_update_then_check_roundtrip(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_frag(root, "demo", _FRAG)
    snippets = docgen.build_snippet_store(["frag:demo#summary"], repo_root=root, index={})

    doc = (
        "# Title\n\n"
        "<!-- docgen:begin frag:demo#summary -->\n"
        "STALE OLD TEXT\n"
        "<!-- docgen:end -->\n\n"
        "tail\n"
    )
    # A drifted body is reported by --check ...
    assert docgen.check_markdown(doc, snippets=snippets) == ["frag:demo#summary"]

    # ... --update injects the canonical fragment body ...
    updated, touched = docgen.update_markdown(doc, snippets=snippets)
    assert touched == ["frag:demo#summary"]
    assert "Terse summary." in updated
    assert "STALE OLD TEXT" not in updated

    # ... and the result is clean + idempotent.
    assert docgen.check_markdown(updated, snippets=snippets) == []
    assert docgen.update_markdown(updated, snippets=snippets)[0] == updated


def test_build_snippet_store_whole_fragment_selector(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_frag(root, "demo", _FRAG)
    store = docgen.build_snippet_store(["frag:demo"], repo_root=root, index={})
    snip = store["frag:demo#fragment"]
    assert snip.language == "markdown"
    assert snip.source == "Full intro.\nTerse summary.\nFull outro.\n"


def test_find_docgen_selectors_lists_all_blocks() -> None:
    md = (
        "<!-- docgen:begin frag:a#summary -->\nx\n<!-- docgen:end -->\n"
        "<!-- docgen:begin frag:b -->\ny\n<!-- docgen:end -->\n"
    )
    assert docgen.find_docgen_selectors(md) == ["frag:a#summary", "frag:b"]
