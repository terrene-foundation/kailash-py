"""
Control Protocol helper mixin for BaseAgent.

Extracts the three bidirectional user-interaction helpers from
``base_agent.py`` -- ``ask_user_question``, ``request_approval`` and
``report_progress``.

These are the agent's outbound half of the Control Protocol: an executing
agent pauses to ask the operator a question, to request approval before a
consequential action, or to stream a progress update. All three share one
precondition (a configured ``control_protocol``), one request type
(``ControlRequest``), and one failure mode (an error response is re-raised as
a ``RuntimeError`` naming the interaction that failed), which is what makes
them a unit rather than three neighbours.

Extracted from ``base_agent.py`` rather than inlined there: that module carries
two line-count guards (``tests/regression/test_loc_invariants.py`` and
``tests/unit/core/test_base_agent_slimming.py``) protecting it against
re-inlined code, and this cluster depends on exactly one piece of host state.

``ControlRequest`` is imported lazily inside each method, exactly as it was
inlined, so importing this module never pulls in ``kaizen.core.autonomy`` --
an agent that never speaks the Control Protocol pays nothing for it.

Uses duck typing -- the host class must provide:
- self.control_protocol: the Control Protocol transport, or None

Copyright 2026 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["ControlProtocolMixin"]


class ControlProtocolMixin:
    """Mixin providing Control Protocol interaction helpers for BaseAgent.

    Every method requires ``self.control_protocol`` to be configured and
    raises ``RuntimeError`` naming the missing wiring when it is not.
    """

    async def ask_user_question(
        self,
        question: str,
        options: Optional[List[str]] = None,
        timeout: float = 60.0,
    ) -> str:
        """Ask user a question during agent execution via Control Protocol."""
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__()"
            )

        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"question": question}
        if options:
            data["options"] = options

        request = ControlRequest.create("question", data)
        response = await self.control_protocol.send_request(request, timeout=timeout)

        if response.is_error:
            raise RuntimeError(f"Question error: {response.error}")

        return response.data.get("answer", "")

    async def request_approval(
        self,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> bool:
        """Request user approval for an action via Control Protocol."""
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__()"
            )

        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"action": action}
        if details:
            data["details"] = details

        request = ControlRequest.create("approval", data)
        response = await self.control_protocol.send_request(request, timeout=timeout)

        if response.is_error:
            raise RuntimeError(f"Approval error: {response.error}")

        return response.data.get("approved", False)

    async def report_progress(
        self,
        message: str,
        percentage: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Report progress update to user via Control Protocol."""
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__() "
                "to enable report_progress()."
            )

        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"message": message}
        if percentage is not None:
            if not (0.0 <= percentage <= 100.0):
                raise ValueError(
                    f"Percentage must be between 0.0 and 100.0, got {percentage}"
                )
            data["percentage"] = percentage
        if details:
            data["details"] = details

        request = ControlRequest.create("progress_update", data)
        await self.control_protocol._transport.write(request.to_json())
