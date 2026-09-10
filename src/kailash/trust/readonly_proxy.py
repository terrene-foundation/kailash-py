# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed, allowlist-gated read-only attribute proxies.

This module exists because the obvious way to write a read-only view in Python
is wrong in a way that is invisible on inspection.

Why ``__getattribute__`` and not ``__getattr__``
------------------------------------------------
``__getattr__`` is consulted ONLY when normal attribute lookup FAILS. A proxy
that stores its target in an instance attribute and guards with ``__getattr__``
therefore leaks the target itself::

    class Leaky:
        def __init__(self, target):
            self._target = target          # a real instance attribute
        def __getattr__(self, name):       # never consulted for "_target"
            if name in _BLOCKED:
                raise AttributeError(...)
            return getattr(self._target, name)

    view = Leaky(engine)
    view.grant_clearance(...)   # denied
    view._target.grant_clearance(...)   # ALLOWED -- the guard never ran

``view._target`` resolves through the normal path and hands the caller the very
object the proxy exists to contain, so every method behind the proxy is one
attribute access away no matter how long the guard's list is.
``__getattribute__`` is consulted for EVERY attribute access, so it is the only
correct enforcement point for a containment boundary.

Why an allowlist and not a blocklist
------------------------------------
A blocklist over a surface that someone else extends is fail-OPEN by
construction: every method added to the target after the list was written is
exposed by default, and nothing signals that the list has gone stale. An
allowlist inverts the default -- a newly added method on the target is denied
until a human classifies it.

Scope, stated honestly
----------------------
This is a containment boundary against ordinary attribute access, not a
sandbox. A caller who can execute arbitrary Python in the same process can
still reach the target via ``object.__getattribute__(proxy, "_target")`` or
``gc.get_referents``. That is a documented Python-level limitation and is not
what this class defends against; it defends against the target escaping through
a plain, innocent-looking attribute read.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["ReadOnlyProxyError", "ReadOnlyAttributeProxy"]

_DEFAULT_MESSAGE_TEMPLATE = "'{label}' does not expose '{name}'."


class ReadOnlyProxyError(AttributeError):
    """Typed denial raised by :class:`ReadOnlyAttributeProxy`.

    Subclasses :class:`AttributeError` so that ``hasattr()`` and ``getattr()``
    with a default keep their ordinary meaning, while remaining catchable as a
    distinct containment denial that names what was denied.

    Attributes:
        proxy_label: Human-readable name of the proxy that denied the access.
        attribute: The attribute name that was denied.
    """

    def __init__(self, proxy_label: str, attribute: str, message: str) -> None:
        self.proxy_label = proxy_label
        self.attribute = attribute
        super().__init__(message)


def _denial(proxy: Any, name: str) -> ReadOnlyProxyError:
    """Build the typed denial for ``name`` without re-entering the guard."""
    label = object.__getattribute__(proxy, "_label")
    overrides = object.__getattribute__(proxy, "_overrides")
    message = overrides.get(name)
    if message is None:
        template = object.__getattribute__(proxy, "_message_template")
        message = template.format(label=label, name=name)
    return ReadOnlyProxyError(label, name, message)


class ReadOnlyAttributeProxy:
    """Allowlist-gated, fail-closed read-only proxy around ``target``.

    Every attribute access is checked against ``allowed``. Anything else is
    denied -- including the proxy's own internals, ``__dict__``,
    ``__reduce_ex__`` (so the proxy cannot be pickled or copied into a handle on
    the target) and the wrapped target itself. Attribute assignment and deletion
    are denied unconditionally.

    Args:
        target: The object being wrapped. Never modified.
        allowed: The attribute names to proxy through. Every name must be a
            public identifier; a leading underscore is rejected at construction
            so an allowlist can never be used to expose internals.
        label: Human-readable proxy name used in denial messages and ``repr``.
            Defaults to ``"<TargetType> read-only view"``.
        message_template: Denial message format, with ``{label}`` and ``{name}``
            placeholders.
        overrides: Per-attribute full denial messages, for names that warrant a
            more specific explanation than the template.

    Raises:
        ValueError: If any allowlist entry is not a public identifier.
    """

    __slots__ = ("_target", "_allowed", "_label", "_message_template", "_overrides")

    def __init__(
        self,
        target: Any,
        allowed: Iterable[str],
        *,
        label: str | None = None,
        message_template: str = _DEFAULT_MESSAGE_TEMPLATE,
        overrides: Mapping[str, str] | None = None,
    ) -> None:
        allowed_set = frozenset(allowed)
        invalid = sorted(
            name
            for name in allowed_set
            if not isinstance(name, str)
            or not name.isidentifier()
            or name.startswith("_")
        )
        if invalid:
            raise ValueError(
                f"read-only proxy allowlist entries must be public identifiers; "
                f"rejected: {invalid}. An allowlist must never be able to expose "
                f"private or dunder attributes."
            )
        # object.__setattr__ because this class's own __setattr__ denies writes.
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_allowed", allowed_set)
        object.__setattr__(
            self, "_label", label or f"{type(target).__name__} read-only view"
        )
        object.__setattr__(self, "_message_template", message_template)
        object.__setattr__(self, "_overrides", dict(overrides or {}))

    def __getattribute__(self, name: str) -> Any:
        # __class__ is answered from the proxy itself so isinstance()/type
        # introspection keeps working; it exposes nothing about the target.
        if name == "__class__":
            return object.__getattribute__(self, "__class__")
        allowed = object.__getattribute__(self, "_allowed")
        if name in allowed:
            return getattr(object.__getattribute__(self, "_target"), name)
        raise _denial(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        label = object.__getattribute__(self, "_label")
        raise ReadOnlyProxyError(
            label,
            name,
            f"'{label}' is read-only; cannot set '{name}'.",
        )

    def __delattr__(self, name: str) -> None:
        label = object.__getattribute__(self, "_label")
        raise ReadOnlyProxyError(
            label,
            name,
            f"'{label}' is read-only; cannot delete '{name}'.",
        )

    def __repr__(self) -> str:
        label = object.__getattribute__(self, "_label")
        target = object.__getattribute__(self, "_target")
        return f"<{label} target={type(target).__name__}>"
