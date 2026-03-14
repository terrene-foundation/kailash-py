# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP enforcement decorators for framework integration.

Provides 3-line integration decorators for adding EATP trust verification
and audit trails to any Python function or method.

Example:
    >>> from eatp.enforce.decorators import verified, audited
    >>>
    >>> @verified(agent_id="agent-001", action="read_data")
    ... async def read_sensitive_data(query: str) -> dict:
    ...     return await db.execute(query)
    >>>
    >>> @audited(agent_id="agent-001")
    ... async def process_data(data: dict) -> dict:
    ...     return transform(data)
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
from typing import Any, Callable, Optional, TypeVar, Union

from eatp.chain import VerificationLevel, VerificationResult
from eatp.enforce.shadow import ShadowEnforcer
from eatp.enforce.strict import HeldBehavior, StrictEnforcer, Verdict
from eatp.operations import TrustOperations

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a coroutine from a synchronous context.

    Handles the case where an event loop is already running (e.g., Jupyter,
    ASGI frameworks) by executing in a separate thread. Falls back to
    ``asyncio.run()`` when no loop is running.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)
    else:
        # Already inside a running loop — run in a thread to avoid
        # "cannot be called from a running event loop" error
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


def verified(
    agent_id: str,
    action: str,
    ops: Optional[TrustOperations] = None,
    level: VerificationLevel = VerificationLevel.STANDARD,
    on_held: HeldBehavior = HeldBehavior.RAISE,
) -> Callable[[F], F]:
    """Decorator that verifies EATP trust before function execution.

    Runs VERIFY before the decorated function. If verification fails,
    raises EATPBlockedError and the function is never called.

    Args:
        agent_id: The agent ID to verify
        action: The action name to verify against capabilities
        ops: TrustOperations instance (can be set later via set_ops)
        level: Verification thoroughness level
        on_held: Behavior when verification result is held

    Returns:
        Decorated function

    Example:
        >>> @verified(agent_id="agent-001", action="read_data")
        ... async def read_data():
        ...     return await fetch()
    """

    def decorator(func: F) -> F:
        _ops = ops
        enforcer = StrictEnforcer(on_held=on_held)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal _ops
            if _ops is None:
                raise RuntimeError(
                    "TrustOperations not configured. Pass ops= to @verified "
                    "or call set_ops() on the decorated function."
                )

            result = await _ops.verify(agent_id=agent_id, action=action, level=level)
            enforcer.enforce(agent_id=agent_id, action=action, result=result)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal _ops
            if _ops is None:
                raise RuntimeError(
                    "TrustOperations not configured. Pass ops= to @verified "
                    "or call set_ops() on the decorated function."
                )

            result = _run_coroutine_sync(
                _ops.verify(agent_id=agent_id, action=action, level=level)
            )
            enforcer.enforce(agent_id=agent_id, action=action, result=result)
            return func(*args, **kwargs)

        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        def set_ops(operations: TrustOperations) -> None:
            nonlocal _ops
            _ops = operations

        wrapper.set_ops = set_ops  # type: ignore[attr-defined]
        wrapper.enforcer = enforcer  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator


def audited(
    agent_id: str,
    ops: Optional[TrustOperations] = None,
) -> Callable[[F], F]:
    """Decorator that creates an audit trail after function execution.

    After the decorated function runs, creates an AUDIT anchor recording
    the action, arguments hash, and result hash.

    Args:
        agent_id: The agent ID for the audit record
        ops: TrustOperations instance (can be set later via set_ops)

    Returns:
        Decorated function

    Example:
        >>> @audited(agent_id="agent-001")
        ... async def process_data(data: dict) -> dict:
        ...     return transform(data)
    """

    def decorator(func: F) -> F:
        _ops = ops

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal _ops
            if _ops is None:
                raise RuntimeError(
                    "TrustOperations not configured. Pass ops= to @audited "
                    "or call set_ops() on the decorated function."
                )

            result = await func(*args, **kwargs)

            action = func.__qualname__
            args_hash = _hash_args(args, kwargs)
            result_hash = _hash_result(result)

            await _ops.audit(
                agent_id=agent_id,
                action=action,
                context_data={
                    "args_hash": args_hash,
                    "result_hash": result_hash,
                    "function": func.__qualname__,
                    "module": func.__module__,
                },
            )
            return result

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal _ops
            if _ops is None:
                raise RuntimeError(
                    "TrustOperations not configured. Pass ops= to @audited "
                    "or call set_ops() on the decorated function."
                )

            result = func(*args, **kwargs)

            action = func.__qualname__
            args_hash = _hash_args(args, kwargs)
            result_hash = _hash_result(result)

            _run_coroutine_sync(
                _ops.audit(
                    agent_id=agent_id,
                    action=action,
                    context_data={
                        "args_hash": args_hash,
                        "result_hash": result_hash,
                        "function": func.__qualname__,
                        "module": func.__module__,
                    },
                )
            )
            return result

        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        def set_ops(operations: TrustOperations) -> None:
            nonlocal _ops
            _ops = operations

        wrapper.set_ops = set_ops  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator


def shadow(
    agent_id: str,
    action: str,
    ops: Optional[TrustOperations] = None,
    level: VerificationLevel = VerificationLevel.STANDARD,
    shadow_enforcer: Optional[ShadowEnforcer] = None,
) -> Callable[[F], F]:
    """Decorator that runs EATP verification in shadow mode.

    Combines verified + shadow: logs verdicts without blocking execution.
    Use this during gradual rollout to observe what WOULD be blocked.

    Args:
        agent_id: The agent ID to verify
        action: The action name to verify
        ops: TrustOperations instance
        level: Verification thoroughness level
        shadow_enforcer: Optional shared ShadowEnforcer for metrics aggregation

    Returns:
        Decorated function

    Example:
        >>> @shadow(agent_id="agent-001", action="read_data")
        ... async def read_data():
        ...     return await fetch()
    """

    def decorator(func: F) -> F:
        _ops = ops
        _shadow = shadow_enforcer or ShadowEnforcer()

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal _ops
            if _ops is not None:
                try:
                    result = await _ops.verify(
                        agent_id=agent_id, action=action, level=level
                    )
                    _shadow.check(agent_id=agent_id, action=action, result=result)
                except Exception as e:
                    logger.warning(
                        f"[SHADOW] Verification error for agent={agent_id}: {e}"
                    )
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal _ops
            if _ops is not None:
                try:
                    result = _run_coroutine_sync(
                        _ops.verify(agent_id=agent_id, action=action, level=level)
                    )
                    _shadow.check(agent_id=agent_id, action=action, result=result)
                except Exception as e:
                    logger.warning(
                        f"[SHADOW] Verification error for agent={agent_id}: {e}"
                    )
            return func(*args, **kwargs)

        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        def set_ops(operations: TrustOperations) -> None:
            nonlocal _ops
            _ops = operations

        wrapper.set_ops = set_ops  # type: ignore[attr-defined]
        wrapper.shadow_enforcer = _shadow  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator


def _hash_args(args: tuple, kwargs: dict) -> str:
    """Create a deterministic hash of function arguments."""
    try:
        data = json.dumps({"args": repr(args), "kwargs": repr(kwargs)}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    except (TypeError, ValueError):
        return hashlib.sha256(repr((args, kwargs)).encode()).hexdigest()[:16]


def _hash_result(result: Any) -> str:
    """Create a deterministic hash of function result."""
    try:
        data = json.dumps(result, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    except (TypeError, ValueError):
        return hashlib.sha256(repr(result).encode()).hexdigest()[:16]


__all__ = [
    "verified",
    "audited",
    "shadow",
]
