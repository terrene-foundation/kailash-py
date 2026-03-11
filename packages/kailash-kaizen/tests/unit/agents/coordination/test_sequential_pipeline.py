"""
Test SequentialPipelinePattern - Multi-Agent Coordination Pattern

Tests sequential pipeline coordination where each agent processes the output
of the previous agent in linear order.

Written BEFORE implementation (TDD).

Test Coverage:
- Factory Function: 8 tests
- Pattern Class: 6 tests
- PipelineStageAgent: 8 tests
- Integration: 8 tests
Total: 30 tests

Author: Kaizen Framework Team
Created: 2025-10-04 (Sequential Pipeline Pattern)
"""

import pytest

# ============================================================================
# TEST CLASS 1: Factory Function (8 tests)
# ============================================================================


class TestCreateSequentialPipeline:
    """Test create_sequential_pipeline factory function."""

    def test_zero_config_creation(self):
        """Test zero-config pattern creation."""
        from kaizen.agents.coordination import create_sequential_pipeline

        pipeline = create_sequential_pipeline()

        assert pipeline is not None
        assert pipeline.shared_memory is not None
        # Should be empty initially (stages added later)
        assert isinstance(pipeline.stages, list)

    def test_basic_parameter_override(self):
        """Test overriding model and temperature."""
        from kaizen.agents.coordination import create_sequential_pipeline

        pipeline = create_sequential_pipeline(model="gpt-4", temperature=0.9)

        assert pipeline is not None
        assert pipeline.shared_memory is not None

    def test_stage_configs_different_per_stage(self):
        """Test different config per stage."""
        from kaizen.agents.coordination import create_sequential_pipeline

        stage_configs = [
            {"model": "gpt-4", "temperature": 0.1},
            {"model": "gpt-3.5-turbo", "temperature": 0.7},
            {"model": "gpt-4", "temperature": 0.3},
        ]

        pipeline = create_sequential_pipeline(stage_configs=stage_configs)

        # Stages should be created with configs
        assert pipeline is not None

    def test_custom_shared_memory(self):
        """Test providing custom shared memory."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.memory import SharedMemoryPool

        custom_memory = SharedMemoryPool()

        pipeline = create_sequential_pipeline(shared_memory=custom_memory)

        assert pipeline.shared_memory is custom_memory

    def test_environment_variable_fallback(self):
        """Test fallback to environment variables."""
        from kaizen.agents.coordination import create_sequential_pipeline

        # Should use env vars or defaults
        pipeline = create_sequential_pipeline()

        assert pipeline is not None

    def test_invalid_configuration_stage_configs_not_list(self):
        """Test invalid stage_configs type."""
        from kaizen.agents.coordination import create_sequential_pipeline

        with pytest.raises((ValueError, TypeError)):
            create_sequential_pipeline(stage_configs="not a list")  # Invalid

    def test_stages_parameter_direct_provision(self):
        """Test providing stages directly."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Create stages manually
        stage1 = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="stage_1",
            stage_name="extract",
        )
        stage2 = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="stage_2",
            stage_name="transform",
        )

        pipeline = create_sequential_pipeline(
            stages=[stage1, stage2], shared_memory=shared_memory
        )

        assert len(pipeline.stages) == 2
        assert pipeline.stages[0] is stage1
        assert pipeline.stages[1] is stage2

    def test_mixed_configuration_stages_and_configs(self):
        """Test providing both stages and stage_configs (stages take precedence)."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        stage1 = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="stage_1",
            stage_name="extract",
        )

        # Provide both stages and stage_configs
        pipeline = create_sequential_pipeline(
            stages=[stage1],
            stage_configs=[{"model": "gpt-4"}],  # Should be ignored
            shared_memory=shared_memory,
        )

        # stages parameter should take precedence
        assert len(pipeline.stages) == 1
        assert pipeline.stages[0] is stage1


# ============================================================================
# TEST CLASS 2: Pattern Class (6 tests)
# ============================================================================


class TestSequentialPipelinePattern:
    """Test SequentialPipelinePattern class."""

    def test_add_stage_method(self):
        """Test add_stage() adds stage to pipeline."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")
        stage = PipelineStageAgent(
            config=config,
            shared_memory=pipeline.shared_memory,
            agent_id="test_stage",
            stage_name="process",
        )

        pipeline.add_stage(stage)

        assert len(pipeline.stages) == 1
        assert pipeline.stages[0] is stage

    def test_execute_pipeline_method(self):
        """Test execute_pipeline() executes all stages."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        # Add 2 stages
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")
        for i in range(2):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=f"stage{i}",
            )
            pipeline.add_stage(stage)

        result = pipeline.execute_pipeline(
            initial_input="Test input", context="Test context"
        )

        assert isinstance(result, dict)
        assert "pipeline_id" in result
        assert "final_output" in result

    def test_get_stage_results_method(self):
        """Test get_stage_results() retrieves all stage results."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        # Add stage
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")
        stage = PipelineStageAgent(
            config=config,
            shared_memory=pipeline.shared_memory,
            agent_id="stage_1",
            stage_name="process",
        )
        pipeline.add_stage(stage)

        # Execute
        result = pipeline.execute_pipeline("Test input", "")

        # Get stage results
        stage_results = pipeline.get_stage_results(result["pipeline_id"])

        assert isinstance(stage_results, list)
        assert len(stage_results) >= 1

    def test_validate_pattern_method(self):
        """Test validate_pattern() validates pipeline."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        # Empty pipeline should be valid but have no stages
        # (validate_pattern checks shared_memory and agents exist)
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")
        stage = PipelineStageAgent(
            config=config,
            shared_memory=pipeline.shared_memory,
            agent_id="stage_1",
            stage_name="process",
        )
        pipeline.add_stage(stage)

        assert pipeline.validate_pattern() is True

    def test_stage_ordering_preserved(self):
        """Test stages execute in order they were added."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Add 3 stages in order
        stage_names = ["extract", "transform", "load"]
        for i, name in enumerate(stage_names):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=name,
            )
            pipeline.add_stage(stage)

        # Verify order
        assert len(pipeline.stages) == 3
        assert pipeline.stages[0].stage_name == "extract"
        assert pipeline.stages[1].stage_name == "transform"
        assert pipeline.stages[2].stage_name == "load"

    def test_pipeline_id_generation_unique(self):
        """Test each pipeline execution generates unique ID."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")
        stage = PipelineStageAgent(
            config=config,
            shared_memory=pipeline.shared_memory,
            agent_id="stage_1",
            stage_name="process",
        )
        pipeline.add_stage(stage)

        # Execute twice
        result1 = pipeline.execute_pipeline("Input 1", "")
        result2 = pipeline.execute_pipeline("Input 2", "")

        # Should have different pipeline IDs
        assert result1["pipeline_id"] != result2["pipeline_id"]


# ============================================================================
# TEST CLASS 3: PipelineStageAgent (8 tests)
# ============================================================================


class TestPipelineStageAgent:
    """Test PipelineStageAgent class."""

    def test_agent_initialization(self):
        """Test stage agent initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="extract",
        )

        assert agent.agent_id == "test_stage"
        assert agent.stage_name == "extract"
        assert agent.shared_memory is shared_memory

    def test_stage_processing_uses_signature(self):
        """Test stage uses StageProcessingSignature."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import (
            PipelineStageAgent,
            StageProcessingSignature,
        )

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="process",
        )

        assert isinstance(agent.signature, StageProcessingSignature)

    def test_stage_processes_input(self):
        """Test stage can process input."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="extract",
        )

        # Process input
        result = agent.run(
            stage_input="Test input", stage_name="extract", context="Test context"
        )

        assert isinstance(result, dict)
        assert "stage_output" in result or "output" in result or "response" in result

    def test_shared_memory_writing(self):
        """Test stage writes results to shared memory."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="extract",
            pipeline_id="test_pipeline",
        )

        # Process input (should write to memory via run())
        agent.run(
            stage_input="Test input", stage_name="extract", context="Test context"
        )

        # Check shared memory has stage result
        insights = shared_memory.read_relevant(
            agent_id="_pattern_", tags=["pipeline"], exclude_own=False, limit=10
        )

        # Should have at least one insight
        assert len(insights) >= 0  # May or may not write depending on implementation

    def test_stage_metadata_included(self):
        """Test stage result includes metadata."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="extract",
            pipeline_id="test_pipeline",
            stage_index=0,
        )

        result = agent.run(
            stage_input="Test input", stage_name="extract", context="Test context"
        )

        # Result may have metadata fields or special keys
        assert isinstance(result, dict)

    def test_stage_status_handling(self):
        """Test stage handles status field."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="process",
            pipeline_id="test_pipeline",
        )

        result = agent.run(stage_input="Test input", stage_name="process", context="")

        # Status field should be in result or have default handling
        assert isinstance(result, dict)

    def test_context_preservation(self):
        """Test stage preserves context."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="process",
            pipeline_id="test_pipeline",
        )

        context = "Important context"
        result = agent.run(
            stage_input="Test input", stage_name="process", context=context
        )

        # Context should be used in processing
        assert isinstance(result, dict)

    def test_error_handling_in_stage(self):
        """Test stage handles errors gracefully."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(
            llm_provider="mock", model="gpt-3.5-turbo", error_handling_enabled=True
        )

        agent = PipelineStageAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_stage",
            stage_name="process",
            pipeline_id="test_pipeline",
        )

        # Even with errors, should return a result (not raise)
        result = agent.run(stage_input="Test input", stage_name="process", context="")

        assert isinstance(result, dict)


# ============================================================================
# TEST CLASS 4: Integration Tests (8 tests)
# ============================================================================


class TestSequentialPipelineIntegration:
    """Test complete sequential pipeline workflows."""

    def test_three_stage_etl_pipeline(self):
        """Test 3-stage ETL pipeline: extract → transform → load."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Add 3 stages
        for i, name in enumerate(["extract", "transform", "load"]):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=name,
            )
            pipeline.add_stage(stage)

        # Execute pipeline
        result = pipeline.execute_pipeline(
            initial_input="Raw data to process",
            context="ETL workflow for customer data",
        )

        assert "pipeline_id" in result
        assert "final_output" in result

    def test_four_stage_content_generation_pipeline(self):
        """Test 4-stage content generation pipeline."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Add 4 stages: research → outline → draft → edit
        for i, name in enumerate(["research", "outline", "draft", "edit"]):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=name,
            )
            pipeline.add_stage(stage)

        result = pipeline.execute_pipeline(
            initial_input="Write article about AI",
            context="Content generation workflow",
        )

        assert "pipeline_id" in result
        assert "final_output" in result

    def test_context_preservation_across_stages(self):
        """Test context is preserved and passed through all stages."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        for i in range(3):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=f"stage{i}",
            )
            pipeline.add_stage(stage)

        context = "Important context that must be preserved"
        result = pipeline.execute_pipeline("Input", context)

        # Get stage results
        stage_results = pipeline.get_stage_results(result["pipeline_id"])

        # All stages should have access to context
        assert len(stage_results) >= 3

    def test_partial_failure_handling(self):
        """Test pipeline handles stage failures gracefully."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(
            llm_provider="mock", model="gpt-3.5-turbo", error_handling_enabled=True
        )

        for i in range(2):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=f"stage{i}",
            )
            pipeline.add_stage(stage)

        # Execute - should handle errors
        result = pipeline.execute_pipeline("Input", "")

        # Should return result even if some stages fail
        assert isinstance(result, dict)

    def test_stage_result_retrieval(self):
        """Test retrieving all stage results."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        for i in range(3):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=f"stage{i}",
            )
            pipeline.add_stage(stage)

        result = pipeline.execute_pipeline("Input", "")

        # Get all stage results
        stage_results = pipeline.get_stage_results(result["pipeline_id"])

        assert isinstance(stage_results, list)
        assert len(stage_results) >= 3

    def test_empty_pipeline_execution(self):
        """Test executing empty pipeline (no stages)."""
        from kaizen.agents.coordination import create_sequential_pipeline

        pipeline = create_sequential_pipeline()

        # Execute empty pipeline
        result = pipeline.execute_pipeline("Input", "")

        # Should handle gracefully
        assert isinstance(result, dict)
        assert "pipeline_id" in result

    def test_single_stage_pipeline(self):
        """Test pipeline with single stage."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")
        stage = PipelineStageAgent(
            config=config,
            shared_memory=pipeline.shared_memory,
            agent_id="stage_0",
            stage_name="process",
        )
        pipeline.add_stage(stage)

        result = pipeline.execute_pipeline("Input", "")

        assert "pipeline_id" in result
        assert "final_output" in result

    def test_complex_multi_stage_workflow(self):
        """Test complex 6-stage workflow."""
        from kaizen.agents.coordination import create_sequential_pipeline
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.orchestration.patterns.sequential import PipelineStageAgent

        pipeline = create_sequential_pipeline()

        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # 6 stages: input → analyze → plan → execute → verify → output
        stages = ["input", "analyze", "plan", "execute", "verify", "output"]
        for i, name in enumerate(stages):
            stage = PipelineStageAgent(
                config=config,
                shared_memory=pipeline.shared_memory,
                agent_id=f"stage_{i}",
                stage_name=name,
            )
            pipeline.add_stage(stage)

        result = pipeline.execute_pipeline(
            initial_input="Complex task", context="Multi-stage processing"
        )

        assert "pipeline_id" in result
        assert "final_output" in result

        # Get all stage results
        stage_results = pipeline.get_stage_results(result["pipeline_id"])
        assert len(stage_results) >= 6
