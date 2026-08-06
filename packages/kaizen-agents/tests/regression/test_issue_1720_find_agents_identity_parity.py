# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Round-3 MED-4: the THIRD identity-taking surface never learned the guard.

`_resolve_identity_scope` refuses a BLANK identity, and its stated rationale is
that a checker is free to read an empty organization as "unscoped" and GRANT::

    a lax checker may read an empty organization as "unscoped" and grant

Both SKILL-metadata surfaces (`get_skill_metadata`, `list_skill_metadata`)
route through it. `find_agents_for_user` — the third public identity-taking
surface in the same class, and the one returning the RICHER payload
(`AgentWithAccess`, which carries `AccessMetadata` including the permission
level and the constraint envelope) — applied NEITHER check. It forwarded the
blank pair straight to `_check_user_access` and on to the caller-supplied
checker: verbatim the scenario the rationale above describes.

It is also the MEDIATED PATH `list_skill_metadata` DELEGATES to, so the guard
belongs in the CALLEE. Putting it only in the two callers fixes the two
instances; putting it in the callee fixes the class.

THE ASYMMETRY THAT IS NOT AN INCONSISTENCY. `get_skill_metadata` and
`list_skill_metadata` declare `user_id: str | None = None`, so "omit both" is a
pre-existing SUPPORTED call shape and stays reachable (loud, once per instance
per surface). `find_agents_for_user` declares `user_id: str` with NO default,
so an all-`None` call was never a supported shape — there is no unfiltered form
to preserve and the disposition is to REFUSE. Fail closed, per
`zero-tolerance.md` Rule 3: a degenerate identity must never widen access.

This is the FIFTH recurrence of the Enforcement-Surface Parity class on this
branch, so the parity test at the bottom asserts the STRUCTURAL property —
every public identity-taking surface routes through ONE shared callable — not
merely that today's three behave alike.
"""

from __future__ import annotations

import pytest

from kaizen_agents.patterns import discovery as discovery_mod
from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery

pytestmark = pytest.mark.regression


class _Agent:
    name = "PayrollAgent"
    description = "Runs payroll"
    agent_id = "agent-1"
    _a2a_card = {"capabilities": ["read_salaries", "issue_payments"]}


class _Meta:
    agent_id = "agent-1"
    agent = _Agent()


class _RecordingRegistry:
    """Records whether the registry was reached at all.

    A boundary refusal must happen BEFORE any registry work: the whole point of
    refusing a degenerate identity is that no lookup is performed under it.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def list_agents(self, status_filter=None):
        self.calls.append("list_agents")
        return [_Meta()]

    async def find_agents_by_capability(self, capability, status_filter=None):
        self.calls.append("find_agents_by_capability")
        return [_Meta()]

    async def get_agent(self, agent_id):
        self.calls.append("get_agent")
        return _Meta() if agent_id == "agent-1" else None


class _LaxChecker:
    """The checker the rationale warns about: an empty scope reads as GRANT.

    Deliberately NOT a denying checker. A denying checker would make every
    assertion below pass for the wrong reason — the agent list would be empty
    because the checker said no, not because the boundary refused. This one
    GRANTS exactly the degenerate scope the guard exists to intercept, so if the
    guard is absent the test sees a populated result rather than an exception.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def verify(self, agent_id, action, user_id, organization_id):
        self.calls.append((agent_id, action, user_id, organization_id))
        granted = not (user_id or "").strip() or not (organization_id or "").strip()
        return type("R", (), {"valid": granted or user_id == "alice"})()


class _FalsyOrgId(str):
    """Present, non-empty, falsy — the identity-vs-truthiness discriminator."""

    def __bool__(self) -> bool:  # pragma: no cover - exercised via the guard
        return False


def _discovery(checker=None):
    registry = _RecordingRegistry()
    return UserFilteredAgentDiscovery(registry, permission_checker=checker), registry


class TestFindAgentsForUserRefusesADegenerateIdentity:
    """THE TEETH. Pre-fix every case below reached the lax checker and GRANTED."""

    @pytest.mark.parametrize(
        "user_id,organization_id,kind",
        [
            pytest.param("", "", "BLANK", id="both-blank"),
            pytest.param("alice", "", "BLANK", id="blank-org"),
            pytest.param("", "org-1", "BLANK", id="blank-user"),
            pytest.param("alice", "   ", "BLANK", id="whitespace-org"),
            pytest.param("\t", "org-1", "BLANK", id="whitespace-user"),
            pytest.param("alice", None, "PARTIAL", id="none-org"),
            pytest.param(None, "org-1", "PARTIAL", id="none-user"),
            pytest.param(None, None, "MISSING", id="no-identity-at-all"),
        ],
    )
    @pytest.mark.asyncio
    async def test_degenerate_identity_raises_instead_of_reaching_the_checker(
        self, user_id, organization_id, kind
    ) -> None:
        checker = _LaxChecker()
        d, registry = _discovery(checker)

        with pytest.raises(ValueError) as excinfo:
            await d.find_agents_for_user(user_id, organization_id)

        assert kind in str(excinfo.value), (
            "the message must distinguish a MISSING half from a BLANK one so "
            "the caller can tell which mistake they made"
        )
        assert "find_agents_for_user" in str(
            excinfo.value
        ), "the message must name the surface that refused"
        assert checker.calls == [], (
            "a degenerate identity reached the permission checker; a lax "
            "checker reads an empty organization as 'unscoped' and grants"
        )
        assert registry.calls == [], (
            "the registry was queried under a degenerate identity — the "
            "refusal must happen at the boundary, before any lookup"
        )

    @pytest.mark.asyncio
    async def test_the_capability_filter_path_refuses_too(self) -> None:
        """The `capability_filter` branch is a SECOND route into the same body.

        It queries a different registry method, so a guard placed inside the
        else-branch would leave this one open.
        """
        checker = _LaxChecker()
        d, registry = _discovery(checker)

        with pytest.raises(ValueError, match="BLANK"):
            await d.find_agents_for_user("", "", capability_filter="payroll")

        assert registry.calls == []
        assert checker.calls == []


class TestTheGuardDiscriminatesIdentityFromTruthiness:
    """The guard must not become the truthiness test it replaced."""

    @pytest.mark.asyncio
    async def test_a_present_but_falsy_org_id_is_MEDIATED_not_refused(self) -> None:
        checker = _LaxChecker()
        d, _ = _discovery(checker)

        found = await d.find_agents_for_user("alice", _FalsyOrgId("org-1"))

        assert checker.calls, (
            "a present, non-empty, falsy organization_id was refused or "
            "bypassed — the guard is testing truthiness, not identity"
        )
        assert len(found) == 1

    @pytest.mark.asyncio
    async def test_a_real_identity_still_returns_the_agents(self) -> None:
        """The fix must not deny a legitimately permitted caller."""
        d, _ = _discovery(_LaxChecker())
        found = await d.find_agents_for_user("alice", "org-1")
        assert len(found) == 1
        assert found[0].agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_list_skill_metadata_still_delegates_successfully(self) -> None:
        """The delegating caller must survive the callee growing a guard.

        `list_skill_metadata` narrows through `_resolve_identity_scope` and then
        calls `find_agents_for_user` with the narrowed pair; if the new callee
        guard were stricter than the caller's, this would now raise.
        """
        d, _ = _discovery(_LaxChecker())
        skills = await d.list_skill_metadata(user_id="alice", organization_id="org-1")
        assert len(skills) == 1

    @pytest.mark.asyncio
    async def test_the_unscoped_skill_metadata_path_is_still_reachable(
        self, caplog
    ) -> None:
        """The optional-identity surfaces keep their documented unfiltered form.

        `find_agents_for_user` gaining a refusal must NOT propagate into the two
        surfaces whose identity parameters are defaulted — that would be a
        backward-compat break dressed as a security fix.
        """
        import logging

        d, _ = _discovery()
        with caplog.at_level(logging.WARNING):
            skills = await d.list_skill_metadata()

        assert len(skills) == 1
        assert any(
            r.getMessage() == "discovery.list_skill_metadata.unfiltered"
            for r in caplog.records
        )


class TestEveryIdentitySurfaceRoutesThroughOnePredicate:
    """Enforcement-Surface Parity, asserted STRUCTURALLY.

    Behavioural parity ("all three refuse a blank") is what the previous two
    attempts asserted, and both times a fourth call shape drifted. Substituting
    the shared predicate and counting the calls pins the ROUTING, so a future
    surface that re-implements the check inline fails here.
    """

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(
                lambda d: d.find_agents_for_user("alice", "org-1"),
                id="find_agents_for_user",
            ),
            pytest.param(
                lambda d: d.get_skill_metadata(
                    "agent-1", user_id="alice", organization_id="org-1"
                ),
                id="get_skill_metadata",
            ),
            pytest.param(
                lambda d: d.list_skill_metadata(
                    user_id="alice", organization_id="org-1"
                ),
                id="list_skill_metadata",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_each_public_surface_calls_the_shared_predicate(
        self, call, monkeypatch
    ) -> None:
        seen: list[str] = []
        real = discovery_mod._require_identity_or_raise

        def _spy(user_id, organization_id, *, surface, omission_remedy):
            seen.append(surface)
            return real(
                user_id,
                organization_id,
                surface=surface,
                omission_remedy=omission_remedy,
            )

        monkeypatch.setattr(discovery_mod, "_require_identity_or_raise", _spy)

        d, _ = _discovery(_LaxChecker())
        await call(d)

        assert seen, (
            "this surface takes a caller identity but never reached the shared "
            "predicate — it is re-implementing (or omitting) the check inline"
        )

    def test_the_predicate_is_the_only_blank_check_in_the_module(self) -> None:
        """One implementation, not three that must agree.

        `security.md` § Credential Decode Helpers states the general form: a
        check that must hold at N surfaces lives in ONE callable, because N
        copies drift. This asserts the count directly against the source rather
        than trusting the three behavioural tests above to notice a fourth copy.
        """
        import inspect

        source = inspect.getsource(discovery_mod)
        # `.strip()` on a caller-supplied identity is the blank test's
        # signature. Exactly one occurrence: inside the shared predicate.
        occurrences = source.count("not value.strip()")
        assert occurrences == 1, (
            f"found {occurrences} blank-identity checks; the check must exist "
            "in exactly one callable so the surfaces cannot drift apart"
        )
