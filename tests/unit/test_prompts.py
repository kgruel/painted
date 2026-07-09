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
from painted.vocabulary import Vocabulary


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


def test_input_default_must_pass_validate() -> None:
    with pytest.raises(DeclarationError, match="domain"):
        Input("x", "y", default="bad", validate=_only_digits)


def test_name_must_be_kebab() -> None:
    with pytest.raises(DeclarationError, match="kebab"):
        Confirm("Bad_Name", "y")


def test_valid_default_in_domain_constructs() -> None:
    assert Select("s", "q", values=("a", "b"), default="a").default == "a"
    assert Confirm("c", "q", default=True).default is True
    assert Input("i", "q", default="42", validate=_only_digits).default == "42"


def _only_digits(raw: str) -> str:
    if not raw.isdigit():
        raise ValueError("must be digits")
    return raw


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


@pytest.mark.parametrize("name", ["input", "json", "plain", "quiet", "verbose", "help"])
def test_prompt_colliding_with_framework_flag_raises(name: str) -> None:
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


def test_interactive_seam_is_a_stub_at_a_tty() -> None:
    session = PromptSession([Confirm("overwrite", "o")], {"overwrite": None}, stdin_tty=True)
    with pytest.raises(LifecycleError, match="not built yet"):
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
# Input validation at resolution
# =============================================================================


def test_input_flag_value_runs_validate() -> None:
    inp = Input("count", "how many", validate=_only_digits)
    ok = PromptSession([inp], {"count": "42"}, stdin_tty=False)
    assert ok.ask("count") == "42"
    bad = PromptSession([inp], {"count": "x"}, stdin_tty=False)
    with pytest.raises(PromptContractError):
        bad.ask("count")


# =============================================================================
# Undeclared name + runtime declarations (§6 Q3)
# =============================================================================


def test_ask_undeclared_name_raises_declaration_error() -> None:
    session = PromptSession([Confirm("overwrite", "o")], {"overwrite": None})
    with pytest.raises(DeclarationError, match="no prompt named 'nope'"):
        session.ask("nope")


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


def test_prompt_base_is_the_shared_primitive() -> None:
    # Confirm/Select/Input are domain shapes over one primitive.
    assert issubclass(Confirm, Prompt)
    assert issubclass(Select, Prompt)
    assert issubclass(Input, Prompt)
