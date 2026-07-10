# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: BH5 (#1510) -- a first-class governance circuit-breaker in the
PACT verdict path.

Before BH5 the only breaker in the trust plane was ``PostureCircuitBreaker`` --
an orchestration-only posture-downgrade helper keyed by ``agent_id`` that is
NEVER consulted by ``verify_action``. A repeatedly-escalating ``(role, action)``
was therefore never auto-held by a governance control. BH5 adds
``PactCircuitBreaker`` as a peer control at Step 3.7.

These tests are BEHAVIORAL (call ``verify_action`` / the breaker; assert the
verdict + state), NOT source-grep, per ``testing.md``.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import MonotonicTighteningError, RoleEnvelope
from kailash.trust.pact.store import MemoryClearanceStore
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

pytestmark = pytest.mark.regression

_ROLE = "D1-R1-D1-R1-D1-R1-T1-R1"
_DEFINER = "D1-R1-D1-R1-D1-R1"


def _engine() -> GovernanceEngine:
    org, _ = create_university_org()
    cs = MemoryClearanceStore()
    for clr in create_university_clearances(org).values():
        cs.grant_clearance(clr)
    return GovernanceEngine(org, clearance_store=cs)


def _install_breaker(engine: GovernanceEngine, *, threshold: int) -> None:
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-1510",
            defining_role_address=_DEFINER,
            target_role_address=_ROLE,
            envelope=ConstraintEnvelopeConfig(
                id="env-1510",
                financial=FinancialConstraintConfig(
                    max_spend_usd=1000.0, requires_approval_above_usd=100.0
                ),
                operational=OperationalConstraintConfig(
                    allowed_actions=["deploy"],
                    circuit_failure_threshold=threshold,
                    circuit_window_seconds=3600.0,
                    circuit_cooldown_seconds=300.0,
                ),
            ),
        )
    )


def test_breaker_is_a_verdict_path_control_not_orchestration_only() -> None:
    """The regression: the breaker actually GOVERNS verify_action -- it trips on
    repeated held outcomes and then HOLDS the (role, action) blocked."""
    engine = _engine()
    _install_breaker(engine, threshold=3)
    held = {"cost": 500.0}  # above approval, below max -> HELD each call

    for _ in range(3):
        assert engine.verify_action(_ROLE, "deploy", held).level == "held"

    tripped = engine.verify_action(_ROLE, "deploy", held)
    assert tripped.level == "blocked"
    assert "Circuit-breaker OPEN" in tripped.reason
    assert tripped.audit_details["circuit_breaker"]["tripped"] is True
    assert tripped.audit_details["circuit_breaker"]["state"] == "open"


def test_tripped_breaker_holds_even_a_cheap_call_blocked() -> None:
    """Monotonic tighten-only: once tripped, even an otherwise-auto_approved
    call is blocked (the breaker never de-escalates, only escalates)."""
    engine = _engine()
    _install_breaker(engine, threshold=2)
    held = {"cost": 500.0}
    engine.verify_action(_ROLE, "deploy", held)
    engine.verify_action(_ROLE, "deploy", held)  # tripped
    assert engine.verify_action(_ROLE, "deploy", {"cost": 1.0}).level == "blocked"


def test_no_breaker_config_is_byte_unchanged() -> None:
    """Backward-compat: an envelope with no breaker leaves the verdict AND the
    audit trail exactly as before the seam."""
    engine = _engine()
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-none",
            defining_role_address=_DEFINER,
            target_role_address=_ROLE,
            envelope=ConstraintEnvelopeConfig(
                id="env-none",
                operational=OperationalConstraintConfig(allowed_actions=["deploy"]),
            ),
        )
    )
    for _ in range(25):
        verdict = engine.verify_action(_ROLE, "deploy", {"cost": 1.0})
        assert verdict.level == "auto_approved"
        assert "circuit_breaker" not in verdict.audit_details


def test_re_registration_cannot_silently_strip_the_breaker() -> None:
    """Enforcement-surface parity (security.md): a child envelope that removes a
    parent's breaker is rejected as a widening at registration time -- the
    privilege escalation the fix would otherwise introduce."""
    engine = _engine()
    engine.set_role_envelope(
        RoleEnvelope(
            id="re-parent-1510",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address=_DEFINER,
            envelope=ConstraintEnvelopeConfig(
                id="env-parent-1510",
                operational=OperationalConstraintConfig(
                    allowed_actions=["deploy"],
                    circuit_failure_threshold=3,
                    circuit_window_seconds=3600.0,
                    circuit_cooldown_seconds=300.0,
                ),
            ),
        )
    )
    with pytest.raises(MonotonicTighteningError, match="circuit-breaker widened"):
        engine.set_role_envelope(
            RoleEnvelope(
                id="re-child-1510",
                defining_role_address=_DEFINER,
                target_role_address=_ROLE,
                envelope=ConstraintEnvelopeConfig(
                    id="env-child-1510",
                    operational=OperationalConstraintConfig(
                        allowed_actions=["deploy"]  # breaker stripped
                    ),
                ),
            )
        )


def test_breakerless_envelope_signing_preimage_is_byte_identical_to_pre_bh5() -> None:
    """The HIGH regression (signed-envelope backward compat).

    The breaker fields are NEW on OperationalConstraintConfig. If they entered
    the SignedEnvelope pre-image as ``null`` for a breaker-less envelope, EVERY
    pre-BH5 / cross-SDK (rs-signed) constraint envelope would fail verification
    under post-BH5 code. Unset breaker fields are pruned from the signing dict,
    so a breaker-less envelope's signed BYTES carry no ``circuit_*`` key --
    byte-identical to the pre-BH5 form (the same backward-compat contract BH3
    used for its trace unbound form).
    """
    from kailash.trust.pact.envelopes import _envelope_signing_dict
    from kailash.trust.signing.crypto import serialize_for_signing

    env = ConstraintEnvelopeConfig(
        id="env-bc",
        operational=OperationalConstraintConfig(
            allowed_actions=["deploy"], max_actions_per_day=100
        ),
    )
    payload = serialize_for_signing(_envelope_signing_dict(env))
    # Behavioral assertion on the SIGNED bytes, not the source: no breaker key.
    assert "circuit_" not in payload
    # The pre-existing operational fields are still signed (not over-pruned).
    assert "max_actions_per_day" in payload


def test_configured_breaker_is_bound_into_the_signed_preimage() -> None:
    """A CONFIGURED breaker keeps its fields in the signed pre-image, so a
    tripped/held breaker cannot be silently stripped from a signed envelope
    without invalidating the signature."""
    from kailash.trust.pact.envelopes import _envelope_signing_dict
    from kailash.trust.signing.crypto import serialize_for_signing

    env = ConstraintEnvelopeConfig(
        id="env-cb",
        operational=OperationalConstraintConfig(
            allowed_actions=["deploy"],
            circuit_failure_threshold=3,
            circuit_window_seconds=3600.0,
            circuit_cooldown_seconds=300.0,
        ),
    )
    payload = serialize_for_signing(_envelope_signing_dict(env))
    assert "circuit_failure_threshold" in payload
    assert "circuit_window_seconds" in payload
    assert "circuit_cooldown_seconds" in payload
