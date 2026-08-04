# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: the DOCUMENTED permission checker never worked (forest W12).

`UserFilteredAgentDiscovery.__init__` documents its `permission_checker` as
`(TrustOperations)`. That type's real signature is

    verify(agent_id, action, resource=None, level=..., context=None)

— no `user_id`, no `organization_id`, no `**kwargs`. The call site passed
`user_id=` and `organization_id=`, so wiring the documented checker raised
`TypeError` on the FIRST agent of every call, which the `except Exception`
handler caught and converted into a GRANT.

So the documented integration returned EVERY agent to EVERY user, in every
organization, always. Not a transient outage window — the steady state.

WHY NOTHING CAUGHT IT: every existing test supplies a bespoke duck-typed checker
written to match the call site
(`async def verify(self, agent_id, action, user_id, organization_id)`). No test
used a real `TrustOperations`, and the exception path was untested in both
polarities. The fixture agreed with the code, so the code and the fixture were
consistently wrong together — the same shape as the routing fixture in
`test_issue_1981_second_order_consumers.py`.

THREE DEFECTS FIXED, all of them unambiguous bugs with no posture trade:

1. CALL SHAPE — both forms are now supported, chosen by introspecting the
   checker ONCE at `__init__`. The duck-typed kwargs form (what consumers
   actually wired) keeps working; the `context=` form `TrustOperations`
   declares now works at all.
2. MALFORMED RESULT — `hasattr(result, "valid")` granted access to any object
   lacking `.valid`, reading the ABSENCE of a deny signal as approval. Now
   `is not True`: denied unless the checker affirmatively approved.
3. CONSTRAINTS — `VerificationResult` exposes `effective_constraints`, not
   `constraints`, so the old `hasattr` check was False for the documented type
   and every granted user silently received UNLIMITED constraints. Both names
   are read.

WHAT IS DELIBERATELY NOT CHANGED, and is asserted below so it cannot drift
silently: the `except Exception` path still FAILS OPEN. That one is a genuine
availability-versus-safety trade on a public API — fail-closed means a transient
checker outage denies every user — and it is a decision for its owner, not a
side effect of fixing a call signature. `test_error_path_still_fails_open` pins
the current behaviour so that when the flip does happen it is a deliberate,
reviewed change with a failing test to acknowledge.
"""

from __future__ import annotations

import pytest

from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery
from kaizen_agents.patterns.registry import AgentRegistry

pytestmark = pytest.mark.regression


class _Meta:
    """Minimal stand-in for AgentMetadata; only `agent_id` is read."""

    agent_id = "agent-1"


class _TrustOperationsShaped:
    """Mirrors the REAL `TrustOperations.verify` signature exactly.

    This is the fixture the original suite never had. With the pre-fix call
    site it raises TypeError on the first agent, which is the whole defect.
    """

    def __init__(self, valid: bool) -> None:
        self._valid = valid
        self.seen_context: dict | None = None

    async def verify(self, agent_id, action, resource=None, level=None, context=None):
        self.seen_context = context
        return type("R", (), {"valid": self._valid, "effective_constraints": {}})()


class _DuckTyped:
    """The shape consumers actually wired, and that every prior test used."""

    def __init__(self, valid: bool, constraints: dict | None = None) -> None:
        self._valid = valid
        self._constraints = constraints or {}

    async def verify(self, agent_id, action, user_id, organization_id):
        return type("R", (), {"valid": self._valid, "constraints": self._constraints})()


async def _check(checker):
    d = UserFilteredAgentDiscovery(AgentRegistry(), permission_checker=checker)
    return await d._check_user_access("user-1", "org-1", _Meta())


class TestDocumentedCheckerTypeActuallyWorks:
    @pytest.mark.asyncio
    async def test_denies_when_the_documented_checker_says_invalid(self) -> None:
        """THE TEETH. Pre-fix this GRANTED — the call raised TypeError and the
        handler turned it into access."""
        checker = _TrustOperationsShaped(valid=False)
        granted, _ = await _check(checker)
        assert granted is False, (
            "the documented checker type denied access and the caller was "
            "granted it anyway — the call signature does not match "
            "TrustOperations.verify, so the TypeError is being read as a grant"
        )

    @pytest.mark.asyncio
    async def test_user_and_org_reach_the_documented_checker(self) -> None:
        """Denying is not enough: the checker must receive the subject.

        Without this, a fix that simply stopped passing the kwargs would pass
        the test above while making every check subject-blind.
        """
        checker = _TrustOperationsShaped(valid=True)
        await _check(checker)
        assert checker.seen_context == {
            "user_id": "user-1",
            "organization_id": "org-1",
        }, (
            f"the documented checker was invoked without the subject; it "
            f"received {checker.seen_context!r}"
        )

    @pytest.mark.asyncio
    async def test_grants_when_the_documented_checker_approves(self) -> None:
        """Non-regression: the fix must not deny everything instead."""
        granted, meta = await _check(_TrustOperationsShaped(valid=True))
        assert granted is True
        assert meta.permission_level == "execute"


class TestDuckTypedCheckerStillWorks:
    """The shape consumers actually wired must not break."""

    @pytest.mark.asyncio
    async def test_duck_typed_deny_is_honoured(self) -> None:
        granted, _ = await _check(_DuckTyped(valid=False))
        assert granted is False

    @pytest.mark.asyncio
    async def test_duck_typed_grant_and_constraints(self) -> None:
        granted, meta = await _check(
            _DuckTyped(valid=True, constraints={"max_tokens": 42})
        )
        assert granted is True
        assert meta.constraints.max_tokens_per_session == 42, (
            "constraints from a duck-typed checker were dropped; a granted "
            "user silently receives UNLIMITED constraints"
        )


class TestMalformedResultFailsClosed:
    @pytest.mark.asyncio
    async def test_result_without_valid_is_denied(self) -> None:
        """Absence of a deny signal is not approval.

        Pre-fix `hasattr(result, "valid")` was False for such an object, so it
        fell through to the grant at the end of the method.
        """

        class _NoValid:
            async def verify(self, **kwargs):
                return object()

        granted, _ = await _check(_NoValid())
        assert granted is False, (
            "a checker returning an unreadable result was treated as an "
            "approval; an answer we cannot parse is not a yes"
        )

    @pytest.mark.asyncio
    async def test_result_with_non_true_valid_is_denied(self) -> None:
        """`valid` must be True, not merely truthy-ish or present."""

        class _NoneValid:
            async def verify(self, **kwargs):
                return type("R", (), {"valid": None})()

        granted, _ = await _check(_NoneValid())
        assert granted is False


class TestErrorPathIsDeliberatelyUnchanged:
    @pytest.mark.asyncio
    async def test_error_path_still_fails_open(self) -> None:
        """PINS A DECISION, NOT A DEFECT.

        The `except Exception` path still GRANTS. That is a real
        availability-versus-safety trade on a public API — fail-closed means a
        transient checker outage denies every user — and it belongs to whoever
        owns that trade, not to a commit fixing a call signature.

        If this test starts failing, the flip has happened. That is fine, and
        may well be right: delete this test and say so in the commit. What must
        NOT happen is the flip arriving silently as a side effect of unrelated
        work, which is exactly what this pins against.
        """

        class _Boom:
            async def verify(self, **kwargs):
                raise RuntimeError("checker unavailable")

        granted, _ = await _check(_Boom())
        assert granted is True, (
            "the checker-error path now DENIES. If that was deliberate and "
            "reviewed, delete this test and record the decision. If it was a "
            "side effect, revert it — flipping an authorization default is not "
            "a refactor."
        )
