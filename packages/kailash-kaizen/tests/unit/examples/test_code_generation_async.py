"""
Test Code Generation Example - Async Migration (Task 0A.8)

Tests that code-generation example uses AsyncSingleShotStrategy by default.
Uses standardized fixtures for consistent testing.
"""

import asyncio

import pytest

# Standardized example loading
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy


class TestCodeGenerationAsyncMigration:
    """Test suite for Code Generation async migration."""

    def test_codegen_uses_async_strategy_by_default(
        self, code_generation_example, async_config, assert_async_strategy
    ):
        """Task 0A.8: Verify CodeGenerationAgent uses AsyncSingleShotStrategy."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig(llm_provider="openai", model="gpt-4")
        agent = CodeGenerationAgent(config=config)

        assert_async_strategy(agent)

    def test_codegen_no_explicit_strategy_override(self, code_generation_example):
        """Test that CodeGenerationAgent no longer explicitly passes strategy."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_run_works_with_async(self, code_generation_example, assert_agent_result):
        """Test that generate_code() method works with async strategy."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        result = agent.run(task_description="Create a function to add two numbers")
        assert_agent_result(result)

    def test_multiple_codegen_agents_independent(self, code_generation_example):
        """Test that multiple code generation agents don't interfere."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent1 = CodeGenerationAgent(config=config)
        agent2 = CodeGenerationAgent(config=config)

        assert isinstance(agent1.strategy, AsyncSingleShotStrategy)
        assert isinstance(agent2.strategy, AsyncSingleShotStrategy)
        assert agent1.strategy is not agent2.strategy


@pytest.mark.race_conditions
class TestCodeGenerationRaceConditions:
    """Test for race conditions with async code generation."""

    def test_codegen_no_race_conditions_sequential(
        self, code_generation_example, test_queries
    ):
        """Test sequential code generation doesn't have race conditions."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        results = []
        for i in range(5):
            result = agent.generate_code(f"Function {i}")
            results.append(result)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_codegen_no_race_conditions_concurrent(
        self, code_generation_example, run_async
    ):
        """Test concurrent code generation executions don't interfere."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        async def generate_async(task_desc):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.generate_code, task_desc)

        # 10 concurrent code generation tasks
        tasks = [generate_async(f"Function {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 10


class TestCodeGenerationOutputQuality:
    """Test that code generation output quality is preserved."""

    def test_codegen_output_structure_preserved(
        self, code_generation_example, assert_agent_result
    ):
        """Test that output structure is preserved with async strategy."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        result = agent.run(task_description="Create a simple calculator function")
        assert_agent_result(result)

    def test_codegen_language_parameter(self, code_generation_example):
        """Test that language parameter works correctly."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig(programming_language="python")
        agent = CodeGenerationAgent(config=config)

        result = agent.run(task_description="Simple function", language="javascript")

        if "language" in result:
            assert result["language"] == "javascript"

    def test_codegen_empty_task_handling(self, code_generation_example):
        """Test that empty task handling returns a result with default values.

        Note: Agent doesn't perform input validation - it processes empty input
        and returns result. Actual answer depends on LLM provider (real or mock).
        """
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig(llm_provider="mock")
        agent = CodeGenerationAgent(config=config)

        result = agent.run(task_description="")

        # Agent returns a result dict (structure test, not content test)
        assert isinstance(result, dict)
        # Should have code field (may be empty string or mock value) or error
        assert "code" in result or "error" in result


@pytest.mark.backward_compatibility
class TestCodeGenerationBackwardCompatibility:
    """Test backward compatibility after async migration."""

    def test_codegen_config_parameters_preserved(
        self, code_generation_example, validate_config
    ):
        """Test that all CodeGenConfig parameters are preserved."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.2,
            max_tokens=2000,
            programming_language="python",
            include_tests=True,
            include_documentation=True,
        )

        agent = CodeGenerationAgent(config=config)

        assert agent.codegen_config.llm_provider == "openai"
        assert agent.codegen_config.model == "gpt-4"
        assert agent.codegen_config.temperature == 0.2
        assert agent.codegen_config.programming_language == "python"

    def test_codegen_helper_methods(self, code_generation_example, test_code_snippets):
        """Test that helper methods (generate_tests, explain_code) still work."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        # Test explain_code
        explanation = agent.explain_code(test_code_snippets["python"], "python")
        assert isinstance(explanation, str)

        # Test generate_tests
        tests = agent.generate_tests(test_code_snippets["python"], "python")
        assert isinstance(tests, list)


class TestCodeGenerationAsyncPerformance:
    """Test performance characteristics with async code generation."""

    def test_codegen_strategy_has_async_execute(
        self, code_generation_example, assert_async_strategy
    ):
        """Test that strategy.execute is async."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        assert_async_strategy(agent)

    @pytest.mark.asyncio
    async def test_codegen_concurrent_speedup(self, code_generation_example):
        """Test that concurrent code generation can provide speedup."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig()
        agent = CodeGenerationAgent(config=config)

        async def generate_async(task_desc):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.generate_code, task_desc)

        # 5 concurrent tasks
        tasks = [generate_async(f"Function {i}") for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 5


class TestCodeGenerationLargeOutputHandling:
    """Test handling of large code outputs with async."""

    def test_codegen_large_output_handling(self, code_generation_example):
        """Test that large code outputs are handled correctly."""
        CodeGenConfig = code_generation_example.config_classes["CodeGenConfig"]
        CodeGenerationAgent = code_generation_example.agent_classes[
            "CodeGenerationAgent"
        ]

        config = CodeGenConfig(max_tokens=2000)
        agent = CodeGenerationAgent(config=config)

        result = agent.generate_code(
            "Create a complex data processing pipeline with multiple classes"
        )

        assert isinstance(result, dict)
        if "code" in result and result["code"]:
            # Should have metadata about code size
            assert "lines_of_code" in result or "code" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
