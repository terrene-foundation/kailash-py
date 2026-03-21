# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for AgentRoleMapping -- maps agent IDs to D/T/R role addresses.

Covers:
- TODO-7017: AgentRoleMapping class
- from_org() builds mapping from CompiledOrg
- get_address / get_agent lookups
- resolve() for agent IDs and address passthroughs
- resolve() raises ValueError for unknown inputs
- Manual register()
- Thread safety under concurrent lookups
- Bidirectional mapping consistency
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from pact.build.config.schema import DepartmentConfig, TeamConfig
from pact.build.org.builder import OrgDefinition
from pact.governance.agent_mapping import AgentRoleMapping
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org


# ---------------------------------------------------------------------------
# Helper: build a small org with agent_id assignments
# ---------------------------------------------------------------------------


def _build_org_with_agents() -> CompiledOrg:
    """Build a simple org with 3 roles, 2 of which have agent_id set."""
    departments = [
        DepartmentConfig(department_id="d-eng", name="Engineering"),
    ]
    teams = [
        TeamConfig(id="t-backend", name="Backend", workspace="ws-be"),
    ]
    roles = [
        RoleDefinition(
            role_id="r-cto",
            name="CTO",
            reports_to_role_id=None,
            is_primary_for_unit="d-eng",
            agent_id="agent-cto",
        ),
        RoleDefinition(
            role_id="r-lead",
            name="Tech Lead",
            reports_to_role_id="r-cto",
            is_primary_for_unit="t-backend",
            agent_id="agent-lead",
        ),
        RoleDefinition(
            role_id="r-dev",
            name="Developer",
            reports_to_role_id="r-lead",
            # No agent_id -- vacant role
        ),
    ]
    org = OrgDefinition(
        org_id="test-org-mapping",
        name="Test Mapping Org",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


# ---------------------------------------------------------------------------
# from_org
# ---------------------------------------------------------------------------


class TestFromOrg:
    """from_org() should populate mappings for all roles with agent_id."""

    def test_from_org_populates_mapping(self) -> None:
        """Roles with agent_id are mapped; roles without are skipped."""
        compiled = _build_org_with_agents()
        mapping = AgentRoleMapping.from_org(compiled)

        # agent-cto and agent-lead should be mapped
        assert mapping.get_address("agent-cto") is not None
        assert mapping.get_address("agent-lead") is not None

        # r-dev has no agent_id, should not appear in reverse lookup
        dev_node = compiled.get_node_by_role_id("r-dev")
        assert dev_node is not None
        assert mapping.get_agent(dev_node.address) is None


# ---------------------------------------------------------------------------
# get_address / get_agent lookups
# ---------------------------------------------------------------------------


class TestLookups:
    """Basic get_address and get_agent lookups."""

    def test_get_address_for_agent(self) -> None:
        """get_address returns the D/T/R address for a known agent ID."""
        compiled = _build_org_with_agents()
        mapping = AgentRoleMapping.from_org(compiled)

        address = mapping.get_address("agent-cto")
        assert address is not None
        # The CTO heads d-eng, so address should be D1-R1
        assert "D" in address
        assert "R" in address

    def test_get_agent_for_address(self) -> None:
        """get_agent returns the agent ID for a known address."""
        compiled = _build_org_with_agents()
        mapping = AgentRoleMapping.from_org(compiled)

        # Find the CTO's address first
        cto_address = mapping.get_address("agent-cto")
        assert cto_address is not None

        agent_id = mapping.get_agent(cto_address)
        assert agent_id == "agent-cto"

    def test_get_address_unknown_returns_none(self) -> None:
        """get_address returns None for an unknown agent ID."""
        mapping = AgentRoleMapping()
        assert mapping.get_address("nonexistent-agent") is None

    def test_get_agent_unknown_returns_none(self) -> None:
        """get_agent returns None for an unknown address."""
        mapping = AgentRoleMapping()
        assert mapping.get_agent("D99-R99") is None


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


class TestResolve:
    """resolve() resolves agent IDs to addresses, or passes through addresses."""

    def test_resolve_agent_id(self) -> None:
        """resolve() looks up agent IDs and returns their address."""
        compiled = _build_org_with_agents()
        mapping = AgentRoleMapping.from_org(compiled)

        address = mapping.resolve("agent-cto")
        assert address is not None
        # Should be a valid D/T/R address
        assert "D" in address or "T" in address or "R" in address

    def test_resolve_address_passthrough(self) -> None:
        """resolve() passes through strings that look like D/T/R addresses."""
        mapping = AgentRoleMapping()
        assert mapping.resolve("D1-R1-T1-R1") == "D1-R1-T1-R1"

    def test_resolve_unknown_raises(self) -> None:
        """resolve() raises ValueError for strings that are neither agent IDs nor addresses."""
        mapping = AgentRoleMapping()
        with pytest.raises(ValueError, match="Cannot resolve"):
            mapping.resolve("some-random-string")

    def test_resolve_prefers_agent_id_lookup(self) -> None:
        """If an agent ID is registered, resolve returns its address, not the ID itself."""
        mapping = AgentRoleMapping()
        mapping.register("agent-alpha", "D1-R1-D2-R1")
        assert mapping.resolve("agent-alpha") == "D1-R1-D2-R1"


# ---------------------------------------------------------------------------
# Manual register
# ---------------------------------------------------------------------------


class TestRegister:
    """Manual register() adds agent-to-address mappings."""

    def test_register_manual(self) -> None:
        """register() creates bidirectional mapping."""
        mapping = AgentRoleMapping()
        mapping.register("agent-x", "D1-R1")

        assert mapping.get_address("agent-x") == "D1-R1"
        assert mapping.get_agent("D1-R1") == "agent-x"

    def test_register_overwrites(self) -> None:
        """register() overwrites previous mapping for same agent_id."""
        mapping = AgentRoleMapping()
        mapping.register("agent-x", "D1-R1")
        mapping.register("agent-x", "D2-R1")

        assert mapping.get_address("agent-x") == "D2-R1"
        assert mapping.get_agent("D2-R1") == "agent-x"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """AgentRoleMapping must be thread-safe for concurrent operations."""

    def test_thread_safety_concurrent_lookups(self) -> None:
        """Multiple threads doing register + lookup concurrently must not corrupt state."""
        mapping = AgentRoleMapping()
        errors: list[str] = []

        def worker(agent_num: int) -> None:
            agent_id = f"agent-{agent_num}"
            address = f"D{agent_num}-R1"
            mapping.register(agent_id, address)

            # Verify our own registration
            result = mapping.get_address(agent_id)
            if result != address:
                errors.append(f"Thread {agent_num}: expected {address}, got {result}")

            result_agent = mapping.get_agent(address)
            if result_agent != agent_id:
                errors.append(
                    f"Thread {agent_num}: reverse lookup expected {agent_id}, got {result_agent}"
                )

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()  # Reraise any exceptions

        assert errors == [], f"Thread safety errors: {errors}"

    def test_concurrent_resolve(self) -> None:
        """Multiple threads calling resolve() concurrently on the same mapping."""
        mapping = AgentRoleMapping()
        for i in range(50):
            mapping.register(f"agent-{i}", f"D{i}-R1")

        results: list[str] = []

        def resolver(agent_num: int) -> str:
            return mapping.resolve(f"agent-{agent_num}")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(resolver, i): i for i in range(50)}
            for f in as_completed(futures):
                i = futures[f]
                result = f.result()
                assert result == f"D{i}-R1"


# ---------------------------------------------------------------------------
# Bidirectional mapping
# ---------------------------------------------------------------------------


class TestBidirectionalMapping:
    """Every register() must maintain consistent bidirectional mapping."""

    def test_bidirectional_mapping(self) -> None:
        """For every agent_id -> address, address -> agent_id must also hold."""
        compiled = _build_org_with_agents()
        mapping = AgentRoleMapping.from_org(compiled)

        # Check all known agent IDs
        for agent_id in ["agent-cto", "agent-lead"]:
            address = mapping.get_address(agent_id)
            assert address is not None, f"No address for {agent_id}"
            reverse = mapping.get_agent(address)
            assert (
                reverse == agent_id
            ), f"Bidirectional mismatch: {agent_id} -> {address} -> {reverse}"
