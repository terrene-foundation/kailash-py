# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2227 Route B -- ``governance_callback`` leaked the engine.

``PactEngine.governance`` is a fail-closed read-only view that denies every
mutation method on ``GovernanceEngine``. ``PactEngine.governance_callback`` is
an equally PUBLIC property, and it returned a ``_DefaultGovernanceCallback``
constructed with the RAW engine, stored as an ordinary attribute::

    vars(cb): {'_governance': 'GovernanceEngine', '_on_held': 'NoneType'}
    engine.governance_callback._governance.grant_clearance(...)   # reachable

This is not a proxy defect and #2224 could not have closed it: the route never
goes THROUGH a proxy, it goes AROUND one. Two public accessors on the same
facade disagreed about how much authority a holder gets, and the weaker one won.

The fix is not to hide the attribute -- that is a rename, and the next
attribute name is one ``vars()`` call away. The callback only ever calls
``verify_action``, which the read-only view already proxies, so it never needed
the raw engine: ``governance_callback`` now constructs it with the VIEW. The
leak becomes a leak of an already-contained object.

Both poles are asserted: the escalation must fail AND per-node governance must
still produce real verdicts through the callback.
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.readonly_proxy import ReadOnlyProxyError
from pact.engine import PactEngine, _ReadOnlyGovernanceView

_ORG: dict[str, Any] = {
    "org_id": "org-2227",
    "name": "Issue 2227 Org",
    "departments": [{"id": "d-eng", "name": "Engineering"}],
    "teams": [{"id": "t-backend", "name": "Backend"}],
    "roles": [
        {"id": "r-cto", "name": "CTO", "heads": "d-eng"},
        {"id": "r-lead", "name": "Lead", "reports_to": "r-cto", "heads": "t-backend"},
        {"id": "r-dev", "name": "Dev", "reports_to": "r-lead"},
    ],
}
ADDR = "D1-R1-T1-R1-R1"
SUPERVISOR = "D1-R1-T1-R1"


@pytest.fixture
def engine() -> PactEngine:
    eng = PactEngine(org=_ORG)
    eng._admin_governance.set_role_envelope(
        RoleEnvelope(
            id="re-2227",
            defining_role_address=SUPERVISOR,
            target_role_address=ADDR,
            envelope=ConstraintEnvelopeConfig(
                id="env-2227",
                operational=OperationalConstraintConfig(allowed_actions=["read_docs"]),
            ),
        )
    )
    return eng


class TestGovernanceCallbackDoesNotLeakTheEngine:
    """POLE 1: no ordinary attribute read off the public property reaches the engine."""

    def test_callback_governance_attribute_is_not_the_raw_engine(
        self, engine: PactEngine
    ) -> None:
        callback = engine.governance_callback

        assert callback._governance is not engine._admin_governance
        assert not isinstance(callback._governance, GovernanceEngine)
        assert isinstance(callback._governance, _ReadOnlyGovernanceView)

    def test_no_attribute_in_vars_is_the_raw_engine(self, engine: PactEngine) -> None:
        """``vars()`` is how the leak was found; nothing in it may be the engine.

        Asserted over EVERY attribute rather than the one name the issue
        reported, so renaming the field does not silently reopen this.
        """
        callback = engine.governance_callback
        engine_leaks = [
            name
            for name, value in vars(callback).items()
            if isinstance(value, GovernanceEngine)
        ]
        assert engine_leaks == [], (
            f"{engine_leaks} on the object returned by the PUBLIC "
            f"governance_callback property IS the GovernanceEngine (#2227 Route B)"
        )

    def test_mutation_through_the_callback_is_denied(self, engine: PactEngine) -> None:
        """The concrete escalation from the issue body."""
        callback = engine.governance_callback

        with pytest.raises(ReadOnlyProxyError):
            callback._governance.grant_clearance(ADDR, object())
        with pytest.raises(ReadOnlyProxyError):
            callback._governance.set_role_envelope(object())

    def test_denial_matches_the_governance_view(self, engine: PactEngine) -> None:
        """Surface parity: the two public routes must agree about authority.

        The defect was precisely that they DISAGREED -- ``engine.governance``
        denied ``grant_clearance`` while ``engine.governance_callback``
        delivered it.
        """
        for reach in (
            lambda: engine.governance.grant_clearance,
            lambda: engine.governance_callback._governance.grant_clearance,
        ):
            with pytest.raises(ReadOnlyProxyError):
                reach()


class TestGovernanceCallbackStillGoverns:
    """POLE 2: the callback must still do its job through the view."""

    @pytest.mark.asyncio
    async def test_allowed_action_returns_a_verdict(self, engine: PactEngine) -> None:
        verdict = await engine.governance_callback(ADDR, "read_docs", {})
        assert verdict.allowed is True

    @pytest.mark.asyncio
    async def test_blocked_action_raises(self, engine: PactEngine) -> None:
        from kailash.trust.pact.exceptions import PactError

        with pytest.raises(PactError, match="Governance BLOCKED"):
            await engine.governance_callback(ADDR, "wire_transfer", {})

    def test_on_held_handler_is_still_wired(self, engine: PactEngine) -> None:
        """The other constructor argument must survive the change."""

        async def _handler(*args: Any, **kwargs: Any) -> bool:
            return True

        eng = PactEngine(org=_ORG, on_held=_handler)
        assert eng.governance_callback._on_held is _handler
