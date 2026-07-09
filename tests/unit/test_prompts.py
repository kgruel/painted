"""Inline prompts — the DECLARED rung (docs/PROMPTS_DESIGN.md §12 step 1).

Headless coverage of the whole contract: construction rules, flag generation,
the reserved-registry collisions, the resolution ladder (flag → interactive →
default → ContractError), memoization, ``--no-input``, the ``(default)`` record
line, and the stderr-routed refusal. No terminal is used — the stdin gate is a
plain constructor argument to ``PromptSession``, and the ``run_cli`` integration
fakes ``sys.stdin.isatty()`` so the suite passes identically piped and at a
terminal (the NO_COLOR conftest lesson, applied to ambient TTY-ness).
"""

from __future__ import annotations

import sys

import pytest

from painted.cli import Confirm, Danger, Input, Select
from painted.cli.prompts import MISSING, Prompt, PromptContractError, PromptSession
from painted.cli.types import (
    build_parser,
    consumer_args,
    detect_context,
)
from painted.cli.runner import run_cli
from painted.core.block import Block
from painted.core.cell import Style
from painted.core.errors import ContractError, DeclarationError, LifecycleError
from painted.core.fidelity import Fidelity
from painted.cli.types import OutputMode
from painted.vocabulary import Role, Vocabulary


class _FakeInput:
    """An injectable LINE-rung read stream (design §10) — for tests only.

    Each queued entry is returned verbatim from ``readline()`` — including or
    omitting its trailing newline, exactly like a real ``TextIOWrapper`` — or,
    if it is a ``BaseException`` instance, raised instead (simulating a
    Ctrl-C delivered mid-read). Once exhausted, further reads return ``""``
    (EOF), matching a real stream at end-of-input.
    """

    def __init__(self, lines: list[str | BaseException]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if not self._lines:
            return ""
        item = self._lines.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


# =============================================================================
# Danger — the ordered ceremony vocabulary
# =============================================================================


def test_danger_is_totally_ordered() -> None:
    assert Danger.NONE < Danger.SOFT < Danger.HARD
    assert Danger.HARD > Danger.NONE
    assert Danger.SOFT >= Danger.SOFT
    assert Danger.NONE <= Danger.HARD


def test_danger_compares_only_with_danger() -> None:
    # A cross-type comparison returns NotImplemented → TypeError, never a silent
    # ordinal leak (unlike IntEnum, which would compare against bare ints).
    with pytest.raises(TypeError):
        _ = Danger.SOFT < 1  # type: ignore[operator]


# =============================================================================
# MISSING sentinel
# =============================================================================


def test_missing_is_a_falsy_singleton() -> None:
    from painted.cli.prompts import _MissingType

    assert MISSING is _MissingType()
    assert not MISSING
    assert repr(MISSING) == "MISSING"


def test_absent_default_is_missing_not_none() -> None:
    # default=None is a *declared* answer (illegal here); absent is MISSING.
    assert Select("s", "q", values=("a", "b")).default is MISSING


# =============================================================================
# Construction-time DeclarationErrors (§6, §9)
# =============================================================================


def test_confirm_default_none_is_out_of_domain() -> None:
    with pytest.raises(DeclarationError, match="domain"):
        Confirm("x", "y", default=None)


def test_soft_forbids_default() -> None:
    with pytest.raises(DeclarationError, match="forbids default"):
        Confirm("x", "y", danger=Danger.SOFT, default=True)


def test_select_soft_forbids_default() -> None:
    with pytest.raises(DeclarationError, match="forbids default"):
        Select("x", "y", values=("a", "b"), danger=Danger.SOFT, default="a")


def test_hard_requires_challenge() -> None:
    with pytest.raises(DeclarationError, match="challenge"):
        Confirm("x", "y", danger=Danger.HARD)


def test_challenge_only_on_hard() -> None:
    with pytest.raises(DeclarationError, match="challenge"):
        Confirm("x", "y", challenge="tok")  # danger defaults to NONE
    with pytest.raises(DeclarationError, match="challenge"):
        Confirm("x", "y", danger=Danger.SOFT, challenge="tok")


def test_hard_is_confirm_only() -> None:
    with pytest.raises(DeclarationError, match="Confirm-only"):
        Select("x", "y", values=("a", "b"), danger=Danger.HARD)
    with pytest.raises(DeclarationError, match="Confirm-only"):
        Input("x", "y", danger=Danger.HARD)


def test_select_needs_exactly_one_domain_source() -> None:
    with pytest.raises(DeclarationError, match="neither"):
        Select("x", "y")
    vocab = Vocabulary("v", values=("a", "b"), roles={"a": "accent", "b": "muted"})
    with pytest.raises(DeclarationError, match="both"):
        Select("x", "y", values=("a", "b"), vocabulary=vocab)


def test_select_default_must_be_in_domain() -> None:
    with pytest.raises(DeclarationError, match="domain"):
        Select("x", "y", values=("a", "b"), default="z")


def test_input_default_must_parse() -> None:
    # The declared default is the raw string form; parse validates it at
    # construction, so a default parse can't fail cannot construct.
    with pytest.raises(DeclarationError, match="domain"):
        Input("x", "y", default="bad", parse=int)


def test_empty_challenge_is_rejected() -> None:
    # An empty / whitespace challenge is satisfied by an unset shell variable —
    # the accident the HARD tier exists to refuse (§9).
    with pytest.raises(DeclarationError, match="non-empty token"):
        Confirm("destroy", "d", danger=Danger.HARD, challenge="")
    with pytest.raises(DeclarationError, match="non-empty token"):
        Confirm("destroy", "d", danger=Danger.HARD, challenge="   ")


@pytest.mark.parametrize(
    "bad_values",
    [(), ("a", "a"), ("", "b"), (1, 2)],
    ids=["empty", "duplicate", "empty-string", "non-string"],
)
def test_select_values_must_be_a_coherent_str_domain(bad_values) -> None:
    with pytest.raises(DeclarationError):
        Select("s", "q", values=bad_values)


def test_name_must_be_kebab() -> None:
    with pytest.raises(DeclarationError, match="kebab"):
        Confirm("Bad_Name", "y")


def test_valid_default_in_domain_constructs() -> None:
    assert Select("s", "q", values=("a", "b"), default="a").default == "a"
    assert Confirm("c", "q", default=True).default is True
    # Input's declared default stays the raw string; parse maps it at resolution.
    assert Input("i", "q", default="42", parse=int).default == "42"


# =============================================================================
# Vocabulary-backed Select
# =============================================================================


def test_select_choices_from_vocabulary() -> None:
    vocab = Vocabulary("scope", values=("local", "all"), roles={"local": "accent", "all": "muted"})
    sel = Select("scope", "q", vocabulary=vocab)
    assert sel.choices == ("local", "all")


# =============================================================================
# Flag generation + reserved registry (§6)
# =============================================================================


def test_confirm_generates_boolean_pair() -> None:
    parser = build_parser(prompts=[Confirm("reseal", "r")])
    parsed = parser.parse_args(["--reseal"])
    assert parsed.reseal is True
    parsed = parser.parse_args(["--no-reseal"])
    assert parsed.reseal is False
    parsed = parser.parse_args([])
    assert parsed.reseal is None  # absent is distinguishable from False


def test_select_flag_is_choices_validated() -> None:
    parser = build_parser(prompts=[Select("scope", "w", values=("local", "all"))])
    assert parser.parse_args(["--scope", "all"]).scope == "all"
    with pytest.raises(SystemExit):
        parser.parse_args(["--scope", "bogus"])


def test_input_flag_takes_a_value() -> None:
    parser = build_parser(prompts=[Input("reason", "why")])
    assert parser.parse_args(["--reason", "because"]).reason == "because"


def test_input_parse_maps_str_to_answer_on_the_flag_channel() -> None:
    # parse is argparse type=: a good value converts to T, a bad one fails at
    # parse like any typed flag (eager, not a lazy resolution refusal).
    parser = build_parser(prompts=[Input("count", "how many", parse=int)])
    assert parser.parse_args(["--count", "42"]).count == 42
    with pytest.raises(SystemExit):
        parser.parse_args(["--count", "abc"])


def test_hard_flag_pair_is_value_carrying_and_mutually_exclusive() -> None:
    parser = build_parser(prompts=[Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1")])
    parsed = parser.parse_args(["--reseal", "win-1"])
    assert parsed.reseal == "win-1"
    assert parsed.no_reseal is False
    parsed = parser.parse_args(["--no-reseal"])
    assert parsed.no_reseal is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--reseal", "win-1", "--no-reseal"])


def test_no_input_flag_always_exists() -> None:
    parser = build_parser()
    assert parser.parse_args(["--no-input"]).no_input is True
    assert parser.parse_args([]).no_input is False


@pytest.mark.parametrize(
    "name",
    [
        "input",  # Confirm("input") → --no-input, the doc's canonical case
        "json",
        "plain",
        "quiet",
        "verbose",
        "help",
        "interactive",
        "static",
        "live",
        "max-chars",
        "max-lines",
    ],
)
def test_prompt_colliding_with_framework_flag_raises(name: str) -> None:
    # The full reserved registry — checked regardless of budgets=/modes=
    # filtering, so a declaration valid in one configuration can't break another.
    with pytest.raises(DeclarationError, match="collides"):
        build_parser(prompts=[Confirm(name, "y")])


def test_two_prompts_same_name_collide() -> None:
    with pytest.raises(DeclarationError, match="collides"):
        build_parser(prompts=[Select("s", "a", values=("x",)), Input("s", "b")])


def test_prompt_colliding_with_tag_raises() -> None:
    from painted.cli import Tag

    with pytest.raises(DeclarationError, match="collides"):
        build_parser(
            tags=[Tag("scope", "the scope")], prompts=[Select("scope", "w", values=("a",))]
        )


def test_add_args_cannot_land_on_a_prompt_dest() -> None:
    # A distinct option string with the *same* dest — argparse permits it (no
    # option-string clash), so the framework's dest guard is what must catch it.
    def add_args(parser) -> None:
        parser.add_argument("--other", dest="scope")

    with pytest.raises(DeclarationError, match="collides"):
        build_parser(add_args=add_args, prompts=[Select("scope", "w", values=("a",))])


# =============================================================================
# consumer_args strips prompt dests (§6 Q3 — one door)
# =============================================================================


def test_prompt_dests_stripped_from_consumer_args() -> None:
    prompts = [
        Select("scope", "w", values=("local", "all")),
        Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1"),
    ]

    def add_args(parser) -> None:
        parser.add_argument("--extra")

    parser = build_parser(add_args=add_args, prompts=prompts)
    parsed = parser.parse_args(["--scope", "all", "--extra", "v"])
    view = consumer_args(parsed, None, None, prompts)
    assert "scope" not in view
    assert "reseal" not in view
    assert "no_reseal" not in view
    assert "no_input" not in view
    assert view["extra"] == "v"


# =============================================================================
# Resolution ladder via PromptSession (§3, §6)
# =============================================================================


def test_flag_resolves_silently(capsys: pytest.CaptureFixture[str]) -> None:
    sel = Select("scope", "w", values=("local", "all"))
    session = PromptSession([sel], {"scope": "all"}, stdin_tty=False)
    assert session.ask("scope") == "all"
    # A flag-supplied answer echoes nothing (§7 — the invocation shows it).
    assert capsys.readouterr().err == ""


def test_default_fires_when_not_a_terminal(capsys: pytest.CaptureFixture[str]) -> None:
    sel = Select("scope", "w", values=("local", "all"), default="local")
    session = PromptSession([sel], {"scope": None}, stdin_tty=False, stderr_tty=False)
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    assert "scope: local (default)" in err


def test_default_record_line_is_the_only_echo_and_fires_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "w", values=("local", "all"), default="local")
    session = PromptSession([sel], {"scope": None}, stdin_tty=False)
    session.ask("scope")
    session.ask("scope")  # memoized — no second record line
    assert capsys.readouterr().err.count("(default)") == 1


def test_refusal_names_the_flag(capsys: pytest.CaptureFixture[str]) -> None:
    session = PromptSession([Confirm("overwrite", "o")], {"overwrite": None}, stdin_tty=False)
    with pytest.raises(PromptContractError) as excinfo:
        session.ask("overwrite")
    msg = str(excinfo.value)
    assert "stdin is not a terminal" in msg
    assert "--overwrite" in msg and "--no-overwrite" in msg
    # It is a ContractError to any consumer catching the public class.
    assert isinstance(excinfo.value, ContractError)


def test_memoization_returns_recorded_answer() -> None:
    sel = Select("scope", "w", values=("local", "all"))
    session = PromptSession([sel], {"scope": "all"}, stdin_tty=False)
    assert session.ask("scope") == "all"
    assert session.ask("scope") == "all"


def test_no_input_suppresses_interaction_at_a_tty(capsys: pytest.CaptureFixture[str]) -> None:
    sel = Select("scope", "w", values=("local", "all"), default="local")
    # stdin IS a tty, but --no-input makes it behave as if it were not.
    session = PromptSession([sel], {"scope": None}, stdin_tty=True, no_input=True)
    assert session.ask("scope") == "local"


def test_hard_confirm_interactive_seam_is_a_stub_at_a_tty() -> None:
    # HARD's type-the-challenge ceremony is CELL-only (slice 5) — it stays
    # stubbed at every rung, LINE included.
    hard = Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1")
    session = PromptSession([hard], {"reseal": None, "no_reseal": False}, stdin_tty=True)
    with pytest.raises(LifecycleError, match="CELL"):
        session.ask("reseal")


def test_declared_default_at_a_tty_goes_through_line_not_the_default_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Resolution order (§6): interactive-at-TTY precedes the declared default —
    # at a real TTY the default is *presented through* the LINE rung (bare
    # Enter accepts it), not returned by the non-interactive default path. The
    # record line proves which path fired: LINE's carries no "(default)"
    # suffix (§7's rule — that suffix marks an answer nobody chose).
    sel = Select("scope", "w", values=("local", "all"), default="local")
    session = PromptSession([sel], {"scope": None}, stdin_tty=True, stdin=_FakeInput(["\n"]))
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    # "scope: local" appears only in the record line — the option listing
    # spells it "1) local (default)", not "scope: local".
    assert "scope: local" in err
    assert "scope: local (default)" not in err


def test_no_input_without_a_default_refuses() -> None:
    # --no-input at a TTY behaves as non-terminal: no flag, no default → refusal.
    session = PromptSession(
        [Confirm("overwrite", "o")], {"overwrite": None}, stdin_tty=True, no_input=True
    )
    with pytest.raises(PromptContractError):
        session.ask("overwrite")


# =============================================================================
# HARD confirm resolution (§9)
# =============================================================================


def test_hard_flag_matching_challenge_resolves_true() -> None:
    hard = Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1")
    session = PromptSession([hard], {"reseal": "win-1", "no_reseal": False}, stdin_tty=False)
    assert session.ask("reseal") is True


def test_hard_flag_mismatch_is_a_contract_error() -> None:
    hard = Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1")
    session = PromptSession([hard], {"reseal": "wrong", "no_reseal": False}, stdin_tty=False)
    with pytest.raises(PromptContractError, match="does not match the required challenge"):
        session.ask("reseal")


def test_hard_no_flag_resolves_false() -> None:
    hard = Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1")
    session = PromptSession([hard], {"reseal": None, "no_reseal": True}, stdin_tty=False)
    assert session.ask("reseal") is False


# =============================================================================
# Input parse — str → T, the return becomes the answer (§6)
# =============================================================================


def test_input_parsed_flag_resolves_to_T() -> None:
    inp = Input("count", "how many", parse=int)
    # argparse type= already produced the int; resolution returns it as-is.
    session = PromptSession([inp], {"count": 42}, stdin_tty=False)
    assert session.ask("count") == 42


def test_input_parsed_default_resolves_to_T(capsys: pytest.CaptureFixture[str]) -> None:
    inp = Input("count", "how many", parse=int, default="7")
    session = PromptSession([inp], {"count": None}, stdin_tty=False)
    answer = session.ask("count")
    assert answer == 7 and isinstance(answer, int)


def test_input_without_parse_answers_the_raw_string() -> None:
    inp = Input("reason", "why")
    session = PromptSession([inp], {"reason": "because"}, stdin_tty=False)
    assert session.ask("reason") == "because"


# =============================================================================
# Undeclared name + runtime declarations (§6 Q3)
# =============================================================================


def test_ask_undeclared_name_raises_declaration_error() -> None:
    session = PromptSession([Confirm("overwrite", "o")], {"overwrite": None})
    with pytest.raises(DeclarationError, match="no prompt named 'nope'"):
        session.ask("nope")


def test_runtime_prompt_colliding_with_declared_name_raises() -> None:
    # A runtime declaration whose name shadows a parse-time prompt would resolve
    # against the declared prompt's parked flag answer — outside the runtime
    # domain. That is a DeclarationError telling the caller to ask by name.
    declared = Select("scope", "w", values=("local", "all"))
    session = PromptSession([declared], {"scope": "all"}, stdin_tty=False)
    runtime = Select("scope", "different domain", values=("a", "b"), default="a")
    with pytest.raises(DeclarationError, match="already declared at parse time"):
        session.ask(runtime)


def test_runtime_declaration_refusal_names_the_channel() -> None:
    session = PromptSession([], {}, stdin_tty=False)
    runtime = Select("conflict", "overwrite which?", values=("a", "b"))
    with pytest.raises(PromptContractError, match="declared at runtime"):
        session.ask(runtime)


def test_runtime_declaration_with_default_resolves() -> None:
    session = PromptSession([], {}, stdin_tty=False)
    runtime = Select("conflict", "which?", values=("a", "b"), default="a")
    assert session.ask(runtime) == "a"


def test_runtime_declaration_is_memoized() -> None:
    session = PromptSession([], {}, stdin_tty=False)
    runtime = Select("conflict", "which?", values=("a", "b"), default="a")
    assert session.ask(runtime) == "a"
    assert session.ask(runtime) == "a"  # second read is memoized, no re-resolve


# =============================================================================
# detect_context grows explicit stdin/stderr dimensions (§8)
# =============================================================================


class _FakeStream:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_detect_context_reads_stdin_and_stderr_ttyness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStream(True))
    monkeypatch.setattr(sys, "stderr", _FakeStream(False))
    monkeypatch.setattr(sys, "stdout", _FakeStream(False))
    ctx = detect_context(Fidelity(depth=1), OutputMode.STATIC)
    assert ctx.stdin_is_tty is True
    assert ctx.stderr_is_tty is False
    assert ctx.is_tty is False  # stdout-derived, unchanged


def test_ctx_ask_works_through_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))
    sel = Select("scope", "w", values=("local", "all"))
    ctx = detect_context(
        Fidelity(depth=1), OutputMode.STATIC, prompts=[sel], parked={"scope": "all"}
    )
    assert ctx.ask("scope") == "all"


def test_empty_context_ask_refuses_runtime_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    # A directly-constructed context (no session wiring) still resolves runtime
    # asks non-interactively — its default session is stdin-not-a-TTY.
    from painted.cli.types import CliContext

    ctx = CliContext(
        Fidelity(depth=1), OutputMode.STATIC, use_ansi=False, is_tty=False, width=80, height=24
    )
    with pytest.raises(PromptContractError):
        ctx.ask(Confirm("go", "go?"))


# =============================================================================
# run_cli integration (the whole path)
# =============================================================================


def _render(ctx, data) -> Block:
    return Block.text(str(data), Style())


def test_run_cli_flag_answer_reaches_fetch_and_strips_args(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))
    prompts = [Select("scope", "w", values=("local", "all")), Confirm("force", "f")]

    def fetch(ctx):
        return {"args": sorted(ctx.args), "scope": ctx.ask("scope"), "force": ctx.ask("force")}

    rc = run_cli(["--scope", "all", "--force", "--plain"], _render, fetch, prompts=prompts)
    out = capsys.readouterr().out
    assert rc == 0
    assert "'scope': 'all'" in out
    assert "'force': True" in out
    assert "'args': []" in out  # prompt dests never appear in ctx.args


def test_run_cli_refusal_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))

    def fetch(ctx):
        return {"ok": ctx.ask("overwrite")}

    rc = run_cli(["--plain"], _render, fetch, prompts=[Confirm("overwrite", "o")])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""  # stdout stays a clean data channel
    assert "stdin is not a terminal" in captured.err
    assert "--overwrite" in captured.err


def test_run_cli_default_record_line_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))
    prompts = [Select("scope", "w", values=("local", "all"), default="local")]

    def fetch(ctx):
        return {"scope": ctx.ask("scope")}

    rc = run_cli(["--plain"], _render, fetch, prompts=prompts)
    captured = capsys.readouterr()
    assert rc == 0
    assert "scope: local (default)" in captured.err
    assert "'scope': 'local'" in captured.out


def test_run_cli_no_input_forces_declared_resolution(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # stdin IS a tty; --no-input still resolves the default without prompting.
    monkeypatch.setattr(sys, "stdin", _FakeStream(True))
    prompts = [Select("scope", "w", values=("local", "all"), default="local")]

    def fetch(ctx):
        return {"scope": ctx.ask("scope")}

    rc = run_cli(["--plain", "--no-input"], _render, fetch, prompts=prompts)
    assert rc == 0
    assert "'scope': 'local'" in capsys.readouterr().out


def test_run_cli_json_refusal_emits_nothing_on_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # F1: --json must not print an {"error": ...} object on a refusal — stdout
    # stays parseable (empty), remediation to stderr, nonzero exit.
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))

    def fetch(ctx):
        return {"ok": ctx.ask("overwrite")}

    rc = run_cli(["--json"], _render, fetch, prompts=[Confirm("overwrite", "o")])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "stdin is not a terminal" in captured.err


def test_run_cli_live_stream_refusal_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # F1: a refusal raised inside a streaming render routes through the seam too.
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))

    async def fetch_stream(ctx):
        yield {"n": 1}

    def render(ctx, data):
        ctx.ask("overwrite")  # refuses (non-tty, no flag/default)
        return Block.text(str(data), Style())

    rc = run_cli(
        ["--plain"],
        render,
        lambda: {"n": 0},
        fetch_stream=fetch_stream,
        prompts=[Confirm("overwrite", "o")],
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "stdin is not a terminal" in captured.err


def test_run_cli_custom_handler_refusal_goes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # F1: a refusal from a custom mode handler must not leak a raw traceback —
    # the dispatch-layer seam catches it uniformly.
    monkeypatch.setattr(sys, "stdin", _FakeStream(False))

    def handler(ctx):
        ctx.ask("overwrite")
        return 0

    rc = run_cli(
        ["-i"],
        _render,
        lambda: {},
        handlers={OutputMode.INTERACTIVE: handler},
        prompts=[Confirm("overwrite", "o")],
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "stdin is not a terminal" in captured.err


def test_prompt_base_is_the_shared_primitive() -> None:
    # Confirm/Select/Input are domain shapes over one primitive.
    assert issubclass(Confirm, Prompt)
    assert issubclass(Select, Prompt)
    assert issubclass(Input, Prompt)


# =============================================================================
# LINE rung (§5, §7, §12 step 2) — cooked-mode interactive resolution
# =============================================================================
# All three domain shapes, driven through PromptSession with an injected
# stdin (§10) and stdin_tty=True so the interactive seam actually fires.
# Every test asserts on stderr only — stdout is untouched by prompt UI (§8).


def _line_session(prompt, lines, *, stderr_tty: bool = False) -> PromptSession:
    return PromptSession(
        [prompt],
        {d: None for d in prompt.dests()},
        stdin_tty=True,
        stderr_tty=stderr_tty,
        stdin=_FakeInput(lines),
    )


# --- Confirm ------------------------------------------------------------


def test_line_confirm_explicit_yes_and_no(capsys: pytest.CaptureFixture[str]) -> None:
    assert _line_session(Confirm("go", "Go?"), ["y\n"]).ask("go") is True
    assert _line_session(Confirm("go", "Go?"), ["yes\n"]).ask("go") is True
    assert _line_session(Confirm("go", "Go?"), ["n\n"]).ask("go") is False
    assert _line_session(Confirm("go", "Go?"), ["no\n"]).ask("go") is False


def test_line_confirm_none_bare_enter_accepts_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _line_session(Confirm("go", "Go?", default=True), ["\n"])
    assert session.ask("go") is True
    err = capsys.readouterr().err
    assert "go: yes" in err
    assert "(default)" not in err  # LINE's own record line, not the default path's


def test_line_confirm_soft_bare_enter_is_invalid_and_reprompts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # SOFT forbids default= at construction, so bare Enter can never accept
    # one — it's simply invalid input, same as any unparseable answer.
    soft = Confirm("go", "Go?", danger=Danger.SOFT)
    session = _line_session(soft, ["\n", "y\n"])
    assert session.ask("go") is True
    err = capsys.readouterr().err
    assert "Please answer y or n" in err


def test_line_confirm_invalid_answer_reprompts_then_succeeds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _line_session(Confirm("go", "Go?"), ["maybe\n", "y\n"])
    assert session.ask("go") is True
    err = capsys.readouterr().err
    assert "Please answer y or n" in err
    assert err.count("Please answer") == 1  # exactly one bad attempt


# --- Select ---------------------------------------------------------------


def test_line_select_numeric_choice(capsys: pytest.CaptureFixture[str]) -> None:
    sel = Select("scope", "Which?", values=("local", "all"))
    session = _line_session(sel, ["2\n"])
    assert session.ask("scope") == "all"
    err = capsys.readouterr().err
    assert "1) local" in err
    assert "2) all" in err
    assert "Enter 1-2" in err


def test_line_select_none_bare_enter_accepts_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "Which?", values=("local", "all"), default="local")
    session = _line_session(sel, ["\n"])
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    assert "1) local (default)" in err
    assert "Enter 1-2 [1]" in err
    # "scope: local" appears only in the record line — the option listing
    # spells it "1) local (default)", not "scope: local" — so this pins the
    # record line specifically to carry no "(default)" suffix.
    assert "scope: local" in err
    assert "scope: local (default)" not in err


def test_line_select_out_of_range_and_non_numeric_reprompt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "Which?", values=("local", "all"))
    session = _line_session(sel, ["0\n", "bogus\n", "3\n", "1\n"])
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    assert err.count("Please enter a number between 1 and 2") == 3


# --- Vocabulary marks at LINE (design §5, §7) -------------------------
# "Same value → same treatment, the vocabulary guarantee, applied to input" —
# a Select(vocabulary=...) marks its option values and its record line
# wherever they render styled; a values=-tuple Select has no vocabulary to
# mark with and stays untouched; plain fidelity is unaffected either way
# (marks degrade to nothing, monotonically).

_SCOPE_VOCAB = Vocabulary(
    "scope",
    values=("local", "all"),
    roles={"local": Role("scope-local", Style(underline=True)), "all": "warning"},
)


def test_line_select_vocabulary_marks_options_when_styled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "Which?", vocabulary=_SCOPE_VOCAB)
    session = _line_session(sel, ["1\n"], stderr_tty=True)
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    # "local" is bound to a Role carrying Style(underline=True) — its own,
    # otherwise-unused SGR code — so this pins the mark to the option text,
    # not just "some escape code appeared somewhere in the line".
    assert "\x1b[4m" in err


def test_line_select_vocabulary_options_plain_when_stderr_not_a_tty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "Which?", vocabulary=_SCOPE_VOCAB)
    session = _line_session(sel, ["1\n"], stderr_tty=False)
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    assert "\x1b[" not in err
    assert "1) local" in err and "2) all" in err


def test_line_select_values_tuple_stays_unmarked_even_when_styled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No vocabulary declared: nothing to mark with, even though the surrounding
    # cue/number styling (accent "? ", muted numbering) still renders.
    sel = Select("scope", "Which?", values=("local", "all"))
    session = _line_session(sel, ["1\n"], stderr_tty=True)
    session.ask("scope")
    err = capsys.readouterr().err
    assert "\x1b[4m" not in err  # the vocabulary test's distinguishing code, absent


def test_line_select_vocabulary_marks_the_line_answered_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "Which?", vocabulary=_SCOPE_VOCAB)
    session = _line_session(sel, ["1\n"], stderr_tty=True)
    session.ask("scope")
    err = capsys.readouterr().err
    record_line = err.splitlines()[-1]
    # Styled spans interleave SGR/reset codes between "scope:" and "local", so
    # the record line's *text* isn't one contiguous substring — check both
    # pieces are present, plus the mark's distinguishing code, on that line.
    assert "scope:" in record_line and "local" in record_line
    assert "\x1b[4m" in record_line


def test_default_record_line_is_marked_by_vocabulary_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # §7 makes no distinction between the LINE-answered record and the
    # (default) record — both are drawn by the same _emit_record, so both
    # must carry the mark.
    sel = Select("scope", "Which?", vocabulary=_SCOPE_VOCAB, default="local")
    session = PromptSession([sel], {"scope": None}, stdin_tty=False, stderr_tty=True)
    assert session.ask("scope") == "local"
    err = capsys.readouterr().err
    assert "scope:" in err and "local" in err and "(default)" in err
    assert "\x1b[4m" in err


def test_default_record_line_unmarked_for_values_tuple_select(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sel = Select("scope", "Which?", values=("local", "all"), default="local")
    session = PromptSession([sel], {"scope": None}, stdin_tty=False, stderr_tty=True)
    session.ask("scope")
    err = capsys.readouterr().err
    assert "\x1b[4m" not in err


# --- Input ------------------------------------------------------------


def test_line_input_happy_path_with_parse(capsys: pytest.CaptureFixture[str]) -> None:
    inp = Input("count", "How many?", parse=int)
    session = _line_session(inp, ["42\n"])
    assert session.ask("count") == 42
    err = capsys.readouterr().err
    assert "count: 42" in err


def test_line_input_reprompts_on_parse_failure(capsys: pytest.CaptureFixture[str]) -> None:
    inp = Input("count", "How many?", parse=int)
    session = _line_session(inp, ["abc\n", "7\n"])
    assert session.ask("count") == 7
    err = capsys.readouterr().err
    assert "Invalid input" in err


def test_line_input_none_bare_enter_accepts_default_through_parse(
    capsys: pytest.CaptureFixture[str],
) -> None:
    inp = Input("count", "How many?", parse=int, default="7")
    session = _line_session(inp, ["\n"])
    answer = session.ask("count")
    assert answer == 7 and isinstance(answer, int)


def test_line_input_without_parse_answers_raw_string(capsys: pytest.CaptureFixture[str]) -> None:
    inp = Input("reason", "Why?")
    session = _line_session(inp, ["because\n"])
    assert session.ask("reason") == "because"


# --- Abort paths (§7): EOF and Ctrl-C, never an answer, never the default ---


def test_line_eof_aborts_distinct_from_bare_enter_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No queued lines at all: the very first readline() is EOF (""), not the
    # NONE-tier bare-Enter default-accept ("\n") — the ambiguity trap (§7).
    session = _line_session(Confirm("go", "Go?", default=True), [])
    with pytest.raises(KeyboardInterrupt):
        session.ask("go")


def test_line_ctrl_c_propagates_as_keyboard_interrupt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _line_session(Confirm("go", "Go?"), [KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        session.ask("go")
    # A restoring newline was written to stderr before the exception propagated.
    assert capsys.readouterr().err.endswith("\n")


def test_line_abort_never_yields_none_or_falls_to_default() -> None:
    session = _line_session(Confirm("go", "Go?", default=True), [])
    try:
        session.ask("go")
        pytest.fail("expected KeyboardInterrupt")
    except KeyboardInterrupt:
        pass
    # The memo must not have recorded an invented answer for the aborted ask.
    assert "go" not in session._answers


# --- Record-line collapse: once, memoized second ask stays silent (§7) -----


def test_line_record_line_fires_once_second_ask_is_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _line_session(Confirm("go", "Go?"), ["y\n"])
    assert session.ask("go") is True
    assert session.ask("go") is True  # memoized — no second read, no second line
    err = capsys.readouterr().err
    assert err.count("go: yes") == 1


# --- Styled vs plain, by stderr's own TTY-ness (§8) -------------------------


def test_line_styles_when_stderr_is_a_tty_plain_when_not(
    capsys: pytest.CaptureFixture[str],
) -> None:
    styled = _line_session(Confirm("go", "Go?"), ["y\n"], stderr_tty=True)
    styled.ask("go")
    styled_err = capsys.readouterr().err
    assert "\x1b[" in styled_err  # some SGR escape made it out

    plain = _line_session(Confirm("go", "Go?"), ["y\n"], stderr_tty=False)
    plain.ask("go")
    plain_err = capsys.readouterr().err
    assert "\x1b[" not in plain_err


# --- HARD still stubbed at LINE (§9, §12 step 5) ----------------------------


def test_line_hard_confirm_still_raises_lifecycle_error() -> None:
    hard = Confirm("reseal", "r", danger=Danger.HARD, challenge="win-1")
    session = _line_session(hard, ["win-1\n"])  # never read — the stub raises first
    with pytest.raises(LifecycleError, match="CELL"):
        session.ask("reseal")


# --- The suite passes identically piped and at a terminal (§10) ------------
# These tests never consult ambient TTY-ness — stdin_tty/stdin are always
# explicit constructor arguments — so running under `pytest < /dev/null` or
# interactively makes no difference to any assertion above.


# --- run_cli integration: the injected stdin reaches the LINE rung ---------


class _FakeTTYInput:
    """A combined isatty()+readline() fake for the run_cli integration path."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        return self._lines.pop(0) if self._lines else ""


def test_run_cli_line_prompt_reads_from_injected_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Select's LINE rung reads a *number*, not the value text, so drive it
    # with the option index rather than the literal string.
    monkeypatch.setattr(sys, "stdin", _FakeTTYInput(["2\n"]))
    prompts = [Select("scope", "Which store?", values=("local", "all"))]

    def fetch(ctx):
        return {"scope": ctx.ask("scope")}

    rc = run_cli(["--plain"], _render, fetch, prompts=prompts)
    captured = capsys.readouterr()
    assert rc == 0
    assert "'scope': 'all'" in captured.out
    assert "scope: all" in captured.err
    assert "1) local" in captured.err and "2) all" in captured.err


# =============================================================================
# CELL rung — reducer-driven, injected key source (§5, §7, §12 step 3)
# =============================================================================

import io  # noqa: E402

from painted._prompt_cell import (  # noqa: E402
    _confirm_block,
    _input_block,
    _select_block,
    resolve_cell,
)
from painted.views import ListState, TextInputState  # noqa: E402


def _keys(seq):
    """A blocking key source over a fixed list; None (EOF) once exhausted."""
    it = iter(seq)
    return lambda: next(it, None)


def _block_text(block: Block) -> str:
    return "\n".join("".join(c.char for c in block.row(y)) for y in range(block.height))


def _cell(prompt, seq):
    return resolve_cell(prompt, stdin=io.StringIO(), stderr=io.StringIO(), key_source=_keys(seq))


# --- Select: ListState cursor -------------------------------------------------


def test_cell_select_arrow_then_enter() -> None:
    p = Select("scope", "Which store?", values=("local", "config", "all"))
    assert _cell(p, ["down", "enter"]) == "config"
    assert _cell(p, ["down", "down", "up", "enter"]) == "config"


def test_cell_select_home_end() -> None:
    p = Select("scope", "w", values=("local", "config", "all"))
    assert _cell(p, ["end", "enter"]) == "all"
    assert _cell(p, ["end", "home", "enter"]) == "local"


def test_cell_select_starts_cursor_on_default() -> None:
    p = Select("scope", "w", values=("local", "config", "all"), default="config")
    # Bare Enter accepts the default because the cursor starts *on* it (visible).
    assert _cell(p, ["enter"]) == "config"


def test_cell_select_block_shows_cursor_and_options() -> None:
    p = Select("scope", "Which?", values=("local", "config", "all"))
    state = ListState().with_count(3).move_to(1)
    text = _block_text(_select_block(p, state, 3))
    assert "Which?" in text
    assert "local" in text and "config" in text and "all" in text
    assert "▸" in text  # the ListState cursor glyph on the selected row


def test_cell_select_marks_vocabulary_values() -> None:
    vocab = Vocabulary("scope", values=("local", "all"), roles={"local": "error", "all": "success"})
    p = Select("scope", "w", vocabulary=vocab)
    state = ListState().with_count(2).move_to(0)
    block = _select_block(p, state, 2)
    fgs = {c.style.fg for y in range(block.height) for c in block.row(y)}
    # Same value → same treatment (§5): the marks apply at CELL as everywhere.
    assert "green" in fgs and "red" in fgs


# --- Input: TextInputState editing + parse ------------------------------------


def test_cell_input_types_and_parses() -> None:
    p = Input("count", "How many", parse=int)
    assert _cell(p, ["4", "2", "enter"]) == 42


def test_cell_input_cursor_editing() -> None:
    p = Input("word", "Word")
    # type "ac", move left, insert "b" → "abc"
    assert _cell(p, ["a", "c", "left", "b", "enter"]) == "abc"
    # backspace deletes before the cursor
    assert _cell(p, ["a", "x", "backspace", "b", "enter"]) == "ab"


def test_cell_input_reject_then_fix() -> None:
    p = Input("count", "How many", parse=int)
    # "x" fails parse → hint, keep editing; backspace, "5" → 5
    assert _cell(p, ["x", "enter", "backspace", "5", "enter"]) == 5


def test_cell_input_empty_enter_takes_default() -> None:
    p = Input("count", "How many", parse=int, default="7")
    assert _cell(p, ["enter"]) == 7


def test_cell_input_block_shows_hint_after_reject() -> None:
    p = Input("count", "How many", parse=int)
    state = TextInputState().insert("x")
    text = _block_text(_input_block(p, state, "Invalid input: bad"))
    assert "How many" in text and "Invalid input" in text


# --- Confirm: single-key y/n, danger governs Enter ----------------------------


def test_cell_confirm_y_and_n() -> None:
    p = Confirm("go", "Go?")
    assert _cell(p, ["y"]) is True
    assert _cell(p, ["n"]) is False
    assert _cell(p, ["Y"]) is True  # case-insensitive


def test_cell_confirm_none_enter_accepts_default() -> None:
    assert _cell(Confirm("go", "Go?", default=True), ["enter"]) is True
    assert _cell(Confirm("go", "Go?", default=False), ["enter"]) is False


def test_cell_confirm_soft_ignores_enter() -> None:
    # SOFT has no default and demands an explicit key — Enter re-prompts (§9).
    p = Confirm("go", "Go?", danger=Danger.SOFT)
    assert _cell(p, ["enter", "enter", "y"]) is True


def test_cell_confirm_block_shows_default_cue() -> None:
    assert "[Y/n]" in _block_text(_confirm_block(Confirm("go", "Go?", default=True), None))
    assert "[y/N]" in _block_text(_confirm_block(Confirm("go", "Go?", default=False), None))
    assert "[y/n]" in _block_text(_confirm_block(Confirm("go", "Go?"), None))


# --- Abort: EOF / Ctrl-D are the same KeyboardInterrupt path (§7) -------------


@pytest.mark.parametrize("seq", [[], ["\x04"], ["\x03"]], ids=["eof", "ctrl-d", "ctrl-c-byte"])
def test_cell_abort_raises_keyboard_interrupt(seq) -> None:
    with pytest.raises(KeyboardInterrupt):
        _cell(Confirm("go", "Go?"), seq)


def test_cell_abort_restores_cbreak_before_settling(monkeypatch: pytest.MonkeyPatch) -> None:
    # §7 ordering: exit cbreak FIRST, then settle the region, then propagate.
    order: list[str] = []

    class _FakeKB:
        def __init__(self, stream=None):
            pass

        def __enter__(self):
            order.append("kb_enter")
            return self

        def __exit__(self, *a):
            order.append("kb_exit")

        def read_key(self):
            return "\x04"  # abort immediately

    class _FakeRenderer:
        def __init__(self, stream=None):
            pass

        def __enter__(self):
            order.append("r_enter")
            return self

        def __exit__(self, *a):
            order.append("r_exit")

        def render(self, block):
            order.append("render")

        def clear(self):
            order.append("clear")

    monkeypatch.setattr("painted._prompt_cell.KeyboardInput", _FakeKB)
    monkeypatch.setattr("painted._prompt_cell.InPlaceRenderer", _FakeRenderer)
    with pytest.raises(KeyboardInterrupt):
        resolve_cell(Confirm("go", "Go?"), stdin=io.StringIO(), stderr=io.StringIO())
    assert order.index("kb_exit") < order.index("clear") < order.index("r_exit")


# --- Rung selection matrix (stdin × probe × stderr → CELL / LINE / DECLARED) --


def _rung_session(prompt, *, stdin_tty, stderr_tty):
    return PromptSession(
        [prompt],
        {prompt.dest: None},
        stdin_tty=stdin_tty,
        stderr_tty=stderr_tty,
        stdin=io.StringIO(),
    )


def _stub_rungs(monkeypatch, *, cbreak):
    monkeypatch.setattr("painted.keyboard.cbreak_supported", lambda s=None: cbreak)
    monkeypatch.setattr("painted._prompt_cell.resolve_cell", lambda p, **k: "CELL")
    monkeypatch.setattr("painted.cli._prompt_line.resolve_line", lambda p, **k: "LINE")


def test_rung_cell_when_stdin_stderr_tty_and_cbreak(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_rungs(monkeypatch, cbreak=True)
    sess = _rung_session(Select("s", "w", values=("a", "b")), stdin_tty=True, stderr_tty=True)
    assert sess._render_interactive(sess._by_name["s"]) == "CELL"


def test_rung_line_when_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # stdin + stderr both TTY, but cbreak unavailable → LINE (byte-identical to
    # slice 2, whose own tests pin the exchange).
    _stub_rungs(monkeypatch, cbreak=False)
    sess = _rung_session(Select("s", "w", values=("a", "b")), stdin_tty=True, stderr_tty=True)
    assert sess._render_interactive(sess._by_name["s"]) == "LINE"


def test_rung_line_when_stderr_not_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    # stderr piped → LINE even if cbreak is available (CELL repaints on stderr).
    _stub_rungs(monkeypatch, cbreak=True)
    sess = _rung_session(Select("s", "w", values=("a", "b")), stdin_tty=True, stderr_tty=False)
    assert sess._render_interactive(sess._by_name["s"]) == "LINE"


def test_rung_declared_when_stdin_not_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    # stdin not a TTY: neither interactive rung is reached — the default fires.
    def _boom(*a, **k):
        raise AssertionError("interactive rung reached with stdin not a TTY")

    monkeypatch.setattr("painted._prompt_cell.resolve_cell", _boom)
    monkeypatch.setattr("painted.cli._prompt_line.resolve_line", _boom)
    sess = PromptSession(
        [Select("s", "w", values=("a", "b"), default="a")],
        {"s": None},
        stdin_tty=False,
        stderr_tty=True,
    )
    assert sess.ask("s") == "a"


def test_cell_answer_collapses_to_the_record_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # With CELL selected and the region drawn+cleared by resolve_cell, the only
    # thing left on stderr is the one static record line (§7 collapse).
    monkeypatch.setattr("painted.keyboard.cbreak_supported", lambda s=None: True)
    monkeypatch.setattr("painted._prompt_cell.resolve_cell", lambda p, **k: "config")
    sess = PromptSession(
        [Select("scope", "w", values=("local", "config", "all"))],
        {"scope": None},
        stdin_tty=True,
        stderr_tty=True,  # CELL requires a TTY stderr
        stdin=io.StringIO(),
    )
    assert sess.ask("scope") == "config"
    err = capsys.readouterr().err
    assert "scope" in err and "config" in err  # the record line is present
    assert "?" not in err  # no prompt residue — the region became the record
