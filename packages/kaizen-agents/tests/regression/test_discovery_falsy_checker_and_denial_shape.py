# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: three residual authz defects in `UserFilteredAgentDiscovery`.

Found by a two-lane redteam (adversarial security + independent correctness)
over commit `393f33e27`, which flipped the `except Exception` path in
`_check_user_access` from GRANT to DENY. That flip was correct and is NOT
re-litigated here. These are the defects it left standing, each of which
re-opens the same hole the flip closed.

DEFECT 1 — a wired-but-FALSY permission_checker silently GRANTS, unannounced.

    `__init__` guards its loud startup WARN on `permission_checker is None`
    (identity). `_check_user_access` guarded the ENTIRE enforcement block on
    `if self._permission_checker:` (truthiness). Any checker object that is
    falsy but NOT None — one defining `__bool__` returning False or `__len__`
    returning 0, the realistic shape being a policy-set / rule-collection
    wrapper or a health-gated checker — therefore skipped enforcement
    completely and fell through to the terminal grant, WITHOUT the constructor
    warning that exists to make exactly this state impossible to reach
    silently. A checker was installed, no warning was emitted, and every user
    was granted `execute` on every agent.

    The predicate mismatch is the whole bug: two guards over the same object,
    one identity and one truthiness, disagreeing on a value neither author
    considered.

DEFECT 2 — the denial payload was indistinguishable from a maximally
permissive grant.

    Both denial branches returned a bare `AccessMetadata()`. Its dataclass
    defaults are `permission_level="execute"` and an `AccessConstraints()`
    whose every field is `None` — serialized by `to_dict()` as `null`, which
    is the encoding for UNLIMITED. So the denial object, read on its own,
    said: execute-level access with no cap on invocations, tokens, spend, or
    tools. That is the strictly most permissive value the type can hold.

    LATENT, not live: the sole in-repo consumer (`find_agents_for_user`) gates
    on the boolean and drops the metadata. But `_check_user_access` is on a
    public class and returns a 2-tuple, and `393f33e27` TRIPLED how often that
    payload is produced (the exception path now denies rather than grants).
    This is the same family as the bug that commit itself fixed one branch
    over, where "every granted user silently received UNLIMITED constraints".

    Worse, the suite added alongside that commit PINNED the permissive shape
    as correct (`assert meta.to_dict()["constraints"]["max_tokens_per_session"]
    is None`), so hardening the payload would have RED-ed a test whose message
    said the denial metadata was fine. That assertion is replaced by the
    inverse in `test_discovery_documented_checker_works.py`.

DEFECT 3 — a present-but-None `constraints` shadowed `effective_constraints`.

    `getattr(result, "constraints", getattr(result, "effective_constraints",
    None))` evaluates its default eagerly but USES it only when the attribute
    is ABSENT. A result object that DECLARES `constraints` (a dataclass field
    defaulting to None) while populating `effective_constraints` — plausible
    for any type carrying both names through a rename — yielded `raw = None`,
    failed the `isinstance(raw, dict)` check, and the user was granted with
    all-`None`, i.e. UNLIMITED, constraints. Verbatim the failure the same
    commit's own comment claims to have fixed.

WHY NOTHING CAUGHT ANY OF THESE: every fixture in the existing suites is a
plain object (truthy, and carrying exactly one of the two constraint names),
so the fixtures agreed with the code and were consistently wrong together.
Each test below therefore supplies the shape no prior fixture had.
"""

from __future__ import annotations

import logging

import pytest

from kaizen_agents.patterns.discovery import (
    DENIED_PERMISSION_LEVEL,
    AccessMetadata,
    UserFilteredAgentDiscovery,
)
from kaizen_agents.patterns.registry import AgentRegistry

pytestmark = pytest.mark.regression


class _Meta:
    """Minimal stand-in for AgentMetadata; only `agent_id` is read."""

    agent_id = "agent-1"


class _StubRegistry:
    """Only `list_agents` is reached by `find_agents_for_user`."""

    async def list_agents(self, status_filter=None):
        return [_Meta()]


def _result(**attrs):
    """Build a verification result object with exactly the given attributes."""
    return type("R", (), dict(attrs))()


# --------------------------------------------------------------------------
# DEFECT 1 — falsy-but-not-None checkers
# --------------------------------------------------------------------------


class _FalsyByLen:
    """Falsy via `__len__` — the realistic shape.

    A policy-set / rule-collection wrapper that is empty right now (no rules
    loaded yet, or every rule filtered out for this tenant) is falsy by
    `__len__` while being a perfectly live, wired checker.
    """

    def __init__(self, valid: bool) -> None:
        self._valid = valid
        self.called = False

    def __len__(self) -> int:
        return 0

    async def verify(self, agent_id, action, user_id, organization_id):
        self.called = True
        return _result(valid=self._valid, constraints={})


class _FalsyByBool:
    """Falsy via `__bool__` — e.g. a health-gated checker reporting degraded."""

    def __init__(self, valid: bool) -> None:
        self._valid = valid
        self.called = False

    def __bool__(self) -> bool:
        return False

    async def verify(self, agent_id, action, user_id, organization_id):
        self.called = True
        return _result(valid=self._valid, constraints={})


async def _check(checker):
    d = UserFilteredAgentDiscovery(AgentRegistry(), permission_checker=checker)
    return await d._check_user_access("user-1", "org-1", _Meta())


class TestFalsyCheckerIsStillEnforced:
    """A checker that is falsy but not None is WIRED, and MUST be consulted."""

    @pytest.mark.parametrize("factory", [_FalsyByLen, _FalsyByBool])
    @pytest.mark.asyncio
    async def test_falsy_checker_denial_is_honoured(self, factory) -> None:
        """THE TEETH. Pre-fix this GRANTED, and consulted nothing.

        The enforcement block was guarded on truthiness while the startup
        warning was guarded on identity, so this object fell through both: no
        check ran, and no warning said so.
        """
        checker = factory(valid=False)
        granted, meta = await _check(checker)

        assert checker.called is True, (
            "a wired permission_checker was never consulted — the enforcement "
            "block is guarded on truthiness (`if self._permission_checker:`) "
            "while __init__ guards its warning on identity "
            "(`permission_checker is None`), so a falsy-but-not-None checker "
            "skips enforcement entirely and no warning is emitted"
        )
        assert granted is False, (
            "a falsy-but-not-None permission_checker DENIED access and the "
            "caller was granted it anyway — a silent, unannounced fail-open "
            "with a checker installed"
        )
        assert (
            meta.denied is True
        ), "the falsy-checker denial did not carry the explicit denial marker"

    @pytest.mark.parametrize("factory", [_FalsyByLen, _FalsyByBool])
    @pytest.mark.asyncio
    async def test_falsy_checker_grant_still_grants(self, factory) -> None:
        """Non-regression: the fix must not deny everything instead."""
        checker = factory(valid=True)
        granted, meta = await _check(checker)
        assert granted is True
        assert meta.denied is False
        assert meta.permission_level == "execute"

    @pytest.mark.asyncio
    async def test_falsy_checker_emits_no_unwired_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CONTROL — true before AND after the fix, and that is the point.

        This does not assert the defect's negation; it pins the property that
        made the defect SILENT. A checker IS wired, so the "filtering is off"
        warning correctly does not fire — which is precisely why the
        truthiness guard's fall-through had no audible signal. If a future
        change tries to paper over the predicate mismatch by widening the
        constructor warning to fire on falsy checkers instead of fixing the
        enforcement guard, this fails and says so.
        """
        with caplog.at_level(logging.WARNING):
            UserFilteredAgentDiscovery(
                AgentRegistry(), permission_checker=_FalsyByLen(valid=False)
            )

        hits = [
            r
            for r in caplog.records
            if r.message == "discovery.permission_filtering_disabled"
        ]
        assert hits == [], (
            "the un-wired warning fired for a WIRED checker. Widening this "
            "warning is not the fix for the truthiness/identity predicate "
            "mismatch — the enforcement guard must match __init__'s "
            "`is None`, so that a wired checker is always consulted"
        )

    @pytest.mark.asyncio
    async def test_falsy_checker_denial_reaches_find_agents_for_user(self) -> None:
        """The real caller path: a falsy checker's denial excludes the agent.

        `_check_user_access` is private; this pins what a consumer observes.
        """
        d = UserFilteredAgentDiscovery(
            _StubRegistry(), permission_checker=_FalsyByLen(valid=False)
        )
        found = await d.find_agents_for_user("user-1", "org-1")
        assert found == [], (
            "an agent was returned to a user the wired checker denied; the "
            "falsy-checker fall-through granted access at the caller surface"
        )


# --------------------------------------------------------------------------
# DEFECT 2 — the denial payload must not read as a grant
# --------------------------------------------------------------------------


class _Boom:
    """A checker that is down."""

    async def verify(self, **kwargs):
        raise RuntimeError("checker unavailable")


class _Malformed:
    """A checker answering in a shape we cannot read."""

    async def verify(self, **kwargs):
        return object()


def _assert_not_readable_as_a_grant(meta: AccessMetadata, origin: str) -> None:
    """A denial payload, read WITHOUT its boolean, must not look like access."""
    data = meta.to_dict()

    assert meta.denied is True, (
        f"the {origin} denial metadata carries denied={meta.denied!r}; a "
        f"consumer reading the payload without the boolean cannot tell it "
        f"apart from a grant"
    )
    assert (
        data["denied"] is True
    ), f"the {origin} denial serialized without an explicit denial marker: {data!r}"
    assert meta.permission_level == DENIED_PERMISSION_LEVEL, (
        f"the {origin} denial reported permission_level="
        f"{meta.permission_level!r} — the dataclass default is 'execute', so "
        f"a bare AccessMetadata() denial serializes as an EXECUTE grant"
    )
    assert (
        data["permission_level"] != "execute"
    ), f"the {origin} denial serialized as execute-level access: {data!r}"

    constraints = data["constraints"]
    assert constraints["max_tokens_per_session"] == 0, (
        f"the {origin} denial serialized max_tokens_per_session="
        f"{constraints['max_tokens_per_session']!r}; null is the encoding for "
        f"UNLIMITED, so the denial payload was strictly the most permissive "
        f"value the type can hold"
    )
    assert (
        constraints["max_daily_invocations"] == 0
    ), f"the {origin} denial serialized unlimited daily invocations: {constraints!r}"
    assert (
        constraints["max_cost_per_session_usd"] == 0
    ), f"the {origin} denial serialized unlimited spend: {constraints!r}"
    assert constraints["allowed_tools"] == [], (
        f"the {origin} denial serialized allowed_tools="
        f"{constraints['allowed_tools']!r}; null means UNCONSTRAINED, i.e. "
        f"every tool is allowed"
    )


class TestDenialPayloadIsNotReadableAsAGrant:
    @pytest.mark.asyncio
    async def test_exception_branch_denial_shape(self) -> None:
        """THE TEETH for the checker-ERRORED denial."""
        granted, meta = await _check(_Boom())
        assert granted is False
        _assert_not_readable_as_a_grant(meta, "checker-error")

    @pytest.mark.asyncio
    async def test_malformed_result_branch_denial_shape(self) -> None:
        """THE TEETH for the unreadable-ANSWER denial."""
        granted, meta = await _check(_Malformed())
        assert granted is False
        _assert_not_readable_as_a_grant(meta, "malformed-result")

    @pytest.mark.asyncio
    async def test_checker_denial_shape(self) -> None:
        """THE TEETH for the checker-said-NO denial (the common case)."""
        granted, meta = await _check(_FalsyByLen(valid=False))
        assert granted is False
        _assert_not_readable_as_a_grant(meta, "checker-denied")

    @pytest.mark.asyncio
    async def test_all_denial_branches_share_one_shape(self) -> None:
        """One denial constructor, so the three cannot drift apart.

        Three call sites each hand-building a denial is how one of them ends
        up permissive again. They are deliberately INDISTINGUISHABLE to
        consumers — the LOG is what tells an outage apart from a refusal.
        """
        _, from_error = await _check(_Boom())
        _, from_malformed = await _check(_Malformed())
        _, from_denial = await _check(_FalsyByLen(valid=False))

        assert (
            from_error.to_dict() == from_malformed.to_dict() == (from_denial.to_dict())
        ), (
            "the denial branches produced different payloads; they must come "
            "from ONE constructor so a future edit cannot loosen just one"
        )

    @pytest.mark.asyncio
    async def test_denial_metadata_is_still_caller_safe(self) -> None:
        """The property `393f33e27` correctly insisted on, preserved.

        `find_agents_for_user` unpacks the pair unconditionally and callers
        may serialize the metadata, so hardening the payload must not turn it
        into None or a bare tuple. A fail-closed decision that crashes the
        caller is not fail-closed.
        """
        _, meta = await _check(_Boom())
        assert meta is not None
        assert isinstance(meta, AccessMetadata)
        assert meta.constraints is not None
        meta.to_dict()  # must not raise

    def test_default_constructed_metadata_is_still_a_grant(self) -> None:
        """CONTROL — true before AND after the fix.

        `AccessMetadata()` remains the GRANT shape; the fix adds an explicit
        denial constructor rather than inverting the public default, which
        would silently re-key every existing caller that builds one directly.
        """
        meta = AccessMetadata()
        assert meta.permission_level == "execute"
        assert meta.denied is False
        assert meta.to_dict()["denied"] is False


# --------------------------------------------------------------------------
# DEFECT 3 — present-but-None `constraints` must not shadow the fallback
# --------------------------------------------------------------------------


class _BothNamesConstraintsNone:
    """DECLARES `constraints` (None) while POPULATING `effective_constraints`.

    The shape a type carrying both names through a rename actually has: the
    old field survives as a None-defaulted dataclass attribute, so it is
    PRESENT, and `getattr(obj, "constraints", <fallback>)` never reaches its
    fallback.
    """

    def __init__(self) -> None:
        self.called = False

    async def verify(self, agent_id, action, user_id, organization_id):
        self.called = True
        return _result(
            valid=True,
            constraints=None,
            effective_constraints={"max_tokens": 42, "max_daily_invocations": 7},
        )


class _OnlyConstraints:
    async def verify(self, agent_id, action, user_id, organization_id):
        return _result(
            valid=True,
            constraints={"max_tokens": 11, "max_daily_invocations": 3},
        )


class _OnlyEffectiveConstraints:
    async def verify(self, agent_id, action, user_id, organization_id):
        return _result(
            valid=True,
            effective_constraints={"max_tokens": 99, "max_daily_invocations": 5},
        )


class TestConstraintsFallbackIsNotShadowed:
    @pytest.mark.asyncio
    async def test_present_but_none_constraints_falls_back(self) -> None:
        """THE TEETH. Pre-fix the user was granted with UNLIMITED constraints.

        `getattr(result, "constraints", <default>)` uses its default only when
        the attribute is ABSENT. Present-and-None returns None, fails the
        isinstance check, and the populated `effective_constraints` is never
        read — verbatim the failure the constraints fix claims to have closed.
        """
        granted, meta = await _check(_BothNamesConstraintsNone())
        assert granted is True
        assert meta.constraints.max_tokens_per_session == 42, (
            "a present-but-None `constraints` shadowed the populated "
            "`effective_constraints`; the granted user received UNLIMITED "
            f"tokens (got {meta.constraints.max_tokens_per_session!r})"
        )
        assert meta.constraints.max_daily_invocations == 7, (
            "the invocation cap was dropped for the same reason: "
            f"got {meta.constraints.max_daily_invocations!r}"
        )

    @pytest.mark.asyncio
    async def test_populated_constraints_still_wins(self) -> None:
        """CONTROL — true before AND after the fix.

        `constraints` remains the preferred name when it actually carries a
        mapping; the fix reorders the fallback, it does not swap the priority.
        """
        _, meta = await _check(_OnlyConstraints())
        assert meta.constraints.max_tokens_per_session == 11
        assert meta.constraints.max_daily_invocations == 3

    @pytest.mark.asyncio
    async def test_effective_constraints_only_still_works(self) -> None:
        """CONTROL — the documented `TrustOperations` shape, unchanged."""
        _, meta = await _check(_OnlyEffectiveConstraints())
        assert meta.constraints.max_tokens_per_session == 99
        assert meta.constraints.max_daily_invocations == 5
