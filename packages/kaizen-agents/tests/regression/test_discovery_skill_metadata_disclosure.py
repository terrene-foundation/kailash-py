# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Round-2 HIGH-2 + MEDIUM-3: the skill-metadata surfaces disclosed unmediated.

Both methods return :class:`AgentSkillMetadata`, whose payload includes the
agent's ``input_schema`` (derived from the signature by ``_extract_input_schema``)
and its ``capabilities`` — the same disclosure class as the gated-``inputSchema``
MCP leak closed earlier in this issue. Neither surface mediated it.

HIGH-2 — ``list_skill_metadata`` fell OPEN on a FALSY identity::

    if user_id and organization_id:          # TRUTHINESS
        agents = await self.find_agents_for_user(user_id, organization_id)
    else:
        agents = await self._registry.list_agents()     # NO permission check

So ``list_skill_metadata(user_id="alice", organization_id="")`` — or ``None``,
or any organization id whose ``__bool__`` is False — took the else branch and
returned metadata for EVERY registered agent, with no permission check and no
warning. A caller who supplied a partial identity got MORE than a caller who
supplied a complete one.

This is the SAME truthiness-vs-identity defect that
``_check_user_access`` was fixed for (``if self._permission_checker is not
None:``), left live at a sibling surface in the same file — the
``security.md`` § Enforcement-Surface Parity failure exactly.

MEDIUM-3 — ``get_skill_metadata`` performed NO permission check at all. It took
no identity parameter, so every caller was unmediated by construction, and it
sat between two methods that DO mediate.

THE FIX, ONE SHARED PREDICATE FOR BOTH SURFACES
(``_resolve_identity_scope``), so the two cannot drift apart again:

* BOTH identities supplied (``is not None``, never truthiness) → MEDIATED.
  ``organization_id=""`` now reaches the permission checker rather than
  bypassing it; the checker is the authority on whether an empty org is valid.
* EXACTLY ONE supplied → ``ValueError``. Fail CLOSED: a half-identity never
  silently widens to "everything".
* NEITHER supplied → the unfiltered path stays reachable for the internal /
  single-tenant callers that predate this change, but is now LOUD (a one-time
  WARN per instance per surface, naming the protection that is OFF and how to
  turn it on) instead of silent. `security.md` § "Secure-Default For A New
  Security Feature" names this the sanctioned shape when backward-compat
  forbids on-by-default, and `zero-tolerance.md` Rule 3 requires the wide path
  to be loud.
"""

from __future__ import annotations

import logging

import pytest

from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery

pytestmark = pytest.mark.regression


class InputField:
    """The class NAME is what ``_extract_input_schema`` keys on.

    Named without the leading underscore deliberately: the extractor matches
    ``field_value.__class__.__name__ == "InputField"`` exactly, so a ``_``-
    prefixed fake yields ``input_schema=None`` and the disclosure premise below
    would assert nothing.
    """

    desc = "the caller's private prompt field"
    default = None


class _Signature:
    secret_field = InputField()


class _Agent:
    name = "PayrollAgent"
    description = "Runs payroll"
    agent_id = "agent-1"
    _a2a_card = {"capabilities": ["read_salaries", "issue_payments"]}
    _signature = _Signature()


class _Meta:
    """Stand-in for AgentMetadata; `agent` + `agent_id` are what is read."""

    agent_id = "agent-1"
    agent = _Agent()


class _StubRegistry:
    """`list_agents` is the unfiltered path; `get_agent` the single-agent one."""

    async def list_agents(self, status_filter=None):
        return [_Meta()]

    async def get_agent(self, agent_id):
        return _Meta() if agent_id == "agent-1" else None


class _DenyingChecker:
    """A wired checker that denies everything. Never falsy, never None."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def verify(self, agent_id, action, user_id, organization_id):
        self.calls.append((agent_id, action, user_id, organization_id))
        return type("R", (), {"valid": False})()


class _FalsyOrgId(str):
    """An organization id that is NOT None but IS falsy.

    The realistic shape is the empty string, but a `str` subclass overriding
    `__bool__` proves the guard tests IDENTITY rather than truth even for a
    non-empty value — so the test cannot pass merely because `""` is empty.
    """

    def __bool__(self) -> bool:  # pragma: no cover - exercised via the guard
        return False


def _discovery(checker=None):
    return UserFilteredAgentDiscovery(_StubRegistry(), permission_checker=checker)


# ---------------------------------------------------------------------------
# HIGH-2 — the falsy-identity fall-open
# ---------------------------------------------------------------------------


class TestListSkillMetadataFailsClosedOnPartialIdentity:
    """THE TEETH. Pre-fix each of these returned EVERY agent's skill metadata."""

    @pytest.mark.parametrize(
        "org_id,kind",
        [
            pytest.param("", "BLANK", id="empty-string-org"),
            pytest.param("   ", "BLANK", id="whitespace-org"),
            pytest.param(None, "PARTIAL", id="none-org"),
        ],
    )
    @pytest.mark.asyncio
    async def test_partial_or_blank_identity_raises_instead_of_widening(
        self, org_id, kind
    ) -> None:
        """The reviewer's literal attack: `organization_id=""`.

        Pre-fix each of these took the unfiltered branch and returned every
        registered agent's skill metadata. Both dispositions are refusals; the
        message distinguishes a MISSING half from a BLANK one so the caller can
        tell which mistake they made.
        """
        checker = _DenyingChecker()
        d = _discovery(checker)

        with pytest.raises(ValueError, match="organization_id") as excinfo:
            await d.list_skill_metadata(user_id="alice", organization_id=org_id)

        assert kind in str(excinfo.value)
        assert checker.calls == [], (
            "a partial or blank identity must be REFUSED at the boundary, not "
            "routed to the checker under a degenerate scope"
        )

    @pytest.mark.asyncio
    async def test_partial_identity_the_other_way_round_also_raises(self) -> None:
        d = _discovery(_DenyingChecker())
        with pytest.raises(ValueError, match="user_id"):
            await d.list_skill_metadata(user_id=None, organization_id="org-1")

    @pytest.mark.asyncio
    async def test_a_falsy_but_present_org_id_is_MEDIATED_not_bypassed(self) -> None:
        """The identity-vs-truthiness discriminator.

        `_FalsyOrgId("org-1")` is a non-empty, present organization id whose
        `__bool__` is False. Under the old truthiness guard it took the
        unfiltered branch and disclosed everything. Under an identity guard it
        is supplied, so it goes to the checker — which denies.
        """
        checker = _DenyingChecker()
        d = _discovery(checker)

        skills = await d.list_skill_metadata(
            user_id="alice", organization_id=_FalsyOrgId("org-1")
        )

        assert checker.calls, (
            "a present-but-falsy organization_id skipped the permission check "
            "entirely — the guard is testing truthiness, not identity"
        )
        assert skills == [], "the checker denied; no skill metadata may be returned"

    @pytest.mark.asyncio
    async def test_full_identity_denial_returns_nothing(self) -> None:
        d = _discovery(_DenyingChecker())
        assert await d.list_skill_metadata(user_id="a", organization_id="o") == []

    @pytest.mark.asyncio
    async def test_unscoped_call_still_works_but_is_loud(self, caplog) -> None:
        """Backward-compat path: reachable, no longer silent."""
        d = _discovery()
        with caplog.at_level(logging.WARNING):
            skills = await d.list_skill_metadata()

        assert len(skills) == 1, "the unscoped path must keep working"
        assert any(
            r.getMessage() == "discovery.list_skill_metadata.unfiltered"
            for r in caplog.records
        ), (
            "the unfiltered path returns every agent's input_schema and "
            "capabilities with no permission check and said nothing about it"
        )

    @pytest.mark.asyncio
    async def test_the_unfiltered_warning_fires_once_per_instance(self, caplog) -> None:
        """Loud, not spam (`observability.md` MUST NOT log-spam in hot loops)."""
        d = _discovery()
        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                await d.list_skill_metadata()

        assert (
            sum(
                r.getMessage() == "discovery.list_skill_metadata.unfiltered"
                for r in caplog.records
            )
            == 1
        )


# ---------------------------------------------------------------------------
# MEDIUM-3 — the wholly unmediated single-agent surface
# ---------------------------------------------------------------------------


class TestGetSkillMetadataMediatesWhenScoped:
    """Pre-fix this method had no identity parameter and no check at all."""

    @pytest.mark.asyncio
    async def test_denied_caller_gets_none_not_the_schema(self) -> None:
        checker = _DenyingChecker()
        d = _discovery(checker)

        skill = await d.get_skill_metadata(
            "agent-1", user_id="alice", organization_id="org-1"
        )

        assert checker.calls, "the scoped call never consulted the checker"
        assert skill is None, (
            "a denied caller received the agent's full skill metadata — "
            "input_schema, capabilities and suggested prompts included"
        )

    @pytest.mark.asyncio
    async def test_denial_is_indistinguishable_from_absent(self) -> None:
        """Denial must not confirm the agent exists."""
        d = _discovery(_DenyingChecker())
        denied = await d.get_skill_metadata("agent-1", user_id="a", organization_id="o")
        missing = await d.get_skill_metadata(
            "no-such-agent", user_id="a", organization_id="o"
        )
        assert denied is missing is None

    @pytest.mark.asyncio
    async def test_partial_identity_raises(self) -> None:
        d = _discovery(_DenyingChecker())
        with pytest.raises(ValueError, match="organization_id"):
            await d.get_skill_metadata("agent-1", user_id="alice")

    @pytest.mark.asyncio
    async def test_blank_identity_raises_before_the_registry_is_touched(self) -> None:
        d = _discovery(_DenyingChecker())
        with pytest.raises(ValueError, match="BLANK"):
            await d.get_skill_metadata("agent-1", user_id="alice", organization_id="")

    @pytest.mark.asyncio
    async def test_unscoped_call_still_works_but_is_loud(self, caplog) -> None:
        d = _discovery()
        with caplog.at_level(logging.WARNING):
            skill = await d.get_skill_metadata("agent-1")

        assert skill is not None, "the unscoped path must keep working"
        assert skill.input_schema is not None, (
            "premise check: this surface really does carry the signature-derived "
            "input schema, or the disclosure finding would be moot"
        )
        assert any(
            r.getMessage() == "discovery.get_skill_metadata.unfiltered"
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_granted_caller_still_receives_the_metadata(self) -> None:
        """The fix must not deny a legitimately permitted caller."""

        class _Allowing:
            async def verify(self, agent_id, action, user_id, organization_id):
                return type("R", (), {"valid": True, "constraints": {}})()

        d = _discovery(_Allowing())
        skill = await d.get_skill_metadata(
            "agent-1", user_id="alice", organization_id="org-1"
        )
        assert skill is not None
        assert skill.id == "agent-1"


# ---------------------------------------------------------------------------
# Enforcement-Surface Parity — ONE predicate, both surfaces
# ---------------------------------------------------------------------------


class TestBothSurfacesShareOneIdentityPredicate:
    """The two surfaces must not be able to drift apart again.

    The originating defect was one surface learning a control the sibling in
    the same file did not. Asserting they route through the SAME callable is
    what makes a future one-sided edit fail here rather than in production.
    """

    @pytest.mark.asyncio
    async def test_both_surfaces_reject_the_same_partial_identity(self) -> None:
        d = _discovery(_DenyingChecker())
        with pytest.raises(ValueError):
            await d.list_skill_metadata(user_id="alice", organization_id=None)
        with pytest.raises(ValueError):
            await d.get_skill_metadata("agent-1", user_id="alice", organization_id=None)

    @pytest.mark.asyncio
    async def test_both_surfaces_mediate_a_falsy_present_org(self) -> None:
        checker = _DenyingChecker()
        d = _discovery(checker)
        org = _FalsyOrgId("org-1")

        assert await d.list_skill_metadata(user_id="a", organization_id=org) == []
        assert (
            await d.get_skill_metadata("agent-1", user_id="a", organization_id=org)
            is None
        )
        assert len(checker.calls) == 2, "both surfaces must reach the checker"
