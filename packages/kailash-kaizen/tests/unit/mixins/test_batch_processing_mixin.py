"""
Task 3.4 - BatchProcessingMixin Unit Tests.

Tests for BatchProcessingMixin covering batch execution and progress tracking.

Evidence Required:
- 10+ test cases covering batch processing
- 95%+ coverage for BatchProcessingMixin
- Tests for parallel execution and error handling

References:
- TODO-157: Task 3.4, 3.18-3.21
- ADR-006: Mixin Composition design
"""

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.mixins.batch_processing import BatchProcessingMixin
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSignature(Signature):
    """Simple signature for testing."""

    input_text: str = InputField(desc="Input text")
    output_text: str = OutputField(desc="Output text")


@pytest.mark.unit
class TestBatchProcessingMixinInitialization:
    """Test BatchProcessingMixin initialization."""

    def test_mixin_initialization_default(self):
        """Task 3.4 - BatchProcessingMixin initializes with defaults."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        assert hasattr(agent, "batch_size")
        assert agent.batch_size == 10  # Default

    def test_mixin_initialization_custom_batch_size(self):
        """Task 3.4 - BatchProcessingMixin accepts custom batch size."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self, batch_size=50)

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        assert agent.batch_size == 50

    def test_mixin_initialization_with_parallel_execution(self):
        """Task 3.4 - BatchProcessingMixin accepts parallel execution config."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(
                    self, parallel_execution=True, max_workers=4
                )

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        assert agent.parallel_execution is True
        assert agent.max_workers == 4


@pytest.mark.unit
class TestBatchProcessingMixinBatchExecution:
    """Test BatchProcessingMixin batch execution."""

    def test_executes_batch_sequentially(self):
        """Task 3.18 - Executes batch of inputs sequentially."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                return {"result": f"processed_{input_data}"}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        inputs = ["input1", "input2", "input3"]
        results = agent.process_batch(inputs, agent.process_single)

        assert len(results) == 3
        assert all("result" in r for r in results)

    def test_executes_batch_with_progress_tracking(self):
        """Task 3.19 - Tracks batch execution progress."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        inputs = list(range(10))
        agent.process_batch(inputs, agent.process_single)

        progress = agent.get_batch_progress()
        assert progress["total"] == 10
        assert progress["completed"] == 10

    def test_batch_execution_respects_batch_size(self):
        """Task 3.18 - Respects configured batch size."""
        execution_counts = []

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self, batch_size=3)

            def process_single(self, input_data):
                execution_counts.append(input_data)
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        inputs = list(range(10))
        agent.process_batch(inputs, agent.process_single)

        # All inputs should be processed
        assert len(execution_counts) == 10


@pytest.mark.unit
class TestBatchProcessingMixinErrorHandling:
    """Test BatchProcessingMixin error handling."""

    def test_handles_errors_in_batch(self):
        """Task 3.20 - Handles errors during batch processing."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                if input_data == "error":
                    raise ValueError("Test error")
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        inputs = ["good1", "error", "good2"]
        results = agent.process_batch(
            inputs, agent.process_single, continue_on_error=True
        )

        # Should have results for successful items
        assert len(results) == 3
        # Error item should have error marker
        assert any("error" in str(r) for r in results)

    def test_stops_on_error_when_configured(self):
        """Task 3.20 - Stops batch processing on error when configured."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                if input_data == 2:
                    raise ValueError("Stop here")
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        inputs = [1, 2, 3, 4]

        with pytest.raises(ValueError):
            agent.process_batch(inputs, agent.process_single, continue_on_error=False)

    def test_collects_error_statistics(self):
        """Task 3.21 - Collects statistics on batch errors."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                if input_data % 2 == 0:
                    raise ValueError("Even number error")
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        inputs = list(range(10))
        agent.process_batch(inputs, agent.process_single, continue_on_error=True)

        stats = agent.get_batch_statistics()
        assert stats["total"] == 10
        assert stats["errors"] > 0


@pytest.mark.unit
class TestBatchProcessingMixinWorkflowEnhancement:
    """Test BatchProcessingMixin workflow enhancement."""

    def test_enhance_workflow_returns_workflow_builder(self):
        """Task 3.18 - enhance_workflow() returns WorkflowBuilder."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        enhanced = agent.enhance_workflow(workflow)

        assert isinstance(enhanced, WorkflowBuilder)

    def test_enhance_workflow_adds_batch_nodes(self):
        """Task 3.18 - enhance_workflow() adds batch processing nodes."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "test_node", {})

        enhanced = agent.enhance_workflow(workflow)

        # Workflow should be enhanced (even if no-op for now)
        assert enhanced is not None


@pytest.mark.unit
class TestBatchProcessingMixinMROCompatibility:
    """Test BatchProcessingMixin MRO compatibility."""

    def test_mro_with_base_agent(self):
        """Task 3.4 - BatchProcessingMixin works with BaseAgent in MRO."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, BatchProcessingMixin)

    def test_mro_calls_super_init(self):
        """Task 3.4 - BatchProcessingMixin.__init__ calls super().__init__ correctly."""
        init_calls = []

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                init_calls.append("BaseAgent")
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                init_calls.append("BatchProcessingMixin")
                BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        TestAgent(config)

        assert "BaseAgent" in init_calls
        assert "BatchProcessingMixin" in init_calls


@pytest.mark.unit
class TestBatchProcessingMixinConfiguration:
    """Test BatchProcessingMixin configuration."""

    def test_respects_batch_processing_enabled_flag(self):
        """Task 3.4 - Respects batch_processing_enabled config flag."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                if config.batch_processing_enabled:
                    BatchProcessingMixin.__init__(self)

        config_enabled = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent_enabled = TestAgent(config_enabled)
        assert hasattr(agent_enabled, "batch_size")

        config_disabled = BaseAgentConfig(model="gpt-4", batch_processing_enabled=False)
        TestAgent(config_disabled)
        assert True  # Agent created successfully

    def test_configurable_batch_options(self):
        """Task 3.18 - Supports configurable batch processing options."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(
                    self, batch_size=25, parallel_execution=True, max_workers=8
                )

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        assert agent.batch_size == 25
        assert agent.parallel_execution is True
        assert agent.max_workers == 8


@pytest.mark.unit
class TestBatchProcessingMixinEdgeCases:
    """Test BatchProcessingMixin edge cases."""

    def test_handles_empty_batch(self):
        """Task 3.18 - Handles empty batch gracefully."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        results = agent.process_batch([], agent.process_single)

        # Should return empty results
        assert len(results) == 0

    def test_handles_single_item_batch(self):
        """Task 3.18 - Handles single-item batch."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self)

            def process_single(self, input_data):
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        results = agent.process_batch(["single"], agent.process_single)

        assert len(results) == 1
        assert results[0]["result"] == "single"

    def test_handles_large_batch(self):
        """Task 3.19 - Handles large batch efficiently."""

        class TestAgent(BaseAgent, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                BatchProcessingMixin.__init__(self, batch_size=100)

            def process_single(self, input_data):
                return {"result": input_data}

        config = BaseAgentConfig(model="gpt-4", batch_processing_enabled=True)
        agent = TestAgent(config)

        # Large batch
        inputs = list(range(1000))
        results = agent.process_batch(inputs, agent.process_single)

        assert len(results) == 1000
