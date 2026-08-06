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

FOURTH CHANGE, a RATIFIED POSTURE FLIP rather than a bug fix: the
`except Exception` path now FAILS CLOSED. It used to grant.

That path is a genuine availability-versus-safety trade on a public API, so it
was deliberately excluded from the three fixes above and pinned by a test —
`test_error_path_still_fails_open` — precisely so the flip could not arrive
silently as a side effect of unrelated work. The flip has now been made
deliberately, and that test is DELETED (see the commit that made the flip).
`TestErrorPathFailsClosed` below is its inverse: it asserts the denial, and it
is the tripwire against a silent flip BACK.

The accepted trade, stated so no future reader mistakes it for an oversight: a
transient checker outage now denies EVERY user instead of granting every user.
A denial is a recoverable availability event; a wrong grant is not recoverable.
The denial is loud (ERROR) so an outage is distinguishable from a legitimate
"nobody has access", and the exception text is routed through the shared
`scrub_credentials` helper because a caller-supplied checker may embed a DSN.

NOT changed by the flip: the UN-WIRED default (no `permission_checker` at all)
still grants. That is a separate question — an un-wired instance never asked;
a raising checker was asked and could not answer — and it is pinned by
`test_unwired_instance_still_grants_access` in
`test_silent_authz_and_routing_fallbacks.py`.
"""

from __future__ import annotations

import logging

import pytest

from kaizen_agents.patterns.discovery import AccessMetadata, UserFilteredAgentDiscovery
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


class _Boom:
    """A checker that is down. Its exception text embeds a DSN on purpose."""

    async def verify(self, **kwargs):
        raise RuntimeError(
            "checker unavailable: postgresql://admin:s3cr3t@db.internal:5432/prod"
        )


class _StubRegistry:
    """Only `list_agents` is reached by `find_agents_for_user`."""

    async def list_agents(self, status_filter=None):
        return [_Meta()]


class TestErrorPathFailsClosed:
    """The RATIFIED posture flip: a checker that raised has not approved.

    This class replaces `test_error_path_still_fails_open`, which pinned the
    opposite behaviour so the flip could not happen silently. It was deleted in
    the commit that made the flip. These tests are the tripwire in the other
    direction — a silent flip BACK to fail-open now fails here.
    """

    @pytest.mark.asyncio
    async def test_error_path_denies(self) -> None:
        """THE TEETH. Pre-flip this GRANTED.

        A transient checker outage denying every user is the ACCEPTED trade,
        not an oversight: a denial is recoverable, a wrong grant is not.
        """
        granted, _ = await _check(_Boom())
        assert granted is False, (
            "the checker-error path GRANTED access. A checker that raised has "
            "not approved anything — an unanswered authorization question is "
            "not a yes. If this reverted deliberately it needs its own "
            "reviewed decision; flipping an authorization default back to "
            "fail-open is not a refactor."
        )

    @pytest.mark.asyncio
    async def test_denial_returns_caller_safe_metadata(self) -> None:
        """A denial must return well-formed metadata, never None.

        `find_agents_for_user` unpacks the pair unconditionally and callers may
        serialize the metadata, so a `None` (or a bare tuple) on the denial
        path would turn an authorization outage into an AttributeError inside
        the caller — a fail-closed decision that crashes is not fail-closed.
        """
        granted, meta = await _check(_Boom())
        assert granted is False
        assert meta is not None, "the denial path returned no access metadata"
        assert isinstance(
            meta, AccessMetadata
        ), f"the denial path returned {type(meta).__name__}, not AccessMetadata"
        assert meta.constraints is not None, (
            "denial metadata carried no constraints object; `.constraints` is "
            "dereferenced by consumers without a None check"
        )
        # The shape consumers actually serialize. This assertion USED to read
        #     assert ...["max_tokens_per_session"] is None
        # which PINNED the defect as correct: `null` is this type's encoding
        # for UNLIMITED, and the denial's `permission_level` defaulted to
        # "execute", so the payload read on its own was an execute-level grant
        # with no caps at all — the most permissive value the type can hold.
        # Hardening it would have RED-ed a test whose message said the denial
        # metadata was fine. Full treatment in
        # `test_discovery_falsy_checker_and_denial_shape.py`; this is the
        # caller-safety half only.
        data = meta.to_dict()
        assert data["denied"] is True, (
            f"the denial payload is not marked denied and so is not "
            f"distinguishable from a grant by anything reading it without the "
            f"boolean: {data!r}"
        )
        assert (
            data["permission_level"] != "execute"
        ), f"the denial payload reports execute-level access: {data!r}"
        assert (
            data["constraints"]["max_tokens_per_session"] == 0
        ), f"the denial payload reports UNLIMITED tokens (null): {data!r}"

    @pytest.mark.asyncio
    async def test_denial_excludes_the_agent_from_find_agents_for_user(self) -> None:
        """The real caller path: outage → empty result, not an exception.

        `_check_user_access` is private; this pins the behaviour a consumer
        actually observes.
        """
        d = UserFilteredAgentDiscovery(_StubRegistry(), permission_checker=_Boom())
        found = await d.find_agents_for_user("user-1", "org-1")
        assert found == [], (
            "an agent was returned while the permission checker was down; the "
            "fail-closed denial did not reach the caller"
        )

    @pytest.mark.asyncio
    async def test_denial_is_loud_and_the_exception_text_is_scrubbed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Under fail-closed an outage is a TOTAL discovery outage.

        The ERROR line is the only thing distinguishing "the checker is down"
        from "this user legitimately has access to nothing", so it must be
        emitted at ERROR with the exception detail — and that detail must be
        scrubbed, because a caller-supplied checker may embed a DSN.
        """
        with caplog.at_level(logging.ERROR):
            await _check(_Boom())

        hits = [
            r
            for r in caplog.records
            if r.message == "discovery.permission_check_failed_closed"
        ]
        assert len(hits) == 1, (
            "the fail-closed denial was not logged at ERROR; a silent denial "
            "is indistinguishable from an empty agent list"
        )
        error_text = hits[0].__dict__["error"]
        assert (
            "s3cr3t" not in error_text
        ), f"the checker's exception text reached the log unscrubbed: {error_text!r}"
        assert (
            "[REDACTED]" in error_text
        ), f"expected scrub_credentials output, got {error_text!r}"
