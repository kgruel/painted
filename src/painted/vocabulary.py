"""Vocabularies: the mark channel — meaning becomes color through a declaration.

A **vocabulary** is a closed set of named values that require consistent
treatment: the same value renders the same way in every delivery, at every call
site. Fact kinds, edge direction, freshness, priority — the recurring shape a
program otherwise re-derives as a scatter of ad-hoc ``if kind == ...`` colorings.
Order is an optional property (``ordered=True``), not the price of admission; an
ordered vocabulary unlocks the comparative behaviors (``index``/``at_least``/
``cmp``, and ``Thresholds`` onto a numeric domain).

painted owns the *mechanism* — declaration, validation at construction,
consistent rendering — and never the app's words. Every ``Style`` a renderer
applies for *meaning* traces to a role, and every role traces to a declaration:
one of painted's five core roles, an app-declared ``Role`` carried by a
vocabulary, or the ``series`` ramp (``overflow="series"``). A hex code in a call
site is presentation from nowhere; the mechanism makes it unnecessary.

``mark_style(vocab_name, value)`` is the single point where a value becomes a
``Style`` — resolved through the *current* palette and theme role-overrides, so a
``use_theme`` re-tints marks without touching declarations. This is the mark
analogue of ``fidelity.shows()``.

The honesty rules (design doc §1): an undeclared lookup raises (rule 2); a value
outside the vocabulary raises unless ``overflow`` is declared (rule 3);
vocabularies generate no CLI flags — this module imports neither ``painted.cli``
nor ``argparse``, and that is pinned structurally (rule 4). Rule 1 ("a declared
vocabulary must change output") is not end-to-end testable until a mark-consuming
renderer exists — it lands with the gutter re-expression (slice 3) and
``paint(mark=)``.

Delivery mirrors ``use_palette``: ``use_vocabularies`` is both an immediate setter
and a scoped context manager. Like all painted ambient state it is a ContextVar,
so it does not cross threads; a long-lived handler snapshots at construction and
reapplies per-emit (the ``PaintedHandler`` precedent).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from dataclasses import KW_ONLY, dataclass, field
from types import MappingProxyType
from typing import Any

from .core.cell import Style
from .palette import CORE_ROLE_NAMES, current_palette, series_index

# Deliberate local duplicate of ``cli.types._DECLARED_NAME_RE``. The kebab
# discipline is shared by *convention*, not import: honesty rule 4 forbids this
# module depending on ``cli`` (a vocabulary classifies data; it is not user
# grammar). Two spellings of one rule, kept in sync by review.
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Role:
    """An app-declared role, joining painted's five core roles + the ``text``
    substrate as a named target a vocabulary value can bind to.

    A role is declared exactly once — inline, by the first vocabulary that needs
    it — and referenced by name everywhere else. Declaring the role is what makes
    the value *themeable* rather than hardcoded: a palette or theme overrides an
    app role by name (``Theme(roles={"stale": Style(...)})``) exactly as it
    overrides a core role. Redeclaring the same name with a *different* style
    raises; an identical redeclaration is idempotent-OK (frozen equality).

    A ``Role`` may not reuse a core role name — reference the core role by string
    instead (``"accent"``). ``name`` is lowercase kebab-case.
    """

    name: str
    style: Style

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(
                f"Role name {self.name!r} must be lowercase kebab-case "
                "(it names a themeable target, like a core role)"
            )
        if self.name in CORE_ROLE_NAMES:
            raise ValueError(
                f"Role name {self.name!r} reuses a core role: reference the core "
                f'role by string instead (e.g. "{self.name}"), or pick a distinct '
                "app-role name"
            )


@dataclass(frozen=True)
class Vocabulary:
    """A closed set of named values, each bound to a role.

    ``values`` is the closed set; ``roles`` binds every value to a core role
    (by string) or an inline ``Role``. Order is opt-in: with ``ordered=True``,
    declaration order *is* the order and the comparative behaviors unlock
    (``index``/``at_least``/``cmp`` and ``Thresholds``). ``attention`` names
    which end pulls the eye (``"first"``/``"last"``); it is validated always but
    only meaningful when ordered (it drives gutter emphasis, not set membership).

    ``overflow="series"`` is the upgrade path for mostly-closed sets: a declared
    value gets its bound role, an unknown value falls to the ``series`` ramp
    instead of raising (design doc §5). Left ``None``, an unknown value raises
    (honesty rule 3).

    Construction validates everything the ``check_declarations`` discipline
    demands: kebab name, non-empty/unique values, every value bound, no binding
    dangling onto a non-value, every role reference resolvable, and no two values
    binding the same app-role name to conflicting styles.
    """

    name: str
    values: tuple[str, ...]
    # Everything past `values` is keyword-only (doc §3 signature): a bare
    # positional `Vocabulary("kind", (...), {...}, "series")` would otherwise
    # silently bind "series" to `ordered` (truthy — comparative behaviors unlock)
    # while `overflow` stayed None. Names at the call site, not position.
    _: KW_ONLY
    roles: Mapping[str, str | Role]
    ordered: bool = False
    overflow: str | None = None
    attention: str = "last"
    # Derived at construction, not passed: the normalized value→(role_name, Role)
    # binding and this vocabulary's own app Role objects. Declared (rather than
    # only object.__setattr__-stashed) so type checkers see them; excluded from
    # init/repr/eq — they are a function of the fields above.
    _binding: Mapping[str, tuple[str, Role | None]] = field(init=False, repr=False, compare=False)
    _app_roles: tuple[Role, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(f"Vocabulary name {self.name!r} must be lowercase kebab-case")

        values = tuple(self.values)
        object.__setattr__(self, "values", values)
        if not values:
            raise ValueError(f"Vocabulary {self.name!r} declares no values")
        if any(not isinstance(v, str) or not v for v in values):
            raise ValueError(f"Vocabulary {self.name!r} values must be non-empty strings")
        if len(set(values)) != len(values):
            raise ValueError(f"Vocabulary {self.name!r} has duplicate values")

        if self.overflow not in (None, "series"):
            raise ValueError(
                f'Vocabulary {self.name!r} overflow must be None or "series", not {self.overflow!r}'
            )
        if self.attention not in ("first", "last"):
            raise ValueError(
                f'Vocabulary {self.name!r} attention must be "first" or '
                f'"last", not {self.attention!r}'
            )

        value_set = set(values)
        dangling = [k for k in self.roles if k not in value_set]
        if dangling:
            raise ValueError(
                f"Vocabulary {self.name!r} binds roles for non-values "
                f"{sorted(dangling)!r} (a role key must be one of the values)"
            )
        unbound = [v for v in values if v not in self.roles]
        if unbound:
            raise ValueError(
                f"Vocabulary {self.name!r} leaves values {sorted(unbound)!r} "
                "unbound (every value needs a role)"
            )

        # Resolve each reference into a (role_name, Role|None) pair. A string must
        # name a core role; a Role is taken as-is (its own validation already ran).
        binding: dict[str, tuple[str, Role | None]] = {}
        app_roles: list[Role] = []
        for value in values:
            ref = self.roles[value]
            if isinstance(ref, Role):
                binding[value] = (ref.name, ref)
                app_roles.append(ref)
            elif isinstance(ref, str):
                if ref not in CORE_ROLE_NAMES:
                    raise ValueError(
                        f"Vocabulary {self.name!r} value {value!r} references "
                        f"role {ref!r}, which is not a core role "
                        f"({sorted(CORE_ROLE_NAMES)!r}); pass a Role to declare it"
                    )
                binding[value] = (ref, None)
            else:
                raise ValueError(
                    f"Vocabulary {self.name!r} value {value!r} binds to {ref!r}: "
                    "expected a core-role name (str) or a Role"
                )

        # Two values binding the same app-role name to different styles is a
        # conflict — catch it here, at declaration.
        _merge_roles(app_roles)

        object.__setattr__(self, "roles", MappingProxyType(dict(self.roles)))
        object.__setattr__(self, "_binding", MappingProxyType(binding))
        object.__setattr__(self, "_app_roles", tuple(app_roles))

    def index(self, value: str) -> int:
        """Declaration-order index of ``value``. Requires ``ordered=True``."""
        self._require_ordered("index")
        return self._checked_index(value)

    def at_least(self, value: str) -> tuple[str, ...]:
        """The declaration-order tail from ``value`` onward, inclusive.

        Requires ``ordered=True``. Independent of ``attention`` — this is set
        membership ("everything this severe or worse"), not gutter emphasis.
        """
        self._require_ordered("at_least")
        return self.values[self._checked_index(value) :]

    def cmp(self, a: str, b: str) -> int:
        """Sign of ``index(a) - index(b)``. Requires ``ordered=True``."""
        self._require_ordered("cmp")
        ia = self._checked_index(a)
        ib = self._checked_index(b)
        return (ia > ib) - (ia < ib)

    def _require_ordered(self, op: str) -> None:
        if not self.ordered:
            raise ValueError(f"{op} requires an ordered vocabulary; {self.name!r} is unordered")

    def _checked_index(self, value: str) -> int:
        try:
            return self.values.index(value)
        except ValueError:
            raise ValueError(f"{value!r} is not a member of vocabulary {self.name!r}") from None


@dataclass(frozen=True)
class Thresholds:
    """A mapping from a numeric domain onto an ordered vocabulary's values.

    Generalizes ``DEFAULT_THRESHOLDS`` (levelno floors → severity): a value
    resolves to the vocabulary value of the greatest floor it clears. Below all
    floors, it resolves to the value of the numerically smallest floor (there is
    no quieter rung to fall to). The vocabulary must be ordered — thresholds are
    a comparative behavior — and every mapped value must be a member.
    """

    vocabulary: Vocabulary
    floors: Mapping[float, str]

    def __post_init__(self) -> None:
        if not self.vocabulary.ordered:
            raise ValueError(
                f"Thresholds requires an ordered vocabulary; {self.vocabulary.name!r} is unordered"
            )
        if not self.floors:
            raise ValueError("Thresholds declares no floors")
        for floor, value in self.floors.items():
            if value not in self.vocabulary.values:
                raise ValueError(
                    f"Threshold floor {floor!r} maps to {value!r}, not a member "
                    f"of vocabulary {self.vocabulary.name!r}"
                )
        object.__setattr__(self, "floors", MappingProxyType(dict(self.floors)))

    def resolve(self, value: float) -> str:
        """The vocabulary value of the greatest floor ``value`` clears."""
        best_floor: float | None = None
        best: str | None = None
        for floor, mapped in self.floors.items():
            if value >= floor and (best_floor is None or floor > best_floor):
                best_floor = floor
                best = mapped
        if best is None:
            # Below every floor: fall to the value of the smallest floor.
            return self.floors[min(self.floors)]
        return best


def _merge_roles(roles: Iterable[Role]) -> dict[str, Role]:
    """Fold roles into a name→Role map, raising on a conflicting redeclaration.

    Same name, identical style → idempotent-OK (frozen equality). Same name,
    different style → raise. Shared by ``Vocabulary.__post_init__`` (within one
    vocabulary) and ``_build_registry`` (across all active vocabularies).
    """
    merged: dict[str, Role] = {}
    for role in roles:
        existing = merged.get(role.name)
        if existing is not None and existing != role:
            raise ValueError(
                f"Role {role.name!r} is redeclared with a different style; a role "
                "is declared once and referenced by name after"
            )
        merged[role.name] = role
    return merged


# The single immutable "nothing set" value, shared as the ContextVar default and
# reset target for both ambient channels below. A bare ``{}`` default would hand
# every context the same *mutable* dict — the one uncopied mapping — so use one
# frozen empty proxy instead; the setters already store immutable proxies.
_EMPTY: Mapping[str, Any] = MappingProxyType({})


# --- Two-layer registry: built-in (immutable) + app (replaceable) ------------
# Severity is the built-in mark vocabulary and declared vocabularies EXTEND it —
# the depth-vs-Tag pattern repeating. The built-in layer is empty until slice 2
# fills it with Vocabulary("severity", ...); it exists from day one so an app's
# use_vocabularies REPLACES the app layer WITHOUT wiping the built-ins.

_BUILTIN_VOCABULARIES: Mapping[str, Vocabulary] = MappingProxyType({})

_vocabularies: ContextVar[Mapping[str, Vocabulary]] = ContextVar("vocabularies", default=_EMPTY)


class _VocabulariesOverride(AbstractContextManager[None]):
    def __init__(self, token: Token[Mapping[str, Vocabulary]]) -> None:
        self._token = token
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            _vocabularies.reset(self._token)
            self._active = False
        return False


def _build_registry(vocabs: tuple[Vocabulary, ...]) -> Mapping[str, Vocabulary]:
    """Validate and freeze the app-layer registry from the passed vocabularies.

    Raises on a duplicate ``.name`` across the passed vocabularies, on a
    collision with a built-in name (apps re-tint built-ins via ``Theme(roles=)``,
    never by redeclaration), and on a role declared with conflicting styles
    across them.
    """
    registry: dict[str, Vocabulary] = {}
    app_roles: list[Role] = []
    for vocab in vocabs:
        if vocab.name in registry:
            raise ValueError(f"Vocabulary {vocab.name!r} is declared twice")
        if vocab.name in _BUILTIN_VOCABULARIES:
            raise ValueError(
                f"Vocabulary {vocab.name!r} collides with a built-in vocabulary; "
                "re-tint a built-in via Theme(roles=...), do not redeclare it"
            )
        registry[vocab.name] = vocab
        app_roles.extend(vocab._app_roles)
    _merge_roles(app_roles)
    return MappingProxyType(registry)


def current_vocabularies() -> Mapping[str, Vocabulary]:
    """The active vocabularies — the app layer merged over the built-in layer.

    An app vocabulary cannot shadow a built-in (that collision raises at
    ``use_vocabularies``), so the merge is conflict-free.
    """
    merged = dict(_BUILTIN_VOCABULARIES)
    merged.update(_vocabularies.get())
    return MappingProxyType(merged)


def use_vocabularies(*vocabs: Vocabulary) -> AbstractContextManager[None]:
    """Declare vocabularies for the current context — the app-layer setter.

    REPLACES the app layer (it does not accumulate): the passed vocabularies
    become the active app layer, over the always-present built-in layer. Set
    immediately (setter semantics); the return value is also a scoped context
    manager:

        use_vocabularies(FRESHNESS, KIND)  # ambient until replaced

        with use_vocabularies(FRESHNESS):
            ...  # app layer restored on exit

    Name collisions across the passed vocabularies raise, as does a collision
    with a built-in name.
    """
    registry = _build_registry(vocabs)
    token = _vocabularies.set(registry)
    return _VocabulariesOverride(token)


def reset_vocabularies() -> None:
    """Clear the app layer back to empty (the built-in layer is untouched)."""
    _vocabularies.set(_EMPTY)


# --- Role-override channel (public-named, unexported) -------------------------
# The internal seam a Theme drives via Theme(roles=...). Not exported: the public
# path to re-tinting a role is Theme(roles=...), not this ContextVar (design doc
# D4). mark_style consults it first, so a theme override beats a declared Role.

_role_overrides: ContextVar[Mapping[str, Style]] = ContextVar("role_overrides", default=_EMPTY)


class _RoleOverridesOverride(AbstractContextManager[None]):
    def __init__(self, token: Token[Mapping[str, Style]]) -> None:
        self._token = token
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            _role_overrides.reset(self._token)
            self._active = False
        return False


def current_role_overrides() -> Mapping[str, Style]:
    """The active role→Style overrides (empty unless a Theme set them)."""
    return _role_overrides.get()


def use_role_overrides(overrides: Mapping[str, Style]) -> AbstractContextManager[None]:
    """Set the role-override channel — the internal seam Theme drives."""
    token = _role_overrides.set(MappingProxyType(dict(overrides)))
    return _RoleOverridesOverride(token)


def reset_role_overrides() -> None:
    """Clear all role overrides."""
    _role_overrides.set(_EMPTY)


# --- Resolution: the single point meaning becomes color ----------------------


def mark_style(vocab_name: str, value: str) -> Style:
    """Resolve a ``(vocabulary, value)`` mark to a ``Style``.

    Looks ``vocab_name`` up through the two-layer registry (app over built-in);
    an undeclared name raises (honesty rule 2). A value outside the vocabulary
    raises unless it declares ``overflow="series"``, in which case the value
    falls to the deterministic ``series`` ramp (honesty rule 3). The bound role
    resolves against the *current* palette and theme role-overrides, read at call
    time so ``use_theme`` re-tints marks without redeclaration.
    """
    vocab = _lookup_vocabulary(vocab_name)
    if value not in vocab.values:
        if vocab.overflow == "series":
            return current_palette().series_for(value)
        raise ValueError(
            f"{value!r} is not a member of vocabulary {vocab_name!r} "
            f'({list(vocab.values)!r}); declare overflow="series" to admit '
            "unknown values"
        )
    role_name, role = vocab._binding[value]
    return _role_style(role_name, role)


def _lookup_vocabulary(name: str) -> Vocabulary:
    app = _vocabularies.get()
    if name in app:
        return app[name]
    if name in _BUILTIN_VOCABULARIES:
        return _BUILTIN_VOCABULARIES[name]
    raise ValueError(
        f"No vocabulary named {name!r} is declared; declare it with "
        "use_vocabularies(Vocabulary(...)) before marking with it"
    )


def _role_style(role_name: str, role: Role | None) -> Style:
    """Resolve a bound role to a Style: override channel → core role → app role."""
    overrides = current_role_overrides()
    if role_name in overrides:
        return overrides[role_name]
    if role_name in CORE_ROLE_NAMES:
        style = getattr(current_palette(), role_name)
        # ``text`` is the only core role that may be None (no substrate fg set);
        # a value bound to it then means "unstyled" — a bare Style (design D5).
        return style if style is not None else Style()
    # An app role with no override in play: its declared style.
    assert role is not None  # a non-core role_name always carries its Role
    return role.style
