from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test of the tool agent lifecycle.

Exercises 4 of 6 deliverables end-to-end:
- P1: Agent manifest + introspection + deploy
- P3: DAG validator + schema compat + cost estimator
- P5: PostureStateMachine + evidence
- P6: BudgetTracker + posture-budget integration

P2 (MCP catalog server) is tested at Tier 1 in tests/unit/mcp/test_catalog_server.py.
P4 (DataFlow aggregation) is tested at Tier 1 in tests/unit/query/test_sql_builder.py.

NO MOCKING -- all real.
"""

import tempfile

import pytest

from kailash.trust.constraints.budget_tracker import BudgetTracker, usd_to_microdollars
from kailash.trust.posture.postures import (
    PostureStateMachine,
    PostureTransitionRequest,
    TrustPosture,
)
from kaizen.composition.cost_estimator import estimate_cost
from kaizen.composition.dag_validator import validate_dag
from kaizen.composition.schema_compat import check_schema_compatibility
from kaizen.deploy.client import deploy
from kaizen.deploy.registry import LocalRegistry
from kaizen.governance.posture_budget import PostureBudgetIntegration
from kaizen.manifest.agent import AgentManifest
from kaizen.manifest.governance import GovernanceManifest


@pytest.mark.e2e
class TestToolAgentLifecycle:
    """Full lifecycle test exercising all 6 deliverables (P1-P6).

    Each test method validates a distinct deliverable, and the test order
    mirrors the real deployment lifecycle: manifest creation, deployment,
    composition validation, budget tracking, and posture-budget integration.
    """

    # -----------------------------------------------------------------
    # P1: Agent manifest + introspection + deploy
    # -----------------------------------------------------------------

    def test_p1_manifest_creation_and_toml_roundtrip(self) -> None:
        """P1: Build an AgentManifest with governance, verify TOML roundtrip."""
        governance = GovernanceManifest(
            purpose="Summarize customer support tickets",
            risk_level="medium",
            data_access_needed=["customer_data", "ticket_history"],
            suggested_posture="shared_planning",
            max_budget_microdollars=100_000_000,  # 100 USD
        )

        manifest = AgentManifest(
            name="ticket-summarizer",
            module="myapp.agents.summarizer",
            class_name="TicketSummarizerAgent",
            description="Summarizes support tickets using LLM",
            capabilities=["text-summarization", "pii-detection"],
            tools=["llm-invoke", "ticket-read"],
            supported_models=["gpt-4o", "claude-sonnet"],
            governance=governance,
        )

        # Verify core fields
        assert manifest.name == "ticket-summarizer"
        assert manifest.manifest_version == "1.0"
        assert manifest.governance is not None
        assert manifest.governance.risk_level == "medium"
        assert manifest.governance.max_budget_microdollars == 100_000_000

        # TOML roundtrip
        toml_str = manifest.to_toml()
        assert "[agent]" in toml_str
        assert "[governance]" in toml_str
        assert 'name = "ticket-summarizer"' in toml_str

        restored = AgentManifest.from_toml_str(toml_str)
        assert restored.name == manifest.name
        assert restored.module == manifest.module
        assert restored.class_name == manifest.class_name
        assert restored.capabilities == manifest.capabilities
        assert restored.tools == manifest.tools
        assert restored.governance is not None
        assert restored.governance.purpose == governance.purpose
        assert restored.governance.risk_level == governance.risk_level
        assert restored.governance.suggested_posture == governance.suggested_posture
        assert (
            restored.governance.max_budget_microdollars
            == governance.max_budget_microdollars
        )

    def test_p1_manifest_introspection_and_agent_card(self) -> None:
        """P1: Create manifest via from_introspection and convert to A2A Agent Card."""
        info = {
            "name": "data-classifier",
            "module": "myapp.agents.classifier",
            "class_name": "DataClassifierAgent",
            "description": "Classifies data into categories",
            "capabilities": ["classification"],
            "tools": ["vector-search"],
            "governance": {
                "purpose": "Classify incoming documents",
                "risk_level": "low",
                "data_access_needed": ["documents"],
                "suggested_posture": "continuous_insight",
            },
        }

        manifest = AgentManifest.from_introspection(info)
        assert manifest.name == "data-classifier"
        assert manifest.governance is not None
        assert manifest.governance.suggested_posture == "continuous_insight"

        card = manifest.to_agent_card()
        assert card["name"] == "data-classifier"
        assert "a2a/1.0" in card["protocols"]
        assert "kaizen-manifest/1.0" in card["protocols"]
        assert "governance" in card
        assert card["governance"]["risk_level"] == "low"

    def test_p1_deploy_to_local_registry(self) -> None:
        """P1: Deploy manifest to a local registry, verify lookup and cleanup."""
        governance = GovernanceManifest(
            purpose="Test deployment lifecycle",
            risk_level="low",
            data_access_needed=[],
            suggested_posture="supervised",
        )

        manifest = AgentManifest(
            name="deploy-lifecycle-test",
            module="tests.lifecycle",
            class_name="LifecycleAgent",
            governance=governance,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Deploy via deploy() with no target_url -> local
            result = deploy(
                manifest_dict=manifest.to_dict(),
                target_url=None,
                registry_dir=tmp_dir,
            )
            assert result.agent_name == "deploy-lifecycle-test"
            assert result.status == "registered"
            assert result.mode == "local"

            # Verify agent is in the registry
            registry = LocalRegistry(registry_dir=tmp_dir)
            agent_data = registry.get_agent("deploy-lifecycle-test")
            assert agent_data is not None
            assert agent_data["name"] == "deploy-lifecycle-test"
            assert agent_data["module"] == "tests.lifecycle"

            # List agents
            agents = registry.list_agents()
            assert len(agents) >= 1
            names = [a["name"] for a in agents]
            assert "deploy-lifecycle-test" in names

            # Deregister (cleanup)
            removed = registry.deregister("deploy-lifecycle-test")
            assert removed is True

            # Verify deregistration
            assert registry.get_agent("deploy-lifecycle-test") is None

    # -----------------------------------------------------------------
    # P3: DAG validator + schema compat + cost estimator
    # -----------------------------------------------------------------

    def test_p3_validate_2_agent_dag(self) -> None:
        """P3: Validate a 2-agent composition DAG with no cycles."""
        agents = [
            {
                "name": "extractor",
                "inputs_from": [],
            },
            {
                "name": "summarizer",
                "inputs_from": ["extractor"],
            },
        ]

        result = validate_dag(agents)

        assert result.is_valid is True
        assert len(result.cycles) == 0
        # Topological order: extractor before summarizer
        assert "extractor" in result.topological_order
        assert "summarizer" in result.topological_order
        extractor_idx = result.topological_order.index("extractor")
        summarizer_idx = result.topological_order.index("summarizer")
        assert extractor_idx < summarizer_idx

    def test_p3_schema_compatibility(self) -> None:
        """P3: Check schema compatibility between two agents."""
        # Extractor output schema
        output_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "word_count": {"type": "integer"},
                "confidence": {"type": "number"},
            },
            "required": ["text", "word_count"],
        }

        # Summarizer input schema (requires text + word_count, optional metadata)
        input_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "word_count": {"type": "number"},  # integer widens to number
                "metadata": {"type": "object"},
            },
            "required": ["text", "word_count"],
        }

        compat = check_schema_compatibility(output_schema, input_schema)

        assert compat.compatible is True
        assert len(compat.mismatches) == 0
        # metadata is optional and missing from output -- should be a warning
        assert any("metadata" in w for w in compat.warnings)

    def test_p3_cost_estimator(self) -> None:
        """P3: Estimate cost for a 2-agent composition with historical data."""
        composition = [
            {"name": "extractor"},
            {"name": "summarizer"},
        ]

        historical_data = {
            "extractor": {
                "avg_cost_microdollars": 5_000,  # 0.5 cents
                "invocation_count": 150,
            },
            "summarizer": {
                "avg_cost_microdollars": 15_000,  # 1.5 cents
                "invocation_count": 120,
            },
        }

        estimate = estimate_cost(composition, historical_data)

        assert estimate.estimated_total_microdollars == 20_000
        assert estimate.per_agent["extractor"] == 5_000
        assert estimate.per_agent["summarizer"] == 15_000
        assert estimate.confidence == "high"  # Both > 100 invocations
        assert len(estimate.warnings) == 0

    # -----------------------------------------------------------------
    # P6: BudgetTracker
    # -----------------------------------------------------------------

    def test_p6_budget_tracker_reserve_and_record(self) -> None:
        """P6: Create BudgetTracker with 100 USD, reserve, record, verify remaining."""
        budget_microdollars = usd_to_microdollars(100.0)  # 100_000_000
        tracker = BudgetTracker(allocated_microdollars=budget_microdollars)

        # Initial state
        assert tracker.remaining_microdollars() == budget_microdollars

        # Reserve 10 USD
        reserve_amount = usd_to_microdollars(10.0)
        assert tracker.reserve(reserve_amount) is True
        assert tracker.remaining_microdollars() == budget_microdollars - reserve_amount

        # Record actual usage of 8 USD (under-spent compared to reservation)
        actual_cost = usd_to_microdollars(8.0)
        tracker.record(
            reserved_microdollars=reserve_amount,
            actual_microdollars=actual_cost,
        )

        # Remaining should be 100 - 8 = 92 USD
        expected_remaining = budget_microdollars - actual_cost
        assert tracker.remaining_microdollars() == expected_remaining

        # Check says yes for a 50 USD spend
        check_result = tracker.check(usd_to_microdollars(50.0))
        assert check_result.allowed is True
        assert check_result.committed_microdollars == actual_cost

        # Check says no for a 95 USD spend (only 92 remaining)
        check_result_too_much = tracker.check(usd_to_microdollars(95.0))
        assert check_result_too_much.allowed is False

    # -----------------------------------------------------------------
    # P5 + P6: PostureStateMachine + posture-budget integration
    # -----------------------------------------------------------------

    def test_p5_p6_posture_budget_integration_full_lifecycle(self) -> None:
        """P5+P6: Wire posture-budget integration, spend through thresholds.

        Verifies:
        - 80% threshold -> warning (posture unchanged)
        - 95% threshold -> downgrade to SUPERVISED
        - 100% threshold -> emergency downgrade to PSEUDO_AGENT
        """
        agent_id = "lifecycle-test-agent"
        budget_microdollars = usd_to_microdollars(100.0)  # 100_000_000

        # Create real BudgetTracker and PostureStateMachine
        tracker = BudgetTracker(allocated_microdollars=budget_microdollars)
        state_machine = PostureStateMachine(
            default_posture=TrustPosture.SHARED_PLANNING,
            require_upgrade_approval=False,
        )

        # Set initial posture to SHARED_PLANNING (autonomy_level=3)
        state_machine.set_posture(agent_id, TrustPosture.SHARED_PLANNING)
        assert state_machine.get_posture(agent_id) == TrustPosture.SHARED_PLANNING

        # Wire the integration
        integration = PostureBudgetIntegration(
            budget_tracker=tracker,
            state_machine=state_machine,
            agent_id=agent_id,
        )
        assert integration.agent_id == agent_id
        assert integration.thresholds["warning"] == 0.80
        assert integration.thresholds["downgrade"] == 0.95
        assert integration.thresholds["emergency"] == 1.0

        # ---- Phase 1: Spend to 80% -> warning only, no posture change ----
        spend_80 = usd_to_microdollars(80.0)
        assert tracker.reserve(spend_80) is True
        tracker.record(
            reserved_microdollars=spend_80,
            actual_microdollars=spend_80,
        )

        # Posture should still be SHARED_PLANNING (warning does not change posture)
        assert state_machine.get_posture(agent_id) == TrustPosture.SHARED_PLANNING

        # Remaining: 20 USD
        assert tracker.remaining_microdollars() == usd_to_microdollars(20.0)

        # ---- Phase 2: Spend to 95% -> downgrade to SUPERVISED ----
        spend_15 = usd_to_microdollars(15.0)  # Total: 95 USD
        assert tracker.reserve(spend_15) is True
        tracker.record(
            reserved_microdollars=spend_15,
            actual_microdollars=spend_15,
        )

        # Posture should now be SUPERVISED (downgrade threshold crossed)
        assert state_machine.get_posture(agent_id) == TrustPosture.SUPERVISED

        # Remaining: 5 USD
        assert tracker.remaining_microdollars() == usd_to_microdollars(5.0)

        # ---- Phase 3: Spend to 100% -> emergency downgrade to PSEUDO_AGENT ----
        spend_5 = usd_to_microdollars(5.0)  # Total: 100 USD
        assert tracker.reserve(spend_5) is True
        tracker.record(
            reserved_microdollars=spend_5,
            actual_microdollars=spend_5,
        )

        # Posture should now be PSEUDO_AGENT (emergency downgrade)
        assert state_machine.get_posture(agent_id) == TrustPosture.PSEUDO_AGENT

        # Budget exhausted
        assert tracker.remaining_microdollars() == 0

        # Further reservations should fail
        assert tracker.reserve(usd_to_microdollars(1.0)) is False

        # Verify transition history contains the expected events
        history = state_machine.get_transition_history(agent_id=agent_id)
        assert len(history) >= 2  # At least downgrade + emergency_downgrade

        # Find the downgrade and emergency transitions
        transition_types = [h.transition_type.value for h in history]
        assert "downgrade" in transition_types
        assert "emergency_downgrade" in transition_types

    def test_p5_posture_state_machine_evidence_and_guards(self) -> None:
        """P5: PostureStateMachine with evidence-based transitions and guards."""
        agent_id = "evidence-test-agent"
        state_machine = PostureStateMachine(
            default_posture=TrustPosture.SUPERVISED,
            require_upgrade_approval=True,
        )

        # Agent starts at SUPERVISED (default)
        assert state_machine.get_posture(agent_id) == TrustPosture.SUPERVISED

        # Attempt upgrade without requester_id -> blocked by guard
        request_no_requester = PostureTransitionRequest(
            agent_id=agent_id,
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.SHARED_PLANNING,
            reason="Attempting upgrade without approval",
            requester_id=None,
        )
        result = state_machine.transition(request_no_requester)
        assert result.success is False
        assert result.blocked_by == "upgrade_approval_required"

        # Upgrade with requester_id -> should succeed
        request_with_requester = PostureTransitionRequest(
            agent_id=agent_id,
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.SHARED_PLANNING,
            reason="Agent has proven reliable over 48 hours",
            requester_id="admin-001",
        )
        result = state_machine.transition(request_with_requester)
        assert result.success is True
        assert result.from_posture == TrustPosture.SUPERVISED
        assert result.to_posture == TrustPosture.SHARED_PLANNING
        assert state_machine.get_posture(agent_id) == TrustPosture.SHARED_PLANNING

        # Emergency downgrade bypasses all guards
        emergency = state_machine.emergency_downgrade(
            agent_id=agent_id,
            reason="Security incident detected",
            requester_id="security-system",
        )
        assert emergency.success is True
        assert emergency.to_posture == TrustPosture.PSEUDO_AGENT
        assert state_machine.get_posture(agent_id) == TrustPosture.PSEUDO_AGENT

        # Verify full transition history
        history = state_machine.get_transition_history(agent_id=agent_id)
        assert len(history) == 3  # blocked attempt + successful upgrade + emergency
        assert history[0].success is False  # blocked
        assert history[1].success is True  # upgrade
        assert history[2].success is True  # emergency downgrade

    # -----------------------------------------------------------------
    # Full lifecycle: all deliverables in sequence
    # -----------------------------------------------------------------

    def test_full_lifecycle_all_deliverables(self) -> None:
        """Complete lifecycle exercising P1, P3, P5, P6 in a single scenario.

        Simulates the full journey:
        1. Create manifests for two agents (P1)
        2. Deploy both to local registry (P1)
        3. Validate composition DAG (P3)
        4. Check schema compatibility (P3)
        5. Estimate cost (P3)
        6. Create budget tracker from manifest's max_budget (P6)
        7. Wire posture-budget integration (P5+P6)
        8. Simulate usage through thresholds (P5+P6)
        9. Clean up registry (P1)
        """
        with tempfile.TemporaryDirectory() as registry_dir:
            # ---- Step 1: Create agent manifests (P1) ----
            extractor_manifest = AgentManifest(
                name="lifecycle-extractor",
                module="pipeline.extractor",
                class_name="ExtractorAgent",
                description="Extracts structured data from documents",
                capabilities=["extraction", "ocr"],
                governance=GovernanceManifest(
                    purpose="Extract data from documents",
                    risk_level="low",
                    data_access_needed=["documents"],
                    suggested_posture="shared_planning",
                    max_budget_microdollars=50_000_000,  # 50 USD
                ),
            )

            summarizer_manifest = AgentManifest(
                name="lifecycle-summarizer",
                module="pipeline.summarizer",
                class_name="SummarizerAgent",
                description="Generates summaries from extracted data",
                capabilities=["summarization"],
                governance=GovernanceManifest(
                    purpose="Summarize extracted data",
                    risk_level="medium",
                    data_access_needed=["documents", "summaries"],
                    suggested_posture="shared_planning",
                    max_budget_microdollars=100_000_000,  # 100 USD
                ),
            )

            # ---- Step 2: Deploy to local registry (P1) ----
            for manifest in [extractor_manifest, summarizer_manifest]:
                result = deploy(
                    manifest_dict=manifest.to_dict(),
                    registry_dir=registry_dir,
                )
                assert result.status == "registered"
                assert result.mode == "local"

            registry = LocalRegistry(registry_dir=registry_dir)
            assert len(registry.list_agents()) == 2

            # ---- Step 3: Validate composition DAG (P3) ----
            agents = [
                {"name": "lifecycle-extractor", "inputs_from": []},
                {
                    "name": "lifecycle-summarizer",
                    "inputs_from": ["lifecycle-extractor"],
                },
            ]
            dag_result = validate_dag(agents)
            assert dag_result.is_valid is True
            assert len(dag_result.cycles) == 0

            # ---- Step 4: Schema compatibility (P3) ----
            extractor_output = {
                "type": "object",
                "properties": {
                    "extracted_text": {"type": "string"},
                    "page_count": {"type": "integer"},
                },
                "required": ["extracted_text", "page_count"],
            }
            summarizer_input = {
                "type": "object",
                "properties": {
                    "extracted_text": {"type": "string"},
                    "page_count": {"type": "number"},  # integer -> number widening
                },
                "required": ["extracted_text"],
            }
            compat = check_schema_compatibility(extractor_output, summarizer_input)
            assert compat.compatible is True

            # ---- Step 5: Cost estimate (P3) ----
            historical = {
                "lifecycle-extractor": {
                    "avg_cost_microdollars": 3_000,
                    "invocation_count": 200,
                },
                "lifecycle-summarizer": {
                    "avg_cost_microdollars": 12_000,
                    "invocation_count": 180,
                },
            }
            cost = estimate_cost(
                [{"name": "lifecycle-extractor"}, {"name": "lifecycle-summarizer"}],
                historical,
            )
            assert cost.estimated_total_microdollars == 15_000
            assert cost.confidence == "high"

            # ---- Step 6: Budget tracker from manifest budget (P6) ----
            pipeline_budget = (
                summarizer_manifest.governance.max_budget_microdollars
            )  # 100 USD
            tracker = BudgetTracker(allocated_microdollars=pipeline_budget)
            assert tracker.remaining_microdollars() == pipeline_budget

            # ---- Step 7: Wire posture-budget integration (P5+P6) ----
            agent_id = "lifecycle-summarizer"
            state_machine = PostureStateMachine(
                default_posture=TrustPosture.SHARED_PLANNING,
                require_upgrade_approval=False,
            )
            state_machine.set_posture(agent_id, TrustPosture.SHARED_PLANNING)

            PostureBudgetIntegration(
                budget_tracker=tracker,
                state_machine=state_machine,
                agent_id=agent_id,
            )

            # ---- Step 8: Simulate usage through thresholds (P5+P6) ----

            # Spend 70 USD (70%) -- below warning
            spend = usd_to_microdollars(70.0)
            assert tracker.reserve(spend) is True
            tracker.record(reserved_microdollars=spend, actual_microdollars=spend)
            assert state_machine.get_posture(agent_id) == TrustPosture.SHARED_PLANNING

            # Spend 15 more (85%) -- crosses 80% warning, posture unchanged
            spend = usd_to_microdollars(15.0)
            assert tracker.reserve(spend) is True
            tracker.record(reserved_microdollars=spend, actual_microdollars=spend)
            assert state_machine.get_posture(agent_id) == TrustPosture.SHARED_PLANNING

            # Spend 11 more (96%) -- crosses 95% downgrade threshold
            spend = usd_to_microdollars(11.0)
            assert tracker.reserve(spend) is True
            tracker.record(reserved_microdollars=spend, actual_microdollars=spend)
            assert state_machine.get_posture(agent_id) == TrustPosture.SUPERVISED

            # Spend 4 more (100%) -- crosses 100% emergency threshold
            spend = usd_to_microdollars(4.0)
            assert tracker.reserve(spend) is True
            tracker.record(reserved_microdollars=spend, actual_microdollars=spend)
            assert state_machine.get_posture(agent_id) == TrustPosture.PSEUDO_AGENT

            # Budget exhausted
            assert tracker.remaining_microdollars() == 0
            assert tracker.reserve(1) is False

            # ---- Step 9: Clean up registry (P1) ----
            assert registry.deregister("lifecycle-extractor") is True
            assert registry.deregister("lifecycle-summarizer") is True
            assert len(registry.list_agents()) == 0
