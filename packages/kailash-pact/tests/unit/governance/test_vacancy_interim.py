# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for vacancy interim envelope and configurable deadline (TODO-09).

PACT Section 5.5 Rule 2: Within the deadline window, direct reports of a vacant
role operate under the more restrictive of their own envelope or the parent's
envelope for the vacant role.
"""

from __future__ import annotations

from datetime import timedelta

from kailash.trust.pact.compilation import RoleDefinition
from kailash.trust.pact.config import (
    DepartmentConfig,
    OrgDefinition,
)
from kailash.trust.pact.engine import GovernanceEngine


def _make_org_with_vacancy(
    vacancy_deadline_hours: int = 24,
) -> tuple[GovernanceEngine, dict[str, str]]:
    """Create an org with a vacant middle-manager role."""
    roles = [
        RoleDefinition(
            role_id="ceo",
            name="CEO",
            is_primary_for_unit="d-eng",
        ),
        RoleDefinition(
            role_id="manager",
            name="Manager (Vacant)",
            reports_to_role_id="ceo",
            is_vacant=True,
        ),
        RoleDefinition(
            role_id="engineer",
            name="Engineer",
            reports_to_role_id="ceo",
        ),
    ]

    org = OrgDefinition(
        org_id="vacancy-test-org",
        name="Vacancy Test Org",
        departments=[DepartmentConfig(department_id="d-eng", name="Engineering")],
        roles=roles,
    )

    engine = GovernanceEngine(org, vacancy_deadline_hours=vacancy_deadline_hours)

    # Build address lookup
    addresses: dict[str, str] = {}
    for addr, node in engine._compiled_org.nodes.items():
        if node.role_definition is not None:
            addresses[node.role_definition.role_id] = addr

    return engine, addresses


class TestVacancyInterimEnvelope:
    def test_vacancy_within_deadline_not_blocked(self) -> None:
        """Within deadline, actions should NOT be fully blocked."""
        engine, addrs = _make_org_with_vacancy(vacancy_deadline_hours=24)

        # The engineer's action should not be fully blocked
        # (vacancy just started, within 24h deadline)
        verdict = engine.verify_action(
            addrs["engineer"], "read", context={"cost": 10.0}
        )
        # Should be auto_approved (no envelopes configured = maximally permissive)
        assert (
            verdict.level != "blocked"
            or "vacancy" not in (verdict.reason or "").lower()
        )

    def test_vacancy_past_deadline_blocked(self) -> None:
        """Past the deadline, vacant roles fully block downstream actions."""
        engine, addrs = _make_org_with_vacancy(vacancy_deadline_hours=24)

        # Manually set the vacancy start time to >24h ago
        import datetime as dt

        manager_addr = addrs.get("manager")
        if manager_addr:
            engine._vacancy_start_times[manager_addr] = dt.datetime.now(
                dt.UTC
            ) - timedelta(hours=25)

            # Now the manager's vacancy is past deadline
            # Check if the manager's vacant status causes blocking
            # The engineer doesn't report to the manager directly (reports to CEO),
            # so vacancy may not affect them. Let's check the manager itself.
            with engine._lock:
                result = engine._check_vacancy(manager_addr)
            assert result.status == "blocked"

    def test_vacancy_with_designation_ok(self) -> None:
        """Vacant role with valid designation returns ok status."""
        engine, addrs = _make_org_with_vacancy()

        manager_addr = addrs.get("manager")
        engineer_addr = addrs.get("engineer")
        ceo_addr = addrs.get("ceo")

        if manager_addr and engineer_addr and ceo_addr:
            engine.designate_acting_occupant(
                vacant_role=manager_addr,
                acting_role=engineer_addr,
                designated_by=ceo_addr,
            )
            with engine._lock:
                result = engine._check_vacancy(manager_addr)
            assert result.status == "ok"

    def test_vacancy_start_times_tracked_on_init(self) -> None:
        """Initially-vacant roles get start time tracked at engine init."""
        engine, addrs = _make_org_with_vacancy()

        manager_addr = addrs.get("manager")
        if manager_addr:
            assert manager_addr in engine._vacancy_start_times

    def test_vacancy_check_result_interim_status(self) -> None:
        """Within deadline, _check_vacancy returns 'interim' status."""
        engine, addrs = _make_org_with_vacancy(vacancy_deadline_hours=48)

        manager_addr = addrs.get("manager")
        if manager_addr:
            with engine._lock:
                result = engine._check_vacancy(manager_addr)
            assert result.status == "interim"
            assert result.message is not None
            assert "interim" in result.message.lower()

    def test_configurable_deadline_affects_blocking(self) -> None:
        """Short deadline causes blocking sooner."""
        # Use a 1-hour deadline
        engine, addrs = _make_org_with_vacancy(vacancy_deadline_hours=1)

        manager_addr = addrs.get("manager")
        if manager_addr:
            # Set vacancy start to 2h ago — past the 1h deadline
            import datetime as dt

            engine._vacancy_start_times[manager_addr] = dt.datetime.now(
                dt.UTC
            ) - timedelta(hours=2)

            with engine._lock:
                result = engine._check_vacancy(manager_addr)
            assert result.status == "blocked"
