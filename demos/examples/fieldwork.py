#!/usr/bin/env python3
"""Fieldwork — follow an operational question through recorded evidence.

Search incidents, follow explicit references in either direction, and return
with your question, depth, facets, and scroll position intact. The CLI and
interactive desk share the same evidence renderer. Records are historical
claims: recording time, reported event date, and current health are distinct.

    uv run demos/examples/fieldwork.py -i
    uv run demos/examples/fieldwork.py --match journald -v --checks
    uv run demos/examples/fieldwork.py --match banner --provenance
    uv run demos/examples/fieldwork.py --match journald --json
    uv run demos/examples/fieldwork.py --store ~/Code/gruel.network/.loops/data/homelab-coord.db -i

The bundled excerpt is from gruel.network. --store reads operational facts
from a local loops SQLite store, in read-only mode. It does not fold entities,
verify signatures, execute recorded commands, or query live infrastructure.

Keys: / search, j/k select, tab records/links, enter follow, backspace back,
v/V more/less detail, p provenance, c checks, f fields, m matches, PgUp/PgDn scroll,
? help, q quit. Checks are suggested commands, displayed for manual use.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from painted import Block, Fidelity, Style, Wrap, fit_to_width, join_vertical, run_cli
from painted.cli import OutputMode, Tag
from painted.palette import current_palette
from painted.tui import Region, Surface


_DATA = Path(__file__).with_name("data") / "fieldwork.json"
_KINDS = ("incident", "deploy", "practice", "decision", "principle", "thread", "observation")
_START = "01KY6DHHMM3Y41E2QHXAKS74NA"
_TAGS = [
    Tag("provenance", "Show recording time, observer, and fact ID", implied_at=3),
    Tag("fields", "Show additional recorded payload fields", implied_at=3),
    Tag("checks", "Show suggested checks and what they cannot establish"),
    Tag("matches", "List matching fact names and IDs"),
]


@dataclass(frozen=True)
class Link:
    field: str
    target: str


@dataclass(frozen=True)
class Record:
    id: str
    kind: str
    name: str
    message: str
    recorded: str
    observer: str
    event_date: str
    status: str
    links: tuple[Link, ...]
    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Check:
    records: tuple[str, ...]
    question: str
    command: str
    scope: str
    source: str


@dataclass(frozen=True)
class Archive:
    source: str
    records: tuple[Record, ...]
    checks: tuple[Check, ...] = ()


@dataclass(frozen=True)
class Relation:
    direction: str
    field: str
    target: str
    name: str
    available: bool


@dataclass(frozen=True)
class View:
    source: str
    total: int
    query: str
    kind: str
    matches: tuple[Record, ...]
    selected: Record | None
    relations: tuple[Relation, ...]
    checks: tuple[Check, ...]


@dataclass(frozen=True)
class Location:
    query: str = ""
    kind: str = "all"
    selected: str = _START
    fidelity: Fidelity = Fidelity()
    focus: str = "records"
    link_index: int = 0
    scroll: int = 0
    explicit_facets: frozenset[str] | None = None

    def __post_init__(self) -> None:
        # Direct callers supply explicit visible tags; the CLI passes intent
        # separately because its Fidelity has already absorbed depth implications.
        explicit = self.fidelity.visible if self.explicit_facets is None else self.explicit_facets
        implied = frozenset(
            t.name
            for t in _TAGS
            if t.implied_at is not None and self.fidelity.depth >= t.implied_at
        )
        object.__setattr__(self, "explicit_facets", explicit)
        object.__setattr__(self, "fidelity", replace(self.fidelity, visible=explicit | implied))


def _string(value: object) -> str:
    return (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )


def _record(raw: dict) -> Record:
    payload = raw["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("fact payload must be an object")
    ts = float(raw["ts"])
    if not math.isfinite(ts):
        raise ValueError("fact timestamp must be finite")
    links = [
        Link(key, value)
        for key, value in payload.items()
        if key.endswith("_ref") and isinstance(value, str)
    ]
    # Keep unresolved addresses as evidence of a missing edge, not a guessed join.
    for unresolved in payload.get("_unresolved_refs", ()):
        if isinstance(unresolved, dict) and isinstance(unresolved.get("addr"), str):
            links.append(Link(str(unresolved.get("field", "ref")), unresolved["addr"]))
    hidden = {"name", "topic", "message", "date", "status", "_unresolved_refs"}
    fields = tuple(
        (key, _string(value))
        for key, value in payload.items()
        if key not in hidden and not key.endswith("_ref")
    )
    return Record(
        id=str(raw["id"]),
        kind=str(raw["kind"]),
        name=str(payload.get("name", payload.get("topic", raw["id"]))),
        message=str(payload.get("message", "No message was recorded.")),
        recorded=datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds"),
        observer=str(raw.get("observer", "unknown")),
        event_date=str(payload.get("date", "not separately recorded")),
        status=str(payload.get("status", "not recorded")),
        links=tuple(links),
        fields=fields,
    )


def load_archive(store: Path | None = None) -> Archive:
    sample = json.loads(_DATA.read_text(encoding="utf-8"))
    checks = tuple(
        Check(tuple(c["records"]), c["question"], c["command"], c["scope"], c["source"])
        for c in sample["checks"]
    )
    if store is None:
        raw = sample["facts"]
        source = sample["source"]
    else:
        # mode=ro refuses missing paths instead of accidentally creating an empty DB.
        uri = store.expanduser().resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            placeholders = ",".join("?" for _ in _KINDS)
            cursor = connection.execute(
                "SELECT id,kind,ts,observer,payload FROM facts "
                f"WHERE kind IN ({placeholders}) ORDER BY arrival_ordinal,arrival_seq",
                _KINDS,
            )
            raw = [dict(zip(("id", "kind", "ts", "observer", "payload"), row)) for row in cursor]
        finally:
            connection.close()
        source = f"{store.name} / operational facts in arrival order / read-only snapshot"
    records = tuple(_record(row) for row in raw if row["kind"] in _KINDS)
    if len({r.id for r in records}) != len(records):
        raise ValueError("duplicate fact IDs")
    return Archive(source, records, checks)


def matches(archive: Archive, location: Location) -> tuple[Record, ...]:
    words = location.query.casefold().split()
    return tuple(
        r
        for r in reversed(archive.records)
        if (location.kind == "all" or r.kind == location.kind)
        and all(
            word
            in " ".join(
                (r.name, r.message, r.kind, r.observer, r.id, *[v for _, v in r.fields])
            ).casefold()
            for word in words
        )
    )


def project(archive: Archive, location: Location) -> View:
    found = matches(archive, location)
    selected = next((r for r in found if r.id == location.selected), found[0] if found else None)
    index = {r.id: r for r in archive.records}
    relations: list[Relation] = []
    if selected:
        for link in selected.links:
            target = index.get(link.target)
            relations.append(
                Relation(
                    "out",
                    link.field,
                    link.target,
                    target.name if target else link.target,
                    target is not None,
                )
            )
        for record in archive.records:
            for link in record.links:
                if link.target == selected.id:
                    relations.append(Relation("in", link.field, record.id, record.name, True))
    checks = tuple(c for c in archive.checks if selected and selected.id in c.records)
    return View(
        archive.source,
        len(archive.records),
        location.query,
        location.kind,
        found,
        selected,
        tuple(relations),
        checks,
    )


def _fetch() -> View:
    return project(load_archive(), Location())


def _shown(fidelity: Fidelity, tag: str) -> bool:
    declaration = next(t for t in _TAGS if t.name == tag)
    return fidelity.shows(tag) or (
        declaration.implied_at is not None and fidelity.depth >= declaration.implied_at
    )


def _render(view: View, fidelity: Fidelity, width: int | None) -> Block:
    """One evidence reading, shared unchanged by the CLI and the desk's viewport."""
    w = None if width is None else max(0, width)
    p = current_palette()
    parts: list[Block] = []

    def line(value: str, style: Style | None = None) -> None:
        parts.append(Block.text(value, style or Style(), width=w, wrap=Wrap.WORD))

    def heading(value: str) -> None:
        line(value, p.accent.merge(Style(bold=True)))

    record = view.selected
    if record is None:
        heading("No matching records")
        line(f"query: {view.query or '(all)'} / kind: {view.kind}", p.muted)
        line("This says nothing about current health. Broaden the search or clear it.", p.muted)
        block = join_vertical(*parts)
        return block if w is None else fit_to_width(block, w)
    if fidelity.depth <= 0:
        line(
            f"{record.kind} / {record.name} / {len(view.matches)} matches / "
            f"{len(view.relations)} links / historical record",
            p.accent,
        )
    else:
        heading(record.name)
        line(f"{record.kind} / recorded status: {record.status}", p.muted)
        line("Historical evidence; current health has not been checked.", p.warning)
        line("")
        if fidelity.depth >= 2 or len(record.message) <= 280:
            line(record.message)
        else:
            excerpt = record.message[:280].rsplit(" ", 1)[0]
            line(excerpt + " ...")
            line(
                f"[{len(record.message) - len(excerpt)} more characters: v / -v for full account]",
                p.muted,
            )

        line("")
        heading(f"Connected evidence ({len(view.relations)})")
        if not view.relations:
            line(
                "No explicit references in this snapshot. This is not proof of no related work.",
                p.muted,
            )
        for i, rel in enumerate(view.relations, 1):
            direction = "cites" if rel.direction == "out" else "cited by"
            missing = " [unavailable in snapshot]" if not rel.available else ""
            line(
                f"{i}. {direction} ({rel.field}) {rel.name}{missing}",
                p.accent if rel.available else p.warning,
            )

    if _shown(fidelity, "provenance"):
        line("")
        heading("Provenance")
        line(f"Reported event date: {record.event_date}")
        line(f"Recorded at: {record.recorded}")
        line(f"Observer: {record.observer} / fact: {record.id}")
        line(f"Source: {view.source}", p.muted)
        line("Raw fact; no entity fold or signature verification performed.", p.muted)
    if _shown(fidelity, "fields"):
        line("")
        heading("Recorded fields")
        for key, value in record.fields:
            line(f"{key}: {value}")
        if not record.fields:
            line("No additional fields recorded.", p.muted)
    if _shown(fidelity, "checks"):
        line("")
        heading("Questions to take back to the system")
        for check in view.checks:
            line(check.question, p.accent)
            line(check.command)
            line(check.scope, p.muted)
            line(f"Tool definition: gruel.network/{check.source}", p.muted)
        if not view.checks:
            line(
                "No check is attached to this record. Recorded fixes are not executable actions.",
                p.muted,
            )
    if _shown(fidelity, "matches"):
        line("")
        heading(f"Matching records ({len(view.matches)}/{view.total})")
        for match in view.matches:
            line(f"{match.kind} / {match.name}", p.accent)
            line(match.id, p.muted)
    block = join_vertical(*parts)
    return block if w is None else fit_to_width(block, w)


def _viewport_evidence(total: int, scroll: int, height: int, width: int) -> str:
    visible = min(height, total - scroll)
    label = f"lines {scroll + 1 if visible else 0}-{scroll + visible if visible else 0}/{total}"
    if len(label) <= width:
        return label
    omitted = total - visible
    if omitted:
        compact = f"+{omitted} rows"
        return compact if len(compact) <= width else "+"
    return "all" if width >= 3 else "="


class Fieldwork(Surface):
    def __init__(self, archive: Archive | None = None, location: Location | None = None) -> None:
        super().__init__()
        self.archive = archive if archive is not None else load_archive()
        self.location = location or Location()
        self.history: list[Location] = []
        self.searching = False
        self.draft = ""
        self.help = False
        self.help_scroll = 0
        self.help_max_scroll = 0
        self.notice = ""
        self.body_height = 1
        self.max_scroll = 0

    @property
    def view(self) -> View:
        return project(self.archive, self.location)

    def _move(self, delta: int) -> None:
        view = self.view
        if self.location.focus == "links":
            size = len(view.relations)
            if size:
                self.location = replace(
                    self.location, link_index=(self.location.link_index + delta) % size
                )
        elif view.matches:
            current = next(i for i, r in enumerate(view.matches) if r == view.selected)
            record = view.matches[(current + delta) % len(view.matches)]
            self.location = replace(self.location, selected=record.id, scroll=0, link_index=0)

    def _follow(self) -> None:
        view = self.view
        if not view.relations:
            self.notice = "No explicit links from this record."
            return
        relation = view.relations[self.location.link_index % len(view.relations)]
        if not relation.available:
            self.notice = "That reference is unavailable in this snapshot; it was not guessed."
            return
        self.history.append(self.location)
        self.location = replace(
            self.location,
            query="",
            kind="all",
            selected=relation.target,
            focus="links",
            link_index=0,
            scroll=0,
        )

    def on_key(self, key: str) -> None:
        self.notice = ""
        if self.searching:
            if key == "escape":
                self.searching = False
            elif key == "enter":
                self.history.append(self.location)
                self.location = replace(
                    self.location,
                    query=self.draft,
                    selected="",
                    scroll=0,
                    focus="records",
                    link_index=0,
                )
                self.searching = False
            elif key == "backspace":
                self.draft = self.draft[:-1]
            elif len(key) == 1 and key.isprintable():
                self.draft += key
            return
        if key == "q":
            self.quit()
        elif key == "?":
            self.help = not self.help
        elif key == "escape":
            self.help = False
        elif self.help:
            if key in ("page_down", "page_up", "j", "down", "k", "up"):
                step = max(1, self.body_height - 2) if key.startswith("page_") else 1
                if key in ("page_up", "k", "up"):
                    step = -step
                self.help_scroll = max(0, min(self.help_max_scroll, self.help_scroll + step))
            elif key == "home":
                self.help_scroll = 0
            elif key == "end":
                self.help_scroll = self.help_max_scroll
            return
        elif key == "/":
            self.searching, self.draft = True, self.location.query
        elif key in ("j", "down", "k", "up"):
            self._move(1 if key in ("j", "down") else -1)
        elif key == "tab":
            focus = "links" if self.location.focus == "records" else "records"
            self.location = replace(self.location, focus=focus)
        elif key == "enter":
            self._follow()
        elif key in ("backspace", "left"):
            if self.history:
                self.location = self.history.pop()
            else:
                self.notice = "Already at the start of this investigation."
        elif key in ("v", "V"):
            depth = max(0, min(3, self.location.fidelity.depth + (1 if key == "v" else -1)))
            self.location = replace(
                self.location, fidelity=self.location.fidelity.with_depth(depth), scroll=0
            )
        elif key in ("p", "c", "f", "m"):
            tag = {"p": "provenance", "c": "checks", "f": "fields", "m": "matches"}[key]
            explicit = set(self.location.explicit_facets or ())
            if tag in explicit:
                explicit.remove(tag)
            else:
                explicit.add(tag)
            self.location = replace(
                self.location,
                explicit_facets=frozenset(explicit),
                scroll=0,
            )
            if _shown(self.location.fidelity, tag) and tag not in explicit:
                self.notice = f"{tag} is also implied at depth 3; V reduces depth."
        elif key in ("page_down", "page_up"):
            step = max(1, self.body_height - 2) * (1 if key == "page_down" else -1)
            self.location = replace(
                self.location, scroll=max(0, min(self.max_scroll, self.location.scroll + step))
            )

    def render(self) -> None:
        buf = self._buf
        buf.fill(0, 0, buf.width, buf.height, " ", Style())
        width, height = buf.width, buf.height
        p = current_palette()

        def put(text: str, y: int, style: Style) -> None:
            if 0 <= y < height:
                Block.text(text, style, width=width, wrap=Wrap.ELLIPSIS).paint(buf, 0, y)

        def evidence(total: int, scroll: int) -> None:
            # Last paint wins even on a one-row terminal. Only a zero-sized
            # allocation physically prevents the compact '+' overflow marker.
            put(
                _viewport_evidence(total, scroll, self.body_height, width),
                max(0, height - 2),
                p.muted,
            )

        view = self.view
        put(
            "FIELDWORK  /  recorded evidence  /  " + self.archive.source,
            0,
            p.accent.merge(Style(bold=True)),
        )
        query = (
            "/ " + self.draft + "_"
            if self.searching
            else (
                f"search: {self.location.query or '(all)'} / {self.location.kind} / "
                f"{len(view.matches)}/{view.total} records / back {len(self.history)}"
            )
        )
        put(query, 1, p.warning if self.searching else p.muted)
        self.body_height = max(0, height - 5)
        if self.help:
            text = (
                "FOLLOW A QUESTION\n\n/ search words (all must match); Enter applies, Esc cancels\n"
                "j/k or arrows select; Tab switches records / links\n"
                "Enter follows the selected explicit link; Backspace retraces\n"
                "v / V change depth; p provenance; c checks; f fields; m matches\n"
                "PgUp / PgDn scroll the account or help; ? / Esc close help; q quits\n\n"
                "Try: /journald, choose the size-cap practice, Tab, then follow\n"
                "the fleet rollout. Compare the earlier claim with the later evidence.\n\n"
                "Every row is a raw recorded fact. Repeated names remain separate.\n"
                "Missing links remain visible. No current-health verdict is inferred."
            )
            block = Block.text(text, Style(), width=width, wrap=Wrap.WORD)
            self.help_max_scroll = max(0, block.height - self.body_height)
            self.help_scroll = min(self.help_scroll, self.help_max_scroll)
            block.paint(Region(0, 3, width, self.body_height).view(buf), 0, -self.help_scroll)
            put("PgUp/PgDn scroll; ? / Esc close help", height - 1, p.muted)
            evidence(block.height, self.help_scroll)
            return
        # On narrow terminals the list gets out of the way, with its selection
        # still visible in the status row. The evidence keeps the entire width.
        sidebar = 32 if width >= 88 else 0
        detail_x = sidebar + 2 if sidebar else 0
        detail_width = max(0, width - detail_x)
        detail = _render(view, self.location.fidelity, detail_width)
        self.max_scroll = max(0, detail.height - self.body_height)
        scroll = min(self.location.scroll, self.max_scroll)
        self.location = replace(self.location, scroll=scroll)
        detail.paint(Region(detail_x, 3, detail_width, self.body_height).view(buf), 0, -scroll)
        if sidebar:
            link_focus = self.location.focus == "links"
            entries = view.relations if link_focus else view.matches
            selected = (
                self.location.link_index
                if link_focus
                else next((i for i, r in enumerate(view.matches) if r == view.selected), 0)
            )
            selected = min(selected, max(0, len(entries) - 1))
            available = max(0, self.body_height - 2)
            start = (
                max(0, min(selected - available // 2, len(entries) - available)) if available else 0
            )
            rows = (
                [Block.text("LINKS" if link_focus else "RECORDS", p.accent, width=sidebar)]
                if self.body_height >= 2
                else []
            )
            for i in range(start, min(len(entries), start + available)):
                entry = entries[i]
                label = entry.name
                if link_focus:
                    label = ("<- " if entry.direction == "in" else "-> ") + label
                    if not entry.available:
                        label = "? " + label
                style = p.accent.merge(Style(reverse=True)) if i == selected else p.muted
                rows.append(Block.text(label, style, width=sidebar, wrap=Wrap.ELLIPSIS))
            rows.append(
                Block.text(
                    f"{start} above / {max(0, len(entries) - start - available)} below",
                    p.muted,
                    width=sidebar,
                    wrap=Wrap.ELLIPSIS,
                )
            )
            join_vertical(*rows).paint(Region(0, 3, sidebar, self.body_height).view(buf))
        selected_link = ""
        if self.location.focus == "links" and view.relations:
            rel = view.relations[self.location.link_index % len(view.relations)]
            selected_link = (
                f"link {self.location.link_index + 1}/{len(view.relations)}: {rel.name} / "
            )
        facets = ",".join(t.name for t in _TAGS if _shown(self.location.fidelity, t.name)) or "none"
        status = self.notice or (
            selected_link + f"depth {self.location.fidelity.depth} / facets {facets} / "
            f"focus {self.location.focus}"
        )
        put(status, 2, p.warning if self.notice else p.muted)
        put(
            "/ search  j/k select  tab links  enter follow  backspace back  v depth  p/c/f facets  ? help",
            height - 1,
            p.muted,
        )
        evidence(detail.height, scroll)


def main() -> int:
    explicit_facets: frozenset[str] = frozenset()

    def remember_explicit(args: argparse.Namespace, fidelity: Fidelity) -> Fidelity:
        # The existing compilation hook sees declared flags before ctx.args
        # drops them. Never infer intent by subtracting implications from visible.
        nonlocal explicit_facets
        explicit_facets = frozenset(t.name for t in _TAGS if getattr(args, t.name))
        return fidelity

    def add_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--store", type=Path, help="read operational facts from a loops SQLite store"
        )
        parser.add_argument("--match", default="", help="search words across recorded evidence")
        parser.add_argument(
            "--kind", default="all", choices=("all", *_KINDS), help="filter record kind"
        )
        parser.add_argument("--record", help="select one exact fact ID or unique record name")

    # Load lazily: --help works even when a requested store is unavailable.
    def open_location(ctx) -> tuple[Archive, Location]:
        options = ctx.args
        archive = load_archive(options.store)
        selected = _START if options.store is None else ""
        if options.record:
            found = [
                r for r in archive.records if r.id == options.record or r.name == options.record
            ]
            if len(found) != 1:
                raise ValueError(f"--record matched {len(found)} facts; use an exact fact ID")
            selected = found[0].id
        location = Location(
            query=options.match,
            kind=options.kind,
            selected=selected,
            fidelity=ctx.fidelity,
            explicit_facets=explicit_facets,
        )
        if options.record and not any(r.id == selected for r in matches(archive, location)):
            raise ValueError("--record is excluded by --match or --kind")
        return archive, location

    def fetch(ctx) -> View:
        archive, location = open_location(ctx)
        return project(archive, location)

    def interactive(ctx) -> int:
        archive, location = open_location(ctx)
        asyncio.run(Fieldwork(archive, location).run())
        return 0

    return run_cli(
        sys.argv[1:],
        renderer=_render,
        fetch=fetch,
        add_args=add_args,
        build_fidelity=remember_explicit,
        handlers={OutputMode.INTERACTIVE: interactive},
        description=__doc__,
        prog="fieldwork.py",
        tags=_TAGS,
    )


if __name__ == "__main__":
    sys.exit(main())
