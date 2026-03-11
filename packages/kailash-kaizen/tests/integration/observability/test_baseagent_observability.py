"""
Tier 2 Integration Tests for BaseAgent Observability.

Tests the complete observability stack with real BaseAgent execution.
Validates metrics, logging, tracing, and audit trail integration.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
Week 41: BaseAgent Integration Testing
"""

import json
from pathlib import Path

import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


class SimpleQASignature(Signature):
    """Simple Q&A signature for testing."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Agent answer")


@pytest.fixture
def temp_audit_dir(tmp_path):
    """Fixture providing temporary directory for audit logs."""
    return tmp_path


@pytest.fixture
def agent_config():
    """Fixture providing BaseAgent config with mock provider."""
    return BaseAgentConfig(
        llm_provider="mock", model="mock-model", temperature=0.7, max_tokens=500
    )


@pytest.fixture
def test_agent(agent_config):
    """Fixture providing a test BaseAgent instance."""
    agent = BaseAgent(config=agent_config, signature=SimpleQASignature())
    yield agent
    # Cleanup after test
    agent.cleanup()


class TestFullObservabilityIntegration:
    """Test full observability stack with all components enabled."""

    def test_enable_full_observability(self, test_agent):
        """Test enabling full observability with all components."""
        # Enable full observability
        obs = test_agent.enable_observability(service_name="integration-test-agent")

        # Verify all components enabled
        assert obs.is_component_enabled("metrics")
        assert obs.is_component_enabled("logging")
        assert obs.is_component_enabled("tracing")
        assert obs.is_component_enabled("audit")

        # Verify service name
        assert obs.get_service_name() == "integration-test-agent"

        # Verify enabled components list
        enabled = obs.get_enabled_components()
        assert len(enabled) == 4
        assert "metrics" in enabled
        assert "logging" in enabled
        assert "tracing" in enabled
        assert "audit" in enabled

    def test_observability_manager_components_accessible(self, test_agent):
        """Test that all observability components are accessible."""
        obs = test_agent.enable_observability(service_name="test-agent")

        # Verify metrics component
        assert obs.metrics is not None

        # Verify logging component
        assert obs.logging is not None
        logger = obs.get_logger("test-component")
        assert logger is not None

        # Verify tracing component
        tracing = obs.get_tracing_manager()
        assert tracing is not None

        # Verify audit component
        assert obs.audit is not None


class TestSelectiveObservability:
    """Test selective observability component enabling."""

    def test_metrics_and_logging_only(self, test_agent):
        """Test lightweight observability with metrics and logging only."""
        obs = test_agent.enable_observability(
            service_name="lightweight-agent", enable_tracing=False, enable_audit=False
        )

        # Verify only metrics and logging enabled
        assert obs.is_component_enabled("metrics")
        assert obs.is_component_enabled("logging")
        assert not obs.is_component_enabled("tracing")
        assert not obs.is_component_enabled("audit")

        # Verify disabled components return None
        assert obs.get_tracing_manager() is None

    def test_tracing_only(self, test_agent):
        """Test observability with tracing only."""
        obs = test_agent.enable_observability(
            service_name="tracing-agent",
            enable_metrics=False,
            enable_logging=False,
            enable_audit=False,
        )

        # Verify only tracing enabled
        assert not obs.is_component_enabled("metrics")
        assert not obs.is_component_enabled("logging")
        assert obs.is_component_enabled("tracing")
        assert not obs.is_component_enabled("audit")

        # Verify tracing component accessible
        assert obs.get_tracing_manager() is not None


class TestMetricsCollection:
    """Test metrics collection during agent operations."""

    @pytest.mark.asyncio
    async def test_record_metric_counter(self, test_agent):
        """Test recording counter metrics."""
        obs = test_agent.enable_observability(service_name="metrics-test-agent")

        # Record counter metrics
        await obs.record_metric(
            "test_counter", 1.0, type="counter", labels={"operation": "test"}
        )

        await obs.record_metric(
            "test_counter", 2.0, type="counter", labels={"operation": "test"}
        )

        # Verify counter value
        counter_value = obs.metrics.get_counter_value(
            "test_counter", labels={"operation": "test"}
        )
        assert counter_value == 3.0

    @pytest.mark.asyncio
    async def test_record_metric_gauge(self, test_agent):
        """Test recording gauge metrics."""
        obs = test_agent.enable_observability(service_name="metrics-test-agent")

        # Record gauge metric
        await obs.record_metric(
            "memory_usage", 1024000, type="gauge", labels={"agent_id": "test-agent"}
        )

        # Verify gauge value
        gauge_value = obs.metrics.get_gauge_value(
            "memory_usage", labels={"agent_id": "test-agent"}
        )
        assert gauge_value == 1024000

    @pytest.mark.asyncio
    async def test_record_metric_histogram(self, test_agent):
        """Test recording histogram metrics."""
        obs = test_agent.enable_observability(service_name="metrics-test-agent")

        # Record multiple histogram observations
        for duration in [100, 150, 200, 250, 300]:
            await obs.record_metric(
                "operation_duration_ms",
                duration,
                type="histogram",
                labels={"operation": "test"},
            )

        # Verify histogram values recorded
        histogram_values = obs.metrics.get_histogram_values(
            "operation_duration_ms", labels={"operation": "test"}
        )
        assert len(histogram_values) == 5
        assert 100 in histogram_values
        assert 300 in histogram_values

    @pytest.mark.asyncio
    async def test_export_metrics_prometheus_format(self, test_agent):
        """Test exporting metrics in Prometheus format."""
        obs = test_agent.enable_observability(service_name="metrics-test-agent")

        # Record various metrics
        await obs.record_metric("api_calls_total", 10.0, type="counter")
        await obs.record_metric("active_agents", 3, type="gauge")
        await obs.record_metric("latency_ms", 150, type="histogram")

        # Export metrics
        metrics_text = await obs.export_metrics()

        # Verify Prometheus format
        assert "api_calls_total 10.0" in metrics_text
        assert "active_agents 3" in metrics_text
        assert "latency_ms_p50" in metrics_text


class TestStructuredLogging:
    """Test structured logging with context propagation."""

    def test_get_logger_and_log(self, test_agent):
        """Test getting logger and logging messages."""
        obs = test_agent.enable_observability(service_name="logging-test-agent")

        # Get logger
        logger = obs.get_logger("test-component")
        assert logger is not None

        # Add context
        logger.add_context(agent_id="test-agent", session_id="session-123")

        # Log messages (should not raise exceptions)
        logger.info("Test info message", operation="test")
        logger.warning("Test warning message", duration_ms=150)
        logger.error("Test error message", error_code="TEST_ERROR")

        # Verify context persists
        context = logger.get_context()
        assert context["agent_id"] == "test-agent"
        assert context["session_id"] == "session-123"

    def test_context_propagation(self, test_agent):
        """Test context propagation across log calls."""
        obs = test_agent.enable_observability(service_name="logging-test-agent")

        logger = obs.get_logger("test-component")

        # Add context
        logger.add_context(
            agent_id="test-agent", trace_id="trace-123", span_id="span-456"
        )

        # Context should persist across multiple log calls
        logger.info("First message")
        logger.info("Second message")

        context = logger.get_context()
        assert "agent_id" in context
        assert "trace_id" in context
        assert "span_id" in context

    def test_clear_context(self, test_agent):
        """Test clearing logging context."""
        obs = test_agent.enable_observability(service_name="logging-test-agent")

        logger = obs.get_logger("test-component")
        logger.add_context(key="value")

        # Clear context
        logger.clear_context()

        context = logger.get_context()
        assert len(context) == 0


class TestAuditTrails:
    """Test audit trail recording and querying."""

    @pytest.mark.asyncio
    async def test_record_audit_entry(self, test_agent, temp_audit_dir):
        """Test recording audit trail entry."""
        # Use custom audit file in temp directory
        from kaizen.core.autonomy.observability.audit import FileAuditStorage

        audit_file = str(temp_audit_dir / "test_audit.jsonl")
        custom_storage = FileAuditStorage(audit_file)

        # Create observability with custom audit storage
        obs = test_agent.enable_observability(service_name="audit-test-agent")
        obs.audit.storage = custom_storage  # Override with temp storage

        # Record audit entry
        await obs.record_audit(
            agent_id="test-agent",
            action="tool_execute",
            details={"tool_name": "bash", "command": "ls -la"},
            result="success",
            user_id="test-user@example.com",
            metadata={"danger_level": "MODERATE"},
        )

        # Verify audit file exists and has content
        assert Path(audit_file).exists()

        # Read audit file directly
        with open(audit_file, "r") as f:
            line = f.readline()
            entry = json.loads(line)

            assert entry["agent_id"] == "test-agent"
            assert entry["action"] == "tool_execute"
            assert entry["result"] == "success"
            assert entry["user_id"] == "test-user@example.com"

    @pytest.mark.asyncio
    async def test_query_audit_by_agent(self, test_agent, temp_audit_dir):
        """Test querying audit entries by agent ID."""
        from kaizen.core.autonomy.observability.audit import FileAuditStorage

        audit_file = str(temp_audit_dir / "test_audit.jsonl")
        custom_storage = FileAuditStorage(audit_file)

        obs = test_agent.enable_observability(service_name="audit-test-agent")
        obs.audit.storage = custom_storage

        # Record multiple audit entries
        for i in range(3):
            await obs.record_audit(
                agent_id="test-agent",
                action=f"action_{i}",
                details={"index": i},
                result="success",
            )

        # Query by agent
        entries = await obs.query_audit_by_agent("test-agent")

        assert len(entries) == 3
        assert all(e.agent_id == "test-agent" for e in entries)

    @pytest.mark.asyncio
    async def test_query_audit_by_action(self, test_agent, temp_audit_dir):
        """Test querying audit entries by action type."""
        from kaizen.core.autonomy.observability.audit import FileAuditStorage

        audit_file = str(temp_audit_dir / "test_audit.jsonl")
        custom_storage = FileAuditStorage(audit_file)

        obs = test_agent.enable_observability(service_name="audit-test-agent")
        obs.audit.storage = custom_storage

        # Record entries with different actions
        await obs.record_audit("agent-1", "tool_execute", {}, "success")
        await obs.record_audit("agent-1", "permission_grant", {}, "success")
        await obs.record_audit("agent-2", "tool_execute", {}, "success")

        # Query by action
        entries = await obs.query_audit_by_action("tool_execute")

        assert len(entries) == 2
        assert all(e.action == "tool_execute" for e in entries)


class TestObservabilityCleanup:
    """Test observability cleanup and resource management."""

    def test_cleanup_with_observability(self, agent_config):
        """Test that cleanup properly shuts down observability manager."""
        agent = BaseAgent(config=agent_config, signature=SimpleQASignature())

        # Enable observability
        obs = agent.enable_observability(service_name="cleanup-test-agent")
        assert obs is not None
        assert agent._observability_manager is not None

        # Cleanup agent
        agent.cleanup()

        # Verify observability manager is cleared
        assert agent._observability_manager is None

    def test_cleanup_without_observability(self, agent_config):
        """Test that cleanup works without observability enabled."""
        agent = BaseAgent(config=agent_config, signature=SimpleQASignature())

        # Cleanup without enabling observability (should not raise exception)
        agent.cleanup()

        assert agent._observability_manager is None


class TestDefaultServiceName:
    """Test default service name behavior."""

    def test_default_service_name_uses_agent_id(self, test_agent):
        """Test that default service name uses agent_id."""
        # Enable observability without specifying service_name
        obs = test_agent.enable_observability()

        # Service name should be agent_id
        assert obs.get_service_name() == test_agent.agent_id

    def test_custom_service_name_overrides_agent_id(self, test_agent):
        """Test that custom service_name overrides agent_id."""
        # Enable observability with custom service_name
        obs = test_agent.enable_observability(service_name="custom-service")

        # Service name should be custom value, not agent_id
        assert obs.get_service_name() == "custom-service"
        assert obs.get_service_name() != test_agent.agent_id
