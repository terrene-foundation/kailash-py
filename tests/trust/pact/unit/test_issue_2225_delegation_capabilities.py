# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression tests for GH #2225 -- DelegationRecord.capabilities_delegated
must never advertise a capability the enforcement surfaces deny.

Before the fix, both emission sites in ``engine.py`` populated
``capabilities_delegated`` from the RAW envelope allowlist
(``list(envelope.envelope.operational.allowed_actions)``) -- not reduced by
``blocked_actions``. So a delegation record (a durable, signed EATP
trust-chain artifact an auditor reads) advertised an action every enforcement
surface denies. The divergence was silent and one-directional: it always
OVER-states, never under-states, so nothing failed loudly to reveal it.

The fix derives ``capabilities_delegated`` from the SAME predicate enforcement
uses (``action_policy.delegated_capabilities`` -> ``permitted_action_set`` ->
``allowed - blocked``) so the record and the enforcement path cannot drift.

Each test below is written to FAIL against the unfixed code (the raw-list
population), and asserts BOTH POLES: the blocked action is removed AND a
genuinely-granted action is still present -- guarding against a vacuous
"emptied record" fix that would pass a deny-only assertion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kailash.trust.action_policy import delegated_capabilities, permitted_action_set
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.eatp_emitter import InMemoryPactEmitter
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope, TaskEnvelope
from pact.examples.university.org import create_university_org

# The exact divergence case from the issue: an action that is BOTH allowed and
# blocked. Deny wins, so enforcement denies ``transfer_funds`` everywhere while
# ``read`` remains genuinely granted.
_ALLOWED = ["read", "transfer_funds"]
_BLOCKED = ["transfer_funds"]

_DEAN = "D1-R1-D1-R1-D1-R1"
_CS_CHAIR = "D1-R1-D1-R1-D1-R1-T1-R1"


@pytest.fixture
def compiled_org() -> CompiledOrg:
    return create_university_org()[0]


@pytest.fixture
def emitter() -> InMemoryPactEmitter:
    return InMemoryPactEmitter()


@pytest.fixture
def engine(compiled_org: CompiledOrg, emitter: InMemoryPactEmitter) -> GovernanceEngine:
    # No defining-role envelope is pre-set, so monotonic-tightening validation
    # is skipped and the divergence envelope registers unchanged. The point
    # under test is the RECORD's capability derivation, not tightening.
    return GovernanceEngine(compiled_org, eatp_emitter=emitter)


def _divergence_operational() -> OperationalConstraintConfig:
    return OperationalConstraintConfig(
        allowed_actions=list(_ALLOWED),
        blocked_actions=list(_BLOCKED),
    )


def test_role_envelope_record_excludes_blocked_action(
    engine: GovernanceEngine, emitter: InMemoryPactEmitter
) -> None:
    """Site engine.py:~3216 (set_role_envelope).

    RED before fix: raw list emits ["read", "transfer_funds"].
    GREEN after fix: ["read"] only.
    """
    role_env = RoleEnvelope(
        id="re-2225-role",
        defining_role_address=_DEAN,
        target_role_address=_CS_CHAIR,
        envelope=ConstraintEnvelopeConfig(
            id="env-2225-role",
            description="divergence envelope (role)",
            operational=_divergence_operational(),
        ),
    )
    engine.set_role_envelope(role_env)

    assert len(emitter.delegation_records) == 1
    caps = emitter.delegation_records[-1].capabilities_delegated

    # Pole 1 -- the denied action must NOT be advertised.
    assert (
        "transfer_funds" not in caps
    ), "record advertised a capability every enforcement surface denies"
    # Pole 2 -- the genuinely-granted action MUST still be advertised (guards
    # the vacuous emptied-record fix).
    assert "read" in caps, "record dropped a genuinely-granted capability"
    assert sorted(caps) == ["read"]

    # The record must equal the permitted set the shared predicate computes,
    # tying it to the SAME derivation enforcement uses (no drift).
    assert set(caps) == permitted_action_set(role_env.envelope.operational)


def test_task_envelope_record_excludes_blocked_action(
    engine: GovernanceEngine, emitter: InMemoryPactEmitter
) -> None:
    """Site engine.py:~3305 (set_task_envelope).

    A test exercising only the role site would leave this one diverging, so it
    is asserted independently.
    """
    task_env = TaskEnvelope(
        id="te-2225-task",
        task_id="task-2225",
        parent_envelope_id="re-2225-nonexistent",  # unresolved -> tightening skipped
        envelope=ConstraintEnvelopeConfig(
            id="env-2225-task",
            description="divergence envelope (task)",
            operational=_divergence_operational(),
        ),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    engine.set_task_envelope(task_env)

    assert len(emitter.delegation_records) == 1
    caps = emitter.delegation_records[-1].capabilities_delegated

    assert "transfer_funds" not in caps
    assert "read" in caps
    assert sorted(caps) == ["read"]
    assert set(caps) == permitted_action_set(task_env.envelope.operational)


def test_both_sites_agree_on_the_shared_derivation(
    engine: GovernanceEngine, emitter: InMemoryPactEmitter
) -> None:
    """Both emission sites must produce the SAME derivation for the SAME
    operational policy -- the record and enforcement share one computation."""
    op = _divergence_operational()

    engine.set_role_envelope(
        RoleEnvelope(
            id="re-2225-both",
            defining_role_address=_DEAN,
            target_role_address=_CS_CHAIR,
            envelope=ConstraintEnvelopeConfig(
                id="env-2225-both-role", description="", operational=op
            ),
        )
    )
    engine.set_task_envelope(
        TaskEnvelope(
            id="te-2225-both",
            task_id="task-2225-both",
            parent_envelope_id="re-2225-nonexistent",
            envelope=ConstraintEnvelopeConfig(
                id="env-2225-both-task", description="", operational=op
            ),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )

    assert len(emitter.delegation_records) == 2
    role_caps = sorted(emitter.delegation_records[0].capabilities_delegated)
    task_caps = sorted(emitter.delegation_records[1].capabilities_delegated)
    assert role_caps == task_caps == ["read"]
    # And both equal the shared helper applied to the same operational policy.
    assert role_caps == delegated_capabilities(op)


def test_record_lists_all_genuinely_granted_capabilities(
    engine: GovernanceEngine, emitter: InMemoryPactEmitter
) -> None:
    """Both-poles guard on a multi-action envelope with NO blocked actions:
    every allowed action is still advertised (the fix must not over-filter)."""
    role_env = RoleEnvelope(
        id="re-2225-grant",
        defining_role_address=_DEAN,
        target_role_address=_CS_CHAIR,
        envelope=ConstraintEnvelopeConfig(
            id="env-2225-grant",
            description="",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "grade"],
            ),
        ),
    )
    engine.set_role_envelope(role_env)

    caps = emitter.delegation_records[-1].capabilities_delegated
    assert sorted(caps) == ["grade", "read", "write"]


def test_delegated_capabilities_helper_subtracts_blocked() -> None:
    """The shared derivation itself: allowed - blocked, deterministic order."""
    op = _divergence_operational()
    assert delegated_capabilities(op) == ["read"]
    # None (dimension absent) -> no finite list to advertise; empty understates
    # (safe -- never over-states).
    assert delegated_capabilities(None) == []
