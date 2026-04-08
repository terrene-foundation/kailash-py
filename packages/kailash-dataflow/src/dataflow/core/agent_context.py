# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Agent context propagation for trust-aware query execution.

Provides a process-wide ``contextvars.ContextVar`` that carries the
current agent identity across the Express and Workflow query paths.

DataFlow's trust subsystem (CARE-019/020/021) needs to know *which*
agent is issuing a query so constraints, audit records, and cross-tenant
delegations can be resolved. Rather than threading ``agent_id`` through
every Express method signature (breaking change), we mirror the
``tenant_context.py`` pattern and expose a scoped context manager.

Typical usage::

    from dataflow.core.agent_context import agent_context

    async with agent_context("agent-001"):
        user = await db.express.read("User", "u1")   # trust-aware
        users = await db.express.list("User", ...)   # trust-aware

When no agent context is set, ``get_current_agent_id()`` returns ``None``
and the trust-aware query path treats the call as a system-level request
(no per-agent constraint lookup, no per-agent audit attribution).

This module is intentionally dependency-free — it does not import
from ``dataflow.trust`` so it can be used by the core engine and the
trust subsystem without creating a cycle.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from dataflow.classification.types import DataClassification

logger = logging.getLogger(__name__)

__all__ = [
    "get_current_agent_id",
    "set_current_agent_id",
    "agent_context",
    "async_agent_context",
    "get_current_clearance",
    "set_current_clearance",
    "clearance_context",
    "async_clearance_context",
]

# Thread- and async-safe context variable for the current agent.
_current_agent: ContextVar[Optional[str]] = ContextVar("_current_agent", default=None)

# Thread- and async-safe context variable for the current caller's data
# clearance level (Phase 5.10). The value is a
# ``dataflow.classification.types.DataClassification`` enum; using the
# string type here keeps this module dependency-free and avoids a
# circular import with the classification package.
_current_clearance: ContextVar[Optional["DataClassification"]] = ContextVar(
    "_current_clearance", default=None
)


def get_current_agent_id() -> Optional[str]:
    """Return the agent ID bound to the current execution context.

    Returns:
        The current agent ID, or ``None`` when no agent context is active.
    """
    return _current_agent.get()


def set_current_agent_id(
    agent_id: Optional[str],
) -> Token[Optional[str]]:
    """Set the current agent ID and return the reset token.

    Low-level helper for integrations that manage the context variable
    directly (e.g., middleware binding an agent at request ingress).
    Prefer :func:`agent_context` or :func:`async_agent_context` for
    scoped usage so the token is restored automatically.

    Args:
        agent_id: The agent ID to bind. Pass ``None`` to clear.

    Returns:
        A ``contextvars.Token`` that can be used to reset the variable.
    """
    return _current_agent.set(agent_id)


@contextmanager
def agent_context(agent_id: Optional[str]):
    """Synchronous scoped agent context.

    Example::

        with agent_context("agent-001"):
            db.express_sync.read("User", "u1")

    The previous agent ID (if any) is restored on exit, even on exception.
    """
    token = _current_agent.set(agent_id)
    logger.debug("agent_context.enter", extra={"agent_id": agent_id})
    try:
        yield agent_id
    finally:
        _current_agent.reset(token)
        logger.debug("agent_context.exit", extra={"agent_id": agent_id})


@asynccontextmanager
async def async_agent_context(agent_id: Optional[str]):
    """Async scoped agent context.

    Example::

        async with async_agent_context("agent-001"):
            await db.express.read("User", "u1")

    The previous agent ID (if any) is restored on exit, even on exception.
    ``contextvars`` automatically propagate through ``asyncio`` tasks, so
    queries launched inside the block see the bound agent ID.
    """
    token = _current_agent.set(agent_id)
    logger.debug("async_agent_context.enter", extra={"agent_id": agent_id})
    try:
        yield agent_id
    finally:
        _current_agent.reset(token)
        logger.debug("async_agent_context.exit", extra={"agent_id": agent_id})


# ---------------------------------------------------------------------------
# Clearance context (Phase 5.10 — classification-aware masking)
# ---------------------------------------------------------------------------


def get_current_clearance() -> Optional["DataClassification"]:
    """Return the data-classification clearance bound to the current context.

    Returns ``None`` when no clearance has been set, which is treated by
    :mod:`dataflow.classification.policy` as the most restrictive
    (``PUBLIC``) clearance.
    """
    return _current_clearance.get()


def set_current_clearance(
    clearance: Optional["DataClassification"],
) -> Token[Optional["DataClassification"]]:
    """Set the current clearance and return the reset token.

    Low-level helper for integrations that manage the context variable
    directly. Prefer :func:`clearance_context` or
    :func:`async_clearance_context` for scoped usage.
    """
    return _current_clearance.set(clearance)


@contextmanager
def clearance_context(clearance: Optional["DataClassification"]):
    """Synchronous scoped clearance context.

    Example::

        from dataflow.classification import DataClassification

        with clearance_context(DataClassification.PII):
            user = db.express_sync.read("User", "u1")
    """
    token = _current_clearance.set(clearance)
    logger.debug(
        "clearance_context.enter",
        extra={"clearance": clearance.value if clearance is not None else None},
    )
    try:
        yield clearance
    finally:
        _current_clearance.reset(token)
        logger.debug(
            "clearance_context.exit",
            extra={"clearance": clearance.value if clearance is not None else None},
        )


@asynccontextmanager
async def async_clearance_context(clearance: Optional["DataClassification"]):
    """Async scoped clearance context.

    Example::

        async with async_clearance_context(DataClassification.PII):
            user = await db.express.read("User", "u1")
    """
    token = _current_clearance.set(clearance)
    logger.debug(
        "async_clearance_context.enter",
        extra={"clearance": clearance.value if clearance is not None else None},
    )
    try:
        yield clearance
    finally:
        _current_clearance.reset(token)
        logger.debug(
            "async_clearance_context.exit",
            extra={"clearance": clearance.value if clearance is not None else None},
        )
