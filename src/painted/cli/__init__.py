"""CLI framework layer for painted.

Argument parsing, context detection, mode dispatch, help rendering,
and lifecycle management for CLI tools built on painted's renderer.

    from painted.cli import run_cli, CliContext, Zoom

Imports are lazy (PEP 562), mirroring the top-level ``painted`` facade. This is
load-bearing for completion: ``import painted.cli.complete`` runs this package
``__init__``, and an eager ``from .help import …`` / ``from .runner import …``
here would drag ``core.doc`` / ``core.block`` onto the no-renderer-on-TAB path.
Lazy resolution keeps the package import itself render-free — only the name you
actually touch pulls its module.
"""

from __future__ import annotations

from importlib import import_module as _import_module

# name → (submodule, attr). The only place the module-of-record for each public
# name is declared; __getattr__ imports on demand and caches into globals().
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Types (render-free: types pulls only core.fidelity + core.zoom)
    "Zoom": (".types", "Zoom"),
    "Tag": (".types", "Tag"),
    "OutputMode": (".types", "OutputMode"),
    "Format": (".types", "Format"),
    "Fidelity": (".types", "Fidelity"),
    "CliContext": (".types", "CliContext"),
    "ArgsView": (".types", "ArgsView"),
    "resolve_mode": (".types", "resolve_mode"),
    "detect_context": (".types", "detect_context"),
    "add_cli_args": (".types", "add_cli_args"),
    "build_parser": (".types", "build_parser"),
    "parse_zoom": (".types", "parse_zoom"),
    "parse_mode": (".types", "parse_mode"),
    "parse_format": (".types", "parse_format"),
    "parse_fidelity": (".types", "parse_fidelity"),
    "implied_visible": (".types", "implied_visible"),
    # Inline prompts (render-free: prompts pulls core.errors + vocabulary)
    "MISSING": (".prompts", "MISSING"),
    "Danger": (".prompts", "Danger"),
    "Prompt": (".prompts", "Prompt"),
    "Confirm": (".prompts", "Confirm"),
    "Select": (".prompts", "Select"),
    "Input": (".prompts", "Input"),
    # Completion producer (render-free: complete pulls only types + _argwalk)
    "Candidate": (".complete", "Candidate"),
    "CompletionContext": (".complete", "CompletionContext"),
    "Completer": (".complete", "Completer"),
    "complete_via": (".complete", "complete_via"),
    "complete_args": (".complete", "complete_args"),
    "complete_app": (".complete", "complete_app"),
    "complete_line": (".complete", "complete_line"),
    # Help (pulls core.doc — renderer)
    "HelpArg": (".help", "HelpArg"),
    "help_doc": (".help", "help_doc"),
    "scan_help_args": (".help", "scan_help_args"),
    # Runner (pulls help → core.doc)
    "CliRunner": (".runner", "CliRunner"),
    "run_cli": (".runner", "run_cli"),
    # App runner
    "AppCommand": (".app_runner", "AppCommand"),
    "AppRunner": (".app_runner", "AppRunner"),
    "run_app": (".app_runner", "run_app"),
}

__all__ = list(_LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list(__all__) + list(globals())


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is not None:
        module_path, attr = spec
        mod = _import_module(module_path, __name__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'painted.cli' has no attribute {name!r}")
