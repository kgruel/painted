"""Shell transport for completion — the bridge between a shell's completion
widget and painted's render-free producer (``complete.py``).

Two halves of decision E (loops ``design/completion-install-shape``):

* **emit** — ``painted completion zsh`` prints the shell glue (a ``#compdef``
  function for ``$fpath``); ``--install`` writes it to a completions file painted
  owns instead. Either way painted never edits a dotfile — it tells the user the
  one line to add if their shell isn't already looking where the glue lives.
* **transport** — that glue re-invokes the program with ``_PAINTED_COMPLETE``
  set and ``COMP_LINE``/``COMP_POINT`` carrying the edit buffer. The gate is
  intercepted at the top of ``AppRunner.run`` / ``CliRunner.run``; this module
  parses the buffer (quoting, ``--opt=val``, the cursor's word boundary) into
  the producer's ``preceding``/``prefix`` and prints the candidates back in the
  shell's expected format.

Renderer-free by construction (it imports only the producer + stdlib), so the
gate intercept stays on the no-renderer-on-TAB path.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .complete import (
    Candidate,
    _tolerant_split,
    app_wants_file_completion,
    complete_app,
    complete_args,
    wants_file_completion,
)

if TYPE_CHECKING:
    from .app_runner import AppCommand


# The glue sets this to the shell name (``zsh``); its presence is the request to
# complete rather than run. The value selects the output format below.
_GATE_ENV = "_PAINTED_COMPLETE"

COMPLETION_COMMAND_NAME = "completion"

# A directive line (not a candidate) telling the glue to add file/dir completion
# for this slot. The Unit-Separator prefix can't collide with a real candidate
# value (parsers don't declare control chars) and survives `read -r` intact.
_FILE_DIRECTIVE = "\x1ffiles"


def completion_active() -> str | None:
    """The shell name when a completion request is in flight, else ``None``.

    Read at the top of a runner's ``run``: a non-empty ``_PAINTED_COMPLETE``
    means the glue is calling back for candidates, and its value (``zsh``) is
    the output dialect."""
    shell = os.environ.get(_GATE_ENV)
    return shell or None


# =============================================================================
# Transport — COMP_LINE/COMP_POINT → candidates
# =============================================================================


def run_completion(
    commands: Sequence[AppCommand],
    *,
    prog: str | None,
    default: AppCommand | None,
    shell: str,
) -> int:
    """Complete the in-flight ``COMP_LINE`` against an app roster, print, exit 0.

    The app-level entry: drops the program word and forwards to ``complete_app``
    (roster + per-command forwarding)."""
    words, prefix, opt_prefix = _parse_comp_line(*_read_comp_env())
    preceding = words[1:]
    cands = complete_app(commands, preceding, prefix, prog=prog, default=default)
    files = app_wants_file_completion(commands, preceding, prog=prog, default=default)
    _emit(cands, shell, opt_prefix, files)
    return 0


def run_single_completion(
    parser: argparse.ArgumentParser,
    *,
    shell: str,
) -> int:
    """Complete the in-flight ``COMP_LINE`` against a single parser, print, exit 0.

    The ``run_cli`` entry: a one-command tool has no roster, so the program word
    is dropped and the rest forwarded straight to ``complete_args``."""
    words, prefix, opt_prefix = _parse_comp_line(*_read_comp_env())
    preceding = words[1:]
    cands = complete_args(parser, preceding, prefix)
    files = wants_file_completion(parser, preceding)
    _emit(cands, shell, opt_prefix, files)
    return 0


def _read_comp_env() -> tuple[str, int]:
    """The edit buffer and cursor offset the glue forwarded.

    ``COMP_POINT`` defaults to the end of the line and is clamped into it — a
    shell that under-reports (or omits) the cursor must not slice out of range."""
    line = os.environ.get("COMP_LINE", "")
    raw_point = os.environ.get("COMP_POINT", "")
    try:
        point = int(raw_point)
    except ValueError:
        point = len(line)
    return line, max(0, min(point, len(line)))


def _parse_comp_line(line: str, point: int) -> tuple[list[str], str, str | None]:
    """Tokenize the buffer up to the cursor → ``(words, prefix, opt_prefix)``.

    * ``words`` — the complete tokens before the partial one, program word at
      ``[0]`` (the producer strips it).
    * ``prefix`` — the partial token under the cursor (``""`` on a fresh word,
      i.e. a trailing space).
    * ``opt_prefix`` — set when the partial token is ``--opt=val``: the
      ``--opt=`` head, so the caller can re-attach it to value candidates. The
      option itself is appended to ``words`` so the producer enters that
      option's value context, and ``prefix`` becomes just ``val``.

    Only the left of the cursor is parsed (``COMP_POINT`` honored); quoting is
    tolerated through ``_tolerant_split`` (a dangling quote mid-word is normal).
    """
    left = line[:point]
    words = _tolerant_split(left)
    on_word = bool(left) and not left[-1].isspace()
    if on_word and words:
        prefix = words.pop()
    else:
        prefix = ""

    opt_prefix: str | None = None
    if prefix.startswith("-") and "=" in prefix:
        opt, _, value = prefix.partition("=")
        words.append(opt)  # the producer reads the previous token as the option
        opt_prefix = f"{opt}="
        prefix = value
    return words, prefix, opt_prefix


def _emit(
    cands: Sequence[Candidate], shell: str, opt_prefix: str | None, files: bool = False
) -> None:
    """Print candidates in the shell's dialect, plus the file directive if asked.

    When ``opt_prefix`` is set (an ``--opt=val`` token), each value is re-attached
    as ``--opt=value`` so the shell replaces the whole word. When ``files`` is set
    (an open value slot), a trailing ``_FILE_DIRECTIVE`` line tells the glue to
    add filesystem completion — suppressed under ``opt_prefix``, where prepending
    the option head to a shell-completed path isn't worth the fiddle (v1)."""
    for cand in cands:
        value = f"{opt_prefix}{cand.value}" if opt_prefix else cand.value
        if shell == "zsh":
            # _describe consumes `value:description`; a literal colon in the
            # value is its field separator, so escape it (mined from shtab).
            escaped = value.replace(":", r"\:")
            sys.stdout.write(
                f"{escaped}:{cand.description}\n" if cand.description else f"{escaped}\n"
            )
        else:
            # bash and the naive fallback take bare values, one per line.
            sys.stdout.write(f"{value}\n")
    if files and opt_prefix is None:
        sys.stdout.write(f"{_FILE_DIRECTIVE}\n")


# =============================================================================
# The auto-injected `completion` command — print glue, or --install it
# =============================================================================


def _detect_shell() -> str | None:
    """The user's shell from ``$SHELL``, or ``None`` when it can't be determined.

    ``None`` when ``$SHELL`` is unset or names a shell painted can't emit for.
    The caller decides the fallback: print defaults to ``zsh`` (harmless — it
    goes to stdout), but ``--install`` refuses rather than silently write the
    wrong shell's glue to disk."""
    name = Path(os.environ.get("SHELL", "")).name
    return name if name in _EMITTERS else None


def _install_target(shell: str, prog: str) -> Path | None:
    """The standard user completions *file* for ``shell`` (``None`` when painted
    has no install convention for it).

    Single source of truth for "is this shell installable": ``None`` here means
    the handler refuses — install is a subset of emit, painted won't write to a
    directory whose completion protocol it doesn't know. May raise ``RuntimeError``
    if ``$HOME`` is unresolvable; the caller degrades that to advice."""
    if shell == "zsh":
        base = Path(os.environ.get("ZDOTDIR") or Path.home())
        return base / ".zsh" / "completions" / f"_{prog}"
    if shell == "bash":
        user_dir = os.environ.get("BASH_COMPLETION_USER_DIR")
        base = (
            Path(user_dir)
            if user_dir
            else Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
            / "bash-completion"
        )
        return base / "completions" / prog
    return None


def _post_install_hint(shell: str, prog: str, target: Path) -> str:
    """The one remaining manual step, in plain text.

    Honest by construction: painted can't read the live ``$fpath`` (a zsh runtime
    array) or verify bash-completion is active, so it states the conditional step
    as advice rather than claiming success."""
    if shell == "zsh":
        return (
            f"Wrote {target}.\n"
            f"If {target.parent} is not on your $fpath, add to ~/.zshrc before compinit:\n"
            f"  fpath=({target.parent} $fpath)\n"
            "  autoload -Uz compinit && compinit\n"
            "Then restart your shell."
        )
    return (
        f"Wrote {target}.\n"
        "Restart your shell. If completions do not appear, ensure bash-completion "
        f'is installed, or add to ~/.bashrc:\n  eval "$({prog} completion bash)"'
    )


def _atomic_write(target: Path, content: str) -> None:
    """Write via a temp file + ``os.replace`` so a killed or failed write never
    leaves a truncated completion file (``os.replace`` is atomic on one
    filesystem; the temp sits beside the target, so it always is)."""
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def install_completion(shell: str, prog: str, *, dry_run: bool = False) -> int:
    """Write the shell glue to the standard user completions file and print the
    one remaining manual step. ``dry_run`` previews the plan without writing.

    Never edits a dotfile — it writes a file painted *owns* in a completions
    directory, and tells the user the single line to add if their shell isn't
    already looking there. Returns 0, or 1 with a manual fallback on an
    unsupported shell or a filesystem/``$HOME`` error — completion setup must
    degrade to advice, never a traceback."""
    emit = _EMITTERS.get(shell)
    if emit is None:
        installable = ", ".join(sorted(_EMITTERS))
        sys.stderr.write(f"Cannot install for {shell!r} (installable: {installable})\n")
        return 1
    content = emit(prog)
    try:
        target = _install_target(shell, prog)
    except (OSError, RuntimeError):
        target = None
    if target is None:
        sys.stderr.write(
            f"No install location for {shell!r}; print the glue instead:\n"
            f"  {prog} completion {shell}\n"
        )
        return 1
    hint = _post_install_hint(shell, prog, target)
    if dry_run:
        sys.stdout.write(f"Would write {target}:\n\n{content}\n{hint}\n")
        return 0
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, content)
    except (OSError, RuntimeError) as exc:
        sys.stderr.write(
            f"Could not write {target}: {exc}\n"
            f"Print and install manually: {prog} completion {shell}\n"
        )
        return 1
    sys.stdout.write(hint + "\n")
    return 0


def completion_add_args(parser: argparse.ArgumentParser) -> None:
    """The ``completion`` command's arguments: which shell, and whether to write.

    Declared via ``add_args`` so the command self-describes under ``-h`` and
    completes its own value (``painted completion <TAB>`` → ``zsh``/``bash``, and
    ``painted completion --<TAB>`` → ``--install``/``--dry-run``)."""
    parser.add_argument(
        "shell",
        nargs="?",
        default=None,
        choices=sorted(_EMITTERS),
        help="Shell to set up (default: detected from $SHELL)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Write the glue to your completions dir instead of printing it",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the install (target + glue) without writing",
    )


class _CompletionArgError(Exception):
    """A parse error from the ``completion`` command's own parser — raised
    instead of argparse's ``sys.exit(2)`` so the handler returns a friendly 1."""


def _completion_parser(prog: str | None) -> argparse.ArgumentParser:
    """The ``completion`` command's parser — the SAME grammar ``completion_add_args``
    declares (so ``-h``, TAB completion, and execution never diverge), but with
    ``error`` rerouted to a raise so a bad invocation is rc=1, not exit-2."""
    parser = argparse.ArgumentParser(prog=f"{prog or 'painted'} completion", add_help=False)
    completion_add_args(parser)

    def _raise(message: str) -> None:
        raise _CompletionArgError(message)

    parser.error = _raise  # type: ignore[method-assign]
    return parser


def completion_handler(prog: str | None) -> Callable[[list[str]], int]:
    """The ``completion`` command handler, closed over ``prog``.

    Prints the glue for the requested shell (default: detected from ``$SHELL``)
    and returns 0; ``--install`` writes it to the completions dir instead, and
    ``--dry-run`` previews that. Parses with the command's own declared grammar
    (``completion_add_args``) so ``-h``, TAB completion, and execution agree — a
    malformed invocation is a friendly rc=1, not an argparse exit-2."""

    def handler(argv: list[str]) -> int:
        try:
            ns = _completion_parser(prog).parse_args(argv)
        except _CompletionArgError as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        prog_name = prog or "painted"
        if ns.install or ns.dry_run:
            shell = ns.shell or _detect_shell()
            if shell is None:
                sys.stderr.write(
                    "Could not detect your shell from $SHELL; name it explicitly, "
                    f"e.g. `{prog_name} completion zsh --install`\n"
                )
                return 1
            return install_completion(shell, prog_name, dry_run=ns.dry_run)
        # print path: the benign zsh fallback is fine — it goes to stdout.
        shell = ns.shell or _detect_shell() or "zsh"
        sys.stdout.write(_EMITTERS[shell](prog_name))
        return 0

    return handler


def _zsh_script(prog: str) -> str:
    """A ``#compdef`` completion function for ``$fpath`` (the primary install).

    Save the output as ``_{prog}`` in a directory on ``$fpath`` and restart zsh.
    The function re-invokes the program with the gate set and the edit buffer in
    ``COMP_LINE``/``COMP_POINT``, then hands the ``value:description`` lines to
    ``_describe``. ``${words[1]}`` is the program as actually invoked, so the
    callback works regardless of install path.

    **Command-scoped buffer**: ``COMP_LINE`` is reconstructed from
    ``${words[1,$CURRENT]}`` (the zsh completion-context array for the *current*
    command) rather than from ``$BUFFER`` (the entire edit buffer). On a compound
    line like ``git pull && {prog} dem<TAB>``, ``$BUFFER`` carries the full line;
    the transport would then strip ``git`` as the program word and complete
    garbage. ``$words`` is already scoped to the current command by zsh's
    completion machinery.

    One fidelity loss accepted: ``COMP_POINT`` is set to the length of the
    reconstructed line (end of the partial word) rather than the intra-word cursor
    position. The transport parses only left of ``COMP_POINT``, and a prefix
    match on the partial word is always correct at the end, so this loss is
    harmless for all real completion scenarios."""
    return f"""\
#compdef {prog}
# {prog} shell completion — generated by `{prog} completion zsh`.
# Install: save this as _{prog} in a directory on your $fpath, then restart zsh
#   {prog} completion zsh > "${{fpath[1]}}/_{prog}"
local -a reply
local line files=0
reply=()
# Reconstruct a command-scoped COMP_LINE from the first $CURRENT words of the
# zsh $words completion array (the current command only, not the entire edit
# buffer — avoids the compound-line bug on "git pull && {prog} dem<TAB>").
local _cmd_line="${{(j: :)words[1,$CURRENT]}}"
while IFS= read -r line; do
  if [[ $line == $'\\x1f'* ]]; then files=1; continue; fi
  reply+=("$line")
done < <(_PAINTED_COMPLETE=zsh COMP_LINE="$_cmd_line" COMP_POINT="${{#_cmd_line}}" "${{words[1]}}" 2>/dev/null)
# Explicit status: `(( files )) && _files` as the last line would return 1
# whenever no file directive was sent, making compsys think the function found
# nothing and retry it once per matcher-list entry — re-adding every candidate
# each round (visible as duplicated match groups).
local ret=1
(( $#reply )) && _describe -t {prog} '{prog}' reply && ret=0
(( files )) && _files && ret=0
return ret
"""


def _bash_script(prog: str) -> str:
    """A ``complete -F`` function for bash (source it; e.g. ``eval``-from-rc).

    bash has no ``#compdef``/``$fpath`` autoload, so the install is a sourced
    function rather than a dropped file: ``eval "$({prog} completion bash)"`` in
    ``~/.bashrc``, or append to a bash-completion.d file. The function re-invokes
    the program with the gate set and the edit buffer in ``COMP_LINE``/
    ``COMP_POINT``, then fills ``COMPREPLY`` from the bare value lines (bash
    completion shows no descriptions — the zsh ``_describe`` edge doesn't apply).
    ``IFS=$'\\n'`` keeps a value with spaces intact; ``-o default`` lets bash fall
    back to filename completion when the producer yields nothing."""
    return f"""\
# {prog} bash completion — generated by `{prog} completion bash`.
# Install: eval "$({prog} completion bash)"   (e.g. add to ~/.bashrc)
_{prog}_complete() {{
    local IFS=$'\\n' line
    COMPREPLY=()
    while IFS= read -r line; do
        if [[ $line == $'\\x1f'* ]]; then compopt -o default 2>/dev/null; continue; fi
        COMPREPLY+=( "$line" )
    done < <(_PAINTED_COMPLETE=bash \\
        COMP_LINE="$COMP_LINE" COMP_POINT="$COMP_POINT" \\
        "${{COMP_WORDS[0]}}" 2>/dev/null)
}}
complete -F _{prog}_complete {prog}
"""


# shell name → glue emitter. The transport (_emit) already speaks both dialects:
# zsh gets `value:description` for _describe, every other shell bare values.
_EMITTERS: dict[str, Callable[[str], str]] = {
    "zsh": _zsh_script,
    "bash": _bash_script,
}
