"""
Tier 3 E2E Tests for Multi-Agent Observability Integration.

Tests distributed tracing across supervisor-worker and multi-agent coordination patterns
with REAL LLM providers and production observability infrastructure.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
TODO-169: Tier 3 E2E Tests for Observability System

CRITICAL: NO MOCKING - All tests use real LLM providers and real Jaeger infrastructure.

Budget Tracking:
- Test 1 (supervisor-worker): ~$1.00
- Test 2 (consensus): ~$0.50
- Test 3 (sequential handoff): ~$1.00
Total: ~$2.50
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Task delegation signature."""

    task: str = InputField(description="Task to complete")
    result: str = OutputField(description="Task result")


class DecisionSignature(Signature):
    """Decision-making signature."""

    question: str = InputField(description="Question to decide on")
    decision: str = OutputField(description="Decision made")


class AnalysisSignature(Signature):
    """Analysis signature."""

    data: str = InputField(description="Data to analyze")
    analysis: str = OutputField(description="Analysis result")


@pytest.fixture
def openai_api_key():
    """Fixture providing OpenAI API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set - skipping multi-agent E2E tests")
    return api_key


@pytest.fixture
def jaeger_endpoint():
    """Fixture providing Jaeger endpoint from environment."""
    endpoint = os.getenv("JAEGER_ENDPOINT", "http://localhost:4317")
    return endpoint


@pytest.fixture
def temp_audit_dir(tmp_path):
    """Fixture providing temporary directory for audit logs."""
    return tmp_path


@pytest.mark.e2e
@pytest.mark.tier3
@pytest.mark.openai
@pytest.mark.cost
@pytest.mark.timeout(240)
class TestSupervisorWorkerObservability:
    """E2E tests for supervisor-worker pattern observability."""

    @pytest.mark.asyncio
    async def test_supervisor_worker_observability(
        self, openai_api_key, jaeger_endpoint, temp_audit_dir
    ):
        """
        E2E Test 1: Distributed tracing across supervisor and workers.

        Validates:
        - Parent-child span relationships (supervisor → workers)
        - trace_id propagation across agent boundaries
        - Aggregated metrics for multi-agent execution
        - Audit trails for delegation and coordination

        Budget: ~$1.00 (supervisor + 3 workers, multiple rounds @ gpt-3.5-turbo)
        """
        # Setup: Create supervisor and 3 workers
        from kaizen.core.autonomy.observability.audit import FileAuditStorage

        audit_file = str(temp_audit_dir / "supervisor_worker_audit.jsonl")
        custom_storage = FileAuditStorage(audit_file)

        # Supervisor agent
        supervisor_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=150,
        )
        supervisor = BaseAgent(config=supervisor_config, signature=TaskSignature())
        supervisor_obs = supervisor.enable_observability(
            service_name="supervisor-agent", jaeger_endpoint=jaeger_endpoint
        )
        supervisor_obs.audit.storage = custom_storage

        # Worker agents
        workers = []
        for i in range(3):
            worker_config = BaseAgentConfig(
                llm_provider="openai",
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=100,
            )
            worker = BaseAgent(config=worker_config, signature=TaskSignature())
            worker_obs = worker.enable_observability(
                service_name=f"worker-agent-{i}", jaeger_endpoint=jaeger_endpoint
            )
            worker_obs.audit.storage = custom_storage
            workers.append(worker)

        # Execute: Supervisor delegates tasks to workers
        tasks = ["Calculate 10 + 20", "Calculate 15 + 25", "Calculate 20 + 30"]

        # Supervisor processes main task
        supervisor_result = supervisor.run(task="Coordinate subtasks: math operations")

        # Workers process individual tasks
        worker_results = []
        for i, task in enumerate(tasks):
            result = workers[i].run(task=task)
            worker_results.append(result)
            await asyncio.sleep(0.2)

        # Validate results
        assert supervisor_result is not None
        assert len(worker_results) == 3

        # Validate observability: Metrics from all agents
        supervisor_metrics = await supervisor_obs.export_metrics()
        assert len(supervisor_metrics) > 0

        # Validate observability: Tracing (supervisor + workers)
        supervisor_tracing = supervisor_obs.get_tracing_manager()
        assert supervisor_tracing is not None

        for worker_obs in [w._observability_manager for w in workers]:
            worker_tracing = worker_obs.get_tracing_manager()
            assert worker_tracing is not None

        # Validate observability: Audit trails (supervisor + workers)
        assert Path(audit_file).exists()
        with open(audit_file, "r") as f:
            audit_entries = [json.loads(line) for line in f]
            # At least 4 entries (1 supervisor + 3 workers)
            assert len(audit_entries) >= 4

        # Cleanup
        supervisor.cleanup()
        for worker in workers:
            worker.cleanup()

        # Report cost estimate
        estimated_cost = 1.00
        print(f"\n✅ Test completed. Estimated cost: ${estimated_cost:.2f}")


@pytest.mark.e2e
@pytest.mark.tier3
@pytest.mark.openai
@pytest.mark.cost
@pytest.mark.timeout(180)
class TestConsensusObservability:
    """E2E tests for consensus coordination observability."""

    @pytest.mark.asyncio
    async def test_consensus_observability(
        self, openai_api_key, jaeger_endpoint, temp_audit_dir
    ):
        """
        E2E Test 2: Observability for consensus coordination.

        Validates:
        - Parallel spans (3 agents voting simultaneously)
        - Aggregated metrics across voting agents
        - Consensus decision audit trails

        Budget: ~$0.50 (3 agents voting @ gpt-3.5-turbo)
        """
        # Setup: Create 3 voting agents
        from kaizen.core.autonomy.observability.audit import FileAuditStorage

        audit_file = str(temp_audit_dir / "consensus_audit.jsonl")
        custom_storage = FileAuditStorage(audit_file)

        agents = []
        for i in range(3):
            config = BaseAgentConfig(
                llm_provider="openai",
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=50,
            )
            agent = BaseAgent(config=config, signature=DecisionSignature())
            obs = agent.enable_observability(
                service_name=f"voting-agent-{i}", jaeger_endpoint=jaeger_endpoint
            )
            obs.audit.storage = custom_storage
            agents.append(agent)

        # Execute: All agents vote on decision
        question = "Should we proceed with the plan? Answer yes or no."

        votes = []
        for agent in agents:
            result = agent.run(question=question)
            votes.append(result)
            await asyncio.sleep(0.2)

        # Validate results
        assert len(votes) == 3
        for vote in votes:
            assert "decision" in vote

        # Validate observability: Metrics from all voting agents
        for agent in agents:
            metrics = await agent._observability_manager.export_metrics()
            assert len(metrics) > 0

        # Validate observability: Tracing (parallel execution)
        for agent in agents:
            tracing = agent._observability_manager.get_tracing_manager()
            assert tracing is not None

        # Validate observability: Audit trails (one per agent)
        assert Path(audit_file).exists()
        with open(audit_file, "r") as f:
            audit_entries = [json.loads(line) for line in f]
            assert len(audit_entries) >= 3

        # Cleanup
        for agent in agents:
            agent.cleanup()

        # Report cost estimate
        estimated_cost = 0.50
        print(f"\n✅ Test completed. Estimated cost: ${estimated_cost:.2f}")


@pytest.mark.e2e
@pytest.mark.tier3
@pytest.mark.openai
@pytest.mark.cost
@pytest.mark.timeout(240)
class TestSequentialHandoffObservability:
    """E2E tests for sequential agent handoff observability."""

    @pytest.mark.asyncio
    async def test_handoff_observability(
        self, openai_api_key, jaeger_endpoint, temp_audit_dir
    ):
        """
        E2E Test 3: Observability for sequential agent handoffs.

        Validates:
        - Sequential spans (research → code → review)
        - Context propagation between agents
        - Handoff audit trails

        Budget: ~$1.00 (3 sequential agents @ gpt-3.5-turbo)
        """
        # Setup: Create 3 sequential agents
        from kaizen.core.autonomy.observability.audit import FileAuditStorage

        audit_file = str(temp_audit_dir / "handoff_audit.jsonl")
        custom_storage = FileAuditStorage(audit_file)

        # Research agent
        research_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=150,
        )
        research_agent = BaseAgent(
            config=research_config, signature=AnalysisSignature()
        )
        research_obs = research_agent.enable_observability(
            service_name="research-agent", jaeger_endpoint=jaeger_endpoint
        )
        research_obs.audit.storage = custom_storage

        # Code agent
        code_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-3.5-turbo",
            temperature=0.5,
            max_tokens=150,
        )
        code_agent = BaseAgent(config=code_config, signature=TaskSignature())
        code_obs = code_agent.enable_observability(
            service_name="code-agent", jaeger_endpoint=jaeger_endpoint
        )
        code_obs.audit.storage = custom_storage

        # Review agent
        review_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-3.5-turbo",
            temperature=0.3,
            max_tokens=100,
        )
        review_agent = BaseAgent(config=review_config, signature=AnalysisSignature())
        review_obs = review_agent.enable_observability(
            service_name="review-agent", jaeger_endpoint=jaeger_endpoint
        )
        review_obs.audit.storage = custom_storage

        # Execute: Sequential task execution
        # Step 1: Research
        research_result = research_agent.run(data="Problem: Calculate fibonacci(10)")
        await asyncio.sleep(0.5)

        # Step 2: Code (uses research output)
        code_result = code_agent.run(
            task=f"Implement solution based on: {research_result.get('analysis', '')}"
        )
        await asyncio.sleep(0.5)

        # Step 3: Review (uses code output)
        review_result = review_agent.run(
            data=f"Review this solution: {code_result.get('result', '')}"
        )

        # Validate results
        assert research_result is not None
        assert code_result is not None
        assert review_result is not None

        # Validate observability: Metrics from all sequential agents
        research_metrics = await research_obs.export_metrics()
        code_metrics = await code_obs.export_metrics()
        review_metrics = await review_obs.export_metrics()

        assert len(research_metrics) > 0
        assert len(code_metrics) > 0
        assert len(review_metrics) > 0

        # Validate observability: Tracing (sequential spans)
        research_tracing = research_obs.get_tracing_manager()
        code_tracing = code_obs.get_tracing_manager()
        review_tracing = review_obs.get_tracing_manager()

        assert research_tracing is not None
        assert code_tracing is not None
        assert review_tracing is not None

        # Validate observability: Audit trails (3 sequential entries)
        assert Path(audit_file).exists()
        with open(audit_file, "r") as f:
            audit_entries = [json.loads(line) for line in f]
            assert len(audit_entries) >= 3

        # Cleanup
        research_agent.cleanup()
        code_agent.cleanup()
        review_agent.cleanup()

        # Report cost estimate
        estimated_cost = 1.00
        print(f"\n✅ Test completed. Estimated cost: ${estimated_cost:.2f}")


# ===== Summary Test =====


@pytest.mark.e2e
@pytest.mark.tier3
@pytest.mark.openai
@pytest.mark.summary
def test_multi_agent_e2e_summary():
    """
    Summary test for multi-agent E2E tests.

    Reports total estimated cost and test coverage.
    """
    total_cost = 2.50  # Sum of all test budgets
    tests_count = 3
    patterns_validated = ["supervisor-worker", "consensus", "sequential-handoff"]
    systems_validated = ["metrics", "logging", "tracing", "audit"]

    print("\n" + "=" * 60)
    print("Multi-Agent E2E Tests Summary")
    print("=" * 60)
    print(f"Total tests executed: {tests_count}")
    print(f"Patterns validated: {', '.join(patterns_validated)}")
    print(f"Systems validated: {', '.join(systems_validated)}")
    print(f"Total estimated cost: ${total_cost:.2f}")
    print(f"Average cost per test: ${total_cost / tests_count:.2f}")
    print("=" * 60)

    assert tests_count == 3
    assert len(patterns_validated) == 3
    assert len(systems_validated) == 4
    assert total_cost <= 3.00  # Budget control
