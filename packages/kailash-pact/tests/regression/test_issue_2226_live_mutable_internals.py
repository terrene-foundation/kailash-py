# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2226 -- the engine handed out LIVE mutable internals.

#2224 fixed the read-only PROXY. This is a different bug class in the ENGINE,
and it survived that fix completely: the attack uses ONLY allowlisted read-only
members and never touches a denied name. A holder of ``PactEngine.governance``
could permanently grant itself an action the envelope denied::

    view.get_context(ADDR).effective_envelope.operational.allowed_actions.append(
        "wire_transfer"
    )

Measured on the unfixed tree::

    BEFORE  verify_action('wire_transfer') -> False
    BEFORE  allowed_actions               -> ['read_docs']
    AFTER   allowed_actions               -> ['read_docs', 'wire_transfer']
    AFTER   verify_action('wire_transfer') -> True
    PERSISTED in admin store              -> ['read_docs', 'wire_transfer']

Two layers combined. The store returns its own object rather than a snapshot,
and ``frozen=True`` on a pydantic model does NOT freeze its list fields -- it
blocks attribute REBINDING only. The verdict path then reads that same list,
and the TOCTOU version hash covers only version numbers and envelope IDs, so
it does not notice an in-place mutation.

The fix is at the SOURCE, not at the view: the governance value objects hold
immutable collections (``tuple`` / ``FrozenMapping``), so every caller of
``get_context`` / ``compute_envelope`` / ``get_org`` / ``get_suspension`` is
covered without any copying, and ``GovernanceContext.__reduce__`` may keep
refusing to be deep-copied.

BOTH POLES ARE ASSERTED THROUGHOUT. A test that only shows the attack now fails
cannot distinguish the fix from "the feature is broken for everyone", so every
attack assertion is paired with one showing the legitimate read still works and
the legitimate grant path still changes the verdict.

``TestNoAllowlistedMemberYieldsALiveHandle`` is the anti-staleness pin: it walks
``_ReadOnlyGovernanceView._ALLOWED`` itself rather than a hand-picked list, so a
NEW allowlist entry that returns a mutable internal fails this file -- the same
staleness failure mode #2224 found in the old blocklist.
"""

from __future__ import annotations

import datetime
import enum
from typing import Any

import pytest

from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    OperationalConstraintConfig,
    TeamConfig,
)
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.immutable import FrozenMapping
from kailash.trust.pact.suspension import PlanSuspension, SuspensionTrigger
from pact.engine import PactEngine, _ReadOnlyGovernanceView

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ORG: dict[str, Any] = {
    "org_id": "org-2226",
    "name": "Issue 2226 Org",
    "departments": [{"id": "d-eng", "name": "Engineering"}],
    "teams": [{"id": "t-backend", "name": "Backend", "agents": ["a-1"]}],
    "roles": [
        {"id": "r-cto", "name": "CTO", "heads": "d-eng"},
        {"id": "r-lead", "name": "Lead", "reports_to": "r-cto", "heads": "t-backend"},
        {"id": "r-dev", "name": "Dev", "reports_to": "r-lead"},
    ],
}

#: Positional address of the leaf role, and of its supervisor.
ADDR = "D1-R1-T1-R1-R1"
SUPERVISOR = "D1-R1-T1-R1"
TEAM_ADDR = "D1-R1-T1"
DEPT_ADDR = "D1"


@pytest.fixture
def engine() -> PactEngine:
    """A PactEngine whose leaf role may do exactly one thing: ``read_docs``."""
    eng = PactEngine(org=_ORG)
    eng._admin_governance.set_role_envelope(
        RoleEnvelope(
            id="re-2226",
            defining_role_address=SUPERVISOR,
            target_role_address=ADDR,
            envelope=ConstraintEnvelopeConfig(
                id="env-2226",
                operational=OperationalConstraintConfig(allowed_actions=["read_docs"]),
            ),
        )
    )
    return eng


# ---------------------------------------------------------------------------
# The exact attack from the issue body
# ---------------------------------------------------------------------------


class TestEnvelopeEscalationAttack:
    """The verbatim append attack, and the legitimate paths it must not break."""

    def test_append_to_allowed_actions_is_refused(self, engine: PactEngine) -> None:
        """The exact expression from the issue body must raise, not mutate."""
        view = engine.governance

        with pytest.raises(AttributeError):
            view.get_context(
                ADDR
            ).effective_envelope.operational.allowed_actions.append("wire_transfer")

    def test_denied_action_stays_denied_after_the_attack(
        self, engine: PactEngine
    ) -> None:
        """POLE 1 (attack): the verdict must be unchanged, before and after."""
        view = engine.governance
        assert view.verify_action(ADDR, "wire_transfer", {}).allowed is False

        with pytest.raises(AttributeError):
            view.get_context(
                ADDR
            ).effective_envelope.operational.allowed_actions.append("wire_transfer")

        assert view.verify_action(ADDR, "wire_transfer", {}).allowed is False
        assert view.get_context(
            ADDR
        ).effective_envelope.operational.allowed_actions == ("read_docs",)

    def test_admin_store_is_not_mutated_by_the_attack(self, engine: PactEngine) -> None:
        """POLE 1 (attack): the persisted envelope must be untouched.

        The original attack persisted -- the mutation was visible in the
        admin store, which is what made the escalation permanent rather
        than scoped to one returned object.
        """
        view = engine.governance
        with pytest.raises(AttributeError):
            view.get_context(
                ADDR
            ).effective_envelope.operational.allowed_actions.append("wire_transfer")

        stored = engine._admin_governance._envelope_store.get_role_envelope(ADDR)
        assert stored.envelope.operational.allowed_actions == ("read_docs",)

    def test_allowed_action_still_permitted(self, engine: PactEngine) -> None:
        """POLE 2 (legitimate): the envelope must still PERMIT what it allows."""
        assert engine.governance.verify_action(ADDR, "read_docs", {}).allowed is True

    def test_reading_the_envelope_still_works(self, engine: PactEngine) -> None:
        """POLE 2 (legitimate): every read path on the frozen value object."""
        actions = engine.governance.get_context(
            ADDR
        ).effective_envelope.operational.allowed_actions

        assert "read_docs" in actions
        assert len(actions) == 1
        assert list(actions) == ["read_docs"]
        assert set(actions) == {"read_docs"}

    def test_authorized_grant_through_the_admin_path_still_works(
        self, engine: PactEngine
    ) -> None:
        """POLE 2 (legitimate): the SUPPORTED way to widen must still widen.

        Without this the suite could not tell the fix from "envelopes can no
        longer be changed at all".
        """
        admin = engine._admin_governance
        assert (
            engine.governance.verify_action(ADDR, "wire_transfer", {}).allowed is False
        )

        admin.set_role_envelope(
            RoleEnvelope(
                id="re-2226-b",
                defining_role_address=SUPERVISOR,
                target_role_address=ADDR,
                envelope=ConstraintEnvelopeConfig(
                    id="env-2226-b",
                    operational=OperationalConstraintConfig(
                        allowed_actions=["read_docs", "wire_transfer"]
                    ),
                ),
            )
        )

        assert (
            engine.governance.verify_action(ADDR, "wire_transfer", {}).allowed is True
        )


# ---------------------------------------------------------------------------
# The other live handles named in the issue
# ---------------------------------------------------------------------------


class TestOtherEnvelopeDimensionsAreImmutable:
    """Every sequence dimension, not only the one the attack used."""

    @pytest.mark.parametrize(
        "dimension,field",
        [
            ("operational", "allowed_actions"),
            ("operational", "blocked_actions"),
            ("temporal", "blackout_periods"),
            ("data_access", "read_paths"),
            ("data_access", "write_paths"),
            ("data_access", "blocked_data_types"),
            ("communication", "allowed_channels"),
        ],
    )
    def test_dimension_field_refuses_append(
        self, engine: PactEngine, dimension: str, field: str
    ) -> None:
        envelope = engine.governance.get_context(ADDR).effective_envelope
        value = getattr(getattr(envelope, dimension), field)

        assert not isinstance(value, list)
        with pytest.raises(AttributeError):
            value.append("injected")


class TestTeamConfigIsFrozenLikeItsSibling:
    """``TeamConfig`` had no ``frozen=True`` while ``DepartmentConfig`` did.

    Freezing alone is NOT the fix and this class asserts why: ``DepartmentConfig``
    was ALREADY frozen and was still exploitable through ``.teams.append(...)``,
    because ``frozen=True`` does not freeze a list field. Both the model and its
    collections have to be immutable.
    """

    def test_team_config_is_frozen(self) -> None:
        assert TeamConfig.model_config.get("frozen") is True
        assert DepartmentConfig.model_config.get("frozen") is True

    def test_team_attributes_cannot_be_rebound_through_the_view(
        self, engine: PactEngine
    ) -> None:
        team = engine.governance.get_node(TEAM_ADDR).team
        with pytest.raises(Exception):
            team.name = "pwned"
        assert engine.governance.get_node(TEAM_ADDR).team.name == "Backend"

    def test_team_roster_cannot_be_appended_to(self, engine: PactEngine) -> None:
        team = engine.governance.get_node(TEAM_ADDR).team
        with pytest.raises(AttributeError):
            team.agents.append("attacker-agent")
        assert "attacker-agent" not in engine.governance.get_node(TEAM_ADDR).team.agents

    def test_team_metadata_cannot_be_written(self, engine: PactEngine) -> None:
        team = engine.governance.get_node(TEAM_ADDR).team
        assert isinstance(team.metadata, FrozenMapping)
        with pytest.raises(TypeError):
            team.metadata["backdoor"] = True
        with pytest.raises(TypeError):
            team.metadata.update({"backdoor": True})
        assert "backdoor" not in engine.governance.get_node(TEAM_ADDR).team.metadata

    def test_department_teams_cannot_be_appended_to(self, engine: PactEngine) -> None:
        """The frozen-sibling case: frozen=True did NOT close this."""
        dept = engine.governance.get_node(DEPT_ADDR).department
        with pytest.raises(AttributeError):
            dept.teams.append("t-smuggled")
        assert (
            "t-smuggled" not in engine.governance.get_node(DEPT_ADDR).department.teams
        )

    def test_team_reads_still_work(self, engine: PactEngine) -> None:
        """POLE 2: the team config must still be readable and constructible."""
        team = engine.governance.get_node(TEAM_ADDR).team
        assert team.id == "t-backend"
        assert team.name == "Backend"
        # Empty because the org-dict loader derives team membership from roles
        # and does not carry a team's `agents` list into the compiled config --
        # pre-existing loader behaviour, unrelated to #2226. The direct
        # construction below is what exercises a populated roster.
        assert tuple(team.agents) == ()
        assert dict(team.metadata) == {}

        built = TeamConfig(
            id="t-new", name="New", workspace="ws", agents=["x"], metadata={"k": "v"}
        )
        assert built.agents == ("x",)
        assert built.metadata["k"] == "v"
        assert built.model_dump()["agents"] == ("x",)


class TestSuspensionSnapshotIsImmutable:
    """``get_suspension`` returns the object the suspension gate reads."""

    def test_snapshot_cannot_be_written_through_the_view(
        self, engine: PactEngine
    ) -> None:
        engine._admin_governance.suspend_plan(
            plan_id="plan-1",
            role_address=ADDR,
            trigger=SuspensionTrigger.BUDGET,
            snapshot={"step": 3},
        )
        snapshot = engine.governance.get_suspension("plan-1").snapshot

        with pytest.raises(TypeError):
            snapshot["step"] = 99
        with pytest.raises(TypeError):
            snapshot.clear()

        assert engine.governance.get_suspension("plan-1").snapshot["step"] == 3

    def test_snapshot_reads_and_to_dict_still_work(self, engine: PactEngine) -> None:
        """POLE 2: reads work, and ``to_dict`` still yields a MUTABLE plain dict."""
        suspension = PlanSuspension(
            plan_id="p",
            trigger=SuspensionTrigger.BUDGET,
            suspended_at="2026-01-01T00:00:00Z",
            resume_conditions=(),
            snapshot={"step": 3},
        )
        assert suspension.snapshot["step"] == 3
        assert dict(suspension.snapshot) == {"step": 3}

        as_dict = suspension.to_dict()
        as_dict["snapshot"]["step"] = 99  # caller owns the result -- must not raise
        assert suspension.snapshot["step"] == 3


# ---------------------------------------------------------------------------
# Anti-staleness pin over the whole allowlist
# ---------------------------------------------------------------------------

_IMMUTABLE_SCALARS = (
    str,
    int,
    float,
    bool,
    bytes,
    type(None),
    datetime.datetime,
    datetime.date,
    datetime.time,
    enum.Enum,
)


def _mutable_containers(
    obj: Any, path: str, seen: set[int], depth: int = 0
) -> list[str]:
    """Every in-place-mutable container reachable from ``obj`` by attribute reads.

    A ``dict``/``list`` SUBCLASS that refuses mutation is not reported -- the
    property under test is "can a caller change this", not "what type is it".
    """
    if depth > 5 or id(obj) in seen or isinstance(obj, _IMMUTABLE_SCALARS):
        return []
    seen.add(id(obj))
    found: list[str] = []

    if isinstance(obj, (list, dict, set)):
        try:
            if isinstance(obj, dict):
                obj["__probe__"] = 1
                del obj["__probe__"]
            elif isinstance(obj, list):
                obj.append("__probe__")
                obj.pop()
            else:
                obj.add("__probe__")
                obj.discard("__probe__")
            found.append(f"{path} ({type(obj).__name__})")
        except (TypeError, AttributeError):
            pass
        values = obj.values() if isinstance(obj, dict) else obj
        for i, item in enumerate(list(values)[:10]):
            found += _mutable_containers(item, f"{path}[{i}]", seen, depth + 1)
        return found

    if isinstance(obj, (tuple, frozenset)):
        for i, item in enumerate(list(obj)[:10]):
            found += _mutable_containers(item, f"{path}[{i}]", seen, depth + 1)
        return found

    names: set[str] = set()
    if hasattr(type(obj), "model_fields"):
        names |= set(type(obj).model_fields)
    if hasattr(obj, "__dataclass_fields__"):
        names |= set(obj.__dataclass_fields__)
    for name in sorted(names):
        try:
            found += _mutable_containers(
                getattr(obj, name), f"{path}.{name}", seen, depth + 1
            )
        except Exception:  # noqa: BLE001 -- a property that raises exposes nothing
            continue
    return found


class TestNoAllowlistedMemberYieldsALiveHandle:
    """Walks ``_ALLOWED`` itself, so a NEW leaky entry fails this test.

    ``list_roles`` and ``verify_action`` build a fresh list/dict per call, so a
    caller mutating those changes nothing in the engine -- they are excluded by
    NAME with that reason recorded, not by silently passing.
    """

    #: Members whose return value is rebuilt per call, so mutating it is inert.
    #: Measured, not assumed: mutating each and re-reading shows no change.
    _RETURNS_FRESH_OBJECTS = {"list_roles", "verify_action", "check_access"}

    def test_every_other_allowlisted_member_returns_only_immutables(
        self, engine: PactEngine
    ) -> None:
        engine._admin_governance.suspend_plan(
            plan_id="plan-1",
            role_address=ADDR,
            trigger=SuspensionTrigger.BUDGET,
            snapshot={"step": 3},
        )
        view = engine.governance
        calls = {
            "org_name": lambda: view.org_name,
            "get_org": lambda: view.get_org(),
            "get_node": lambda: view.get_node(TEAM_ADDR),
            "get_context": lambda: view.get_context(ADDR),
            "compute_envelope": lambda: view.compute_envelope(ADDR),
            "get_suspension": lambda: view.get_suspension("plan-1"),
            "get_vacancy_designation": lambda: view.get_vacancy_designation(ADDR),
            "verify_audit_integrity": lambda: view.verify_audit_integrity(),
        }

        unclassified = (
            _ReadOnlyGovernanceView._ALLOWED - set(calls) - self._RETURNS_FRESH_OBJECTS
        )
        assert not unclassified, (
            f"_ReadOnlyGovernanceView._ALLOWED gained {sorted(unclassified)} since "
            f"this test was written. Classify each: add it to `calls` so its return "
            f"value is checked for live mutable handles (#2226), or to "
            f"_RETURNS_FRESH_OBJECTS with evidence it rebuilds per call."
        )

        leaks: list[str] = []
        for name, call in calls.items():
            result = call()
            if result is None:
                continue
            leaks += _mutable_containers(result, name, set())

        assert leaks == [], (
            f"These allowlisted members hand back containers a read-only holder "
            f"can mutate in place, changing governance state without an audit "
            f"record (#2226): {leaks}"
        )

    def test_the_excluded_members_really_do_rebuild(self, engine: PactEngine) -> None:
        """The exclusion above must be measured, not asserted.

        If ``list_roles`` ever starts returning the engine's own list, this
        fails and the exclusion has to be revisited.
        """
        view = engine.governance

        roles = view.list_roles()
        roles.append("smuggled")
        assert "smuggled" not in view.list_roles()

        verdict = view.verify_action(ADDR, "read_docs", {})
        verdict.audit_details["smuggled"] = True
        assert "smuggled" not in view.verify_action(ADDR, "read_docs", {}).audit_details


class TestFrozenMappingResidual:
    """Pins the documented limit of ``FrozenMapping`` so it stays known.

    A ``dict`` subclass cannot block an UNBOUND base-class call. This is the
    same class of limitation ``readonly_proxy`` documents about
    ``object.__getattribute__``: a caller writing ``dict.__setitem__(m, k, v)``
    is executing arbitrary Python, not reading an attribute, and both issues
    are scoped to ordinary attribute access.

    It is asserted here so that (a) nobody believes the mapping fields are
    absolutely immune, and (b) if a future change adopts a type that DOES close
    it, this test fails and forces the docstring to be corrected with it.
    """

    def test_ordinary_mutation_is_refused(self) -> None:
        mapping = FrozenMapping({"a": 1})
        for mutate in (
            lambda: mapping.__setitem__("x", 1),
            lambda: mapping.update({"x": 1}),
            lambda: mapping.clear(),
            lambda: mapping.pop("a"),
            lambda: mapping.setdefault("x", 1),
        ):
            with pytest.raises(TypeError):
                mutate()
        assert dict(mapping) == {"a": 1}

    def test_unbound_base_call_is_the_known_residual(self) -> None:
        """NOT closable for a dict subclass. Documented, not fixed."""
        mapping = FrozenMapping({"a": 1})
        dict.__setitem__(mapping, "x", 1)
        assert mapping["x"] == 1

    def test_sequence_dimensions_have_no_equivalent_escape(self) -> None:
        """The fields the #2226 attack actually used are closed completely."""
        actions = OperationalConstraintConfig(allowed_actions=["read"]).allowed_actions

        assert isinstance(actions, tuple)
        assert not hasattr(actions, "__setitem__")
        assert not hasattr(actions, "append")
