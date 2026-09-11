# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""WrapperBase -- abstract base for composition wrappers.

Composition wrappers add cross-cutting concerns (governance, monitoring,
streaming) around an inner ``BaseAgent`` without modifying it.

Canonical stacking order::

    BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent

Invariants
----------
1. ``_inner`` is ALWAYS called (verified by ``_inner_called`` flag).
2. ``get_parameters()`` proxies to inner agent.
3. ``to_workflow()`` proxies to inner agent (StreamingAgent overrides).
4. ``isinstance(wrapper, BaseAgent)`` is True.
5. Stacking validates no duplicate wrapper types.

Containment: which accessor is a boundary
-----------------------------------------
``inner`` and ``innermost`` are the PUBLIC accessors and both honour a
wrapper's containment boundary (see :meth:`WrapperBase._containment_boundary`).
A wrapper that enforces a security boundary substitutes its protected proxy for
everything beneath it, so no public attribute read hands back an object that
executes ungoverned.

``_inner`` is NOT a containment boundary and does not claim to be. It is the
wrapper machinery's own link: every wrapper's ``run``/``run_async`` calls
through it, ``_collect_wrapper_types`` walks it to validate stacking order,
``StreamingAgent`` walks it to resolve the model config and system prompt from
the base agent, and ``Delegate.core_agent`` walks it to expose the loop-agent
bridge. Substituting a proxy there would have to be done in all five places at
once and would change what those resolvers can read. A caller who reaches for
``wrapper._inner`` is reaching into private machinery, which Python does not
prevent and this module does not claim to -- the same honest scope statement
:mod:`kailash.trust.readonly_proxy` makes about its own boundary. Tracked as
the named residual of #2227 Route A.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)

__all__ = [
    "WrapperBase",
    "DuplicateWrapperError",
    "WrapperOrderError",
]

# Canonical wrapper stack priority (lower = more innermost).
# BaseAgent -> GovernedAgent -> MonitoredAgent -> StreamingAgent.
# A wrapper cannot be applied on top of a wrapper with a HIGHER priority.
_WRAPPER_PRIORITY: dict[str, int] = {
    "L3GovernedAgent": 1,
    "GovernedAgent": 1,
    "MonitoredAgent": 2,
    "StreamingAgent": 3,
}


class DuplicateWrapperError(TypeError):
    """Raised when the same wrapper type is applied twice in the stack."""

    pass


class WrapperOrderError(TypeError):
    """Raised when wrappers are applied out of canonical order.

    Canonical order (innermost to outermost)::

        BaseAgent -> GovernedAgent -> MonitoredAgent -> StreamingAgent
    """

    pass


def _collect_wrapper_types(agent: BaseAgent) -> list[type]:
    """Walk the wrapper stack and collect all wrapper types."""
    types: list[type] = []
    current = agent
    while isinstance(current, WrapperBase):
        types.append(type(current))
        current = current._inner
    return types


class WrapperBase(BaseAgent):
    """Abstract base for composition wrappers.

    Holds an ``_inner`` agent and proxies core methods (``get_parameters``,
    ``to_workflow``) to it.  Subclasses override ``run_async`` to add
    behaviour around the inner agent's execution.

    Parameters
    ----------
    inner:
        The agent to wrap.  Must be a ``BaseAgent`` instance.
    **kwargs:
        Passed through to ``BaseAgent.__init__`` (typically unused by
        wrappers, but needed for cooperative multiple inheritance).
    """

    def __init__(self, inner: BaseAgent, **kwargs: Any) -> None:
        if not isinstance(inner, BaseAgent):
            raise TypeError(
                f"WrapperBase requires a BaseAgent instance, got {type(inner).__name__}"
            )

        # Validate no duplicate wrappers in the stack
        existing_types = _collect_wrapper_types(inner)
        self_type = type(self)
        if self_type in existing_types:
            raise DuplicateWrapperError(
                f"Wrapper {self_type.__name__} is already present in the stack. "
                f"Current stack: {[t.__name__ for t in existing_types]}"
            )

        # Validate canonical stack ordering: a wrapper cannot be applied on top
        # of a wrapper with a higher priority (more outermost) than itself.
        self_priority = _WRAPPER_PRIORITY.get(self_type.__name__)
        if self_priority is not None:
            for existing in existing_types:
                existing_priority = _WRAPPER_PRIORITY.get(existing.__name__)
                if existing_priority is not None and existing_priority >= self_priority:
                    raise WrapperOrderError(
                        f"Cannot apply {self_type.__name__} on top of "
                        f"{existing.__name__}. Canonical order (innermost to "
                        f"outermost): BaseAgent -> GovernedAgent -> "
                        f"MonitoredAgent -> StreamingAgent. "
                        f"Current stack (innermost first): "
                        f"{[t.__name__ for t in reversed(existing_types)]}"
                    )

        self._inner = inner
        self._inner_called = False

        # Initialise BaseAgent with the inner agent's config and signature
        # so that isinstance checks and attribute access work correctly.
        super().__init__(
            config=inner.config,
            signature=inner.signature,
        )

    def get_parameters(self) -> dict[str, Any]:
        """Proxy to inner agent's parameters."""
        return self._inner.get_parameters()

    def to_workflow(self) -> Any:
        """Proxy to inner agent's workflow conversion."""
        return self._inner.to_workflow()

    def run(self, **inputs: Any) -> dict[str, Any]:
        """Synchronous execution -- delegates to inner agent.

        Subclasses that need synchronous interception should override this
        method, call ``self._inner.run(**inputs)``, and set
        ``self._inner_called = True``.
        """
        self._inner_called = True
        return self._inner.run(**inputs)

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        """Asynchronous execution -- delegates to inner agent.

        Subclasses override this to add behaviour (governance checks,
        cost tracking, streaming) around the inner agent's execution.
        """
        self._inner_called = True
        return await self._inner.run_async(**inputs)

    def _containment_boundary(self) -> Any | None:
        """The object this wrapper substitutes for everything beneath it.

        Returns ``None`` for an ordinary wrapper, which adds a cross-cutting
        concern but claims no authority over what it wraps. A wrapper that
        enforces a security boundary -- ``L3GovernedAgent`` is the only one
        today -- overrides this to return its protected proxy, which makes
        :attr:`innermost` stop there instead of walking past it.

        A hook rather than an ``isinstance`` check in :attr:`innermost`, so
        ``wrapper_base`` does not have to import the governance module (which
        imports it), and so any future enforcing wrapper is covered without
        editing this file.
        """
        return None

    @property
    def inner(self) -> BaseAgent:
        """Access the wrapped inner agent."""
        return self._inner

    @property
    def innermost(self) -> Any:
        """The innermost agent, or the containment boundary that stands for it.

        Walks the stack and returns the first non-wrapper agent -- UNLESS some
        wrapper along the way declares a containment boundary
        (:meth:`_containment_boundary`), in which case that boundary is
        returned and the walk stops there.

        Why the walk stops (#2227 Route A)
        ----------------------------------
        ``L3GovernedAgent`` overrides ``inner`` to return a
        ``_ProtectedInnerProxy``, but this property is defined HERE and walked
        the private ``_inner`` chain, so it reached straight past that proxy to
        the raw agent::

            governed.innermost.run(query="...")   # ungoverned execution

        Overriding ``innermost`` on ``L3GovernedAgent`` alone would NOT have
        fixed it: for a stacked ``StreamingAgent(MonitoredAgent(governed))``
        the walk starts at the outermost wrapper and never consults any
        intermediate wrapper's ``innermost``. The boundary has to be honoured
        by the walk itself, which is what this does -- ``streaming.innermost``,
        ``monitored.innermost`` and ``governed.innermost`` now all stop at the
        same proxy.

        The boundary object is returned rather than raising, because the
        legitimate consumers of ``innermost`` want the inner agent's ``config``
        and ``signature`` (streaming resolves its model from them) and the
        proxy still serves those. What it refuses is ``run``/``run_async``.

        Note: this is the PUBLIC accessor and is the containment boundary.
        ``_inner`` is private wrapper machinery -- every wrapper's execution
        path, the stack-order validator, the streaming config resolver and the
        delegate facade all traverse it -- and is NOT a containment boundary.
        See the module docstring.

        Returns:
            The innermost non-wrapper ``BaseAgent``, or the containment
            boundary object of the innermost enforcing wrapper.
        """
        current: Any = self
        while isinstance(current, WrapperBase):
            boundary = current._containment_boundary()
            if boundary is not None:
                return boundary
            current = current._inner
        return current
