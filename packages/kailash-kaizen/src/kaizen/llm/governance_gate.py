# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Kaizen-side enforcement of the core ``governance_required`` posture (#1779).

Framework-first layering: core ``kailash`` (PACT) owns the posture STATE
(``kailash.is_governance_required``) + the typed error
(``kailash.trust.pact.UngovernedEgressRefused``); Kaizen owns the LLM client
and AGENT and performs the ENFORCEMENT here — it reads the posture at
construction (and, defense-in-depth, at real-transport binding) and refuses a
bare un-governed client/agent that would make real egress.

Exemptions (any one short-circuits the refusal):

* ``ungoverned=True`` — the caller's explicit opt-out.
* mock / deterministic — a mock-preset deployment (``preset_name == "mock"``)
  or an ``Agent(llm_provider="mock")``; also an injected mock transport
  (marked ``is_mock_transport``) at the lazy binding check.
* the posture is OFF (default) — byte-identical to pre-#1779 behaviour.

NO interceptor-presence exemption. The four-axis ``LlmClient`` does NOT route
its egress through the process-global outbound interceptor (``embed`` /
``complete`` / ``stream`` call ``http_client.post`` directly), so a merely
INSTALLED interceptor does NOT govern this client's egress — exempting on
``active_interceptor() is not None`` would be FAIL-OPEN (it would waive the
refusal without the egress actually being governed). Wiring the four-axis
client into the outbound seam is a separate follow-up (the #1517 seam applied
to ``LlmClient``); until then the only opt-out is ``ungoverned=True``, and the
governed path is the legacy ``GovernedProvider`` wrapper (which genuinely wraps
egress). Removing this exemption is the #1779 redteam CRITICAL fix.

Fail-closed (invariant 5): if the posture reader errors, treat the posture as
ACTIVE — refuse rather than silently allow ungoverned egress.

All ``kailash`` imports are function-local: the module is imported by the LLM
client + agent hot path, and a module-scope ``import kailash`` would add a
load-time kaizen→kailash edge and pull the PACT package into every client
construction. The lazy import hits ``sys.modules`` after the first call.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "enforce_governance_posture",
    "is_mock_deployment",
]

# The construction-time mock discriminator: ``mock_preset()`` (in the test-only
# transport package) is the only deployment factory that sets
# ``preset_name="mock"``. Real presets set their own literal; manual
# constructions leave it ``None``.
_MOCK_PRESET_NAME = "mock"


def is_mock_deployment(deployment: Any) -> bool:
    """Return True iff ``deployment`` is a mock/deterministic deployment.

    Keyed on ``preset_name == "mock"`` — a pure attribute read, never a probe
    (invariant 3: exempt by class/flag identity, never a network call).
    Fail-closed (invariant 5): any error reading the attribute is treated as
    NOT mock (i.e. real) so an undecidable deployment is gated, not exempted.
    """
    try:
        return getattr(deployment, "preset_name", None) == _MOCK_PRESET_NAME
    except Exception:  # pragma: no cover - defensive; getattr on odd objects
        return False


def enforce_governance_posture(
    *,
    is_mock: bool,
    ungoverned: bool,
    surface: str,
) -> None:
    """Refuse if the ``governance_required`` posture is active and this
    construction/egress would be a real, un-governed LLM call.

    Args:
        is_mock: caller-computed mock discriminator (``is_mock_deployment(dep)``
            for the client; ``llm_provider == "mock"`` for the agent).
        ungoverned: the caller's explicit opt-out flag.
        surface: the construction surface name for the error message
            (``"LlmClient"`` / ``"Agent"``). No secret is interpolated.

    Raises:
        kailash.trust.pact.UngovernedEgressRefused: when the posture is active
            and the call is not exempt (not ungoverned, not mock). There is no
            interceptor-presence exemption (see module docstring — it would be
            fail-open for the four-axis client).
    """
    if ungoverned or is_mock:
        return

    # Resolve the posture. Fail-closed: an error reading it => treat as ACTIVE.
    try:
        from kailash import is_governance_required

        active = is_governance_required()
    except Exception:
        logger.warning(
            "governance_gate.posture_read_failed_fail_closed",
            extra={"surface": surface},
        )
        active = True
    if not active:
        return

    # NO interceptor-presence exemption: the four-axis LlmClient does not route
    # egress through the process-global interceptor, so a merely-installed
    # interceptor does not govern it — exempting on it would be fail-open (the
    # #1779 redteam CRITICAL). The only exemptions are ungoverned=True, mock,
    # and the OFF posture, all handled above.
    from kailash.trust.pact import UngovernedEgressRefused

    raise UngovernedEgressRefused(surface)
