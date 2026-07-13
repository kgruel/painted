"""Slice 4 — the reflections beyond parse (docs/PROMPTS_DESIGN.md §12 step 4).

Three deliverables, one theme: a declared prompt is real argparse grammar, so
everything that already reads a parser's actions reads a prompt's for free.

* The run_app mirror — ``AppCommand.prompts`` (§6's "run_app mirrors the
  declaration" paragraph): the same collision rules ``build_parser`` enforces
  for a single ``run_cli``, at construction and at first real parse build.
* Help (the second reflection) — a prompt's flag(s) render in both plain
  ``run_cli``'s own ``-h`` and ``AppRunner``'s intercepted subcommand help,
  built the same way ``add_args`` already is: register on a throwaway parser,
  walk it, project to ``Def`` — no new help machinery.
* Completion (the third reflection, composing with the fourth, §6's domain
  table): ``Select``'s choices complete for free (enumerable domain);
  ``Input.completer=`` rides the ``.completer`` seam, and without one the open
  slot keeps the file/dir fallback; HARD's challenge value never completes
  (§9) — the explicit "complete nothing" contract COMPLETION_DESIGN §5 already
  supports (a completer returning no candidates).
"""

from __future__ import annotations

import pytest

from painted import Block, Style
from painted.cli import (
    AppCommand,
    Confirm,
    Danger,
    Input,
    Select,
    Tag,
    build_parser,
    run_app,
    run_cli,
)
from painted.cli.complete import complete_app, complete_args, wants_file_completion
from painted.cli.help import framework_sections
from painted.core.doc import Defs, Section
from painted.core.errors import DeclarationError
from painted.vocabulary import Vocabulary


def _section_headings(nodes):
    return [n.heading for n in nodes if isinstance(n, Section)]


def _terms(section: Section) -> list[str]:
    return [d.term for defs in section.body if isinstance(defs, Defs) for d in defs.items]


def _render(data, _fidelity, _width):
    return Block.text(str(data), Style())


def _values(cands):
    return [c.value for c in cands]


# =============================================================================
# 1. The run_app mirror — AppCommand.prompts
# =============================================================================


class TestAppCommandPromptsMirror:
    def test_prompts_field_coerced_to_tuple(self):
        cmd = AppCommand("go", "Go", handler=lambda argv: 0, prompts=[Confirm("force", "Force?")])
        assert isinstance(cmd.prompts, tuple)

    def test_prompt_colliding_with_framework_flag_raises_at_construction(self):
        with pytest.raises(DeclarationError, match="collides"):
            AppCommand("go", "Go", handler=lambda argv: 0, prompts=[Confirm("input", "Force?")])

    def test_prompt_colliding_with_tag_raises_at_construction(self):
        with pytest.raises(DeclarationError, match="collides"):
            AppCommand(
                "go",
                "Go",
                handler=lambda argv: 0,
                tags=[Tag("scope", "the scope")],
                prompts=[Select("scope", "Which?", values=("a", "b"))],
            )

    def test_two_prompts_same_name_collide_at_construction(self):
        with pytest.raises(DeclarationError, match="collides"):
            AppCommand(
                "go",
                "Go",
                handler=lambda argv: 0,
                prompts=[Select("s", "a", values=("x",)), Input("s", "b")],
            )

    def test_prompt_construction_rules_still_apply(self):
        # AppCommand doesn't re-validate a Prompt's own construction rules —
        # they already fired at Prompt.__post_init__, before the AppCommand
        # ever sees the object. Confirming the plumbing doesn't swallow them.
        with pytest.raises(DeclarationError, match="Confirm-only"):
            AppCommand(
                "go",
                "Go",
                handler=lambda argv: 0,
                prompts=[Select("s", "q", values=("a",), danger=Danger.HARD)],
            )

    def test_add_args_prompt_dest_collision_surfaces_when_parser_is_built(self):
        # AppCommand construction alone doesn't build a real parser (mirrors
        # tags' existing behavior: TestAddArgsDestCollision in
        # test_tag_grammar.py is a run_cli-level test for the identical
        # reason) — the collision surfaces the first time a real parser is
        # built from the declarations. completion is exactly that moment at
        # the app level: the same build_parser() run_cli itself uses.
        cmd = AppCommand(
            "go",
            "Go",
            handler=lambda argv: 0,
            prompts=[Select("scope", "Which?", values=("a", "b"))],
            add_args=lambda p: p.add_argument("--other", dest="scope"),
        )
        with pytest.raises(DeclarationError, match="collides"):
            complete_app([cmd], ["go"], "--", prog="myapp")


# =============================================================================
# 2. Help — the second reflection
# =============================================================================


class TestFrameworkSectionsPrompts:
    def test_prompts_section_when_declared(self):
        sections = framework_sections(0, prompts=[Confirm("force", "Force?")])
        assert "Prompts" in _section_headings(sections)

    def test_no_prompts_section_without_prompts(self):
        assert "Prompts" not in _section_headings(framework_sections(0))

    def test_prompts_leads_and_never_steps_back(self):
        # Prompts is app-declared content, like Layers: it renders first and
        # stays at MINIMAL even when the universal grammar steps back (depth=1).
        sections = framework_sections(1, prompts=[Confirm("force", "Force?")])
        headings = _section_headings(sections)
        assert headings[0] == "Prompts"
        prompts_section = next(
            n for n in sections if isinstance(n, Section) and n.heading == "Prompts"
        )
        assert prompts_section.min_depth == 0

    def test_layers_leads_prompts_when_both_declared(self):
        sections = framework_sections(
            0, tags=[Tag("stats", "x")], prompts=[Confirm("force", "Force?")]
        )
        headings = _section_headings(sections)
        assert headings[:2] == ["Layers", "Prompts"]

    def test_confirm_boolean_pair_is_one_row(self):
        sections = framework_sections(0, prompts=[Confirm("force", "Force overwrite?")])
        section = next(n for n in sections if isinstance(n, Section) and n.heading == "Prompts")
        assert _terms(section) == ["--force, --no-force"]

    def test_select_row_shows_question_as_summary(self):
        sections = framework_sections(
            0, prompts=[Select("scope", "Which store?", values=("local", "all"))]
        )
        section = next(n for n in sections if isinstance(n, Section) and n.heading == "Prompts")
        assert section.body
        defs = next(n for n in section.body if isinstance(n, Defs))
        row = next(d for d in defs.items if d.term == "--scope")
        assert row.summary == "Which store?"

    def test_hard_confirm_shows_two_asymmetric_rows(self):
        # HARD registers two distinct argparse actions (a value-carrying yes,
        # a bare no) — walk_args yields two ArgSpecs, so two rows, honestly
        # reflecting the asymmetry rather than collapsing it like the boolean
        # pair (which really is one action).
        sections = framework_sections(
            0,
            prompts=[
                Confirm("reseal", "Re-seal the window?", danger=Danger.HARD, challenge="win-1")
            ],
        )
        section = next(n for n in sections if isinstance(n, Section) and n.heading == "Prompts")
        terms = _terms(section)
        assert "--reseal" in terms
        assert "--no-reseal" in terms
        defs = next(n for n in section.body if isinstance(n, Defs))
        yes_row = next(d for d in defs.items if d.term == "--reseal")
        # The help text names the ceremony without leaking the challenge value.
        assert "type the challenge" in yes_row.summary
        assert "win-1" not in yes_row.summary


class TestRunCliHelpRendersPrompts:
    def test_confirm_and_select_flags_render(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        result = run_cli(
            ["--help"],
            renderer=_render,
            fetch=lambda: "ok",
            prog="myapp",
            prompts=[
                Confirm("force", "Force overwrite?"),
                Select("scope", "Which store?", values=("local", "all")),
            ],
        )
        assert result == 0
        out = capsys.readouterr().out
        assert "Prompts" in out
        assert "--force" in out
        assert "--scope" in out
        assert "Force overwrite?" in out


class TestAppSubcommandHelpRendersPrompts:
    def test_declared_prompts_render_in_intercepted_help(self, capsys, monkeypatch):
        from painted.cli import HelpArg

        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        cmd = AppCommand(
            "reseal",
            "Reseal the window",
            handler=lambda argv: 0,
            help_args=[HelpArg("--dry-run", "preview only")],
            prompts=[
                Confirm("force", "Force reseal?"),
                Select("scope", "Which window?", values=("a", "b")),
            ],
        )
        assert run_app(["reseal", "-h"], [cmd], prog="myapp") == 0
        out = capsys.readouterr().out
        assert "Prompts" in out
        assert "--force" in out
        assert "--scope" in out
        assert "Force reseal?" in out

    def test_prompt_only_command_intercepts_help(self, capsys, monkeypatch):
        # prompts as the ONLY declaration mirror still intercepts -h: the
        # mirror exists exactly for the surfaces that never run the handler
        # (§12 step 4) — without interception the declared flag would be
        # invisible to help whenever the handler is opaque.
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        cmd = AppCommand(
            "go",
            "Go",
            handler=lambda argv: 17,  # sentinel exit — interception must not run this
            prompts=[Confirm("force", "Force?")],
        )
        assert run_app(["go", "-h"], [cmd], prog="myapp") == 0
        out = capsys.readouterr().out
        assert "Prompts" in out
        assert "--force" in out
        assert "Force?" in out


# =============================================================================
# 3. Completion — the third reflection composing with the fourth
# =============================================================================


class TestSelectCompletionIsFree:
    def test_values_tuple_choices_complete(self):
        parser = build_parser(prompts=[Select("scope", "Which?", values=("local", "all"))])
        assert _values(complete_args(parser, ["--scope"], "")) == ["all", "local"]

    def test_vocabulary_choices_complete(self):
        vocab = Vocabulary(
            "scope", values=("local", "all"), roles={"local": "accent", "all": "muted"}
        )
        parser = build_parser(prompts=[Select("scope", "Which?", vocabulary=vocab)])
        assert _values(complete_args(parser, ["--scope"], "")) == ["all", "local"]

    def test_prefix_filters_choices(self):
        parser = build_parser(prompts=[Select("scope", "Which?", values=("local", "all"))])
        assert _values(complete_args(parser, ["--scope"], "l")) == ["local"]

    def test_at_app_level_too(self):
        cmd = AppCommand(
            "go",
            "Go",
            handler=lambda argv: 0,
            prompts=[Select("scope", "Which?", values=("local", "all"))],
        )
        vals = _values(complete_app([cmd], ["go", "--scope"], "", prog="myapp"))
        assert vals == ["all", "local"]

    def test_prompt_flags_offered_in_word_context(self):
        cmd = AppCommand(
            "go",
            "Go",
            handler=lambda argv: 0,
            prompts=[Confirm("force", "Force?"), Select("scope", "Which?", values=("a", "b"))],
        )
        vals = _values(complete_app([cmd], ["go"], "--", prog="myapp"))
        assert "--force" in vals
        assert "--no-force" in vals
        assert "--scope" in vals


class TestInputCompletion:
    def test_declared_completer_candidates_appear(self):
        def complete_reason(ctx):
            return ["late", "broken", "typo"]

        parser = build_parser(prompts=[Input("reason", "Why?", completer=complete_reason)])
        assert _values(complete_args(parser, ["--reason"], "")) == ["broken", "late", "typo"]

    def test_completer_receives_the_context(self):
        seen = []

        def complete_reason(ctx):
            seen.append(ctx.prefix)
            return []

        parser = build_parser(prompts=[Input("reason", "Why?", completer=complete_reason)])
        complete_args(parser, ["--reason"], "br")
        assert seen == ["br"]

    def test_no_completer_falls_back_to_file_completion(self):
        parser = build_parser(prompts=[Input("reason", "Why?")])
        assert wants_file_completion(parser, ["--reason"]) is True

    def test_completer_returning_empty_opts_out_of_file_fallback(self):
        # The explicit opt-out (COMPLETION_DESIGN §5): a completer that
        # returns no candidates suppresses the file/dir fallback too, not
        # just the (already-empty) candidate list.
        parser = build_parser(prompts=[Input("reason", "Why?", completer=lambda ctx: [])])
        assert wants_file_completion(parser, ["--reason"]) is False
        assert complete_args(parser, ["--reason"], "") == []

    def test_at_app_level_too(self):
        cmd = AppCommand(
            "go",
            "Go",
            handler=lambda argv: 0,
            prompts=[Input("reason", "Why?", completer=lambda ctx: ["a", "b"])],
        )
        vals = _values(complete_app([cmd], ["go", "--reason"], "", prog="myapp"))
        assert vals == ["a", "b"]


class TestHardChallengeNeverCompletes:
    def test_challenge_value_never_completes(self):
        parser = build_parser(
            prompts=[Confirm("reseal", "Reseal?", danger=Danger.HARD, challenge="win-1")]
        )
        assert complete_args(parser, ["--reseal"], "") == []

    def test_challenge_value_slot_is_not_file_completion_either(self):
        # Not offering candidates isn't enough on its own — an untouched open
        # slot would fall to the file/dir fallback, which is exactly the kind
        # of surfaced candidate the ceremony (typing it yourself) forbids.
        parser = build_parser(
            prompts=[Confirm("reseal", "Reseal?", danger=Danger.HARD, challenge="win-1")]
        )
        assert wants_file_completion(parser, ["--reseal"]) is False

    def test_flag_names_still_complete_in_word_context(self):
        parser = build_parser(
            prompts=[Confirm("reseal", "Reseal?", danger=Danger.HARD, challenge="win-1")]
        )
        vals = _values(complete_args(parser, [], "--"))
        assert "--reseal" in vals  # the flag NAME, not its value
        assert "--no-reseal" in vals


# =============================================================================
# Render-free completion is preserved
# =============================================================================


class TestCompletionStillRenderFreeWithPrompts:
    def _imports_renderer(self, script: str) -> dict:
        import json
        import subprocess
        import sys

        probe = script + (
            "\nimport sys, json\n"
            "print(json.dumps({"
            "'block': 'painted.core.block' in sys.modules, "
            "'doc': 'painted.core.doc' in sys.modules}))\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_app_prompts_completion_is_render_free(self):
        flags = self._imports_renderer(
            "from painted.cli import AppCommand, Confirm, Select, complete_app\n"
            "cmds = [AppCommand('go', 'Go', lambda a: 0, "
            "prompts=[Confirm('force', 'Force?'), "
            "Select('scope', 'Which?', values=('a', 'b'))])]\n"
            "complete_app(cmds, ['go'], '--')\n"
        )
        assert flags == {"block": False, "doc": False}

    def test_single_command_prompts_completion_is_render_free(self):
        flags = self._imports_renderer(
            "from painted.cli import Confirm, build_parser\n"
            "from painted.cli.complete import complete_args\n"
            "parser = build_parser(prompts=[Confirm('force', 'Force?')])\n"
            "complete_args(parser, [], '--')\n"
        )
        assert flags == {"block": False, "doc": False}
