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

    @property
    def inner(self) -> BaseAgent:
        """Access the wrapped inner agent."""
        return self._inner

    @property
    def innermost(self) -> BaseAgent:
        """Walk the wrapper stack to find the innermost (non-wrapper) agent."""
        current = self._inner
        while isinstance(current, WrapperBase):
            current = current._inner
        return current
