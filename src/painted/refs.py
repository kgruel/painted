"""Refs: the denotation channel — a ref becomes a URI through a declaration.

A **ref** is an opaque per-cell string annotation — denotation, never behavior:
"what does this cell *refer to*?" and nothing else. painted moves refs through
every Block operation and hands them to deliveries; it never interprets them
beyond the resolver seam here. A ref optionally carries a scheme,
``"scheme:value"``, split on the first colon: ``"fact:01JQ8F…"`` has scheme
``fact``; ``"sidebar"`` has no scheme. Scheme-less refs are the hit-testing idiom
and stay fully supported — they are simply inert in link deliveries (a button
target is not a URL).

``RefScheme`` is the declaration a link delivery resolves a ref through: a name
(kebab-case) and a resolver ``Callable[[str], str | None]`` that receives the
ref's value part (after the colon) and returns a URI or ``None`` — ``None`` is a
legal "no URI for this one," which a bare template string cannot express. No
styling field, ever: link color is the delivery's concern (design doc §4).

The honesty rules (design doc §4): a declaration is validated at construction
(``DeclarationError`` on a bad name or a non-callable resolver — *validate every
declaration, tolerate all data*); an *undeclared* scheme is **inert**, not an
error, the one deliberate asymmetry with ``mark_style`` — a ref without a URI
still renders its content perfectly, so painted never invents URIs. A resolver
that raises propagates unwrapped: the resolver is app code, and ``PaintedError``
means "painted itself detected this" — wrapping would misattribute.

Registration mirrors ``use_palette``: ``use_refs`` is both an immediate setter and
a scoped context manager, REPLACE semantics. Single-layer ContextVar (like
``_palette``, unlike ``_vocabularies``): there is no built-in ref scheme the way
``severity`` is a built-in vocabulary, so no two-layer merge. Like all painted
ambient state it does not cross threads. Ref schemes generate no CLI flags — this
module imports neither ``painted.cli`` nor ``argparse`` (vocabularies rule 4).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from types import MappingProxyType

from .core.errors import DeclarationError

# Deliberate local duplicate of ``cli.types._DECLARED_NAME_RE`` (the same choice
# ``vocabulary.py`` makes). The kebab discipline is shared by *convention*, not
# import: a ref scheme names a denotation channel; it is not user grammar, and
# this module must not depend on ``cli``. Two spellings of one rule, kept in sync
# by review.
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class RefScheme:
    """A declared ref scheme: a kebab-case ``name`` and a ``resolve`` callable.

    ``resolve`` receives the value part of a ref (everything after the first
    colon) and returns a URI or ``None``. Validated at construction: a bad name
    shape or a non-callable resolver raises ``DeclarationError``.
    """

    name: str
    resolve: Callable[[str], str | None]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME_RE.match(self.name):
            raise DeclarationError(
                f"RefScheme name {self.name!r} must be lowercase kebab-case "
                "(it names a denotation scheme, like a role)"
            )
        if not callable(self.resolve):
            raise DeclarationError(
                f"RefScheme {self.name!r} resolver must be callable (a value -> URI|None function)"
            )


# The single immutable "nothing declared" value, shared as the ContextVar default
# and reset target. A bare ``{}`` default would hand every context the same
# *mutable* dict; use one frozen empty proxy instead (the ``vocabulary._EMPTY``
# precedent) — the setter already stores an immutable proxy.
_EMPTY: Mapping[str, RefScheme] = MappingProxyType({})

# Single-layer ambient registry (unlike vocabularies' two-layer built-in+app
# split): there is no built-in ref scheme, so there is nothing to merge over.
_ref_schemes: ContextVar[Mapping[str, RefScheme]] = ContextVar("ref_schemes", default=_EMPTY)


class _RefSchemesOverride(AbstractContextManager[None]):
    def __init__(self, token: Token[Mapping[str, RefScheme]]) -> None:
        self._token = token
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            _ref_schemes.reset(self._token)
            self._active = False
        return False


def _build_registry(schemes: tuple[RefScheme, ...]) -> Mapping[str, RefScheme]:
    """Validate and freeze the registry from the passed schemes.

    Raises on a duplicate ``.name`` across the passed schemes (each scheme's own
    field validation already ran at its construction).
    """
    registry: dict[str, RefScheme] = {}
    for scheme in schemes:
        if scheme.name in registry:
            raise DeclarationError(f"RefScheme {scheme.name!r} is declared twice")
        registry[scheme.name] = scheme
    return MappingProxyType(registry)


def current_ref_schemes() -> Mapping[str, RefScheme]:
    """The active ref schemes (empty unless ``use_refs`` declared some)."""
    return _ref_schemes.get()


def use_refs(*schemes: RefScheme) -> AbstractContextManager[None]:
    """Declare ref schemes for the current context — the setter.

    REPLACES the registry (it does not accumulate): the passed schemes become the
    active set. Set immediately (setter semantics); the return value is also a
    scoped context manager:

        use_refs(RefScheme("fact", resolve))  # ambient until replaced

        with use_refs(RefScheme("fact", resolve)):
            ...  # registry restored on exit

    Name collisions across the passed schemes raise ``DeclarationError``.
    """
    registry = _build_registry(schemes)
    token = _ref_schemes.set(registry)
    return _RefSchemesOverride(token)


def reset_refs() -> None:
    """Clear all declared ref schemes back to empty."""
    _ref_schemes.set(_EMPTY)


def resolve_ref(ref: str) -> str | None:
    """Resolve a ref to a URI, or ``None`` — the single link-delivery choke point.

    A ref with no scheme (no colon), or a scheme no ``RefScheme`` declares, is
    **inert**: ``None``, never an error. A declared scheme's resolver may itself
    decline with ``None``. A resolver that raises propagates unwrapped — the
    resolver is app code (design doc §4).
    """
    scheme, sep, value = ref.partition(":")
    if not sep:
        return None  # scheme-less → inert
    declared = current_ref_schemes().get(scheme)
    if declared is None:
        return None  # undeclared scheme → inert
    return declared.resolve(value)  # may itself decline with None
