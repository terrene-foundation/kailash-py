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

Why an allowlisted method is not handed back as a bound method
--------------------------------------------------------------
Gating the NAME is not enough. ``getattr(target, "some_method")`` returns a
BOUND METHOD, and every bound method carries ``__self__`` -- the target. So a
proxy that returns bound methods leaks the target through any allowlisted
method in two plain attribute reads::

    view.list_roles.__self__            # -> the GovernanceEngine itself
    view.list_roles.__self__.grant_clearance(...)

That defeats the allowlist completely: the caller never touches a denied name.
Allowlisted callables are therefore returned as forwarding closures that hold
the proxy and the attribute name -- never the target.

Why the target is not stored in a readable slot
-----------------------------------------------
A ``__slots__`` entry installs a member descriptor on the CLASS, and the class
is always reachable (``type(x)`` reads the type pointer directly; no attribute
access on the instance is involved). So a slot holding the target is readable
through ``super(type(v), v)._target`` and through the descriptor itself. The
slot therefore holds a SEALED accessor: a closure that returns the target only
when handed this module's private token.

Scope, stated honestly
----------------------
This is a containment boundary against ordinary attribute access, not a
sandbox. A caller who can execute arbitrary Python in the same process can
still reach the target -- by digging the sealed accessor's ``__closure__``
cell, by reading this module's private token out of ``sys.modules``, or via
``gc.get_referents``. Those are documented Python-level limitations and are not
what this class defends against. What it does guarantee is that NO sequence of
ordinary attribute reads on the proxy -- including through an allowlisted
member's return value -- yields the target.

Known residual, deliberately NOT solved here
---------------------------------------------
This class contains the PROXY. It cannot make the target's own return values
safe: if an allowlisted method hands back a live mutable internal (a store's
own list, a config object whose list fields are still mutable), a caller can
mutate that object in place and change the target's behaviour without ever
touching a denied name. Closing that requires the TARGET to return snapshots or
immutable structures. See issue #2226.

Equally, it cannot close a route that never goes THROUGH the proxy -- a second
public accessor on the same facade that hands out the raw object. See #2227.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

__all__ = ["ReadOnlyProxyError", "ReadOnlyAttributeProxy"]

_DEFAULT_MESSAGE_TEMPLATE = "'{label}' does not expose '{name}'."

# Module-private sentinel. The sealed accessor in the proxy's slot returns the
# target ONLY when handed this exact object, so reading the slot (via the class
# descriptor or super()) yields an accessor that refuses to open.
_ACCESS_TOKEN = object()


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


def _seal(target: Any) -> Callable[[Any], Any]:
    """Wrap ``target`` so only a holder of ``_ACCESS_TOKEN`` can open it.

    This is what the proxy's slot holds, so reading the slot -- through the
    class's member descriptor, or through ``super()`` -- yields this function
    rather than the target.
    """

    def _unseal(token: Any) -> Any:
        if token is not _ACCESS_TOKEN:
            raise ReadOnlyProxyError(
                "<sealed>",
                "_target",
                "the wrapped target is sealed and cannot be opened from outside "
                "kailash.trust.readonly_proxy.",
            )
        return target

    return _unseal


def _target_of(proxy: Any) -> Any:
    """Open the sealed target. Module-internal; never exposed on the proxy."""
    return object.__getattribute__(proxy, "_target")(_ACCESS_TOKEN)


def _forwarder(proxy: Any, name: str) -> Callable[..., Any]:
    """Return a callable that forwards to ``target.name`` on each call.

    Deliberately closes over the PROXY and the NAME, never over the target or a
    bound method of it -- so the returned function's ``__closure__`` holds
    nothing that leads to the target except through the sealed accessor.
    """

    def _call(*args: Any, **kwargs: Any) -> Any:
        return getattr(_target_of(proxy), name)(*args, **kwargs)

    _call.__name__ = name
    _call.__qualname__ = f"{object.__getattribute__(proxy, '_label')}.{name}"
    _call.__doc__ = (
        f"Read-only forwarder for '{name}'. The underlying bound method is not "
        f"returned, because its __self__ would expose the wrapped object."
    )
    return _call


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
        # __init__ writes through object.__setattr__, which __setattr__ cannot
        # police -- so re-invoking it (type(v).__init__(v, ...)) would otherwise
        # widen the allowlist of a live proxy in place, including one another
        # component is holding. Refuse a second initialisation.
        try:
            object.__getattribute__(self, "_target")
        except AttributeError:
            pass
        else:
            raise ReadOnlyProxyError(
                "ReadOnlyAttributeProxy",
                "__init__",
                "this read-only proxy is already initialised; re-initialising "
                "would rebind its target and widen its allowlist in place.",
            )
        # object.__setattr__ because this class's own __setattr__ denies writes.
        object.__setattr__(self, "_target", _seal(target))
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
        if name not in allowed:
            raise _denial(self, name)
        value = getattr(_target_of(self), name)
        if callable(value):
            # NEVER return the bound method itself: its __self__ is the target.
            return _forwarder(self, name)
        return value

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

    @staticmethod
    def _repr_detail(target: Any) -> str:
        """Extra repr text for a subclass. Receives the target directly.

        A hook rather than a ``__repr__`` override, so a subclass never needs
        its own route to the sealed target. Looked up on the CLASS by
        ``__repr__`` below, so it is not reachable as ``proxy._repr_detail``.
        """
        return ""

    def __repr__(self) -> str:
        label = object.__getattribute__(self, "_label")
        detail = type(self)._repr_detail(_target_of(self))
        return f"<{label}{detail}>"
