"""Derive an MCP ``inputSchema`` from a callable's signature.

WHY THIS EXISTS
---------------
``tools/list`` advertises each tool's ``inputSchema`` so a client can discover
what arguments to send. ``MCPServer.tool()`` previously stored no input schema
at all, so ``_handle_list_tools`` fell through to ``info.get("input_schema", {})``
and EVERY tool — including fully type-annotated ones — was advertised as taking
no discoverable arguments. A client had no protocol-level way to learn a tool's
parameters; it had to already know them.

That is also why a ``**kwargs``-only tool function was rejected outright by
strict MCP implementations (independent ``fastmcp``): there is nothing in the
signature to describe, so the tool cannot be advertised honestly. Deriving the
schema here fixes both halves — typed signatures get real properties, and an
open ``**kwargs`` signature gets an HONEST open schema
(``additionalProperties: true``) rather than a silently empty one.

DESIGN NOTE — honesty over precision
------------------------------------
An annotation this module cannot map is emitted as ``{}`` (no constraint)
rather than guessed at. An unconstrained property is truthful; a wrong ``type``
makes a client reject arguments the tool would have accepted. The same
principle governs ``**kwargs``: ``additionalProperties: true`` says "further
arguments are accepted and I cannot enumerate them", which is exactly true.
"""

from __future__ import annotations

import inspect
import logging
import typing
from typing import Any, Callable, Dict, Literal, Union, get_args, get_origin

logger = logging.getLogger(__name__)

# Direct Python -> JSON Schema primitive mappings.
_PRIMITIVES: Dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}

# Parameter kinds that cannot appear as named arguments in an MCP
# ``tools/call`` ``arguments`` object.
#
# POSITIONAL_ONLY is here for correctness, not tidiness: a positional-only
# parameter CANNOT be supplied by name, so advertising it as a schema property
# would tell a client to send an argument the callable will reject. Mostly this
# affects builtins and C functions; a tool defined with a normal ``def`` has no
# positional-only parameters unless it opts in with ``/``.
_SKIPPED_KINDS = frozenset(
    {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.POSITIONAL_ONLY}
)

_SELF_NAMES = frozenset({"self", "cls"})


def _is_optional(annotation: Any) -> bool:
    """True when ``annotation`` is ``Optional[X]`` / ``X | None``."""
    if get_origin(annotation) is Union:
        return type(None) in get_args(annotation)
    # PEP 604 unions (``int | None``) surface as types.UnionType on 3.10+.
    return type(None) in get_args(annotation) if get_args(annotation) else False


def _strip_none(annotation: Any) -> Any:
    """Return ``X`` from ``Optional[X]``; unchanged otherwise.

    Multi-member unions (``int | str | None``) collapse to no constraint —
    see the honesty note in the module docstring.
    """
    args = [a for a in get_args(annotation) if a is not type(None)]
    return args[0] if len(args) == 1 else Any


def json_type_for(annotation: Any) -> Dict[str, Any]:
    """Map a Python annotation to a JSON Schema fragment.

    Returns ``{}`` (no constraint) for anything unmappable, deliberately —
    see the module docstring.
    """
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}

    if _is_optional(annotation):
        annotation = _strip_none(annotation)
        if annotation is Any:
            return {}

    if annotation in _PRIMITIVES:
        # bool before int matters at the mapping level, not here: dict lookup
        # is exact, and bool is its own key.
        return {"type": _PRIMITIVES[annotation]}

    origin = get_origin(annotation)

    if origin is Literal:
        choices = list(get_args(annotation))
        frag: Dict[str, Any] = {"enum": choices}
        types = {_PRIMITIVES.get(type(c)) for c in choices}
        if len(types) == 1 and None not in types:
            frag["type"] = types.pop()
        return frag

    if annotation in (list, tuple, set) or origin in (list, tuple, set):
        args = get_args(annotation)
        items = json_type_for(args[0]) if args else {}
        return {"type": "array", "items": items} if items else {"type": "array"}

    if annotation is dict or origin is dict:
        return {"type": "object"}

    # Unmappable (custom classes, protocols, forward refs that did not
    # resolve). No constraint is the truthful answer.
    return {}


def build_input_schema(func: Callable[..., Any]) -> Dict[str, Any]:
    """Build an MCP ``inputSchema`` object for ``func``.

    Args:
        func: The tool callable to introspect.

    Returns:
        A JSON Schema ``object`` with ``properties``, ``required``, and
        ``additionalProperties``. A signature that accepts ``**kwargs`` sets
        ``additionalProperties: true``; a closed signature sets it to ``false``
        so a client sending an unknown argument is told so rather than having
        it silently dropped.

    Never raises: a callable whose signature or type hints cannot be resolved
    yields the permissive open schema. A tool that registers is strictly better
    than a registration that fails on introspection.
    """
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):  # builtins, C functions, exotic callables
        logger.debug("input-schema: signature unavailable for %r", func)
        return {"type": "object", "properties": {}, "additionalProperties": True}

    # Resolved hints give us real types for ``from __future__ import
    # annotations`` modules, where raw annotations are strings. Fall back to
    # the raw annotations rather than failing.
    try:
        hints = typing.get_type_hints(func)
    except Exception:  # unresolvable forward ref — use what we have
        hints = getattr(func, "__annotations__", {}) or {}

    properties: Dict[str, Any] = {}
    required: list[str] = []
    accepts_extra = False

    for name, param in signature.parameters.items():
        if name in _SELF_NAMES or param.kind in _SKIPPED_KINDS:
            continue
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            accepts_extra = True
            continue

        annotation = hints.get(name, param.annotation)
        properties[name] = json_type_for(annotation)

        # Required = no default AND not Optional-typed. An Optional parameter
        # with no default is still technically required by Python, but every
        # MCP client treats a nullable argument as omittable, so declaring it
        # required produces spurious client-side validation failures.
        if param.default is inspect.Parameter.empty and not _is_optional(annotation):
            required.append(name)

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": accepts_extra,
    }
    if required:
        schema["required"] = required
    return schema
