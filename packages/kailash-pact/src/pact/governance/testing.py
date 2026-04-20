# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Test-only namespace for PACT governance testing utilities.

This module is intended for use in **test suites only** — production code
MUST NOT import from it. The utilities here drive deterministic probes
against a live ``PactEngine`` / ``GovernanceEngine`` without requiring an
LLM backend.

Surfaces:

- ``MockGovernedAgent`` — scripted tool-execution harness for exercising
  governance enforcement paths without an LLM.
- ``run_negative_drills`` — fail-CLOSED batch runner for negative
  governance probes (each drill MUST raise ``GovernanceHeldError`` to
  pass). Added in PR#7 of issue #567, replacing the rejected MLFP
  ``GovernanceDiagnostics.run_negative_drills`` facade with a test-only
  first-class helper.

MockGovernedAgent usage::

    @governed_tool("read", cost=0.0)
    def tool_read() -> str:
        return "read_result"

    @governed_tool("write", cost=10.0)
    def tool_write() -> str:
        return "write_result"

    mock = MockGovernedAgent(
        engine=engine,
        role_address="D1-R1-T1-R1",
        tools=[tool_read, tool_write],
        script=["read", "write", "read"],
    )
    results = mock.run()  # ["read_result", "write_result", "read_result"]

Governance is fully enforced: blocked actions raise GovernanceBlockedError,
held actions raise GovernanceHeldError. The script execution stops at the
first governance error (fail-fast).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence, Union, runtime_checkable

from kailash.trust.pact.agent import (
    GovernanceHeldError as _KailashGovernanceHeldError,
    PactGovernedAgent,
)
from kailash.trust.pact.config import TrustPostureLevel
from kailash.trust.pact.engine import GovernanceEngine

from pact.engine import GovernanceHeldError as _PactEngineGovernanceHeldError
from pact.governance.results import NegativeDrillResult

logger = logging.getLogger(__name__)

__all__ = [
    "MockGovernedAgent",
    "NegativeDrill",
    "NegativeDrillResult",
    "run_negative_drills",
]


class MockGovernedAgent:
    """Governed agent that executes tools deterministically without LLM.

    Wraps PactGovernedAgent with a scripted execution sequence.
    Tools are auto-registered from their @governed_tool metadata.

    Args:
        engine: The GovernanceEngine for verification.
        role_address: The D/T/R positional address for the agent.
        tools: List of @governed_tool decorated callables.
        script: Ordered list of action names to execute.
        posture: Trust posture level. Defaults to SUPERVISED.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        role_address: str,
        tools: list[Callable[..., Any]],
        script: list[str],
        posture: TrustPostureLevel = TrustPostureLevel.SUPERVISED,
    ) -> None:
        self._governed = PactGovernedAgent(
            engine=engine,
            role_address=role_address,
            posture=posture,
        )
        self._script = script
        self._tools: dict[str, Callable[..., Any]] = {}

        # Auto-register tools from their @governed_tool metadata
        for tool in tools:
            if hasattr(tool, "_governance_action"):
                action_name: str = tool._governance_action
                cost: float = getattr(tool, "_governance_cost", 0.0)
                resource: str | None = getattr(tool, "_governance_resource", None)
                self._governed.register_tool(
                    action_name,
                    cost=cost,
                    resource=resource,
                )
                self._tools[action_name] = tool
            else:
                logger.warning(
                    "Tool %r does not have @governed_tool metadata -- skipping",
                    tool,
                )

    def run(self) -> list[Any]:
        """Execute the scripted sequence through governance enforcement.

        Runs each action in the script in order. Actions whose tool name
        does not match any registered tool are silently skipped (the tool
        is simply not available in this agent's toolkit).

        Actions that ARE registered but violate governance will raise
        GovernanceBlockedError or GovernanceHeldError (fail-fast).

        Returns:
            List of results from each successfully executed tool.

        Raises:
            GovernanceBlockedError: If any action is blocked by governance.
            GovernanceHeldError: If any action is held for approval.
        """
        results: list[Any] = []
        for action in self._script:
            tool = self._tools.get(action)
            if tool is None:
                # Tool not in this agent's toolkit -- skip
                logger.debug(
                    "Action '%s' has no matching tool in MockGovernedAgent -- skipping",
                    action,
                )
                continue
            result = self._governed.execute_tool(action, _tool_fn=tool)
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# Negative governance drills (PR#7, issue #567)
# ---------------------------------------------------------------------------


@runtime_checkable
class _CallableProbe(Protocol):
    """A raw-callable drill shape: ``callable(engine) -> None``."""

    def __call__(self, engine: Any) -> None: ...


@dataclass(frozen=True)
class NegativeDrill:
    """A named negative governance drill.

    A drill is a deterministic probe that SHOULD be refused by the
    governance engine. Construct a drill either with the explicit
    dataclass form or pass a bare ``(name, callable)`` tuple to
    ``run_negative_drills``.

    Attributes:
        name: Stable identifier used for reporting + audit. Keep short
            and grep-able (e.g. ``"unauthorized_tool"``,
            ``"compartment_escalation"``).
        callable: A callable accepting a single positional argument — the
            ``PactEngine`` under test — and expected to raise
            ``GovernanceHeldError`` when governance correctly refuses
            the probed action.
    """

    name: str
    callable: _CallableProbe


#: Accepted drill input shapes. Either a :class:`NegativeDrill`, a bare
#: callable (drill name derived from ``callable.__name__``), or a
#: ``(name, callable)`` tuple.
_DrillInput = Union[
    NegativeDrill,
    _CallableProbe,
    tuple[str, _CallableProbe],
]


def _coerce_drill(item: _DrillInput) -> NegativeDrill:
    if isinstance(item, NegativeDrill):
        return item
    if isinstance(item, tuple):
        if len(item) != 2 or not isinstance(item[0], str):
            raise TypeError(
                "tuple drills must have shape (name: str, callable); " f"got {item!r}"
            )
        name, fn = item
        if not callable(fn):
            raise TypeError(f"drill callable must be callable; got {type(fn).__name__}")
        return NegativeDrill(name=name, callable=fn)
    if callable(item):
        name = getattr(item, "__name__", "anonymous_drill") or "anonymous_drill"
        return NegativeDrill(name=name, callable=item)
    raise TypeError(
        "drill must be NegativeDrill, (name, callable), or a callable; "
        f"got {type(item).__name__}"
    )


def run_negative_drills(
    engine: Any,
    drills: Sequence[_DrillInput],
    *,
    stop_at_first_failure: bool = False,
) -> list[NegativeDrillResult]:
    """Execute a sequence of negative governance drills against ``engine``.

    **Fail-CLOSED contract** (PACT MUST Rule 4):

    - A drill passes **only** if it raises
      :class:`GovernanceHeldError` — the engine correctly refused the
      probed action.
    - A drill that **returns normally** is a FAILURE: the engine
      permitted the action that governance should have held.
    - A drill that raises ANY OTHER exception type is a FAILURE: the
      probe did not complete its check. Exceptions from drills DO NOT
      mean "pass". This is the single most common misuse pattern for
      negative governance probes.

    Both ``kailash.trust.pact.agent.GovernanceHeldError`` and
    ``pact.engine.GovernanceHeldError`` are accepted as the "pass"
    exception type. The former fires inside ``PactGovernedAgent``; the
    latter fires inside ``PactEngine.submit``. Drills written against
    either surface behave identically.

    Args:
        engine: The :class:`PactEngine` (or compatible) under test. Passed
            as the single positional argument to each drill callable.
        drills: Ordered sequence of drills. Each element may be a
            :class:`NegativeDrill`, a bare callable (name derived from
            ``__name__``), or a ``(name, callable)`` tuple.
        stop_at_first_failure: When ``True``, the runner short-circuits
            at the first failure. The returned list contains only drills
            that were actually executed.

    Returns:
        Ordered list of :class:`NegativeDrillResult` — one per drill
        executed. ``passed=True`` means the engine held the action.
    """
    held_types: tuple[type[BaseException], ...] = (
        _KailashGovernanceHeldError,
        _PactEngineGovernanceHeldError,
    )

    results: list[NegativeDrillResult] = []
    for raw in drills:
        drill = _coerce_drill(raw)
        try:
            drill.callable(engine)
        except held_types as exc:
            results.append(
                NegativeDrillResult(
                    drill_name=drill.name,
                    passed=True,
                    reason=(
                        f"engine held action as expected: {exc!r}"
                        if str(exc)
                        else "engine raised GovernanceHeldError as expected"
                    ),
                    exception_type=type(exc).__name__,
                )
            )
            logger.info(
                "negative_drill.passed",
                extra={"drill_name": drill.name, "exc_type": type(exc).__name__},
            )
            continue
        except Exception as exc:
            results.append(
                NegativeDrillResult(
                    drill_name=drill.name,
                    passed=False,
                    reason=(
                        "drill raised unexpected exception type "
                        f"{type(exc).__name__}: {exc!r} — expected "
                        "GovernanceHeldError"
                    ),
                    exception_type=type(exc).__name__,
                )
            )
            logger.warning(
                "negative_drill.unexpected_exception",
                extra={
                    "drill_name": drill.name,
                    "exc_type": type(exc).__name__,
                },
            )
            if stop_at_first_failure:
                break
            continue

        results.append(
            NegativeDrillResult(
                drill_name=drill.name,
                passed=False,
                reason=(
                    "drill returned normally — engine permitted the action "
                    "that governance should have refused"
                ),
                exception_type=None,
            )
        )
        logger.warning(
            "negative_drill.not_refused",
            extra={"drill_name": drill.name},
        )
        if stop_at_first_failure:
            break

    return results
